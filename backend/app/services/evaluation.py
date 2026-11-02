"""Chronological walk-forward evaluation for ChargeQueue Phase 5."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .dataset_loader import iter_csv_chunks
from .forecasting_service import forecast_station


ALL_STATION_MODELS = [
    "seasonal_naive_daily",
    "seasonal_naive_weekly",
    "holt_winters_daily",
]
REPRESENTATIVE_MODELS = ["holt_winters_weekly", "sarima_daily"]
HORIZONS = {1: "30m", 2: "60m"}


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not math.isfinite(float(value)) else float(value)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return value


def chronological_split(timestamps: pd.Series | pd.DatetimeIndex, train_ratio: float = 0.70, validation_ratio: float = 0.15) -> dict[str, Any]:
    """Return shared positional split boundaries without shuffling."""

    index = pd.DatetimeIndex(pd.to_datetime(timestamps, utc=True))
    if len(index) < 10 or not index.is_monotonic_increasing:
        raise ValueError("timestamps must be a sufficiently long chronological sequence")
    train_end = int(len(index) * train_ratio)
    validation_end = int(len(index) * (train_ratio + validation_ratio))
    if not 0 < train_end < validation_end < len(index):
        raise ValueError("split ratios do not produce three non-empty partitions")
    return {
        "total_count": int(len(index)),
        "train_count": int(train_end),
        "validation_count": int(validation_end - train_end),
        "test_count": int(len(index) - validation_end),
        "train_start_position": 0,
        "train_end_position_exclusive": int(train_end),
        "validation_start_position": int(train_end),
        "validation_end_position_exclusive": int(validation_end),
        "test_start_position": int(validation_end),
        "test_end_position_exclusive": int(len(index)),
        "train_start_timestamp": index[0],
        "train_end_timestamp": index[train_end - 1],
        "validation_start_timestamp": index[train_end],
        "validation_end_timestamp": index[validation_end - 1],
        "test_start_timestamp": index[validation_end],
        "test_end_timestamp": index[-1],
    }


def evaluation_origins(split: dict[str, Any], partition: str, horizon_steps: int = 2, stride: int = 336) -> list[int]:
    """Return boundary-safe origins shared by every model and station."""

    if stride <= 0:
        raise ValueError("stride must be positive")
    if partition == "validation":
        start = int(split["validation_start_position"]) - 1
        last = int(split["validation_end_position_exclusive"]) - horizon_steps - 1
    elif partition == "test":
        start = int(split["test_start_position"]) - 1
        last = int(split["test_end_position_exclusive"]) - horizon_steps - 1
    else:
        raise ValueError("partition must be validation or test")
    if last < start:
        return []
    origins = list(range(start, last + 1, stride))
    if origins[-1] != last:
        origins.append(last)
    return origins


def mean_absolute_error(actual: Any, predicted: Any) -> float:
    actual_array = np.asarray(actual, dtype=float)
    predicted_array = np.asarray(predicted, dtype=float)
    if actual_array.size == 0 or actual_array.shape != predicted_array.shape:
        raise ValueError("actual and predicted arrays must be non-empty and have the same shape")
    return float(np.mean(np.abs(actual_array - predicted_array)))


def root_mean_squared_error(actual: Any, predicted: Any) -> float:
    actual_array = np.asarray(actual, dtype=float)
    predicted_array = np.asarray(predicted, dtype=float)
    if actual_array.size == 0 or actual_array.shape != predicted_array.shape:
        raise ValueError("actual and predicted arrays must be non-empty and have the same shape")
    return float(np.sqrt(np.mean((actual_array - predicted_array) ** 2)))


def assign_demand_groups(station_summary_path: Path) -> pd.DataFrame:
    """Assign equal-count low/medium/high groups by Phase 3 average demand rank."""

    summary = pd.read_csv(station_summary_path).sort_values("average_occupied_ports").reset_index(drop=True)
    if summary.empty:
        raise ValueError("station summary is empty")
    count = len(summary)
    labels = np.where(
        np.arange(count) < math.ceil(count / 3),
        "low",
        np.where(np.arange(count) < math.ceil(2 * count / 3), "medium", "high"),
    )
    return pd.DataFrame(
        {
            "station_id": summary["station_id"].astype(str),
            "average_occupied_ports": summary["average_occupied_ports"].astype(float),
            "demand_group": labels,
            "demand_rank_ascending": np.arange(1, count + 1),
        }
    )


def load_station_histories(processed_path: Path, station_ids: set[str] | None = None, chunksize: int = 100_000) -> dict[str, pd.DataFrame]:
    columns = ["station_id", "timestamp", "ports_occupied", "ports_total"]
    frames: dict[str, list[pd.DataFrame]] = {}
    for chunk in iter_csv_chunks(processed_path, chunksize=chunksize, usecols=columns):
        chunk["station_id"] = chunk["station_id"].astype(str)
        if station_ids is not None:
            chunk = chunk[chunk["station_id"].isin(station_ids)]
        for station_id, group in chunk.groupby("station_id", sort=False):
            frames.setdefault(station_id, []).append(group)
    histories: dict[str, pd.DataFrame] = {}
    for station_id, parts in frames.items():
        frame = pd.concat(parts, ignore_index=True)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        histories[station_id] = frame.sort_values("timestamp").reset_index(drop=True)
    if station_ids is not None and set(histories) != station_ids:
        raise ValueError(f"missing station histories: {sorted(station_ids.difference(histories))}")
    return histories


def _split_summary(histories: dict[str, pd.DataFrame], split: dict[str, Any], groups: pd.DataFrame) -> pd.DataFrame:
    rows = []
    group_map = groups.set_index("station_id")["demand_group"].to_dict()
    for station_id, frame in sorted(histories.items()):
        rows.append(
            {
                "station_id": station_id,
                "demand_group": group_map[station_id],
                "total_observations": len(frame),
                "train_observations": split["train_count"],
                "validation_observations": split["validation_count"],
                "test_observations": split["test_count"],
                "train_start_timestamp": frame["timestamp"].iloc[0].isoformat(),
                "train_end_timestamp": frame["timestamp"].iloc[split["train_count"] - 1].isoformat(),
                "validation_start_timestamp": frame["timestamp"].iloc[split["train_count"]].isoformat(),
                "validation_end_timestamp": frame["timestamp"].iloc[split["validation_end_position_exclusive"] - 1].isoformat(),
                "test_start_timestamp": frame["timestamp"].iloc[split["test_start_position"]].isoformat(),
                "test_end_timestamp": frame["timestamp"].iloc[-1].isoformat(),
            }
        )
    return pd.DataFrame(rows)


def _run_station_model(
    frame: pd.DataFrame,
    station_id: str,
    demand_group: str,
    model_name: str,
    partition: str,
    origins: list[int],
    history_limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    prediction_rows: list[dict[str, Any]] = []
    run_rows: list[dict[str, Any]] = []
    for origin_position in origins:
        origin_timestamp = frame["timestamp"].iloc[origin_position]
        historical = frame.iloc[: origin_position + 1].copy()
        started = time.perf_counter()
        try:
            result = forecast_station(historical, model_name, history_limit=history_limit)
            warnings_list = result["model_configuration"].get("model_warnings", [])
            run_rows.append(
                {
                    "station_id": station_id,
                    "demand_group": demand_group,
                    "model_name": model_name,
                    "partition": partition,
                    "origin_position": origin_position,
                    "forecast_origin": origin_timestamp.isoformat(),
                    "status": "completed",
                    "warning_count": len(warnings_list),
                    "warnings": " | ".join(warnings_list),
                    "error": "",
                    "elapsed_seconds": time.perf_counter() - started,
                }
            )
            for horizon_steps, suffix in HORIZONS.items():
                actual = float(frame["ports_occupied"].iloc[origin_position + horizon_steps])
                raw_prediction = float(result[f"raw_predicted_occupied_ports_{suffix}"])
                display_prediction = int(result[f"predicted_occupied_ports_{suffix}"])
                prediction_rows.append(
                    {
                        "station_id": station_id,
                        "demand_group": demand_group,
                        "model_name": model_name,
                        "partition": partition,
                        "forecast_origin": origin_timestamp.isoformat(),
                        "forecast_timestamp": frame["timestamp"].iloc[origin_position + horizon_steps].isoformat(),
                        "horizon_steps": horizon_steps,
                        "actual_occupied_ports": actual,
                        "raw_prediction": raw_prediction,
                        "display_prediction": display_prediction,
                        "error": raw_prediction - actual,
                        "absolute_error": abs(raw_prediction - actual),
                        "squared_error": (raw_prediction - actual) ** 2,
                        "raw_prediction_negative": raw_prediction < 0,
                    }
                )
        except Exception as exc:  # noqa: BLE001 - every failed origin is recorded
            run_rows.append(
                {
                    "station_id": station_id,
                    "demand_group": demand_group,
                    "model_name": model_name,
                    "partition": partition,
                    "origin_position": origin_position,
                    "forecast_origin": origin_timestamp.isoformat(),
                    "status": "failed",
                    "warning_count": 0,
                    "warnings": "",
                    "error": f"{type(exc).__name__}: {exc}",
                    "elapsed_seconds": time.perf_counter() - started,
                }
            )
    return prediction_rows, run_rows


def _metric_rows(predictions: pd.DataFrame, runs: pd.DataFrame, partition: str, station_count: int) -> pd.DataFrame:
    rows = []
    partition_predictions = predictions[predictions["partition"] == partition]
    partition_runs = runs[runs["partition"] == partition]
    for (model_name, horizon_steps), group in partition_predictions.groupby(["model_name", "horizon_steps"], sort=True):
        run_group = partition_runs[partition_runs["model_name"] == model_name]
        rows.append(
            {
                "partition": partition,
                "model_name": model_name,
                "horizon": HORIZONS[int(horizon_steps)],
                "horizon_steps": int(horizon_steps),
                "mae": mean_absolute_error(group["actual_occupied_ports"], group["raw_prediction"]),
                "rmse": root_mean_squared_error(group["actual_occupied_ports"], group["raw_prediction"]),
                "observation_count": len(group),
                "stations_with_predictions": int(group["station_id"].nunique()),
                "stations_requested": station_count if model_name in ALL_STATION_MODELS else int(run_group["station_id"].nunique()),
                "successful_fits": int((run_group["status"] == "completed").sum()),
                "failed_fits": int((run_group["status"] == "failed").sum()),
                "warning_count": int(run_group["warning_count"].sum()),
                "negative_raw_prediction_count": int(group["raw_prediction_negative"].sum()),
                "elapsed_seconds": float(run_group["elapsed_seconds"].sum()),
            }
        )
    return pd.DataFrame(rows).sort_values(["horizon_steps", "mae", "rmse", "model_name"])


def _station_metrics(predictions: pd.DataFrame, runs: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (partition, station_id, demand_group, model_name, horizon_steps), group in predictions.groupby(
        ["partition", "station_id", "demand_group", "model_name", "horizon_steps"], sort=True
    ):
        run_group = runs[(runs["partition"] == partition) & (runs["station_id"] == station_id) & (runs["model_name"] == model_name)]
        rows.append(
            {
                "partition": partition,
                "station_id": station_id,
                "demand_group": demand_group,
                "model_name": model_name,
                "horizon": HORIZONS[int(horizon_steps)],
                "horizon_steps": int(horizon_steps),
                "mae": mean_absolute_error(group["actual_occupied_ports"], group["raw_prediction"]),
                "rmse": root_mean_squared_error(group["actual_occupied_ports"], group["raw_prediction"]),
                "observation_count": len(group),
                "successful_fits": int((run_group["status"] == "completed").sum()),
                "failed_fits": int((run_group["status"] == "failed").sum()),
                "warning_count": int(run_group["warning_count"].sum()),
                "negative_raw_prediction_count": int(group["raw_prediction_negative"].sum()),
            }
        )
    return pd.DataFrame(rows)


def _group_metrics(station_metrics: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (partition, demand_group, model_name, horizon_steps), group in station_metrics.groupby(
        ["partition", "demand_group", "model_name", "horizon_steps"], sort=True
    ):
        rows.append(
            {
                "partition": partition,
                "demand_group": demand_group,
                "model_name": model_name,
                "horizon": HORIZONS[int(horizon_steps)],
                "horizon_steps": int(horizon_steps),
                "average_station_mae": float(group["mae"].mean()),
                "median_station_mae": float(group["mae"].median()),
                "average_station_rmse": float(group["rmse"].mean()),
                "median_station_rmse": float(group["rmse"].median()),
                "stations_evaluated": int(group["station_id"].nunique()),
                "successful_fits": int(group["successful_fits"].sum()),
                "failed_fits": int(group["failed_fits"].sum()),
                "warning_count": int(group["warning_count"].sum()),
            }
        )
    return pd.DataFrame(rows)


def select_validation_models(validation_metrics: pd.DataFrame, all_station_count: int) -> dict[str, Any]:
    """Select one full-coverage configuration per horizon using validation only."""

    eligible = validation_metrics[
        (validation_metrics["stations_with_predictions"] == all_station_count)
        & (validation_metrics["failed_fits"] == 0)
    ].copy()
    selected: dict[str, Any] = {}
    rankings: dict[str, list[dict[str, Any]]] = {}
    for horizon, group in eligible.groupby("horizon", sort=True):
        ranked = group.sort_values(["mae", "rmse", "warning_count", "elapsed_seconds", "model_name"]).reset_index(drop=True)
        rankings[horizon] = ranked.to_dict(orient="records")
        if not ranked.empty:
            selected[horizon] = ranked.iloc[0].to_dict()
    return {
        "selection_rule": "lowest validation MAE, then RMSE, then warning count, then elapsed time; only complete all-station configurations are eligible",
        "selected_by_horizon": selected,
        "validation_rankings": rankings,
        "representative_only_models_excluded_from_overall_selection": ["holt_winters_weekly", "sarima_daily"],
    }


def run_evaluation(
    processed_path: Path,
    station_summary_path: Path,
    output_dir: Path,
    *,
    stride: int = 336,
    history_limit: int = 1_000,
    chunksize: int = 100_000,
) -> dict[str, Any]:
    """Run all-station baseline/Holt-Winters and representative SARIMA evaluation."""

    output_dir.mkdir(parents=True, exist_ok=True)
    charts_dir = output_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    groups = assign_demand_groups(station_summary_path)
    all_histories = load_station_histories(processed_path, chunksize=chunksize)
    station_ids = set(all_histories)
    if station_ids != set(groups["station_id"]):
        raise ValueError("processed station IDs and Phase 3 station summary IDs do not match")
    reference_timestamps = all_histories[sorted(all_histories)[0]]["timestamp"]
    split = chronological_split(reference_timestamps)
    for station_id, frame in all_histories.items():
        if not frame["timestamp"].equals(reference_timestamps):
            raise ValueError(f"station {station_id} does not share the global timestamp sequence")
    split_frame = _split_summary(all_histories, split, groups)
    split_frame.to_csv(output_dir / "data_split_summary.csv", index=False)
    split_json = {
        "split_method": "chronological positional split using shared global timestamp sequence",
        "ratios": {"train": 0.70, "validation": 0.15, "test": 0.15},
        "split": split,
        "station_count": len(all_histories),
        "observations_per_station": int(len(reference_timestamps)),
        "no_overlap": True,
        "global_boundaries_apply_to_all_stations": True,
    }
    (output_dir / "data_split_summary.json").write_text(json.dumps(split_json, indent=2, default=_json_default), encoding="utf-8")
    representative_ids = {
        groups.iloc[0]["station_id"],
        groups.iloc[len(groups) // 2]["station_id"],
        groups.iloc[-1]["station_id"],
    }
    model_station_sets = {model: station_ids for model in ALL_STATION_MODELS}
    for model in REPRESENTATIVE_MODELS:
        model_station_sets[model] = representative_ids
    demand_group_map = groups.set_index("station_id")["demand_group"].to_dict()
    all_prediction_rows: list[dict[str, Any]] = []
    all_run_rows: list[dict[str, Any]] = []
    execution_started = time.perf_counter()
    origin_counts: dict[str, int] = {}
    for partition in ("validation", "test"):
        origins = evaluation_origins(split, partition, stride=stride)
        origin_counts[partition] = len(origins)
        for model_name, eligible_stations in model_station_sets.items():
            for station_id in sorted(eligible_stations):
                prediction_rows, run_rows = _run_station_model(
                    all_histories[station_id],
                    station_id,
                    demand_group_map[station_id],
                    model_name,
                    partition,
                    origins,
                    history_limit,
                )
                all_prediction_rows.extend(prediction_rows)
                all_run_rows.extend(run_rows)
    predictions = pd.DataFrame(all_prediction_rows)
    runs = pd.DataFrame(all_run_rows)
    if predictions.empty:
        raise RuntimeError("evaluation produced no successful predictions")
    predictions.to_csv(output_dir / "evaluation_predictions.csv", index=False)
    runs.to_csv(output_dir / "evaluation_run_log.csv", index=False)
    station_metrics = _station_metrics(predictions, runs)
    group_metrics = _group_metrics(station_metrics)
    station_metrics.to_csv(output_dir / "station_wise_metrics.csv", index=False)
    group_metrics.to_csv(output_dir / "demand_group_metrics.csv", index=False)
    validation_metrics = _metric_rows(predictions, runs, "validation", len(station_ids))
    test_metrics = _metric_rows(predictions, runs, "test", len(station_ids))
    validation_metrics.to_csv(output_dir / "validation_metrics.csv", index=False)
    test_metrics.to_csv(output_dir / "test_metrics.csv", index=False)
    selection = select_validation_models(validation_metrics, len(station_ids))
    selected_test_rows = []
    for horizon, selected in selection["selected_by_horizon"].items():
        selected_test_rows.append(
            test_metrics[
                (test_metrics["model_name"] == selected["model_name"])
                & (test_metrics["horizon"] == horizon)
            ].to_dict(orient="records")
        )
    selection["selected_test_metrics_for_reference_only"] = [row for rows in selected_test_rows for row in rows]
    selection["test_results_not_used_for_selection"] = True
    (output_dir / "model_selection.json").write_text(json.dumps(selection, indent=2, default=_json_default), encoding="utf-8")
    execution_by_model = []
    for model_name, group in runs.groupby("model_name", sort=True):
        execution_by_model.append(
            {
                "model_name": model_name,
                "stations_requested": int(len(model_station_sets[model_name])),
                "stations_with_completed_predictions": int(predictions[predictions["model_name"] == model_name]["station_id"].nunique()),
                "attempted_fits": int(len(group)),
                "successful_fits": int((group["status"] == "completed").sum()),
                "failed_fits": int((group["status"] == "failed").sum()),
                "warning_count": int(group["warning_count"].sum()),
                "elapsed_seconds": float(group["elapsed_seconds"].sum()),
                "failure_examples": group.loc[group["status"] == "failed", "error"].head(5).tolist(),
            }
        )
    execution_summary = {
        "target": "ports_occupied",
        "horizons": {"30m": 1, "60m": 2},
        "evaluation_stride_steps": stride,
        "evaluation_stride_minutes": stride * 30,
        "history_limit_for_statsmodels": history_limit,
        "origin_counts": origin_counts,
        "all_station_models": ALL_STATION_MODELS,
        "representative_station_models": REPRESENTATIVE_MODELS,
        "representative_station_ids": sorted(representative_ids),
        "execution_elapsed_seconds": time.perf_counter() - execution_started,
        "by_model": execution_by_model,
        "warnings_are_preserved": True,
        "metrics_use_raw_predictions": True,
        "display_predictions_excluded_from_metrics": True,
    }
    (output_dir / "model_execution_summary.json").write_text(json.dumps(execution_summary, indent=2, default=_json_default), encoding="utf-8")
    summary = {
        "dataset": {
            "processed_file": str(processed_path),
            "observations": int(sum(len(frame) for frame in all_histories.values())),
            "stations": len(all_histories),
            "observations_per_station": len(reference_timestamps),
            "timestamp_start": reference_timestamps.iloc[0],
            "timestamp_end": reference_timestamps.iloc[-1],
        },
        "split": split_json,
        "evaluation": {
            "stride_steps": stride,
            "stride_minutes": stride * 30,
            "origins_are_identical_for_compared_models": True,
            "two_step_forecasts_from_one_origin": True,
            "metrics_use_raw_predictions": True,
        },
        "validation_metrics": validation_metrics.to_dict(orient="records"),
        "test_metrics": test_metrics.to_dict(orient="records"),
        "selection": selection,
        "grouping": {
            "method": "ascending Phase 3 average_occupied_ports rank divided into three equal-count groups",
            "counts": groups["demand_group"].value_counts().sort_index().to_dict(),
            "minimum_average_by_group": groups.groupby("demand_group")["average_occupied_ports"].min().to_dict(),
            "maximum_average_by_group": groups.groupby("demand_group")["average_occupied_ports"].max().to_dict(),
        },
        "limitations": [
            "Stride is one week because refitting Statsmodels at every 30-minute origin across 150 stations is not computationally practical.",
            "Weekly Holt-Winters and SARIMA results cover only the low, medium, and high representative stations and are not complete 150-station comparisons.",
            "Weekly SARIMA was not evaluated.",
        ],
    }
    (output_dir / "evaluation_summary.json").write_text(json.dumps(summary, indent=2, default=_json_default), encoding="utf-8")
    return {
        "split": split_json,
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
        "station_metrics": station_metrics,
        "group_metrics": group_metrics,
        "predictions": predictions,
        "runs": runs,
        "selection": selection,
        "execution_summary": execution_summary,
        "summary": summary,
        "output_dir": output_dir,
        "charts_dir": charts_dir,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed", type=Path, default=Path("data/processed/ev_charging_processed.csv"))
    parser.add_argument("--station-summary", type=Path, default=Path("data/reports/eda/station_demand_summary.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/reports/evaluation"))
    parser.add_argument("--stride", type=int, default=336)
    parser.add_argument("--history-limit", type=int, default=1_000)
    args = parser.parse_args()
    result = run_evaluation(args.processed, args.station_summary, args.output_dir, stride=args.stride, history_limit=args.history_limit)
    print(json.dumps({"output_dir": str(result["output_dir"]), "validation_metrics": result["validation_metrics"].to_dict(orient="records"), "test_metrics": result["test_metrics"].to_dict(orient="records"), "selection": result["selection"]}, indent=2, default=_json_default))


if __name__ == "__main__":
    main()

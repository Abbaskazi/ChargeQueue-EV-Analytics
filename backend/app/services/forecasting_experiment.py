"""Bounded representative-station forecasting experiment for Phase 4."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .dataset_loader import iter_csv_chunks
from .forecasting_service import forecast_station
from .model_registry import registry_configuration


EXPERIMENT_MODELS = [
    "seasonal_naive_daily",
    "seasonal_naive_weekly",
    "holt_winters_daily",
    "holt_winters_weekly",
    "sarima_daily",
]


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(float(value)) else float(value)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, Path):
        return str(value)
    return value


def select_representative_stations(summary_path: Path) -> pd.DataFrame:
    """Select high, median, and low demand stations from Phase 3 results."""

    summary = pd.read_csv(summary_path).sort_values("average_occupied_ports").reset_index(drop=True)
    if summary.empty:
        raise ValueError("station summary is empty")
    indexes = {"low": 0, "medium": (len(summary) - 1) // 2, "high": len(summary) - 1}
    rows = []
    for group, index in indexes.items():
        row = summary.iloc[index]
        rows.append(
            {
                "selection_group": group,
                "station_id": str(row["station_id"]),
                "average_occupied_ports": float(row["average_occupied_ports"]),
                "average_operational_utilization": float(row["average_operational_utilization"]),
                "selection_basis": "low, median, or high station average occupied ports from Phase 3 station_demand_summary.csv",
            }
        )
    return pd.DataFrame(rows)


def _load_selected_histories(processed_path: Path, station_ids: set[str], chunksize: int = 100_000) -> dict[str, pd.DataFrame]:
    columns = ["station_id", "timestamp", "ports_occupied", "ports_total"]
    frames: dict[str, list[pd.DataFrame]] = {station_id: [] for station_id in station_ids}
    for chunk in iter_csv_chunks(processed_path, chunksize=chunksize, usecols=columns):
        selected = chunk[chunk["station_id"].astype(str).isin(station_ids)].copy()
        for station_id, group in selected.groupby(selected["station_id"].astype(str), sort=False):
            frames[station_id].append(group)
    return {
        station_id: pd.concat(parts, ignore_index=True).sort_values("timestamp").reset_index(drop=True)
        for station_id, parts in frames.items()
        if parts
    }


def run_experiment(
    processed_path: Path,
    station_summary_path: Path,
    output_dir: Path,
    *,
    chunksize: int = 100_000,
    history_limit: int = 2_000,
) -> dict[str, Any]:
    """Run model execution only; no train/test split or evaluation metrics."""

    output_dir.mkdir(parents=True, exist_ok=True)
    selection = select_representative_stations(station_summary_path)
    selection.to_csv(output_dir / "representative_station_selection.csv", index=False)
    station_ids = set(selection["station_id"])
    histories = _load_selected_histories(processed_path, station_ids, chunksize=chunksize)
    rows: list[dict[str, Any]] = []
    execution: list[dict[str, Any]] = []
    for selection_row in selection.to_dict(orient="records"):
        station_id = selection_row["station_id"]
        history = histories.get(station_id)
        if history is None:
            raise RuntimeError(f"selected station {station_id} was not found in processed data")
        capacity = int(history["ports_total"].iloc[0]) if history["ports_total"].nunique() == 1 else None
        for model_name in EXPERIMENT_MODELS:
            started = time.perf_counter()
            record: dict[str, Any] = {
                "station_id": station_id,
                "selection_group": selection_row["selection_group"],
                "model_name": model_name,
                "model_status": "failed",
            }
            try:
                result = forecast_station(history, model_name, station_capacity=capacity, history_limit=history_limit)
                record.update(result)
                record["selection_group"] = selection_row["selection_group"]
                rows.append(record)
                status = "completed"
                error = None
            except Exception as exc:  # noqa: BLE001 - report each model failure without fabricating output
                record["error"] = f"{type(exc).__name__}: {exc}"
                rows.append(record)
                status = "failed"
                error = record["error"]
            execution.append(
                {
                    "station_id": station_id,
                    "selection_group": selection_row["selection_group"],
                    "model_name": model_name,
                    "status": status,
                    "error": error,
                    "elapsed_seconds": round(time.perf_counter() - started, 3),
                    "history_observations_available": int(len(history)),
                    "history_observations_used": min(int(len(history)), history_limit),
                }
            )
    pd.DataFrame(rows).to_csv(output_dir / "sample_forecasts.csv", index=False)
    completed = sum(item["status"] == "completed" for item in execution)
    summary = {
        "experiment_type": "representative_station_development_execution",
        "formal_evaluation": False,
        "evaluation_metrics": None,
        "target": "ports_occupied",
        "horizon_steps": 2,
        "step_minutes": 30,
        "history_limit_for_statsmodels": history_limit,
        "selected_stations": selection.to_dict(orient="records"),
        "models_attempted": EXPERIMENT_MODELS,
        "completed_runs": completed,
        "failed_runs": len(execution) - completed,
        "runs": execution,
        "weekly_sarima": "Not run in the representative experiment because a 336-step seasonal state-space fit was outside the bounded initial experiment; the registered configuration remains available for a later controlled trial.",
    }
    (output_dir / "forecasting_execution_summary.json").write_text(json.dumps(summary, indent=2, default=_json_default), encoding="utf-8")
    configuration = {
        "seasonal_periods": {"daily": 48, "weekly": 336},
        "registered_models": registry_configuration(),
        "experiment_models": EXPERIMENT_MODELS,
        "history_limit_for_statsmodels": history_limit,
        "display_postprocessing": {
            "raw_predictions_preserved": True,
            "display_predictions": "rounded to nearest integer, clamped to non-negative, and capped only when ports_total is constant for the station",
        },
        "leakage_controls": [
            "station histories sorted by timestamp",
            "forecast origin is the last supplied historical timestamp",
            "only observations at or before the origin are used",
            "no random shuffling, future measurements, or evaluation split",
        ],
    }
    (output_dir / "model_configuration.json").write_text(json.dumps(configuration, indent=2, default=_json_default), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed", type=Path, default=Path("data/processed/ev_charging_processed.csv"))
    parser.add_argument("--station-summary", type=Path, default=Path("data/reports/eda/station_demand_summary.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/reports/forecasting"))
    parser.add_argument("--history-limit", type=int, default=2_000)
    args = parser.parse_args()
    result = run_experiment(args.processed, args.station_summary, args.output_dir, history_limit=args.history_limit)
    print(json.dumps(result, indent=2, default=_json_default))


if __name__ == "__main__":
    main()


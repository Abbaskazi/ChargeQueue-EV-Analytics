"""Matplotlib charts for Phase 5 evaluation outputs."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def _bar_metric(metrics: pd.DataFrame, metric: str, horizon: str, path: Path, title: str) -> None:
    frame = metrics[metrics["horizon"] == horizon].sort_values(metric)
    plt.figure(figsize=(10, 5))
    plt.bar(frame["model_name"], frame[metric], color="#2563eb")
    plt.ylabel(metric.upper())
    plt.xlabel("Model configuration")
    plt.title(title)
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def create_evaluation_charts(output_dir: Path, validation: pd.DataFrame, station: pd.DataFrame, groups: pd.DataFrame, predictions: pd.DataFrame) -> list[str]:
    charts: list[str] = []
    for metric in ("mae", "rmse"):
        for horizon, label in (("30m", "30 minutes"), ("60m", "60 minutes")):
            filename = f"model_{metric}_{horizon}.png"
            _bar_metric(validation, metric, horizon, output_dir / filename, f"Validation {metric.upper()} comparison at {label}")
            charts.append(filename)

    full_station = station[station["model_name"].isin(validation[validation["stations_requested"] == validation["stations_requested"].max()]["model_name"].unique())]
    plt.figure(figsize=(11, 6))
    for model_name, frame in full_station[full_station["horizon"] == "60m"].groupby("model_name"):
        plt.plot(frame["station_id"], frame["mae"], marker="o", label=model_name)
    plt.xlabel("Station ID")
    plt.ylabel("Station MAE")
    plt.title("Station-wise validation MAE at 60 minutes")
    plt.xticks(rotation=90, fontsize=6)
    plt.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(output_dir / "station_wise_mae.png", dpi=150)
    plt.close()
    charts.append("station_wise_mae.png")

    group_plot = groups[(groups["partition"] == "validation") & (groups["horizon"] == "60m")]
    pivot = group_plot.pivot_table(index="demand_group", columns="model_name", values="average_station_mae")
    ax = pivot.plot(kind="bar", figsize=(10, 5))
    ax.set_ylabel("Average station MAE")
    ax.set_xlabel("Demand group")
    ax.set_title("Validation performance by demand group at 60 minutes")
    plt.xticks(rotation=0)
    plt.tight_layout()
    plt.savefig(output_dir / "demand_group_performance.png", dpi=150)
    plt.close()
    charts.append("demand_group_performance.png")

    representative_stations = predictions.loc[predictions["model_name"] == "sarima_daily", "station_id"].drop_duplicates().tolist()
    selected = predictions[(predictions["partition"] == "test") & (predictions["station_id"].isin(representative_stations)) & (predictions["model_name"] == "seasonal_naive_daily")]
    selected = selected[selected["horizon_steps"] == 1].copy()
    if not selected.empty:
        selected["forecast_timestamp"] = pd.to_datetime(selected["forecast_timestamp"], utc=True)
        plt.figure(figsize=(12, 6))
        for station_id, frame in selected.groupby("station_id"):
            frame = frame.sort_values("forecast_timestamp")
            plt.plot(frame["forecast_timestamp"], frame["actual_occupied_ports"], label=f"{station_id} actual")
            plt.plot(frame["forecast_timestamp"], frame["raw_prediction"], linestyle="--", label=f"{station_id} predicted")
        plt.xlabel("Timestamp")
        plt.ylabel("Occupied ports")
        plt.title("Test actual versus predicted occupied ports, 30-minute horizon")
        plt.legend(fontsize=8)
        plt.tight_layout()
        plt.savefig(output_dir / "actual_vs_predicted_selected_stations.png", dpi=150)
        plt.close()
        charts.append("actual_vs_predicted_selected_stations.png")

    errors = predictions[predictions["partition"] == "test"].copy()
    plt.figure(figsize=(10, 5))
    for model_name, frame in errors.groupby("model_name"):
        plt.hist(frame["error"], bins=25, alpha=0.45, label=model_name)
    plt.xlabel("Raw prediction error (prediction - actual)")
    plt.ylabel("Frequency")
    plt.title("Test forecast error distribution")
    plt.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(output_dir / "forecast_error_distribution.png", dpi=150)
    plt.close()
    charts.append("forecast_error_distribution.png")
    return charts

"""Plotting functions for ChargeQueue Phase 3 exploratory analysis."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd


plt.rcParams.update({"axes.grid": True, "grid.alpha": 0.25})


def _save(fig: plt.Figure, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_hourly_demand(frame: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(frame["hour"], frame["average_occupied_ports"], marker="o", label="Average")
    ax.plot(frame["hour"], frame["median_occupied_ports"], marker="o", label="Median")
    ax.set_title("Occupied Ports by Hour of Day")
    ax.set_xlabel("Hour of day (UTC)")
    ax.set_ylabel("Occupied ports")
    ax.set_xticks(frame["hour"])
    ax.legend()
    _save(fig, path)


def plot_weekday_demand(frame: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(frame["weekday_name"], frame["average_occupied_ports"], color="#2f6f9f")
    ax.set_title("Average Occupied Ports by Day of Week")
    ax.set_xlabel("Day of week")
    ax.set_ylabel("Average occupied ports")
    ax.tick_params(axis="x", rotation=20)
    _save(fig, path)


def plot_monthly_demand(frame: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(frame["month_name"], frame["average_occupied_ports"], marker="o", color="#2f6f9f")
    ax.set_title("Average Occupied Ports by Month")
    ax.set_xlabel("Month")
    ax.set_ylabel("Average occupied ports")
    ax.tick_params(axis="x", rotation=20)
    _save(fig, path)


def plot_daily_demand(frame: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(pd.to_datetime(frame["date"]), frame["average_occupied_ports"], color="#2f6f9f", linewidth=1.4)
    ax.set_title("Daily Mean Occupied Ports")
    ax.set_xlabel("Date")
    ax.set_ylabel("Mean occupied ports")
    _save(fig, path)


def plot_top_stations(frame: pd.DataFrame, path: Path) -> None:
    ordered = frame.sort_values("average_occupied_ports")
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.barh(ordered["station_id"], ordered["average_occupied_ports"], color="#2f6f9f")
    ax.set_title("Top 10 Stations by Average Occupied Ports")
    ax.set_xlabel("Average occupied ports")
    ax.set_ylabel("Station")
    _save(fig, path)


def plot_station_utilization(frame: pd.DataFrame, path: Path) -> None:
    ordered = frame.sort_values("average_operational_utilization")
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.barh(ordered["station_id"], ordered["average_operational_utilization"], color="#d97941")
    ax.set_title("Top 10 Stations by Operational Utilization")
    ax.set_xlabel("Average operational utilization")
    ax.set_ylabel("Station")
    _save(fig, path)


def plot_occupancy_distribution(values: pd.Series, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))
    minimum = int(values.min())
    maximum = int(values.max())
    bins = range(minimum, maximum + 2)
    ax.hist(values, bins=bins, align="left", rwidth=0.9, color="#2f6f9f")
    ax.set_title("Distribution of Occupied Ports")
    ax.set_xlabel("Occupied ports")
    ax.set_ylabel("Observation count")
    _save(fig, path)


def plot_occupancy_boxplot(values: pd.Series, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 3.5))
    box = ax.boxplot(values, vert=False, patch_artist=True, flierprops={"markersize": 2})
    for patch in box["boxes"]:
        patch.set_facecolor("#9ecae1")
    ax.set_title("Occupied-Port Boxplot")
    ax.set_xlabel("Occupied ports")
    _save(fig, path)


def plot_hour_weekday_heatmap(frame: pd.DataFrame, path: Path) -> None:
    pivot = frame.pivot(index="weekday_name", columns="hour", values="average_occupied_ports")
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    pivot = pivot.reindex(order)
    fig, ax = plt.subplots(figsize=(13, 5))
    image = ax.imshow(pivot.to_numpy(dtype=float), aspect="auto", cmap="YlOrRd")
    ax.set_xticks(range(len(pivot.columns)), labels=[str(hour) for hour in pivot.columns])
    ax.set_yticks(range(len(pivot.index)), labels=pivot.index)
    fig.colorbar(image, ax=ax, label="Average occupied ports")
    ax.set_title("Average Occupied Ports by Weekday and Hour (UTC)")
    ax.set_xlabel("Hour of day")
    ax.set_ylabel("Day of week")
    _save(fig, path)


def plot_weekday_weekend(frame: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    for period, group in frame.groupby("period_type", sort=False):
        ax.plot(group["hour"], group["average_occupied_ports"], marker="o", label=period)
    ax.set_title("Weekday and Weekend Hourly Demand")
    ax.set_xlabel("Hour of day (UTC)")
    ax.set_ylabel("Average occupied ports")
    ax.set_xticks(range(24))
    ax.legend()
    _save(fig, path)


def plot_occupancy_outliers(daily_frame: pd.DataFrame, upper_bound: float, lower_bound: float, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 5))
    dates = pd.to_datetime(daily_frame["date"])
    ax.plot(dates, daily_frame["maximum_occupied_ports"], color="#2f6f9f", label="Daily maximum")
    ax.axhline(upper_bound, color="#c0392b", linestyle="--", label=f"Upper IQR bound ({upper_bound:.2f})")
    ax.axhline(lower_bound, color="#d97941", linestyle="--", label=f"Lower IQR bound ({lower_bound:.2f})")
    ax.set_title("Daily Maximum Occupied Ports and IQR Bounds")
    ax.set_xlabel("Date")
    ax.set_ylabel("Occupied ports")
    ax.legend()
    _save(fig, path)


def create_all_charts(
    output_dir: Path,
    hourly: pd.DataFrame,
    weekday: pd.DataFrame,
    monthly: pd.DataFrame,
    daily: pd.DataFrame,
    top_stations: pd.DataFrame,
    top_utilization: pd.DataFrame,
    occupancy_values: pd.Series,
    heatmap: pd.DataFrame,
    weekday_weekend: pd.DataFrame,
    upper_bound: float,
    lower_bound: float,
) -> list[str]:
    """Create all Phase 3 charts from the same summary frames saved as CSV."""

    plot_hourly_demand(hourly, output_dir / "hourly_demand.png")
    plot_weekday_demand(weekday, output_dir / "weekday_demand.png")
    plot_monthly_demand(monthly, output_dir / "monthly_demand.png")
    plot_daily_demand(daily, output_dir / "daily_demand_trend.png")
    plot_top_stations(top_stations, output_dir / "top_stations.png")
    plot_station_utilization(top_utilization, output_dir / "station_utilization.png")
    plot_occupancy_distribution(occupancy_values, output_dir / "occupancy_distribution.png")
    plot_occupancy_boxplot(occupancy_values, output_dir / "occupancy_boxplot.png")
    plot_hour_weekday_heatmap(heatmap, output_dir / "hour_weekday_heatmap.png")
    plot_weekday_weekend(weekday_weekend, output_dir / "weekday_weekend_comparison.png")
    plot_occupancy_outliers(daily, upper_bound, lower_bound, output_dir / "occupancy_outliers.png")
    return [
        "hourly_demand.png",
        "weekday_demand.png",
        "monthly_demand.png",
        "daily_demand_trend.png",
        "top_stations.png",
        "station_utilization.png",
        "occupancy_distribution.png",
        "occupancy_boxplot.png",
        "hour_weekday_heatmap.png",
        "weekday_weekend_comparison.png",
        "occupancy_outliers.png",
    ]

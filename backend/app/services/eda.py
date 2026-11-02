"""Chunked, reproducible exploratory analysis for ChargeQueue Phase 3."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .data_validator import parse_timestamps
from .dataset_loader import iter_csv_chunks, read_csv_header
from .eda_visualizations import create_all_charts


EDA_COLUMNS = ["timestamp", "station_id", "ports_occupied", "operational_utilization"]
WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTH_NAMES = {7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December"}
EDA_CHUNK_SIZE = 100_000


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not math.isfinite(float(value)) else float(value)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if pd.isna(value):
        return None
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, default=_json_value)


def _safe_percentage(value: int | float, denominator: int | float) -> float | None:
    return None if not denominator else float(value) / float(denominator) * 100.0


def summary_statistics(values: pd.Series | np.ndarray) -> dict[str, float | int | None]:
    """Return descriptive statistics for a finite numeric series."""

    array = np.asarray(pd.Series(values).dropna(), dtype=float)
    if array.size == 0:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "standard_deviation": None,
            "minimum": None,
            "maximum": None,
            "q1": None,
            "q3": None,
            "skewness": None,
        }
    series = pd.Series(array)
    return {
        "count": int(array.size),
        "mean": float(array.mean()),
        "median": float(np.median(array)),
        "standard_deviation": float(array.std(ddof=1)) if array.size > 1 else 0.0,
        "minimum": float(array.min()),
        "maximum": float(array.max()),
        "q1": float(np.quantile(array, 0.25)),
        "q3": float(np.quantile(array, 0.75)),
        "skewness": float(series.skew()) if array.size > 2 else 0.0,
    }


def iqr_outlier_bounds(values: pd.Series | np.ndarray) -> tuple[float, float, float, float, float]:
    """Return q1, q3, IQR, lower bound, and upper bound using the 1.5 IQR rule."""

    array = np.asarray(pd.Series(values).dropna(), dtype=float)
    if array.size == 0:
        raise ValueError("Cannot calculate IQR bounds for an empty series")
    q1, q3 = np.quantile(array, [0.25, 0.75])
    iqr = q3 - q1
    return float(q1), float(q3), float(iqr), float(q1 - 1.5 * iqr), float(q3 + 1.5 * iqr)


@dataclass
class GroupAccumulator:
    """Collect bounded arrays per group for exact count, mean, median, and extrema."""

    values: dict[str, list[np.ndarray]] = field(default_factory=dict)

    def add(self, keys: pd.Series, values: pd.Series) -> None:
        frame = pd.DataFrame({"key": keys, "value": pd.to_numeric(values, errors="coerce")})
        frame = frame.dropna(subset=["key", "value"])
        if frame.empty:
            return
        frame["key"] = frame["key"].astype(str)
        for key, group in frame.groupby("key", sort=False)["value"]:
            self.values.setdefault(key, []).append(group.to_numpy(dtype=float, copy=True))

    def frame(self, key_name: str) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for key in sorted(self.values):
            array = np.concatenate(self.values[key])
            rows.append(
                {
                    key_name: key,
                    "count": int(array.size),
                    "sum": float(array.sum()),
                    "average": float(array.mean()),
                    "median": float(np.median(array)),
                    "minimum": float(array.min()),
                    "maximum": float(array.max()),
                }
            )
        return pd.DataFrame(rows)


def _format_hourly(accumulator: GroupAccumulator) -> pd.DataFrame:
    frame = accumulator.frame("hour")
    frame["hour"] = frame["hour"].astype(int)
    frame = frame.sort_values("hour").rename(
        columns={
            "average": "average_occupied_ports",
            "median": "median_occupied_ports",
            "maximum": "maximum_occupied_ports",
            "minimum": "minimum_occupied_ports",
        }
    )
    return frame[["hour", "count", "average_occupied_ports", "median_occupied_ports", "minimum_occupied_ports", "maximum_occupied_ports"]]


def _format_weekday(accumulator: GroupAccumulator) -> pd.DataFrame:
    frame = accumulator.frame("day_of_week")
    frame["day_of_week"] = frame["day_of_week"].astype(int)
    frame["weekday_name"] = frame["day_of_week"].map(dict(enumerate(WEEKDAY_NAMES)))
    frame = frame.sort_values("day_of_week").rename(
        columns={
            "average": "average_occupied_ports",
            "median": "median_occupied_ports",
            "maximum": "maximum_occupied_ports",
            "minimum": "minimum_occupied_ports",
        }
    )
    return frame[["day_of_week", "weekday_name", "count", "average_occupied_ports", "median_occupied_ports", "minimum_occupied_ports", "maximum_occupied_ports"]]


def _format_monthly(occupied: GroupAccumulator, utilization: GroupAccumulator) -> pd.DataFrame:
    frame = occupied.frame("month")
    frame["month"] = frame["month"].astype(int)
    frame["month_name"] = frame["month"].map(MONTH_NAMES)
    util = utilization.frame("month")
    util["month"] = util["month"].astype(int)
    util = util.rename(columns={"average": "average_operational_utilization", "count": "valid_utilization_observations"})
    frame = frame.merge(util[["month", "average_operational_utilization", "valid_utilization_observations"]], on="month", how="left")
    frame["occupied_observation_count"] = frame["count"]
    frame["occupied_ports_sum"] = frame["sum"]
    frame = frame.sort_values("month").rename(
        columns={
            "average": "average_occupied_ports",
            "median": "median_occupied_ports",
            "maximum": "maximum_occupied_ports",
            "minimum": "minimum_occupied_ports",
        }
    )
    return frame[["month", "month_name", "occupied_observation_count", "occupied_ports_sum", "average_occupied_ports", "median_occupied_ports", "minimum_occupied_ports", "maximum_occupied_ports", "average_operational_utilization", "valid_utilization_observations"]]


def _format_station(occupied: GroupAccumulator, utilization: GroupAccumulator) -> pd.DataFrame:
    frame = occupied.frame("station_id")
    util = utilization.frame("station_id")
    util = util.rename(columns={"average": "average_operational_utilization", "count": "valid_utilization_observations"})
    frame = frame.merge(util[["station_id", "average_operational_utilization", "valid_utilization_observations"]], on="station_id", how="left")
    return frame.rename(
        columns={
            "count": "observation_count",
            "sum": "occupied_ports_sum",
            "average": "average_occupied_ports",
            "median": "median_occupied_ports",
            "minimum": "minimum_occupied_ports",
            "maximum": "maximum_occupied_ports",
        }
    ).sort_values("station_id")


def _format_daily(accumulator: GroupAccumulator) -> pd.DataFrame:
    frame = accumulator.frame("date").sort_values("date")
    return frame.rename(
        columns={
            "count": "observation_count",
            "sum": "occupied_ports_sum",
            "average": "average_occupied_ports",
            "median": "median_occupied_ports",
            "minimum": "minimum_occupied_ports",
            "maximum": "maximum_occupied_ports",
        }
    )


def _format_heatmap(accumulator: GroupAccumulator) -> pd.DataFrame:
    frame = accumulator.frame("weekday_hour")
    split = frame["weekday_hour"].str.split("_", n=1, expand=True)
    frame["day_of_week"] = split[0].astype(int)
    frame["hour"] = split[1].astype(int)
    frame["weekday_name"] = frame["day_of_week"].map(dict(enumerate(WEEKDAY_NAMES)))
    return frame.sort_values(["day_of_week", "hour"]).rename(columns={"average": "average_occupied_ports"})[
        ["day_of_week", "weekday_name", "hour", "count", "average_occupied_ports", "median", "minimum", "maximum"]
    ].rename(columns={"median": "median_occupied_ports", "minimum": "minimum_occupied_ports", "maximum": "maximum_occupied_ports"})


def _format_weekend(accumulator: GroupAccumulator) -> pd.DataFrame:
    frame = accumulator.frame("period_hour")
    split = frame["period_hour"].str.split("_", n=1, expand=True)
    frame["period_type"] = split[0]
    frame["hour"] = split[1].astype(int)
    return frame.sort_values(["period_type", "hour"]).rename(
        columns={
            "average": "average_occupied_ports",
            "median": "median_occupied_ports",
            "minimum": "minimum_occupied_ports",
            "maximum": "maximum_occupied_ports",
        }
    )[["period_type", "hour", "count", "average_occupied_ports", "median_occupied_ports", "minimum_occupied_ports", "maximum_occupied_ports"]]


def _run_adf(station_values: dict[str, list[np.ndarray]], stations: list[str]) -> list[dict[str, Any]]:
    try:
        from statsmodels.tsa.stattools import adfuller
    except ImportError:
        return [{"station_id": station, "status": "statsmodels unavailable"} for station in stations]
    rows: list[dict[str, Any]] = []
    for station in stations:
        values = np.concatenate(station_values[station])
        try:
            result = adfuller(values, regression="c", autolag="AIC")
            rows.append(
                {
                    "station_id": station,
                    "observations": int(len(values)),
                    "adf_statistic": float(result[0]),
                    "p_value": float(result[1]),
                    "used_lag": int(result[2]),
                    "status": "completed",
                }
            )
        except Exception as exc:  # pragma: no cover - protects the full EDA run from one series
            rows.append({"station_id": station, "observations": int(len(values)), "status": f"failed: {exc}"})
    return rows


def _write_suitability_report(
    path: Path,
    overview: dict[str, Any],
    hourly: pd.DataFrame,
    weekday: pd.DataFrame,
    daily: pd.DataFrame,
    station_summary: pd.DataFrame,
    adf_rows: list[dict[str, Any]],
) -> None:
    busiest_hour = hourly.loc[hourly["average_occupied_ports"].idxmax()]
    least_hour = hourly.loc[hourly["average_occupied_ports"].idxmin()]
    highest_weekday = weekday.loc[weekday["average_occupied_ports"].idxmax()]
    lowest_weekday = weekday.loc[weekday["average_occupied_ports"].idxmin()]
    daily_index = np.arange(len(daily), dtype=float)
    daily_slope = float(np.polyfit(daily_index, daily["average_occupied_ports"], 1)[0]) if len(daily) > 1 else 0.0
    lines = [
        "# Forecasting Suitability",
        "",
        "## Scope",
        "",
        "This is an exploratory assessment of whether `ports_occupied` is suitable for future time-series forecasting. No forecasting model, train/validation/test split, or model evaluation was performed in Phase 3.",
        "",
        "## Evidence from the dataset",
        "",
        f"- The processed dataset contains {overview['total_observations']:,} observations from {overview['total_stations']} stations.",
        f"- Each station has a regular {overview['sampling_frequency_minutes']}-minute interval and the observed UTC range is {overview['minimum_timestamp_utc']} to {overview['maximum_timestamp_utc']}.",
        f"- Average occupied ports are {overview['average_occupied_ports']:.4f}; the observed range is {overview['minimum_occupied_ports']:.0f} to {overview['maximum_occupied_ports']:.0f}.",
        f"- The highest average hourly demand occurs at {int(busiest_hour['hour']):02d}:00 UTC ({busiest_hour['average_occupied_ports']:.4f}), while the lowest occurs at {int(least_hour['hour']):02d}:00 UTC ({least_hour['average_occupied_ports']:.4f}).",
        f"- The highest average weekday demand is on {highest_weekday['weekday_name']} ({highest_weekday['average_occupied_ports']:.4f}); the lowest is on {lowest_weekday['weekday_name']} ({lowest_weekday['average_occupied_ports']:.4f}).",
        f"- The daily mean occupied-port trend has an exploratory linear slope of {daily_slope:.6f} ports per day. This is descriptive and is not a formal stationarity test.",
        f"- Station average demand ranges from {station_summary['average_occupied_ports'].min():.4f} to {station_summary['average_occupied_ports'].max():.4f}, supporting examination of station-specific behavior.",
        "",
        "## Seasonality interpretation",
        "",
        "The repeated hourly and weekday profiles are observed recurring patterns in the historical data. They support testing daily (48 half-hour steps) and weekly (336 half-hour steps) seasonal baselines or features in a later phase, but the charts alone do not formally establish seasonal stationarity.",
        "",
        "## Illustrative stationarity assessment",
        "",
        "The Augmented Dickey-Fuller (ADF) test has the null hypothesis that a unit root is present, which is commonly interpreted as non-stationarity. Results below apply only to the listed representative station series and must not be generalized to every station.",
        "",
        "| Station | Observations | ADF statistic | p-value | Status |",
        "|---|---:|---:|---:|---|",
    ]
    for row in adf_rows:
        lines.append(
            f"| {row.get('station_id', '')} | {row.get('observations', '')} | {row.get('adf_statistic', '')} | {row.get('p_value', '')} | {row.get('status', '')} |"
        )
    lines += [
        "",
        "## Assessment",
        "",
        "The data is suitable for forecasting preparation because it has a long, regular station-wise history, a clearly defined occupied-port target, and visible time-of-day and weekday variation. Candidate models should account for station-level scale differences and should compare seasonal baselines against more complex methods after chronological evaluation is authorized.",
        "",
        "The supplied `utilization_rate` should not replace `ports_occupied` as the target. Operational utilization is useful for descriptive analysis, but zero denominators are null and the supplied utilization field disagrees with the operational formula for most comparable rows.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_eda_report(
    path: Path,
    overview: dict[str, Any],
    quality: dict[str, Any],
    hourly: pd.DataFrame,
    weekday: pd.DataFrame,
    monthly: pd.DataFrame,
    daily: pd.DataFrame,
    station_summary: pd.DataFrame,
    distribution: dict[str, Any],
    outlier: dict[str, Any],
    adf_rows: list[dict[str, Any]],
) -> None:
    busiest_hour = hourly.loc[hourly["average_occupied_ports"].idxmax()]
    least_hour = hourly.loc[hourly["average_occupied_ports"].idxmin()]
    highest_weekday = weekday.loc[weekday["average_occupied_ports"].idxmax()]
    lowest_weekday = weekday.loc[weekday["average_occupied_ports"].idxmin()]
    highest_month = monthly.loc[monthly["average_occupied_ports"].idxmax()]
    lowest_month = monthly.loc[monthly["average_occupied_ports"].idxmin()]
    top_station = station_summary.loc[station_summary["average_occupied_ports"].idxmax()]
    top_util = station_summary.dropna(subset=["average_operational_utilization"]).loc[
        station_summary.dropna(subset=["average_operational_utilization"])["average_operational_utilization"].idxmax()
    ]
    charts = [
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
    lines = [
        "# ChargeQueue Exploratory Data Analysis",
        "",
        "## 1. Introduction",
        "",
        "This Phase 3 analysis describes historical EV charging demand using `ports_occupied` as the primary demand variable and `operational_utilization` as a separate descriptive measure. It does not train or evaluate forecasting models.",
        "",
        "## 2. Dataset overview",
        "",
        f"The processed dataset contains {overview['total_observations']:,} observations from {overview['total_stations']} stations across {overview['processed_columns']} processed columns ({overview['original_columns']} original source columns). The UTC range is {overview['minimum_timestamp_utc']} to {overview['maximum_timestamp_utc']}, with a regular {overview['sampling_frequency_minutes']}-minute station interval.",
        "",
        f"Average occupied ports are {overview['average_occupied_ports']:.4f}, with a median of {overview['median_occupied_ports']:.4f} and a range of {overview['minimum_occupied_ports']:.0f} to {overview['maximum_occupied_ports']:.0f}. Average operational utilization, excluding {overview['zero_denominator_utilization_records']:,} zero-denominator rows, is {overview['average_operational_utilization']:.6f}.",
        "",
        "## 3. Data quality recap",
        "",
        f"Phase 2 found {quality['missing_values']['total_missing_cells']:,} missing cells, {quality['duplicates']['fully_duplicated_rows_extra_occurrences']:,} extra fully duplicated rows, and {quality['duplicates']['duplicated_station_timestamp_rows_extra_occurrences']:,} extra duplicated station-timestamp rows. There were no invalid timestamps, port-balance violations, or irregular station intervals.",
        "",
        "The supplied `utilization_rate` is retained but not substituted for operational utilization. Estimated wait time is not treated as reliable real-world queue waiting time because its methodology is unverified and most values are zero.",
        "",
        "## 4. Hourly demand findings",
        "",
        f"The busiest average hour is {int(busiest_hour['hour']):02d}:00 UTC with {busiest_hour['average_occupied_ports']:.4f} occupied ports. The least busy average hour is {int(least_hour['hour']):02d}:00 UTC with {least_hour['average_occupied_ports']:.4f}. See [hourly_demand.png](hourly_demand.png).",
        "",
        "## 5. Day-of-week findings",
        "",
        f"{highest_weekday['weekday_name']} has the highest average demand at {highest_weekday['average_occupied_ports']:.4f}; {lowest_weekday['weekday_name']} has the lowest at {lowest_weekday['average_occupied_ports']:.4f}. The ordering is Monday through Sunday. See [weekday_demand.png](weekday_demand.png).",
        "",
        "## 6. Monthly demand findings",
        "",
        f"The highest average month is {highest_month['month_name']} at {highest_month['average_occupied_ports']:.4f} occupied ports, while the lowest is {lowest_month['month_name']} at {lowest_month['average_occupied_ports']:.4f}. Monthly valid-utilization averages exclude zero-denominator records. See [monthly_demand.png](monthly_demand.png).",
        "",
        "## 7. Daily trend findings",
        "",
        "Daily demand is defined as the mean of all valid station-level `ports_occupied` observations for each calendar date. The daily trend is descriptive and does not imply a forecast or causal effect. See [daily_demand_trend.png](daily_demand_trend.png).",
        "",
        "## 8. Station-wise analysis",
        "",
        f"The station with the highest average occupied-port demand is {top_station['station_id']} at {top_station['average_occupied_ports']:.4f}. The station with the highest average operational utilization is {top_util['station_id']} at {top_util['average_operational_utilization']:.6f}. These rankings are intentionally separate: a station can have high occupied-port counts because it has more ports without having the highest utilization.",
        "",
        "See [top_stations.png](top_stations.png) and [station_utilization.png](station_utilization.png).",
        "",
        "## 9. Demand distribution",
        "",
        f"Occupied ports have mean {distribution['mean']:.4f}, median {distribution['median']:.4f}, standard deviation {distribution['standard_deviation']:.4f}, Q1 {distribution['q1']:.4f}, and Q3 {distribution['q3']:.4f}. Skewness is {distribution['skewness']:.6f}. Zero occupancy occurs in {distribution['zero_occupancy_observations']:,} observations ({distribution['zero_occupancy_percentage']:.4f}%). See [occupancy_distribution.png](occupancy_distribution.png) and [occupancy_boxplot.png](occupancy_boxplot.png).",
        "",
        "## 10. Daily and weekly seasonality",
        "",
        "The hourly profile and weekday profile show recurring historical differences. The weekday-hour heatmap and weekday/weekend comparison are descriptive visual evidence; they do not by themselves establish formal seasonal stationarity. See [hour_weekday_heatmap.png](hour_weekday_heatmap.png) and [weekday_weekend_comparison.png](weekday_weekend_comparison.png).",
        "",
        "## 11. Outlier analysis",
        "",
        f"Using the 1.5 IQR rule, the lower bound is {outlier['lower_bound']:.4f} and the upper bound is {outlier['upper_bound']:.4f}. {outlier['flagged_observations']:,} observations ({outlier['flagged_percentage']:.4f}%) were flagged. A flagged value is not automatically an error; legitimate peak demand can be extreme. No observations were deleted or modified. See [occupancy_outliers.png](occupancy_outliers.png).",
        "",
        "## 12. Forecasting suitability",
        "",
        "The dataset is suitable for forecasting preparation because it provides long, regular station-wise histories and a clearly defined occupied-port target. Hourly and weekday profiles suggest that daily and weekly seasonal periods should be investigated in the next authorized phase. Station-level scale differences also support comparing station-specific and pooled approaches.",
        "",
        "The representative ADF results in `forecasting_suitability.md` apply only to selected stations. They are not a substitute for model evaluation and are not generalized to the complete station set.",
        "",
        "## 13. Key findings",
        "",
        f"- Average occupied ports: {overview['average_occupied_ports']:.4f}.",
        f"- Busiest hour: {int(busiest_hour['hour']):02d}:00 UTC.",
        f"- Highest-demand weekday: {highest_weekday['weekday_name']}.",
        f"- Highest-demand month: {highest_month['month_name']}.",
        f"- Top station by average occupied ports: {top_station['station_id']}.",
        f"- IQR-flagged observations: {outlier['flagged_observations']:,}.",
        "",
        "## 14. Recommendations for Phase 4",
        "",
        "1. Establish leakage-controlled feature definitions using 48 half-hour steps for daily seasonality and 336 half-hour steps for weekly seasonality.",
        "2. Compare simple seasonal baselines with more complex models only after chronological evaluation is authorized.",
        "3. Account for station-level scale and utilization differences; do not rank demand and utilization as interchangeable measures.",
        "4. Keep `ports_occupied` as the primary target and treat supplied utilization and estimated wait-time fields cautiously.",
        "5. Investigate whether flagged extremes represent legitimate peaks before applying any future transformation or exclusion rule.",
        "",
        "## Generated charts",
        "",
    ]
    lines.extend(f"- [{chart}]({chart})" for chart in charts)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_eda(
    processed_path: str | Path,
    output_dir: str | Path,
    phase2_overview_path: str | Path = "data/reports/dataset_overview.json",
    phase2_quality_path: str | Path = "data/reports/data_quality_report.json",
    chunksize: int = EDA_CHUNK_SIZE,
) -> dict[str, Any]:
    """Run all Phase 3 EDA calculations and write reports and charts."""

    processed_path = Path(processed_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if not processed_path.exists():
        raise FileNotFoundError(f"Processed dataset not found: {processed_path}")

    header = read_csv_header(processed_path)
    missing = sorted(set(EDA_COLUMNS).difference(header))
    if missing:
        raise ValueError(f"Processed dataset is missing EDA columns: {missing}")

    phase2_overview = json.loads(Path(phase2_overview_path).read_text(encoding="utf-8"))
    phase2_quality = json.loads(Path(phase2_quality_path).read_text(encoding="utf-8"))

    hourly = GroupAccumulator()
    weekday = GroupAccumulator()
    monthly = GroupAccumulator()
    monthly_utilization = GroupAccumulator()
    daily = GroupAccumulator()
    station = GroupAccumulator()
    station_utilization = GroupAccumulator()
    heatmap = GroupAccumulator()
    weekend_hour = GroupAccumulator()
    all_occupied: list[np.ndarray] = []
    valid_utilization: list[np.ndarray] = []
    total_observations = 0
    zero_denominator_records = 0
    zero_occupancy_records = 0
    station_ids: set[str] = set()
    unique_timestamps: set[pd.Timestamp] = set()
    minimum_timestamp: pd.Timestamp | None = None
    maximum_timestamp: pd.Timestamp | None = None

    for chunk in iter_csv_chunks(processed_path, chunksize=chunksize, usecols=EDA_COLUMNS):
        total_observations += len(chunk)
        timestamps = parse_timestamps(chunk["timestamp"])
        occupied = pd.to_numeric(chunk["ports_occupied"], errors="coerce")
        utilization = pd.to_numeric(chunk["operational_utilization"], errors="coerce")
        valid_occupied = occupied.notna() & timestamps.notna()
        valid_util = utilization.notna() & timestamps.notna()
        station_values = chunk["station_id"].astype("string").str.strip()
        station_ids.update(station_values.dropna().astype(str).tolist())
        if timestamps.notna().any():
            valid_times = timestamps.dropna()
            minimum_timestamp = valid_times.min() if minimum_timestamp is None else min(minimum_timestamp, valid_times.min())
            maximum_timestamp = valid_times.max() if maximum_timestamp is None else max(maximum_timestamp, valid_times.max())
            unique_timestamps.update(pd.unique(valid_times))

        zero_denominator_records += int(utilization.isna().sum())
        zero_occupancy_records += int(occupied.eq(0).sum())
        if valid_occupied.any():
            all_occupied.append(occupied[valid_occupied].to_numpy(dtype=float, copy=True))
        if valid_util.any():
            valid_utilization.append(utilization[valid_util].to_numpy(dtype=float, copy=True))

        hour = timestamps.dt.hour
        day_of_week = timestamps.dt.dayofweek
        month = timestamps.dt.month
        date = timestamps.dt.strftime("%Y-%m-%d")
        valid_keys = valid_occupied
        hourly.add(hour[valid_keys], occupied[valid_keys])
        weekday.add(day_of_week[valid_keys], occupied[valid_keys])
        monthly.add(month[valid_keys], occupied[valid_keys])
        daily.add(date[valid_keys], occupied[valid_keys])
        station.add(station_values[valid_keys], occupied[valid_keys])
        heatmap.add(
            (day_of_week[valid_keys].astype("Int64").astype(str) + "_" + hour[valid_keys].astype("Int64").astype(str)),
            occupied[valid_keys],
        )
        weekend_labels = np.where(day_of_week[valid_keys].to_numpy() >= 5, "Weekend", "Weekday")
        weekend_hour.add(
            pd.Series(weekend_labels, index=hour[valid_keys].index).astype(str) + "_" + hour[valid_keys].astype("Int64").astype(str),
            occupied[valid_keys],
        )
        monthly_utilization.add(month[valid_util], utilization[valid_util])
        station_utilization.add(station_values[valid_util], utilization[valid_util])

    occupied_values = np.concatenate(all_occupied)
    utilization_values = np.concatenate(valid_utilization) if valid_utilization else np.array([], dtype=float)
    distribution = summary_statistics(occupied_values)
    distribution["zero_occupancy_observations"] = zero_occupancy_records
    distribution["zero_occupancy_percentage"] = _safe_percentage(zero_occupancy_records, total_observations)
    q1, q3, iqr, lower_bound, upper_bound = iqr_outlier_bounds(occupied_values)
    outlier_mask = (occupied_values < lower_bound) | (occupied_values > upper_bound)
    outlier_summary = {
        "method": "IQR-based outlier detection",
        "multiplier": 1.5,
        "q1": q1,
        "q3": q3,
        "iqr": iqr,
        "lower_bound": lower_bound,
        "upper_bound": upper_bound,
        "flagged_observations": int(outlier_mask.sum()),
        "flagged_percentage": _safe_percentage(int(outlier_mask.sum()), len(occupied_values)),
        "lower_outlier_observations": int((occupied_values < lower_bound).sum()),
        "upper_outlier_observations": int((occupied_values > upper_bound).sum()),
        "interpretation": "Flagged observations may represent legitimate peak demand and were not removed or modified.",
    }

    hourly_frame = _format_hourly(hourly)
    weekday_frame = _format_weekday(weekday)
    monthly_frame = _format_monthly(monthly, monthly_utilization)
    daily_frame = _format_daily(daily)
    station_frame = _format_station(station, station_utilization)
    heatmap_frame = _format_heatmap(heatmap)
    weekend_frame = _format_weekend(weekend_hour)
    top_stations = station_frame.sort_values("average_occupied_ports", ascending=False).head(10)
    bottom_stations = station_frame.sort_values("average_occupied_ports", ascending=True).head(10)
    top_utilization = station_frame.sort_values("average_operational_utilization", ascending=False).head(10)
    occupancy_frequency = (
        pd.Series(occupied_values, name="ports_occupied")
        .value_counts()
        .sort_index()
        .rename_axis("ports_occupied")
        .reset_index(name="observation_count")
    )
    occupancy_frequency["percentage"] = occupancy_frequency["observation_count"] / len(occupied_values) * 100.0

    overview = {
        "processed_file": str(processed_path),
        "total_observations": int(total_observations),
        "total_stations": int(len(station_ids)),
        "processed_columns": int(len(header)),
        "original_columns": int(phase2_overview["schema"]["columns"]),
        "minimum_timestamp_utc": minimum_timestamp.isoformat() if minimum_timestamp is not None else None,
        "maximum_timestamp_utc": maximum_timestamp.isoformat() if maximum_timestamp is not None else None,
        "unique_timestamp_count": int(len(unique_timestamps)),
        "sampling_frequency_minutes": int(phase2_overview["sampling"]["expected_interval_minutes"]),
        "average_occupied_ports": float(occupied_values.mean()),
        "median_occupied_ports": float(np.median(occupied_values)),
        "minimum_occupied_ports": float(occupied_values.min()),
        "maximum_occupied_ports": float(occupied_values.max()),
        "average_operational_utilization": float(utilization_values.mean()) if utilization_values.size else None,
        "median_operational_utilization": float(np.median(utilization_values)) if utilization_values.size else None,
        "valid_utilization_observations": int(utilization_values.size),
        "zero_denominator_utilization_records": int(zero_denominator_records),
        "phase2_reference_matches": {
            "rows": int(total_observations) == int(phase2_overview["schema"]["rows"]),
            "stations": int(len(station_ids)) == int(phase2_overview["stations"]["unique_station_count"]),
            "minimum_timestamp": minimum_timestamp.isoformat() == phase2_overview["timestamps"]["minimum_timestamp_utc"] if minimum_timestamp is not None else False,
            "maximum_timestamp": maximum_timestamp.isoformat() == phase2_overview["timestamps"]["maximum_timestamp_utc"] if maximum_timestamp is not None else False,
        },
    }

    eda_summary_rows = [
        {"section": "dataset", "metric": "total_observations", "value": overview["total_observations"], "notes": "Processed input rows"},
        {"section": "dataset", "metric": "total_stations", "value": overview["total_stations"], "notes": "Unique station IDs"},
        {"section": "dataset", "metric": "average_occupied_ports", "value": overview["average_occupied_ports"], "notes": "Primary demand variable"},
        {"section": "dataset", "metric": "median_occupied_ports", "value": overview["median_occupied_ports"], "notes": "Primary demand variable"},
        {"section": "dataset", "metric": "average_operational_utilization", "value": overview["average_operational_utilization"], "notes": "Excludes zero denominators"},
        {"section": "dataset", "metric": "median_operational_utilization", "value": overview["median_operational_utilization"], "notes": "Excludes zero denominators"},
        {"section": "dataset", "metric": "zero_denominator_utilization_records", "value": overview["zero_denominator_utilization_records"], "notes": "Not treated as zero utilization"},
        {"section": "outliers", "metric": "iqr_flagged_observations", "value": outlier_summary["flagged_observations"], "notes": "1.5 IQR rule"},
    ]
    pd.DataFrame(eda_summary_rows).to_csv(output_dir / "eda_summary.csv", index=False)
    _write_json(output_dir / "dataset_overview.json", overview)
    hourly_frame.to_csv(output_dir / "hourly_demand.csv", index=False)
    weekday_frame.to_csv(output_dir / "weekday_demand.csv", index=False)
    monthly_frame.to_csv(output_dir / "monthly_demand.csv", index=False)
    daily_frame.to_csv(output_dir / "daily_demand_trend.csv", index=False)
    station_frame.to_csv(output_dir / "station_demand_summary.csv", index=False)
    top_stations.to_csv(output_dir / "top_10_stations.csv", index=False)
    bottom_stations.to_csv(output_dir / "bottom_10_stations.csv", index=False)
    top_utilization.to_csv(output_dir / "top_10_utilization.csv", index=False)
    occupancy_frequency.to_csv(output_dir / "occupancy_frequency.csv", index=False)
    heatmap_frame.to_csv(output_dir / "hour_weekday_heatmap.csv", index=False)
    weekend_frame.to_csv(output_dir / "weekday_weekend_comparison.csv", index=False)
    _write_json(output_dir / "outlier_summary.json", outlier_summary)

    station_outlier_rows = []
    for station_id, arrays in station.values.items():
        values = np.concatenate(arrays)
        lower_count = int((values < lower_bound).sum())
        upper_count = int((values > upper_bound).sum())
        flagged = lower_count + upper_count
        station_outlier_rows.append(
            {
                "station_id": station_id,
                "observation_count": int(len(values)),
                "lower_outliers": lower_count,
                "upper_outliers": upper_count,
                "flagged_outliers": flagged,
                "flagged_percentage": _safe_percentage(flagged, len(values)),
            }
        )
    station_outlier_frame = pd.DataFrame(station_outlier_rows).sort_values("flagged_outliers", ascending=False)
    station_outlier_frame.to_csv(output_dir / "station_outlier_summary.csv", index=False)

    representative_stations = sorted(station_ids)
    if representative_stations:
        representative_stations = [
            representative_stations[0],
            representative_stations[len(representative_stations) // 2],
            representative_stations[-1],
        ]
        representative_stations = list(dict.fromkeys(representative_stations))
    adf_rows = _run_adf(station.values, representative_stations)
    _write_suitability_report(output_dir / "forecasting_suitability.md", overview, hourly_frame, weekday_frame, daily_frame, station_frame, adf_rows)
    _write_eda_report(output_dir / "EDA_REPORT.md", overview, phase2_quality, hourly_frame, weekday_frame, monthly_frame, daily_frame, station_frame, {**distribution, "zero_occupancy_observations": zero_occupancy_records, "zero_occupancy_percentage": _safe_percentage(zero_occupancy_records, total_observations)}, outlier_summary, adf_rows)

    chart_files = create_all_charts(
        output_dir,
        hourly_frame,
        weekday_frame,
        monthly_frame,
        daily_frame,
        top_stations,
        top_utilization,
        pd.Series(occupied_values, name="ports_occupied"),
        heatmap_frame,
        weekend_frame,
        upper_bound,
        lower_bound,
    )
    return {"overview": overview, "outlier_summary": outlier_summary, "chart_files": chart_files}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed", type=Path, default=Path("data/processed/ev_charging_processed.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/reports/eda"))
    parser.add_argument("--chunksize", type=int, default=EDA_CHUNK_SIZE)
    args = parser.parse_args()
    result = run_eda(args.processed, args.output_dir, chunksize=args.chunksize)
    print(json.dumps(result, indent=2, default=_json_value))


if __name__ == "__main__":
    main()

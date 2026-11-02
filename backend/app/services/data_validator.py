"""Validation and feature helpers for ChargeQueue time-series data."""

from __future__ import annotations

import numpy as np
import pandas as pd


PORT_COLUMNS = [
    "ports_total",
    "ports_available",
    "ports_occupied",
    "ports_out_of_service",
]


def parse_timestamps(values: pd.Series) -> pd.Series:
    """Parse timestamps to timezone-aware UTC values; invalid values become NaT."""

    return pd.to_datetime(values, errors="coerce", utc=True)


def numeric_port_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Return port columns as numeric values without changing the input frame."""

    return frame.reindex(columns=PORT_COLUMNS).apply(pd.to_numeric, errors="coerce")


def validate_port_balance(frame: pd.DataFrame) -> pd.Series:
    """Return a row mask where valid port counts do not balance to total ports."""

    ports = numeric_port_frame(frame)
    valid = ports.notna().all(axis=1)
    balance = (
        ports["ports_available"]
        + ports["ports_occupied"]
        + ports["ports_out_of_service"]
        - ports["ports_total"]
    )
    return valid & ~np.isclose(balance, 0.0, atol=1e-9, rtol=0.0)


def calculate_operational_utilization(frame: pd.DataFrame) -> pd.Series:
    """Calculate occupied/(available+occupied), returning NaN for zero denominators."""

    ports = numeric_port_frame(frame)
    denominator = ports["ports_available"] + ports["ports_occupied"]
    numerator = ports["ports_occupied"]
    return numerator.div(denominator.where(denominator.ne(0)))


def create_calendar_features(frame: pd.DataFrame, timestamp_column: str = "timestamp") -> pd.DataFrame:
    """Add calendar fields from an already parsed timestamp column."""

    result = frame.copy()
    timestamps = pd.to_datetime(result[timestamp_column], errors="coerce", utc=True)
    derived = {
        "hour": timestamps.dt.hour.astype("Int64"),
        "day_of_week": timestamps.dt.dayofweek.astype("Int64"),
        "day": timestamps.dt.day.astype("Int64"),
        "month": timestamps.dt.month.astype("Int64"),
        "is_weekend": timestamps.dt.dayofweek.ge(5).astype("boolean"),
    }
    for column, values in derived.items():
        if column not in result.columns:
            result[column] = values
    return result


def sort_station_time_series(frame: pd.DataFrame) -> pd.DataFrame:
    """Return observations ordered by station and timestamp without resetting source values."""

    return frame.sort_values(["station_id", "timestamp"], kind="mergesort").reset_index(drop=True)

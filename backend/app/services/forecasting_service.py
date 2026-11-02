"""Leakage-aware station forecasting service with a stable output contract."""

from __future__ import annotations

import warnings
from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd

from ..models.common import ForecastingError, ModelForecast
from .model_registry import get_model_spec


HORIZON_STEPS = 2
STEP_MINUTES = 30


def _json_value(value: Any) -> Any:
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(float(value)) else float(value)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, tuple):
        return list(value)
    return value


def _validate_history(history: pd.DataFrame, forecast_origin: pd.Timestamp | str | None) -> tuple[str, pd.DataFrame]:
    required = {"station_id", "timestamp", "ports_occupied"}
    missing = required.difference(history.columns)
    if missing:
        raise ForecastingError(f"station history is missing required columns: {sorted(missing)}")
    frame = history.copy()
    stations = frame["station_id"].dropna().astype(str).unique().tolist()
    if len(stations) != 1:
        raise ForecastingError("station history must contain exactly one non-null station_id")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
    if frame["timestamp"].isna().any():
        raise ForecastingError("station history contains invalid timestamps")
    frame["ports_occupied"] = pd.to_numeric(frame["ports_occupied"], errors="coerce")
    if frame["ports_occupied"].isna().any():
        raise ForecastingError("station history contains invalid ports_occupied values")
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    if frame["timestamp"].duplicated().any():
        raise ForecastingError("station history contains duplicate timestamps")
    if forecast_origin is not None:
        origin = pd.to_datetime(forecast_origin, errors="raise", utc=True)
        frame = frame.loc[frame["timestamp"] <= origin].copy()
    if frame.empty:
        raise ForecastingError("station history has no observations at or before the forecast origin")
    return stations[0], frame


def _reliable_capacity(frame: pd.DataFrame, station_capacity: int | float | None) -> int | None:
    if station_capacity is not None:
        numeric = float(station_capacity)
        return int(numeric) if np.isfinite(numeric) and numeric >= 0 else None
    if "ports_total" not in frame.columns:
        return None
    ports = pd.to_numeric(frame["ports_total"], errors="coerce").dropna()
    if ports.empty or ports.nunique() != 1:
        return None
    value = float(ports.iloc[0])
    return int(value) if np.isfinite(value) and value >= 0 else None


def _display_value(raw: float, capacity: int | None) -> int:
    value = max(0.0, float(raw))
    if capacity is not None:
        value = min(value, float(capacity))
    return int(np.rint(value))


def forecast_station(
    history: pd.DataFrame,
    model_name: str,
    *,
    forecast_origin: pd.Timestamp | str | None = None,
    station_capacity: int | float | None = None,
    configuration: dict[str, Any] | None = None,
    history_limit: int | None = None,
    horizon_steps: int | None = None,
) -> dict[str, Any]:
    """Fit one registered model using observations available at the origin.

    ``history`` must contain only information available to the caller. An
    optional origin further restricts rows to timestamps at or before it. No
    future observations or future operational measurements are constructed.
    """

    if not isinstance(history, pd.DataFrame):
        raise ForecastingError("history must be a pandas DataFrame")
    station_id, frame = _validate_history(history, forecast_origin)
    origin = frame["timestamp"].max()
    if history_limit is not None:
        if history_limit <= 0:
            raise ValueError("history_limit must be positive")
        frame = frame.tail(history_limit).reset_index(drop=True)
    spec = get_model_spec(model_name)
    config = dict(spec.default_configuration)
    config.update(configuration or {})
    seasonal_period = int(config.pop("seasonal_period", spec.seasonal_period))
    horizon = int(horizon_steps if horizon_steps is not None else config.pop("horizon", HORIZON_STEPS))
    if horizon <= 0:
        raise ValueError("forecast horizon must be positive")
    series = pd.Series(frame["ports_occupied"].to_numpy(dtype=float))
    warning_messages: list[str] = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fit_result: ModelForecast = spec.runner(series, seasonal_period, horizon, config)
        warning_messages = [str(item.message) for item in caught]
    raw = np.asarray(fit_result.predictions, dtype=float)
    if raw.size != horizon or not np.isfinite(raw).all():
        raise ForecastingError(f"{model_name} returned invalid forecast values")
    capacity = _reliable_capacity(frame, station_capacity)
    timestamps = [origin + timedelta(minutes=STEP_MINUTES * step) for step in range(1, horizon + 1)]
    display_values = [_display_value(value, capacity) for value in raw]
    forecast_points = [
        {
            "forecast_timestamp": timestamp.isoformat(),
            "horizon_minutes": step * STEP_MINUTES,
            "predicted_occupied_ports": display_values[step - 1],
            "raw_predicted_occupied_ports": float(raw[step - 1]),
        }
        for step, timestamp in enumerate(timestamps, start=1)
    ]
    result = {
        "station_id": station_id,
        "model_name": model_name,
        "forecast_origin": origin.isoformat(),
        "forecast_points": forecast_points,
        "seasonal_period": seasonal_period if spec.family != "seasonal_naive" or seasonal_period else None,
        "model_configuration": {
            **fit_result.configuration,
            "history_observations_used": int(len(series)),
            "forecast_horizon_steps": horizon,
            "step_minutes": STEP_MINUTES,
            "capacity_used_for_display_cap": capacity,
            "display_adjustment": "round to nearest non-negative integer and cap at reliable ports_total",
            "model_warnings": warning_messages,
        },
        "model_diagnostics": fit_result.diagnostics,
        "model_status": "completed",
    }
    for index, suffix in ((0, "30m"), (1, "60m")):
        if index < len(forecast_points):
            result[f"forecast_timestamp_{index + 1}"] = forecast_points[index]["forecast_timestamp"]
            result[f"raw_predicted_occupied_ports_{suffix}"] = forecast_points[index]["raw_predicted_occupied_ports"]
            result[f"predicted_occupied_ports_{suffix}"] = forecast_points[index]["predicted_occupied_ports"]
    return {key: _json_value(value) if key not in {"model_configuration", "model_diagnostics"} else value for key, value in result.items()}

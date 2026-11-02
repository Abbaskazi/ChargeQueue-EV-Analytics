"""Registry mapping public model names to forecasting implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd

from ..models import holt_winters, sarima, seasonal_naive
from ..models.common import ModelForecast


ModelRunner = Callable[[pd.Series, int, int, dict[str, Any]], ModelForecast]


@dataclass(frozen=True)
class ModelSpec:
    """Public metadata and runner for one forecast configuration."""

    name: str
    family: str
    seasonal_period: int
    runner: ModelRunner
    default_configuration: dict[str, Any]


def _seasonal_naive_runner(series: pd.Series, period: int, horizon: int, config: dict[str, Any]) -> ModelForecast:
    return seasonal_naive.forecast(series, seasonal_period=period, horizon=horizon, configuration=config)


def _holt_winters_runner(series: pd.Series, period: int, horizon: int, config: dict[str, Any]) -> ModelForecast:
    return holt_winters.forecast(series, seasonal_period=period, horizon=horizon, configuration=config)


def _sarima_runner(series: pd.Series, period: int, horizon: int, config: dict[str, Any]) -> ModelForecast:
    return sarima.forecast(series, seasonal_period=period, horizon=horizon, configuration=config)


MODEL_REGISTRY: dict[str, ModelSpec] = {
    "seasonal_naive": ModelSpec("seasonal_naive", "seasonal_naive", 48, _seasonal_naive_runner, {}),
    "seasonal_naive_daily": ModelSpec("seasonal_naive_daily", "seasonal_naive", 48, _seasonal_naive_runner, {}),
    "seasonal_naive_weekly": ModelSpec("seasonal_naive_weekly", "seasonal_naive", 336, _seasonal_naive_runner, {}),
    "holt_winters": ModelSpec("holt_winters", "holt_winters", 48, _holt_winters_runner, {"trend": "add", "seasonal": "add"}),
    "holt_winters_daily": ModelSpec("holt_winters_daily", "holt_winters", 48, _holt_winters_runner, {"trend": "add", "seasonal": "add"}),
    "holt_winters_weekly": ModelSpec("holt_winters_weekly", "holt_winters", 336, _holt_winters_runner, {"trend": "add", "seasonal": "add"}),
    "sarima": ModelSpec("sarima", "sarima", 48, _sarima_runner, {"order": (1, 0, 0), "maxiter": 50}),
    "sarima_daily": ModelSpec("sarima_daily", "sarima", 48, _sarima_runner, {"order": (1, 0, 0), "maxiter": 50}),
    "sarima_weekly": ModelSpec("sarima_weekly", "sarima", 336, _sarima_runner, {"order": (1, 0, 0), "maxiter": 50}),
}


def get_model_spec(model_name: str) -> ModelSpec:
    """Return a registered model or raise a clear error."""

    try:
        return MODEL_REGISTRY[model_name]
    except KeyError as exc:
        available = ", ".join(sorted(MODEL_REGISTRY))
        raise ValueError(f"Unknown model '{model_name}'. Available models: {available}") from exc


def registry_configuration() -> dict[str, dict[str, Any]]:
    """Return JSON-friendly registry metadata for reports."""

    return {
        name: {
            "family": spec.family,
            "seasonal_period": spec.seasonal_period,
            "default_configuration": {
                key: list(value) if isinstance(value, tuple) else value
                for key, value in spec.default_configuration.items()
            },
        }
        for name, spec in MODEL_REGISTRY.items()
    }


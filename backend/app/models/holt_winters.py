"""Holt-Winters exponential-smoothing forecasting model."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .common import InsufficientHistoryError, ModelDependencyError, ModelForecast


def forecast(
    series: pd.Series,
    seasonal_period: int = 48,
    horizon: int = 2,
    trend: str | None = "add",
    seasonal: str = "add",
    configuration: dict[str, Any] | None = None,
) -> ModelForecast:
    """Fit additive Holt-Winters and return raw forecasts.

    At least two complete seasonal cycles are required. Statsmodels warnings
    are captured by the forecasting service so convergence information is not
    silently discarded.
    """

    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ModelDependencyError("statsmodels is required for Holt-Winters") from exc
    if seasonal_period <= 0 or horizon <= 0:
        raise ValueError("seasonal_period and horizon must be positive")
    values = pd.to_numeric(series, errors="coerce")
    if values.isna().any():
        raise ValueError("Holt-Winters history contains missing or non-numeric target values")
    minimum = 2 * seasonal_period
    if len(values) < minimum:
        raise InsufficientHistoryError(
            f"Holt-Winters requires at least {minimum} observations; received {len(values)}"
        )
    model = ExponentialSmoothing(
        values.astype(float),
        trend=trend,
        seasonal=seasonal,
        seasonal_periods=seasonal_period,
        initialization_method="estimated",
    )
    fitted = model.fit(optimized=True, use_brute=False, remove_bias=False)
    predictions = np.asarray(fitted.forecast(horizon), dtype=float)
    return ModelForecast(
        predictions=predictions,
        configuration={
            "model_family": "holt_winters",
            "trend": trend,
            "seasonal": seasonal,
            "seasonal_period": int(seasonal_period),
            "horizon": int(horizon),
            **(configuration or {}),
        },
        diagnostics={"aic": float(fitted.aic) if np.isfinite(fitted.aic) else None},
    )


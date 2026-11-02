"""Small, configurable SARIMA forecasting model."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .common import InsufficientHistoryError, ModelDependencyError, ModelForecast


def forecast(
    series: pd.Series,
    seasonal_period: int = 48,
    horizon: int = 2,
    order: tuple[int, int, int] = (1, 0, 0),
    seasonal_order: tuple[int, int, int, int] | None = None,
    maxiter: int = 50,
    configuration: dict[str, Any] | None = None,
) -> ModelForecast:
    """Fit one documented SARIMA configuration and return raw forecasts."""

    try:
        from statsmodels.tsa.statespace.sarimax import SARIMAX
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ModelDependencyError("statsmodels is required for SARIMA") from exc
    if seasonal_period <= 0 or horizon <= 0:
        raise ValueError("seasonal_period and horizon must be positive")
    values = pd.to_numeric(series, errors="coerce")
    if values.isna().any():
        raise ValueError("SARIMA history contains missing or non-numeric target values")
    minimum = max(2 * seasonal_period, 100)
    if len(values) < minimum:
        raise InsufficientHistoryError(
            f"SARIMA requires at least {minimum} observations for the configured seasonal period; received {len(values)}"
        )
    actual_seasonal_order = seasonal_order or (1, 0, 0, seasonal_period)
    if actual_seasonal_order[3] != seasonal_period:
        raise ValueError("seasonal_order period must match seasonal_period")
    model = SARIMAX(
        values.astype(float),
        order=order,
        seasonal_order=actual_seasonal_order,
        enforce_stationarity=False,
        enforce_invertibility=False,
    )
    fitted = model.fit(disp=False, maxiter=maxiter)
    predictions = np.asarray(fitted.forecast(steps=horizon), dtype=float)
    converged = fitted.mle_retvals.get("converged") if hasattr(fitted, "mle_retvals") else None
    return ModelForecast(
        predictions=predictions,
        configuration={
            "model_family": "sarima",
            "order": list(order),
            "seasonal_order": list(actual_seasonal_order),
            "seasonal_period": int(seasonal_period),
            "maxiter": int(maxiter),
            "horizon": int(horizon),
            **(configuration or {}),
        },
        diagnostics={
            "converged": bool(converged) if converged is not None else None,
            "aic": float(fitted.aic) if np.isfinite(fitted.aic) else None,
        },
    )


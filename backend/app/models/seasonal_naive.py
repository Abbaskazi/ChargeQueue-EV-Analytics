"""Seasonal naive forecasting baseline."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .common import InsufficientHistoryError, ModelForecast


def forecast(
    series: pd.Series,
    seasonal_period: int = 48,
    horizon: int = 2,
    configuration: dict[str, Any] | None = None,
) -> ModelForecast:
    """Repeat the historical values at the matching seasonal positions.

    The forecast for step ``h`` is the observed value at the same position in
    the latest complete seasonal cycle. No values after the supplied history
    are accessed.
    """

    if seasonal_period <= 0 or horizon <= 0:
        raise ValueError("seasonal_period and horizon must be positive")
    values = pd.to_numeric(series, errors="coerce")
    if values.isna().any():
        raise ValueError("seasonal naive history contains missing or non-numeric target values")
    if len(values) < seasonal_period + horizon - 1:
        raise InsufficientHistoryError(
            f"seasonal naive requires at least {seasonal_period + horizon - 1} observations; received {len(values)}"
        )
    array = values.to_numpy(dtype=float)
    predictions = np.asarray(
        [array[-seasonal_period + offset] for offset in range(horizon)], dtype=float
    )
    return ModelForecast(
        predictions=predictions,
        configuration={
            "model_family": "seasonal_naive",
            "seasonal_period": int(seasonal_period),
            "horizon": int(horizon),
            **(configuration or {}),
        },
    )


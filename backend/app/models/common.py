"""Shared errors and return types for forecasting models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


class ForecastingError(Exception):
    """Base error for invalid forecasting requests or model failures."""


class InsufficientHistoryError(ForecastingError):
    """Raised when a model cannot be fitted with the supplied history."""


class ModelDependencyError(ForecastingError):
    """Raised when an optional model dependency is unavailable."""


@dataclass
class ModelForecast:
    """Raw model output and diagnostics before display post-processing."""

    predictions: np.ndarray
    configuration: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)


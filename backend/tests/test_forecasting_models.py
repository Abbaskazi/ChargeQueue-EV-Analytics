"""Lightweight unit tests for Phase 4 forecasting contracts."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from backend.app.models.common import ForecastingError, InsufficientHistoryError
from backend.app.services.forecasting_service import forecast_station
from backend.app.services.model_registry import get_model_spec


def sample_history(length: int = 240, station_id: str = "TEST001") -> pd.DataFrame:
    timestamps = pd.date_range("2025-01-01", periods=length, freq="30min", tz="UTC")
    values = (2.0 + np.sin(np.arange(length) * 2 * np.pi / 48) + (np.arange(length) % 7) * 0.1).clip(0)
    return pd.DataFrame(
        {
            "station_id": station_id,
            "timestamp": timestamps,
            "ports_occupied": values,
            "ports_total": 10,
        }
    )


class ForecastingModelTests(unittest.TestCase):
    def test_seasonal_naive_daily_forecasting(self) -> None:
        history = sample_history(100)
        result = forecast_station(history, "seasonal_naive_daily")
        self.assertEqual(result["model_status"], "completed")
        self.assertEqual(result["seasonal_period"], 48)
        self.assertEqual(result["predicted_occupied_ports_30m"], round(history.iloc[-48]["ports_occupied"]))

    def test_seasonal_naive_weekly_forecasting(self) -> None:
        history = sample_history(340)
        result = forecast_station(history, "seasonal_naive_weekly")
        self.assertEqual(result["seasonal_period"], 336)
        self.assertEqual(result["predicted_occupied_ports_60m"], round(history.iloc[-335]["ports_occupied"]))

    def test_holt_winters_forecasting(self) -> None:
        result = forecast_station(sample_history(), "holt_winters_daily")
        self.assertEqual(result["model_status"], "completed")
        self.assertEqual(len([result["predicted_occupied_ports_30m"], result["predicted_occupied_ports_60m"]]), 2)

    def test_sarima_forecasting(self) -> None:
        result = forecast_station(sample_history(), "sarima_daily", configuration={"maxiter": 20})
        self.assertEqual(result["model_status"], "completed")
        self.assertIn("converged", result["model_diagnostics"])

    def test_exact_two_steps_and_timestamps(self) -> None:
        result = forecast_station(sample_history(100), "seasonal_naive_daily")
        origin = pd.Timestamp(result["forecast_origin"])
        self.assertEqual(pd.Timestamp(result["forecast_timestamp_1"]), origin + pd.Timedelta(minutes=30))
        self.assertEqual(pd.Timestamp(result["forecast_timestamp_2"]), origin + pd.Timedelta(minutes=60))

    def test_variable_horizon_uses_daily_seasonal_observations(self) -> None:
        history = sample_history(100)
        result = forecast_station(history, "seasonal_naive_daily", horizon_steps=12)
        origin = pd.Timestamp(result["forecast_origin"])
        points = result["forecast_points"]
        self.assertEqual(len(points), 12)
        for offset, point in enumerate(points, start=1):
            self.assertEqual(
                pd.Timestamp(point["forecast_timestamp"]),
                origin + pd.Timedelta(minutes=30 * offset),
            )
            self.assertEqual(
                point["raw_predicted_occupied_ports"],
                history.iloc[-48 + offset - 1]["ports_occupied"],
            )

    def test_insufficient_history(self) -> None:
        with self.assertRaises(InsufficientHistoryError):
            forecast_station(sample_history(10), "seasonal_naive_daily")

    def test_invalid_station_history(self) -> None:
        history = sample_history(100)
        history.loc[1, "station_id"] = "OTHER"
        with self.assertRaises(ForecastingError):
            forecast_station(history, "seasonal_naive_daily")

    def test_non_negative_display_predictions_and_capacity_cap(self) -> None:
        history = sample_history(100)
        history.loc[0, "ports_occupied"] = 20
        result = forecast_station(history, "seasonal_naive_daily")
        self.assertGreaterEqual(result["predicted_occupied_ports_30m"], 0)
        self.assertLessEqual(result["predicted_occupied_ports_30m"], 10)
        self.assertIn("raw_predicted_occupied_ports_30m", result)

    def test_output_structure(self) -> None:
        result = forecast_station(sample_history(100), "seasonal_naive_daily")
        required = {
            "station_id", "model_name", "forecast_origin", "forecast_timestamp_1", "forecast_timestamp_2",
            "predicted_occupied_ports_30m", "predicted_occupied_ports_60m", "seasonal_period",
            "model_configuration", "model_status",
        }
        self.assertTrue(required.issubset(result))

    def test_registry_selection(self) -> None:
        self.assertEqual(get_model_spec("seasonal_naive_daily").seasonal_period, 48)
        self.assertEqual(get_model_spec("seasonal_naive_weekly").seasonal_period, 336)
        with self.assertRaises(ValueError):
            get_model_spec("not-a-model")


if __name__ == "__main__":
    unittest.main()

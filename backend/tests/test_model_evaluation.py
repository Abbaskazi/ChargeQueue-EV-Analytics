"""Unit tests for chronological evaluation helpers."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from backend.app.services.evaluation import (
    _run_station_model,
    assign_demand_groups,
    chronological_split,
    evaluation_origins,
    mean_absolute_error,
    root_mean_squared_error,
    select_validation_models,
)


class EvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.timestamps = pd.date_range("2025-01-01", periods=100, freq="30min", tz="UTC")

    def test_chronological_split_boundaries_and_no_overlap(self) -> None:
        split = chronological_split(self.timestamps)
        self.assertEqual(split["train_count"], 70)
        self.assertEqual(split["validation_count"], 15)
        self.assertEqual(split["test_count"], 15)
        train = set(range(split["train_start_position"], split["train_end_position_exclusive"]))
        validation = set(range(split["validation_start_position"], split["validation_end_position_exclusive"]))
        test = set(range(split["test_start_position"], split["test_end_position_exclusive"]))
        self.assertEqual(train & validation, set())
        self.assertEqual(validation & test, set())
        self.assertEqual(train | validation | test, set(range(100)))

    def test_no_random_shuffling_and_forecast_origin_correctness(self) -> None:
        split = chronological_split(self.timestamps)
        origins = evaluation_origins(split, "test", stride=5)
        self.assertEqual(origins[0], split["test_start_position"] - 1)
        self.assertTrue(all(left < right for left, right in zip(origins, origins[1:])))
        self.assertTrue(all(origin + 2 < split["test_end_position_exclusive"] for origin in origins))
        self.assertTrue(all(origin + 1 >= split["test_start_position"] for origin in origins))

    def test_two_step_validation_origins_stay_inside_validation(self) -> None:
        split = chronological_split(self.timestamps)
        origins = evaluation_origins(split, "validation", stride=5)
        self.assertTrue(all(origin + 2 < split["validation_end_position_exclusive"] for origin in origins))

    def test_mae_and_rmse(self) -> None:
        actual = np.array([1.0, 3.0, 5.0])
        predicted = np.array([2.0, 1.0, 4.0])
        self.assertAlmostEqual(mean_absolute_error(actual, predicted), 4 / 3)
        self.assertAlmostEqual(root_mean_squared_error(actual, predicted), np.sqrt(2))

    def test_demand_groups_are_ranked_and_equal_count(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "station_summary.csv"
            pd.DataFrame(
                {
                    "station_id": [f"S{i:02d}" for i in range(6)],
                    "average_occupied_ports": [5, 1, 6, 2, 4, 3],
                }
            ).to_csv(path, index=False)
            groups = assign_demand_groups(path)
            self.assertEqual(groups.groupby("demand_group").size().to_dict(), {"high": 2, "low": 2, "medium": 2})
            self.assertEqual(groups.iloc[0]["station_id"], "S01")
            self.assertEqual(groups.iloc[-1]["station_id"], "S02")

    def test_failure_handling_records_failed_origin(self) -> None:
        frame = pd.DataFrame(
            {
                "station_id": "S01",
                "timestamp": pd.date_range("2025-01-01", periods=10, freq="30min", tz="UTC"),
                "ports_occupied": 1.0,
                "ports_total": 2,
            }
        )
        predictions, runs = _run_station_model(frame, "S01", "low", "seasonal_naive_daily", "validation", [8], 1000)
        self.assertEqual(predictions, [])
        self.assertEqual(runs[0]["status"], "failed")

    def test_raw_prediction_is_distinct_from_display_prediction(self) -> None:
        frame = pd.DataFrame(
            {
                "station_id": "S01",
                "timestamp": pd.date_range("2025-01-01", periods=60, freq="30min", tz="UTC"),
                "ports_occupied": np.linspace(0, 4, 60),
                "ports_total": 10,
            }
        )
        predictions, _ = _run_station_model(frame, "S01", "low", "seasonal_naive_daily", "test", [48], 1000)
        self.assertNotEqual(predictions[0]["raw_prediction"], predictions[0]["display_prediction"])

    def test_validation_only_model_selection(self) -> None:
        rows = []
        for model_name, mae in (("model_a", 1.0), ("model_b", 2.0)):
            rows.append(
                {
                    "partition": "validation",
                    "model_name": model_name,
                    "horizon": "30m",
                    "horizon_steps": 1,
                    "mae": mae,
                    "rmse": mae,
                    "observation_count": 10,
                    "stations_with_predictions": 2,
                    "stations_requested": 2,
                    "successful_fits": 2,
                    "failed_fits": 0,
                    "warning_count": 0,
                    "elapsed_seconds": 1.0,
                }
            )
        selected = select_validation_models(pd.DataFrame(rows), 2)
        self.assertEqual(selected["selected_by_horizon"]["30m"]["model_name"], "model_a")
        self.assertNotIn("test_metrics", selected)


if __name__ == "__main__":
    unittest.main()


"""Lightweight Phase 2 tests using small in-memory or temporary datasets."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backend.app.services.data_validator import (
    calculate_operational_utilization,
    create_calendar_features,
    parse_timestamps,
    sort_station_time_series,
    validate_port_balance,
)
from backend.app.services.preprocessing import run_pipeline


class Phase2ServiceTests(unittest.TestCase):
    def test_timestamp_parsing_handles_invalid_values(self) -> None:
        parsed = parse_timestamps(pd.Series(["2025-07-01 00:00:00", "not-a-time"]))
        self.assertEqual(str(parsed.iloc[0].tz), "UTC")
        self.assertTrue(pd.isna(parsed.iloc[1]))

    def test_port_balance_validation(self) -> None:
        frame = pd.DataFrame(
            {
                "ports_total": [6, 6],
                "ports_available": [1, 6],
                "ports_occupied": [0, 1],
                "ports_out_of_service": [5, 0],
            }
        )
        result = validate_port_balance(frame)
        self.assertEqual(result.tolist(), [False, True])

    def test_operational_utilization_and_zero_denominator(self) -> None:
        frame = pd.DataFrame(
            {
                "ports_available": [2, 0],
                "ports_occupied": [2, 0],
                "ports_total": [4, 0],
                "ports_out_of_service": [0, 0],
            }
        )
        result = calculate_operational_utilization(frame)
        self.assertAlmostEqual(float(result.iloc[0]), 0.5)
        self.assertTrue(pd.isna(result.iloc[1]))

    def test_calendar_feature_creation(self) -> None:
        frame = pd.DataFrame({"timestamp": pd.to_datetime(["2025-07-05 13:30:00"], utc=True)})
        result = create_calendar_features(frame)
        self.assertEqual(int(result.loc[0, "hour"]), 13)
        self.assertEqual(int(result.loc[0, "day_of_week"]), 5)
        self.assertEqual(int(result.loc[0, "day"]), 5)
        self.assertEqual(int(result.loc[0, "month"]), 7)
        self.assertTrue(bool(result.loc[0, "is_weekend"]))

    def test_station_wise_chronological_sorting(self) -> None:
        frame = pd.DataFrame(
            {
                "station_id": ["EV2", "EV1", "EV1"],
                "timestamp": pd.to_datetime(
                    ["2025-07-01 01:00:00", "2025-07-01 01:00:00", "2025-07-01 00:30:00"], utc=True
                ),
            }
        )
        result = sort_station_time_series(frame)
        self.assertEqual(result["station_id"].tolist(), ["EV1", "EV1", "EV2"])
        self.assertEqual(result.loc[0, "timestamp"].hour, 0)

    def test_small_pipeline_excludes_invalid_timestamp_without_interpolation(self) -> None:
        source = pd.DataFrame(
            [
                {
                    "timestamp": "2025-07-01 00:30:00",
                    "station_id": "EV2",
                    "ports_total": 4,
                    "ports_available": 2,
                    "ports_occupied": 2,
                    "ports_out_of_service": 0,
                    "utilization_rate": 0.75,
                    "station_status": "operational",
                    "estimated_wait_time_mins": 0,
                },
                {
                    "timestamp": "2025-07-01 00:00:00",
                    "station_id": "EV1",
                    "ports_total": 4,
                    "ports_available": 4,
                    "ports_occupied": 0,
                    "ports_out_of_service": 0,
                    "utilization_rate": 0.20,
                    "station_status": "operational",
                    "estimated_wait_time_mins": 0,
                },
                {
                    "timestamp": "not-a-time",
                    "station_id": "EV1",
                    "ports_total": 4,
                    "ports_available": 4,
                    "ports_occupied": 0,
                    "ports_out_of_service": 0,
                    "utilization_rate": 0.20,
                    "station_status": "operational",
                    "estimated_wait_time_mins": 0,
                },
            ]
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_path = root / "sample.csv"
            processed_path = root / "processed.csv"
            reports_path = root / "reports"
            source.to_csv(input_path, index=False)
            result = run_pipeline(input_path, processed_path, reports_path, chunksize=2)
            processed = pd.read_csv(processed_path)
            self.assertEqual(result["preprocessing_summary"]["input_rows"], 3)
            self.assertEqual(result["preprocessing_summary"]["output_rows"], 2)
            self.assertIn("ports_occupied", processed.columns)
            self.assertIn("operational_utilization", processed.columns)
            self.assertEqual(processed["station_id"].tolist(), ["EV1", "EV2"])
            self.assertFalse((processed["timestamp"] == "2025-07-01T00:00:00Z").iloc[1])
            self.assertTrue((reports_path / "data_quality_report.json").exists())


if __name__ == "__main__":
    unittest.main()

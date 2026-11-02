"""Phase 6 API tests using a small in-memory dataset."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_dataset_service
from backend.app.main import app
from backend.app.services.api_data_service import DatasetService


def _sample_frame() -> pd.DataFrame:
    timestamps = pd.date_range("2025-07-01", periods=60, freq="30min", tz="UTC")
    rows: list[dict[str, object]] = []
    configurations = {
        "TEST": (10, 8, 2),
        "LOW": (10, 9, 1),
        "MOD": (10, 4, 6),
        "HIGH": (10, 1, 9),
        "ZERO": (0, 0, 0),
        "SHORT": (10, 9, 1),
    }
    for station_id, (total, available, occupied) in configurations.items():
        station_timestamps = timestamps[:10] if station_id == "SHORT" else timestamps
        for index, timestamp in enumerate(station_timestamps):
            current_occupied = occupied if station_id != "TEST" else float(2 + (index % 3))
            current_available = available if station_id != "TEST" else total - int(current_occupied)
            denominator = current_available + current_occupied
            rows.append(
                {
                    "station_id": station_id,
                    "timestamp": timestamp,
                    "ports_total": total,
                    "ports_available": current_available,
                    "ports_occupied": current_occupied,
                    "ports_out_of_service": total - current_available - current_occupied,
                    "operational_utilization": current_occupied / denominator if denominator else np.nan,
                    "station_status": "operational",
                }
            )
    return pd.DataFrame(rows)


class Phase6ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        missing_root = Path(cls.temp_dir.name)
        cls.service = DatasetService(
            processed_path=missing_root / "processed.csv",
            overview_path=missing_root / "overview.json",
            quality_path=missing_root / "quality.json",
            station_summary_path=missing_root / "station_summary.csv",
            frame=_sample_frame(),
        )
        app.dependency_overrides[get_dataset_service] = lambda: cls.service
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.clear()
        cls.temp_dir.cleanup()

    def test_health_endpoint(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_dataset_overview_and_station_listing(self) -> None:
        overview = self.client.get("/api/dataset/overview")
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(overview.json()["total_records"], 310)
        stations = self.client.get("/api/stations?page=1&page_size=2")
        self.assertEqual(stations.status_code, 200)
        self.assertEqual(stations.json()["total_stations"], 6)
        self.assertEqual(len(stations.json()["stations"]), 2)

    def test_station_details_and_unknown_station(self) -> None:
        response = self.client.get("/api/stations/TEST")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["historical_record_count"], 60)
        missing = self.client.get("/api/stations/UNKNOWN")
        self.assertEqual(missing.status_code, 404)

    def test_history_and_timestamp_validation(self) -> None:
        response = self.client.get(
            "/api/stations/TEST/history",
            params={"start": "2025-07-01T00:00:00Z", "end": "2025-07-01T02:00:00Z", "limit": 3},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["record_count"], 3)
        invalid_order = self.client.get(
            "/api/stations/TEST/history",
            params={"start": "2025-07-02T00:00:00Z", "end": "2025-07-01T00:00:00Z"},
        )
        self.assertEqual(invalid_order.status_code, 400)
        naive_timestamp = self.client.get(
            "/api/stations/TEST/history?start=2025-07-01T00:00:00",
        )
        self.assertEqual(naive_timestamp.status_code, 400)

    def test_forecast_horizons_and_errors(self) -> None:
        expected = {
            30: ("2025-07-02T06:00:00Z", 1),
            60: ("2025-07-02T06:30:00Z", 2),
            180: ("2025-07-02T08:30:00Z", 6),
            360: ("2025-07-02T11:30:00Z", 12),
        }
        for horizon, (expected_timestamp, expected_count) in expected.items():
            response = self.client.get(f"/api/stations/TEST/forecast?horizon={horizon}")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["horizon_minutes"], horizon)
            self.assertEqual(payload["forecast_timestamp"], expected_timestamp)
            self.assertEqual(len(payload["forecast_points"]), expected_count)
            self.assertEqual(
                [point["horizon_minutes"] for point in payload["forecast_points"]],
                list(range(30, horizon + 1, 30)),
            )
            self.assertEqual(payload["model_name"], "seasonal_naive_daily")
            self.assertIn("raw_predicted_occupied_ports", payload)
        invalid = self.client.get("/api/stations/TEST/forecast?horizon=45")
        self.assertEqual(invalid.status_code, 400)
        insufficient = self.client.get("/api/stations/SHORT/forecast")
        self.assertEqual(insufficient.status_code, 400)

    def test_alert_thresholds_and_zero_denominator(self) -> None:
        expected = {"LOW": "low", "MOD": "moderate", "HIGH": "high", "ZERO": "unknown"}
        for station_id, level in expected.items():
            response = self.client.get(f"/api/stations/{station_id}/alerts")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["alert_level"], level)
        self.assertIsNone(self.client.get("/api/stations/ZERO/alerts").json()["operational_utilization"])


if __name__ == "__main__":
    unittest.main()

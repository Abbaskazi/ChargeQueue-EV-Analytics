"""Run a one-process, read-only smoke test against the real local dataset."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from ..main import app


def main() -> None:
    """Verify the documented API routes without changing project artifacts."""

    with TestClient(app) as client:
        checks = {
            "health": client.get("/api/health"),
            "overview": client.get("/api/dataset/overview"),
            "stations": client.get("/api/stations?page=1&page_size=3"),
            "station": client.get("/api/stations/EV00144"),
            "history": client.get("/api/stations/EV00144/history?limit=3"),
            "forecast_30m": client.get("/api/stations/EV00144/forecast?horizon=30"),
            "forecast_60m": client.get("/api/stations/EV00144/forecast?horizon=60"),
            "alerts": client.get("/api/stations/EV00144/alerts"),
            "unknown_station": client.get("/api/stations/NOT_A_STATION"),
            "swagger": client.get("/docs"),
            "openapi": client.get("/openapi.json"),
            "redoc": client.get("/redoc"),
        }
        result = {name: response.status_code for name, response in checks.items()}
        result["forecast_30m_timestamp"] = checks["forecast_30m"].json().get("forecast_timestamp")
        result["forecast_60m_timestamp"] = checks["forecast_60m"].json().get("forecast_timestamp")
        result["forecast_30m_raw_prediction"] = checks["forecast_30m"].json().get("raw_predicted_occupied_ports")
        result["forecast_30m_display_prediction"] = checks["forecast_30m"].json().get("predicted_occupied_ports")
        result["forecast_60m_raw_prediction"] = checks["forecast_60m"].json().get("raw_predicted_occupied_ports")
        result["forecast_60m_display_prediction"] = checks["forecast_60m"].json().get("predicted_occupied_ports")
        result["alert_level"] = checks["alerts"].json().get("alert_level")
        result["alert_operational_utilization"] = checks["alerts"].json().get("operational_utilization")
        result["station_count"] = checks["overview"].json().get("total_stations")
        result["history_records_returned"] = checks["history"].json().get("record_count")
        print(json.dumps(result, indent=2))
        expected_successes = {
            "health": 200,
            "overview": 200,
            "stations": 200,
            "station": 200,
            "history": 200,
            "forecast_30m": 200,
            "forecast_60m": 200,
            "alerts": 200,
            "unknown_station": 404,
            "swagger": 200,
            "openapi": 200,
            "redoc": 200,
        }
        failures = {
            name: status
            for name, status in result.items()
            if name in expected_successes and status != expected_successes[name]
        }
        if failures:
            raise SystemExit(f"API verification failed: {failures}")


if __name__ == "__main__":
    main()

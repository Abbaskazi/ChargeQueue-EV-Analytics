"""Cached access to the processed ChargeQueue CSV for API requests."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .dataset_loader import read_csv_header


API_COLUMNS = [
    "station_id",
    "timestamp",
    "ports_total",
    "ports_available",
    "ports_occupied",
    "ports_out_of_service",
    "operational_utilization",
    "station_status",
]


def _json_safe(value: Any) -> Any:
    """Convert pandas/numpy scalars and missing values to JSON-safe values."""

    if value is None or value is pd.NA:
        return None
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(float(value)) else float(value)
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if pd.isna(value):
        return None
    return value


class DatasetService:
    """Load the processed data once and serve immutable, filtered views.

    The production instance caches only the API columns in memory. The source
    CSV remains read-only and is never rewritten by this service.
    """

    def __init__(
        self,
        processed_path: str | Path | None = None,
        overview_path: str | Path | None = None,
        quality_path: str | Path | None = None,
        station_summary_path: str | Path | None = None,
        frame: pd.DataFrame | None = None,
    ) -> None:
        root = Path(__file__).resolve().parents[3]
        self.processed_path = Path(processed_path or root / "data" / "processed" / "ev_charging_processed.csv")
        self.overview_path = Path(overview_path or root / "data" / "reports" / "eda" / "dataset_overview.json")
        self.quality_path = Path(quality_path or root / "data" / "reports" / "data_quality_report.json")
        self.station_summary_path = Path(
            station_summary_path or root / "data" / "reports" / "eda" / "station_demand_summary.csv"
        )
        self._frame = self._normalise_frame(frame) if frame is not None else None
        self._station_summary: pd.DataFrame | None = None
        self._available_columns: list[str] | None = None
        self._lock = threading.Lock()

    @staticmethod
    def _normalise_frame(frame: pd.DataFrame) -> pd.DataFrame:
        result = frame.copy()
        required = {"station_id", "timestamp", "ports_occupied"}
        missing = required.difference(result.columns)
        if missing:
            raise ValueError(f"API frame is missing required columns: {sorted(missing)}")
        result["station_id"] = result["station_id"].astype("string")
        result["timestamp"] = pd.to_datetime(result["timestamp"], errors="raise", utc=True)
        for column in [
            "ports_total",
            "ports_available",
            "ports_occupied",
            "ports_out_of_service",
            "operational_utilization",
        ]:
            if column in result:
                result[column] = pd.to_numeric(result[column], errors="coerce")
        if "station_status" not in result:
            result["station_status"] = pd.NA
        result = result.sort_values(["station_id", "timestamp"], kind="mergesort").reset_index(drop=True)
        return result

    @property
    def available(self) -> bool:
        return self.processed_path.exists() or self._frame is not None

    def load(self) -> pd.DataFrame:
        """Return the cached API frame, loading the processed CSV at most once."""

        if self._frame is None:
            with self._lock:
                if self._frame is None:
                    if not self.processed_path.exists():
                        raise FileNotFoundError(f"Processed dataset not found: {self.processed_path}")
                    columns = [column for column in API_COLUMNS if column in read_csv_header(self.processed_path)]
                    frame = pd.read_csv(
                        self.processed_path,
                        usecols=columns,
                        dtype={"station_id": "string", "timestamp": "string", "station_status": "string"},
                        low_memory=False,
                    )
                    self._frame = self._normalise_frame(frame)
        return self._frame

    def clear_cache(self) -> None:
        """Clear the in-memory frame; intended for tests and explicit invalidation."""

        with self._lock:
            self._frame = None
            self._station_summary = None

    def available_columns(self) -> list[str]:
        if self._available_columns is None:
            if self.processed_path.exists():
                self._available_columns = read_csv_header(self.processed_path)
            else:
                self._available_columns = list(self.load().columns)
        return list(self._available_columns)

    def _load_station_summary(self) -> pd.DataFrame:
        if self._station_summary is None:
            if self.station_summary_path.exists():
                summary = pd.read_csv(self.station_summary_path, low_memory=False)
                summary["station_id"] = summary["station_id"].astype(str)
                self._station_summary = summary
            else:
                frame = self.load()
                valid_util = frame["operational_utilization"].notna()
                grouped = frame.groupby("station_id", sort=True)
                self._station_summary = grouped.agg(
                    observation_count=("ports_occupied", "size"),
                    average_occupied_ports=("ports_occupied", "mean"),
                    minimum_occupied_ports=("ports_occupied", "min"),
                    maximum_occupied_ports=("ports_occupied", "max"),
                ).reset_index()
                util_counts = frame.loc[valid_util].groupby("station_id")["operational_utilization"].agg(
                    ["mean", "size"]
                )
                self._station_summary["average_operational_utilization"] = self._station_summary["station_id"].map(
                    util_counts["mean"]
                )
                self._station_summary["valid_utilization_observations"] = self._station_summary["station_id"].map(
                    util_counts["size"]
                ).fillna(0).astype(int)
        return self._station_summary

    def station_ids(self) -> list[str]:
        summary = self._load_station_summary()
        return sorted(summary["station_id"].astype(str).tolist())

    def get_overview(self) -> dict[str, Any]:
        if self.overview_path.exists():
            with self.overview_path.open("r", encoding="utf-8") as handle:
                overview = json.load(handle)
        else:
            frame = self.load()
            overview = {
                "total_observations": len(frame),
                "total_stations": int(frame["station_id"].nunique()),
                "minimum_timestamp_utc": frame["timestamp"].min().isoformat(),
                "maximum_timestamp_utc": frame["timestamp"].max().isoformat(),
                "sampling_frequency_minutes": 30,
            }
        quality: dict[str, Any] = {}
        if self.quality_path.exists():
            with self.quality_path.open("r", encoding="utf-8") as handle:
                report = json.load(handle)
            quality = {
                "missing_values": report.get("missing_values", {}),
                "duplicates": report.get("duplicates", {}),
                "timestamp_validation": report.get("timestamp_validation", {}),
                "port_validation": report.get("port_validation", {}),
                "utilization_validation": report.get("utilization_validation", {}),
                "estimated_wait_time_limitation": report.get("estimated_wait_time_limitation", {}),
            }
        return {
            "total_records": int(overview["total_observations"]),
            "total_stations": int(overview["total_stations"]),
            "dataset_start": pd.to_datetime(overview["minimum_timestamp_utc"], utc=True).to_pydatetime(),
            "dataset_end": pd.to_datetime(overview["maximum_timestamp_utc"], utc=True).to_pydatetime(),
            "sampling_frequency_minutes": int(overview.get("sampling_frequency_minutes", 30)),
            "available_columns": self.available_columns(),
            "quality_info": quality,
        }

    def get_station_summary(self, station_id: str) -> dict[str, Any] | None:
        summary = self._load_station_summary()
        rows = summary.loc[summary["station_id"].astype(str).eq(station_id)]
        if rows.empty:
            return None
        row = rows.iloc[0].to_dict()
        return {
            "station_id": station_id,
            "historical_record_count": int(row.get("observation_count", row.get("historical_record_count", 0))),
            "average_occupied_ports": _json_safe(row.get("average_occupied_ports")),
            "maximum_occupied_ports": _json_safe(row.get("maximum_occupied_ports")),
            "average_operational_utilization": _json_safe(row.get("average_operational_utilization")),
            "valid_utilization_observations": int(row.get("valid_utilization_observations", 0)),
            "minimum_occupied_ports": _json_safe(row.get("minimum_occupied_ports")),
        }

    def list_station_summaries(self, page: int, page_size: int, prefix: str | None = None) -> tuple[list[dict[str, Any]], int]:
        summary = self._load_station_summary().copy()
        summary["station_id"] = summary["station_id"].astype(str)
        if prefix:
            summary = summary.loc[summary["station_id"].str.startswith(prefix)]
        summary = summary.sort_values("station_id")
        total = len(summary)
        rows = summary.iloc[(page - 1) * page_size : page * page_size]
        return [self.get_station_summary(str(station_id)) for station_id in rows["station_id"]], total

    def station_history(
        self,
        station_id: str,
        start: pd.Timestamp | None = None,
        end: pd.Timestamp | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        frame = self.load()
        station = frame.loc[frame["station_id"].astype(str).eq(station_id)].copy()
        if station.empty:
            raise KeyError(station_id)
        if start is not None:
            station = station.loc[station["timestamp"] >= start]
        if end is not None:
            station = station.loc[station["timestamp"] <= end]
        station = station.sort_values("timestamp")
        if limit is not None:
            station = station.head(limit)
        return station.reset_index(drop=True)

    def latest_station_record(self, station_id: str) -> pd.Series:
        history = self.station_history(station_id)
        if history.empty:
            raise KeyError(station_id)
        return history.iloc[-1]

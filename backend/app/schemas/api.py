"""Request and response schemas for the Phase 6 backend API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    application_name: str
    version: str
    dataset_available: bool
    model_available: bool


class DatasetOverviewResponse(BaseModel):
    total_records: int
    total_stations: int
    dataset_start: datetime
    dataset_end: datetime
    sampling_frequency_minutes: int
    available_columns: list[str]
    quality_info: dict[str, Any]


class StationSummaryResponse(BaseModel):
    station_id: str
    historical_record_count: int
    average_occupied_ports: float | None
    maximum_occupied_ports: float | None
    average_operational_utilization: float | None
    valid_utilization_observations: int
    minimum_occupied_ports: float | None = None


class StationListResponse(BaseModel):
    stations: list[StationSummaryResponse]
    total_stations: int
    page: int
    page_size: int


class HistoryRecord(BaseModel):
    timestamp: datetime
    ports_total: int | None
    ports_available: int | None
    ports_occupied: int
    ports_out_of_service: int | None
    operational_utilization: float | None
    station_status: str | None


class HistoryResponse(BaseModel):
    station_id: str
    start_timestamp: datetime | None
    end_timestamp: datetime | None
    record_count: int
    records: list[HistoryRecord]


class ForecastPoint(BaseModel):
    forecast_timestamp: datetime
    horizon_minutes: int
    predicted_occupied_ports: int
    raw_predicted_occupied_ports: float


class ForecastResponse(BaseModel):
    station_id: str
    generated_at: datetime
    forecast_origin: datetime
    forecast_timestamp: datetime
    horizon_minutes: int = Field(description="Requested forecast horizon in minutes.")
    predicted_occupied_ports: int
    raw_predicted_occupied_ports: float
    model_name: str
    seasonal_period: int
    units: str
    model_configuration: dict[str, Any]
    limitations: list[str]
    forecast_points: list[ForecastPoint] = Field(default_factory=list)


class AlertResponse(BaseModel):
    station_id: str
    evaluation_timestamp: datetime
    current_timestamp: datetime
    current_occupancy: int
    operational_utilization: float | None
    alert_level: str
    alert_message: str
    threshold_note: str
    forecast_based: bool

"""REST endpoints for ChargeQueue dataset, forecasts, and alerts."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query

from ..models.common import ForecastingError, InsufficientHistoryError
from ..schemas.api import (
    AlertResponse,
    DatasetOverviewResponse,
    ForecastResponse,
    HealthResponse,
    HistoryResponse,
    StationListResponse,
    StationSummaryResponse,
)
from ..services.api_data_service import DatasetService
from ..services.congestion_alerts import classify_congestion
from ..services.forecasting_service import STEP_MINUTES, forecast_station
from ..services.model_registry import get_model_spec
from .dependencies import get_dataset_service


router = APIRouter(prefix="/api")
APP_NAME = "ChargeQueue API"
API_VERSION = "0.1.0"
SELECTED_MODEL = "seasonal_naive_daily"


def _utc_datetime(value: datetime | None, name: str) -> pd.Timestamp | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise HTTPException(status_code=400, detail=f"{name} must include a timezone; use UTC timestamps.")
    return pd.Timestamp(value).tz_convert("UTC")


def _station_or_404(service: DatasetService, station_id: str) -> dict:
    summary = service.get_station_summary(station_id)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Unknown station_id: {station_id}")
    return summary


@router.get("/health", response_model=HealthResponse, summary="Check API and data availability")
def health(service: DatasetService = Depends(get_dataset_service)) -> HealthResponse:
    model_available = True
    try:
        get_model_spec(SELECTED_MODEL)
    except ValueError:
        model_available = False
    return HealthResponse(
        status="ok" if service.available and model_available else "degraded",
        application_name=APP_NAME,
        version=API_VERSION,
        dataset_available=service.available,
        model_available=model_available,
    )


@router.get("/dataset/overview", response_model=DatasetOverviewResponse, summary="Return verified dataset overview")
def dataset_overview(service: DatasetService = Depends(get_dataset_service)) -> DatasetOverviewResponse:
    try:
        return DatasetOverviewResponse(**service.get_overview())
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Processed dataset is unavailable.") from exc


@router.get("/stations", response_model=StationListResponse, summary="List available charging stations")
def stations(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    prefix: str | None = Query(None, min_length=1, max_length=20),
    service: DatasetService = Depends(get_dataset_service),
) -> StationListResponse:
    summaries, total = service.list_station_summaries(page, page_size, prefix)
    return StationListResponse(
        stations=[StationSummaryResponse(**summary) for summary in summaries if summary is not None],
        total_stations=total,
        page=page,
        page_size=page_size,
    )


@router.get("/stations/{station_id}", response_model=StationSummaryResponse, summary="Return one station summary")
def station_details(station_id: str, service: DatasetService = Depends(get_dataset_service)) -> StationSummaryResponse:
    return StationSummaryResponse(**_station_or_404(service, station_id))


@router.get("/stations/{station_id}/history", response_model=HistoryResponse, summary="Return historical station demand")
def station_history(
    station_id: str,
    start: datetime | None = Query(None, description="Inclusive UTC start timestamp."),
    end: datetime | None = Query(None, description="Inclusive UTC end timestamp."),
    limit: int = Query(500, ge=1, le=5000),
    service: DatasetService = Depends(get_dataset_service),
) -> HistoryResponse:
    _station_or_404(service, station_id)
    start_utc = _utc_datetime(start, "start")
    end_utc = _utc_datetime(end, "end")
    if start_utc is not None and end_utc is not None and start_utc > end_utc:
        raise HTTPException(status_code=400, detail="start must be earlier than or equal to end.")
    try:
        frame = service.station_history(station_id, start_utc, end_utc, limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown station_id: {station_id}") from exc
    records = []
    for row in frame.to_dict(orient="records"):
        records.append(
            {
                "timestamp": row["timestamp"].to_pydatetime(),
                "ports_total": None if pd.isna(row.get("ports_total")) else int(row["ports_total"]),
                "ports_available": None if pd.isna(row.get("ports_available")) else int(row["ports_available"]),
                "ports_occupied": int(row["ports_occupied"]),
                "ports_out_of_service": None
                if pd.isna(row.get("ports_out_of_service"))
                else int(row["ports_out_of_service"]),
                "operational_utilization": None
                if pd.isna(row.get("operational_utilization"))
                else float(row["operational_utilization"]),
                "station_status": None if pd.isna(row.get("station_status")) else str(row["station_status"]),
            }
        )
    return HistoryResponse(
        station_id=station_id,
        start_timestamp=records[0]["timestamp"] if records else start_utc.to_pydatetime() if start_utc else None,
        end_timestamp=records[-1]["timestamp"] if records else end_utc.to_pydatetime() if end_utc else None,
        record_count=len(records),
        records=records,
    )


@router.get("/stations/{station_id}/forecast", response_model=ForecastResponse, summary="Forecast occupied ports")
def station_forecast(
    station_id: str,
    horizon: int = Query(60, description="Forecast horizon in minutes; supported values are 30, 60, 180, and 360."),
    history_window: int | None = Query(None, ge=49, le=8785, description="Optional recent-history size in rows."),
    service: DatasetService = Depends(get_dataset_service),
) -> ForecastResponse:
    if horizon not in {30, 60, 180, 360}:
        raise HTTPException(status_code=400, detail="horizon must be one of 30, 60, 180, or 360 minutes.")
    _station_or_404(service, station_id)
    try:
        history = service.station_history(station_id)
        result = forecast_station(
            history,
            SELECTED_MODEL,
            history_limit=history_window,
            horizon_steps=horizon // STEP_MINUTES,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown station_id: {station_id}") from exc
    except InsufficientHistoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (ForecastingError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=f"Forecast generation failed: {exc}") from exc
    selected_point = result["forecast_points"][-1]
    return ForecastResponse(
        station_id=station_id,
        generated_at=datetime.now(timezone.utc),
        forecast_origin=pd.Timestamp(result["forecast_origin"]).to_pydatetime(),
        forecast_timestamp=pd.Timestamp(selected_point["forecast_timestamp"]).to_pydatetime(),
        horizon_minutes=horizon,
        predicted_occupied_ports=int(selected_point["predicted_occupied_ports"]),
        raw_predicted_occupied_ports=float(selected_point["raw_predicted_occupied_ports"]),
        model_name=SELECTED_MODEL,
        seasonal_period=int(result["seasonal_period"]),
        units="occupied_ports",
        model_configuration=result["model_configuration"],
        limitations=[
            "The forecast targets occupied charging ports, not estimated waiting time.",
            "The selected model was chosen using Phase 5 validation results; it is not a universal optimum.",
            "Phase 5 used a sparse 14-day walk-forward stride and had limited coverage for SARIMA and weekly Holt-Winters.",
            "Displayed predictions are rounded and non-negative; raw statistical predictions are also returned.",
        ],
        forecast_points=result["forecast_points"],
    )


@router.get("/stations/{station_id}/alerts", response_model=AlertResponse, summary="Classify current station congestion")
def station_alert(station_id: str, service: DatasetService = Depends(get_dataset_service)) -> AlertResponse:
    _station_or_404(service, station_id)
    try:
        row = service.latest_station_record(station_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown station_id: {station_id}") from exc
    classification = classify_congestion(float(row["ports_available"]), float(row["ports_occupied"]))
    now = datetime.now(timezone.utc)
    return AlertResponse(
        station_id=station_id,
        evaluation_timestamp=now,
        current_timestamp=row["timestamp"].to_pydatetime(),
        current_occupancy=int(row["ports_occupied"]),
        forecast_based=False,
        **classification,
    )

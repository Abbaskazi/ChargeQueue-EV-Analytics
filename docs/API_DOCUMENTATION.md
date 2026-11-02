# ChargeQueue API Documentation

## Phase 6 scope

The Phase 6 backend is a local FastAPI service for the academic ChargeQueue project. It exposes verified historical station data, station summaries, the validation-selected occupied-port forecast, and transparent current-state congestion alerts. Frontend integration, authentication, databases, streaming, and deployment are outside this phase.

## Installation and startup

From the project root in Windows Command Prompt:

```cmd
python -m pip install -r backend\requirements.txt
python -m uvicorn backend.app.main:app --reload
```

The automatic API documentation is available at `http://127.0.0.1:8000/docs`, the OpenAPI schema at `/openapi.json`, and ReDoc at `/redoc`.

## Endpoints

### `GET /api/health`

Returns API, processed-dataset, and selected-model availability.

### `GET /api/dataset/overview`

Returns the verified record count, station count, UTC date range, 30-minute sampling interval, all processed CSV columns, and relevant Phase 2 quality information.

### `GET /api/stations?page=1&page_size=50&prefix=EV00`

Returns paginated station summaries. `page_size` is limited to 200. The optional prefix filter matches station identifiers.

### `GET /api/stations/{station_id}`

Returns historical record count, occupied-port summary statistics, and average operational utilization. Unknown stations return HTTP 404.

### `GET /api/stations/{station_id}/history?start=...&end=...&limit=500`

Returns chronological historical records. `start` and `end` are inclusive, timezone-aware UTC timestamps. The default limit is 500 and the maximum is 5,000. Naive timestamps and an end before the start return HTTP 400.

### `GET /api/stations/{station_id}/forecast?horizon=30`

Returns a one-step or two-step forecast for `horizon=30` or `horizon=60`. The endpoint uses the existing forecasting service and the Phase 5 validation-selected `seasonal_naive_daily` model with seasonal period 48. The forecast origin is the latest historical observation available for the station. An optional `history_window` can restrict the number of recent rows, but at least 49 observations are required by the daily two-step baseline.

The response includes both the raw floating-point prediction and a presentation prediction rounded to a non-negative integer and capped at a reliable constant station capacity. The raw value is not replaced by the display value.

Example:

```text
GET /api/stations/EV00144/forecast?horizon=60
```

```json
{
  "station_id": "EV00144",
  "horizon_minutes": 60,
  "predicted_occupied_ports": 12,
  "raw_predicted_occupied_ports": 12.0,
  "model_name": "seasonal_naive_daily",
  "seasonal_period": 48,
  "units": "occupied_ports"
}
```

The example values above illustrate response shape; live values come from the local processed dataset.

### `GET /api/stations/{station_id}/alerts`

Classifies the latest observed station state using operational utilization:

```text
ports_occupied / (ports_available + ports_occupied)
```

The provisional rules are low below 50%, moderate from 50% to below 80%, and high at 80% or above. These thresholds are reviewable project rules, not scientifically validated operational thresholds. A zero denominator returns `unknown` and a null utilization rather than an artificial zero.

## Error responses

- `400`: invalid horizon, timezone, timestamp ordering, or insufficient history.
- `404`: unknown station or unavailable processed dataset.
- `422`: FastAPI/Pydantic request validation failure, such as a non-numeric pagination value.
- `500`: unexpected forecast-generation failure; internal stack traces are not returned.

## Loading and caching

The application-level `DatasetService` reads only the API columns from `data/processed/ev_charging_processed.csv` and caches the resulting sorted frame for the process lifetime. Requests filter this shared frame rather than reopening the 362 MB CSV. The cache has no automatic file-watcher invalidation; restart the process after a deliberate processed-data refresh. Phase 6 does not modify the raw or processed CSV.

The Seasonal Naive model is lightweight and is invoked from the existing forecasting service using station history through the latest forecast origin. No future rows are used and no alternate model is silently substituted.

## Evaluation limitations carried forward

Phase 5 used a sparse 14-day walk-forward stride, not every 30-minute origin. Seasonal Naive daily, Seasonal Naive weekly, and daily Holt-Winters had all-station evaluation coverage. SARIMA and weekly Holt-Winters were evaluated only on representative stations, and weekly SARIMA was not evaluated. The API therefore exposes the selected validation configuration without presenting the selection as a universal optimum.

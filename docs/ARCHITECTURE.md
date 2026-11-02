# ChargeQueue Architecture

## Status

This document describes the current architecture and implementation boundary. Phase 2 provides dataset loading, validation, and preprocessing services. Phase 4 provides a modular forecasting engine and model registry. Phase 5 provides chronological evaluation artifacts. Phase 6 now provides the FastAPI API; frontend components remain unimplemented.

## Overall system architecture

ChargeQueue is planned as a small client-server application with four logical areas:

1. React/Vite frontend for dashboard presentation and user interaction.
2. FastAPI backend for application/API access and coordination.
3. Data-processing services for validating raw observations and creating derived data products.
4. Forecasting services for feature preparation, model execution, and forecast evaluation.

The architecture intentionally avoids additional infrastructure. Files and local Python services are sufficient for the planned academic workflow unless a later requirement changes that decision.

## Frontend responsibilities

The React frontend will:

- Present station and aggregate demand summaries.
- Render historical and forecast time series with Recharts.
- Display forecast horizon and congestion-alert status.
- Request dashboard data from the backend service.
- Handle loading, empty, and error states clearly.
- Keep visualization and interaction logic separate from backend and model logic.

Frontend pages and components are planned but are not implemented in Phase 1.

## Backend responsibilities

The FastAPI backend now:

- Expose documented HTTP endpoints for dashboard data.
- Validate request parameters and return consistent response shapes.
- Coordinate data and forecasting services.
- Avoid embedding data-cleaning or model-training logic directly in route handlers.
- Provide suitable error responses without exposing secrets or internal file details.
- Cache the processed CSV API columns in an application-level dataset service.
- Call the existing `forecast_station` service with the validation-selected `seasonal_naive_daily` model.
- Classify current congestion using a documented operational-utilization rule.

The API is implemented in Phase 6. It does not add a database or modify source data.

## Data-processing responsibilities

Data-processing services now:

- Read the verified source data without modifying the raw file.
- Validate columns, timestamps, station identifiers, ranges, duplicates, and missingness.
- Document assumptions and data-quality decisions.
- Produce derived data under `data/processed/` and reports under `data/reports/`.
- Preserve chronological order and ensure transformations do not use future information.

Phase 2 processed the full CSV in bounded chunks without modifying the raw file. No artificial observations were introduced and no charging-port observations were interpolated.

## Forecasting-engine responsibilities

The forecasting layer now:

- Define `ports_occupied` as the target and provide a two-step, 60-minute horizon.
- Provide Seasonal Naive daily/weekly baselines, additive Holt-Winters daily/weekly models, and a small configurable SARIMA model.
- Use a registry so callers select a model by name without knowing its internal implementation.
- Sort station histories chronologically and restrict input to the forecast origin to prevent future-data leakage.
- Return raw predictions, display-adjusted predictions, timestamps, configuration, diagnostics, warnings, and status.
- Support bounded development experiments; chronological evaluation and model selection remain Phase 5 work.

Forecasting modules are organized as follows:

```text
backend/app/models/
├── common.py
├── seasonal_naive.py
├── holt_winters.py
└── sarima.py

backend/app/services/
├── model_registry.py
├── forecasting_service.py
└── forecasting_experiment.py
```

No forecasting model is developed during Phase 1.

## Phase 6 API modules

```text
backend/app/
├── api/
│   ├── dependencies.py
│   └── routes.py
├── schemas/
│   └── api.py
├── services/
│   ├── api_data_service.py
│   ├── congestion_alerts.py
│   ├── forecasting_service.py
│   └── model_registry.py
└── main.py
```

Routes handle HTTP concerns and Pydantic response validation. `DatasetService` loads the API columns once and filters cached data. The forecasting route reuses the Phase 4 service and model registry; no duplicate Seasonal Naive implementation exists in the API layer. Alert logic is isolated in `congestion_alerts.py`.

## Communication between frontend and backend

The browser will communicate with the FastAPI service over HTTP using JSON responses. The frontend service layer will centralize API calls, while the backend will obtain data from processed artifacts and forecasting services. CORS and local development origins will be configured only when the backend and frontend phases begin.

## Expected API structure

The implemented API shape is:

```text
GET /api/health
GET /api/stations
GET /api/stations/{station_id}/history
GET /api/stations/{station_id}/forecast
GET /api/stations/{station_id}/alerts
```

Parameters, response schemas, error behavior, startup commands, caching, and limitations are documented in `docs/API_DOCUMENTATION.md`. FastAPI also exposes Swagger UI, OpenAPI, and ReDoc automatically.

## Data flow from raw CSV to dashboard

```text
Raw CSV in data/raw/
        |
        v
Schema and quality verification
        |
        v
Chronological preprocessing and derived data in data/processed/
        |
        +----------------------+
        v                      v
Historical summaries    Forecasting engine
        |                      |
        +----------+-----------+
                   v
          Forecasting engine
       (model registry and services)
                   |
                   v
          FastAPI service/API
                   |
                   v
          React/Vite dashboard
```

The raw dataset remains unchanged throughout the flow. Every later transformation and model result should be reproducible from documented inputs and code.

# ChargeQueue

## EV Charging Demand Forecasting and Congestion Alert System

ChargeQueue is an academic Time Series Data Analytics (TSDA) project. It is intended to analyze historical EV charging-station availability patterns, forecast occupied charging ports for the next 60 minutes, identify potential peak-demand periods, and provide congestion alerts through an interactive dashboard.

The backend API is implemented in Phase 6. Phases 1 and 2 established the documented foundation and processed station-wise time series, Phase 3 completed exploratory data analysis, Phase 4 implemented the forecasting model layer with bounded representative-station execution, and Phase 5 produced chronological evaluation artifacts with documented coverage limits. The React dashboard remains a future phase.

## Problem statement

EV charging stations experience demand that changes throughout the day. Operators and users need visibility into occupied ports, expected near-term demand, and possible congestion. ChargeQueue will investigate historical station availability and develop a time-series forecasting workflow to support these needs.

## Objectives

- Understand historical charging-station availability and occupancy patterns.
- Forecast the number of occupied charging ports for the next 60 minutes.
- Identify potential peak-demand and congestion periods.
- Expose forecast and alert information through a simple interactive dashboard.
- Document a reproducible, leakage-aware TSDA workflow.

## Dataset

The planned input is the **EV Charging Station Availability Tracking** dataset.

- Verified size: 1,317,750 records.
- Verified stations: 150.
- Verified observation interval: 30 minutes per station.
- Verified period: 2025-07-01 00:00 UTC through 2025-12-31 00:00 UTC.
- Verified width: 33 columns.
- Source: [Tolstoyj/ev-charging-station-availability-tracking](https://github.com/Tolstoyj/ev-charging-station-availability-tracking).

The original raw dataset remains unchanged and must not be committed to Git. Some field meanings, including the supplied utilization and estimated wait-time methodologies, remain unverified.

## Planned features

- Historical occupancy and utilization exploration, with Phase 3 reports and charts under `data/reports/eda/`.
- Station-level and aggregate demand views.
- 60-minute occupied-port forecasts using Seasonal Naive, Holt-Winters, and SARIMA development implementations.
- Potential congestion alerts based on documented thresholds or forecast behavior.
- Interactive charts and status summaries in a web dashboard.

## Technology stack

- Frontend: React.js, Vite, JavaScript, CSS, and Recharts.
- Backend: Python, FastAPI, and Uvicorn.
- Analytics: Pandas, NumPy, Matplotlib, and Seaborn.
- Forecasting: Statsmodels and Scikit-learn.
- Development environment: Visual Studio Code, Windows 11, and Windows CMD.

## Architecture overview

The planned system will separate browser presentation, backend/API services, data processing, and forecasting. Raw CSV data will be inspected and transformed into derived data products, forecasting services will consume leakage-controlled time-series features, and the backend will provide dashboard-ready responses to the React frontend. Details are documented in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Project directory structure

```text
ChargeQueue/
├── AGENTS.md
├── README.md
├── .gitignore
├── docs/
│   ├── PROJECT_PLAN.md
│   ├── ARCHITECTURE.md
│   ├── DATA_DICTIONARY.md
│   └── PHASE_LOG.md
├── data/
│   ├── raw/
│   ├── processed/
│   └── reports/
├── notebooks/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── services/
│   │   ├── models/
│   │   └── main.py
│   └── tests/
└── frontend/
    └── src/
        ├── components/
        ├── pages/
        └── services/
```

## Development phases

1. Project foundation and documentation — completed.
2. Dataset integration and preprocessing — completed.
3. Exploratory time-series analysis.
4. Time-series forecasting model development — completed for bounded representative experiments.
5. Model evaluation and selection — partially completed with chronological validation/test reports.
6. Backend/API implementation — completed with FastAPI dataset, history, forecast, and alert endpoints.
7. Frontend dashboard implementation — not started.
8. Integration and testing — not started.
9. Documentation and final academic presentation — not started.

Phases 1, 2, 3, 4, and 6 are complete at the current project state. Phase 5 has produced evaluation reports with documented representative-only limitations. Phase 7 has not started.

## Setup

Phase 2 uses the existing Python/Pandas environment for preprocessing, Phase 3 uses the EDA service to generate reports and charts, Phase 4 uses the forecasting services and `backend/requirements.txt`, and Phase 5 writes evaluation outputs under `data/reports/evaluation/`. Start the Phase 6 backend from Windows CMD with `python -m uvicorn backend.app.main:app --reload`. Endpoint details, response examples, caching, and limitations are documented in [`docs/API_DOCUMENTATION.md`](docs/API_DOCUMENTATION.md). Frontend setup remains for Phase 7.

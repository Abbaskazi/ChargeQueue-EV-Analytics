# ChargeQueue Project Plan

## Project context

ChargeQueue is an academic TSDA project for forecasting EV charging demand and identifying potential congestion. The project will use historical charging-station availability observations to support near-term operational awareness through a dashboard.

## Problem statement

Charging demand varies by time and station. Without a view of historical patterns and near-term expected occupancy, users and operators may have difficulty anticipating busy periods. ChargeQueue will analyze the number of occupied charging ports and forecast the next 60 minutes to support congestion alerts.

## Objectives

- Verify and understand the source dataset and its schema.
- Prepare a reproducible, quality-checked time-series dataset.
- Explore temporal, station-level, and aggregate occupancy patterns.
- Build and evaluate forecasting approaches for occupied charging ports over a 60-minute horizon.
- Provide forecast and congestion information through a simple web dashboard.
- Maintain clear documentation of assumptions, methods, and limitations.

## Scope

### In scope

- Historical EV charging-station availability analysis.
- Aggregate and, where supported by the data, station-level occupancy analysis.
- Time-series forecasting of occupied charging ports.
- Evaluation using chronological validation and test data.
- Congestion-alert logic documented and exposed through the planned application.
- React dashboard and FastAPI backend integration.

### Out of scope unless explicitly approved later

- Real-time station hardware integration.
- Reservation, billing, or payment functionality.
- Automatic control of charging infrastructure.
- Production cloud deployment or additional infrastructure.
- Claims about future conditions beyond what the data and evaluated models support.

## Dataset details

The integrated dataset is the EV Charging Station Availability Tracking dataset from https://github.com/Tolstoyj/ev-charging-station-availability-tracking. Phase 2 verified 1,317,750 records, 150 stations, 33 columns, 8,785 unique timestamps, and 30-minute station intervals from 2025-07-01 00:00 UTC through 2025-12-31 00:00 UTC. The original raw file remains immutable and excluded from Git. Field semantics that are not established by the CSV itself remain marked as unverified in the data dictionary.

## Functional requirements

1. Record the verified dataset schema and data-quality findings.
2. Preserve raw observations and generate traceable processed data products.
3. Support chronological analysis of occupied ports, availability, and utilization where fields are verified.
4. Produce a documented 60-minute occupied-port forecast.
5. Evaluate candidate forecasts using time-ordered validation and test data.
6. Identify potential congestion using a documented, reviewable rule.
7. Provide dashboard-ready backend responses for historical data, forecasts, and alerts.
8. Present relevant results using readable charts and status summaries.

## Non-functional requirements

- Maintainable, modular, and understandable code.
- Reproducible processing and evaluation steps.
- No time-series data leakage.
- Clear separation between frontend, backend, processing, and forecasting responsibilities.
- Reasonable performance for the stated dataset size without unnecessary infrastructure.
- Honest reporting of limitations, assumptions, and unverified schema details.
- Keep secrets and large data files out of source control.

## Technology stack

- React.js, Vite, JavaScript, CSS, and Recharts.
- Python, FastAPI, and Uvicorn.
- Pandas, NumPy, Matplotlib, and Seaborn.
- Statsmodels and Scikit-learn.
- Windows 11, Visual Studio Code, and Windows CMD for development.

## Development roadmap

1. Foundation: repository structure, instructions, and documentation.
2. Dataset integration and preprocessing: inspect the schema, validate records, create derived data products, and prepare station-wise series.
3. EDA: analyze occupancy, utilization, station behavior, temporal patterns, distributions, and outliers — completed.
4. Forecasting model development: implement Seasonal Naive, Holt-Winters, SARIMA, and a reusable forecast contract — completed.
5. Evaluation: compare models on chronological validation and test periods — partially completed with documented coverage limits.
6. Backend: implement application services and API endpoints — completed in Phase 6.
7. Frontend: implement dashboard pages, charts, and alert presentation — not started.
8. Integration and testing: test the complete workflow — not started.
9. Documentation and presentation: refine documentation and prepare the academic deliverables — not started.

## Expected deliverables

- A documented and verified data-understanding report.
- Reproducible processing and analysis artifacts.
- Evaluated forecasting model(s) for the 60-minute horizon.
- FastAPI backend with documented dashboard data endpoints.
- React/Vite dashboard with charts and congestion alerts.
- Tests, architecture documentation, limitations, and final academic project materials.

## Phase 3 completion record

Phase 3 completed a chunked exploratory analysis of the processed dataset. The analysis generated temporal, station-wise, distributional, seasonality, outlier, and forecasting-suitability outputs under `data/reports/eda/`, plus the reproducible notebook `notebooks/eda.ipynb`.

Measured highlights:

- Average occupied ports: 2.393753; median: 1.0; range: 0 to 23.
- Average operational utilization: 0.318250, excluding 84,382 zero-denominator rows.
- Busiest average hour: 17:00 UTC; least busy: 03:00 UTC.
- Highest-demand weekday: Monday; lowest: Sunday.
- Highest-demand month: December; lowest: October.
- Highest average-demand station: EV00144.
- IQR upper-bound outliers: 75,384 observations, or 5.72066%; no rows were removed.

The EDA supports investigating daily and weekly seasonal periods of 48 and 336 half-hour steps in Phase 4. It does not establish formal seasonality or forecast performance. The optional ADF assessment was documented as unavailable because `statsmodels` was not installed and the restricted environment could not reach pip.

## Phase 4 completion record

Phase 4 implemented a modular forecasting engine for the `ports_occupied` target and executed a bounded representative-station development experiment. The engine provides daily and weekly Seasonal Naive, additive daily and weekly Holt-Winters, and configurable SARIMA registrations. Daily SARIMA was executed with `order=(1,0,0)`, seasonal `order=(1,0,0,48)`, and `maxiter=50`. Weekly SARIMA remains registered but was not run in the bounded experiment because its 336-step seasonal state-space fit was outside the initial computation boundary.

Representative stations were selected from the Phase 3 station summary: EV00063 (low average demand, 0.151964), EV00105 (median-demand selection, 1.863062), and EV00144 (high average demand, 13.485031). Five configurations were attempted for each station, using the latest 2,000 observations for the bounded Statsmodels runs. All 15 runs completed; weekly Holt-Winters emitted convergence warnings for the representative stations, and those warnings are preserved in the sample output. The experiment is not formal evaluation and reports no MAE/RMSE.

The forecasting method and output contract are documented in `docs/FORECASTING_METHODOLOGY.md`. Phase 5 must perform chronological evaluation and comparison before any model is selected for application use.

## Phase 5 evaluation record

Phase 5 generated chronological split, walk-forward, station-wise, demand-group, model execution, selection, prediction, chart, and Markdown report outputs under `data/reports/evaluation/`. All 150 stations use the same 70/15/15 boundaries: training positions 0–6148, validation positions 6149–7466, and test positions 7467–8784. The UTC boundaries are recorded in `data_split_summary.json`.

The evaluation used a 672-step (14-day) stride with three validation and three test origins per station. Seasonal Naive daily, Seasonal Naive weekly, and daily Holt-Winters completed 900 fits each across all stations. Weekly Holt-Winters and daily SARIMA completed 18 representative fits each for EV00059, EV00063, and EV00144. No fits failed; weekly Holt-Winters generated 18 warnings.

Validation selected Seasonal Naive daily for both horizons. At 30 minutes its validation MAE/RMSE were 0.513333/1.446067; at 60 minutes they were 0.457778/1.429841. On the untouched test period, the selected model produced MAE/RMSE of 1.233333/2.350886 at 30 minutes and 1.015556/2.101322 at 60 minutes. Test results were not used for selection.

Because weekly Holt-Winters and SARIMA do not have all-station coverage and weekly SARIMA was not run, Phase 5 is marked Partially Completed. The methodology, limitations, and all measured outputs are documented in `docs/MODEL_EVALUATION_METHODOLOGY.md` and `data/reports/evaluation/EVALUATION_REPORT.md`.

## Phase 6 completion record

Phase 6 implemented the FastAPI backend without changing the raw or processed CSVs or regenerating Phase 1–5 results. The API exposes health, dataset overview, paginated station summaries, station history, selected-model occupied-port forecasts, and provisional current-state congestion alerts. `DatasetService` reads the required processed CSV columns once per application process and serves filtered copies from its cache. Forecast requests reuse the Phase 4 `forecast_station` service and the validation-selected `seasonal_naive_daily` model (period 48) for 30- and 60-minute horizons.

Phase 5 limitations remain visible in API documentation: evaluation used a sparse 14-day walk-forward stride, while SARIMA and weekly Holt-Winters had limited representative-station coverage. The API does not claim universal model optimality, real-time hardware integration, or reliable waiting-time prediction. Frontend development remains Phase 7.

## Phase 2 completion record

Phase 2 completed the bounded CSV integration and preprocessing workflow. The raw CSV was read in chunks and was not modified. A station-wise, chronologically sorted processed CSV was created with UTC timestamps, operational utilization, and calendar features. Validation reports cover schema, missingness, duplicates, timestamp frequency, station coverage, port balances, utilization discrepancies, and preprocessing exclusions.

Important limitations discovered:

- The supplied `utilization_rate` does not match the required operational-utilization formula for 99.6261% of comparable rows, so both fields must remain distinct.
- `estimated_wait_time_mins` is zero in 1,233,368 of 1,317,750 rows and its measurement methodology is unverified; it is not a reliable primary queue-wait target.
- No train/validation/test split, exploratory analysis, forecast, model, API, or frontend work has been performed.

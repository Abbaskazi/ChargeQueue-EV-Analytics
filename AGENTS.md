# ChargeQueue Development Instructions

## Project purpose and scope

ChargeQueue is an academic Time Series Data Analytics (TSDA) project titled **EV Charging Demand Forecasting and Congestion Alert System**. Its primary objective is to use historical EV charging-station availability data to forecast occupied charging ports for the next 60 minutes, identify possible peak-demand periods, and present congestion alerts through an interactive dashboard.

This repository is developed in explicit phases. Work must remain within the phase requested by the project owner. Do not begin a future phase automatically.

## Technology stack

- Frontend: React.js, Vite, JavaScript, CSS, and Recharts.
- Backend: Python, FastAPI, and Uvicorn.
- Data analytics: Pandas, NumPy, Matplotlib, and Seaborn.
- Forecasting: Statsmodels and Scikit-learn.
- Development environment: Visual Studio Code, Windows 11, and Windows Command Prompt (CMD).

Keep the stack simple. Add dependencies only when a clear project requirement justifies them.

## Repository structure

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

Backend modules own API and server-side behavior. Frontend modules own the dashboard presentation and browser-side interaction. Data-processing and forecasting logic should be kept modular and separated from request handling and UI code.

## Coding conventions

- Prefer small, understandable modules with one clear responsibility.
- Use descriptive names and avoid unexplained abbreviations.
- Follow standard Python formatting and type-oriented, readable function interfaces where practical.
- Use modern, readable JavaScript and keep React components focused.
- Keep configuration separate from application logic.
- Add comments only when they explain a non-obvious decision or data constraint.
- Do not introduce frameworks, services, or infrastructure that are not required.
- Preserve existing working functionality when making changes.

## Dataset handling rules

- The source dataset is the EV Charging Station Availability Tracking dataset from https://github.com/Tolstoyj/ev-charging-station-availability-tracking.
- Treat `data/raw/` as an immutable input area. Never overwrite, edit, or delete the original raw dataset.
- Do not commit the large raw CSV or other generated large data artifacts to Git.
- Store derived, reproducible outputs in `data/processed/` and generated analysis outputs in `data/reports/`.
- Inspect schemas and data quality before relying on a column. Unknown field definitions must be verified rather than guessed.
- Do not fabricate records, values, findings, model results, or evaluation metrics.

## Time-series forecasting rules

- Preserve timestamps and document timezone assumptions.
- Sort observations chronologically before time-series operations.
- Use chronological train, validation, and test splits; never randomly shuffle temporal observations.
- Fit transformations, imputers, scalers, feature generators, and models using training information only where applicable.
- Avoid leakage from future observations, future aggregates, or target-derived information.
- Record the forecast horizon, sampling interval, baseline, features, and evaluation method for each model.
- Forecast occupied charging ports for the requested 60-minute horizon only after the relevant phase authorizes model development.

## Testing expectations

- Run focused checks for every implemented change.
- Add backend tests for API and service behavior as those components are implemented.
- Validate data-processing steps on representative samples before using the full dataset.
- Test forecasting pipelines for chronological splitting and leakage-sensitive behavior.
- Keep tests reproducible and report commands and outcomes in the phase documentation.

## Documentation requirements

- Keep README and architecture/planning documents aligned with the actual implementation status.
- Do not describe planned components as already implemented.
- Update the preliminary data dictionary when verified schema information becomes available.
- Update `docs/PHASE_LOG.md` after every completed phase, including work completed, files changed, commands, verification, issues, and the next phase.
- Document assumptions, limitations, and unresolved questions rather than silently filling gaps.

## Phase-based workflow

1. Read the current phase request, relevant documentation, and existing code before changing files.
2. Confirm the requested scope and avoid beginning future phases.
3. Make the smallest modular change that satisfies the phase.
4. Verify the directory, code, documentation, and tests relevant to that phase.
5. Update `docs/PHASE_LOG.md` only after verification; mark the phase completed only when its required work is complete.
6. Report the exact files changed, verification results, limitations, and the next phase without executing it.

For Phase 1 specifically, establish documentation and directory structure only. Do not load or process the full CSV, perform EDA, develop forecasting models, implement API endpoints, develop frontend pages, or install unnecessary dependencies.

# ChargeQueue Forecasting Methodology

## Phase 4 scope

Phase 4 implements forecasting model contracts and bounded development experiments. It does not perform chronological train/validation/test splitting, formal model comparison, or final error reporting. Those activities belong to Phase 5.

## Forecasting problem

The target is `ports_occupied`, the observed number of occupied charging ports. The processed data has a 30-minute station-wise frequency, so the requested 60-minute horizon contains exactly two forecast steps. `estimated_wait_time_mins` and `utilization_rate` are not used as the primary target.

The EDA-supported seasonal periods are:

- Daily: 48 half-hour observations.
- Weekly: 336 half-hour observations.

## Models

### Seasonal Naive

The daily and weekly baselines copy the values at the corresponding positions in the latest complete seasonal cycle. The method accesses only values in the supplied history and raises an insufficient-history error when the requested seasonal positions are unavailable.

### Holt-Winters

Statsmodels `ExponentialSmoothing` is configured with additive trend and additive seasonality. Daily (`seasonal_periods=48`) and weekly (`seasonal_periods=336`) configurations were fitted in the representative experiment. At least two complete seasonal cycles are required. Statsmodels warnings are captured in the forecast output rather than hidden.

### SARIMA

The initial configuration is intentionally small: `order=(1, 0, 0)` and seasonal `order=(1, 0, 0, 48)` with `maxiter=50`. Daily SARIMA was fitted for the representative stations. A weekly SARIMA configuration is registered, but was not run in the bounded experiment because a 336-step seasonal state-space fit was reserved for a later controlled trial.

## Representative development experiment

Stations were selected from the Phase 3 `station_demand_summary.csv` by average occupied ports:

| Group | Station | Average occupied ports |
|---|---|---:|
| Low | EV00063 | 0.151964 |
| Medium | EV00105 | 1.863062 |
| High | EV00144 | 13.485031 |

The experiment read all available observations for these stations, then used the latest 2,000 observations to bound Statsmodels fitting time. The forecast origin for each run was the final supplied timestamp, `2025-12-31T00:00:00+00:00`. This is a development execution record, not a held-out test forecast.

## Forecast output contract

The service returns station ID, model name, forecast origin, timestamps at +30 and +60 minutes, raw predictions, display-adjusted predictions, seasonal period, configuration, diagnostics, warnings, and status. Raw statistical predictions are retained as floating-point values. Display predictions are rounded to the nearest integer, clamped to zero, and capped at `ports_total` only when that capacity is constant and therefore reliable for the station.

## Leakage prevention

Each station history is sorted chronologically. An optional forecast origin restricts input rows to timestamps at or before that origin. No future occupied-port values, future operational measurements, random shuffling, or train/test split is used in Phase 4. Calendar or exogenous features are not used by these models.

## Limitations and Phase 5 preparation

- The representative experiment is not formal evaluation and has no MAE/RMSE results.
- Statsmodels fitting is bounded to 2,000 recent observations in the development experiment; full-history fitting and scaling to all 150 stations require a controlled performance decision.
- Weekly Holt-Winters produced convergence warnings for the three representative stations even though forecasts were returned; these warnings are preserved and must be considered during evaluation.
- Weekly SARIMA remains implemented in the registry but was not executed in this bounded experiment.
- Display rounding and capacity capping are presentation post-processing, not part of model fitting.

Phase 5 should create chronological validation/test origins, compare the models using MAE and RMSE, inspect convergence and station-level behavior, and select configurations without using future data.

## Phase 5 evaluation record

Phase 5 applied shared 70/15/15 chronological boundaries to all 150 station series and used expanding-history walk-forward evaluation. The stride was 672 half-hour steps (14 days), producing three validation origins and three test origins per station. Metrics were calculated from raw predictions only.

Seasonal Naive daily, Seasonal Naive weekly, and daily Holt-Winters were evaluated across all 150 stations. Weekly Holt-Winters and daily SARIMA were evaluated for representative stations EV00059, EV00063, and EV00144. Weekly Holt-Winters produced 18 warnings; no fits failed. Weekly SARIMA was not evaluated.

Validation selected Seasonal Naive daily for both horizons: 30-minute MAE 0.513333 and RMSE 1.446067; 60-minute MAE 0.457778 and RMSE 1.429841. The selected model's test MAE/RMSE were 1.233333/2.350886 at 30 minutes and 1.015556/2.101322 at 60 minutes. These values are evaluation results for this dataset period, not operational guarantees.

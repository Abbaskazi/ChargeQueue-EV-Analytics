# ChargeQueue Model Evaluation Methodology

## Phase 5 scope

Phase 5 evaluates `ports_occupied` forecasts using actual held-out observations. It does not implement FastAPI endpoints, frontend components, or Phase 6 work.

## Chronological split

Each station has 8,785 observations on the same UTC timestamp sequence. A shared positional split was applied to all stations:

- Training: 6,149 observations, `2025-07-01T00:00:00+00:00` through `2025-11-06T02:00:00+00:00`.
- Validation: 1,318 observations, `2025-11-06T02:30:00+00:00` through `2025-12-03T13:00:00+00:00`.
- Test: 1,318 observations, `2025-12-03T13:30:00+00:00` through `2025-12-31T00:00:00+00:00`.

There is no overlap and no random shuffling. The first validation origin is the final training observation. The first test origin is the final validation observation. Both forecast steps must remain within the relevant evaluation partition.

## Walk-forward evaluation

At each origin, the existing forecasting service receives only the station history through that origin. It produces a genuine two-step forecast for +30 and +60 minutes. The actual observations at those timestamps are then compared with the raw model predictions. The origin advances chronologically.

The evaluation stride is 672 observations, or 20,160 minutes (14 days), with the final boundary origin explicitly included. This produces three validation origins and three test origins per station. A stride of one was not computationally practical because Statsmodels models would need thousands of repeated station-specific fits.

## Metrics

For each horizon, MAE and RMSE are calculated from raw floating-point model predictions:

```text
MAE  = mean(abs(actual - raw_prediction))
RMSE = sqrt(mean((actual - raw_prediction)^2))
```

Rounded, non-negative, capacity-capped display predictions are excluded from metrics. Negative raw predictions are retained and counted separately.

## Model coverage

The following configurations were evaluated for all 150 stations:

- Seasonal Naive daily, period 48.
- Seasonal Naive weekly, period 336.
- Holt-Winters daily, additive trend and seasonality, period 48.

Weekly Holt-Winters and daily SARIMA were evaluated for representative stations EV00059, EV00063, and EV00144. Weekly SARIMA was not evaluated because its 336-step seasonal state-space fit exceeded the bounded computation strategy.

Statsmodels fitting used the latest 1,000 observations available at each origin. This is a computation limit, not a future-data shortcut; all selected observations still end at the current origin.

## Demand groups

Stations were sorted by Phase 3 `average_occupied_ports` and divided into three equal-count rank groups: 50 low-demand, 50 medium-demand, and 50 high-demand stations. Grouping uses occupied-port demand, not operational utilization.

## Model selection

Overall selection uses validation results only. Complete all-station configurations with zero failed fits are eligible. The priority is:

1. Lowest validation MAE.
2. Lowest validation RMSE.
3. Fewer convergence warnings.
4. Lower execution time.

The selected configuration is then assessed on the untouched test period. Test results are not used to alter the selection.

## Measured selection result

Daily Seasonal Naive was selected for both horizons:

- 30 minutes: validation MAE 0.513333 and RMSE 1.446067.
- 60 minutes: validation MAE 0.457778 and RMSE 1.429841.

The selected configuration's test metrics were MAE 1.233333 and RMSE 2.350886 at 30 minutes, and MAE 1.015556 and RMSE 2.101322 at 60 minutes.

## Limitations

- The two-week stride means the evaluation contains three origins per partition rather than every 30-minute origin.
- Weekly Holt-Winters and SARIMA are representative-only results and cannot support a complete 150-station superiority claim.
- Weekly Holt-Winters produced convergence warnings at all 18 representative fits.
- Weekly SARIMA remains unevaluated.
- Results describe the July–December 2025 dataset period and are not operational guarantees.


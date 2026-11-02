"""Create Phase 5 charts and the measured evaluation report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .evaluation_visualizations import create_evaluation_charts


def _fmt(value: Any, digits: int = 6) -> str:
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def write_report(output_dir: Path) -> list[str]:
    """Generate charts and Markdown from evaluation artifacts only."""

    validation = pd.read_csv(output_dir / "validation_metrics.csv")
    test = pd.read_csv(output_dir / "test_metrics.csv")
    station = pd.read_csv(output_dir / "station_wise_metrics.csv")
    groups = pd.read_csv(output_dir / "demand_group_metrics.csv")
    predictions = pd.read_csv(output_dir / "evaluation_predictions.csv")
    split = json.loads((output_dir / "data_split_summary.json").read_text(encoding="utf-8"))
    selection = json.loads((output_dir / "model_selection.json").read_text(encoding="utf-8"))
    execution = json.loads((output_dir / "model_execution_summary.json").read_text(encoding="utf-8"))
    summary = json.loads((output_dir / "evaluation_summary.json").read_text(encoding="utf-8"))
    representative_ids = ", ".join(execution["representative_station_ids"])
    charts = create_evaluation_charts(output_dir / "charts", validation, station, groups, predictions)

    validation_table = validation[["model_name", "horizon", "mae", "rmse", "observation_count", "stations_with_predictions", "failed_fits", "warning_count"]].to_string(index=False, float_format=lambda value: f"{value:.6f}")
    test_table = test[["model_name", "horizon", "mae", "rmse", "observation_count", "stations_with_predictions", "failed_fits", "warning_count"]].to_string(index=False, float_format=lambda value: f"{value:.6f}")
    selected_lines = []
    for horizon, row in selection["selected_by_horizon"].items():
        selected_lines.append(
            f"- `{horizon}`: `{row['model_name']}` with validation MAE {_fmt(row['mae'])} and validation RMSE {_fmt(row['rmse'])}."
        )
    group_best_lines = []
    group_comparison = groups[(groups["partition"] == "validation") & (groups["stations_evaluated"] >= 50)]
    for (demand_group, horizon), frame in group_comparison.groupby(["demand_group", "horizon"]):
        best = frame.sort_values(["average_station_mae", "average_station_rmse"]).iloc[0]
        group_best_lines.append(
            f"- `{demand_group}` / `{horizon}`: `{best['model_name']}` had the lowest average station MAE ({best['average_station_mae']:.6f}) among configurations evaluated for that group."
        )
    chart_lines = "\n".join(f"- [charts/{chart}](charts/{chart})" for chart in charts)
    report = f"""# ChargeQueue Model Evaluation Report

## 1. Scope

This Phase 5 report evaluates `ports_occupied` forecasts using actual held-out observations from the processed dataset. Metrics use raw statistical predictions, not rounded or capacity-clipped display predictions. No API or frontend work was performed.

## 2. Data splitting

The same chronological timestamp boundaries were applied to all {split['station_count']} stations. The split used 70% training, 15% validation, and 15% test observations per station.

- Training: `{split['split']['train_start_timestamp']}` through `{split['split']['train_end_timestamp']}` ({split['split']['train_count']:,} observations per station).
- Validation: `{split['split']['validation_start_timestamp']}` through `{split['split']['validation_end_timestamp']}` ({split['split']['validation_count']:,} observations per station).
- Test: `{split['split']['test_start_timestamp']}` through `{split['split']['test_end_timestamp']}` ({split['split']['test_count']:,} observations per station).

The split contains no overlap and no random shuffling.

## 3. Evaluation methodology

Evaluation used expanding-history walk-forward forecasts with two steps from each origin. The evaluation stride was {execution['evaluation_stride_steps']} observations ({execution['evaluation_stride_minutes']} minutes), selected because repeated Statsmodels refitting at every 30-minute origin across 150 stations was not computationally practical. The validation and test origins were identical for all models being compared. Each model saw only observations at or before its forecast origin.

Validation origins: {execution['origin_counts']['validation']}. Test origins: {execution['origin_counts']['test']}.

MAE is the mean absolute raw prediction error. RMSE is the square root of the mean squared raw prediction error. Negative raw predictions were retained in metrics and counted separately.

## 4. Validation results

```text
{validation_table}
```

## 5. Test results

The test period remained untouched during model selection. These results are reported after the validation-based configurations were frozen.

```text
{test_table}
```

## 6. Selected configurations

Selection used validation MAE, then validation RMSE, warning count, and elapsed time. Only configurations with complete all-station coverage and zero failed fits were eligible for overall selection.

{chr(10).join(selected_lines)}

SARIMA and weekly Holt-Winters were evaluated only for the representative stations `{representative_ids}`. They are not eligible for an overall 150-station winner claim.

## 7. Station and demand-group analysis

Demand groups were created by sorting Phase 3 `average_occupied_ports` and assigning equal-count low, medium, and high groups. Demand and utilization were kept separate.

{chr(10).join(group_best_lines)}

Station-level metrics are available in `station_wise_metrics.csv`, and group summaries are available in `demand_group_metrics.csv`.

## 8. Execution reliability

| Model | Stations requested | Successful fits | Failed fits | Warnings |
|---|---:|---:|---:|---:|
"""
    for row in execution["by_model"]:
        report += f"| {row['model_name']} | {row['stations_requested']} | {row['successful_fits']} | {row['failed_fits']} | {row['warning_count']} |\n"
    report += f"""
Weekly Holt-Winters warnings, if present, are retained in `evaluation_run_log.csv`. Weekly SARIMA was not evaluated.

## 9. Charts

{chart_lines}

## 10. Limitations

- The two-week stride reduces the number of origins compared with a stride-1 evaluation.
- SARIMA results cover only three representative stations.
- Weekly SARIMA was not run because its seasonal state-space configuration was outside the computation budget.
- Evaluation results are specific to this dataset period and should not be interpreted as real-time operational guarantees.

## 11. Reproducibility outputs

- `data_split_summary.csv` and `data_split_summary.json`
- `validation_metrics.csv`
- `test_metrics.csv`
- `station_wise_metrics.csv`
- `demand_group_metrics.csv`
- `evaluation_predictions.csv`
- `evaluation_run_log.csv`
- `model_execution_summary.json`
- `model_selection.json`
- `evaluation_summary.json`
"""
    (output_dir / "EVALUATION_REPORT.md").write_text(report, encoding="utf-8")
    return charts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/reports/evaluation"))
    args = parser.parse_args()
    print(json.dumps({"charts": write_report(args.output_dir)}, indent=2))


if __name__ == "__main__":
    main()

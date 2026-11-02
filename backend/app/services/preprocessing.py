"""Phase 2 dataset validation and preprocessing pipeline for ChargeQueue."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .data_validator import (
    PORT_COLUMNS,
    calculate_operational_utilization,
    create_calendar_features,
    numeric_port_frame,
    parse_timestamps,
    sort_station_time_series,
    validate_port_balance,
)
from .dataset_loader import EXPECTED_COLUMNS, iter_csv_chunks, read_csv_header, read_csv_sample


CHUNK_SIZE = 100_000
REQUIRED_COLUMNS = {
    "station_id",
    "timestamp",
    *PORT_COLUMNS,
    "utilization_rate",
    "station_status",
    "estimated_wait_time_mins",
}
ADDED_COLUMNS = ["operational_utilization", "hour", "day", "calendar_timezone"]


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not math.isfinite(float(value)) else float(value)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (pd.Timestamp,)):  # pandas timestamps are not JSON-native
        return value.isoformat()
    if pd.isna(value):
        return None
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, default=_json_value)


def _safe_station_id(value: Any) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _update_hash_counts(counter: Counter[int], values: pd.Series) -> None:
    for value, count in values.value_counts(dropna=False).items():
        counter[int(value)] += int(count)


def _update_numeric_check(
    checks: dict[str, dict[str, Any]],
    name: str,
    evaluated: pd.Series,
    violations: pd.Series,
) -> None:
    evaluated_count = int(evaluated.sum())
    violation_count = int((evaluated & violations).sum())
    current = checks.setdefault(name, {"rows_evaluated": 0, "violations": 0})
    current["rows_evaluated"] += evaluated_count
    current["violations"] += violation_count


def _port_checks(frame: pd.DataFrame) -> dict[str, dict[str, Any]]:
    ports = numeric_port_frame(frame)
    complete = ports.notna().all(axis=1)
    checks: dict[str, dict[str, Any]] = {}
    balance = (
        ports["ports_available"]
        + ports["ports_occupied"]
        + ports["ports_out_of_service"]
        - ports["ports_total"]
    )
    _update_numeric_check(checks, "port_balance", complete, ~np.isclose(balance, 0.0, atol=1e-9, rtol=0.0))
    for column in PORT_COLUMNS:
        valid = ports[column].notna()
        _update_numeric_check(checks, f"negative_{column}", valid, ports[column].lt(0))
    for column in ["ports_available", "ports_occupied", "ports_out_of_service"]:
        valid = ports[[column, "ports_total"]].notna().all(axis=1)
        _update_numeric_check(checks, f"{column}_greater_than_total", valid, ports[column].gt(ports["ports_total"]))
    return checks


def _merge_check_counts(target: dict[str, dict[str, Any]], source: dict[str, dict[str, Any]]) -> None:
    for name, values in source.items():
        current = target.setdefault(name, {"rows_evaluated": 0, "violations": 0})
        current["rows_evaluated"] += values["rows_evaluated"]
        current["violations"] += values["violations"]


def _safe_percentage(numerator: int | float, denominator: int | float) -> float | None:
    return None if not denominator else float(numerator) / float(denominator) * 100.0


def _raw_column_roles(sample: pd.DataFrame) -> dict[str, str]:
    roles: dict[str, str] = {}
    for column in sample.columns:
        if column == "timestamp":
            roles[column] = "datetime"
        elif pd.api.types.is_bool_dtype(sample[column]):
            roles[column] = "categorical_boolean"
        elif pd.api.types.is_numeric_dtype(sample[column]):
            roles[column] = "numeric"
        else:
            roles[column] = "categorical_or_text"
    return roles


def _frequency_rows(keys: pd.DataFrame, station_counts: Counter[str], global_min: pd.Timestamp | None, global_max: pd.Timestamp | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    unique_keys = keys.drop_duplicates(["station_id", "timestamp"]).sort_values(
        ["station_id", "timestamp"], kind="mergesort"
    )
    expected_intervals = None
    if global_min is not None and global_max is not None:
        expected_intervals = int((global_max - global_min).total_seconds() // 1800) + 1

    frequency_rows: list[dict[str, Any]] = []
    station_rows: list[dict[str, Any]] = []
    for station_id, group in unique_keys.groupby("station_id", sort=True, dropna=False):
        station = str(station_id)
        timestamps = group["timestamp"].sort_values()
        deltas = timestamps.diff().dropna().dt.total_seconds().div(60.0)
        interval_count = int(len(deltas))
        regular_count = int(deltas.eq(30.0).sum())
        irregular_count = int((~deltas.eq(30.0)).sum())
        missing_intervals = 0
        for minutes in deltas[deltas.gt(30.0)].tolist():
            steps = minutes / 30.0
            if math.isclose(steps, round(steps), rel_tol=0.0, abs_tol=1e-9):
                missing_intervals += max(0, int(round(steps)) - 1)
        unique_count = int(len(timestamps))
        expected = expected_intervals
        coverage = None if not expected else unique_count / expected * 100.0
        insufficient = bool(expected and unique_count < expected * 0.8)
        row = {
            "station_id": station,
            "records": int(station_counts.get(station, 0)),
            "unique_timestamps": unique_count,
            "min_timestamp": timestamps.min().isoformat() if unique_count else None,
            "max_timestamp": timestamps.max().isoformat() if unique_count else None,
            "interval_count": interval_count,
            "interval_30m_count": regular_count,
            "interval_30m_percentage": _safe_percentage(regular_count, interval_count),
            "irregular_interval_count": irregular_count,
            "missing_intervals_count": int(missing_intervals),
            "min_interval_minutes": float(deltas.min()) if interval_count else None,
            "max_interval_minutes": float(deltas.max()) if interval_count else None,
            "expected_intervals_global_range": expected,
            "coverage_percentage_global_range": coverage,
            "insufficient_observations_lt_80pct_global_range": insufficient,
        }
        frequency_rows.append(
            {
                key: row[key]
                for key in [
                    "station_id",
                    "unique_timestamps",
                    "interval_count",
                    "interval_30m_count",
                    "interval_30m_percentage",
                    "irregular_interval_count",
                    "missing_intervals_count",
                    "min_interval_minutes",
                    "max_interval_minutes",
                    "min_timestamp",
                    "max_timestamp",
                ]
            }
        )
        station_rows.append(row)
    return pd.DataFrame(frequency_rows), pd.DataFrame(station_rows)


def run_pipeline(
    input_path: str | Path,
    processed_path: str | Path,
    reports_dir: str | Path,
    chunksize: int = CHUNK_SIZE,
) -> dict[str, Any]:
    """Validate and preprocess the complete CSV into station-sorted output."""

    input_path = Path(input_path)
    processed_path = Path(processed_path)
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    processed_path.parent.mkdir(parents=True, exist_ok=True)
    if not input_path.exists():
        raise FileNotFoundError(f"Input CSV not found: {input_path}")

    columns = read_csv_header(input_path)
    missing_required = sorted(REQUIRED_COLUMNS.difference(columns))
    if missing_required:
        raise ValueError(f"Required columns missing from CSV: {missing_required}")

    sample = read_csv_sample(input_path, 1_000)
    raw_roles = _raw_column_roles(sample)
    raw_dtypes = {column: str(dtype) for column, dtype in sample.dtypes.items()}
    missing_counts: Counter[str] = Counter()
    station_counts: Counter[str] = Counter()
    row_hash_counts: Counter[int] = Counter()
    station_timestamp_hash_counts: Counter[int] = Counter()
    unique_timestamps: set[pd.Timestamp] = set()
    port_checks: dict[str, dict[str, Any]] = {}
    source_utilization_count = 0
    utilization_discrepancy_count = 0
    utilization_abs_error_sum = 0.0
    utilization_abs_error_max = 0.0
    utilization_zero_denominator_count = 0
    wait_counts = {"non_missing": 0, "zero": 0, "positive": 0, "negative": 0}
    wait_min: float | None = None
    wait_max: float | None = None
    source_calendar_mismatches: Counter[str] = Counter()
    input_rows = 0
    output_rows = 0
    excluded_by_reason: Counter[str] = Counter()
    timestamp_invalid_count = 0
    timestamp_valid_count = 0
    global_min: pd.Timestamp | None = None
    global_max: pd.Timestamp | None = None
    partition_paths: dict[str, Path] = {}
    timestamp_key_path: Path
    first_output_columns: list[str] | None = None

    staging_dir = Path(tempfile.mkdtemp(prefix="chargequeue_phase2_", dir=str(processed_path.parent)))
    timestamp_key_path = staging_dir / "timestamp_keys.csv"
    try:
        for chunk in iter_csv_chunks(input_path, chunksize=chunksize, columns=columns):
            input_rows += len(chunk)
            missing_counts.update({column: int(value) for column, value in chunk.isna().sum().items()})
            _update_hash_counts(row_hash_counts, pd.util.hash_pandas_object(chunk, index=False))

            station_values = chunk["station_id"].astype("string").str.strip()
            valid_station = station_values.notna() & station_values.ne("")
            for station_id in station_values.loc[valid_station].astype(str):
                station_counts[station_id] += 1

            parsed_timestamps = parse_timestamps(chunk["timestamp"])
            valid_timestamp = parsed_timestamps.notna()
            timestamp_valid_count += int(valid_timestamp.sum())
            timestamp_invalid_count += int((~valid_timestamp).sum())
            if valid_timestamp.any():
                chunk_min = parsed_timestamps[valid_timestamp].min()
                chunk_max = parsed_timestamps[valid_timestamp].max()
                global_min = chunk_min if global_min is None else min(global_min, chunk_min)
                global_max = chunk_max if global_max is None else max(global_max, chunk_max)
                unique_timestamps.update(pd.unique(parsed_timestamps[valid_timestamp]))

            valid_key = valid_station & valid_timestamp
            key_frame = pd.DataFrame(
                {"station_id": station_values.loc[valid_key], "timestamp": parsed_timestamps.loc[valid_key]}
            )
            if not key_frame.empty:
                _update_hash_counts(
                    station_timestamp_hash_counts,
                    pd.util.hash_pandas_object(key_frame, index=False),
                )
                key_frame.to_csv(
                    timestamp_key_path,
                    mode="a",
                    header=not timestamp_key_path.exists(),
                    index=False,
                )

            _merge_check_counts(port_checks, _port_checks(chunk))
            operational = calculate_operational_utilization(chunk)
            denominator = pd.to_numeric(chunk["ports_available"], errors="coerce") + pd.to_numeric(
                chunk["ports_occupied"], errors="coerce"
            )
            utilization_zero_denominator_count += int(denominator.eq(0).sum())
            supplied_utilization = pd.to_numeric(chunk["utilization_rate"], errors="coerce")
            comparable = operational.notna() & supplied_utilization.notna()
            source_utilization_count += int(comparable.sum())
            if comparable.any():
                absolute_error = (operational[comparable] - supplied_utilization[comparable]).abs()
                utilization_abs_error_sum += float(absolute_error.sum())
                utilization_abs_error_max = max(utilization_abs_error_max, float(absolute_error.max()))
                utilization_discrepancy_count += int(absolute_error.gt(0.001).sum())

            wait = pd.to_numeric(chunk["estimated_wait_time_mins"], errors="coerce")
            wait_valid = wait.dropna()
            wait_counts["non_missing"] += int(len(wait_valid))
            wait_counts["zero"] += int(wait_valid.eq(0).sum())
            wait_counts["positive"] += int(wait_valid.gt(0).sum())
            wait_counts["negative"] += int(wait_valid.lt(0).sum())
            if not wait_valid.empty:
                current_min = float(wait_valid.min())
                current_max = float(wait_valid.max())
                wait_min = current_min if wait_min is None else min(wait_min, current_min)
                wait_max = current_max if wait_max is None else max(wait_max, current_max)

            for source_column, derived in [
                ("hour_of_day", parsed_timestamps.dt.hour),
                ("day_of_week", parsed_timestamps.dt.dayofweek),
                ("month", parsed_timestamps.dt.month),
                ("is_weekend", parsed_timestamps.dt.dayofweek.ge(5)),
            ]:
                if source_column in chunk:
                    source_values = chunk[source_column]
                    comparable_calendar = valid_timestamp & source_values.notna()
                    source_calendar_mismatches[source_column] += int(
                        (comparable_calendar & source_values.ne(derived)).sum()
                    )

            processed = chunk.copy()
            processed["station_id"] = station_values
            processed["timestamp"] = parsed_timestamps.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            for column in PORT_COLUMNS:
                processed[column] = pd.to_numeric(processed[column], errors="coerce")
            processed["utilization_rate"] = pd.to_numeric(processed["utilization_rate"], errors="coerce")
            processed["operational_utilization"] = operational
            processed = create_calendar_features(processed, "timestamp")
            processed["calendar_timezone"] = "UTC"
            if first_output_columns is None:
                first_output_columns = list(processed.columns)

            missing_station = ~valid_station
            invalid_time = ~valid_timestamp
            excluded_by_reason["missing_station_id"] += int((missing_station & ~invalid_time).sum())
            excluded_by_reason["invalid_timestamp"] += int((invalid_time & ~missing_station).sum())
            excluded_by_reason["missing_station_id_and_invalid_timestamp"] += int((missing_station & invalid_time).sum())
            valid_processed = processed.loc[~(missing_station | invalid_time)]
            output_rows += len(valid_processed)
            if not valid_processed.empty:
                for station_id, station_frame in valid_processed.groupby("station_id", sort=False):
                    station_key = str(station_id)
                    if station_key not in partition_paths:
                        partition_paths[station_key] = staging_dir / f"station_{len(partition_paths):04d}.csv"
                    partition_path = partition_paths[station_key]
                    station_frame.to_csv(
                        partition_path,
                        mode="a",
                        header=not partition_path.exists(),
                        index=False,
                    )

        if output_rows == 0:
            raise ValueError("No valid station/timestamp rows remained for preprocessing")

        final_columns = first_output_columns or []
        wrote_output = False
        for station_id in sorted(partition_paths):
            station_frame = pd.read_csv(partition_paths[station_id], low_memory=False)
            station_frame["timestamp"] = parse_timestamps(station_frame["timestamp"])
            station_frame = sort_station_time_series(station_frame)
            station_frame["timestamp"] = station_frame["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            station_frame.to_csv(
                processed_path,
                mode="a" if wrote_output else "w",
                header=not wrote_output,
                index=False,
                columns=final_columns,
            )
            wrote_output = True

        keys = pd.read_csv(timestamp_key_path, dtype={"station_id": "string"}, low_memory=False)
        keys["timestamp"] = parse_timestamps(keys["timestamp"])
        frequency_summary, station_summary = _frequency_rows(keys, station_counts, global_min, global_max)
        frequency_summary.to_csv(reports_dir / "timestamp_frequency_summary.csv", index=False)
        station_summary.to_csv(reports_dir / "station_time_series_summary.csv", index=False)

        station_timestamp_duplicates = sum(count - 1 for count in station_timestamp_hash_counts.values() if count > 1)
        fully_duplicated_rows = sum(count - 1 for count in row_hash_counts.values() if count > 1)
        duplicate_station_timestamp_rows = int(station_timestamp_duplicates)
        station_validation = station_summary.copy()
        if not station_validation.empty:
            station_validation["duplicate_station_timestamp_rows"] = duplicate_station_timestamp_rows
            station_validation["missing_station_id_rows"] = int(missing_counts.get("station_id", 0))
            station_validation["invalid_timestamp_rows_global"] = timestamp_invalid_count
        station_validation.to_csv(reports_dir / "station_validation_summary.csv", index=False)

        missing_rows = []
        for column in columns:
            count = int(missing_counts.get(column, 0))
            missing_rows.append(
                {
                    "column_name": column,
                    "raw_dtype_from_sample": raw_dtypes.get(column),
                    "inferred_role": raw_roles.get(column),
                    "non_missing_count": input_rows - count,
                    "missing_count": count,
                    "missing_percentage": _safe_percentage(count, input_rows),
                    "required_for_phase2": column in REQUIRED_COLUMNS,
                }
            )
        pd.DataFrame(missing_rows).to_csv(reports_dir / "column_validation_summary.csv", index=False)

        port_rows = []
        for check_name, values in port_checks.items():
            evaluated = values["rows_evaluated"]
            violations = values["violations"]
            port_rows.append(
                {
                    "check": check_name,
                    "rows_evaluated": evaluated,
                    "violations": violations,
                    "violation_percentage": _safe_percentage(violations, evaluated),
                }
            )
        pd.DataFrame(port_rows).to_csv(reports_dir / "port_balance_validation.csv", index=False)

        utilization_summary = pd.DataFrame(
            [
                {
                    "metric": "rows_with_calculable_operational_and_supplied_utilization",
                    "value": source_utilization_count,
                },
                {
                    "metric": "rows_with_absolute_discrepancy_greater_than_0.001",
                    "value": utilization_discrepancy_count,
                },
                {
                    "metric": "discrepancy_percentage_of_comparable_rows",
                    "value": _safe_percentage(utilization_discrepancy_count, source_utilization_count),
                },
                {
                    "metric": "mean_absolute_discrepancy",
                    "value": utilization_abs_error_sum / source_utilization_count if source_utilization_count else None,
                },
                {"metric": "maximum_absolute_discrepancy", "value": utilization_abs_error_max},
                {"metric": "zero_operational_denominator_rows", "value": utilization_zero_denominator_count},
                {"metric": "comparison_tolerance", "value": 0.001},
            ]
        )
        utilization_summary.to_csv(reports_dir / "utilization_validation_summary.csv", index=False)

        station_ids = sorted(station_counts)
        global_unique_timestamps = len(unique_timestamps)
        regular_station_count = int(
            station_summary["irregular_interval_count"].eq(0).sum() if not station_summary.empty else 0
        )
        overview = {
            "source": {
                "filename": input_path.name,
                "path": str(input_path),
                "file_size_bytes": input_path.stat().st_size,
            },
            "schema": {
                "rows": input_rows,
                "columns": len(columns),
                "column_names": columns,
                "raw_dtypes_from_1000_row_sample": raw_dtypes,
                "numeric_columns": [column for column, role in raw_roles.items() if role == "numeric"],
                "categorical_columns": [
                    column for column, role in raw_roles.items() if role.startswith("categorical")
                ],
                "datetime_columns": [column for column, role in raw_roles.items() if role == "datetime"],
            },
            "stations": {
                "unique_station_count": len(station_ids),
                "station_ids": station_ids,
                "records_per_station": dict(sorted(station_counts.items())),
            },
            "timestamps": {
                "unique_timestamp_count": global_unique_timestamps,
                "minimum_timestamp_utc": global_min.isoformat() if global_min is not None else None,
                "maximum_timestamp_utc": global_max.isoformat() if global_max is not None else None,
                "valid_timestamp_rows": timestamp_valid_count,
                "invalid_timestamp_rows": timestamp_invalid_count,
                "timezone_representation": "UTC",
            },
            "sampling": {
                "expected_interval_minutes": 30,
                "stations_with_no_irregular_intervals": regular_station_count,
                "stations_with_irregular_intervals": len(station_ids) - regular_station_count,
                "all_station_series_regular_30_minutes": regular_station_count == len(station_ids),
            },
            "target_selection": {
                "primary_target": "ports_occupied",
                "estimated_wait_time_mins_is_primary_target": False,
                "reason": "ports_occupied directly represents occupied charging ports; wait-time methodology is unverified.",
            },
        }
        _write_json(reports_dir / "dataset_overview.json", overview)

        quality_report = {
            "source_file": input_path.name,
            "rows": input_rows,
            "columns": len(columns),
            "missing_values": {
                "total_missing_cells": int(sum(missing_counts.values())),
                "by_column": {
                    column: {
                        "count": int(missing_counts.get(column, 0)),
                        "percentage": _safe_percentage(missing_counts.get(column, 0), input_rows),
                    }
                    for column in columns
                },
            },
            "duplicates": {
                "fully_duplicated_rows_extra_occurrences": int(fully_duplicated_rows),
                "duplicated_station_timestamp_rows_extra_occurrences": duplicate_station_timestamp_rows,
            },
            "timestamp_validation": {
                "invalid_timestamp_rows": timestamp_invalid_count,
                "valid_timestamp_rows": timestamp_valid_count,
                "minimum_timestamp_utc": global_min.isoformat() if global_min is not None else None,
                "maximum_timestamp_utc": global_max.isoformat() if global_max is not None else None,
                "unique_timestamp_count": global_unique_timestamps,
                "expected_frequency_minutes": 30,
            },
            "station_validation": {
                "unique_station_count": len(station_ids),
                "missing_station_id_rows": int(missing_counts.get("station_id", 0)),
                "insufficient_observation_threshold": "fewer than 80% of expected 30-minute intervals across the global date range",
                "stations_below_threshold": int(
                    station_summary["insufficient_observations_lt_80pct_global_range"].sum()
                    if not station_summary.empty
                    else 0
                ),
            },
            "port_validation": {"checks": port_rows},
            "utilization_validation": {
                "formula": "ports_occupied / (ports_available + ports_occupied)",
                "zero_denominator_rows_returned_as_null": utilization_zero_denominator_count,
                "comparable_rows": source_utilization_count,
                "discrepancy_rows_absolute_error_greater_than_0.001": utilization_discrepancy_count,
                "mean_absolute_discrepancy": utilization_abs_error_sum / source_utilization_count
                if source_utilization_count
                else None,
                "maximum_absolute_discrepancy": utilization_abs_error_max,
                "supplied_utilization_rate_preserved": True,
            },
            "calendar_validation": {
                "source_columns_compared_to_timestamp": dict(source_calendar_mismatches),
                "derived_features_added": ["hour", "day"],
                "existing_source_calendar_columns_preserved": [
                    column for column in ["hour_of_day", "day_of_week", "month", "is_weekend"] if column in columns
                ],
            },
            "estimated_wait_time_limitation": {
                "non_missing_rows": wait_counts["non_missing"],
                "zero_rows": wait_counts["zero"],
                "positive_rows": wait_counts["positive"],
                "negative_rows": wait_counts["negative"],
                "minimum_value": wait_min,
                "maximum_value": wait_max,
                "interpretation": "Most values and the measurement methodology must be verified; this field is not used as the primary target and should not be claimed as reliable real-world queue waiting time.",
            },
        }
        _write_json(reports_dir / "data_quality_report.json", quality_report)

        preprocessing_summary = {
            "source_file": input_path.name,
            "processed_file": str(processed_path),
            "input_rows": input_rows,
            "output_rows": output_rows,
            "excluded_rows": input_rows - output_rows,
            "excluded_by_reason": dict(excluded_by_reason),
            "retained_original_columns": columns,
            "added_columns": ["operational_utilization", "hour", "day", "calendar_timezone"],
            "preserved_source_calendar_columns": [
                column for column in ["hour_of_day", "day_of_week", "month", "is_weekend"] if column in columns
            ],
            "primary_target": "ports_occupied",
            "timezone": "UTC",
            "station_sort_order": "station_id ascending, timestamp ascending",
            "missing_observation_policy": "No artificial observations were introduced and no charging-port values were interpolated.",
            "future_information_policy": "No future occupied-port or operational measurements were generated or used as features; only row-local calendar fields were added.",
            "train_validation_test_split_performed": False,
            "forecasting_performed": False,
            "chunk_size": chunksize,
        }
        _write_json(reports_dir / "preprocessing_summary.json", preprocessing_summary)
        return {
            "overview": overview,
            "quality_report": quality_report,
            "preprocessing_summary": preprocessing_summary,
        }
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/raw/ev_charging_dataset.csv"))
    parser.add_argument("--processed", type=Path, default=Path("data/processed/ev_charging_processed.csv"))
    parser.add_argument("--reports-dir", type=Path, default=Path("data/reports"))
    parser.add_argument("--chunksize", type=int, default=CHUNK_SIZE)
    args = parser.parse_args()
    result = run_pipeline(args.input, args.processed, args.reports_dir, args.chunksize)
    print(json.dumps(result["preprocessing_summary"], indent=2, default=_json_value))


if __name__ == "__main__":
    main()

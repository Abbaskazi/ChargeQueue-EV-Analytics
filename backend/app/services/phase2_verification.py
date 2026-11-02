"""Final bounded checks for Phase 2 generated artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .data_validator import calculate_operational_utilization, parse_timestamps


def verify_outputs(raw_path: str | Path, processed_path: str | Path, expected_raw_size: int) -> dict[str, object]:
    raw_path = Path(raw_path)
    processed_path = Path(processed_path)
    if raw_path.stat().st_size != expected_raw_size:
        raise AssertionError(f"Raw file size changed: {raw_path.stat().st_size} != {expected_raw_size}")
    header = pd.read_csv(processed_path, nrows=0)
    required = {"station_id", "timestamp", "ports_occupied", "operational_utilization"}
    missing = sorted(required.difference(header.columns))
    if missing:
        raise AssertionError(f"Processed target/features missing: {missing}")

    usecols = [
        "station_id",
        "timestamp",
        "ports_available",
        "ports_occupied",
        "operational_utilization",
    ]
    rows = 0
    stations: set[str] = set()
    minimum_timestamp = None
    maximum_timestamp = None
    previous_station: str | None = None
    previous_timestamp = None
    unsorted_rows = 0
    utilization_mismatches = 0
    zero_denominator_rows = 0
    for chunk in pd.read_csv(processed_path, usecols=usecols, chunksize=100_000, low_memory=False):
        timestamps = parse_timestamps(chunk["timestamp"])
        station_ids = chunk["station_id"].astype(str)
        stations.update(station_ids.tolist())
        rows += len(chunk)
        minimum_timestamp = timestamps.min() if minimum_timestamp is None else min(minimum_timestamp, timestamps.min())
        maximum_timestamp = timestamps.max() if maximum_timestamp is None else max(maximum_timestamp, timestamps.max())
        local_previous_station = station_ids.shift(1).fillna("")
        local_previous_timestamp = timestamps.shift(1)
        local_unsorted = station_ids.lt(local_previous_station) | (
            station_ids.eq(local_previous_station) & timestamps.lt(local_previous_timestamp)
        )
        unsorted_rows += int(local_unsorted.fillna(False).sum())
        if previous_station is not None:
            first_station = station_ids.iloc[0]
            first_timestamp = timestamps.iloc[0]
            if first_station < previous_station or (
                first_station == previous_station and first_timestamp < previous_timestamp
            ):
                unsorted_rows += 1
        previous_station = station_ids.iloc[-1]
        previous_timestamp = timestamps.iloc[-1]

        operational = calculate_operational_utilization(chunk)
        supplied_operational = pd.to_numeric(chunk["operational_utilization"], errors="coerce")
        denominator = pd.to_numeric(chunk["ports_available"], errors="coerce") + pd.to_numeric(
            chunk["ports_occupied"], errors="coerce"
        )
        zero_denominator_rows += int(denominator.eq(0).sum())
        comparable = operational.notna() & supplied_operational.notna()
        utilization_mismatches += int(
            (comparable & ~np.isclose(operational, supplied_operational, atol=1e-9, rtol=0.0)).sum()
        )

    return {
        "raw_exists": raw_path.exists(),
        "raw_size_bytes": raw_path.stat().st_size,
        "processed_exists": processed_path.exists(),
        "processed_rows": rows,
        "processed_station_count": len(stations),
        "processed_minimum_timestamp_utc": minimum_timestamp.isoformat() if minimum_timestamp is not None else None,
        "processed_maximum_timestamp_utc": maximum_timestamp.isoformat() if maximum_timestamp is not None else None,
        "processed_sorted_by_station_and_timestamp": unsorted_rows == 0,
        "unsorted_rows": unsorted_rows,
        "primary_target_present": "ports_occupied" in header.columns,
        "operational_utilization_present": "operational_utilization" in header.columns,
        "operational_utilization_mismatches": utilization_mismatches,
        "zero_denominator_rows": zero_denominator_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("data/raw/ev_charging_dataset.csv"))
    parser.add_argument("--processed", type=Path, default=Path("data/processed/ev_charging_processed.csv"))
    parser.add_argument("--raw-size", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(verify_outputs(args.raw, args.processed, args.raw_size), indent=2))


if __name__ == "__main__":
    main()

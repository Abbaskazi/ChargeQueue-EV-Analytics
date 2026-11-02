"""CSV loading helpers for the ChargeQueue dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterator

import pandas as pd


EXPECTED_COLUMNS = {
    "station_id",
    "timestamp",
    "ports_total",
    "ports_available",
    "ports_occupied",
    "ports_out_of_service",
    "utilization_rate",
    "station_status",
    "estimated_wait_time_mins",
}


def read_csv_sample(path: str | Path, nrows: int = 1_000) -> pd.DataFrame:
    """Read a bounded sample for schema inspection without loading the dataset."""

    return pd.read_csv(path, nrows=nrows, low_memory=False)


def read_csv_header(path: str | Path) -> list[str]:
    """Return the CSV column names without reading data rows."""

    return list(pd.read_csv(path, nrows=0).columns)


def csv_read_kwargs(columns: list[str]) -> dict[str, object]:
    """Build stable read options while preserving raw non-key column inference."""

    dtype: dict[str, str] = {}
    if "station_id" in columns:
        dtype["station_id"] = "string"
    if "timestamp" in columns:
        dtype["timestamp"] = "string"
    return {"dtype": dtype, "low_memory": False}


def iter_csv_chunks(
    path: str | Path,
    chunksize: int = 100_000,
    columns: list[str] | None = None,
    usecols: list[str] | None = None,
) -> Iterator[pd.DataFrame]:
    """Yield bounded CSV chunks using stable key-column types."""

    actual_columns = columns or read_csv_header(path)
    selected_columns = usecols or actual_columns
    yield from pd.read_csv(
        path,
        chunksize=chunksize,
        usecols=usecols,
        **csv_read_kwargs(selected_columns),
    )


def _inspect(path: Path, sample_rows: int) -> dict[str, object]:
    sample = read_csv_sample(path, sample_rows)
    return {
        "path": str(path),
        "sample_rows": int(len(sample)),
        "columns": list(sample.columns),
        "dtypes": {column: str(dtype) for column, dtype in sample.dtypes.items()},
        "sample": sample.head(5).where(sample.head(5).notna(), None).to_dict(orient="records"),
        "expected_columns_present": sorted(EXPECTED_COLUMNS.intersection(sample.columns)),
        "expected_columns_missing": sorted(EXPECTED_COLUMNS.difference(sample.columns)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--sample-rows", type=int, default=1_000)
    args = parser.parse_args()
    print(json.dumps(_inspect(args.path, args.sample_rows), indent=2, default=str))


if __name__ == "__main__":
    main()

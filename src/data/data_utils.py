"""
data_utils.py — Core data loading and utility functions for the TWCS dataset.

Provides chunked-reading helpers so the full ~500 MB CSV is never loaded
entirely into memory during profiling / inspection steps.
"""

import os
import csv
import pandas as pd
from pathlib import Path
from typing import Optional, Iterator

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_CSV_PATH = PROJECT_ROOT / "archive" / "twcs" / "twcs.csv"
SAMPLE_CSV_PATH = PROJECT_ROOT / "archive" / "sample.csv"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

CHUNK_SIZE = 100_000  # rows per chunk — good trade-off for ~3M rows


def get_raw_csv_path() -> Path:
    """Return the path to the raw TWCS CSV, raising if missing."""
    if not RAW_CSV_PATH.exists():
        raise FileNotFoundError(
            f"Raw dataset not found at {RAW_CSV_PATH}. "
            "Place twcs.csv inside archive/twcs/."
        )
    return RAW_CSV_PATH


def iter_chunks(
    path: Optional[Path] = None,
    chunksize: int = CHUNK_SIZE,
    usecols: Optional[list] = None,
    dtype: Optional[dict] = None,
) -> Iterator[pd.DataFrame]:
    """
    Yield DataFrames of *chunksize* rows from the CSV at *path*.

    Parameters
    ----------
    path : Path, optional
        Defaults to the raw TWCS CSV.
    chunksize : int
        Number of rows per chunk.
    usecols : list[str], optional
        Subset of columns to read (saves memory).
    dtype : dict, optional
        Explicit dtype map forwarded to pd.read_csv.
    """
    if path is None:
        path = get_raw_csv_path()

    reader = pd.read_csv(
        path,
        chunksize=chunksize,
        usecols=usecols,
        dtype=dtype,
        low_memory=False,
        encoding="utf-8",
    )
    yield from reader


def load_full(
    path: Optional[Path] = None,
    usecols: Optional[list] = None,
    dtype: Optional[dict] = None,
) -> pd.DataFrame:
    """
    Load the entire CSV into a single DataFrame.

    Use sparingly — ~3M rows × 7 cols ≈ 1–2 GB in RAM.
    """
    if path is None:
        path = get_raw_csv_path()
    return pd.read_csv(
        path,
        usecols=usecols,
        dtype=dtype,
        low_memory=False,
        encoding="utf-8",
    )


def file_size_mb(path: Optional[Path] = None) -> float:
    """Return file size in megabytes."""
    if path is None:
        path = get_raw_csv_path()
    return os.path.getsize(path) / (1024 * 1024)


def quick_row_count(path: Optional[Path] = None) -> int:
    """
    Count rows using the csv module (faster than pandas for just counting).
    Subtracts 1 for the header.
    """
    if path is None:
        path = get_raw_csv_path()
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        count = sum(1 for _ in reader)
    return count - 1  # exclude header

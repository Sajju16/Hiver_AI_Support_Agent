"""
inspect_dataset.py — Reusable dataset inspection module for TWCS dataset.

Inspects:
  - Total row count, file size, columns, data types
  - Missing values per column
  - Duplicate tweet IDs
  - Inbound vs Outbound distribution
  - Unique authors (customers vs brands)
  - Sample records

Usage:
    python -m src.data.inspect_dataset
"""

import sys, json, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from src.data.data_utils import get_raw_csv_path, iter_chunks, file_size_mb, CHUNK_SIZE

OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def inspect_dataset(dataset_path=None):
    if dataset_path is None:
        dataset_path = get_raw_csv_path()

    print("=" * 70)
    print(f"INSPECTING DATASET: {dataset_path}")
    print("=" * 70)

    size_mb = file_size_mb(dataset_path)
    size_bytes = Path(dataset_path).stat().st_size
    print(f"File Size: {size_mb:.2f} MB ({size_bytes:,} bytes)")

    t0 = time.time()
    total_rows = 0
    missing_counts = {}
    dtypes_seen = {}
    inbound_counts = {"True": 0, "False": 0}
    unique_authors = set()
    brand_authors = set()
    tweet_ids = set()
    duplicate_tweet_ids = 0
    sample_records = []

    for chunk in iter_chunks(dataset_path):
        if total_rows == 0:
            for col in chunk.columns:
                missing_counts[col] = 0
                dtypes_seen[col] = str(chunk[col].dtype)

        for col in chunk.columns:
            missing_counts[col] += int(chunk[col].isna().sum())

        for tid in chunk['tweet_id']:
            tid_str = str(tid)
            if tid_str in tweet_ids:
                duplicate_tweet_ids += 1
            else:
                tweet_ids.add(tid_str)

        for _, row in chunk.iterrows():
            author = str(row['author_id'])
            inbound = str(row['inbound']).strip().capitalize()
            
            unique_authors.add(author)
            if inbound == "True":
                inbound_counts["True"] += 1
            else:
                inbound_counts["False"] += 1
                brand_authors.add(author)

        if len(sample_records) < 5:
            sample_records.extend(chunk.head(5 - len(sample_records)).to_dict(orient="records"))

        total_rows += len(chunk)

    elapsed = time.time() - t0

    profile = {
        "file_info": {
            "path": str(dataset_path),
            "size_mb": round(size_mb, 2),
            "size_bytes": size_bytes
        },
        "total_rows": total_rows,
        "elapsed_seconds": round(elapsed, 2),
        "columns": list(missing_counts.keys()),
        "data_types": dtypes_seen,
        "missing_values": missing_counts,
        "duplicate_tweet_ids": duplicate_tweet_ids,
        "inbound_distribution": {
            "inbound_customer (True)": inbound_counts["True"],
            "outbound_brand (False)": inbound_counts["False"],
            "inbound_pct": round(inbound_counts["True"] / total_rows * 100, 2),
            "outbound_pct": round(inbound_counts["False"] / total_rows * 100, 2),
        },
        "authors": {
            "total_unique_authors": len(unique_authors),
            "unique_brand_handles": len(brand_authors),
            "unique_customer_authors": len(unique_authors - brand_authors),
        },
        "sample_records": sample_records[:3],
    }

    out_path = OUTPUT_DIR / "dataset_profile.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, default=str)

    print(f"\nCompleted in {elapsed:.2f}s")
    print(f"Total Rows: {total_rows:,}")
    print(f"Duplicate Tweet IDs: {duplicate_tweet_ids}")
    print(f"Inbound Ratio: {profile['inbound_distribution']['inbound_pct']}% inbound vs {profile['inbound_distribution']['outbound_pct']}% outbound")
    print(f"Unique Authors: {len(unique_authors):,} ({len(brand_authors)} brand handles)")

    return profile


if __name__ == "__main__":
    inspect_dataset()

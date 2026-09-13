"""
inspect_dataset.py — Phase 1 dataset inspection for the TWCS dataset.

Produces a comprehensive profiling report via chunked processing.

Usage:
    py scripts/inspect_dataset.py
"""

import sys, os, json, time
from pathlib import Path
from collections import Counter, defaultdict

# Ensure project root is on the path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from src.data.data_utils import (
    get_raw_csv_path, iter_chunks, file_size_mb, CHUNK_SIZE
)

# ── Output directory ─────────────────────────────────────────────────────────
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def inspect():
    csv_path = get_raw_csv_path()
    print(f"=== TWCS Dataset Inspection ===")
    print(f"File: {csv_path}")
    print(f"Size: {file_size_mb():.1f} MB")

    # ── 1. Read header & first chunk for schema ─────────────────────────────
    first_chunk = next(iter_chunks(chunksize=5))
    columns = list(first_chunk.columns)
    print(f"\nColumns ({len(columns)}): {columns}")
    print(f"\nFirst 5 rows:")
    print(first_chunk.to_string(index=False))
    print(f"\nDtypes:\n{first_chunk.dtypes}")

    # ── 2. Chunked profiling ────────────────────────────────────────────────
    total_rows = 0
    null_counts = Counter()
    dtype_samples = {}
    inbound_counts = Counter()
    author_counts = Counter()
    duplicate_tweet_ids = Counter()
    tweets_with_response = 0
    tweets_with_in_response_to = 0
    tweets_with_text = 0
    text_lengths = []
    created_at_samples = []
    response_tweet_id_samples = []
    malformed_rows = 0
    empty_text_count = 0

    # Brand detection: authors that appear as outbound (inbound == False)
    outbound_authors = Counter()
    inbound_authors = Counter()

    print(f"\nProcessing in chunks of {CHUNK_SIZE}...")
    t0 = time.time()

    for i, chunk in enumerate(iter_chunks()):
        n = len(chunk)
        total_rows += n

        # Null counts per column
        for col in chunk.columns:
            null_counts[col] += chunk[col].isna().sum()

        # Inbound distribution
        inbound_counts.update(chunk["inbound"].value_counts().to_dict())

        # Author frequency
        author_counts.update(chunk["author_id"].value_counts().to_dict())

        # Duplicate tweet_id tracking
        duplicate_tweet_ids.update(chunk["tweet_id"].value_counts().to_dict())

        # Response link stats
        tweets_with_response += chunk["response_tweet_id"].notna().sum()
        tweets_with_in_response_to += chunk["in_response_to_tweet_id"].notna().sum()

        # Text stats
        text_mask = chunk["text"].notna() & (chunk["text"].astype(str).str.strip() != "")
        tweets_with_text += text_mask.sum()
        empty_text_count += (~text_mask).sum()

        # Sample text lengths (sample to keep memory low)
        sample_texts = chunk.loc[text_mask, "text"].astype(str)
        text_lengths.extend(sample_texts.str.len().tolist()[:500])

        # Outbound vs inbound authors
        outbound_mask = chunk["inbound"] == False
        inbound_mask = chunk["inbound"] == True
        outbound_authors.update(
            chunk.loc[outbound_mask, "author_id"].value_counts().to_dict()
        )
        inbound_authors.update(
            chunk.loc[inbound_mask, "author_id"].value_counts().to_dict()
        )

        # Sample timestamps
        if len(created_at_samples) < 20:
            created_at_samples.extend(
                chunk["created_at"].dropna().head(5).tolist()
            )

        # Sample response_tweet_id formats
        if len(response_tweet_id_samples) < 20:
            response_tweet_id_samples.extend(
                chunk["response_tweet_id"].dropna().head(5).astype(str).tolist()
            )

        if (i + 1) % 5 == 0:
            print(f"  ... processed {total_rows:,} rows ({time.time()-t0:.1f}s)")

    elapsed = time.time() - t0
    print(f"\nTotal rows: {total_rows:,}  (processed in {elapsed:.1f}s)")

    # ── 3. Duplicate analysis ───────────────────────────────────────────────
    exact_duplicate_ids = {tid: c for tid, c in duplicate_tweet_ids.items() if c > 1}
    num_duplicate_ids = len(exact_duplicate_ids)
    total_duplicate_rows = sum(c - 1 for c in exact_duplicate_ids.values())

    # ── 4. Brand identification ─────────────────────────────────────────────
    # Brands are outbound authors (inbound==False) — sort by tweet count
    top_brands = outbound_authors.most_common(50)
    top_inbound_authors = inbound_authors.most_common(20)

    # ── 5. Text length stats ────────────────────────────────────────────────
    import statistics
    text_len_stats = {
        "count": len(text_lengths),
        "min": min(text_lengths) if text_lengths else 0,
        "max": max(text_lengths) if text_lengths else 0,
        "mean": statistics.mean(text_lengths) if text_lengths else 0,
        "median": statistics.median(text_lengths) if text_lengths else 0,
    }

    # ── 6. Build results dict ───────────────────────────────────────────────
    results = {
        "file_path": str(csv_path),
        "file_size_mb": round(file_size_mb(), 1),
        "total_rows": total_rows,
        "columns": columns,
        "null_counts": dict(null_counts),
        "null_percentages": {
            col: round(null_counts[col] / total_rows * 100, 2)
            for col in columns
        },
        "inbound_distribution": dict(inbound_counts),
        "tweets_with_response_link": int(tweets_with_response),
        "tweets_with_in_response_to": int(tweets_with_in_response_to),
        "tweets_with_text": int(tweets_with_text),
        "empty_text_count": int(empty_text_count),
        "text_length_stats": text_len_stats,
        "duplicate_tweet_ids_count": num_duplicate_ids,
        "total_duplicate_rows": int(total_duplicate_rows),
        "unique_authors": len(author_counts),
        "top_brands_outbound": [
            {"author_id": aid, "outbound_tweets": c}
            for aid, c in top_brands[:30]
        ],
        "top_inbound_authors": [
            {"author_id": aid, "inbound_tweets": c}
            for aid, c in top_inbound_authors
        ],
        "timestamp_samples": created_at_samples[:10],
        "response_tweet_id_samples": response_tweet_id_samples[:10],
        "processing_time_seconds": round(elapsed, 1),
    }

    # ── 7. Save results ────────────────────────────────────────────────────
    out_path = OUTPUT_DIR / "dataset_profile.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nProfile saved to: {out_path}")

    # ── 8. Print summary ───────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("DATASET PROFILE SUMMARY")
    print("=" * 70)
    print(f"File size:              {results['file_size_mb']} MB")
    print(f"Total rows:             {results['total_rows']:,}")
    print(f"Columns:                {results['columns']}")
    print(f"\nNull counts:")
    for col in columns:
        pct = results['null_percentages'][col]
        print(f"  {col:30s}  {null_counts[col]:>10,}  ({pct}%)")

    print(f"\nInbound distribution:")
    for k, v in results['inbound_distribution'].items():
        print(f"  {str(k):10s}  {v:>10,}")

    print(f"\nTweets with response_tweet_id:      {results['tweets_with_response_link']:,}")
    print(f"Tweets with in_response_to_tweet_id: {results['tweets_with_in_response_to']:,}")
    print(f"Tweets with non-empty text:          {results['tweets_with_text']:,}")
    print(f"Tweets with empty/missing text:      {results['empty_text_count']:,}")

    print(f"\nText length: mean={text_len_stats['mean']:.0f}, "
          f"median={text_len_stats['median']:.0f}, "
          f"max={text_len_stats['max']}")

    print(f"\nDuplicate tweet_ids:   {num_duplicate_ids:,} IDs "
          f"({total_duplicate_rows:,} extra rows)")
    print(f"Unique authors:        {results['unique_authors']:,}")

    print(f"\nTop 15 brands (outbound authors):")
    for entry in results['top_brands_outbound'][:15]:
        print(f"  {entry['author_id']:25s}  {entry['outbound_tweets']:>8,} tweets")

    print(f"\nTimestamp samples:      {created_at_samples[:5]}")
    print(f"response_tweet_id samples: {response_tweet_id_samples[:5]}")

    return results


if __name__ == "__main__":
    inspect()

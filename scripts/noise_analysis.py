"""
noise_analysis.py — Blazingly fast vectorized noise analysis for TWCS dataset.

Usage:
    $env:PYTHONIOENCODING='utf-8'; py -u scripts/noise_analysis.py
"""

import sys, json, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from src.data.data_utils import get_raw_csv_path, CHUNK_SIZE

OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def analyze_noise():
    dataset_path = get_raw_csv_path()
    print("=" * 70)
    print("NOISE / DATA QUALITY ANALYSIS (Blazing Fast)")
    print("=" * 70)

    t0 = time.time()

    total_rows = 0
    all_tweet_ids = set()
    all_parent_refs = set()
    has_parent = set()
    has_children = set()

    empty_text = 0
    very_short_text = 0
    url_only = 0
    mention_only = 0
    has_masked_content = 0

    inbound_no_response = 0
    inbound_total = 0
    outbound_total = 0

    inbound_roots = 0
    outbound_roots = 0

    print("Scanning dataset in 200k chunks...")
    for chunk in pd.read_csv(dataset_path, chunksize=200_000, dtype={'tweet_id': str, 'author_id': str}, low_memory=False):
        # Tweet ID string
        tids = chunk['tweet_id'].astype(str).str.strip()
        
        # Parent ID float -> int string
        parents_raw = chunk['in_response_to_tweet_id']
        parents = parents_raw.dropna().astype(str).str.strip().str.rstrip('.0')
        parents = parents[~parents.isin(['nan', 'None', '', 'NaN'])]

        valid_tids = set(tids)
        valid_parents = set(parents)

        all_tweet_ids.update(valid_tids)
        all_parent_refs.update(valid_parents)

        chunk_parents_series = parents_raw.dropna()
        has_parent.update(tids.loc[chunk_parents_series.index])
        has_children.update(valid_parents)

        inbound_mask = chunk['inbound'].astype(str).str.upper() == 'TRUE'
        no_parent_mask = chunk['in_response_to_tweet_id'].isna()

        inbound_roots += (no_parent_mask & inbound_mask).sum()
        outbound_roots += (no_parent_mask & ~inbound_mask).sum()

        inbound_total += inbound_mask.sum()
        outbound_total += (~inbound_mask).sum()

        no_resp_mask = chunk['response_tweet_id'].isna()
        inbound_no_response += (inbound_mask & no_resp_mask).sum()

        text_series = chunk['text'].fillna('').astype(str).str.strip()
        empty_text += (text_series == '').sum()
        very_short_text += ((text_series != '') & (text_series.str.len() < 10)).sum()

        url_only += (text_series.str.startswith('http://') | text_series.str.startswith('https://')).sum()
        mention_only += (text_series.str.startswith('@') & ~text_series.str.contains(' ')).sum()
        has_masked_content += (text_series.str.contains('__email__') | text_series.str.contains('__url__')).sum()

        total_rows += len(chunk)
        print(f"  ... scanned {total_rows:,} rows ({time.time()-t0:.1f}s)", flush=True)

    elapsed = time.time() - t0
    print(f"Scanned {total_rows:,} rows in {elapsed:.2f}s", flush=True)

    orphan_refs = all_parent_refs - all_tweet_ids
    isolated = all_tweet_ids - has_parent - has_children

    results = {
        "total_rows": total_rows,
        "noise_summary": {
            "empty_text": int(empty_text),
            "very_short_text_lt10": int(very_short_text),
            "url_only_tweets": int(url_only),
            "mention_only_tweets": int(mention_only),
            "tweets_with_masked_content": int(has_masked_content),
            "inbound_without_response": int(inbound_no_response),
            "inbound_total": int(inbound_total),
            "outbound_total": int(outbound_total),
            "unanswered_rate_pct": round(
                inbound_no_response / max(inbound_total, 1) * 100, 2
            ),
        },
        "conversation_structure": {
            "total_roots": int(inbound_roots + outbound_roots),
            "inbound_roots": int(inbound_roots),
            "outbound_roots": int(outbound_roots),
            "orphan_parent_references": len(orphan_refs),
            "orphan_rate_pct": round(
                len(orphan_refs) / max(len(all_parent_refs), 1) * 100, 2
            ),
            "isolated_tweets": len(isolated),
            "isolated_rate_pct": round(
                len(isolated) / max(total_rows, 1) * 100, 2
            ),
            "tweets_with_parent": len(has_parent),
            "tweets_that_are_parents": len(has_children),
        },
        "recommended_exclusions": {
            "empty_text": "Exclude — no content to analyze",
            "url_only": "May exclude — low information content",
            "mention_only": "Exclude — no meaningful message",
            "isolated_tweets": "Exclude for conversation task — single orphan tweet without thread context",
            "orphan_references": "Cannot reconstruct full thread — parent tweet missing from dataset",
        },
    }

    print("\n" + "=" * 70, flush=True)
    print("NOISE ANALYSIS RESULTS", flush=True)
    print("=" * 70, flush=True)

    print("\n  Text Quality Issues:", flush=True)
    for k, v in results["noise_summary"].items():
        print(f"    {k:40s}  {v:>10}", flush=True)

    print("\n  Conversation Structure:", flush=True)
    for k, v in results["conversation_structure"].items():
        print(f"    {k:40s}  {v:>10}", flush=True)

    print("\n  Recommended Exclusion Rules:", flush=True)
    for k, v in results["recommended_exclusions"].items():
        print(f"    {k:30s}  {v}", flush=True)

    out_path = OUTPUT_DIR / "noise_analysis.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nSaved to {out_path}", flush=True)

    return results


if __name__ == "__main__":
    analyze_noise()

"""
brand_analysis.py — Per-brand deep analysis for candidate selection.

CORRECTED VERSION: Uses the full conversation graph properly.

The key insight: most conversations start with a CUSTOMER tweet (inbound=True).
Brand tweets are usually responses (children) — they have in_response_to_tweet_id set.
So we walk threads from ALL roots and check which brands participate.

Usage:
    $env:PYTHONIOENCODING='utf-8'; py scripts/brand_analysis.py
"""

import sys, json, time
from pathlib import Path
from collections import Counter, defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from src.data.data_utils import iter_chunks, CHUNK_SIZE

OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Top brands to deep-analyze (from inspection results)
TOP_BRANDS = [
    "AmazonHelp", "AppleSupport", "Uber_Support", "SpotifyCares",
    "Delta", "Tesco", "AmericanAir", "TMobileHelp", "comcastcares",
    "British_Airways", "SouthwestAir", "VirginTrains", "Ask_Spectrum",
    "XboxSupport", "sprintcare", "hulu_support", "sainsburys",
    "GWRHelp", "AskPlayStation", "ChipotleTweets",
]
TOP_BRAND_SET = set(TOP_BRANDS)


def analyze_brands():
    print("=" * 70)
    print("BRAND ANALYSIS — Full Graph Walk")
    print("=" * 70)

    # ── Pass 1: Build the full tweet graph (lightweight) ────────────────
    # Only store author_id and inbound flag per tweet (memory efficient)
    tweet_author = {}     # tid → author_id
    tweet_inbound = {}    # tid → bool
    parent_children = defaultdict(list)
    child_parent = {}
    roots = set()

    print("\nPass 1: Building tweet graph...")
    t0 = time.time()
    row_count = 0

    for chunk in iter_chunks(
        usecols=["tweet_id", "author_id", "inbound", "in_response_to_tweet_id"]
    ):
        for _, row in chunk.iterrows():
            tid = str(row["tweet_id"])
            author = str(row["author_id"]) if pd.notna(row["author_id"]) else ""
            inbound = bool(row["inbound"])

            parent_raw = row["in_response_to_tweet_id"]
            parent = None
            if pd.notna(parent_raw):
                parent = str(parent_raw).strip()
                if "." in parent:
                    try:
                        parent = str(int(float(parent)))
                    except (ValueError, OverflowError):
                        parent = None
                if parent in ("nan", "", "None"):
                    parent = None

            tweet_author[tid] = author
            tweet_inbound[tid] = inbound

            if parent:
                parent_children[parent].append(tid)
                child_parent[tid] = parent
            else:
                roots.add(tid)

            row_count += 1

        if row_count % 500_000 < CHUNK_SIZE:
            print(f"  ... {row_count:,} tweets ({time.time()-t0:.1f}s)")

    print(f"  Graph built: {row_count:,} tweets, {len(roots):,} roots ({time.time()-t0:.1f}s)")

    # ── Pass 2: Walk ALL roots and attribute conversations to brands ────
    print("\nPass 2: Walking ALL conversation threads...")
    t1 = time.time()

    # Per-brand accumulators
    brand_stats = {brand: {
        "outbound_tweets": 0,
        "total_conversations": 0,
        "usable_conversations": 0,  # has customer + brand
        "multi_turn_3plus": 0,
        "total_messages": 0,
        "customer_messages": 0,
        "brand_messages": 0,
        "single_tweet_conversations": 0,
        "max_thread_length": 0,
        "thread_lengths": [],  # for mean/median later
    } for brand in TOP_BRANDS}

    # Count outbound tweets per brand
    for tid, author in tweet_author.items():
        if author in TOP_BRAND_SET and not tweet_inbound.get(tid, True):
            brand_stats[author]["outbound_tweets"] += 1

    # Walk each root
    walked = 0
    for root_id in roots:
        # BFS
        queue = [root_id]
        visited = set()
        thread_tids = []

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            if current in tweet_author:
                thread_tids.append(current)
            for child in parent_children.get(current, []):
                if child not in visited:
                    queue.append(child)

        thread_len = len(thread_tids)
        if thread_len == 0:
            continue

        # Analyze thread
        participating_brands = set()
        has_customer = False
        cust_count = 0
        brand_count = 0

        for tid in thread_tids:
            author = tweet_author.get(tid, "")
            inb = tweet_inbound.get(tid, True)

            if inb:
                has_customer = True
                cust_count += 1
            else:
                if author in TOP_BRAND_SET:
                    participating_brands.add(author)
                brand_count += 1

        # Attribute to each participating brand
        for brand in participating_brands:
            s = brand_stats[brand]
            s["total_conversations"] += 1
            s["total_messages"] += thread_len
            s["customer_messages"] += cust_count
            s["brand_messages"] += brand_count
            s["thread_lengths"].append(thread_len)

            if thread_len == 1:
                s["single_tweet_conversations"] += 1
            if thread_len >= 3:
                s["multi_turn_3plus"] += 1
            if has_customer:
                s["usable_conversations"] += 1
            if thread_len > s["max_thread_length"]:
                s["max_thread_length"] = thread_len

        walked += 1
        if walked % 200_000 == 0:
            print(f"  ... walked {walked:,} roots ({time.time()-t1:.1f}s)")

    elapsed_total = time.time() - t0
    print(f"\nAnalysis complete ({elapsed_total:.1f}s)")

    # ── Compute averages ────────────────────────────────────────────────
    import statistics

    for brand in TOP_BRANDS:
        s = brand_stats[brand]
        lengths = s["thread_lengths"]
        if lengths:
            s["avg_thread_length"] = round(statistics.mean(lengths), 2)
            s["median_thread_length"] = statistics.median(lengths)
        else:
            s["avg_thread_length"] = 0
            s["median_thread_length"] = 0
        del s["thread_lengths"]  # Don't save the full list

    # ── Print results ───────────────────────────────────────────────────
    print("\n" + "=" * 120)
    print(f"{'Brand':25s} {'Outbound':>9s} {'Convos':>9s} {'Usable':>9s} "
          f"{'Multi3+':>9s} {'AvgLen':>7s} {'MedLen':>7s} {'MaxLen':>7s} "
          f"{'CustMsg':>9s} {'BrandMsg':>9s}")
    print("-" * 120)

    ranked = sorted(TOP_BRANDS,
                    key=lambda b: brand_stats[b]["usable_conversations"],
                    reverse=True)

    for brand in ranked:
        s = brand_stats[brand]
        print(f"{brand:25s} {s['outbound_tweets']:>9,} {s['total_conversations']:>9,} "
              f"{s['usable_conversations']:>9,} {s['multi_turn_3plus']:>9,} "
              f"{s['avg_thread_length']:>7.1f} {s['median_thread_length']:>7.0f} "
              f"{s['max_thread_length']:>7} "
              f"{s['customer_messages']:>9,} {s['brand_messages']:>9,}")

    # ── Save ────────────────────────────────────────────────────────────
    out_path = OUTPUT_DIR / "brand_analysis.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(brand_stats, f, indent=2, default=str)
    print(f"\nSaved to {out_path}")

    return brand_stats


if __name__ == "__main__":
    analyze_brands()

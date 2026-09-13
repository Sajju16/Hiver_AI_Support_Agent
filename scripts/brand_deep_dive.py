"""
brand_deep_dive.py — Blazingly fast candidate brand deep dive using parallel dict mapping.

Runs in ~8 seconds on 2.81M rows.

Usage:
    py -u scripts/brand_deep_dive.py
"""

import sys, json, time, re
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from src.data.data_utils import get_raw_csv_path

OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CANDIDATES = [
    "AmazonHelp",
    "AppleSupport",
    "Uber_Support",
    "SpotifyCares",
    "AmericanAir",
    "Delta",
    "comcastcares",
    "Tesco",
    "VirginTrains",
    "XboxSupport",
]
CANDIDATES_SET = set(CANDIDATES)

DM_KEYWORDS = [r"\bdm\b", r"direct message", r"private message", r"send us a message", r"link in bio", r"reach out in dm", r"help link"]
ACTION_KEYWORDS = [r"try ", r"check ", r"restart", r"steps", r"update", r"settings", r"http", r"please note", r"flight", r"policy", r"refund", r"order"]


def run_deep_dive():
    print("=" * 80, flush=True)
    print(" CANDIDATE BRAND DEEP DIVE & SELECTION ANALYSIS (Blazing Speed)", flush=True)
    print("=" * 80, flush=True)

    csv_path = get_raw_csv_path()
    print(f"Loading candidate dataset from {csv_path}...", flush=True)
    t0 = time.time()

    df = pd.read_csv(
        csv_path,
        dtype={'tweet_id': str, 'author_id': str, 'inbound': str, 'in_response_to_tweet_id': str},
        usecols=['tweet_id', 'author_id', 'inbound', 'created_at', 'text', 'in_response_to_tweet_id'],
        low_memory=False
    )
    print(f"Loaded {len(df):,} rows in {time.time()-t0:.1f}s", flush=True)

    t0_clean = time.time()
    tids = df['tweet_id'].astype(str).str.strip().values
    authors = df['author_id'].fillna('').astype(str).str.strip().values
    inbounds = (df['inbound'].astype(str).str.upper() == 'TRUE').values
    created_ats = df['created_at'].fillna('').astype(str).values
    texts = df['text'].fillna('').astype(str).values
    
    parent_series = df['in_response_to_tweet_id'].astype(str).str.strip().str.rstrip('.0')
    parents = parent_series.replace(['nan', 'None', '', 'NaN', '<NA>'], None).values

    print(f"Vectorized column extraction in {time.time()-t0_clean:.1f}s", flush=True)

    # Parallel dict mapping
    t0_idx = time.time()
    tweet_author = dict(zip(tids, authors))
    tweet_inbound = dict(zip(tids, [bool(x) for x in inbounds]))
    tweet_created = dict(zip(tids, created_ats))
    tweet_text = dict(zip(tids, texts))

    parent_children = defaultdict(list)
    roots = set()

    for tid, parent in zip(tids, parents):
        if parent:
            parent_children[parent].append(tid)
        else:
            roots.add(tid)

    print(f"Built parallel dict mappings & graph index in {time.time()-t0_idx:.1f}s", flush=True)

    # Pass 2: Walk conversations for candidate brands
    t1 = time.time()
    brand_data = {brand: {
        "conversations": [],
        "dm_handoff_count": 0,
        "inline_action_count": 0,
        "total_brand_responses": 0,
        "multi_turn_3plus": 0,
        "multi_turn_5plus": 0,
        "total_convos": 0,
    } for brand in CANDIDATES}

    walked = 0
    for root_id in roots:
        queue = [root_id]
        visited = set()
        thread_tids = []

        while queue:
            curr = queue.pop(0)
            if curr in visited:
                continue
            visited.add(curr)
            if curr in tweet_author:
                thread_tids.append(curr)
            for child in parent_children.get(curr, []):
                if child not in visited:
                    queue.append(child)

        if not thread_tids:
            continue

        participating = set()
        has_cust = False
        for tid in thread_tids:
            inb = tweet_inbound.get(tid, True)
            aut = tweet_author.get(tid, "")
            if inb:
                has_cust = True
            else:
                if aut in CANDIDATES_SET:
                    participating.add(aut)

        if not has_cust or not participating:
            continue

        thread_len = len(thread_tids)

        for brand in participating:
            b_data = brand_data[brand]
            b_data["total_convos"] += 1

            if thread_len >= 3:
                b_data["multi_turn_3plus"] += 1
            if thread_len >= 5:
                b_data["multi_turn_5plus"] += 1

            for tid in thread_tids:
                inb = tweet_inbound.get(tid, True)
                aut = tweet_author.get(tid, "")
                txt = tweet_text.get(tid, "")

                if not inb and aut == brand:
                    b_data["total_brand_responses"] += 1
                    txt_lower = txt.lower()

                    is_dm = any(re.search(pat, txt_lower) for pat in DM_KEYWORDS)
                    is_action = any(re.search(pat, txt_lower) for pat in ACTION_KEYWORDS)

                    if is_dm:
                        b_data["dm_handoff_count"] += 1
                    if is_action and not is_dm:
                        b_data["inline_action_count"] += 1

            if thread_len >= 3 and len(b_data["conversations"]) < 15:
                b_data["conversations"].append({
                    "conversation_id": f"{root_id}_{brand}",
                    "message_count": thread_len,
                    "root_tweet_id": root_id,
                    "customer_initial_query": next((tweet_text[t] for t in thread_tids if tweet_inbound.get(t, True)), ""),
                    "messages": [{
                        "tweet_id": str(t),
                        "author_id": str(tweet_author[t]),
                        "inbound": bool(tweet_inbound[t]),
                        "created_at": str(tweet_created[t]),
                        "text": str(tweet_text[t])
                    } for t in thread_tids]
                })

        walked += 1

    print(f"\nWalked candidate roots in {time.time()-t1:.1f}s", flush=True)

    summary_results = {}
    examples_by_brand = {}

    print("\n" + "=" * 95, flush=True)
    print(f"{'Brand':16s} {'Total Convos':>12s} {'3+ Turn':>9s} {'5+ Turn':>9s} {'Brand Msgs':>11s} {'DM Handoff %':>13s} {'Inline Action %':>15s}", flush=True)
    print("-" * 95, flush=True)

    for brand in CANDIDATES:
        bd = brand_data[brand]
        tot_convos = bd["total_convos"]
        tot_resp = max(bd["total_brand_responses"], 1)

        dm_pct = round(bd["dm_handoff_count"] / tot_resp * 100, 2)
        action_pct = round(bd["inline_action_count"] / tot_resp * 100, 2)
        m3_pct = round(bd["multi_turn_3plus"] / max(tot_convos, 1) * 100, 2)
        m5_pct = round(bd["multi_turn_5plus"] / max(tot_convos, 1) * 100, 2)

        summary_results[brand] = {
            "total_conversations": tot_convos,
            "multi_turn_3plus": bd["multi_turn_3plus"],
            "multi_turn_3plus_pct": m3_pct,
            "multi_turn_5plus": bd["multi_turn_5plus"],
            "multi_turn_5plus_pct": m5_pct,
            "total_brand_responses": bd["total_brand_responses"],
            "dm_handoff_count": bd["dm_handoff_count"],
            "dm_handoff_pct": dm_pct,
            "inline_action_count": bd["inline_action_count"],
            "inline_action_pct": action_pct,
        }

        print(f"{brand:16s} {tot_convos:>12,} {bd['multi_turn_3plus']:>9,} {bd['multi_turn_5plus']:>9,} {bd['total_brand_responses']:>11,} {dm_pct:>12.1f}% {action_pct:>14.1f}%", flush=True)

        examples_by_brand[brand] = bd["conversations"][:10]

    out_summary_path = OUTPUT_DIR / "brand_deep_dive_summary.json"
    out_examples_path = OUTPUT_DIR / "candidate_brand_examples.json"

    with open(out_summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_results, f, indent=2)

    with open(out_examples_path, "w", encoding="utf-8") as f:
        json.dump(examples_by_brand, f, indent=2)

    print(f"\nSummary metrics saved to: {out_summary_path}", flush=True)
    print(f"Extracted conversation examples saved to: {out_examples_path}", flush=True)

    return summary_results, examples_by_brand


if __name__ == "__main__":
    run_deep_dive()

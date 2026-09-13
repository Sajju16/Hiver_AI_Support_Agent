"""
scripts/find_delivery_vs_marked_delivered_candidates.py — Retrieve 8-10 Delivery vs Marked Delivered boundary candidates
"""

import sys, json, re
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from src.data.data_utils import get_raw_csv_path

import hashlib

GOLDEN_PATH = PROJECT_ROOT / "data" / "golden" / "golden_candidates_200.json"
CHECKSUM_PATH = PROJECT_ROOT / "data" / "golden" / "golden_candidates_200.json.sha256"
DEV_PATH = PROJECT_ROOT / "data" / "dev" / "dev_candidates_50.json"
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "delivery_vs_marked_delivered_candidates.json"

TARGET_BRAND = "AmazonHelp"
amazon_numeric_aids = {"115821", "115830", "115850", "116875", "116928", "117086", "116316", "115825", "120533", "116062"}

def verify_golden_checksum():
    if not CHECKSUM_PATH.exists():
        raise FileNotFoundError(f"Checksum file missing: {CHECKSUM_PATH}")
    with open(CHECKSUM_PATH, "r", encoding="utf-8") as f:
        stored_hash = f.read().strip().split()[0]
    with open(GOLDEN_PATH, "rb") as f:
        computed_hash = hashlib.sha256(f.read()).hexdigest()
    if computed_hash != stored_hash:
        raise ValueError(
            f"GOLDEN SET CHECKSUM MISMATCH!\n"
            f"Path: {GOLDEN_PATH}\n"
            f"Computed: {computed_hash}\n"
            f"Stored:   {stored_hash}"
        )
    print(f"VERIFIED CHECKSUM MATCH: {computed_hash} ({GOLDEN_PATH.name})")

def main():
    verify_golden_checksum()

    with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
        golden = json.load(f)
    with open(DEV_PATH, "r", encoding="utf-8") as f:
        dev = json.load(f)

    used_convos = set(c["conversation_id"] for c in golden).union(set(c["conversation_id"] for c in dev))
    used_turn_keys = set((c["conversation_id"], c["turn_index"]) for c in golden).union(set((c["conversation_id"], c["turn_index"]) for c in dev))

    print(f"Loaded Golden ({len(golden)}) and Dev ({len(dev)}). Used conversation IDs: {len(used_convos):,}")

    csv_path = get_raw_csv_path()
    df = pd.read_csv(
        csv_path,
        dtype={'tweet_id': str, 'author_id': str, 'inbound': str, 'in_response_to_tweet_id': str, 'response_tweet_id': str},
        low_memory=False
    )
    tids = df['tweet_id'].astype(str).str.strip().values
    authors = df['author_id'].fillna('').astype(str).str.strip().values
    inbounds = (df['inbound'].astype(str).str.upper() == 'TRUE').values
    texts = df['text'].fillna('').astype(str).values
    parent_series = df['in_response_to_tweet_id'].astype(str).str.strip().str.rstrip('.0')
    parents = parent_series.replace(['nan', 'None', '', 'NaN', '<NA>'], None).values

    tweet_author = dict(zip(tids, authors))
    tweet_inbound = dict(zip(tids, [bool(x) for x in inbounds]))
    tweet_text = dict(zip(tids, texts))
    tweet_parent = dict(zip(tids, parents))

    parent_children = defaultdict(list)
    for tid, parent in zip(tids, parents):
        if parent:
            parent_children[parent].append(tid)

    # Keywords bridging Delivery Delay and Marked Delivered Not Received
    delivery_keywords = ["track", "tracking", "delay", "delayed", "late", "where is my", "where's my", "haven't received", "hasn't arrived", "not arrived", "when will", "out for delivery", "dispatch", "shipment"]
    delivered_keywords = ["delivered", "says delivered", "show delivered", "marked delivered", "shows delivered", "showing as delivered", "delivered yesterday", "never received", "didn't receive", "stolen", "not delivered"]

    candidates = []

    for tid, author in tweet_author.items():
        is_cust = tweet_inbound.get(tid, True)
        if not is_cust:
            continue

        txt = tweet_text[tid]
        txt_lower = txt.lower()

        has_del = any(k in txt_lower for k in delivery_keywords)
        has_dvd = any(k in txt_lower for k in delivered_keywords)

        # Look for turns that mention both OR are ambiguous on non-receipt / delivery status
        if not (has_del and has_dvd):
            continue

        # Check local association with AmazonHelp
        direct_children_authors = [tweet_author.get(child) for child in parent_children.get(tid, [])]
        is_direct_child = TARGET_BRAND in direct_children_authors
        handles = re.findall(r'@(\w+)', txt)
        has_amazon_handle = any(h.lower() in ["amazonhelp", "amazon", "amazonca", "amazonuk", "amazonin", "amazonde"] for h in handles)
        has_mapped_numeric = any(h in amazon_numeric_aids for h in handles)

        if is_direct_child or has_amazon_handle or has_mapped_numeric:
            ancestors = []
            curr_parent = tweet_parent.get(tid)
            visited_ancestors = set()
            while curr_parent and curr_parent in tweet_author and curr_parent not in visited_ancestors:
                visited_ancestors.add(curr_parent)
                ancestors.append({
                    "author": tweet_author[curr_parent],
                    "text": tweet_text[curr_parent],
                    "is_customer": tweet_inbound.get(curr_parent, True),
                    "tweet_id": curr_parent
                })
                curr_parent = tweet_parent.get(curr_parent)

            ancestors.reverse()
            root_id = ancestors[0]["tweet_id"] if ancestors else tid
            cid = f"{root_id}_{TARGET_BRAND}"
            turn_idx = len([m for m in ancestors if m["is_customer"]])

            if cid in used_convos or (cid, turn_idx) in used_turn_keys:
                continue

            rationale = "Customer inquiry blends delivery tracking/status questions with non-receipt or marked-as-delivered dispute."

            candidates.append({
                "conversation_id": cid,
                "turn_index": turn_idx,
                "raw_text": txt,
                "thread_context": [
                    {"author": m["author"], "text": m["text"], "is_customer": m["is_customer"]}
                    for m in ancestors
                ],
                "retrieval_rationale": rationale
            })

    print(f"Found {len(candidates)} eligible boundary candidates.")

    # Save top 10 candidates
    selected_10 = candidates[:10]
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(selected_10, f, indent=2, ensure_ascii=False)

    print(f"Exported top 10 candidates to {OUTPUT_PATH}")

if __name__ == "__main__":
    main()

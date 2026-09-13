"""
extract_examples.py — Extract and display example conversations from the TWCS dataset.

Loads a small sample and reconstructs conversations to verify
the inbound/outbound semantics and conversation linking structure.

Usage:
    py scripts/extract_examples.py
"""

import sys, json, time
from pathlib import Path
from collections import defaultdict
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from src.data.data_utils import get_raw_csv_path

OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def parse_timestamp(ts_str):
    if pd.isna(ts_str) or not isinstance(ts_str, str):
        return None
    try:
        return datetime.strptime(ts_str, "%a %b %d %H:%M:%S %z %Y")
    except (ValueError, TypeError):
        return None


def extract_examples():
    """
    Load first 50k rows, reconstruct a few conversations, and verify
    inbound/outbound semantics with concrete examples.
    """
    csv_path = get_raw_csv_path()
    print("Loading first 50,000 rows for example extraction...")

    df = pd.read_csv(csv_path, nrows=50000, low_memory=False)
    print(f"Loaded {len(df):,} rows")

    # ── 1. Verify inbound semantics ─────────────────────────────────────
    print("\n" + "=" * 70)
    print("INBOUND/OUTBOUND SEMANTICS VERIFICATION")
    print("=" * 70)

    # Show examples of inbound=True (customer) and inbound=False (brand)
    inbound_true = df[df["inbound"] == True].head(5)
    inbound_false = df[df["inbound"] == False].head(5)

    print("\n--- inbound=True examples (should be CUSTOMER messages) ---")
    for _, row in inbound_true.iterrows():
        print(f"  tweet_id={row['tweet_id']}, author_id={row['author_id']}, "
              f"text={str(row['text'])[:100]}")

    print("\n--- inbound=False examples (should be BRAND responses) ---")
    for _, row in inbound_false.iterrows():
        print(f"  tweet_id={row['tweet_id']}, author_id={row['author_id']}, "
              f"text={str(row['text'])[:100]}")

    # Verify: all inbound=False authors should be brand handles
    outbound_authors = df[df["inbound"] == False]["author_id"].unique()
    inbound_authors = df[df["inbound"] == True]["author_id"].unique()

    print(f"\nUnique outbound (brand) authors in sample: {len(outbound_authors)}")
    print(f"  Examples: {list(outbound_authors[:15])}")
    print(f"Unique inbound (customer) authors in sample: {len(inbound_authors)}")
    print(f"  Examples: {list(inbound_authors[:10])}")

    # Check if any author appears in BOTH inbound and outbound
    overlap = set(outbound_authors) & set(inbound_authors)
    if overlap:
        print(f"\n⚠️  Authors appearing as BOTH inbound and outbound: {len(overlap)}")
        print(f"  Examples: {list(overlap)[:10]}")
    else:
        print(f"\n✓ No overlap: brands and customers are distinct author sets")

    # ── 2. Reconstruct example conversations ────────────────────────────
    print("\n" + "=" * 70)
    print("CONVERSATION RECONSTRUCTION EXAMPLES")
    print("=" * 70)

    # Build index
    tweet_map = {}
    parent_children = defaultdict(list)
    roots = set()

    for _, row in df.iterrows():
        tid = str(row["tweet_id"])
        parent_raw = row["in_response_to_tweet_id"]
        parent = str(int(parent_raw)) if pd.notna(parent_raw) else None

        tweet_map[tid] = {
            "tweet_id": tid,
            "author_id": str(row["author_id"]),
            "inbound": row["inbound"],
            "created_at": str(row["created_at"]),
            "text": str(row["text"]),
            "in_response_to": parent,
        }

        if parent:
            parent_children[parent].append(tid)
        else:
            roots.add(tid)

    print(f"Tweets indexed: {len(tweet_map):,}")
    print(f"Roots: {len(roots):,}")

    # Walk a few conversations
    example_convos = []
    for root_id in roots:
        queue = [root_id]
        visited = set()
        thread = []

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            if current in tweet_map:
                thread.append(tweet_map[current])
            for child in parent_children.get(current, []):
                if child not in visited:
                    queue.append(child)

        # Sort by timestamp
        thread.sort(key=lambda t: parse_timestamp(t["created_at"]) or datetime.min)

        # Only keep conversations with >= 3 messages and both customer + brand
        has_cust = any(t["inbound"] for t in thread)
        has_brand = any(not t["inbound"] for t in thread)

        if len(thread) >= 3 and has_cust and has_brand:
            example_convos.append(thread)
            if len(example_convos) >= 10:
                break

    print(f"\nFound {len(example_convos)} example multi-turn conversations\n")

    examples_output = []

    for i, thread in enumerate(example_convos[:5]):
        print(f"\n{'─' * 70}")
        print(f"CONVERSATION #{i+1} ({len(thread)} messages)")
        print(f"{'─' * 70}")

        conv_data = {
            "conversation_number": i + 1,
            "message_count": len(thread),
            "messages": [],
        }

        for msg in thread:
            direction = "CUSTOMER →" if msg["inbound"] else "  BRAND ←"
            text_clean = msg["text"].replace("\n", " ").strip()
            print(f"  [{direction}] @{msg['author_id']} (id:{msg['tweet_id']})")
            print(f"    {msg['created_at']}")
            print(f"    {text_clean[:200]}")
            print()
            conv_data["messages"].append({
                "tweet_id": msg["tweet_id"],
                "author_id": msg["author_id"],
                "inbound": msg["inbound"],
                "direction": "customer" if msg["inbound"] else "brand",
                "created_at": msg["created_at"],
                "text": text_clean,
            })

        examples_output.append(conv_data)

    # ── 3. Analyze linking structure ────────────────────────────────────
    print("\n" + "=" * 70)
    print("CONVERSATION LINKING ANALYSIS")
    print("=" * 70)

    # Check response_tweet_id patterns
    resp_col = df["response_tweet_id"]
    print(f"\nresponse_tweet_id analysis:")
    print(f"  Non-null: {resp_col.notna().sum():,}")
    print(f"  Null:     {resp_col.isna().sum():,}")

    # Check for comma-separated values
    multi_resp = df[resp_col.notna()]["response_tweet_id"].astype(str)
    has_comma = multi_resp.str.contains(",").sum()
    print(f"  With multiple responses (comma-separated): {has_comma:,}")

    # in_response_to_tweet_id
    in_resp_col = df["in_response_to_tweet_id"]
    print(f"\nin_response_to_tweet_id analysis:")
    print(f"  Non-null: {in_resp_col.notna().sum():,}")
    print(f"  Null:     {in_resp_col.isna().sum():,}")

    # Check: tweets with null in_response_to should be roots
    root_tweets = df[in_resp_col.isna()]
    print(f"\nRoot tweets (no parent): {len(root_tweets):,}")
    print(f"  Inbound roots: {(root_tweets['inbound'] == True).sum():,}")
    print(f"  Outbound roots: {(root_tweets['inbound'] == False).sum():,}")

    # Check: do any in_response_to point to tweet_ids not in this sample?
    all_tids = set(df["tweet_id"].astype(str))
    in_resp_ids = set(in_resp_col.dropna().astype(int).astype(str))
    orphan_refs = in_resp_ids - all_tids
    print(f"\nOrphan references (parent tweet_id not in this 50k sample): {len(orphan_refs):,}")

    # ── 4. Noise detection ──────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("NOISE / QUALITY ISSUES")
    print("=" * 70)

    # Check for very short texts
    text_lengths = df["text"].astype(str).str.len()
    short_texts = (text_lengths < 10).sum()
    print(f"  Very short texts (<10 chars): {short_texts:,}")

    # Check for URL-only tweets
    url_pattern = df["text"].astype(str).str.match(r'^https?://\S+$')
    print(f"  URL-only tweets: {url_pattern.sum():,}")

    # Check for tweets that are just @mentions
    mention_only = df["text"].astype(str).str.match(r'^@\S+\s*$')
    print(f"  Mention-only tweets: {mention_only.sum():,}")

    # Check for masked content
    masked = df["text"].astype(str).str.contains("__email__|__url__", na=False)
    print(f"  Tweets with masked content (__email__ or __url__): {masked.sum():,}")

    # Save examples
    out_path = OUTPUT_DIR / "example_conversations.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(examples_output, f, indent=2, default=str)
    print(f"\nExamples saved to {out_path}")


if __name__ == "__main__":
    extract_examples()

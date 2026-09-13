"""
reconstruct_conversations.py — Reconstruct conversation threads from TWCS tweets.

The TWCS dataset links tweets via:
  - response_tweet_id:       IDs of tweets that respond TO this tweet (comma-separated)
  - in_response_to_tweet_id: ID of the tweet THIS tweet replies to

Strategy:
  1. Build a tweet lookup: tweet_id → tweet record
  2. Build a parent→children graph from in_response_to_tweet_id
  3. Identify conversation roots (tweets with no in_response_to_tweet_id)
  4. Walk the tree from each root to collect all tweets in a conversation
  5. Sort each conversation's tweets chronologically
  6. Attach metadata: conversation_id, message_count, customer/brand stats, etc.

Usage:
    py scripts/reconstruct_conversations.py [--brand BRAND_AUTHOR_ID] [--sample N]
"""

import sys, json, time, argparse
from pathlib import Path
from collections import defaultdict
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from src.data.data_utils import iter_chunks, get_raw_csv_path, CHUNK_SIZE

OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def parse_timestamp(ts_str):
    """Parse Twitter-style timestamp: 'Tue Oct 31 22:10:47 +0000 2017'"""
    if pd.isna(ts_str) or not isinstance(ts_str, str):
        return None
    try:
        return datetime.strptime(ts_str, "%a %b %d %H:%M:%S %z %Y")
    except (ValueError, TypeError):
        return None


def parse_response_ids(val):
    """
    Parse the response_tweet_id field, which can be:
      - NaN / empty
      - A single integer ID
      - Comma-separated IDs like '119290,119291'
    Returns a list of string IDs.
    """
    if pd.isna(val):
        return []
    s = str(val).strip()
    if not s:
        return []
    return [x.strip() for x in s.split(",") if x.strip()]


def build_tweet_index_and_graph(brand_filter=None):
    """
    Read the full CSV in chunks and build:
      - tweets: dict[tweet_id_str] → tweet record dict
      - children: dict[parent_id_str] → list[child_id_str]
      - roots: set of tweet_ids that have no parent (conversation starters)

    If brand_filter is provided, only include tweets where the author_id
    matches the brand OR where the tweet references the brand's tweets.
    (We need to include customer tweets too, so we do a two-pass approach
     if filtering by brand.)
    """
    tweets = {}
    children = defaultdict(list)
    roots = set()

    print("Pass 1: Building tweet index...")
    t0 = time.time()
    row_count = 0

    for chunk in iter_chunks():
        for _, row in chunk.iterrows():
            tid = str(row["tweet_id"]).strip()
            parent_id = (
                str(row["in_response_to_tweet_id"]).strip()
                if pd.notna(row["in_response_to_tweet_id"])
                else None
            )
            # Normalize 'nan' strings
            if parent_id in ("nan", "", "None"):
                parent_id = None

            record = {
                "tweet_id": tid,
                "author_id": str(row["author_id"]).strip() if pd.notna(row["author_id"]) else "",
                "inbound": row["inbound"],
                "created_at": str(row["created_at"]) if pd.notna(row["created_at"]) else "",
                "text": str(row["text"]) if pd.notna(row["text"]) else "",
                "response_tweet_id": parse_response_ids(row.get("response_tweet_id")),
                "in_response_to_tweet_id": parent_id,
            }

            tweets[tid] = record

            if parent_id:
                children[parent_id].append(tid)
            else:
                roots.add(tid)

            row_count += 1

        if row_count % 500_000 < CHUNK_SIZE:
            print(f"  ... indexed {row_count:,} tweets ({time.time()-t0:.1f}s)")

    elapsed = time.time() - t0
    print(f"  Indexed {row_count:,} tweets in {elapsed:.1f}s")
    print(f"  Roots (no parent): {len(roots):,}")
    print(f"  Tweets with children: {len(children):,}")

    return tweets, children, roots


def walk_thread(root_id, tweets, children):
    """
    BFS/DFS walk from a root tweet to collect all tweets in the conversation.
    Returns a list of tweet records, sorted by timestamp.
    """
    thread = []
    visited = set()
    queue = [root_id]

    while queue:
        tid = queue.pop(0)
        if tid in visited:
            continue
        visited.add(tid)

        if tid in tweets:
            thread.append(tweets[tid])

        # Add children
        for child_id in children.get(tid, []):
            if child_id not in visited:
                queue.append(child_id)

    # Sort by timestamp
    def sort_key(t):
        dt = parse_timestamp(t["created_at"])
        return dt if dt else datetime.min.replace(tzinfo=None)

    # Handle timezone-aware vs naive
    try:
        thread.sort(key=lambda t: parse_timestamp(t["created_at"]) or datetime.min)
    except TypeError:
        # Mix of aware/naive — use string sort as fallback
        thread.sort(key=lambda t: t["created_at"])

    return thread


def build_conversation_record(thread, conv_id):
    """
    Build a structured conversation record from a list of tweet records.
    """
    customer_messages = []
    brand_messages = []
    authors = set()

    for msg in thread:
        authors.add(msg["author_id"])
        inbound = msg["inbound"]
        # Handle string 'True'/'False' vs bool
        if isinstance(inbound, str):
            is_inbound = inbound.lower() == "true"
        else:
            is_inbound = bool(inbound)

        if is_inbound:
            customer_messages.append(msg)
        else:
            brand_messages.append(msg)

    brand_author_ids = set()
    customer_author_ids = set()
    for msg in brand_messages:
        brand_author_ids.add(msg["author_id"])
    for msg in customer_messages:
        customer_author_ids.add(msg["author_id"])

    start_time = thread[0]["created_at"] if thread else ""
    end_time = thread[-1]["created_at"] if thread else ""

    return {
        "conversation_id": conv_id,
        "message_count": len(thread),
        "customer_message_count": len(customer_messages),
        "brand_message_count": len(brand_messages),
        "has_customer_message": len(customer_messages) > 0,
        "has_brand_response": len(brand_messages) > 0,
        "brand_author_ids": list(brand_author_ids),
        "customer_author_ids": list(customer_author_ids),
        "all_author_ids": list(authors),
        "start_time": start_time,
        "end_time": end_time,
        "messages": thread,
    }


def reconstruct_all(brand_filter=None, sample_n=None):
    """
    Main entry: build tweet index, walk all roots, produce conversation records.

    Parameters
    ----------
    brand_filter : str, optional
        If given, only keep conversations where this author_id appears as
        a brand (outbound) participant.
    sample_n : int, optional
        If given, only reconstruct this many conversations (for quick testing).
    """
    tweets, children, roots = build_tweet_index_and_graph()

    print(f"\nReconstructing conversations from {len(roots):,} roots...")
    t0 = time.time()

    conversations = []
    skipped = 0

    for i, root_id in enumerate(roots):
        thread = walk_thread(root_id, tweets, children)

        if len(thread) == 0:
            skipped += 1
            continue

        conv_id = f"conv_{root_id}"
        conv = build_conversation_record(thread, conv_id)

        # Brand filter: skip if the brand is not a participant
        if brand_filter:
            if brand_filter not in conv["brand_author_ids"]:
                continue

        conversations.append(conv)

        if sample_n and len(conversations) >= sample_n:
            print(f"  Stopped at sample limit of {sample_n}")
            break

        if (i + 1) % 100_000 == 0:
            print(f"  ... processed {i+1:,} roots, "
                  f"{len(conversations):,} conversations ({time.time()-t0:.1f}s)")

    elapsed = time.time() - t0
    print(f"\nDone: {len(conversations):,} conversations "
          f"from {len(roots):,} roots ({elapsed:.1f}s)")
    print(f"Skipped (empty threads): {skipped:,}")

    return conversations


def compute_conversation_stats(conversations):
    """Compute summary statistics over the conversation list."""
    total = len(conversations)
    if total == 0:
        return {}

    msg_counts = [c["message_count"] for c in conversations]
    cust_counts = [c["customer_message_count"] for c in conversations]
    brand_counts = [c["brand_message_count"] for c in conversations]

    has_both = sum(
        1 for c in conversations
        if c["has_customer_message"] and c["has_brand_response"]
    )
    customer_only = sum(
        1 for c in conversations
        if c["has_customer_message"] and not c["has_brand_response"]
    )
    brand_only = sum(
        1 for c in conversations
        if not c["has_customer_message"] and c["has_brand_response"]
    )
    single_msg = sum(1 for c in conversations if c["message_count"] == 1)
    multi_turn = sum(1 for c in conversations if c["message_count"] >= 3)

    # Brand distribution
    brand_conv_counts = defaultdict(int)
    for c in conversations:
        for bid in c["brand_author_ids"]:
            brand_conv_counts[bid] += 1

    import statistics

    stats = {
        "total_conversations": total,
        "has_customer_and_brand": has_both,
        "customer_only": customer_only,
        "brand_only": brand_only,
        "single_message": single_msg,
        "multi_turn_3plus": multi_turn,
        "message_count_mean": round(statistics.mean(msg_counts), 2),
        "message_count_median": statistics.median(msg_counts),
        "message_count_max": max(msg_counts),
        "customer_msg_mean": round(statistics.mean(cust_counts), 2),
        "brand_msg_mean": round(statistics.mean(brand_counts), 2),
        "brand_conversation_counts": dict(
            sorted(brand_conv_counts.items(), key=lambda x: -x[1])[:30]
        ),
    }
    return stats


def save_conversations(conversations, filename="conversations.json"):
    """Save conversations to JSON."""
    out_path = OUTPUT_DIR / filename
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(conversations, f, indent=2, default=str)
    print(f"Saved {len(conversations)} conversations to {out_path}")
    return out_path


def save_conversation_stats(stats, filename="conversation_stats.json"):
    """Save conversation statistics to JSON."""
    out_path = OUTPUT_DIR / filename
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, default=str)
    print(f"Saved stats to {out_path}")
    return out_path


# ── CLI ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Reconstruct conversation threads from TWCS dataset."
    )
    parser.add_argument(
        "--brand", type=str, default=None,
        help="Filter to conversations involving this brand author_id."
    )
    parser.add_argument(
        "--sample", type=int, default=None,
        help="Only reconstruct this many conversations (for quick testing)."
    )
    args = parser.parse_args()

    conversations = reconstruct_all(
        brand_filter=args.brand, sample_n=args.sample
    )

    stats = compute_conversation_stats(conversations)

    # Print stats
    print("\n" + "=" * 70)
    print("CONVERSATION STATISTICS")
    print("=" * 70)
    for k, v in stats.items():
        if k == "brand_conversation_counts":
            print(f"\n  Top brands by conversation count:")
            for bid, cnt in list(v.items())[:15]:
                print(f"    {bid:25s}  {cnt:>8,}")
        else:
            print(f"  {k:35s}  {v}")

    # Save
    if args.brand:
        suffix = f"_{args.brand}"
    elif args.sample:
        suffix = f"_sample{args.sample}"
    else:
        suffix = ""

    save_conversations(conversations, f"conversations{suffix}.json")
    save_conversation_stats(stats, f"conversation_stats{suffix}.json")

    # Print example conversations
    print("\n" + "=" * 70)
    print("EXAMPLE CONVERSATIONS")
    print("=" * 70)
    examples = [c for c in conversations if c["message_count"] >= 3][:5]
    for conv in examples:
        print(f"\n--- {conv['conversation_id']} "
              f"({conv['message_count']} messages) ---")
        for msg in conv["messages"]:
            direction = "CUSTOMER" if msg.get("inbound") in (True, "True") else "BRAND  "
            text_preview = msg["text"][:120].replace("\n", " ")
            print(f"  [{direction}] @{msg['author_id']}: {text_preview}")

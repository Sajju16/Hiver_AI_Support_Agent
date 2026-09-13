"""
scripts/check_b2_structure.py — Check B2 structure in golden_candidates_200.json
"""

import json
from pathlib import Path
from collections import Counter

GOLDEN_PATH = Path("data/golden/golden_candidates_200.json")

PAIRS = [
    "Delivery vs Refund",
    "Refund vs Return",
    "Delivery vs Marked Delivered Not Received",
    "Damaged vs Return",
    "Delivery vs Return",
    "Refund vs Cancellation",
    "Technical vs Prime"
]

def main():
    with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
        golden = json.load(f)

    b2_candidates = [c for c in golden if c.get("candidate_bucket") == "B2_confusing"]
    print(f"Total B2 candidates found in golden_candidates_200.json: {len(b2_candidates)}\n")

    pair_counts = Counter()
    unassigned = []

    for c in b2_candidates:
        hint = c.get("candidate_intent_hint", "")
        found_pair = None
        for pair in PAIRS:
            if pair.lower() in hint.lower():
                found_pair = pair
                break
        if found_pair:
            pair_counts[found_pair] += 1
        else:
            unassigned.append(c)

    print("==================================================")
    print("B2 CONFUSING PAIR COUNTS TABLE")
    print("==================================================")
    print(f"{'pair':<42} | {'count':<5}")
    print("-" * 50)
    for pair in PAIRS:
        print(f"{pair:<42} | {pair_counts[pair]:<5}")

    print("\n==================================================")
    print(f"UNASSIGNED / UNCLEAN B2 CANDIDATES ({len(unassigned)})")
    print("==================================================")
    for c in unassigned:
        print(f"example_id: {c['example_id']} | hint: {c['candidate_intent_hint']}")

    all_have_5 = all(pair_counts[pair] == 5 for pair in PAIRS)
    print(f"\nAll seven pairs have exactly 5 candidates: {all_have_5}")

if __name__ == "__main__":
    main()

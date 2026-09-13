"""
scripts/investigate_overlap_bug.py — Investigate overlap check defect
"""

import sys, json
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_PATH = PROJECT_ROOT / "data" / "golden" / "golden_candidates_200.json"
DEV_PATH = PROJECT_ROOT / "data" / "dev" / "dev_candidates_50.json"

def main():
    print("Loading CURRENT files...", flush=True)
    with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
        golden = json.load(f)
    with open(DEV_PATH, "r", encoding="utf-8") as f:
        dev = json.load(f)

    print(f"Golden Path: {GOLDEN_PATH}")
    print(f"Dev Path: {DEV_PATH}\n")

    golden_keys = [(c["conversation_id"], c["turn_index"]) for c in golden]
    dev_keys = [(c["conversation_id"], c["turn_index"]) for c in dev]

    golden_convos = set(c["conversation_id"] for c in golden)
    dev_convos = set(c["conversation_id"] for c in dev)

    # Check duplicates within Golden
    golden_key_counts = Counter(golden_keys)
    golden_dups = {k: v for k, v in golden_key_counts.items() if v > 1}

    # Check duplicates within Dev
    dev_key_counts = Counter(dev_keys)
    dev_dups = {k: v for k, v in dev_key_counts.items() if v > 1}

    # Golden vs Dev overlap
    key_overlap = set(golden_keys).intersection(set(dev_keys))
    convo_overlap = golden_convos.intersection(dev_convos)

    print("==================================================")
    print("DIRECT MECHANICAL CHECK RESULTS")
    print("==================================================")
    print(f"Golden count: {len(golden)}")
    print(f"Unique Golden keys (conversation_id, turn_index): {len(set(golden_keys))}")
    print(f"Unique Golden conversation_ids: {len(golden_convos)}")
    print(f"Dev count: {len(dev)}")
    print(f"Unique Dev keys (conversation_id, turn_index): {len(set(dev_keys))}")
    print(f"Unique Dev conversation_ids: {len(dev_convos)}")
    print(f"Golden AND Dev KEY overlap count: {len(key_overlap)}")
    print(f"Golden AND Dev CONVERSATION overlap count: {len(convo_overlap)}")
    print(f"Duplicate keys within Golden: {len(golden_dups)} ({golden_dups})")
    print(f"Duplicate keys within Dev: {len(dev_dups)} ({dev_dups})")

    # Check GOLDEN_172 / 13905_AmazonHelp specifically
    golden_172_record = [c for c in golden if c.get("example_id") == "GOLDEN_172"]
    convo_13905_records = [c for c in golden if c.get("conversation_id") == "13905_AmazonHelp"]

    print("\n==================================================")
    print("GOLDEN_172 / 13905_AmazonHelp SPECIFIC CHECK")
    print("==================================================")
    if golden_172_record:
        print(f"GOLDEN_172 record found:")
        print(f"  example_id: {golden_172_record[0]['example_id']}")
        print(f"  conversation_id: {golden_172_record[0]['conversation_id']}")
        print(f"  turn_index: {golden_172_record[0]['turn_index']}")
        print(f"  raw_text: {golden_172_record[0]['raw_text']}")
    else:
        print("GOLDEN_172 record NOT found in Golden file!")

    print(f"\nTotal records in Golden with conversation_id '13905_AmazonHelp': {len(convo_13905_records)}")
    for r in convo_13905_records:
        print(f"  example_id: {r['example_id']} | turn_index: {r['turn_index']} | text snippet: {r['raw_text'][:60]}")

if __name__ == "__main__":
    main()

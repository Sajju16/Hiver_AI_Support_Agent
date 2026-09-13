"""
scripts/execute_golden_rebalance.py — Execute final Golden Set rebalance and seal file

Rebalances Golden Set from (B1=105, B2=30, B3=25, B4=20, B5=20) to (B1=100, B2=35, B3=25, B4=20, B5=20).
Adds 5 approved B2 candidates for Delivery vs Marked Delivered Not Received stratum.
Removes 5 General candidate B1 records to achieve exactly 10 B1 records per core intent.
"""

import sys, json, hashlib, csv
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_PATH = PROJECT_ROOT / "data" / "golden" / "golden_candidates_200.json"
CHECKSUM_PATH = PROJECT_ROOT / "data" / "golden" / "golden_candidates_200.json.sha256"
DEV_PATH = PROJECT_ROOT / "data" / "dev" / "dev_candidates_50.json"
DECISION_LOG_PATH = PROJECT_ROOT / "DECISION_LOG.md"
CSV_PATH = PROJECT_ROOT / "archive" / "twcs" / "twcs.csv"

def verify_checksum(path, expected_checksum_path):
    with open(expected_checksum_path, "r", encoding="utf-8") as f:
        stored_hash = f.read().strip().split()[0].lower()
    with open(path, "rb") as f:
        computed_hash = hashlib.sha256(f.read()).hexdigest().lower()
    assert computed_hash == stored_hash, f"Checksum Mismatch! Computed: {computed_hash}, Stored: {stored_hash}"
    return computed_hash

def main():
    print("Step 1: Pre-flight checksum verification...", flush=True)
    old_checksum = verify_checksum(GOLDEN_PATH, CHECKSUM_PATH)
    print(f"OLD CHECKSUM VERIFIED: {old_checksum}")

    print("Step 2: Loading Golden Set and Dev Set...", flush=True)
    with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
        golden = json.load(f)
    with open(DEV_PATH, "r", encoding="utf-8") as f:
        dev = json.load(f)

    # Step 3 & 4: Inspect B1 candidates before removal
    b1_records = [r for r in golden if r["candidate_bucket"] == "B1_core"]
    b1_intent_counts_before = Counter(r["candidate_intent_hint"] for r in b1_records)

    # Target 5 B1 records for removal ("General candidate")
    removed_records = [r for r in golden if r["candidate_bucket"] == "B1_core" and r["candidate_intent_hint"] == "General candidate"]
    assert len(removed_records) == 5, f"Expected 5 General candidate B1 records, found {len(removed_records)}"

    # Keep all records except the 5 removed General candidates
    removed_eids = set(r["example_id"] for r in removed_records)
    new_golden = [r for r in golden if r["example_id"] not in removed_eids]
    assert len(new_golden) == 195, f"Expected 195 records after removal, got {len(new_golden)}"

    # Step 5: Build approved B2 candidate records from TWCS
    tweet_author = {}
    tweet_inbound = {}
    tweet_text = {}
    tweet_parent = {}

    print("Reading TWCS CSV to build exact context for 5 approved B2 candidates...", flush=True)
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tid = row["tweet_id"].strip()
            tweet_author[tid] = row["author_id"].strip()
            tweet_inbound[tid] = (row["inbound"].strip().upper() == "TRUE")
            tweet_text[tid] = row["text"]
            p = row["in_response_to_tweet_id"].strip()
            if p and p.lower() not in ("nan", "none", "<na>", ""):
                if p.endswith(".0"):
                    p = p[:-2]
                tweet_parent[tid] = p

    approved_cids = [
        ("646_AmazonHelp", 0),
        ("17183_AmazonHelp", 0),
        ("22557_AmazonHelp", 0),
        ("10321_AmazonHelp", 0),
        ("617_AmazonHelp", 1)
    ]

    new_b2_records = []
    for cid, target_turn in approved_cids:
        root_tid = cid.split("_")[0]
        # Find candidate matching target_turn
        for tid in tweet_author:
            ancestors = []
            curr_parent = tweet_parent.get(tid)
            visited = set()
            while curr_parent and curr_parent in tweet_author and curr_parent not in visited:
                visited.add(curr_parent)
                ancestors.append({
                    "author": tweet_author[curr_parent],
                    "text": tweet_text[curr_parent],
                    "is_customer": tweet_inbound.get(curr_parent, True),
                    "tweet_id": curr_parent
                })
                curr_parent = tweet_parent.get(curr_parent)
            ancestors.reverse()
            r_id = ancestors[0]["tweet_id"] if ancestors else tid
            calc_cid = f"{r_id}_AmazonHelp"
            if calc_cid == cid and tweet_inbound.get(tid, True):
                t_idx = len([m for m in ancestors if m["is_customer"]])
                if t_idx == target_turn:
                    new_b2_records.append({
                        "example_id": "", # Will re-index sequentially
                        "conversation_id": cid,
                        "turn_index": t_idx,
                        "raw_text": tweet_text[tid],
                        "thread_context": [
                            {"author": m["author"], "text": m["text"], "is_customer": m["is_customer"]}
                            for m in ancestors
                        ],
                        "candidate_bucket": "B2_confusing",
                        "candidate_intent_hint": "Delivery_Tracking_And_Delays vs Marked_Delivered_Not_Received",
                        "primary_intent": None,
                        "secondary_intent": None,
                        "escalate": None,
                        "escalate_reason": None,
                        "language_flag": None,
                        "ambiguity_flag": None,
                        "annotator_notes": None
                    })
                    break

    assert len(new_b2_records) == 5, f"Expected 5 new B2 records, built {len(new_b2_records)}"

    # Append new B2 records and re-index example_ids cleanly as GOLDEN_001 .. GOLDEN_200
    final_golden = new_golden + new_b2_records
    for i, rec in enumerate(final_golden):
        rec["example_id"] = f"GOLDEN_{i+1:03d}"

    print(f"Step 6: Writing updated Golden Set ({len(final_golden)} records) to disk...", flush=True)
    with open(GOLDEN_PATH, "w", encoding="utf-8") as f:
        json.dump(final_golden, f, indent=2, ensure_ascii=False)

    print("\n" + "="*80)
    print("RUNNING MECHANICAL VALIDATIONS (A THROUGH H)")
    print("="*80)

    # A. Total count == 200
    assert len(final_golden) == 200, f"Validation A Failed: Total count {len(final_golden)} != 200"
    print("VALIDATION A PASSED: Total count == 200")

    # B. Bucket counts
    bucket_counts = Counter(r["candidate_bucket"] for r in final_golden)
    assert bucket_counts["B1_core"] == 100, f"Validation B Failed: B1={bucket_counts['B1_core']}"
    assert bucket_counts["B2_confusing"] == 35, f"Validation B Failed: B2={bucket_counts['B2_confusing']}"
    assert bucket_counts["B3_escalation"] == 25, f"Validation B Failed: B3={bucket_counts['B3_escalation']}"
    assert bucket_counts["B4_non_english"] == 20, f"Validation B Failed: B4={bucket_counts['B4_non_english']}"
    assert bucket_counts["B5_other"] == 20, f"Validation B Failed: B5={bucket_counts['B5_other']}"
    print(f"VALIDATION B PASSED: Bucket counts == {dict(bucket_counts)}")

    # C. B1 per-intent counts == 10 each
    b1_final = [r for r in final_golden if r["candidate_bucket"] == "B1_core"]
    b1_final_counts = Counter(r["candidate_intent_hint"] for r in b1_final)
    assert len(b1_final_counts) == 10, f"Validation C Failed: Intent count types = {len(b1_final_counts)}"
    for intent, count in b1_final_counts.items():
        assert count == 10, f"Validation C Failed: {intent} count = {count} != 10"
    print("VALIDATION C PASSED: Each of 10 core B1 intents == exactly 10")

    # D. B2 pair counts == 5 each for 7 pairs
    b2_final = [r for r in final_golden if r["candidate_bucket"] == "B2_confusing"]
    b2_pair_counts = Counter(r["candidate_intent_hint"] for r in b2_final)
    assert len(b2_pair_counts) == 7, f"Validation D Failed: B2 pair count types = {len(b2_pair_counts)}"
    for pair, count in b2_pair_counts.items():
        assert count == 5, f"Validation D Failed: Pair {pair} count = {count} != 5"
    print("VALIDATION D PASSED: All 7 B2 confusing pairs == exactly 5 each")

    # E. Golden internal uniqueness
    keys = [(r["conversation_id"], r["turn_index"]) for r in final_golden]
    convos = [r["conversation_id"] for r in final_golden]
    eids = [r["example_id"] for r in final_golden]

    assert len(set(keys)) == 200, f"Validation E Failed: {len(set(keys))} unique keys"
    assert len(set(convos)) == 200, f"Validation E Failed: {len(set(convos))} unique convos"
    assert len(set(eids)) == 200, f"Validation E Failed: {len(set(eids))} unique eids"
    print("VALIDATION E PASSED: Unique keys=200, Unique convos=200, Duplicate eids=0")

    # F. Golden/Dev overlap
    dev_convos = set(r["conversation_id"] for r in dev)
    dev_keys = set((r["conversation_id"], r["turn_index"]) for r in dev)

    convo_overlap = set(convos).intersection(dev_convos)
    key_overlap = set(keys).intersection(dev_keys)

    assert len(convo_overlap) == 0, f"Validation F Failed: convo overlap = {len(convo_overlap)}"
    assert len(key_overlap) == 0, f"Validation F Failed: key overlap = {len(key_overlap)}"
    print("VALIDATION F PASSED: Golden/Dev convo overlap=0, key overlap=0")

    # G. Annotation fields null
    gt_fields = ["primary_intent", "secondary_intent", "escalate", "escalate_reason", "language_flag", "ambiguity_flag", "annotator_notes"]
    for r in final_golden:
        for fld in gt_fields:
            assert r[fld] is None, f"Validation G Failed: {r['example_id']} {fld} is not None"
    print("VALIDATION G PASSED: All 7 ground truth annotation fields are null across all 200 records")

    # H. Confirm all 5 approved B2 candidates present
    added_cids = {"646_AmazonHelp", "17183_AmazonHelp", "22557_AmazonHelp", "10321_AmazonHelp", "617_AmazonHelp"}
    present_cids = set(r["conversation_id"] for r in final_golden)
    missing = added_cids - present_cids
    assert len(missing) == 0, f"Validation H Failed: missing candidates {missing}"
    print("VALIDATION H PASSED: All 5 approved B2 candidates are verified present in Golden Set")

    # Step 8: Recompute SHA-256 for FINAL Golden file and overwrite checksum file
    with open(GOLDEN_PATH, "rb") as f:
        new_checksum = hashlib.sha256(f.read()).hexdigest().lower()

    with open(CHECKSUM_PATH, "w", encoding="utf-8") as f:
        f.write(f"{new_checksum}  golden_candidates_200.json\n")
    print(f"Step 8 Complete: Overwrote {CHECKSUM_PATH.name} with new checksum: {new_checksum}")

    # Step 9: Re-verify checksum match immediately
    reverified_checksum = verify_checksum(GOLDEN_PATH, CHECKSUM_PATH)
    print(f"Step 9 Complete: RE-VERIFIED SHA256 MATCH: {reverified_checksum}")

    # Step 10: Update Decision Log
    entries = [
        "- **[2026-09-12] Candidate Selection Pre-Flight Checksum Guard**: A transient discrepancy appeared between a candidate-review table and the actual golden file state during B2 rebalancing, traced to a likely stale intermediate artifact; underlying files were verified uncorrupted; a SHA-256 pre-flight check was added to candidate-generation scripts to prevent recurrence.\n",
        "- **[2026-09-12] B2 Confusing Pair Coverage Resolution**: B2 confusing-pair coverage was found missing Delivery-vs-MarkedDeliveredNotReceived coverage (0/5); five manually verified status-contradiction examples were added and B1 was deliberately rebalanced to restore the specified 100/35/25/20/20 composition.\n",
        "- **[2026-09-12] Final Golden Set Rebalance & Sealing**: Final Golden Set composition was sealed at 100 B1 / 35 B2 / 25 B3 / 20 B4 / 20 B5 = 200 examples, with exactly 10 B1 examples per core intent and exactly 5 examples for each of the 7 B2 confusing pairs.\n"
    ]
    with open(DECISION_LOG_PATH, "a", encoding="utf-8") as f:
        for entry in entries:
            f.write(entry)
    print("Step 10 Complete: Decision Log updated with mandatory freeze entries.")

    print("\nREBALANCE EXECUTION SUCCESSFUL!")

if __name__ == "__main__":
    main()

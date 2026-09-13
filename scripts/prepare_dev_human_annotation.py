"""
scripts/prepare_dev_human_annotation.py — Separate automated prelabels and prepare clean human-labeling queue

1. Saves current auto-labeled Dev set to data/dev/dev_prelabels_50.json (archival prelabels).
2. Creates data/dev/dev_human_labels_50.json and resets data/dev/dev_candidates_50.json with all 7 ground-truth annotation fields set to null.
3. Appends mandatory decision-log entry.
4. Verifies Golden set remains sealed and untouched.
"""

import sys, json, hashlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEV_PATH = PROJECT_ROOT / "data" / "dev" / "dev_candidates_50.json"
DEV_PRELABELS_PATH = PROJECT_ROOT / "data" / "dev" / "dev_prelabels_50.json"
DEV_HUMAN_PATH = PROJECT_ROOT / "data" / "dev" / "dev_human_labels_50.json"
GOLDEN_PATH = PROJECT_ROOT / "data" / "golden" / "golden_candidates_200.json"
GOLDEN_CHECKSUM_PATH = PROJECT_ROOT / "data" / "golden" / "golden_candidates_200.json.sha256"
DECISION_LOG_PATH = PROJECT_ROOT / "DECISION_LOG.md"

EXPECTED_GOLDEN_SHA256 = "57682c611278ede6a89cadb5c7b1887498049689d2520952865a361c5a59adda"

def main():
    print("Loading current Dev candidates...", flush=True)
    with open(DEV_PATH, "r", encoding="utf-8") as f:
        dev_data = json.load(f)

    assert len(dev_data) == 50, f"Expected 50 records, got {len(dev_data)}"

    # 1. Save archival prelabels artifact
    print(f"Saving archival prelabels to {DEV_PRELABELS_PATH}...", flush=True)
    with open(DEV_PRELABELS_PATH, "w", encoding="utf-8") as f:
        json.dump(dev_data, f, indent=2, ensure_ascii=False)

    # 2. Reset ground-truth annotation fields to null for human labeling queue
    human_dev_data = []
    gt_fields = ["primary_intent", "secondary_intent", "escalate", "escalate_reason", "language_flag", "ambiguity_flag", "annotator_notes"]

    for rec in dev_data:
        clean_rec = {
            "example_id": rec["example_id"],
            "conversation_id": rec["conversation_id"],
            "turn_index": rec["turn_index"],
            "raw_text": rec["raw_text"],
            "thread_context": rec["thread_context"],
            "candidate_bucket": rec["candidate_bucket"],
            "candidate_intent_hint": rec.get("candidate_intent_hint")
        }
        for fld in gt_fields:
            clean_rec[fld] = None
        human_dev_data.append(clean_rec)

    print(f"Writing clean human-labeling queue to {DEV_HUMAN_PATH}...", flush=True)
    with open(DEV_HUMAN_PATH, "w", encoding="utf-8") as f:
        json.dump(human_dev_data, f, indent=2, ensure_ascii=False)

    print(f"Resetting {DEV_PATH} to clean human-labeling queue state...", flush=True)
    with open(DEV_PATH, "w", encoding="utf-8") as f:
        json.dump(human_dev_data, f, indent=2, ensure_ascii=False)

    # 3. Add Decision Log Entry
    entry = "- **[2026-09-12] Dev Annotation Pass Re-classification**: The first Dev annotation pass was identified as automated pre-labeling rather than genuine human annotation. The generated labels were preserved as prelabels for later comparison, but were removed from the ground-truth workflow. Dev and Golden ground truth will be assigned through explicit human review to maintain independence from automated heuristics.\n"

    with open(DECISION_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(entry)
    print("Updated DECISION_LOG.md with re-classification entry.")

    # 4. Run Verification Checks
    print("\n" + "="*80)
    print("RUNNING VERIFICATION CHECKS")
    print("="*80)

    with open(DEV_PRELABELS_PATH, "r", encoding="utf-8") as f:
        prelabel_records = json.load(f)
    with open(DEV_HUMAN_PATH, "r", encoding="utf-8") as f:
        human_records = json.load(f)

    assert len(prelabel_records) == 50, f"Prelabel count {len(prelabel_records)} != 50"
    assert len(human_records) == 50, f"Human queue count {len(human_records)} != 50"
    print("VERIFICATION 1 PASSED: Both prelabel and human files contain exactly 50 examples.")

    prelabel_eids = [r["example_id"] for r in prelabel_records]
    human_eids = [r["example_id"] for r in human_records]
    assert prelabel_eids == human_eids, "Example ID mismatch between prelabels and human queue!"
    print("VERIFICATION 2 PASSED: Identical example_ids in both files.")

    for r in human_records:
        for fld in gt_fields:
            assert r[fld] is None, f"{r['example_id']} field {fld} is not null!"
    print("VALIDATION 3 PASSED: All 7 ground-truth annotation fields in human-labeling queue are null.")

    with open(GOLDEN_PATH, "rb") as f:
        current_golden_hash = hashlib.sha256(f.read()).hexdigest().lower()
    assert current_golden_hash == EXPECTED_GOLDEN_SHA256, f"GOLDEN CHECKSUM MISMATCH! Current: {current_golden_hash}, Expected: {EXPECTED_GOLDEN_SHA256}"
    print(f"VERIFICATION 4 PASSED: Golden file UNTOUCHED. Verified SHA256: {current_golden_hash}")

    print("\nPREPARATION COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    main()

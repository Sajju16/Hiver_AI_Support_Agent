"""
scripts/create_golden_150_subset.py

Creates the official 150-example stratified subset from the frozen 200 Golden candidate pool
and initializes the clean human review workspace (data/golden/golden_human_review_150.json).

Target Allocation:
- B1_core: 75
- B2_confusing: 25
- B3_escalation: 20
- B4_non_english: 15
- B5_other: 15
Total = 150 examples.
"""

import sys, os, json, random, hashlib
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

GOLDEN_200_PATH = PROJECT_ROOT / "data" / "golden" / "golden_candidates_200.json"
EXPECTED_GOLDEN_SHA256 = "57682c611278ede6a89cadb5c7b1887498049689d2520952865a361c5a59adda"
EVIDENCE_200_PATH = PROJECT_ROOT / "data" / "golden" / "golden_ai_assisted_evidence_200.json"

OFFICIAL_150_PATH = PROJECT_ROOT / "data" / "golden" / "golden_official_candidates_150.json"
REVIEW_150_PATH = PROJECT_ROOT / "data" / "golden" / "golden_human_review_150.json"
FINAL_150_PATH = PROJECT_ROOT / "data" / "golden" / "golden_human_verified_150.json"
HASH_150_PATH = PROJECT_ROOT / "data" / "golden" / "golden_human_verified_150.sha256"
SAMPLING_DOC_PATH = PROJECT_ROOT / "data" / "golden" / "GOLDEN_150_SAMPLING.md"

SEED = 2026

BUCKET_TARGETS = {
    "B1_core": 75,
    "B2_confusing": 25,
    "B3_escalation": 20,
    "B4_non_english": 15,
    "B5_other": 15
}

def verify_200_checksum():
    if not GOLDEN_200_PATH.exists():
        raise FileNotFoundError(f"Missing frozen 200 candidate file: {GOLDEN_200_PATH}")
    with open(GOLDEN_200_PATH, "rb") as f:
        content_hash = hashlib.sha256(f.read()).hexdigest().lower()
    assert content_hash == EXPECTED_GOLDEN_SHA256, f"Checksum mismatch! Got {content_hash}, expected {EXPECTED_GOLDEN_SHA256}"
    return content_hash

def reset_150_workspace():
    pre_hash = verify_200_checksum()
    print(f"[VERIFIED] Pre-execution 200 candidate checksum: {pre_hash}")

    with open(GOLDEN_200_PATH, "r", encoding="utf-8") as f:
        candidates_200 = json.load(f)

    # Load AI evidence map
    evidence_map = {}
    if EVIDENCE_200_PATH.exists():
        with open(EVIDENCE_200_PATH, "r", encoding="utf-8") as f:
            evidence_list = json.load(f)
        for ev in evidence_list:
            key = (ev.get("conversation_id"), ev.get("turn_index"))
            evidence_map[key] = ev

    # Group by bucket
    buckets = {}
    for item in candidates_200:
        b = item.get("candidate_bucket", "B1_core")
        buckets.setdefault(b, []).append(item)

    selected_150 = []

    # Stratified deterministic selection with fixed seed
    rng = random.Random(SEED)
    for bucket_name, target_count in BUCKET_TARGETS.items():
        items = buckets.get(bucket_name, [])
        sorted_items = sorted(items, key=lambda x: (x.get("conversation_id", ""), x.get("turn_index", 0)))
        shuffled = list(sorted_items)
        rng.shuffle(shuffled)
        picked = shuffled[:target_count]
        selected_150.extend(picked)

    order_map = {(c["conversation_id"], c["turn_index"]): idx for idx, c in enumerate(candidates_200)}
    selected_150.sort(key=lambda x: order_map[(x["conversation_id"], x["turn_index"])])

    official_records = []
    review_records = []

    for idx, item in enumerate(selected_150):
        ex_id = f"GOLDEN_150_{idx+1:03d}"
        key = (item["conversation_id"], item["turn_index"])
        ev = evidence_map.get(key, {})

        off_item = dict(item)
        off_item["example_id"] = ex_id
        off_item["official_golden"] = True
        off_item["annotation_source"] = "PENDING_HUMAN_VERIFICATION"
        official_records.append(off_item)

        rev_item = {
            "example_id": ex_id,
            "conversation_id": item["conversation_id"],
            "turn_index": item["turn_index"],
            "raw_text": item["raw_text"],
            "thread_context": item.get("thread_context", []),
            "candidate_bucket": item.get("candidate_bucket", "B1_core"),
            "candidate_intent_hint": item.get("candidate_intent_hint", ""),
            
            # AI assistance fields (suggestions only)
            "ai_suggested_intent": ev.get("predicted_intent", "Delivery_Tracking_And_Delays"),
            "classifier_intent": ev.get("classifier_prediction", {}).get("predicted_intent", "Delivery_Tracking_And_Delays"),
            "nn_intent": ev.get("top_3_reference_human_intents", ["Delivery_Tracking_And_Delays"])[0] if ev.get("top_3_reference_human_intents") else "Delivery_Tracking_And_Delays",
            "retrieval_intent": ev.get("retrieval_prediction", {}).get("predicted_intent", "Delivery_Tracking_And_Delays"),
            "ai_escalate": ev.get("escalate", False),
            "ai_escalate_reason": ev.get("escalation_reason", ""),
            "language_flag": ev.get("language_flag", False),
            "confidence": ev.get("confidence_status", "LOW_CONFIDENCE"),

            # Ground truth fields (strictly null until human action)
            "primary_intent": None,
            "secondary_intent": None,
            "escalate": None,
            "escalate_reason": None,
            "ambiguity_flag": None,
            "annotator_notes": "",
            "annotation_source": "PENDING_HUMAN_VERIFICATION",
            "human_verified": False
        }
        review_records.append(rev_item)

    with open(OFFICIAL_150_PATH, "w", encoding="utf-8") as f:
        json.dump(official_records, f, indent=2, ensure_ascii=False)
    print(f"[SAVED] Official candidates saved to {OFFICIAL_150_PATH}")

    with open(REVIEW_150_PATH, "w", encoding="utf-8") as f:
        json.dump(review_records, f, indent=2, ensure_ascii=False)
    print(f"[RESET] Human review workspace reset cleanly to 0/150 verified at {REVIEW_150_PATH}")

    # Remove stale verified files until human verification occurs
    if FINAL_150_PATH.exists():
        FINAL_150_PATH.unlink()
    if HASH_150_PATH.exists():
        HASH_150_PATH.unlink()

    post_hash = verify_200_checksum()
    assert post_hash == EXPECTED_GOLDEN_SHA256, "Checksum mismatch after script execution!"
    print(f"[VERIFIED] Post-execution 200 candidate checksum: {post_hash} (MATCH)")

if __name__ == "__main__":
    reset_150_workspace()

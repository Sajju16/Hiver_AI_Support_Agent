"""
scripts/build_golden_ai_assisted_150.py

Builds the 150-example AI-Assisted Provisional Evaluation Set (golden_ai_assisted_150.json)
from the deterministic 150 official candidates and evidence data.

Integrity Requirements:
1. golden_candidates_200.json SHA-256 remains sealed and untouched.
2. Every record explicitly sets:
   annotation_source = "AI_ASSISTED_PROVISIONAL"
   human_verified = False
3. Preserves all AI evidence, nearest-neighbour votes, classifier predictions, and escalation policy decisions.
"""

import sys, os, json, hashlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

GOLDEN_200_PATH = PROJECT_ROOT / "data" / "golden" / "golden_candidates_200.json"
EXPECTED_GOLDEN_SHA256 = "57682c611278ede6a89cadb5c7b1887498049689d2520952865a361c5a59adda"

OFFICIAL_150_PATH = PROJECT_ROOT / "data" / "golden" / "golden_official_candidates_150.json"
EVIDENCE_200_PATH = PROJECT_ROOT / "data" / "golden" / "golden_ai_assisted_evidence_200.json"
AI_ASSISTED_150_PATH = PROJECT_ROOT / "data" / "golden" / "golden_ai_assisted_150.json"
HASH_150_PATH = PROJECT_ROOT / "data" / "golden" / "golden_ai_assisted_150.sha256"


def verify_200_checksum():
    if not GOLDEN_200_PATH.exists():
        raise FileNotFoundError(f"Missing candidate file {GOLDEN_200_PATH}")
    with open(GOLDEN_200_PATH, "rb") as f:
        content_hash = hashlib.sha256(f.read()).hexdigest().lower()
    assert content_hash == EXPECTED_GOLDEN_SHA256, f"200 candidate checksum mismatch: {content_hash}"
    return content_hash


def build_ai_assisted_150():
    pre_hash = verify_200_checksum()
    print(f"[VERIFIED] Pre-execution 200 candidate checksum: {pre_hash}")

    if not OFFICIAL_150_PATH.exists():
        raise FileNotFoundError(f"Missing {OFFICIAL_150_PATH}")
    if not EVIDENCE_200_PATH.exists():
        raise FileNotFoundError(f"Missing {EVIDENCE_200_PATH}")

    with open(OFFICIAL_150_PATH, "r", encoding="utf-8") as f:
        official_candidates = json.load(f)

    with open(EVIDENCE_200_PATH, "r", encoding="utf-8") as f:
        evidence_list = json.load(f)

    evidence_map = {}
    for ev in evidence_list:
        key = (ev.get("conversation_id"), ev.get("turn_index"))
        evidence_map[key] = ev

    ai_assisted_150 = []

    for item in official_candidates:
        key = (item["conversation_id"], item["turn_index"])
        ev = evidence_map.get(key, {})

        rec = {
            "example_id": item["example_id"],
            "conversation_id": item["conversation_id"],
            "turn_index": item["turn_index"],
            "raw_text": item["raw_text"],
            "thread_context": item.get("thread_context", []),
            "candidate_bucket": item.get("candidate_bucket", "B1_core"),
            "candidate_intent_hint": item.get("candidate_intent_hint", ""),

            # Provisional AI-assisted labels
            "primary_intent": ev.get("predicted_intent", "Delivery_Tracking_And_Delays"),
            "secondary_intent": None,
            "escalate": ev.get("escalate", False),
            "escalate_reason": ev.get("escalation_reason", ""),
            "language_flag": ev.get("language_flag", False),
            "ambiguity_flag": ev.get("ambiguity_flag", False),
            "confidence_status": ev.get("confidence_status", "LOW_CONFIDENCE"),

            # Mandatory Integrity Metadata
            "annotation_source": "AI_ASSISTED_PROVISIONAL",
            "human_verified": False,

            # Evidence Breakdown
            "classifier_prediction": ev.get("classifier_prediction", {}),
            "top_3_reference_example_ids": ev.get("top_3_reference_example_ids", []),
            "top_3_reference_human_intents": ev.get("top_3_reference_human_intents", []),
            "top_3_similarity_scores": ev.get("top_3_similarity_scores", []),
            "retrieval_prediction": ev.get("retrieval_prediction", {}),
            "vote_distribution": ev.get("vote_distribution", {}),
            "decision_reason": ev.get("decision_reason", "")
        }
        ai_assisted_150.append(rec)

    # Sort deterministically by example_id
    ai_assisted_150.sort(key=lambda x: x["example_id"])

    json_bytes = json.dumps(ai_assisted_150, indent=2, ensure_ascii=False).encode("utf-8")
    with open(AI_ASSISTED_150_PATH, "wb") as f:
        f.write(json_bytes)
    print(f"[SAVED] AI-Assisted 150 evaluation set saved to {AI_ASSISTED_150_PATH}")

    # Compute and save SHA-256 hash
    file_sha256 = hashlib.sha256(json_bytes).hexdigest().lower()
    with open(HASH_150_PATH, "w", encoding="utf-8") as f:
        f.write(f"{file_sha256}  golden_ai_assisted_150.json\n")
    print(f"[SAVED] Checksum saved to {HASH_150_PATH} ({file_sha256})")

    post_hash = verify_200_checksum()
    assert post_hash == EXPECTED_GOLDEN_SHA256, "Checksum mismatch after build!"
    print(f"[VERIFIED] Post-execution 200 candidate checksum: {post_hash} (MATCH)")


if __name__ == "__main__":
    build_ai_assisted_150()

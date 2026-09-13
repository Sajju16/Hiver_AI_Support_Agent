"""
scripts/execute_spanish_replacements.py — Replace 5 mis-tagged B4 candidates in Golden Set

Replaces GOLDEN_161, GOLDEN_164, GOLDEN_168, GOLDEN_172, GOLDEN_175 with 5 manually verified Spanish customer-support turns.
Performs full verification checks, computes SHA256 checksum, and updates DECISION_LOG.md.
"""

import sys, json, hashlib
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_PATH = PROJECT_ROOT / "data" / "golden" / "golden_candidates_200.json"
DEV_PATH = PROJECT_ROOT / "data" / "dev" / "dev_candidates_50.json"
DECISION_LOG_PATH = PROJECT_ROOT / "DECISION_LOG.md"
CHECKSUM_PATH = PROJECT_ROOT / "data" / "golden" / "golden_candidates_200.json.sha256"

PROPOSED_REPLACEMENTS = {
    "GOLDEN_161": {
        "conversation_id": "4952_AmazonHelp",
        "turn_index": 0,
        "raw_text": "@116875 ¿como puedo trackear si esta próximo a ser entregado un paquete que tiene fecha de hoy? Gracias",
        "thread_context": []
    },
    "GOLDEN_164": {
        "conversation_id": "5779_AmazonHelp",
        "turn_index": 0,
        "raw_text": "@AmazonHelp https://t.co/ohEeuAt7A6 estais de coña no?el reembolso lo quiero ya, era para un regalo para hoy y tenia que llegar ayer.",
        "thread_context": []
    },
    "GOLDEN_168": {
        "conversation_id": "8516_AmazonHelp",
        "turn_index": 0,
        "raw_text": "@116875 Exijo mi reembolso inmediato ya que yo en ningún momento solicité dicha membresía \"prime\", hubo algún error.\nSolución inmediata",
        "thread_context": []
    },
    "GOLDEN_172": {
        "conversation_id": "13905_AmazonHelp",
        "turn_index": 0,
        "raw_text": "@116875 @118923 Uno de mis envíos acaba de ser devuelto, ( llevaba dos semanas en las instalaciones de mi ciudad.) ¿Qué pasa?",
        "thread_context": []
    },
    "GOLDEN_175": {
        "conversation_id": "24969_AmazonHelp",
        "turn_index": 0,
        "raw_text": "@116928 necesito ayuda ya que estoy recibiendo paquetes que no he comprado y me dijeron en atc que son regalos. Pero... De quien??",
        "thread_context": []
    }
}


def main():
    print("Loading existing Golden Set (200) and Dev Set (50)...", flush=True)
    with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
        golden = json.load(f)
    with open(DEV_PATH, "r", encoding="utf-8") as f:
        dev = json.load(f)

    print(f"Original Golden count: {len(golden)}")

    # Execute replacements
    replaced_count = 0
    for record in golden:
        eid = record["example_id"]
        if eid in PROPOSED_REPLACEMENTS:
            rep = PROPOSED_REPLACEMENTS[eid]
            record["conversation_id"] = rep["conversation_id"]
            record["turn_index"] = rep["turn_index"]
            record["raw_text"] = rep["raw_text"]
            record["thread_context"] = rep["thread_context"]
            record["candidate_bucket"] = "B4_non_english"
            record["candidate_intent_hint"] = "Non-English candidate (Spanish)"
            
            # Ground truth fields MUST be null
            record["primary_intent"] = None
            record["secondary_intent"] = None
            record["escalate"] = None
            record["escalate_reason"] = None
            record["language_flag"] = None
            record["ambiguity_flag"] = None
            record["annotator_notes"] = None
            replaced_count += 1

    print(f"Successfully replaced {replaced_count} records in Golden memory structure.")

    # Save updated Golden Set
    with open(GOLDEN_PATH, "w", encoding="utf-8") as f:
        json.dump(golden, f, indent=2, ensure_ascii=False)
    print(f"Saved updated Golden Set to {GOLDEN_PATH}")

    # VERIFICATION CHECKS
    print("\n" + "="*80)
    print("RUNNING POST-REPLACEMENT VERIFICATION CHECKS")
    print("="*80)

    # 1. Total Golden records == 200
    assert len(golden) == 200, f"Expected 200 Golden records, got {len(golden)}"
    print("VERIFIED: Exactly 200 Golden records.")

    # 2. Unique example IDs == 200
    eids = [r["example_id"] for r in golden]
    assert len(set(eids)) == 200, f"Duplicate example_ids found! {len(set(eids))} unique."
    print("VERIFIED: 200 unique example IDs.")

    # 3. Bucket counts
    bucket_counts = Counter(r["candidate_bucket"] for r in golden)
    print(f"Bucket Counts: {dict(bucket_counts)}")
    assert bucket_counts["B4_non_english"] == 20
    assert bucket_counts["B3_escalation"] == 25
    assert bucket_counts["B5_other"] == 20
    assert sum(bucket_counts.values()) == 200
    print("VERIFIED: Bucket counts preserved (Total=200, B4=20, B3=25, B5=20).")

    # 4. Zero Golden/Dev conversation overlap
    golden_convos = set(r["conversation_id"] for r in golden)
    dev_convos = set(r["conversation_id"] for r in dev)
    overlap = golden_convos.intersection(dev_convos)
    assert len(overlap) == 0, f"Leakage detected! {len(overlap)} overlapping conversation IDs."
    print("VERIFIED: Zero Golden/Dev conversation overlap.")

    # 5. All ground truth fields remain null
    for r in golden:
        for field in ["primary_intent", "secondary_intent", "escalate", "escalate_reason", "language_flag", "ambiguity_flag", "annotator_notes"]:
            assert r[field] is None, f"Field {field} in {r['example_id']} is not null!"
    print("VERIFIED: All ground-truth annotation fields are null.")

    # COMPUTE AND SAVE SHA256 CHECKSUM
    with open(GOLDEN_PATH, "rb") as f:
        golden_bytes = f.read()
    sha256_hash = hashlib.sha256(golden_bytes).hexdigest()

    with open(CHECKSUM_PATH, "w", encoding="utf-8") as f:
        f.write(f"{sha256_hash}  golden_candidates_200.json\n")
    print(f"VERIFIED & SEALED: SHA256 checksum created at {CHECKSUM_PATH}: {sha256_hash}")

    # UPDATE DECISION LOG
    decision_entry = "\n- **[2026-09-12] Spanish B4 Verification & Replacement**: Spanish language-detection heuristic showed persistently poor precision across two independent spot-checks; Spanish B4 candidates were manually verified before inclusion in the Golden set.\n"
    with open(DECISION_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(decision_entry)
    print(f"VERIFIED: Updated {DECISION_LOG_PATH} with mandatory decision log entry.")

if __name__ == "__main__":
    main()

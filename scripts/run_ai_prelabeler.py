"""
scripts/run_ai_prelabeler.py — Script to execute AI Pre-labeling over Dev Set (50 examples)

Executes unbiased AI pre-labeling over data/dev/dev_candidates_50.json.
Exports structured pre-labels to data/dev/dev_ai_prelabels_50.json.
Generates comprehensive schema validation and report artifact.
"""

import sys, json, hashlib
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.ai.prelabeler import run_ai_prelabeler, CORE_INTENTS, TAXONOMY_PROMPT

DEV_PATH = PROJECT_ROOT / "data" / "dev" / "dev_candidates_50.json"
OUTPUT_PRELABELS_PATH = PROJECT_ROOT / "data" / "dev" / "dev_ai_prelabels_50.json"
REPORT_PATH = PROJECT_ROOT / "data" / "dev" / "dev_ai_prelabel_report.json"
GOLDEN_PATH = PROJECT_ROOT / "data" / "golden" / "golden_candidates_200.json"
GOLDEN_CHECKSUM_PATH = PROJECT_ROOT / "data" / "golden" / "golden_candidates_200.json.sha256"

EXPECTED_GOLDEN_SHA256 = "57682c611278ede6a89cadb5c7b1887498049689d2520952865a361c5a59adda"
MODEL_NAME = "zero_shot_classifier_v1"
PROMPT_VERSION = "v1.0.0"

def main():
    print("Executing AI Pre-labeler over 50 Dev examples...", flush=True)

    # 1. Compute prompt hash for reproducibility
    prompt_bytes = TAXONOMY_PROMPT.encode("utf-8")
    prompt_hash = hashlib.sha256(prompt_bytes).hexdigest()

    # 2. Run Pre-labeler
    results = run_ai_prelabeler(
        input_filepath=DEV_PATH,
        output_filepath=OUTPUT_PRELABELS_PATH,
        model_name=MODEL_NAME,
        prompt_version=PROMPT_VERSION
    )

    # 3. SCHEMA & INTEGRITY VALIDATIONS
    print("\n" + "="*80)
    print("RUNNING SCHEMA & INTEGRITY VALIDATION CHECKS")
    print("="*80)

    # Check 1: Total processed == 50
    assert len(results) == 50, f"Expected 50 results, got {len(results)}"
    print("VALIDATION 1 PASSED: Processed exactly 50 Dev examples.")

    # Check 2: Schema validation per record
    for r in results:
        assert "example_id" in r and "conversation_id" in r and "turn_index" in r and "raw_text" in r
        assert "ai_prelabel" in r and "model_metadata" in r

        pre = r["ai_prelabel"]
        assert pre["primary_intent"] in CORE_INTENTS, f"Invalid primary_intent: {pre['primary_intent']}"
        assert isinstance(pre["escalate"], bool), f"Escalate is not bool for {r['example_id']}"
        assert isinstance(pre["escalation_reason"], str), f"Escalation_reason is not str for {r['example_id']}"
        assert isinstance(pre["language_flag"], bool), f"Language_flag is not bool for {r['example_id']}"
        assert isinstance(pre["ambiguity_flag"], bool), f"Ambiguity_flag is not bool for {r['example_id']}"
        assert isinstance(pre["reasoning"], str) and len(pre["reasoning"]) > 0, f"Reasoning invalid for {r['example_id']}"

    print("VALIDATION 2 PASSED: 100% schema compliance across all 50 records.")

    # Check 3: Candidate ground-truth fields in source file remain null/untouched
    with open(DEV_PATH, "r", encoding="utf-8") as f:
        dev_orig = json.load(f)
    for r in dev_orig:
        assert r.get("primary_intent") is None, f"{r['example_id']} in source file was modified!"
    print("VALIDATION 3 PASSED: Source Dev candidate ground-truth fields remain null/untouched.")

    # Check 4: Golden set file remains sealed and untouched
    with open(GOLDEN_PATH, "rb") as f:
        golden_bytes = f.read()
    golden_hash = hashlib.sha256(golden_bytes).hexdigest().lower()
    assert golden_hash == EXPECTED_GOLDEN_SHA256, f"GOLDEN CHECKSUM MISMATCH! Computed: {golden_hash}, Expected: {EXPECTED_GOLDEN_SHA256}"
    print(f"VALIDATION 4 PASSED: Golden set UNTOUCHED. Verified SHA256: {golden_hash}")

    # 4. METRICS & SUMMARY GENERATION
    predicted_intents = Counter(r["ai_prelabel"]["primary_intent"] for r in results)
    escalate_cnt = sum(1 for r in results if r["ai_prelabel"]["escalate"])
    ambiguity_cnt = sum(1 for r in results if r["ai_prelabel"]["ambiguity_flag"])
    non_en_cnt = sum(1 for r in results if r["ai_prelabel"]["language_flag"])

    report_data = {
        "summary": {
            "total_examples_processed": len(results),
            "valid_predictions_count": len(results),
            "invalid_or_missing_predictions": 0,
            "escalation_count": escalate_cnt,
            "escalation_rate_pct": round(escalate_cnt / len(results) * 100, 2),
            "ambiguity_count": ambiguity_cnt,
            "ambiguity_rate_pct": round(ambiguity_cnt / len(results) * 100, 2),
            "non_english_count": non_en_cnt,
            "non_english_rate_pct": round(non_en_cnt / len(results) * 100, 2)
        },
        "model_configuration": {
            "model_name": MODEL_NAME,
            "prompt_version": PROMPT_VERSION,
            "prompt_hash_sha256": prompt_hash,
            "unbiased_input_fields": ["raw_text", "thread_context"],
            "excluded_metadata_fields": ["candidate_bucket", "candidate_intent_hint", "sampling_reason"]
        },
        "predicted_intent_distribution": dict(predicted_intents),
        "golden_checksum_verification": {
            "golden_filepath": str(GOLDEN_PATH),
            "expected_sha256": EXPECTED_GOLDEN_SHA256,
            "computed_sha256": golden_hash,
            "verification_status": "MATCH_CONFIRMED"
        }
    }

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)
    print(f"\nGenerated report artifact at {REPORT_PATH}")

    print("\n" + "="*80)
    print("AI PRE-LABELING METRICS SUMMARY")
    print("="*80)
    print(f"Total Examples Processed: {len(results)}")
    print(f"Model Configuration: {MODEL_NAME} (Prompt {PROMPT_VERSION})")
    print(f"Prompt SHA256: {prompt_hash}")
    print("\nPredicted Primary Intent Distribution:")
    for intent, cnt in predicted_intents.most_common():
        print(f"  {intent}: {cnt}")
    print(f"\nEscalation Count: {escalate_cnt} / 50 ({escalate_cnt/50*100:.1f}%)")
    print(f"Ambiguity Count: {ambiguity_cnt} / 50 ({ambiguity_cnt/50*100:.1f}%)")
    print(f"Non-English Count: {non_en_cnt} / 50 ({non_en_cnt/50*100:.1f}%)")

if __name__ == "__main__":
    main()

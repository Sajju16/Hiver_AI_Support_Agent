"""
scripts/verify_b4_golden_candidates.py — B4 Non-English Verification

Inspects B4 candidates in data/golden/golden_candidates_200.json without encoding errors.
Outputs JSON and clean text.
"""

import json
from pathlib import Path

GOLDEN_PATH = Path("data/golden/golden_candidates_200.json")
OUTPUT_PATH = Path("data/processed/b4_verification_details.json")

def main():
    with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
        candidates = json.load(f)

    b4_candidates = [c for c in candidates if c.get("candidate_bucket") == "B4_non_english"]

    out = []
    for c in b4_candidates:
        out.append({
            "example_id": c["example_id"],
            "conversation_id": c["conversation_id"],
            "raw_text": c["raw_text"],
            "candidate_intent_hint": c["candidate_intent_hint"]
        })

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"Extracted {len(out)} B4 candidates to {OUTPUT_PATH}")

if __name__ == "__main__":
    main()

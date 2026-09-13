"""
scripts/review_golden_150.py

Interactive CLI Reviewer & Verification Engine for Golden 150 Set.

Rules & Capabilities:
1. Displays Customer Turn + Thread Context + AI Evidence.
2. Allows:
   - [ENTER] Accept AI Suggested Intent -> annotation_source = "HUMAN_VERIFIED_AI_ASSISTED"
   - [1-11] Select taxonomy override -> annotation_source = "HUMAN_VERIFIED_MANUAL_OVERRIDE"
   - [b] Go back to previous example
   - [j] Jump to specific example index (1-150)
   - [q] Quit session & save progress immediately.
3. Strict Escalation Reason Validation:
   - When Escalate = True (y), a non-empty, valid escalation reason is MANDATORY.
   - Reject 'n', 'no', 'false', or empty inputs as an escalation reason.
   - Provides standard mandatory escalation options (1-4) or custom input (5).
4. Full Support for Re-Reviewing/Editing Verified Records:
   - Can edit any previously verified record at any time.
5. Strictly requires interactive human confirmation to set human_verified = True.
"""

import sys, os, json, hashlib
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

REVIEW_150_PATH = PROJECT_ROOT / "data" / "golden" / "golden_human_review_150.json"
FINAL_150_PATH = PROJECT_ROOT / "data" / "golden" / "golden_human_verified_150.json"
HASH_150_PATH = PROJECT_ROOT / "data" / "golden" / "golden_human_verified_150.sha256"
REPORT_150_PATH = PROJECT_ROOT / "data" / "golden" / "GOLDEN_150_FREEZE_REPORT.md"
GOLDEN_200_PATH = PROJECT_ROOT / "data" / "golden" / "golden_candidates_200.json"
EXPECTED_GOLDEN_SHA256 = "57682c611278ede6a89cadb5c7b1887498049689d2520952865a361c5a59adda"

TAXONOMY_INTENTS = [
    "Delivery_Tracking_And_Delays",
    "Technical_App_And_Website_Issues",
    "Prime_Subscription_And_Digital_Media",
    "Refund_Status_And_Billing_Disputes",
    "Return_Exchange_And_Pickup",
    "Order_Cancellation_And_Address_Change",
    "Damaged_Defective_Or_Wrong_Item",
    "General_Service_Complaint_Escalation",
    "Promotions_GiftCards_And_Pricing",
    "Marked_Delivered_Not_Received",
    "Other_Unclassified_Inquiry"
]

STANDARD_ESCALATION_REASONS = [
    "Mandatory Risk Rule: Package marked delivered but not received / suspected theft.",
    "Mandatory Risk Rule: Unauthorized billing, fraud allegation, or scam report.",
    "Mandatory Risk Rule: Account security or compromise issue.",
    "Mandatory Risk Rule: Legal or regulatory action threat."
]


def verify_200_checksum():
    with open(GOLDEN_200_PATH, "rb") as f:
        content_hash = hashlib.sha256(f.read()).hexdigest().lower()
    assert content_hash == EXPECTED_GOLDEN_SHA256, f"200 candidate checksum mismatch: {content_hash}"
    return content_hash


def get_sorting_priority(item: dict) -> tuple:
    bucket = item.get("candidate_bucket", "B1_core")
    confidence = item.get("confidence", "LOW_CONFIDENCE")
    
    if bucket == "B1_core" and confidence == "HIGH_CONFIDENCE":
        prio = 0
    elif bucket == "B1_core":
        prio = 1
    elif bucket == "B4_non_english":
        prio = 2
    elif bucket == "B5_other":
        prio = 3
    elif bucket == "B2_confusing":
        prio = 4
    elif bucket == "B3_escalation":
        prio = 5
    else:
        prio = 6
        
    return (prio, item.get("example_id", ""))


def export_final_golden_set(records: list):
    """Exports final human verified 150 golden file, SHA-256 hash, and freeze report."""
    verify_200_checksum()

    verified_records = [r for r in records if r.get("human_verified") is True]
    if len(verified_records) < 150:
        print(f"\n[NOTICE] Currently {len(verified_records)}/150 records verified. Final export requires all 150.")
        return

    final_output = []
    for item in verified_records:
        rec = {
            "example_id": item["example_id"],
            "conversation_id": item["conversation_id"],
            "turn_index": item["turn_index"],
            "raw_text": item["raw_text"],
            "thread_context": item.get("thread_context", []),
            "candidate_bucket": item.get("candidate_bucket", "B1_core"),
            "primary_intent": item["primary_intent"],
            "secondary_intent": item.get("secondary_intent"),
            "escalate": item["escalate"],
            "escalate_reason": item.get("escalate_reason", ""),
            "language_flag": item.get("language_flag", False),
            "ambiguity_flag": item.get("ambiguity_flag", False),
            "annotator_notes": item.get("annotator_notes", ""),
            "annotation_source": item.get("annotation_source", "HUMAN_VERIFIED_AI_ASSISTED"),
            "human_verified": True
        }
        final_output.append(rec)

    final_output.sort(key=lambda x: x["example_id"])

    json_bytes = json.dumps(final_output, indent=2, ensure_ascii=False).encode("utf-8")
    with open(FINAL_150_PATH, "wb") as f:
        f.write(json_bytes)
    print(f"\n[EXPORTED] Final 150 Human-Verified Golden set saved to {FINAL_150_PATH}")

    final_sha256 = hashlib.sha256(json_bytes).hexdigest().lower()
    with open(HASH_150_PATH, "w", encoding="utf-8") as f:
        f.write(f"{final_sha256}  golden_human_verified_150.json\n")
    print(f"[EXPORTED] Checksum saved to {HASH_150_PATH} ({final_sha256})")

    sources_cnt = Counter(r["annotation_source"] for r in final_output)
    buckets_cnt = Counter(r["candidate_bucket"] for r in final_output)
    intents_cnt = Counter(r["primary_intent"] for r in final_output)
    escalate_cnt = Counter(r["escalate"] for r in final_output)
    ambiguous_cnt = sum(1 for r in final_output if r.get("ambiguity_flag"))
    lang_cnt = sum(1 for r in final_output if r.get("language_flag"))

    ai_assisted_cnt = sources_cnt.get("HUMAN_VERIFIED_AI_ASSISTED", 0)
    manual_override_cnt = sources_cnt.get("HUMAN_VERIFIED_MANUAL_OVERRIDE", 0)

    freeze_report = f"""# Golden 150 Set — Final Freeze Report

## 1. Executive Summary
- **Official Golden Set Size**: Exactly 150 Human-Verified Examples
- **Verification Status**: 100% Human-Verified (`human_verified = true`)
- **Sealed Candidate SHA-256 Checksum**: `{EXPECTED_GOLDEN_SHA256}` (UNTOUCHED)
- **Final Official Golden 150 SHA-256 Checksum**: `{final_sha256}`

## 2. Verification Method Breakdown
- **Human-Confirmed AI Suggestions**: {ai_assisted_cnt} examples ({ai_assisted_cnt/150:.1%})
- **Human Manual Overrides**: {manual_override_cnt} examples ({manual_override_cnt/150:.1%})
- **Unverified AI Records Included**: 0 (STRICT INTEGRITY ENFORCED)

## 3. Stratified Bucket Distribution
| Bucket | Count | Target Ratio |
|---|---|---|
| **B1_core** | {buckets_cnt.get('B1_core', 0)} | 50.0% (75/150) |
| **B2_confusing** | {buckets_cnt.get('B2_confusing', 0)} | 16.7% (25/150) |
| **B3_escalation** | {buckets_cnt.get('B3_escalation', 0)} | 13.3% (20/150) |
| **B4_non_english** | {buckets_cnt.get('B4_non_english', 0)} | 10.0% (15/150) |
| **B5_other** | {buckets_cnt.get('B5_other', 0)} | 10.0% (15/150) |
| **TOTAL** | **150** | **100.0%** |

## 4. Intent Distribution (Human Verified Ground Truth)
| Intent | Count | Percentage |
|---|---|---|
"""
    for intent, count in sorted(intents_cnt.items(), key=lambda x: x[1], reverse=True):
        freeze_report += f"| `{intent}` | {count} | {count/150:.1%} |\n"

    freeze_report += f"""
## 5. Escalation & Quality Flags
- **Escalated Cases (`escalate = True`)**: {escalate_cnt.get(True, 0)} ({escalate_cnt.get(True, 0)/150:.1%})
- **Non-Escalated Cases (`escalate = False`)**: {escalate_cnt.get(False, 0)} ({escalate_cnt.get(False, 0)/150:.1%})
- **Ambiguous Cases Flagged**: {ambiguous_cnt} ({ambiguous_cnt/150:.1%})
- **Non-English Language Flagged**: {lang_cnt} ({lang_cnt/150:.1%})

## 6. Integrity Statement
No AI predictions were written to the ground-truth evaluation set without explicit human review and approval. Every record in `golden_human_verified_150.json` has `human_verified = true` and `primary_intent != null`.
"""

    with open(REPORT_150_PATH, "w", encoding="utf-8") as f:
        f.write(freeze_report)
    print(f"[EXPORTED] Freeze report saved to {REPORT_150_PATH}")


def prompt_escalation_reason(ai_esc_reason: str) -> str:
    """Interactively prompts and validates a non-empty escalation reason."""
    print("\n  SELECT / ENTER ESCALATION REASON:")
    for idx, reason in enumerate(STANDARD_ESCALATION_REASONS, 1):
        print(f"    {idx}. {reason}")
    print(f"    5. Custom Escalation Reason...")
    if ai_esc_reason:
        print(f"    [ENTER] Use AI suggestion: '{ai_esc_reason}'")

    while True:
        try:
            choice = input("  Escalation Reason Choice > ").strip()
        except EOFError:
            return ai_esc_reason if ai_esc_reason else STANDARD_ESCALATION_REASONS[0]

        if choice == "" and ai_esc_reason:
            return ai_esc_reason
        elif choice == "1":
            return STANDARD_ESCALATION_REASONS[0]
        elif choice == "2":
            return STANDARD_ESCALATION_REASONS[1]
        elif choice == "3":
            return STANDARD_ESCALATION_REASONS[2]
        elif choice == "4":
            return STANDARD_ESCALATION_REASONS[3]
        elif choice == "5":
            try:
                custom_r = input("  Enter Custom Reason > ").strip()
            except EOFError:
                custom_r = ""
            if custom_r and custom_r.lower() not in ["n", "no", "false"]:
                return custom_r
            print("  [ERROR] Custom reason cannot be empty or 'n'/'no'. Please enter a valid reason.")
        else:
            # Direct text input check
            if choice and choice.lower() not in ["n", "no", "false"]:
                return choice
            print("  [ERROR] When Escalate=True, a valid non-empty escalation reason is REQUIRED ('n' is not accepted).")


def run_cli_reviewer():
    if not REVIEW_150_PATH.exists():
        from create_golden_150_subset import reset_150_workspace
        reset_150_workspace()

    with open(REVIEW_150_PATH, "r", encoding="utf-8") as f:
        records = json.load(f)

    # Sort for optimal human review speed
    sorted_records = sorted(records, key=get_sorting_priority)

    verified_count = sum(1 for r in sorted_records if r.get("human_verified") is True)
    total_count = len(sorted_records)

    print("==================================================")
    print("      GOLDEN 150 HUMAN VERIFICATION CLI REVIEWER  ")
    print("==================================================")
    print(f"Total Examples: {total_count}")
    print(f"Already Verified: {verified_count} / {total_count}")

    curr_idx = 0

    # If verified count > 0, find first unverified example
    for i, item in enumerate(sorted_records):
        if not item.get("human_verified"):
            curr_idx = i
            break

    while True:
        if curr_idx < 0:
            curr_idx = 0
        if curr_idx >= total_count:
            curr_idx = total_count - 1

        item = sorted_records[curr_idx]

        ex_id = item.get("example_id")
        raw_text = item.get("raw_text", "")
        context = item.get("thread_context", [])
        bucket = item.get("candidate_bucket", "B1_core")
        sug_intent = item.get("ai_suggested_intent")
        clf_intent = item.get("classifier_intent")
        nn_intent = item.get("nn_intent")
        ret_intent = item.get("retrieval_intent")
        ai_esc = item.get("ai_escalate")
        ai_esc_reason = item.get("ai_escalate_reason")
        conf = item.get("confidence")

        is_verified = item.get("human_verified", False)
        status_str = f"VERIFIED ({item.get('primary_intent')})" if is_verified else "PENDING"

        print("\n" + "="*60)
        print(f"Example {curr_idx+1} / {total_count} [{ex_id}] — Bucket: {bucket} | Status: {status_str}")
        print("="*60)
        print(f"Customer Turn: {raw_text}")
        if context:
            ctx_str = " | ".join([f"{c.get('author')}: {c.get('text')}" for c in context])
            print(f"Thread Context: {ctx_str}")

        print("\nAI Evidence:")
        print(f"  - Classifier Prediction: {clf_intent}")
        print(f"  - Nearest-Neighbour Vote: {nn_intent}")
        print(f"  - Historical Retrieval:   {ret_intent}")
        print(f"  - AI Suggested Intent:    {sug_intent}")
        print(f"  - AI Escalation Suggestion: {ai_esc} ({ai_esc_reason})")

        print("\nTAXONOMY INTENTS:")
        for i, intent_name in enumerate(TAXONOMY_INTENTS, 1):
            marker = " -> [SUGGESTED]" if intent_name == sug_intent else ""
            if is_verified and intent_name == item.get("primary_intent"):
                marker += " [CURRENTLY VERIFIED]"
            print(f"  {i:2d}. {intent_name}{marker}")

        print("\nOption:")
        print(f"  [ENTER] Accept AI Suggested Intent: {sug_intent}")
        print("  [1-11] Select intent override by number")
        print("  [b] Go to previous example")
        print("  [j] Jump to specific example index (1-150)")
        print("  [q] Quit review and save progress")

        try:
            user_in = input("\nYour Choice > ").strip().lower()
        except EOFError:
            print("\nNon-interactive session detected. Exiting CLI reviewer.")
            break

        if user_in == 'q':
            print("Progress saved. Exiting CLI reviewer.")
            break
        elif user_in == 'b':
            curr_idx = max(0, curr_idx - 1)
            continue
        elif user_in == 'j':
            try:
                j_idx = input(f"Enter example index to jump to (1-{total_count}) > ").strip()
                if j_idx.isdigit() and 1 <= int(j_idx) <= total_count:
                    curr_idx = int(j_idx) - 1
                    continue
            except EOFError:
                pass
            print("Invalid jump index!")
            continue

        chosen_intent = None
        source = None

        if user_in == "":
            chosen_intent = sug_intent
            source = "HUMAN_VERIFIED_AI_ASSISTED"
            print(f"Confirmed: {chosen_intent}")
        elif user_in.isdigit() and 1 <= int(user_in) <= 11:
            chosen_intent = TAXONOMY_INTENTS[int(user_in) - 1]
            source = "HUMAN_VERIFIED_MANUAL_OVERRIDE"
            print(f"Selected Override: {chosen_intent}")
        else:
            print("Invalid selection! Skipping example...")
            continue

        # Escalation input with strict validation
        while True:
            try:
                esc_in = input(f"Escalate? (y/n) [default: {'y' if ai_esc else 'n'}]: ").strip().lower()
            except EOFError:
                esc_in = "y" if ai_esc else "n"

            if esc_in == 'y' or (esc_in == "" and ai_esc):
                esc_val = True
                esc_reason_val = prompt_escalation_reason(ai_esc_reason)
                break
            elif esc_in == 'n' or (esc_in == "" and not ai_esc):
                esc_val = False
                esc_reason_val = ""
                break
            else:
                print("Please enter 'y' for escalate or 'n' for no escalation.")

        try:
            amb_in = input("Flag as Ambiguous? (y/n) [default: n]: ").strip().lower()
        except EOFError:
            amb_in = "n"
        amb_val = (amb_in == 'y')

        try:
            notes_in = input("Annotator Notes (optional): ").strip()
        except EOFError:
            notes_in = ""

        # Save record update
        item["primary_intent"] = chosen_intent
        item["escalate"] = esc_val
        item["escalate_reason"] = esc_reason_val
        item["ambiguity_flag"] = amb_val
        item["annotator_notes"] = notes_in
        item["annotation_source"] = source
        item["human_verified"] = True

        with open(REVIEW_150_PATH, "w", encoding="utf-8") as f:
            json.dump(sorted_records, f, indent=2, ensure_ascii=False)

        verified_count = sum(1 for r in sorted_records if r.get("human_verified") is True)
        print(f"Saved! ({verified_count}/{total_count} verified)")

        curr_idx += 1
        if curr_idx >= total_count:
            # Check if all verified
            unverified_remaining = [r for r in sorted_records if not r.get("human_verified")]
            if len(unverified_remaining) == 0:
                print("\nAll 150 examples are now human-verified!")
                export_final_golden_set(sorted_records)
                break
            else:
                curr_idx = sorted_records.index(unverified_remaining[0])


if __name__ == "__main__":
    run_cli_reviewer()

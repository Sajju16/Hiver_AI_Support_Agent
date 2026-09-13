"""
scripts/annotate_golden_human_cli.py — Interactive Human Cold-Labeling Tool for Golden 200 Set

Provides an unbiased, zero-hint CLI interface for human cold-labeling of the 200 Golden examples.
Based on the DEV annotation CLI, adapted for the Golden evaluation set.

Key differences from the DEV CLI:
- Reads/writes data/golden/golden_candidates_200.json directly (annotates in-place with labels).
- Produces a separate golden_human_labels_200.json output file for labelled data.
- Verifies the Golden set checksum before every session.
- Hides candidate_bucket and candidate_intent_hint from the annotator.
- Does NOT show any AI prelabels or external labels.
- Saves a golden_human_annotation_report.json after each annotation.
- Does NOT modify DEV 50 or external 187 data.
"""

import sys, json, hashlib, copy
from pathlib import Path
from datetime import datetime, timezone

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


PROJECT_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_CANDIDATES_PATH = PROJECT_ROOT / "data" / "golden" / "golden_candidates_200.json"
GOLDEN_HUMAN_LABELS_PATH = PROJECT_ROOT / "data" / "golden" / "golden_human_labels_200.json"
GOLDEN_REPORT_PATH = PROJECT_ROOT / "data" / "golden" / "golden_human_annotation_report.json"

EXPECTED_GOLDEN_SHA256 = "57682c611278ede6a89cadb5c7b1887498049689d2520952865a361c5a59adda"

INTENT_MAP = {
    1: "Delivery_Tracking_And_Delays",
    2: "Technical_App_And_Website_Issues",
    3: "Prime_Subscription_And_Digital_Media",
    4: "Refund_Status_And_Billing_Disputes",
    5: "Return_Exchange_And_Pickup",
    6: "Order_Cancellation_And_Address_Change",
    7: "Damaged_Defective_Or_Wrong_Item",
    8: "General_Service_Complaint_Escalation",
    9: "Promotions_GiftCards_And_Pricing",
    10: "Marked_Delivered_Not_Received",
    11: "Other_Unclassified_Inquiry"
}

TAXONOMY_CHEAT_SHEET = """
================================================================================
FROZEN 10-INTENT TAXONOMY CHEAT SHEET (+ 1 AUXILIARY NOISE CATEGORY)
================================================================================
 1. Delivery_Tracking_And_Delays        : ETA, tracking, delay, late delivery, shipment status.
 2. Technical_App_And_Website_Issues    : Website/app glitches, login failure, cart/checkout error.
 3. Prime_Subscription_And_Digital_Media: Prime membership, Prime Video, Kindle, Alexa, Music.
 4. Refund_Status_And_Billing_Disputes   : Refund status, missing refund, double charge, bank dispute.
 5. Return_Exchange_And_Pickup          : Return process, return label, courier pickup, item exchange.
 6. Order_Cancellation_And_Address_Change: Pre-dispatch cancel order, change shipping address.
 7. Damaged_Defective_Or_Wrong_Item     : Broken product, defective hardware, wrong item delivered.
 8. General_Service_Complaint_Escalation: Support rep complaint, agent hung up, manager demand.
 9. Promotions_GiftCards_And_Pricing    : Gift card, promo code, discount, price drop/match.
10. Marked_Delivered_Not_Received      : Tracking says delivered BUT package is missing/stolen.
11. Other_Unclassified_Inquiry         : Social banter, memes, praise, unanswerable link-only.
================================================================================
"""

ESCALATION_GUIDANCE = """
================================================================================
ESCALATION GUIDANCE (Independent from intent classification)
================================================================================
Escalate = True ONLY for:
  - Missing/stolen package (confirmed, not just tracking delay)
  - Public PII/privacy exposure
  - Account security/compromise
  - Unauthorized billing/fraud
  - Severe supervisor/legal/regulatory situation
  - Other clearly high-risk cases

Do NOT escalate merely because:
  - Classifier confidence is low
  - Intent is Other_Unclassified_Inquiry
  - Language is non-English
================================================================================
"""

GT_FIELDS = ["primary_intent", "secondary_intent", "escalate", "escalate_reason",
             "language_flag", "ambiguity_flag", "annotator_notes"]


def verify_golden_candidates_checksum():
    """Verify the original Golden 200 candidates file checksum."""
    if not GOLDEN_CANDIDATES_PATH.exists():
        raise FileNotFoundError(f"Golden candidates file missing: {GOLDEN_CANDIDATES_PATH}")
    with open(GOLDEN_CANDIDATES_PATH, "rb") as f:
        computed = hashlib.sha256(f.read()).hexdigest().lower()
    if computed != EXPECTED_GOLDEN_SHA256:
        raise AssertionError(
            f"GOLDEN SET CHECKSUM MISMATCH!\n"
            f"  Computed: {computed}\n"
            f"  Expected: {EXPECTED_GOLDEN_SHA256}\n"
            f"  The Golden candidates file may have been modified. Aborting."
        )
    return computed


def init_golden_labels_file():
    """
    Initialize or load data/golden/golden_human_labels_200.json.
    The original golden_candidates_200.json is NEVER modified.
    Labels are stored in a separate file.
    """
    verify_golden_candidates_checksum()

    with open(GOLDEN_CANDIDATES_PATH, "r", encoding="utf-8") as f:
        candidates = json.load(f)

    if GOLDEN_HUMAN_LABELS_PATH.exists():
        with open(GOLDEN_HUMAN_LABELS_PATH, "r", encoding="utf-8") as f:
            existing = json.load(f)
        # Validate alignment
        if len(existing) == len(candidates):
            # Verify example_ids match
            existing_ids = [r["example_id"] for r in existing]
            candidate_ids = [r["example_id"] for r in candidates]
            if existing_ids == candidate_ids:
                print(f"Resuming from existing labels file ({GOLDEN_HUMAN_LABELS_PATH.name})")
                return existing

    # Create new labels file from candidates (deep copy, no bucket/hint leakage)
    labels = []
    for c in candidates:
        rec = {
            "example_id": c["example_id"],
            "conversation_id": c["conversation_id"],
            "turn_index": c["turn_index"],
            "raw_text": c["raw_text"],
            "thread_context": copy.deepcopy(c.get("thread_context", [])),
            # Ground-truth fields start as null
            "primary_intent": None,
            "secondary_intent": None,
            "escalate": None,
            "escalate_reason": None,
            "language_flag": None,
            "ambiguity_flag": None,
            "annotator_notes": None,
        }
        # NOTE: candidate_bucket and candidate_intent_hint are deliberately EXCLUDED
        #       to prevent any annotation bias.
        labels.append(rec)

    save_labels(labels)
    print(f"Created new labels file: {GOLDEN_HUMAN_LABELS_PATH.name}")
    return labels


def save_labels(labels):
    """Save the labels file with instant persistence."""
    GOLDEN_HUMAN_LABELS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(GOLDEN_HUMAN_LABELS_PATH, "w", encoding="utf-8") as f:
        json.dump(labels, f, indent=2, ensure_ascii=False)


def generate_report(labels):
    """Generate and save annotation progress report."""
    completed = [r for r in labels if r.get("primary_intent") is not None]
    flagged = [r for r in labels if r.get("primary_intent") is None and r.get("annotator_notes") == "FLAGGED FOR REVIEW"]
    remaining = [r for r in labels if r.get("primary_intent") is None and r.get("annotator_notes") != "FLAGGED FOR REVIEW"]

    intent_counts = {}
    escalate_count = 0
    ambiguity_count = 0
    non_en_count = 0

    for r in completed:
        p = r["primary_intent"]
        intent_counts[p] = intent_counts.get(p, 0) + 1
        if r.get("escalate") is True:
            escalate_count += 1
        if r.get("ambiguity_flag") is True:
            ambiguity_count += 1
        if r.get("language_flag") is True:
            non_en_count += 1

    report = {
        "total_examples": len(labels),
        "completed_count": len(completed),
        "flagged_count": len(flagged),
        "remaining_count": len(remaining),
        "primary_intent_distribution": dict(sorted(intent_counts.items())),
        "escalation_count": escalate_count,
        "ambiguity_count": ambiguity_count,
        "non_english_count": non_en_count,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }

    with open(GOLDEN_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    return report


def print_progress(labels):
    """Print current progress summary."""
    completed = sum(1 for r in labels if r.get("primary_intent") is not None)
    flagged = sum(1 for r in labels if r.get("primary_intent") is None and r.get("annotator_notes") == "FLAGGED FOR REVIEW")
    remaining = len(labels) - completed - flagged
    print(f"\n  Progress: {completed}/200 completed | {flagged} flagged | {remaining} remaining")


def prompt_primary_intent():
    """Prompts for Primary Intent, accepting ONLY integer 1-11."""
    while True:
        val = input("\nPrimary Intent [1-11]: ").strip()
        if val.isdigit():
            num = int(val)
            if 1 <= num <= 11:
                chosen = INTENT_MAP[num]
                print(f"  -> {chosen}")
                return chosen
        print("ERROR: Invalid input. Primary Intent must be an integer between 1 and 11.")


def display_example(rec, idx, total):
    """Display a single example for annotation (bias-free)."""
    is_flagged = rec.get("primary_intent") is None and rec.get("annotator_notes") == "FLAGGED FOR REVIEW"
    is_completed = rec.get("primary_intent") is not None
    if is_flagged:
        status_str = "FLAGGED FOR REVIEW"
    elif is_completed:
        status_str = "COMPLETED"
    else:
        status_str = "UNPROCESSED"

    print("\n" + "=" * 80)
    print(f"GOLDEN EXAMPLE {idx + 1} / {total}  [{status_str}]  (ID: {rec['example_id']})")
    print("=" * 80)

    # STRICT ISOLATION: Display ONLY customer message and thread context.
    # NO candidate_bucket, NO candidate_intent_hint, NO AI prelabels.
    print("\nCUSTOMER MESSAGE:")
    print(f"  {rec['raw_text']}")

    print("\nPREVIOUS THREAD CONTEXT:")
    ctx = rec.get("thread_context", [])
    if ctx:
        for t_i, turn in enumerate(ctx):
            author = turn.get("author", "User")
            text = turn.get("text", "")
            print(f"  [{t_i + 1}] {author}: {text}")
    else:
        print("  (None -- Standalone Customer Turn)")

    print("-" * 80)
    if is_completed:
        print(f"[Saved Label: {rec['primary_intent']} | Escalate: {rec['escalate']} | Lang: {rec['language_flag']} | Amb: {rec['ambiguity_flag']}]")
        print("-" * 80)
    elif is_flagged:
        print("[Status: FLAGGED FOR REVIEW]")
        print("-" * 80)


def collect_annotation():
    """Collect all annotation fields from human input."""
    # 1. Primary Intent (STRICT: ONLY 1-11 accepted)
    p_intent = prompt_primary_intent()

    # 2. Secondary Intent (optional)
    sec_val = input("Secondary Intent [1-11, or Enter for none]: ").strip()
    s_intent = None
    if sec_val.isdigit() and 1 <= int(sec_val) <= 11:
        s_intent = INTENT_MAP[int(sec_val)]
        print(f"  -> {s_intent}")

    # 3 & 4. Escalate & Reason
    esc_val = input("Escalate? [y/N, default=n]: ").strip().lower()
    is_esc = esc_val.startswith('y')
    esc_reason = ""
    if is_esc:
        while not esc_reason:
            esc_reason = input("Escalation Reason [Required]: ").strip()

    # 5. Language flag
    lang_val = input("Language flag (Non-English)? [y/N, default=n]: ").strip().lower()
    is_lang = lang_val.startswith('y')

    # 6. Ambiguity flag
    amb_val = input("Ambiguity flag? [y/N, default=n]: ").strip().lower()
    is_amb = amb_val.startswith('y')

    # 7. Annotator notes
    notes = input("Annotator Notes [optional]: ").strip()

    return {
        "primary_intent": p_intent,
        "secondary_intent": s_intent,
        "escalate": is_esc,
        "escalate_reason": esc_reason,
        "language_flag": is_lang,
        "ambiguity_flag": is_amb,
        "annotator_notes": notes if notes else None,
    }


def show_review(annotation):
    """Display annotation for human confirmation before saving."""
    print("\n" + "-" * 40)
    print("REVIEW ANNOTATION")
    print("-" * 40)
    print(f"Primary Intent:    {annotation['primary_intent']}")
    print(f"Secondary Intent:  {annotation['secondary_intent']}")
    print(f"Escalate:          {annotation['escalate']}")
    print(f"Escalation Reason: {annotation['escalate_reason']}")
    print(f"Language Flag:     {annotation['language_flag']}")
    print(f"Ambiguity Flag:    {annotation['ambiguity_flag']}")
    print(f"Notes:             {annotation['annotator_notes'] or '(None)'}")


def run_review_flagged_pass(labels):
    """Pass for reviewing and labeling flagged examples."""
    flagged_indices = [
        i for i, r in enumerate(labels)
        if r.get("primary_intent") is None and r.get("annotator_notes") == "FLAGGED FOR REVIEW"
    ]
    if not flagged_indices:
        print("\nNo flagged examples found to review.")
        return

    print("\n" + "=" * 80)
    print(f"REVIEWING {len(flagged_indices)} FLAGGED EXAMPLE(S)")
    print("=" * 80)

    for idx, f_idx in enumerate(flagged_indices):
        rec = labels[f_idx]
        display_example(rec, f_idx, len(labels))

        action = input("\nReview options: (l)abel now, (s)kip for later, (q)uit review: ").strip().lower()
        if action in ['q', 'quit']:
            print("Exiting flagged review pass.")
            break
        elif action in ['s', 'skip']:
            continue

        annotation = collect_annotation()
        show_review(annotation)

        save_confirm = input("\nSave this annotation? [Y/n]: ").strip().lower()
        if save_confirm in ['', 'y', 'yes']:
            for key, val in annotation.items():
                rec[key] = val
            save_labels(labels)
            print(f"SUCCESS: Saved annotation for {rec['example_id']}. Item is no longer flagged.")
            generate_report(labels)


def print_session_summary(labels):
    """Print final session summary with full stats."""
    report = generate_report(labels)
    print("\n" + "=" * 80)
    print("SESSION SUMMARY")
    print("=" * 80)
    print(f"  Total examples:     {report['total_examples']}")
    print(f"  Completed:          {report['completed_count']}")
    print(f"  Flagged for review: {report['flagged_count']}")
    print(f"  Remaining:          {report['remaining_count']}")
    print(f"\n  Escalation count:   {report['escalation_count']}")
    print(f"  Ambiguity count:    {report['ambiguity_count']}")
    print(f"  Non-English count:  {report['non_english_count']}")
    print(f"\n  Intent distribution:")
    for intent, count in sorted(report.get("primary_intent_distribution", {}).items()):
        print(f"    {intent}: {count}")
    print(f"\n  Report saved to: {GOLDEN_REPORT_PATH}")
    print("=" * 80)


def run_golden_annotation(auto_start=False):
    """Main annotation session for the Golden 200 set."""
    print("=" * 80)
    print("GOLDEN SET HUMAN ANNOTATION CLI")
    print("200 Examples | Zero-Hint | Ground-Truth Labeling")
    print("=" * 80)

    print("\nInitializing...")
    labels = init_golden_labels_file()

    completed_cnt = sum(1 for r in labels if r.get("primary_intent") is not None)
    flagged_cnt = sum(1 for r in labels if r.get("primary_intent") is None and r.get("annotator_notes") == "FLAGGED FOR REVIEW")
    remaining_cnt = len(labels) - completed_cnt - flagged_cnt

    print(TAXONOMY_CHEAT_SHEET)
    print(ESCALATION_GUIDANCE)
    print(f"Loaded {len(labels)} Golden examples.")
    print(f"  Completed         : {completed_cnt}")
    print(f"  Flagged for review: {flagged_cnt}")
    print(f"  Remaining         : {remaining_cnt}")

    if not auto_start:
        print("\nSession initialized cleanly. Run with auto_start=True to begin annotation.")
        return labels

    # Find first unprocessed example
    curr_idx = 0
    for i, r in enumerate(labels):
        if r.get("primary_intent") is None and r.get("annotator_notes") != "FLAGGED FOR REVIEW":
            curr_idx = i
            break
    else:
        # All examples are either completed or flagged
        for i, r in enumerate(labels):
            if r.get("primary_intent") is None:
                curr_idx = i
                break
        else:
            print("\nAll 200 Golden examples are already annotated!")
            print_session_summary(labels)
            return labels

    try:
        while 0 <= curr_idx < len(labels):
            rec = labels[curr_idx]
            total = len(labels)

            display_example(rec, curr_idx, total)
            print_progress(labels)

            # Menu options
            menu_action = input(
                "\nOptions: (c)ontinue/label, (f)lag and continue, (p)rev, "
                "(j)ump to #, (r)eview flagged, (s)ummary, (q)uit: "
            ).strip().lower()

            if menu_action in ['q', 'quit']:
                print("\nExiting annotation tool. All progress saved.")
                break

            elif menu_action in ['p', 'prev', 'previous']:
                curr_idx = max(0, curr_idx - 1)
                continue

            elif menu_action in ['j', 'jump']:
                jump_val = input("Jump to example # [1-200]: ").strip()
                if jump_val.isdigit():
                    j = int(jump_val)
                    if 1 <= j <= 200:
                        curr_idx = j - 1
                        continue
                print("Invalid example number.")
                continue

            elif menu_action in ['f', 'flag']:
                rec["primary_intent"] = None
                rec["secondary_intent"] = None
                rec["escalate"] = None
                rec["escalate_reason"] = None
                rec["language_flag"] = None
                rec["ambiguity_flag"] = None
                rec["annotator_notes"] = "FLAGGED FOR REVIEW"
                save_labels(labels)
                generate_report(labels)
                print(f"FLAGGED: Saved record {rec['example_id']} as 'FLAGGED FOR REVIEW'.")
                curr_idx += 1
                continue

            elif menu_action in ['r', 'review', 'review flagged']:
                run_review_flagged_pass(labels)
                generate_report(labels)
                continue

            elif menu_action in ['s', 'summary']:
                print_session_summary(labels)
                continue

            elif menu_action not in ['c', 'continue', 'label', 'l', '']:
                print("Unknown option. Use (c)ontinue, (f)lag, (p)rev, (j)ump, (r)eview, (s)ummary, or (q)uit.")
                continue

            # Collect annotation
            annotation = collect_annotation()
            show_review(annotation)

            # Confirm save
            save_confirm = input(
                "\nSave options: [Y]es / (f)lag and continue / (r)e-annotate / (p)rev / (q)uit: "
            ).strip().lower()

            if save_confirm in ['', 'y', 'yes']:
                for key, val in annotation.items():
                    rec[key] = val
                save_labels(labels)
                print(f"SUCCESS: Saved annotation for {rec['example_id']}.")
                generate_report(labels)
                curr_idx += 1

            elif save_confirm in ['f', 'flag']:
                rec["primary_intent"] = None
                rec["secondary_intent"] = None
                rec["escalate"] = None
                rec["escalate_reason"] = None
                rec["language_flag"] = None
                rec["ambiguity_flag"] = None
                rec["annotator_notes"] = "FLAGGED FOR REVIEW"
                save_labels(labels)
                generate_report(labels)
                print(f"FLAGGED: Saved record {rec['example_id']} as 'FLAGGED FOR REVIEW'.")
                curr_idx += 1

            elif save_confirm in ['r', 're-annotate', 'redo']:
                print("Annotation discarded. Re-annotating current example.")
                continue

            elif save_confirm in ['p', 'prev', 'previous']:
                curr_idx = max(0, curr_idx - 1)
                continue

            elif save_confirm in ['q', 'quit']:
                print("\nExiting annotation tool. All progress saved.")
                break

            else:
                print("Annotation discarded. Re-annotating current example.")
                continue

    except KeyboardInterrupt:
        print("\n\nAnnotation session paused via Ctrl+C. All progress preserved.")

    # Final summary
    print_session_summary(labels)

    completed_final = sum(1 for r in labels if r.get("primary_intent") is not None)
    if completed_final == len(labels):
        print("\n" + "=" * 80)
        print("ALL 200 GOLDEN EXAMPLES ANNOTATED!")
        print("The Golden human labels file is ready for evaluation.")
        print("=" * 80)

    return labels


if __name__ == "__main__":
    run_golden_annotation(auto_start=True)

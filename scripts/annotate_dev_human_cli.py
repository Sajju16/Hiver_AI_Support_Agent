"""
scripts/annotate_dev_human_cli.py — Interactive Human Cold-Labeling Tool for Development Set

Provides an unbiased, zero-hint CLI interface for human cold-labeling of the 50 Dev examples.
Enforces data safety, instant per-example auto-saving, annotation confirmation review,
flag-and-continue workflow for ambiguous examples, strict input validation, zero-skip safety,
and report generation upon completion.
"""

import sys, json, hashlib
from pathlib import Path
from datetime import datetime, timezone

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEV_CANDIDATES_PATH = PROJECT_ROOT / "data" / "dev" / "dev_candidates_50.json"
DEV_HUMAN_LABELS_PATH = PROJECT_ROOT / "data" / "dev" / "dev_human_labels_50.json"
DEV_REPORT_PATH = PROJECT_ROOT / "data" / "dev" / "dev_human_annotation_report.json"
GOLDEN_PATH = PROJECT_ROOT / "data" / "golden" / "golden_candidates_200.json"

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

def verify_golden_untouched():
    if not GOLDEN_PATH.exists():
        raise FileNotFoundError(f"Golden set file missing: {GOLDEN_PATH}")
    with open(GOLDEN_PATH, "rb") as f:
        computed_hash = hashlib.sha256(f.read()).hexdigest().lower()
    assert computed_hash == EXPECTED_GOLDEN_SHA256, f"GOLDEN SET CHECKSUM MISMATCH! Computed: {computed_hash}, Expected: {EXPECTED_GOLDEN_SHA256}"
    return computed_hash

def init_human_labels_file():
    """
    Initializes or loads data/dev/dev_human_labels_50.json without modifying dev_candidates_50.json.
    """
    verify_golden_untouched()
    
    if not DEV_CANDIDATES_PATH.exists():
        raise FileNotFoundError(f"Source candidate file missing: {DEV_CANDIDATES_PATH}")
        
    with open(DEV_CANDIDATES_PATH, "r", encoding="utf-8") as f:
        candidates = json.load(f)

    if DEV_HUMAN_LABELS_PATH.exists():
        with open(DEV_HUMAN_LABELS_PATH, "r", encoding="utf-8") as f:
            existing = json.load(f)
        if len(existing) == len(candidates):
            return existing, candidates

    gt_fields = ["primary_intent", "secondary_intent", "escalate", "escalate_reason", "language_flag", "ambiguity_flag", "annotator_notes"]
    human_queue = []
    for c in candidates:
        rec = {
            "example_id": c["example_id"],
            "conversation_id": c["conversation_id"],
            "turn_index": c["turn_index"],
            "raw_text": c["raw_text"],
            "thread_context": c.get("thread_context", []),
            "candidate_bucket": c.get("candidate_bucket"),
            "candidate_intent_hint": c.get("candidate_intent_hint")
        }
        for fld in gt_fields:
            rec[fld] = None
        human_queue.append(rec)

    DEV_HUMAN_LABELS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DEV_HUMAN_LABELS_PATH, "w", encoding="utf-8") as f:
        json.dump(human_queue, f, indent=2, ensure_ascii=False)

    return human_queue, candidates

def save_single_annotation(human_queue):
    """Saves updated queue to data/dev/dev_human_labels_50.json instantly."""
    with open(DEV_HUMAN_LABELS_PATH, "w", encoding="utf-8") as f:
        json.dump(human_queue, f, indent=2, ensure_ascii=False)

def generate_completion_report(human_queue):
    completed = [r for r in human_queue if r.get("primary_intent") is not None]
    flagged = [r for r in human_queue if r.get("primary_intent") is None and r.get("annotator_notes") == "FLAGGED FOR REVIEW"]
    remaining = [r for r in human_queue if r.get("primary_intent") is None and r.get("annotator_notes") != "FLAGGED FOR REVIEW"]
    
    intent_counts = {}
    escalate_count = sum(1 for r in completed if r.get("escalate") is True)
    ambiguity_count = sum(1 for r in completed if r.get("ambiguity_flag") is True)
    non_en_count = sum(1 for r in completed if r.get("language_flag") is True)

    for r in completed:
        p = r["primary_intent"]
        intent_counts[p] = intent_counts.get(p, 0) + 1

    report = {
        "total_examples": len(human_queue),
        "completed_count": len(completed),
        "flagged_count": len(flagged),
        "remaining_count": len(remaining),
        "primary_intent_distribution": intent_counts,
        "escalation_count": escalate_count,
        "ambiguity_count": ambiguity_count,
        "non_english_count": non_en_count,
        "timestamp_utc": datetime.now(timezone.utc).isoformat()
    }

    with open(DEV_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    return report

def prompt_primary_intent():
    """Prompts for Primary Intent, accepting ONLY integer 1-11."""
    while True:
        val = input("\nPrimary Intent [1-11]: ").strip()
        if val.isdigit():
            num = int(val)
            if 1 <= num <= 11:
                return INTENT_MAP[num]
        print("ERROR: Invalid input. Primary Intent must be an integer between 1 and 11.")

def run_review_flagged_pass(human_queue):
    """Pass for reviewing and labeling flagged examples."""
    flagged_indices = [i for i, r in enumerate(human_queue) if r.get("primary_intent") is None and r.get("annotator_notes") == "FLAGGED FOR REVIEW"]
    if not flagged_indices:
        print("\nNo flagged examples found to review.")
        return

    print("\n" + "="*80)
    print(f"REVIEWING {len(flagged_indices)} FLAGGED EXAMPLE(S)")
    print("="*80)

    for idx, f_idx in enumerate(flagged_indices):
        rec = human_queue[f_idx]
        print("\n" + "="*80)
        print(f"FLAGGED ITEM {idx + 1} / {len(flagged_indices)}  (ID: {rec['example_id']} | Convo: {rec['conversation_id']} | Turn: {rec['turn_index']})")
        print("="*80)

        print("\nCUSTOMER MESSAGE:")
        print(f"  {rec['raw_text']}")

        print("\nPREVIOUS THREAD CONTEXT:")
        ctx = rec.get("thread_context", [])
        if ctx:
            for t_i, turn in enumerate(ctx):
                print(f"  [{t_i+1}] {turn.get('author', 'User')}: {turn.get('text', '')}")
        else:
            print("  (None — Standalone Customer Turn)")

        action = input("\nReview options: (l)abel now, (s)kip for later, (q)uit review: ").strip().lower()
        if action in ['q', 'quit']:
            print("Exiting flagged review pass.")
            break
        elif action in ['s', 'skip']:
            continue

        p_intent = prompt_primary_intent()

        sec_val = input("Secondary Intent [1-11, or Enter for none]: ").strip()
        s_intent = None
        if sec_val.isdigit() and 1 <= int(sec_val) <= 11:
            s_intent = INTENT_MAP[int(sec_val)]

        esc_val = input("Escalate? [y/N, default=n]: ").strip().lower()
        is_esc = esc_val.startswith('y')
        esc_reason = ""
        if is_esc:
            while not esc_reason:
                esc_reason = input("Escalation Reason [Required]: ").strip()

        lang_val = input("Language flag (Non-English)? [y/N, default=n]: ").strip().lower()
        is_lang = lang_val.startswith('y')

        amb_val = input("Ambiguity flag? [y/N, default=n]: ").strip().lower()
        is_amb = amb_val.startswith('y')

        notes = input("Annotator Notes [optional]: ").strip()

        print("\n--------------------------------")
        print("Review annotation")
        print("--------------------------------")
        print(f"Primary Intent:    {p_intent}")
        print(f"Secondary Intent:  {s_intent}")
        print(f"Escalate:          {is_esc}")
        print(f"Escalation Reason: {esc_reason}")
        print(f"Language Flag:     {is_lang}")
        print(f"Ambiguity Flag:    {is_amb}")
        print(f"Notes:             {notes if notes else '(None)'}")

        save_confirm = input("\nSave this annotation? [Y/n]: ").strip().lower()
        if save_confirm in ['', 'y', 'yes']:
            rec["primary_intent"] = p_intent
            rec["secondary_intent"] = s_intent
            rec["escalate"] = is_esc
            rec["escalate_reason"] = esc_reason
            rec["language_flag"] = is_lang
            rec["ambiguity_flag"] = is_amb
            rec["annotator_notes"] = notes if notes else None

            save_single_annotation(human_queue)
            print(f"SUCCESS: Saved annotation for {rec['example_id']}. Item is no longer flagged.")

def run_labeling_session(auto_start=False):
    print("Initializing Human Cold-Labeling CLI Tool...", flush=True)
    human_queue, source_candidates = init_human_labels_file()

    completed_cnt = sum(1 for r in human_queue if r.get('primary_intent') is not None)
    flagged_cnt = sum(1 for r in human_queue if r.get('primary_intent') is None and r.get('annotator_notes') == "FLAGGED FOR REVIEW")
    remaining_cnt = sum(1 for r in human_queue if r.get('primary_intent') is None and r.get('annotator_notes') != "FLAGGED FOR REVIEW")

    curr_idx = 0
    for i, r in enumerate(human_queue):
        if r.get("primary_intent") is None and r.get("annotator_notes") != "FLAGGED FOR REVIEW":
            curr_idx = i
            break
    else:
        for i, r in enumerate(human_queue):
            if r.get("primary_intent") is None:
                curr_idx = i
                break

    print(TAXONOMY_CHEAT_SHEET)
    print(f"Loaded {len(human_queue)} Dev examples.")
    print(f"  Completed         : {completed_cnt}")
    print(f"  Flagged for review: {flagged_cnt}")
    print(f"  Remaining         : {remaining_cnt}")
    
    if not auto_start:
        print("\nSession initialized cleanly. Run python scripts/annotate_dev_human_cli.py to begin.")
        return human_queue

    try:
        while 0 <= curr_idx < len(human_queue):
            rec = human_queue[curr_idx]
            total = len(human_queue)

            print("\n" + "="*80)
            is_flagged = rec.get("primary_intent") is None and rec.get("annotator_notes") == "FLAGGED FOR REVIEW"
            status_str = "FLAGGED FOR REVIEW" if is_flagged else ("COMPLETED" if rec.get("primary_intent") else "UNPROCESSED")
            print(f"EXAMPLE {curr_idx + 1} / {total}  [{status_str}]  (ID: {rec['example_id']} | Convo: {rec['conversation_id']} | Turn: {rec['turn_index']})")
            print("="*80)

            # STRICT ISOLATION: Display ONLY customer message and thread context.
            print("\nCUSTOMER MESSAGE:")
            print(f"  {rec['raw_text']}")

            print("\nPREVIOUS THREAD CONTEXT:")
            ctx = rec.get("thread_context", [])
            if ctx:
                for t_i, turn in enumerate(ctx):
                    print(f"  [{t_i+1}] {turn.get('author', 'User')}: {turn.get('text', '')}")
            else:
                print("  (None — Standalone Customer Turn)")

            print("-" * 80)
            if rec.get("primary_intent"):
                print(f"[Saved Label: {rec['primary_intent']} | Escalate: {rec['escalate']} | Lang: {rec['language_flag']} | Amb: {rec['ambiguity_flag']}]")
                print("-" * 80)
            elif is_flagged:
                print("[Status: FLAGGED FOR REVIEW]")
                print("-" * 80)

            # Menu options between examples
            menu_action = input("\nOptions: (c)ontinue/label, (f)lag and continue, (p)rev edit, (r)eview flagged, (q)uit: ").strip().lower()
            if menu_action in ['q', 'quit']:
                print("\nExiting annotation tool. All progress saved.")
                break
            elif menu_action in ['p', 'prev', 'previous']:
                curr_idx = max(0, curr_idx - 1)
                continue
            elif menu_action in ['f', 'flag']:
                rec["primary_intent"] = None
                rec["secondary_intent"] = None
                rec["escalate"] = None
                rec["escalate_reason"] = None
                rec["language_flag"] = None
                rec["ambiguity_flag"] = None
                rec["annotator_notes"] = "FLAGGED FOR REVIEW"
                save_single_annotation(human_queue)
                generate_completion_report(human_queue)
                print(f"FLAGGED: Saved record {rec['example_id']} as 'FLAGGED FOR REVIEW'.")
                curr_idx += 1
                continue
            elif menu_action in ['r', 'review', 'review flagged']:
                run_review_flagged_pass(human_queue)
                generate_completion_report(human_queue)
                continue

            # 1. Primary Intent (STRICT: ONLY 1-11 accepted)
            p_intent = prompt_primary_intent()

            # 2. Secondary Intent
            sec_val = input("Secondary Intent [1-11, or Enter for none]: ").strip()
            s_intent = None
            if sec_val.isdigit() and 1 <= int(sec_val) <= 11:
                s_intent = INTENT_MAP[int(sec_val)]

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

            # REVIEW ANNOTATION STEP
            print("\n--------------------------------")
            print("Review annotation")
            print("--------------------------------")
            print(f"Primary Intent:    {p_intent}")
            print(f"Secondary Intent:  {s_intent}")
            print(f"Escalate:          {is_esc}")
            print(f"Escalation Reason: {esc_reason}")
            print(f"Language Flag:     {is_lang}")
            print(f"Ambiguity Flag:    {is_amb}")
            print(f"Notes:             {notes if notes else '(None)'}")

            save_confirm = input("\nSave options: [Y]es / (f)lag and continue / (p)rev edit / (q)uit: ").strip().lower()
            if save_confirm in ['', 'y', 'yes']:
                rec["primary_intent"] = p_intent
                rec["secondary_intent"] = s_intent
                rec["escalate"] = is_esc
                rec["escalate_reason"] = esc_reason
                rec["language_flag"] = is_lang
                rec["ambiguity_flag"] = is_amb
                rec["annotator_notes"] = notes if notes else None

                save_single_annotation(human_queue)
                print(f"SUCCESS: Saved annotation for {rec['example_id']}.")
                generate_completion_report(human_queue)
                curr_idx += 1
            elif save_confirm in ['f', 'flag']:
                rec["primary_intent"] = None
                rec["secondary_intent"] = None
                rec["escalate"] = None
                rec["escalate_reason"] = None
                rec["language_flag"] = None
                rec["ambiguity_flag"] = None
                rec["annotator_notes"] = "FLAGGED FOR REVIEW"
                save_single_annotation(human_queue)
                generate_completion_report(human_queue)
                print(f"FLAGGED: Saved record {rec['example_id']} as 'FLAGGED FOR REVIEW'.")
                curr_idx += 1
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

    completed_final = sum(1 for r in human_queue if r.get('primary_intent') is not None)
    flagged_final = sum(1 for r in human_queue if r.get('primary_intent') is None and r.get('annotator_notes') == "FLAGGED FOR REVIEW")
    
    if completed_final == len(human_queue):
        print("\n" + "="*80)
        print("ALL 50 DEV EXAMPLES ANNOTATED!")
        print("="*80)
    elif completed_final + flagged_final == len(human_queue):
        print("\n" + "="*80)
        print(f"ALL 50 DEV EXAMPLES PROCESSED ({completed_final} Completed, {flagged_final} Flagged for Review)!")
        print("Use option (r)eview flagged to resolve flagged examples.")
        print("="*80)

    report = generate_completion_report(human_queue)
    print(f"Report saved to {DEV_REPORT_PATH}")

    return human_queue

if __name__ == "__main__":
    run_labeling_session(auto_start=True)

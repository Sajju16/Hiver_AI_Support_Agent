"""
scripts/review_golden_ai_annotations.py — Human Review of AI-Predicted Golden Annotations

Interactive CLI that presents AI predictions for human accept/edit/flag workflow.
Saves final verified annotations to data/golden/golden_human_verified_labels_200.json.

Review priority order:
1. B2 confusing cases
2. B3 escalation cases
3. Low-confidence AI predictions
4. Classifier/retrieval disagreement
5. B4 non-English
6. B5 Other/noise/edge cases
7. Remaining B1 examples

Batch-accept mode:
- Only B1_core examples with confidence >= 0.20, ambiguity_flag == False,
  and no escalation trigger are eligible.
- B2, B3, B4, B5, low-confidence, and escalation cases are NEVER batch-accepted.
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
AI_PREDICTIONS_PATH = PROJECT_ROOT / "data" / "golden" / "golden_ai_predictions_200.json"
VERIFIED_LABELS_PATH = PROJECT_ROOT / "data" / "golden" / "golden_human_verified_labels_200.json"
QUALITY_REPORT_PATH = PROJECT_ROOT / "data" / "golden" / "golden_annotation_quality_report.json"

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
    11: "Other_Unclassified_Inquiry",
}

TAXONOMY_CHEAT = """\
 1. Delivery_Tracking_And_Delays     : ETA, tracking, delay, late delivery
 2. Technical_App_And_Website_Issues : Website/app glitches, login, cart error
 3. Prime_Subscription_And_Digital   : Prime, Video, Kindle, Alexa, Music
 4. Refund_Status_And_Billing        : Refund status, double charge, dispute
 5. Return_Exchange_And_Pickup       : Return process, label, pickup, exchange
 6. Order_Cancellation_And_Address   : Cancel order, change address
 7. Damaged_Defective_Or_Wrong_Item  : Broken, defective, wrong item
 8. General_Service_Complaint_Escal  : Rep complaint, manager demand
 9. Promotions_GiftCards_And_Pricing : Gift card, promo, discount, price
10. Marked_Delivered_Not_Received    : Tracking=delivered but missing/stolen
11. Other_Unclassified_Inquiry       : Banter, memes, praise, link-only"""


def verify_checksum():
    with open(GOLDEN_CANDIDATES_PATH, "rb") as f:
        computed = hashlib.sha256(f.read()).hexdigest().lower()
    assert computed == EXPECTED_GOLDEN_SHA256, f"CHECKSUM MISMATCH: {computed}"
    return computed


def build_priority_order(predictions, candidates):
    """Build review priority: B2 > B3 > low-conf > disagreement > B4 > B5 > B1."""
    # Build bucket lookup from candidates (not shown to reviewer, only for ordering)
    bucket_map = {}
    for c in candidates:
        bucket_map[c["example_id"]] = c.get("candidate_bucket", "B1_core")

    # Categorize indices
    b2, b3, low_conf, disagree, b4, b5, b1 = [], [], [], [], [], [], []

    for idx, pred in enumerate(predictions):
        eid = pred["example_id"]
        bucket = bucket_map.get(eid, "B1_core")
        conf = pred["ai_prediction"]["confidence"]
        ai_intent = pred["ai_prediction"]["primary_intent"]
        retr_cat = pred.get("retrieval_evidence", {}).get("matched_category", "")

        # Classify by priority
        if "B2" in bucket:
            b2.append(idx)
        elif "B3" in bucket:
            b3.append(idx)
        elif conf < 0.3:
            low_conf.append(idx)
        elif retr_cat and retr_cat.lower() not in ai_intent.lower() and not pred.get("retrieval_evidence", {}).get("is_fallback", True):
            disagree.append(idx)
        elif "B4" in bucket:
            b4.append(idx)
        elif "B5" in bucket:
            b5.append(idx)
        else:
            b1.append(idx)

    priority = b2 + b3 + low_conf + disagree + b4 + b5 + b1
    # Ensure all indices present
    all_idx = set(range(len(predictions)))
    remaining = sorted(all_idx - set(priority))
    priority.extend(remaining)

    return priority


def init_verified_labels(predictions):
    """Initialize or load the verified labels file."""
    if VERIFIED_LABELS_PATH.exists():
        with open(VERIFIED_LABELS_PATH, "r", encoding="utf-8") as f:
            existing = json.load(f)
        if len(existing) == len(predictions):
            # Verify alignment
            if all(existing[i]["example_id"] == predictions[i]["example_id"] for i in range(len(predictions))):
                print(f"Resuming from existing verified labels ({VERIFIED_LABELS_PATH.name})")
                return existing

    # Create fresh from predictions
    labels = []
    for pred in predictions:
        rec = {
            "example_id": pred["example_id"],
            "conversation_id": pred["conversation_id"],
            "turn_index": pred["turn_index"],
            "raw_text": pred["raw_text"],
            "thread_context": pred.get("thread_context", []),
            # Ground-truth fields (initially from AI, pending verification)
            "primary_intent": None,
            "secondary_intent": None,
            "escalate": None,
            "escalate_reason": None,
            "language_flag": None,
            "ambiguity_flag": None,
            "annotator_notes": None,
            # Provenance
            "annotation_source": "AI_ASSISTED_HUMAN_VERIFIED",
            "ai_prediction": copy.deepcopy(pred["ai_prediction"]),
            "human_verified": False,
            "human_changed_prediction": False,
        }
        labels.append(rec)

    save_labels(labels)
    return labels


def save_labels(labels):
    VERIFIED_LABELS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(VERIFIED_LABELS_PATH, "w", encoding="utf-8") as f:
        json.dump(labels, f, indent=2, ensure_ascii=False)


def generate_quality_report(labels):
    """Generate quality report for annotation review progress."""
    total = len(labels)
    verified = [r for r in labels if r.get("human_verified")]
    changed = [r for r in labels if r.get("human_changed_prediction")]
    flagged = [r for r in labels if r.get("annotator_notes") == "FLAGGED FOR REVIEW" and not r.get("human_verified")]
    unverified = [r for r in labels if not r.get("human_verified") and r.get("annotator_notes") != "FLAGGED FOR REVIEW"]

    # Per-intent agreement
    per_intent_agreement = {}
    per_intent_total = {}
    escalation_agree = 0
    escalation_total = 0

    for r in verified:
        ai_intent = r["ai_prediction"]["primary_intent"]
        human_intent = r["primary_intent"]
        per_intent_total[ai_intent] = per_intent_total.get(ai_intent, 0) + 1
        if ai_intent == human_intent:
            per_intent_agreement[ai_intent] = per_intent_agreement.get(ai_intent, 0) + 1

        ai_esc = r["ai_prediction"].get("escalate", False)
        human_esc = r.get("escalate", False)
        escalation_total += 1
        if ai_esc == human_esc:
            escalation_agree += 1

    intent_agreement_rates = {}
    for intent, count in per_intent_total.items():
        agreed = per_intent_agreement.get(intent, 0)
        intent_agreement_rates[intent] = {
            "total": count,
            "agreed": agreed,
            "rate": round(agreed / count, 4) if count > 0 else 0.0,
        }

    overall_agreement = 0
    if verified:
        overall_agreement = sum(
            1 for r in verified if r["primary_intent"] == r["ai_prediction"]["primary_intent"]
        )

    avg_confidence = 0.0
    if labels:
        avg_confidence = round(
            sum(r["ai_prediction"]["confidence"] for r in labels) / len(labels), 4
        )

    # Intent distribution of verified labels
    intent_dist = {}
    for r in verified:
        p = r["primary_intent"]
        if p:
            intent_dist[p] = intent_dist.get(p, 0) + 1

    batch_accepted = sum(1 for r in verified if r.get("verification_method") == "BATCH_ACCEPT_HIGH_CONFIDENCE")
    individually_reviewed = sum(1 for r in verified if r.get("verification_method") != "BATCH_ACCEPT_HIGH_CONFIDENCE")

    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "total_examples": total,
        "ai_predictions_completed": total,
        "human_verified_count": len(verified),
        "human_changed_count": len(changed),
        "flagged_count": len(flagged),
        "unverified_count": len(unverified),
        "batch_accepted_count": batch_accepted,
        "individually_reviewed_count": individually_reviewed,
        "agreement_rate": round(overall_agreement / len(verified), 4) if verified else 0.0,
        "per_intent_agreement": dict(sorted(intent_agreement_rates.items())),
        "escalation_agreement": {
            "total_verified": escalation_total,
            "agreed": escalation_agree,
            "rate": round(escalation_agree / escalation_total, 4) if escalation_total > 0 else 0.0,
        },
        "average_ai_confidence": avg_confidence,
        "verified_intent_distribution": dict(sorted(intent_dist.items())),
        "escalation_count": sum(1 for r in verified if r.get("escalate")),
        "ambiguity_count": sum(1 for r in verified if r.get("ambiguity_flag")),
        "non_english_count": sum(1 for r in verified if r.get("language_flag")),
    }

    with open(QUALITY_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    return report


def prompt_primary_intent():
    """Numeric-only primary intent selection."""
    while True:
        val = input("\nPrimary Intent [1-11]: ").strip()
        if val.isdigit():
            num = int(val)
            if 1 <= num <= 11:
                chosen = INTENT_MAP[num]
                print(f"  -> {chosen}")
                return chosen
        print("ERROR: Must be 1-11.")


def display_for_review(rec, idx, total, priority_label=""):
    """Display example with AI prediction for human review."""
    verified = rec.get("human_verified", False)
    flagged = rec.get("annotator_notes") == "FLAGGED FOR REVIEW" and not verified
    status = "VERIFIED" if verified else ("FLAGGED" if flagged else "PENDING")
    ai = rec["ai_prediction"]

    print("\n" + "=" * 80)
    print(f"EXAMPLE {idx + 1}/200  [{status}]  ID: {rec['example_id']}  {priority_label}")
    print("=" * 80)

    # Customer message
    print("\nCUSTOMER MESSAGE:")
    print(f"  {rec['raw_text']}")

    # Thread context
    ctx = rec.get("thread_context", [])
    if ctx:
        print("\nTHREAD CONTEXT:")
        for t_i, turn in enumerate(ctx):
            author = turn.get("author", "User")
            text = turn.get("text", "")
            print(f"  [{t_i + 1}] {author}: {text}")

    # AI Prediction
    print("\n" + "-" * 40)
    print("AI PREDICTION:")
    print(f"  Intent:      {ai['primary_intent']}")
    print(f"  Confidence:  {ai['confidence']:.4f}")
    if ai.get("secondary_intent"):
        print(f"  2nd Intent:  {ai['secondary_intent']} ({ai.get('top2_confidence', 0):.4f})")
    print(f"  Escalate:    {ai['escalate']}")
    if ai["escalate"]:
        print(f"  Esc Reason:  {ai['escalation_reason']}")
    print(f"  Language:    {'NON-ENGLISH' if ai['language_flag'] else 'English'}")
    print(f"  Ambiguity:   {ai['ambiguity_flag']}")
    print(f"  Reasoning:   {ai['reasoning']}")
    print("-" * 40)

    if verified:
        print(f"\n  [VERIFIED] Intent: {rec['primary_intent']} | Changed: {rec['human_changed_prediction']}")


def accept_prediction(rec, verification_method="INDIVIDUAL_REVIEW"):
    """Accept AI prediction as ground truth."""
    ai = rec["ai_prediction"]
    rec["primary_intent"] = ai["primary_intent"]
    rec["secondary_intent"] = ai.get("secondary_intent")
    rec["escalate"] = ai["escalate"]
    rec["escalate_reason"] = ai.get("escalation_reason", "")
    rec["language_flag"] = ai["language_flag"]
    rec["ambiguity_flag"] = ai["ambiguity_flag"]
    rec["annotation_source"] = "AI_ASSISTED_HUMAN_VERIFIED"
    rec["human_verified"] = True
    rec["human_changed_prediction"] = False
    rec["verification_method"] = verification_method
    if verification_method == "BATCH_ACCEPT_HIGH_CONFIDENCE":
        rec["annotator_notes"] = "Batch-accepted: B1 core, conf>=0.20, no ambiguity, no escalation"
    else:
        rec["annotator_notes"] = "Accepted AI prediction"


def is_batch_eligible(rec, bucket):
    """Check if an example is eligible for batch-accept.

    Eligible only if ALL of these are true:
    - Bucket is B1_core
    - AI confidence >= 0.20
    - ambiguity_flag == False
    - No escalation trigger (escalate == False)
    - Not already verified or flagged

    Never batch-accept B2, B3, B4, B5, low-confidence, or escalation cases.
    """
    if rec.get("human_verified"):
        return False
    if rec.get("annotator_notes") == "FLAGGED FOR REVIEW":
        return False
    if "B1" not in bucket:
        return False  # Excludes B2, B3, B4, B5
    ai = rec["ai_prediction"]
    if ai["confidence"] < 0.20:
        return False
    if ai["ambiguity_flag"]:
        return False
    if ai["escalate"]:
        return False
    return True


def run_batch_accept(labels, bucket_map):
    """Find and batch-accept all eligible B1 high-confidence examples.

    Returns the count of batch-accepted examples.
    """
    eligible = []
    for idx, rec in enumerate(labels):
        bucket = bucket_map.get(rec["example_id"], "B1_core")
        if is_batch_eligible(rec, bucket):
            eligible.append((idx, rec))

    if not eligible:
        print("\n  No examples eligible for batch-accept.")
        print("  Criteria: B1_core, confidence >= 0.20, no ambiguity, no escalation.")
        return 0

    # Show summary before confirming
    print(f"\n{'=' * 60}")
    print(f"BATCH ACCEPT: {len(eligible)} eligible B1 examples found")
    print(f"{'=' * 60}")
    print(f"  Bucket:        B1_core only")
    print(f"  Confidence:    >= 0.20")
    print(f"  Ambiguity:     False")
    print(f"  Escalation:    False")

    # Show intent distribution of eligible examples
    intent_dist = {}
    confs = []
    for _, rec in eligible:
        ai_intent = rec["ai_prediction"]["primary_intent"]
        intent_dist[ai_intent] = intent_dist.get(ai_intent, 0) + 1
        confs.append(rec["ai_prediction"]["confidence"])

    print(f"\n  Intent distribution:")
    for intent, count in sorted(intent_dist.items()):
        print(f"    {intent}: {count}")

    if confs:
        print(f"\n  Confidence range: {min(confs):.4f} - {max(confs):.4f}")
        print(f"  Average confidence: {sum(confs)/len(confs):.4f}")

    # Show a few sample examples
    print(f"\n  Sample examples:")
    for i, (idx, rec) in enumerate(eligible[:5]):
        ai = rec["ai_prediction"]
        text_preview = rec["raw_text"][:80] + ("..." if len(rec["raw_text"]) > 80 else "")
        print(f"    {rec['example_id']}: {ai['primary_intent']} (conf={ai['confidence']:.4f})")
        print(f"      {text_preview}")
    if len(eligible) > 5:
        print(f"    ... and {len(eligible) - 5} more")

    confirm = input(f"\nBatch-accept all {len(eligible)} examples? [y/N]: ").strip().lower()
    if confirm not in ["y", "yes"]:
        print("  Batch-accept cancelled.")
        return 0

    # Execute batch accept
    count = 0
    for idx, rec in eligible:
        accept_prediction(rec, verification_method="BATCH_ACCEPT_HIGH_CONFIDENCE")
        count += 1

    save_labels(labels)
    print(f"\n  BATCH ACCEPTED: {count} examples")
    return count


def edit_prediction(rec):
    """Let human edit the AI prediction."""
    ai = rec["ai_prediction"]
    print(f"\n  Current AI intent: {ai['primary_intent']}")
    print(TAXONOMY_CHEAT)

    p_intent = prompt_primary_intent()

    sec_val = input("Secondary Intent [1-11, or Enter for none]: ").strip()
    s_intent = None
    if sec_val.isdigit() and 1 <= int(sec_val) <= 11:
        s_intent = INTENT_MAP[int(sec_val)]

    print(f"\n  AI escalation: {ai['escalate']}")
    esc_val = input("Escalate? [y/N]: ").strip().lower()
    is_esc = esc_val.startswith("y")
    esc_reason = ""
    if is_esc:
        while not esc_reason:
            esc_reason = input("Escalation Reason [Required]: ").strip()

    lang_val = input("Language flag (Non-English)? [y/N]: ").strip().lower()
    is_lang = lang_val.startswith("y")

    amb_val = input("Ambiguity flag? [y/N]: ").strip().lower()
    is_amb = amb_val.startswith("y")

    notes = input("Annotator Notes [optional]: ").strip()

    # Review
    print("\n" + "-" * 40)
    print("REVIEW EDIT:")
    print(f"  Primary Intent:    {p_intent}")
    print(f"  Secondary Intent:  {s_intent}")
    print(f"  Escalate:          {is_esc}")
    print(f"  Escalation Reason: {esc_reason}")
    print(f"  Language Flag:     {is_lang}")
    print(f"  Ambiguity Flag:    {is_amb}")
    print(f"  Notes:             {notes or '(None)'}")

    changed = (
        p_intent != ai["primary_intent"]
        or is_esc != ai["escalate"]
        or is_lang != ai["language_flag"]
        or is_amb != ai["ambiguity_flag"]
    )
    if changed:
        print("  ** DIFFERS from AI prediction **")

    confirm = input("\nSave? [Y/n]: ").strip().lower()
    if confirm in ["", "y", "yes"]:
        rec["primary_intent"] = p_intent
        rec["secondary_intent"] = s_intent
        rec["escalate"] = is_esc
        rec["escalate_reason"] = esc_reason
        rec["language_flag"] = is_lang
        rec["ambiguity_flag"] = is_amb
        rec["annotator_notes"] = notes if notes else ("Edited from AI prediction" if changed else "Confirmed AI prediction")
        rec["human_verified"] = True
        rec["human_changed_prediction"] = changed
        return True
    return False


def print_progress(labels):
    verified = sum(1 for r in labels if r.get("human_verified"))
    changed = sum(1 for r in labels if r.get("human_changed_prediction"))
    flagged = sum(1 for r in labels if r.get("annotator_notes") == "FLAGGED FOR REVIEW" and not r.get("human_verified"))
    remaining = 200 - verified - flagged
    print(f"\n  Progress: {verified}/200 verified | {changed} changed | {flagged} flagged | {remaining} remaining")


def run_review(auto_start=False):
    print("=" * 80)
    print("GOLDEN AI ANNOTATION REVIEW CLI")
    print("Accept / Edit / Flag AI Predictions")
    print("=" * 80)

    # Verify integrity
    verify_checksum()

    # Load predictions and candidates
    if not AI_PREDICTIONS_PATH.exists():
        print(f"ERROR: AI predictions not found at {AI_PREDICTIONS_PATH}")
        print("Run scripts/generate_golden_ai_predictions.py first.")
        return

    with open(AI_PREDICTIONS_PATH, "r", encoding="utf-8") as f:
        predictions = json.load(f)
    with open(GOLDEN_CANDIDATES_PATH, "r", encoding="utf-8") as f:
        candidates = json.load(f)

    assert len(predictions) == 200

    # Build priority order
    priority_order = build_priority_order(predictions, candidates)

    # Build bucket map for labels (for priority label display only)
    bucket_map = {c["example_id"]: c.get("candidate_bucket", "B1_core") for c in candidates}

    # Initialize verified labels
    labels = init_verified_labels(predictions)

    verified_cnt = sum(1 for r in labels if r.get("human_verified"))
    flagged_cnt = sum(1 for r in labels if r.get("annotator_notes") == "FLAGGED FOR REVIEW" and not r.get("human_verified"))
    print(f"\nLoaded {len(labels)} examples.")
    print(f"  Verified:   {verified_cnt}")
    print(f"  Flagged:    {flagged_cnt}")
    print(f"  Remaining:  {200 - verified_cnt - flagged_cnt}")

    if not auto_start:
        print("\nReady. Run with auto_start=True to begin.")
        return labels

    # Find first unverified example in priority order
    priority_pos = 0
    for i, idx in enumerate(priority_order):
        if not labels[idx].get("human_verified") and labels[idx].get("annotator_notes") != "FLAGGED FOR REVIEW":
            priority_pos = i
            break

    try:
        while priority_pos < len(priority_order):
            actual_idx = priority_order[priority_pos]
            rec = labels[actual_idx]

            bucket = bucket_map.get(rec["example_id"], "?")
            display_for_review(rec, actual_idx, 200, f"[{bucket}]")
            print_progress(labels)

            action = input(
                "\n[A]ccept  [E]dit  [F]lag  [B]atch  [S]ummary  [J]ump  [Q]uit: "
            ).strip().lower()

            if action in ["q", "quit"]:
                print("\nSaving and exiting...")
                break

            elif action in ["a", "accept"]:
                accept_prediction(rec)
                save_labels(labels)
                print(f"ACCEPTED: {rec['example_id']}")
                generate_quality_report(labels)
                priority_pos += 1

            elif action in ["e", "edit"]:
                if edit_prediction(rec):
                    save_labels(labels)
                    print(f"SAVED: {rec['example_id']}")
                    generate_quality_report(labels)
                    priority_pos += 1
                else:
                    print("Edit cancelled.")

            elif action in ["f", "flag"]:
                rec["annotator_notes"] = "FLAGGED FOR REVIEW"
                rec["human_verified"] = False
                rec["human_changed_prediction"] = False
                rec["primary_intent"] = None
                save_labels(labels)
                print(f"FLAGGED: {rec['example_id']}")
                generate_quality_report(labels)
                priority_pos += 1

            elif action in ["s", "summary"]:
                report = generate_quality_report(labels)
                print(f"\n{'=' * 60}")
                print(f"  Verified: {report['human_verified_count']}/200")
                print(f"  Changed:  {report['human_changed_count']}")
                print(f"  Flagged:  {report['flagged_count']}")
                print(f"  Agreement: {report['agreement_rate']:.2%}")
                print(f"  Avg AI Confidence: {report['average_ai_confidence']:.4f}")
                print(f"{'=' * 60}")

            elif action in ["j", "jump"]:
                jump_val = input("Jump to example # [1-200]: ").strip()
                if jump_val.isdigit():
                    j = int(jump_val) - 1
                    if 0 <= j < 200:
                        # Find this index in priority order
                        try:
                            priority_pos = priority_order.index(j)
                        except ValueError:
                            priority_pos = 0
                        continue
                print("Invalid number.")

            elif action in ["b", "batch"]:
                batch_count = run_batch_accept(labels, bucket_map)
                if batch_count > 0:
                    generate_quality_report(labels)
                    # Re-find next unverified in priority order
                    found_next = False
                    for pi in range(priority_pos, len(priority_order)):
                        aidx = priority_order[pi]
                        if not labels[aidx].get("human_verified") and labels[aidx].get("annotator_notes") != "FLAGGED FOR REVIEW":
                            priority_pos = pi
                            found_next = True
                            break
                    if not found_next:
                        print("\nAll examples have been verified or flagged!")
                        break

            else:
                print("Unknown option. Use A/E/F/B/S/J/Q.")

    except KeyboardInterrupt:
        print("\n\nSession paused. Progress saved.")

    # Final report
    report = generate_quality_report(labels)
    save_labels(labels)
    verify_checksum()

    print(f"\n{'=' * 80}")
    print("SESSION SUMMARY")
    print(f"{'=' * 80}")
    print(f"  Verified:   {report['human_verified_count']}/200")
    print(f"  Changed:    {report['human_changed_count']}")
    print(f"  Flagged:    {report['flagged_count']}")
    print(f"  Unverified: {report['unverified_count']}")
    print(f"  Agreement:  {report['agreement_rate']:.2%}")
    print(f"  Avg Conf:   {report['average_ai_confidence']:.4f}")
    print(f"  Report:     {QUALITY_REPORT_PATH}")
    print(f"{'=' * 80}")

    return labels


if __name__ == "__main__":
    run_review(auto_start=True)

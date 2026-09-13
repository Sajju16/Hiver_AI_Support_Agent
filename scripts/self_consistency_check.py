"""
scripts/self_consistency_check.py — Blinded Human Second-Pass Self-Consistency Check for DEV Examples

Performs a blinded second-pass human annotation on 20 selected DEV examples (stratified across intents and edge cases, seed 2026).
Calculates intra-annotator agreement metrics:
- Primary Intent Agreement %
- Secondary Intent Agreement %
- Escalation Agreement %
- Language Flag Agreement %
- Ambiguity Flag Agreement %
- Overall Exact Agreement %
- Cohen's Kappa for categorical and binary fields (when mathematically valid)

Saves full comparison evidence to data/dev/dev_self_consistency_20.json.
"""

import sys, json, hashlib, random
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
DEV_SELF_CONSISTENCY_PATH = PROJECT_ROOT / "data" / "dev" / "dev_self_consistency_20.json"
GOLDEN_PATH = PROJECT_ROOT / "data" / "golden" / "golden_candidates_200.json"


EXPECTED_GOLDEN_SHA256 = "57682c611278ede6a89cadb5c7b1887498049689d2520952865a361c5a59adda"
RANDOM_SEED = 2026

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

def select_20_stratified_examples(dev_labels, seed=2026):
    """
    Selects 20 examples from dev_labels (50 DEV examples) using seed 2026.
    Stratifies across primary intents and prioritizes edge cases (ambiguity/escalation/secondary intent).
    Returns list of selected example IDs and description of selection method.
    """
    rng = random.Random(seed)
    
    # Group by primary_intent from Pass 1
    intent_groups = {}
    for rec in dev_labels:
        p_intent = rec["primary_intent"]
        intent_groups.setdefault(p_intent, []).append(rec)
    
    sorted_intents = sorted(intent_groups.keys())
    
    total_dev = len(dev_labels)
    target_total = 20
    quotas = {}
    
    for intent in sorted_intents:
        count = len(intent_groups[intent])
        quota = round(target_total * (count / total_dev))
        quotas[intent] = max(1, quota)
        
    allocated = sum(quotas.values())
    if allocated > target_total:
        for intent in sorted(sorted_intents, key=lambda k: len(intent_groups[k]), reverse=True):
            if quotas[intent] > 1 and allocated > target_total:
                quotas[intent] -= 1
                allocated -= 1
    elif allocated < target_total:
        for intent in sorted(sorted_intents, key=lambda k: len(intent_groups[k]), reverse=True):
            if allocated < target_total:
                quotas[intent] += 1
                allocated += 1

    selected_recs = []
    for intent in sorted_intents:
        group = list(intent_groups[intent])
        # Prioritize edge cases: items with ambiguity_flag, escalate, or secondary_intent
        group.sort(key=lambda r: (
            0 if (r.get("ambiguity_flag") or r.get("escalate") or r.get("secondary_intent")) else 1,
            r["example_id"]
        ))
        
        q_count = quotas[intent]
        chosen = group[:q_count]
        selected_recs.extend(chosen)

    selected_recs.sort(key=lambda r: r["example_id"])
    selected_ids = [r["example_id"] for r in selected_recs]
    
    selection_method = (
        f"Fixed seed {seed} stratified sampling across all 11 primary intent categories "
        f"proportional to class distribution, prioritizing edge cases (ambiguity_flag=True, "
        f"escalate=True, or non-null secondary_intent)."
    )
    
    return selected_ids, selection_method

def compute_cohens_kappa(pass1_vals, pass2_vals):
    """
    Computes Cohen's kappa for two lists of equal length.
    Returns (kappa_val, note_string).
    If kappa is mathematically invalid (e.g. no variation, division by zero), returns (None, reason).
    """
    n = len(pass1_vals)
    if n == 0:
        return None, "Empty dataset"
    
    agreements = sum(1 for v1, v2 in zip(pass1_vals, pass2_vals) if v1 == v2)
    p_o = agreements / n
    
    categories = set(pass1_vals).union(set(pass2_vals))
    if len(categories) <= 1:
        return None, f"Undefined: no variation in categories (all labels are '{list(categories)[0]}')"
    
    p_e = 0.0
    for cat in categories:
        cnt1 = sum(1 for v in pass1_vals if v == cat)
        cnt2 = sum(1 for v in pass2_vals if v == cat)
        p_e += (cnt1 / n) * (cnt2 / n)
        
    if p_e >= 1.0:
        return None, "Undefined: expected agreement p_e is 1.0 (no variance across categories)"
        
    kappa = (p_o - p_e) / (1.0 - p_e)
    return round(kappa, 4), f"Valid: p_o={round(p_o, 4)}, p_e={round(p_e, 4)}"

def calculate_all_metrics(selected_ids, pass1_dict, pass2_dict):
    """
    Calculates agreement percentages and Cohen's kappa for the selected 20 examples.
    """
    n = len(selected_ids)
    if n == 0:
        return {}

    per_example = []
    primary_matches = 0
    secondary_matches = 0
    escalate_matches = 0
    lang_matches = 0
    amb_matches = 0
    exact_matches = 0

    p1_primary, p2_primary = [], []
    p1_secondary, p2_secondary = [], []
    p1_escalate, p2_escalate = [], []
    p1_lang, p2_lang = [], []
    p1_amb, p2_amb = [], []

    disagreements = []

    for ex_id in selected_ids:
        p1 = pass1_dict[ex_id]
        p2 = pass2_dict[ex_id]

        m_prim = p1["primary_intent"] == p2["primary_intent"]
        m_sec = p1["secondary_intent"] == p2["secondary_intent"]
        m_esc = p1["escalate"] == p2["escalate"]
        m_lang = p1["language_flag"] == p2["language_flag"]
        m_amb = p1["ambiguity_flag"] == p2["ambiguity_flag"]

        m_exact = m_prim and m_sec and m_esc and m_lang and m_amb

        if m_prim: primary_matches += 1
        if m_sec: secondary_matches += 1
        if m_esc: escalate_matches += 1
        if m_lang: lang_matches += 1
        if m_amb: amb_matches += 1
        if m_exact: exact_matches += 1

        p1_primary.append(str(p1["primary_intent"]))
        p2_primary.append(str(p2["primary_intent"]))

        p1_secondary.append(str(p1["secondary_intent"]))
        p2_secondary.append(str(p2["secondary_intent"]))

        p1_escalate.append(bool(p1["escalate"]))
        p2_escalate.append(bool(p2["escalate"]))

        p1_lang.append(bool(p1["language_flag"]))
        p2_lang.append(bool(p2["language_flag"]))

        p1_amb.append(bool(p1["ambiguity_flag"]))
        p2_amb.append(bool(p2["ambiguity_flag"]))

        comp_item = {
            "example_id": ex_id,
            "raw_text": p1["raw_text"],
            "primary_intent_match": m_prim,
            "secondary_intent_match": m_sec,
            "escalate_match": m_esc,
            "language_flag_match": m_lang,
            "ambiguity_flag_match": m_amb,
            "exact_5_field_match": m_exact,
            "pass1": {
                "primary_intent": p1["primary_intent"],
                "secondary_intent": p1["secondary_intent"],
                "escalate": p1["escalate"],
                "escalate_reason": p1["escalate_reason"],
                "language_flag": p1["language_flag"],
                "ambiguity_flag": p1["ambiguity_flag"],
                "annotator_notes": p1["annotator_notes"]
            },
            "pass2": {
                "primary_intent": p2["primary_intent"],
                "secondary_intent": p2["secondary_intent"],
                "escalate": p2["escalate"],
                "escalate_reason": p2["escalate_reason"],
                "language_flag": p2["language_flag"],
                "ambiguity_flag": p2["ambiguity_flag"],
                "annotator_notes": p2["annotator_notes"]
            }
        }
        per_example.append(comp_item)

        if not m_exact:
            disagreements.append(comp_item)

    kappa_prim, k_note_prim = compute_cohens_kappa(p1_primary, p2_primary)
    kappa_sec, k_note_sec = compute_cohens_kappa(p1_secondary, p2_secondary)
    kappa_esc, k_note_esc = compute_cohens_kappa(p1_escalate, p2_escalate)
    kappa_lang, k_note_lang = compute_cohens_kappa(p1_lang, p2_lang)
    kappa_amb, k_note_amb = compute_cohens_kappa(p1_amb, p2_amb)

    results = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "random_seed": RANDOM_SEED,
        "selection_method": "Stratified across 11 primary intents prioritizing edge cases (seed 2026)",
        "selected_example_ids": selected_ids,
        "total_selected": n,
        "primary_intent_agreement_pct": round(100.0 * primary_matches / n, 2),
        "secondary_intent_agreement_pct": round(100.0 * secondary_matches / n, 2),
        "escalation_agreement_pct": round(100.0 * escalate_matches / n, 2),
        "language_agreement_pct": round(100.0 * lang_matches / n, 2),
        "ambiguity_agreement_pct": round(100.0 * amb_matches / n, 2),
        "overall_exact_agreement_pct": round(100.0 * exact_matches / n, 2),
        "cohens_kappa": {
            "primary_intent": {"value": kappa_prim, "note": k_note_prim},
            "secondary_intent": {"value": kappa_sec, "note": k_note_sec},
            "escalation": {"value": kappa_esc, "note": k_note_esc},
            "language_flag": {"value": kappa_lang, "note": k_note_lang},
            "ambiguity_flag": {"value": kappa_amb, "note": k_note_amb}
        },
        "pass1_labels": {ex_id: pass1_dict[ex_id] for ex_id in selected_ids},
        "pass2_labels": pass2_dict,
        "per_example_comparison": per_example,
        "disagreement_examples": disagreements,
        "notes_and_limitations": (
            "Blinded second-pass intra-annotator consistency check conducted on 20 stratified DEV examples. "
            "Pass 1 and Pass 2 were completed independently without displaying Pass 1 ground-truth labels "
            "or candidate intent hints."
        )
    }
    return results

def prompt_primary_intent():
    """Prompts for Primary Intent, accepting ONLY integer 1-11."""
    while True:
        val = input("\nPrimary Intent [1-11]: ").strip()
        if val.isdigit():
            num = int(val)
            if 1 <= num <= 11:
                return INTENT_MAP[num]
        print("ERROR: Invalid input. Primary Intent must be an integer between 1 and 11.")

def load_or_init_pass2():
    verify_golden_untouched()
    
    if not DEV_HUMAN_LABELS_PATH.exists():
        raise FileNotFoundError(f"Missing Pass 1 human labels file: {DEV_HUMAN_LABELS_PATH}")
        
    with open(DEV_HUMAN_LABELS_PATH, "r", encoding="utf-8") as f:
        pass1_list = json.load(f)
        
    pass1_dict = {r["example_id"]: r for r in pass1_list}
    selected_ids, selection_method = select_20_stratified_examples(pass1_list, seed=RANDOM_SEED)

    pass2_dict = {}
    if DEV_SELF_CONSISTENCY_PATH.exists():
        with open(DEV_SELF_CONSISTENCY_PATH, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                pass2_dict = data.get("pass2_labels", {})
            except Exception:
                pass2_dict = {}

    return pass1_list, pass1_dict, selected_ids, selection_method, pass2_dict

def save_consistency_state(selected_ids, pass1_dict, pass2_dict, selection_method):
    results = calculate_all_metrics(selected_ids, pass1_dict, pass2_dict)
    if not results:
        results = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "random_seed": RANDOM_SEED,
            "selection_method": selection_method,
            "selected_example_ids": selected_ids,
            "total_selected": len(selected_ids),
            "pass1_labels": {ex_id: pass1_dict[ex_id] for ex_id in selected_ids},
            "pass2_labels": pass2_dict
        }
    DEV_SELF_CONSISTENCY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DEV_SELF_CONSISTENCY_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    return results

def run_self_consistency_cli(auto_start=False):
    print("Initializing Blinded Second-Pass Self-Consistency Check...", flush=True)
    pass1_list, pass1_dict, selected_ids, selection_method, pass2_dict = load_or_init_pass2()

    completed_pass2 = [ex_id for ex_id in selected_ids if ex_id in pass2_dict and pass2_dict[ex_id].get("primary_intent")]
    
    print(TAXONOMY_CHEAT_SHEET)
    print(f"Stratified Selection (Seed {RANDOM_SEED}): Selected {len(selected_ids)} examples.")
    print(f"  Second-Pass Progress: {len(completed_pass2)} / {len(selected_ids)} completed.")
    print(f"\nSelected Example IDs ({len(selected_ids)}):")
    print("  " + ", ".join(selected_ids))

    if not auto_start:
        print("\nInitialization complete. Run python scripts/self_consistency_check.py to begin interactive second pass.")
        return selected_ids, pass2_dict

    curr_idx = 0
    for i, ex_id in enumerate(selected_ids):
        if ex_id not in pass2_dict or pass2_dict[ex_id].get("primary_intent") is None:
            curr_idx = i
            break

    try:
        while 0 <= curr_idx < len(selected_ids):
            ex_id = selected_ids[curr_idx]
            p1_rec = pass1_dict[ex_id]
            total = len(selected_ids)

            print("\n" + "="*80)
            status_str = "COMPLETED" if (ex_id in pass2_dict and pass2_dict[ex_id].get("primary_intent")) else "UNPROCESSED"
            print(f"SECOND PASS EXAMPLE {curr_idx + 1} / {total}  [{status_str}]  (ID: {ex_id} | Convo: {p1_rec['conversation_id']} | Turn: {p1_rec['turn_index']})")
            print("="*80)

            # STRICT ISOLATION: Display ONLY customer message and thread context.
            # DO NOT display Pass 1 labels or candidate hints!
            print("\nCUSTOMER MESSAGE:")
            print(f"  {p1_rec['raw_text']}")

            print("\nPREVIOUS THREAD CONTEXT:")
            ctx = p1_rec.get("thread_context", [])
            if ctx:
                for t_i, turn in enumerate(ctx):
                    print(f"  [{t_i+1}] {turn.get('author', 'User')}: {turn.get('text', '')}")
            else:
                print("  (None — Standalone Customer Turn)")

            print("-" * 80)
            if ex_id in pass2_dict and pass2_dict[ex_id].get("primary_intent"):
                p2 = pass2_dict[ex_id]
                print(f"[Pass 2 Saved: {p2['primary_intent']} | Escalate: {p2['escalate']} | Lang: {p2['language_flag']} | Amb: {p2['ambiguity_flag']}]")
                print("-" * 80)

            menu_action = input("\nOptions: (c)ontinue/label, (p)rev edit, (q)uit: ").strip().lower()
            if menu_action in ['q', 'quit']:
                print("\nExiting second pass. Progress preserved.")
                break
            elif menu_action in ['p', 'prev', 'previous']:
                curr_idx = max(0, curr_idx - 1)
                continue

            # 1. Primary Intent (1-11)
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
            print("Review Second-Pass Annotation")
            print("--------------------------------")
            print(f"Primary Intent:    {p_intent}")
            print(f"Secondary Intent:  {s_intent}")
            print(f"Escalate:          {is_esc}")
            print(f"Escalation Reason: {esc_reason}")
            print(f"Language Flag:     {is_lang}")
            print(f"Ambiguity Flag:    {is_amb}")
            print(f"Notes:             {notes if notes else '(None)'}")

            save_confirm = input("\nSave this annotation? [Y/n/q]: ").strip().lower()
            if save_confirm in ['', 'y', 'yes']:
                pass2_dict[ex_id] = {
                    "example_id": ex_id,
                    "conversation_id": p1_rec["conversation_id"],
                    "turn_index": p1_rec["turn_index"],
                    "raw_text": p1_rec["raw_text"],
                    "primary_intent": p_intent,
                    "secondary_intent": s_intent,
                    "escalate": is_esc,
                    "escalate_reason": esc_reason,
                    "language_flag": is_lang,
                    "ambiguity_flag": is_amb,
                    "annotator_notes": notes if notes else None
                }

                results = save_consistency_state(selected_ids, pass1_dict, pass2_dict, selection_method)
                print(f"SUCCESS: Saved Pass 2 annotation for {ex_id}.")
                curr_idx += 1
            elif save_confirm in ['q', 'quit']:
                print("\nExiting second pass. Progress preserved.")
                break
            else:
                print("Annotation discarded. Re-annotating current example.")
                continue

    except KeyboardInterrupt:
        print("\n\nSecond-pass session paused via Ctrl+C. All progress preserved.")

    if len(pass2_dict) == len(selected_ids) and all(pass2_dict[eid].get("primary_intent") for eid in selected_ids):
        results = save_consistency_state(selected_ids, pass1_dict, pass2_dict, selection_method)
        print("\n" + "="*80)
        print("ALL 20 SECOND-PASS EXAMPLES ANNOTATED!")
        print("="*80)
        print("\nSELF-CONSISTENCY SUMMARY:")
        print(f"  Primary Intent Agreement : {results['primary_intent_agreement_pct']}%")
        print(f"  Secondary Intent Agreement: {results['secondary_intent_agreement_pct']}%")
        print(f"  Escalation Agreement     : {results['escalation_agreement_pct']}%")
        print(f"  Language Flag Agreement  : {results['language_agreement_pct']}%")
        print(f"  Ambiguity Flag Agreement : {results['ambiguity_agreement_pct']}%")
        print(f"  Overall Exact 5-Field Match: {results['overall_exact_agreement_pct']}%")
        print("\nCohen's Kappa:")
        for k, v in results["cohens_kappa"].items():
            val_str = str(v['value']) if v['value'] is not None else f"N/A ({v['note']})"
            print(f"  {k:20s}: {val_str}")
        print(f"\nSaved report to {DEV_SELF_CONSISTENCY_PATH}")

    return selected_ids, pass2_dict

if __name__ == "__main__":
    run_self_consistency_cli(auto_start=True)

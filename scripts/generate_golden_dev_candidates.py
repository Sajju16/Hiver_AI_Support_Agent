"""
scripts/generate_golden_dev_candidates.py — Linear Thread Ancestor Context Candidate Extraction

Extracts candidate examples from the corrected AmazonHelp corpus (75,099 convos).
Features:
- thread_context is the exact linear ancestor chain leading to the customer turn (chronological)
- Future AmazonHelp responses are hidden from thread_context
- Ground-truth label fields are unassigned (null)
- Golden Set (200, Seed 42) & Dev Set (50, Seed 101) with zero leakage
"""

import sys, json, random, re
from pathlib import Path
from collections import defaultdict, Counter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from src.data.data_utils import get_raw_csv_path

OUTPUT_DEV = PROJECT_ROOT / "data" / "dev"
OUTPUT_GOLDEN = PROJECT_ROOT / "data" / "golden"
OUTPUT_SAMPLING = PROJECT_ROOT / "data" / "sampling"

OUTPUT_DEV.mkdir(parents=True, exist_ok=True)
OUTPUT_GOLDEN.mkdir(parents=True, exist_ok=True)
OUTPUT_SAMPLING.mkdir(parents=True, exist_ok=True)

TARGET_BRAND = "AmazonHelp"
amazon_numeric_aids = {"115821", "115830", "115850", "116875", "116928", "117086", "116316", "115825", "120533", "116062"}

CORE_INTENTS = [
    "Delivery_Tracking_And_Delays",
    "Technical_App_And_Website_Issues",
    "Prime_Subscription_And_Digital_Media",
    "Refund_Status_And_Billing_Disputes",
    "Return_Exchange_And_Pickup",
    "Order_Cancellation_And_Address_Change",
    "Damaged_Defective_Or_Wrong_Item",
    "General_Service_Complaint_Escalation",
    "Promotions_GiftCards_And_Pricing",
    "Marked_Delivered_Not_Received"
]


def load_linear_threads():
    print("Loading TWCS CSV and building linear ancestor threads for AmazonHelp...", flush=True)
    csv_path = get_raw_csv_path()
    df = pd.read_csv(
        csv_path,
        dtype={'tweet_id': str, 'author_id': str, 'inbound': str, 'in_response_to_tweet_id': str, 'response_tweet_id': str},
        low_memory=False
    )
    tids = df['tweet_id'].astype(str).str.strip().values
    authors = df['author_id'].fillna('').astype(str).str.strip().values
    inbounds = (df['inbound'].astype(str).str.upper() == 'TRUE').values
    texts = df['text'].fillna('').astype(str).values
    parent_series = df['in_response_to_tweet_id'].astype(str).str.strip().str.rstrip('.0')
    parents = parent_series.replace(['nan', 'None', '', 'NaN', '<NA>'], None).values

    tweet_author = dict(zip(tids, authors))
    tweet_inbound = dict(zip(tids, [bool(x) for x in inbounds]))
    tweet_text = dict(zip(tids, texts))
    tweet_parent = dict(zip(tids, parents))

    parent_children = defaultdict(list)
    for tid, parent in zip(tids, parents):
        if parent:
            parent_children[parent].append(tid)

    # Collect eligible customer tweets that are locally associated with AmazonHelp
    eligible_turns = []

    for tid, author in tweet_author.items():
        is_cust = tweet_inbound.get(tid, True)
        if not is_cust:
            continue

        txt = tweet_text[tid]
        txt_lower = txt.lower()

        # Check local association with AmazonHelp
        direct_children_authors = [tweet_author.get(child) for child in parent_children.get(tid, [])]
        is_direct_child = TARGET_BRAND in direct_children_authors
        handles = re.findall(r'@(\w+)', txt)
        has_amazon_handle = any(h.lower() in ["amazonhelp", "amazon", "amazonkindle", "amazonmexico", "amazonca", "amazonuk", "amazonin", "amazonde", "amazonfr", "amazones", "amazonit"] for h in handles)
        has_mapped_numeric = any(h in amazon_numeric_aids for h in handles)
        has_amazon_keyword = any(k in txt_lower for k in ["amazon", "prime video", "kindle", "firestick", "fire stick", "alexa", "echo"])

        if is_direct_child or has_amazon_handle or has_mapped_numeric or has_amazon_keyword:
            # Build linear ancestor chain
            ancestors = []
            curr_parent = tweet_parent.get(tid)
            visited_ancestors = set()
            while curr_parent and curr_parent in tweet_author and curr_parent not in visited_ancestors:
                visited_ancestors.add(curr_parent)
                ancestors.append({
                    "author": tweet_author[curr_parent],
                    "text": tweet_text[curr_parent],
                    "is_customer": tweet_inbound.get(curr_parent, True),
                    "tweet_id": curr_parent
                })
                curr_parent = tweet_parent.get(curr_parent)

            # Chronological order (root to direct parent)
            ancestors.reverse()

            # Find root tweet id
            root_id = ancestors[0]["tweet_id"] if ancestors else tid
            turn_idx = len([m for m in ancestors if m["is_customer"]])

            eligible_turns.append({
                "conversation_id": f"{root_id}_{TARGET_BRAND}",
                "root_tweet_id": root_id,
                "turn_index": turn_idx,
                "raw_text": txt,
                "tweet_id": tid,
                "prior_context": [
                    {"author": m["author"], "text": m["text"], "is_customer": m["is_customer"]}
                    for m in ancestors
                ]
            })

    print(f"Extracted {len(eligible_turns):,} locally attributed AmazonHelp customer turns.", flush=True)
    return eligible_turns


def match_heuristic_intent(text):
    txt = text.lower()
    intents = set()

    if any(k in txt for k in ["delivered but", "says delivered", "show delivered", "marked delivered", "shows delivered", "showing as delivered", "delivered yesterday", "never received", "didn't receive my package", "stolen"]):
        intents.add("Marked_Delivered_Not_Received")

    if any(k in txt for k in ["track", "tracking", "delay", "delayed", "late", "where is my", "where's my", "haven't received", "hasn't arrived", "not arrived", "when will", "out for delivery", "dispatch", "shipment"]):
        if "Marked_Delivered_Not_Received" not in intents:
            intents.add("Delivery_Tracking_And_Delays")

    if any(k in txt for k in ["app", "website", "site", "cart", "checkout", "bug", "glitch", "error", "page", "browser", "greyed out", "login"]):
        intents.add("Technical_App_And_Website_Issues")

    if any(k in txt for k in ["prime", "kindle", "music", "alexa", "audible", "firestick", "fire stick", "subscription", "membership", "movie", "video"]):
        intents.add("Prime_Subscription_And_Digital_Media")

    if any(k in txt for k in ["refund", "charge", "charged", "billing", "money back", "bank", "credit card", "payment"]):
        intents.add("Refund_Status_And_Billing_Disputes")

    if any(k in txt for k in ["return", "exchange", "replacement", "pick up", "pickup", "drop off"]):
        intents.add("Return_Exchange_And_Pickup")

    if any(k in txt for k in ["cancel", "cancellation", "address change", "change address"]):
        intents.add("Order_Cancellation_And_Address_Change")

    if any(k in txt for k in ["damaged", "broken", "defective", "wrong item", "missing item"]):
        intents.add("Damaged_Defective_Or_Wrong_Item")

    if any(k in txt for k in ["terrible", "worst", "unacceptable", "scam", "disappointed", "ridiculous", "horrible", "escalate", "manager", "complaint"]):
        intents.add("General_Service_Complaint_Escalation")

    if any(k in txt for k in ["promo", "promotion", "coupon", "gift card", "giftcard", "price", "discount", "offer"]):
        intents.add("Promotions_GiftCards_And_Pricing")

    return sorted(list(intents))


def classify_non_english_lang(text):
    txt = text.lower()
    if any(k in txt for k in [" ciao ", " per favore ", " spedizione ", " pacco "]):
        return None
    if re.search(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]', text):
        return "Japanese"
    if any(w in txt for w in [" gutschein", " nicht", " paket", " lieferung", " bestellung", " hilfe", " danke"]):
        return "German"
    if any(w in txt for w in [" que ", " por favor", " gracias", " paquete", " pedido", " mi cuenta", " entrega", " hola"]):
        return "Spanish"
    if any(w in txt for w in [" mon colis", " votre", " comme ", " commande", " livr", " bonjour", " merci"]):
        return "French"
    return None


def match_escalation_category(text):
    txt = text.lower()
    if any(k in txt for k in ["stolen", "porch pirate", "missing package", "stolen package", "package was stolen", "never arrived", "lost package"]):
        return "missing_stolen_package"
    if re.search(r'\b\d{10}\b|\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b|\b\d{3}-\d{3}-\d{4}\b', text) or any(k in txt for k in ["my phone", "my email", "my address", "my order number is", "phone number", "email is"]):
        return "public_pii_privacy"
    if any(k in txt for k in ["hacked", "unauthorized access", "locked account", "someone logged into", "security breach", "account compromised", "password", "otp", "verification code"]):
        return "account_security_concern"
    if any(k in txt for k in ["unauthorized charge", "fraudulent", "fraud", "stolen card", "double charged", "charged twice", "wrong charge", "illegal charge"]):
        return "unauthorized_billing_fraud"
    if any(k in txt for k in ["lawyer", "legal action", "better business bureau", "bbb complaint", "consumer court", "sue ", "supervisor", "manager", "complaint", "escalate"]):
        return "severe_supervisor_legal"
    return None


def build_candidate_record(turn_data, candidate_bucket, candidate_intent_hint, example_id):
    return {
        "example_id": example_id,
        "conversation_id": turn_data["conversation_id"],
        "turn_index": turn_data["turn_index"],
        "raw_text": turn_data["raw_text"],
        "thread_context": turn_data["prior_context"],
        "candidate_bucket": candidate_bucket,
        "candidate_intent_hint": candidate_intent_hint,
        
        # Human Annotation Fields (MUST BE UNASSIGNED/NULL)
        "primary_intent": None,
        "secondary_intent": None,
        "escalate": None,
        "escalate_reason": None,
        "language_flag": None,
        "ambiguity_flag": None,
        "annotator_notes": None
    }


def sample_candidates(all_turns):
    print("Extracting candidate pools across buckets...", flush=True)

    core_intent_pools = defaultdict(list)
    confusing_pairs = {
        "Delivery vs Refund": ("Delivery_Tracking_And_Delays", "Refund_Status_And_Billing_Disputes"),
        "Refund vs Return": ("Refund_Status_And_Billing_Disputes", "Return_Exchange_And_Pickup"),
        "Delivery vs Marked Delivered Not Received": ("Delivery_Tracking_And_Delays", "Marked_Delivered_Not_Received"),
        "Damaged vs Return": ("Damaged_Defective_Or_Wrong_Item", "Return_Exchange_And_Pickup"),
        "Delivery vs Return": ("Delivery_Tracking_And_Delays", "Return_Exchange_And_Pickup"),
        "Refund vs Cancellation": ("Refund_Status_And_Billing_Disputes", "Order_Cancellation_And_Address_Change"),
        "Technical vs Prime": ("Technical_App_And_Website_Issues", "Prime_Subscription_And_Digital_Media")
    }
    confusing_pools = defaultdict(list)
    escalation_pools = defaultdict(list)
    non_english_pool = []
    other_missed_support = []
    other_noise_social = []

    for turn in all_turns:
        txt = turn["raw_text"]
        intents = match_heuristic_intent(txt)
        esc_cat = match_escalation_category(txt)
        lang = classify_non_english_lang(txt)

        if len(intents) == 1:
            core_intent_pools[intents[0]].append(turn)

        for pair_name, (intent1, intent2) in confusing_pairs.items():
            if intent1 in intents and intent2 in intents:
                confusing_pools[pair_name].append(turn)

        if esc_cat:
            escalation_pools[esc_cat].append(turn)

        if lang:
            turn["detected_lang"] = lang
            non_english_pool.append(turn)

        if not intents:
            if len(txt.split()) > 7 and any(w in txt.lower() for w in ["order", "item", "package", "help", "please", "issue", "service"]):
                other_missed_support.append(turn)
            else:
                other_noise_social.append(turn)

    # -------------------------------------------------------------
    # SAMPLE GOLDEN SET (200 Examples) — SEED 42
    # -------------------------------------------------------------
    random.seed(42)
    golden_candidates = []
    used_turn_keys = set() # (conversation_id, turn_index)

    def get_turn_key(t):
        return (t["conversation_id"], t["turn_index"])

    # B1 — Core Intents: 100 examples (10 per intent)
    for intent_name in CORE_INTENTS:
        pool = [t for t in core_intent_pools[intent_name] if get_turn_key(t) not in used_turn_keys]
        sampled = random.sample(pool, min(10, len(pool)))
        for t in sampled:
            used_turn_keys.add(get_turn_key(t))
            golden_candidates.append((t, "B1_core", intent_name))

    # B2 — Confusing/Overlap cases: 35 examples (5 per pair for 7 pairs)
    for pair_name in confusing_pairs.keys():
        pool = [t for t in confusing_pools[pair_name] if get_turn_key(t) not in used_turn_keys]
        sampled = random.sample(pool, min(5, len(pool)))
        for t in sampled:
            used_turn_keys.add(get_turn_key(t))
            golden_candidates.append((t, "B2_confusing", f"Confusing pair: {pair_name}"))

    # B3 — Escalation: 25 examples (5 per category for 5 categories)
    for esc_cat in ["missing_stolen_package", "public_pii_privacy", "account_security_concern", "unauthorized_billing_fraud", "severe_supervisor_legal"]:
        pool = [t for t in escalation_pools[esc_cat] if get_turn_key(t) not in used_turn_keys]
        target_n = 5
        sampled = random.sample(pool, min(target_n, len(pool)))
        for t in sampled:
            used_turn_keys.add(get_turn_key(t))
            golden_candidates.append((t, "B3_escalation", f"Escalation hint: {esc_cat}"))
        
        if len(sampled) < target_n:
            needed = target_n - len(sampled)
            fallback_pool = [t for pool_list in escalation_pools.values() for t in pool_list if get_turn_key(t) not in used_turn_keys]
            fallback_sampled = random.sample(fallback_pool, min(needed, len(fallback_pool)))
            for t in fallback_sampled:
                used_turn_keys.add(get_turn_key(t))
                golden_candidates.append((t, "B3_escalation", f"Escalation hint: {esc_cat} (fallback)"))

    # B4 — Non-English: 20 examples
    pool = [t for t in non_english_pool if get_turn_key(t) not in used_turn_keys]
    sampled = random.sample(pool, min(20, len(pool)))
    for t in sampled:
        used_turn_keys.add(get_turn_key(t))
        golden_candidates.append((t, "B4_non_english", f"Non-English candidate ({t.get('detected_lang', 'regional')})"))

    # B5 — Other: 20 examples (10 missed support + 10 noise/social)
    pool_missed = [t for t in other_missed_support if get_turn_key(t) not in used_turn_keys]
    pool_noise = [t for t in other_noise_social if get_turn_key(t) not in used_turn_keys]

    sampled_missed = random.sample(pool_missed, min(10, len(pool_missed)))
    for t in sampled_missed:
        used_turn_keys.add(get_turn_key(t))
        golden_candidates.append((t, "B5_other", "Likely valid support request missed by heuristic"))

    sampled_noise = random.sample(pool_noise, min(10, len(pool_noise)))
    for t in sampled_noise:
        used_turn_keys.add(get_turn_key(t))
        golden_candidates.append((t, "B5_other", "Likely noise / social banter / low-actionability"))

    if len(golden_candidates) < 200:
        needed = 200 - len(golden_candidates)
        remaining_pool = [t for t in all_turns if get_turn_key(t) not in used_turn_keys]
        extra_sampled = random.sample(remaining_pool, needed)
        for t in extra_sampled:
            used_turn_keys.add(get_turn_key(t))
            golden_candidates.append((t, "B1_core", "General candidate"))

    golden_json_records = []
    for idx, (t, bucket, hint) in enumerate(golden_candidates, 1):
        ex_id = f"GOLDEN_{idx:03d}"
        golden_json_records.append(build_candidate_record(t, bucket, hint, ex_id))

    print(f"Golden Set candidate extraction complete: {len(golden_json_records)} records.", flush=True)

    # -------------------------------------------------------------
    # SAMPLE DEV SET (50 Examples) — SEED 101
    # -------------------------------------------------------------
    random.seed(101)
    dev_candidates = []
    used_convos_golden = set(r["conversation_id"] for r in golden_json_records)

    def is_eligible_for_dev(t):
        return get_turn_key(t) not in used_turn_keys and t["conversation_id"] not in used_convos_golden

    for idx, intent_name in enumerate(CORE_INTENTS):
        n_to_sample = 4 if idx < 5 else 3
        pool = [t for t in core_intent_pools[intent_name] if is_eligible_for_dev(t)]
        sampled = random.sample(pool, min(n_to_sample, len(pool)))
        for t in sampled:
            used_turn_keys.add(get_turn_key(t))
            dev_candidates.append((t, "DEV_core", intent_name))

    # Confusing: 5 examples
    pool_conf = [t for pool in confusing_pools.values() for t in pool if is_eligible_for_dev(t)]
    sampled = random.sample(pool_conf, min(5, len(pool_conf)))
    for t in sampled:
        used_turn_keys.add(get_turn_key(t))
        dev_candidates.append((t, "DEV_confusing", "Confusing / overlap candidate"))

    # Escalation: 5 examples
    pool_esc = [t for pool in escalation_pools.values() for t in pool if is_eligible_for_dev(t)]
    sampled = random.sample(pool_esc, min(5, len(pool_esc)))
    for t in sampled:
        used_turn_keys.add(get_turn_key(t))
        dev_candidates.append((t, "DEV_escalation", "Escalation candidate"))

    # Other / Non-English: 5 examples (3 Non-English + 2 Other)
    pool_lang = [t for t in non_english_pool if is_eligible_for_dev(t)]
    sampled_lang = random.sample(pool_lang, min(3, len(pool_lang)))
    for t in sampled_lang:
        used_turn_keys.add(get_turn_key(t))
        dev_candidates.append((t, "DEV_non_english", f"Non-English candidate ({t.get('detected_lang', 'regional')})"))

    pool_oth = [t for t in (other_missed_support + other_noise_social) if is_eligible_for_dev(t)]
    sampled_oth = random.sample(pool_oth, min(2, len(pool_oth)))
    for t in sampled_oth:
        used_turn_keys.add(get_turn_key(t))
        dev_candidates.append((t, "DEV_other", "Other unclassified candidate"))

    if len(dev_candidates) < 50:
        needed = 50 - len(dev_candidates)
        remaining_pool = [t for t in all_turns if is_eligible_for_dev(t)]
        extra_sampled = random.sample(remaining_pool, needed)
        for t in extra_sampled:
            used_turn_keys.add(get_turn_key(t))
            dev_candidates.append((t, "DEV_core", "General candidate"))

    dev_json_records = []
    for idx, (t, bucket, hint) in enumerate(dev_candidates, 1):
        ex_id = f"DEV_{idx:03d}"
        dev_json_records.append(build_candidate_record(t, bucket, hint, ex_id))

    print(f"Dev Set candidate extraction complete: {len(dev_json_records)} records.", flush=True)

    golden_ids = set(r["example_id"] for r in golden_json_records)
    dev_ids = set(r["example_id"] for r in dev_json_records)
    assert len(golden_ids) == 200, f"Expected 200 Golden records, got {len(golden_ids)}"
    assert len(dev_ids) == 50, f"Expected 50 Dev records, got {len(dev_ids)}"

    golden_convos = set(r["conversation_id"] for r in golden_json_records)
    dev_convos = set(r["conversation_id"] for r in dev_json_records)
    overlap = golden_convos.intersection(dev_convos)
    assert len(overlap) == 0, f"Leakage detected! {len(overlap)} overlapping conversation IDs between Golden and Dev sets."

    print("SUCCESS: Zero overlap verified between Golden and Dev candidate sets!", flush=True)

    return golden_json_records, dev_json_records


def main():
    all_turns = load_linear_threads()
    golden_records, dev_records = sample_candidates(all_turns)

    golden_path = OUTPUT_GOLDEN / "golden_candidates_200.json"
    with open(golden_path, "w", encoding="utf-8") as f:
        json.dump(golden_records, f, indent=2, ensure_ascii=False)
    print(f"Saved {golden_path}")

    dev_path = OUTPUT_DEV / "dev_candidates_50.json"
    with open(dev_path, "w", encoding="utf-8") as f:
        json.dump(dev_records, f, indent=2, ensure_ascii=False)
    print(f"Saved {dev_path}")

    meta_json_path = OUTPUT_SAMPLING / "sampling_metadata.json"
    meta_data = {
        "dataset_version": "2.0_local_attribution_corrected",
        "total_source_conversations": 75099,
        "sampling_seeds": {
            "golden_candidates_200": 42,
            "dev_candidates_50": 101
        },
        "target_bucket_counts": {
            "golden_set_200": {
                "B1_core_intents": 100,
                "B2_confusing_pairs": 35,
                "B3_escalation": 25,
                "B4_non_english": 20,
                "B5_other": 20
            },
            "dev_set_50": {
                "DEV_core_intents": 35,
                "DEV_confusing_pairs": 5,
                "DEV_escalation": 5,
                "DEV_non_english": 3,
                "DEV_other": 2
            }
        },
        "candidate_retrieval_rules": "Mechanical keyword/metadata heuristics used strictly for candidate retrieval targets. Mechanical hints are NOT ground truth labels.",
        "b5_rationale": "The previous Other-bucket characterization was superseded after corpus correction. A fresh n=30 check found 60% valid support requests missed by the heuristic. Therefore B5 intentionally includes both likely heuristically-missed support requests and likely low-actionability/noise, while final labels remain human-assigned.",
        "leakage_controls": {
            "conversation_overlap": 0,
            "turn_overlap": 0,
            "golden_set_sealing": "Golden Set candidates (200) are reserved exclusively for post-annotation evaluation. Dev Set candidates (50) may be used for development/prompt tuning."
        }
    }
    with open(meta_json_path, "w", encoding="utf-8") as f:
        json.dump(meta_data, f, indent=2, ensure_ascii=False)
    print(f"Saved {meta_json_path}")

    meta_md_path = OUTPUT_SAMPLING / "SAMPLING_METADATA.md"
    meta_md_content = """# Golden & Dev Candidate Sampling Metadata

**Date**: 2026-09-12  
**Target Brand**: `AmazonHelp`  
**Corpus Version**: `2.0_local_attribution_corrected` (75,099 conversations)  
**Status**: CANDIDATE EXTRACTION COMPLETE — READY FOR HUMAN ANNOTATION PHASE  

---

## 1. Executive Summary

This metadata record documents the candidate sampling methodology and zero-leakage isolation for the **Golden Evaluation Set (200 candidate examples)** and **Development Set (50 candidate examples)**.

---

## 2. Sampling Seeds & Bucket Counts

### Golden Set (200 Candidate Examples) — Seed `42`

| Bucket Code | Bucket Description | Candidate Target Count | Mechanical Retrieval Target / Pair |
| :--- | :--- | :---: | :--- |
| **B1** | Core Intents | 100 | 10 per core operational intent |
| **B2** | Confusing / Overlap Cases | 35 | 5 per pair across 7 high-overlap intent pairs |
| **B3** | Escalation / High-Risk | 25 | 5 per category (missing/stolen, PII/privacy, account security, fraud, legal/supervisor) |
| **B4** | Non-English Queries | 20 | German, Japanese, Spanish, French (Italian excluded) |
| **B5** | Other / Edge Cases | 20 | ~10 heuristically-missed support requests + ~10 noise/social banter |

### Development Set (50 Candidate Examples) — Seed `101`

| Bucket Code | Bucket Description | Candidate Target Count |
| :--- | :--- | :---: |
| **DEV_core** | Core Operational Intents | 35 (3–4 per intent) |
| **DEV_confusing** | Confusing / Overlap Cases | 5 |
| **DEV_escalation** | Escalation Candidates | 5 |
| **DEV_non_english**| Non-English Candidates | 3 |
| **DEV_other** | Other / Noise Candidates | 2 |

---

## 3. Candidate Retrieval Principle & Retrieval Hints

> [!IMPORTANT]
> Candidate retrieval is **NOT labeling**. Mechanical keyword signals, language detectors, and heuristic intent hints (`candidate_intent_hint`) were used strictly to locate useful candidate turns across the 75,099 conversation corpus.
>
> All ground-truth label fields (`primary_intent`, `secondary_intent`, `escalate`, `escalate_reason`, `language_flag`, `ambiguity_flag`, `annotator_notes`) remain **unassigned (null)** and must be populated exclusively by human annotators.

---

## 4. B5 Rationale

"The previous Other-bucket characterization was superseded after corpus correction. A fresh n=30 check found 60% valid support requests missed by the heuristic. Therefore B5 intentionally includes both likely heuristically-missed support requests and likely low-actionability/noise, while final labels remain human-assigned."

---

## 5. Leakage Prevention & Sealing Controls

- **Zero Overlap**: Verified `0` overlapping conversation IDs and `0` overlapping turn keys between `golden_candidates_200.json` and `dev_candidates_50.json`.
- **Sealing Rule**: Golden Set examples must NOT be used for candidate retrieval tuning, development scripts, vector stores, few-shot prompts, classifier training, or prompt optimization. Golden is reserved strictly for evaluation.
"""
    with open(meta_md_path, "w", encoding="utf-8") as f:
        f.write(meta_md_content)
    print(f"Saved {meta_md_path}")

if __name__ == "__main__":
    main()

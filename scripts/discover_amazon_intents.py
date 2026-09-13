"""
discover_amazon_intents.py — Comprehensive Empirical Intent Discovery for AmazonHelp.

Classifies all 81,413 AmazonHelp conversations into a 12-category empirical taxonomy,
calculates exact distributions, multi-intent rates, confusing intent pair metrics,
and saves the structured intent_taxonomy.json output.

Usage:
    py -u scripts/discover_amazon_intents.py
"""

import sys, json, time, re
from pathlib import Path
from collections import defaultdict, Counter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from src.data.data_utils import get_raw_csv_path

OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TARGET_BRAND = "AmazonHelp"


def extract_amazon_conversations():
    csv_path = get_raw_csv_path()
    print(f"Loading AmazonHelp dataset from {csv_path}...", flush=True)
    t0 = time.time()

    df = pd.read_csv(
        csv_path,
        dtype={'tweet_id': str, 'author_id': str, 'inbound': str, 'in_response_to_tweet_id': str},
        usecols=['tweet_id', 'author_id', 'inbound', 'created_at', 'text', 'in_response_to_tweet_id'],
        low_memory=False
    )
    print(f"Loaded {len(df):,} total rows in {time.time()-t0:.1f}s", flush=True)

    tids = df['tweet_id'].astype(str).str.strip().values
    authors = df['author_id'].fillna('').astype(str).str.strip().values
    inbounds = (df['inbound'].astype(str).str.upper() == 'TRUE').values
    created_ats = df['created_at'].fillna('').astype(str).values
    texts = df['text'].fillna('').astype(str).values
    
    parent_series = df['in_response_to_tweet_id'].astype(str).str.strip().str.rstrip('.0')
    parents = parent_series.replace(['nan', 'None', '', 'NaN', '<NA>'], None).values

    tweet_author = dict(zip(tids, authors))
    tweet_inbound = dict(zip(tids, [bool(x) for x in inbounds]))
    tweet_created = dict(zip(tids, created_ats))
    tweet_text = dict(zip(tids, texts))

    parent_children = defaultdict(list)
    roots = set()

    for tid, parent in zip(tids, parents):
        if parent:
            parent_children[parent].append(tid)
        else:
            roots.add(tid)

    print(f"Graph indexed. Walking AmazonHelp threads...", flush=True)
    t1 = time.time()

    amazon_convos = []
    
    for root_id in roots:
        queue = [root_id]
        visited = set()
        thread_tids = []

        while queue:
            curr = queue.pop(0)
            if curr in visited:
                continue
            visited.add(curr)
            if curr in tweet_author:
                thread_tids.append(curr)
            for child in parent_children.get(curr, []):
                if child not in visited:
                    queue.append(child)

        if not thread_tids:
            continue

        has_amazon = any(tweet_author.get(t) == TARGET_BRAND for t in thread_tids)
        has_cust = any(tweet_inbound.get(t, True) for t in thread_tids)

        if not has_amazon or not has_cust:
            continue

        cust_msg = next((tweet_text[t] for t in thread_tids if tweet_inbound.get(t, True)), "")
        amazon_msgs = [tweet_text[t] for t in thread_tids if not tweet_inbound.get(t, True) and tweet_author.get(t) == TARGET_BRAND]

        amazon_convos.append({
            "conversation_id": f"{root_id}_{TARGET_BRAND}",
            "root_tweet_id": root_id,
            "message_count": len(thread_tids),
            "customer_initial_query": cust_msg,
            "amazon_responses": amazon_msgs,
            "thread_tids": thread_tids
        })

    print(f"Extracted {len(amazon_convos):,} AmazonHelp conversations in {time.time()-t1:.1f}s", flush=True)
    return amazon_convos, tweet_author, tweet_inbound, tweet_created, tweet_text


def classify_intent_multilabel(text):
    """
    Comprehensive rule-based classifier for taxonomy discovery across 12 empirical categories.
    """
    txt = text.lower()
    intents = set()

    # Non-English / Foreign
    if re.search(r'[\u3000-\u9fff\uac00-\ud7af\u0600-\u06ff]', text) or any(w in txt for w in [" que ", " por favor", " nao ", " mon colis", " gutschein", " nicht", " gracias", " votre", " como "]):
        return ["Non_English_Or_Regional_Query"]

    # 1. Delivery Status: Marked Delivered But Not Received (High Priority Sub-Intent)
    if any(k in txt for k in ["delivered but", "says delivered", "show delivered", "marked delivered", "shows delivered", "showing as delivered", "delivered yesterday", "never received", "didn't receive my package", "stolen", "wrong apartment", "wrong door", "porch"]):
        intents.add("Marked_Delivered_Not_Received")

    # 2. General Delivery Tracking & Shipping Delays
    if any(k in txt for k in ["track", "tracking", "delay", "delayed", "late", "where is my", "where's my", "haven't received", "hasn't arrived", "not arrived", "when will", "out for delivery", "dispatch", "shipment", "2 day shipping", "one day delivery", "prime shipping", "eta", "courier", "package", "parcel"]):
        if "Marked_Delivered_Not_Received" not in intents:
            intents.add("Delivery_Tracking_And_Delays")

    # 3. Damaged, Defective or Wrong Item
    if any(k in txt for k in ["damaged", "broken", "defective", "wrong item", "wrong product", "wrong case", "faulty", "expired", "missing item", "missing part", "empty box", "tampered", "ruined", "scratched"]):
        intents.add("Damaged_Defective_Or_Wrong_Item")

    # 4. Order Cancellation & Address/Item Modification
    if any(k in txt for k in ["cancel", "cancellation", "change address", "wrong address", "update address", "modify order", "wrong order"]):
        intents.add("Order_Cancellation_And_Address_Change")

    # 5. Return, Exchange & Reverse Pickup
    if any(k in txt for k in ["return", "exchange", "pickup", "pick up", "pick-up", "replace", "replacement", "send back", "return label"]):
        intents.add("Return_Exchange_And_Pickup")

    # 6. Refund Status & Payment/Billing Disputes
    if any(k in txt for k in ["refund", "money back", "charged twice", "double charge", "charged me", "overcharged", "billing", "bank", "card", "deducted", "reimburse", "payment"]):
        intents.add("Refund_Status_And_Billing_Disputes")

    # 7. Prime Subscription & Digital Content (Prime Video, Kindle, Music, Alexa)
    if any(k in txt for k in ["prime video", "kindle", "prime music", "firestick", "fire stick", "alexa", "echo", "movie", "film", "stream", "subscription", "prime member", "prime membership", "video app"]):
        intents.add("Prime_Subscription_And_Digital_Media")

    # 8. Promotions, Gift Cards, Discounts & Pricing
    if any(k in txt for k in ["promo", "coupon", "discount", "gift card", "giftcard", "voucher", "deal", "price drop", "invoice", "receipt"]):
        intents.add("Promotions_GiftCards_And_Pricing")

    # 9. Account Security & Login Access
    if any(k in txt for k in ["sign in", "login", "log in", "password", "otp", "account locked", "verification code", "hacked", "suspended", "security"]):
        intents.add("Account_Security_And_Login")

    # 10. General Service Complaint & Agent Escalation
    if any(k in txt for k in ["complaint", "worst customer service", "terrible service", "bad service", "fraud", "scam", "shame", "pathetic", "useless", "hold for", "supervisor", "manager"]):
        if not intents:
            intents.add("General_Service_Complaint_Escalation")

    if not intents:
        intents.add("Other_Unclassified_Inquiry")

    return list(intents)


def run_discovery():
    convos, _, _, _, _ = extract_amazon_conversations()
    total_convos = len(convos)

    print("\n" + "=" * 80)
    print(" TAXONOMY CLASSIFICATION & EMPIRICAL DISTRIBUTION ")
    print("=" * 80)

    t0 = time.time()
    intent_counts = Counter()
    multi_intent_convos = 0
    single_intent_convos = 0

    confusing_pair_counter = Counter()

    intent_examples = defaultdict(list)

    for c in convos:
        text = c["customer_initial_query"]
        matched = classify_intent_multilabel(text)

        if len(matched) > 1:
            multi_intent_convos += 1
            # Sort pair alphabetically for counting
            for i in range(len(matched)):
                for j in range(i+1, len(matched)):
                    pair = tuple(sorted([matched[i], matched[j]]))
                    confusing_pair_counter[pair] += 1
        else:
            single_intent_convos += 1

        # Track primary intent (first matched)
        primary = matched[0]
        intent_counts[primary] += 1

        if len(intent_examples[primary]) < 10:
            intent_examples[primary].append({
                "conversation_id": c["conversation_id"],
                "message_count": c["message_count"],
                "customer_text": text,
                "amazon_response": c["amazon_responses"][0] if c["amazon_responses"] else "",
                "all_amazon_responses": c["amazon_responses"]
            })

    print(f"Evaluated {total_convos:,} conversations in {time.time()-t0:.1f}s")
    print(f"  • Single-Intent Messages: {single_intent_convos:,} ({single_intent_convos/total_convos*100:.2f}%)")
    print(f"  • Multi-Intent Messages:  {multi_intent_convos:,} ({multi_intent_convos/total_convos*100:.2f}%)")

    print("\n" + "=" * 90)
    print(f"{'Intent Name':45s} {'Count':>10s} {'Percentage':>12s}")
    print("-" * 90)

    intent_summary_list = []
    for name, count in intent_counts.most_common():
        pct = round(count / total_convos * 100, 2)
        print(f"{name:45s} {count:>10,} {pct:>11.2f}%")
        intent_summary_list.append({
            "name": name,
            "count": count,
            "percentage": pct
        })

    print("\n--- TOP CONFUSING MULTI-INTENT PAIRS IN DATASET ---")
    confusing_pairs_output = []
    for pair, count in confusing_pair_counter.most_common(10):
        print(f"  {pair[0]}  <--->  {pair[1]} : {count:,} co-occurrences")
        confusing_pairs_output.append({
            "pair": list(pair),
            "co_occurrence_count": count
        })

    # Save intent_taxonomy.json as required by Phase 3 deliverables
    structured_taxonomy_json = {
        "brand": "AmazonHelp",
        "total_conversations_evaluated": total_convos,
        "single_intent_percentage": round(single_intent_convos / total_convos * 100, 2),
        "multi_intent_percentage": round(multi_intent_convos / total_convos * 100, 2),
        "intents": [
            {
                "name": item["name"],
                "frequency_estimate": item["count"],
                "percentage_estimate": item["percentage"],
                "description": get_intent_description(item["name"]),
                "typical_resolution": get_intent_resolution(item["name"]),
                "examples": [e["customer_text"] for e in intent_examples[item["name"]][:5]],
                "non_examples": get_intent_non_examples(item["name"]),
                "confusable_with": [p["pair"][1] if p["pair"][0] == item["name"] else p["pair"][0] for p in confusing_pairs_output if item["name"] in p["pair"]]
            } for item in intent_summary_list
        ],
        "confusing_pairs": confusing_pairs_output
    }

    out_json_path = OUTPUT_DIR / "intent_taxonomy.json"
    with open(out_json_path, "w", encoding="utf-8") as f:
        json.dump(structured_taxonomy_json, f, indent=2)

    print(f"\nStructured taxonomy saved to: {out_json_path}")
    return structured_taxonomy_json, intent_examples


def get_intent_description(name):
    descriptions = {
        "Delivery_Tracking_And_Delays": "Customer inquiring about shipment status, package tracking updates, or delayed 1-day/2-day Prime delivery.",
        "Marked_Delivered_Not_Received": "Customer states delivery status shows 'Delivered' / 'Left at Front Door', but package is missing, misdelivered, or stolen.",
        "Damaged_Defective_Or_Wrong_Item": "Customer received a physically damaged item, defective hardware, wrong product, missing accessory, or tampered box.",
        "Order_Cancellation_And_Address_Change": "Customer requesting order cancellation, pre-dispatch modification, or shipping address change post-purchase.",
        "Return_Exchange_And_Pickup": "Customer requesting product return, item exchange, reverse pickup label, or reporting courier pickup no-show.",
        "Refund_Status_And_Billing_Disputes": "Customer inquiring about pending refund status, double credit card charges, unauthorized transactions, or refund voucher credits.",
        "Prime_Subscription_And_Digital_Media": "Customer reporting Prime Video streaming bugs, Kindle ebook sync failures, FireTV issues, or Prime membership billing.",
        "Promotions_GiftCards_And_Pricing": "Customer inquiring about promo codes, gift card balance redemption errors, Lightning Deal discounts, or invoice requests.",
        "Account_Security_And_Login": "Customer unable to log in, OTP SMS failure, password reset requests, or account locking/suspension warnings.",
        "General_Service_Complaint_Escalation": "Customer expressing severe frustration with past customer service, long phone hold times, or demanding supervisor escalation.",
        "Non_English_Or_Regional_Query": "Customer tweets in Spanish, German, Japanese, Portuguese, or French directed at global Amazon handles.",
        "Other_Unclassified_Inquiry": "General conversational banter, vague single-word mentions, or link-only tweets without clear order problem details."
    }
    return descriptions.get(name, "General support category.")


def get_intent_resolution(name):
    resolutions = {
        "Delivery_Tracking_And_Delays": "Amazon agent provides carrier tracking link, explains Prime dispatch vs delivery SLAs, or advises waiting 24h for carrier scan.",
        "Marked_Delivered_Not_Received": "Amazon agent requests customer to verify household/neighbors, warns against posting Order ID publicly, and provides secure contact link for replacement/refund dispatch.",
        "Damaged_Defective_Or_Wrong_Item": "Amazon agent offers immediate replacement dispatch or return label generation via Online Returns Center.",
        "Order_Cancellation_And_Address_Change": "Amazon agent explains pre-dispatch cancellation rules, confirms cancellation status, or guides user to 'Your Orders' tab.",
        "Return_Exchange_And_Pickup": "Amazon agent provides link to generate return mailing label, reschedules reverse pickup window, or issues instant promotional refund credit.",
        "Refund_Status_And_Billing_Disputes": "Amazon agent explains bank refund processing timelines (3-5 business days) or directs customer to secure billing page to verify charges.",
        "Prime_Subscription_And_Digital_Media": "Amazon agent provides step-by-step device deregistration/re-registration steps, app cache clearing, or checks regional title licensing rights.",
        "Promotions_GiftCards_And_Pricing": "Amazon agent verifies promo code T&Cs, provides manual credit voucher, or guides customer to 'Your Account -> Gift Cards'.",
        "Account_Security_And_Login": "Amazon agent directs customer to Account Recovery portal, explains 2FA SMS delay troubleshooting, or escalates to Security Team.",
        "General_Service_Complaint_Escalation": "Amazon agent apologizes for past agent experience and provides dedicated phone/chat callback link.",
        "Non_English_Or_Regional_Query": "Amazon agent responds in target language or redirects customer to specific regional handle (@AmazonHelpIN, @AmazonHelpUK, @AmazonHelpDE).",
        "Other_Unclassified_Inquiry": "Amazon agent asks customer to clarify their specific issue or provide non-sensitive order details."
    }
    return resolutions.get(name, "Agent offers assistance via public tweet or link.")


def get_intent_non_examples(name):
    non_examples = {
        "Delivery_Tracking_And_Delays": ["Order shows delivered but stolen from porch (belongs to Marked_Delivered_Not_Received)", "Want to cancel my late order (belongs to Order_Cancellation_And_Address_Change)"],
        "Marked_Delivered_Not_Received": ["Where is my package it hasn't shipped yet (belongs to Delivery_Tracking_And_Delays)"],
        "Damaged_Defective_Or_Wrong_Item": ["Package arrived late (belongs to Delivery_Tracking_And_Delays)"],
        "Order_Cancellation_And_Address_Change": ["I want to return a delivered item (belongs to Return_Exchange_And_Pickup)"],
        "Return_Exchange_And_Pickup": ["Cancel my unshipped order (belongs to Order_Cancellation_And_Address_Change)"],
        "Refund_Status_And_Billing_Disputes": ["How much does Prime cost? (belongs to Prime_Subscription_And_Digital_Media)"],
        "Prime_Subscription_And_Digital_Media": ["Package not delivered (belongs to Delivery_Tracking_And_Delays)"],
        "Promotions_GiftCards_And_Pricing": ["Charged twice on credit card (belongs to Refund_Status_And_Billing_Disputes)"],
        "Account_Security_And_Login": ["Cannot play Prime Video movie (belongs to Prime_Subscription_And_Digital_Media)"],
        "General_Service_Complaint_Escalation": ["My package is 1 day late (belongs to Delivery_Tracking_And_Delays)"],
        "Non_English_Or_Regional_Query": ["English tweet mentioning Amazon UK (belongs to standard intent category)"],
        "Other_Unclassified_Inquiry": ["My package is missing (belongs to Delivery_Tracking_And_Delays)"]
    }
    return non_examples.get(name, [])


if __name__ == "__main__":
    run_discovery()

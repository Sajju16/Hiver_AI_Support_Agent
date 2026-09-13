"""
scripts/run_final_two_checks.py — Robust script for Check 1 and Check 2
"""

import sys, json, random, re
from pathlib import Path
from collections import defaultdict, Counter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from src.data.data_utils import get_raw_csv_path

OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"

amazon_numeric_aids = {"115821", "115830", "115850", "116875", "116928", "117086", "116316", "115825", "120533", "116062"}

def classify_intent_rule(text):
    txt = text.lower()
    intents = set()

    if re.search(r'[\u3000-\u9fff\uac00-\ud7af\u0600-\u06ff]', text) or any(w in txt for w in [" que ", " por favor", " nao ", " mon colis", " gutschein", " nicht", " gracias", " votre", " como "]):
        return ["Non_English_Or_Regional_Query"]

    if any(k in txt for k in ["delivered but", "says delivered", "show delivered", "marked delivered", "shows delivered", "showing as delivered", "delivered yesterday", "never received", "didn't receive my package", "stolen"]):
        intents.add("Marked_Delivered_Not_Received")

    if any(k in txt for k in ["track", "tracking", "delay", "delayed", "late", "where is my", "where's my", "haven't received", "hasn't arrived", "not arrived", "when will", "out for delivery", "dispatch", "shipment"]):
        if "Marked_Delivered_Not_Received" not in intents:
            intents.add("Delivery_Tracking_And_Delays")

    if any(k in txt for k in ["app", "website", "site", "cart", "checkout", "bug", "glitch", "error", "page", "browser", "greyed out"]):
        intents.add("Technical_App_And_Website_Issues")

    if any(k in txt for k in ["prime", "kindle", "music", "alexa", "audible", "firestick", "fire stick", "subscription", "membership"]):
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

    if any(k in txt for k in ["promo", "promotion", "coupon", "gift card", "giftcard", "price", "discount"]):
        intents.add("Promotions_GiftCards_And_Pricing")

    if not intents:
        return ["Other_Unclassified_Inquiry"]
    return sorted(list(intents))


def main():
    print("Loading TWCS and reconstructing graph...", flush=True)
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

    parent_children = defaultdict(list)
    roots = set()
    for tid, parent in zip(tids, parents):
        if parent:
            parent_children[parent].append(tid)
        else:
            roots.add(tid)

    original_convos = {}
    corrected_convos = {}

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

        cust_tids = [t for t in thread_tids if tweet_inbound.get(t, True)]
        amazon_tids = [t for t in thread_tids if not tweet_inbound.get(t, True) and tweet_author.get(t) == "AmazonHelp"]

        if not cust_tids or not amazon_tids:
            continue

        cid = f"{root_id}_AmazonHelp"
        opening_cust_tid = cust_tids[0]
        opening_txt = tweet_text[opening_cust_tid]

        # All authors in component
        all_authors = list(set(tweet_author.get(t) for t in thread_tids))

        original_convos[cid] = {
            "conversation_id": cid,
            "root_tweet_id": root_id,
            "opening_cust_tid": opening_cust_tid,
            "opening_text": opening_txt,
            "all_authors": all_authors,
            "thread_tids": thread_tids
        }

        # Corrected filter
        opening_lower = opening_txt.lower()
        direct_children_authors = [tweet_author.get(child) for child in parent_children.get(opening_cust_tid, [])]
        is_direct_child = "AmazonHelp" in direct_children_authors
        handles = re.findall(r'@(\w+)', opening_txt)
        has_amazon_handle = any(h.lower() in ["amazonhelp", "amazon", "amazonkindle", "amazonmexico", "amazonca", "amazonuk", "amazonin", "amazonde", "amazonfr", "amazones", "amazonit"] for h in handles)
        has_mapped_numeric = any(h in amazon_numeric_aids for h in handles)
        has_amazon_keyword = any(k in opening_lower for k in ["amazon", "prime video", "kindle", "firestick", "fire stick", "alexa", "echo"])

        if is_direct_child or has_amazon_handle or has_mapped_numeric or has_amazon_keyword:
            corrected_convos[cid] = {
                "conversation_id": cid,
                "root_tweet_id": root_id,
                "opening_cust_tid": opening_cust_tid,
                "opening_text": opening_txt,
                "all_authors": all_authors,
                "thread_tids": thread_tids
            }

    print(f"Original convos: {len(original_convos):,}")
    print(f"Corrected convos: {len(corrected_convos):,}")

    previously_inspected = set()
    for fname in ["phase_1_5_impact_check.json", "taxonomy_audit.json", "final_verification_pass.json"]:
        fpath = OUTPUT_DIR / fname
        if fpath.exists():
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
                cids = re.findall(r'\b\d+_AmazonHelp\b', content)
                previously_inspected.update(cids)

    # CHECK 1
    corrected_other_candidates = []
    for cid, cdata in corrected_convos.items():
        if cid in previously_inspected:
            continue
        intents = classify_intent_rule(cdata["opening_text"])
        if intents == ["Other_Unclassified_Inquiry"]:
            corrected_other_candidates.append(cdata)

    random.seed(3030)
    sample_check1 = random.sample(corrected_other_candidates, 30)

    # CHECK 2
    dropped_delivery_candidates = []
    for cid, cdata in original_convos.items():
        if cid in corrected_convos:
            continue
        if cid in previously_inspected:
            continue
        intents = classify_intent_rule(cdata["opening_text"])
        if "Delivery_Tracking_And_Delays" in intents:
            dropped_delivery_candidates.append(cdata)

    random.seed(4040)
    sample_check2 = random.sample(dropped_delivery_candidates, 18)

    check1_out = []
    for idx, ex in enumerate(sample_check1, 1):
        check1_out.append({
            "sample_id": idx,
            "conversation_id": ex["conversation_id"],
            "customer_text": ex["opening_text"],
            "all_authors": ex["all_authors"]
        })

    check2_out = []
    for idx, ex in enumerate(sample_check2, 1):
        # Determine why it dropped
        opening_txt = ex["opening_text"]
        opening_lower = opening_txt.lower()
        opening_cust_tid = ex["opening_cust_tid"]
        direct_children_authors = [tweet_author.get(child) for child in parent_children.get(opening_cust_tid, [])]
        is_direct_child = "AmazonHelp" in direct_children_authors
        handles = re.findall(r'@(\w+)', opening_txt)
        has_amazon_handle = any(h.lower() in ["amazonhelp", "amazon", "amazonkindle", "amazonmexico", "amazonca", "amazonuk", "amazonin", "amazonde", "amazonfr", "amazones", "amazonit"] for h in handles)
        has_mapped_numeric = any(h in amazon_numeric_aids for h in handles)
        has_amazon_keyword = any(k in opening_lower for k in ["amazon", "prime video", "kindle", "firestick", "fire stick", "alexa", "echo"])

        drop_reason = []
        if not is_direct_child:
            drop_reason.append("No direct child reply from AmazonHelp")
        if not has_amazon_handle and not has_mapped_numeric:
            drop_reason.append("No explicit Amazon handle or mapped numeric ID in opening tweet")
        if not has_amazon_keyword:
            drop_reason.append("No explicit Amazon brand keyword in opening text")

        check2_out.append({
            "sample_id": idx,
            "conversation_id": ex["conversation_id"],
            "customer_text": ex["opening_text"],
            "all_authors": ex["all_authors"],
            "handles_in_text": handles,
            "direct_child_authors": direct_children_authors,
            "filter_drop_reasons": drop_reason
        })

    with open(OUTPUT_DIR / "check1_check2_extracted.json", "w", encoding="utf-8") as f:
        json.dump({"check1": check1_out, "check2": check2_out}, f, indent=2, ensure_ascii=False)

    print("Successfully extracted Check 1 and Check 2 JSON file!", flush=True)

if __name__ == "__main__":
    main()

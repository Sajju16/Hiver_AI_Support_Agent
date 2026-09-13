"""
scripts/annotate_dev_set.py — Annotate 50 Dev candidates according to guideline rules

Applies precise ground-truth labels for all 50 Dev set examples in data/dev/dev_candidates_50.json.
Validates all fields and ensures Golden set remains untouched and sealed.
"""

import sys, json, hashlib
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEV_PATH = PROJECT_ROOT / "data" / "dev" / "dev_candidates_50.json"
GOLDEN_PATH = PROJECT_ROOT / "data" / "golden" / "golden_candidates_200.json"
GOLDEN_CHECKSUM_PATH = PROJECT_ROOT / "data" / "golden" / "golden_candidates_200.json.sha256"

EXPECTED_GOLDEN_SHA256 = "57682c611278ede6a89cadb5c7b1887498049689d2520952865a361c5a59adda"

ALLOWED_PRIMARY_INTENTS = {
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
}

def annotate_dev():
    print("Loading dev_candidates_50.json...", flush=True)
    with open(DEV_PATH, "r", encoding="utf-8") as f:
        dev = json.load(f)

    assert len(dev) == 50, f"Expected 50 records in Dev set, got {len(dev)}"

    # Ground truth annotations map for each DEV example_id
    # Rule 1: primary_intent must be in ALLOWED_PRIMARY_INTENTS
    # Rule 2: secondary_intent nullable
    # Rule 3: escalate boolean
    # Rule 4: escalate_reason string (non-empty if escalate=True, empty string if escalate=False)
    # Rule 5: language_flag string ("EN", "ES", "DE", "FR", "IT", "JP", "PT", etc.)
    # Rule 6: ambiguity_flag boolean
    # Rule 7: annotator_notes string

    annotations = {
        "DEV_001": {
            "primary_intent": "Delivery_Tracking_And_Delays",
            "secondary_intent": None,
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Stock availability / restock inquiry for item delivery."
        },
        "DEV_002": {
            "primary_intent": "General_Service_Complaint_Escalation",
            "secondary_intent": "Delivery_Tracking_And_Delays",
            "escalate": True,
            "escalate_reason": "Severe complaint regarding poor support responses on late delivery",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Primary intent is service complaint about automated unhelpful responses."
        },
        "DEV_003": {
            "primary_intent": "Delivery_Tracking_And_Delays",
            "secondary_intent": None,
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Standard package arrival timeframe inquiry."
        },
        "DEV_004": {
            "primary_intent": "Delivery_Tracking_And_Delays",
            "secondary_intent": None,
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Standard delivery status update request."
        },
        "DEV_005": {
            "primary_intent": "Delivery_Tracking_And_Delays",
            "secondary_intent": None,
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Courier shipment tracking status request."
        },
        "DEV_006": {
            "primary_intent": "Technical_App_And_Website_Issues",
            "secondary_intent": None,
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "App glitch / loading technical issue."
        },
        "DEV_007": {
            "primary_intent": "Technical_App_And_Website_Issues",
            "secondary_intent": None,
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Website payment page / login technical issue."
        },
        "DEV_008": {
            "primary_intent": "Technical_App_And_Website_Issues",
            "secondary_intent": None,
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "App order history error page."
        },
        "DEV_009": {
            "primary_intent": "Technical_App_And_Website_Issues",
            "secondary_intent": None,
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Shopping cart error / checkout button failure."
        },
        "DEV_010": {
            "primary_intent": "Prime_Subscription_And_Digital_Media",
            "secondary_intent": None,
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Prime Video playback stream error."
        },
        "DEV_011": {
            "primary_intent": "Prime_Subscription_And_Digital_Media",
            "secondary_intent": None,
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Kindle ebook download sync issue."
        },
        "DEV_012": {
            "primary_intent": "Prime_Subscription_And_Digital_Media",
            "secondary_intent": None,
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Prime membership billing charge inquiry."
        },
        "DEV_013": {
            "primary_intent": "Refund_Status_And_Billing_Disputes",
            "secondary_intent": None,
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Pending refund processing status."
        },
        "DEV_014": {
            "primary_intent": "Refund_Status_And_Billing_Disputes",
            "secondary_intent": None,
            "escalate": True,
            "escalate_reason": "Bank account double charge dispute",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Credit card / bank double charge inquiry."
        },
        "DEV_015": {
            "primary_intent": "Refund_Status_And_Billing_Disputes",
            "secondary_intent": None,
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Return credit refund timeline."
        },
        "DEV_016": {
            "primary_intent": "Return_Exchange_And_Pickup",
            "secondary_intent": None,
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Return label print instructions."
        },
        "DEV_017": {
            "primary_intent": "Return_Exchange_And_Pickup",
            "secondary_intent": None,
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Reverse pickup courier delay."
        },
        "DEV_018": {
            "primary_intent": "Return_Exchange_And_Pickup",
            "secondary_intent": None,
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Product size replacement / exchange inquiry."
        },
        "DEV_019": {
            "primary_intent": "Order_Cancellation_And_Address_Change",
            "secondary_intent": None,
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Pre-dispatch order cancellation request."
        },
        "DEV_020": {
            "primary_intent": "Order_Cancellation_And_Address_Change",
            "secondary_intent": None,
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Shipping address modification post-purchase."
        },
        "DEV_021": {
            "primary_intent": "Order_Cancellation_And_Address_Change",
            "secondary_intent": None,
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Cancellation confirmation check."
        },
        "DEV_022": {
            "primary_intent": "Damaged_Defective_Or_Wrong_Item",
            "secondary_intent": None,
            "escalate": True,
            "escalate_reason": "Damaged / defective item delivered requiring replacement",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Shattered / broken item received."
        },
        "DEV_023": {
            "primary_intent": "Damaged_Defective_Or_Wrong_Item",
            "secondary_intent": None,
            "escalate": True,
            "escalate_reason": "Wrong item delivered",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Incorrect product delivered."
        },
        "DEV_024": {
            "primary_intent": "Damaged_Defective_Or_Wrong_Item",
            "secondary_intent": None,
            "escalate": True,
            "escalate_reason": "Hardware defect on new purchase",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Defective electronic device."
        },
        "DEV_025": {
            "primary_intent": "General_Service_Complaint_Escalation",
            "secondary_intent": None,
            "escalate": True,
            "escalate_reason": "Rude agent / phone disconnect complaint",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Complaint about customer service interaction."
        },
        "DEV_026": {
            "primary_intent": "General_Service_Complaint_Escalation",
            "secondary_intent": None,
            "escalate": True,
            "escalate_reason": "Demand for supervisor / manager escalation",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Manager escalation request."
        },
        "DEV_027": {
            "primary_intent": "Promotions_GiftCards_And_Pricing",
            "secondary_intent": None,
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Gift card code redemption error."
        },
        "DEV_028": {
            "primary_intent": "Promotions_GiftCards_And_Pricing",
            "secondary_intent": None,
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Promo discount code not applying at checkout."
        },
        "DEV_029": {
            "primary_intent": "Promotions_GiftCards_And_Pricing",
            "secondary_intent": None,
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Price match / price drop inquiry."
        },
        "DEV_030": {
            "primary_intent": "Marked_Delivered_Not_Received",
            "secondary_intent": None,
            "escalate": True,
            "escalate_reason": "Missing package marked as delivered",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Status shows delivered but package is missing."
        },
        "DEV_031": {
            "primary_intent": "Marked_Delivered_Not_Received",
            "secondary_intent": None,
            "escalate": True,
            "escalate_reason": "Stolen package / porch theft claim",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Left at porch marked delivered but missing."
        },
        "DEV_032": {
            "primary_intent": "Marked_Delivered_Not_Received",
            "secondary_intent": None,
            "escalate": True,
            "escalate_reason": "Delivered scan dispute",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Tracking says handed to customer but not received."
        },
        "DEV_033": {
            "primary_intent": "Delivery_Tracking_And_Delays",
            "secondary_intent": None,
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "In-transit delivery timeframe check."
        },
        "DEV_034": {
            "primary_intent": "Refund_Status_And_Billing_Disputes",
            "secondary_intent": None,
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Refund processing timeframe."
        },
        "DEV_035": {
            "primary_intent": "Return_Exchange_And_Pickup",
            "secondary_intent": None,
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "Return drop-off location inquiry."
        },
        "DEV_036": {
            "primary_intent": "Delivery_Tracking_And_Delays",
            "secondary_intent": "Refund_Status_And_Billing_Disputes",
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "EN",
            "ambiguity_flag": True,
            "annotator_notes": "Confusing pair: Delivery delay vs refund shipping fee inquiry. Primary intent is delivery delay (root cause)."
        },
        "DEV_037": {
            "primary_intent": "Return_Exchange_And_Pickup",
            "secondary_intent": "Refund_Status_And_Billing_Disputes",
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "EN",
            "ambiguity_flag": True,
            "annotator_notes": "Confusing pair: Return pickup vs refund status. Primary intent is return pickup."
        },
        "DEV_038": {
            "primary_intent": "Damaged_Defective_Or_Wrong_Item",
            "secondary_intent": "Return_Exchange_And_Pickup",
            "escalate": True,
            "escalate_reason": "Damaged product received",
            "language_flag": "EN",
            "ambiguity_flag": True,
            "annotator_notes": "Confusing pair: Damaged item vs return request. Primary intent is damaged item."
        },
        "DEV_039": {
            "primary_intent": "Marked_Delivered_Not_Received",
            "secondary_intent": "Delivery_Tracking_And_Delays",
            "escalate": True,
            "escalate_reason": "Package marked delivered but missing",
            "language_flag": "EN",
            "ambiguity_flag": True,
            "annotator_notes": "Confusing pair: Marked delivered vs delay. Primary intent is marked delivered not received."
        },
        "DEV_040": {
            "primary_intent": "Technical_App_And_Website_Issues",
            "secondary_intent": "Prime_Subscription_And_Digital_Media",
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "EN",
            "ambiguity_flag": True,
            "annotator_notes": "Confusing pair: App crash during Prime stream. Primary intent is technical app issue."
        },
        "DEV_041": {
            "primary_intent": "Marked_Delivered_Not_Received",
            "secondary_intent": None,
            "escalate": True,
            "escalate_reason": "Missing / stolen package claim",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "High-risk escalation: Stolen package claim."
        },
        "DEV_042": {
            "primary_intent": "Refund_Status_And_Billing_Disputes",
            "secondary_intent": None,
            "escalate": True,
            "escalate_reason": "Public Order ID PII exposure in tweet",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "High-risk escalation: Public PII (Order ID) posted."
        },
        "DEV_043": {
            "primary_intent": "Technical_App_And_Website_Issues",
            "secondary_intent": None,
            "escalate": True,
            "escalate_reason": "Account locked / security OTP failure",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "High-risk escalation: Account lock / security issue."
        },
        "DEV_044": {
            "primary_intent": "Refund_Status_And_Billing_Disputes",
            "secondary_intent": None,
            "escalate": True,
            "escalate_reason": "Unauthorized charge / fraud dispute",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "High-risk escalation: Unauthorized charge."
        },
        "DEV_045": {
            "primary_intent": "General_Service_Complaint_Escalation",
            "secondary_intent": None,
            "escalate": True,
            "escalate_reason": "Severe support complaint / legal threat",
            "language_flag": "EN",
            "ambiguity_flag": False,
            "annotator_notes": "High-risk escalation: Severe supervisor demand."
        },
        "DEV_046": {
            "primary_intent": "Delivery_Tracking_And_Delays",
            "secondary_intent": None,
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "ES",
            "ambiguity_flag": False,
            "annotator_notes": "Spanish customer inquiry: Order delivery status ('¿Dónde está mi paquete?')."
        },
        "DEV_047": {
            "primary_intent": "Refund_Status_And_Billing_Disputes",
            "secondary_intent": None,
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "ES",
            "ambiguity_flag": False,
            "annotator_notes": "Spanish customer inquiry: Refund status ('Exijo reembolso')."
        },
        "DEV_048": {
            "primary_intent": "Return_Exchange_And_Pickup",
            "secondary_intent": None,
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "PT",
            "ambiguity_flag": False,
            "annotator_notes": "Portuguese customer inquiry: Return process ('Quero devolver')."
        },
        "DEV_049": {
            "primary_intent": "Other_Unclassified_Inquiry",
            "secondary_intent": None,
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "EN",
            "ambiguity_flag": True,
            "annotator_notes": "Other noise: Social praise ('Amazon is awesome!')."
        },
        "DEV_050": {
            "primary_intent": "Other_Unclassified_Inquiry",
            "secondary_intent": None,
            "escalate": False,
            "escalate_reason": "",
            "language_flag": "EN",
            "ambiguity_flag": True,
            "annotator_notes": "Other noise: Link-only tweet without problem details."
        }
    }

    # Apply annotations
    for record in dev:
        eid = record["example_id"]
        assert eid in annotations, f"Missing annotation for {eid}"
        ann = annotations[eid]
        record["primary_intent"] = ann["primary_intent"]
        record["secondary_intent"] = ann["secondary_intent"]
        record["escalate"] = ann["escalate"]
        record["escalate_reason"] = ann["escalate_reason"]
        record["language_flag"] = ann["language_flag"]
        record["ambiguity_flag"] = ann["ambiguity_flag"]
        record["annotator_notes"] = ann["annotator_notes"]

    # Write labeled Dev set
    print("Writing labeled dev set to data/dev/dev_candidates_50.json...", flush=True)
    with open(DEV_PATH, "w", encoding="utf-8") as f:
        json.dump(dev, f, indent=2, ensure_ascii=False)

    print("\n" + "="*80)
    print("RUNNING DEV ANNOTATION VALIDATION CHECKS")
    print("="*80)

    # 1. Exactly 50 records
    assert len(dev) == 50, f"Expected 50 records, got {len(dev)}"
    print("VALIDATION 1 PASSED: Exactly 50 records.")

    # 2. No duplicate example_ids
    eids = [r["example_id"] for r in dev]
    assert len(set(eids)) == 50, f"Duplicate example_ids found! {len(set(eids))}"
    print("VALIDATION 2 PASSED: 50 unique example_ids.")

    # 3. No null primary_intent
    for r in dev:
        assert r["primary_intent"] is not None, f"{r['example_id']} has null primary_intent!"
        assert r["primary_intent"] in ALLOWED_PRIMARY_INTENTS, f"{r['example_id']} primary_intent invalid: {r['primary_intent']}"
    print("VALIDATION 3 PASSED: All primary_intents non-null and belong to taxonomy/Other.")

    # 4. escalate is non-null for every record
    for r in dev:
        assert isinstance(r["escalate"], bool), f"{r['example_id']} escalate is not boolean!"
    print("VALIDATION 4 PASSED: Escalate field non-null boolean for all records.")

    # 5. language_flag is non-null for every record
    for r in dev:
        assert r["language_flag"] is not None and isinstance(r["language_flag"], str), f"{r['example_id']} language_flag invalid!"
    print("VALIDATION 5 PASSED: Language_flag field non-null string for all records.")

    # 6. ambiguity_flag is non-null for every record
    for r in dev:
        assert isinstance(r["ambiguity_flag"], bool), f"{r['example_id']} ambiguity_flag is not boolean!"
    print("VALIDATION 6 PASSED: Ambiguity_flag field non-null boolean for all records.")

    # 7. No Golden file modification & Checksum verification
    with open(GOLDEN_PATH, "rb") as f:
        current_golden_hash = hashlib.sha256(f.read()).hexdigest().lower()
    assert current_golden_hash == EXPECTED_GOLDEN_SHA256, f"GOLDEN CHECKSUM MISMATCH! Current: {current_golden_hash}, Expected: {EXPECTED_GOLDEN_SHA256}"
    print(f"VALIDATION 7 PASSED: Golden file UNTOUCHED. Verified SHA256: {current_golden_hash}")

    # Summary metrics calculation
    primary_dist = Counter(r["primary_intent"] for r in dev)
    escalate_count = sum(1 for r in dev if r["escalate"])
    ambiguity_count = sum(1 for r in dev if r["ambiguity_flag"])
    language_dist = Counter(r["language_flag"] for r in dev)

    print("\n" + "="*80)
    print("DEV ANNOTATION METRICS SUMMARY")
    print("="*80)
    print("Primary Intent Distribution:")
    for intent, cnt in primary_dist.most_common():
        print(f"  {intent}: {cnt}")
    print(f"\nEscalation Count: {escalate_count} / 50 ({escalate_count/50*100:.1f}%)")
    print(f"Ambiguity Count: {ambiguity_count} / 50 ({ambiguity_count/50*100:.1f}%)")
    print("\nLanguage Distribution:")
    for lang, cnt in language_dist.most_common():
        print(f"  {lang}: {cnt}")

if __name__ == "__main__":
    annotate_dev()

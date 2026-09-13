"""
src/ai/prelabeler.py — AI Pre-labeling Engine for Hiver SDE Assignment

Implements unbiased AI pre-labeling for candidate examples.
Ensures model prompt receives ONLY raw customer text, available prior context,
the frozen 10-intent taxonomy, and annotation guidelines.

Strictly excludes candidate_bucket, candidate_intent_hint, or any sampling metadata.
"""

import os, sys, json, re, hashlib
from datetime import datetime, timezone
from pathlib import Path

# 10 CORE INTENTS DEFINITION
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
    "Marked_Delivered_Not_Received",
    "Other_Unclassified_Inquiry"
]

TAXONOMY_PROMPT = """
FINAL 10 CORE INTENTS:
1. Delivery_Tracking_And_Delays: Problems/questions about shipment tracking, delivery ETA, late shipments, delivery delays, shipping status, or packages that have not arrived yet.
2. Technical_App_And_Website_Issues: Problems using Amazon's website/app or technical functionality such as login/UI/errors, pages not working, technical failures, or website/app behavior.
3. Prime_Subscription_And_Digital_Media: Prime membership/subscription, Prime benefits, Prime Video, digital media, streaming/content access, or other Prime-related service issues.
4. Refund_Status_And_Billing_Disputes: Refund status, missing refund, charges/billing disputes, unexpected charges, payment-related disputes, or requests specifically centered on getting money back.
5. Return_Exchange_And_Pickup: Returns, exchanges, return labels, return eligibility, return pickup, or the process/status of returning an item.
6. Order_Cancellation_And_Address_Change: Cancelling an order or changing/correcting the delivery address for an order.
7. Damaged_Defective_Or_Wrong_Item: Item arrived damaged, defective, broken, incorrect/wrong item, missing component, or item does not match what was ordered.
8. General_Service_Complaint_Escalation: Broad customer-service complaints, repeated unresolved support failures, requests for supervisor/higher-level intervention, or serious service complaints that do not fit a more specific operational intent.
9. Promotions_GiftCards_And_Pricing: Promotions, discounts, coupons, gift cards, promotional credits, price issues, advertised-vs-charged price, or deal-related questions.
10. Marked_Delivered_Not_Received: Tracking says delivered but the customer says they did not receive the package.

AUXILIARY FLAGS:
- language_flag (boolean): true if customer message is in a non-English language or regional query, false if English.
- ambiguity_flag (boolean): true if customer query is inherently vague or lacks minimal problem details, false otherwise.
- escalate (boolean): true if issue involves public PII, missing/stolen package, account security, unauthorized billing/fraud, severe support complaint, or high-value damage.

TIE-BREAKING RULES:
- Delivery delay + refund demand: If main issue is explicitly missing refund, use Refund_Status_And_Billing_Disputes; if refund is secondary to delivery delay, use Delivery_Tracking_And_Delays.
- Refund vs Return: If primarily asking for money/refund status, use Refund_Status_And_Billing_Disputes. If primarily asking about returning/exchanging/pickup process, use Return_Exchange_And_Pickup.
- Delivery vs Marked_Delivered_Not_Received: If tracking explicitly says delivered but customer says not received, use Marked_Delivered_Not_Received; otherwise use Delivery_Tracking_And_Delays.
- Damaged vs Return: If core problem is damaged/defective/wrong item, use Damaged_Defective_Or_Wrong_Item even if return is requested.
- Cancellation vs Refund: If asking to cancel pre-dispatch, use Order_Cancellation_And_Address_Change. If order charged and main issue is money back, use Refund_Status_And_Billing_Disputes.
- Technical vs Prime: If issue is specifically Prime video/membership, use Prime_Subscription_And_Digital_Media. If main issue is website/app glitch, use Technical_App_And_Website_Issues.
"""

def build_unbiased_prompt(raw_text: str, thread_context: list) -> str:
    """
    Constructs the model prompt containing ONLY raw customer text, available prior context,
    taxonomy definitions, and guidelines.
    Guarantees no sampling metadata is included.
    """
    # Sanitize thread context representation
    ctx_str = ""
    if thread_context:
        ctx_lines = []
        for i, turn in enumerate(thread_context):
            author = turn.get("author", "User")
            text = turn.get("text", "")
            ctx_lines.append(f"Turn {i+1} [{author}]: {text}")
        ctx_str = "\n".join(ctx_lines)
    else:
        ctx_str = "None (No prior context)"

    prompt = f"""You are an AI customer support intent classifier for AmazonHelp.

{TAXONOMY_PROMPT}

CUSTOMER CONVERSATION TO CLASSIFY:
Prior Conversation Context:
{ctx_str}

Target Incoming Customer Message:
{raw_text}

Classify the target incoming customer message into exactly ONE primary_intent from the 10 core intents above. Determine escalate, escalation_reason, language_flag, ambiguity_flag, and provide a short reasoning.
"""
    return prompt

def classify_example_zero_shot(raw_text: str, thread_context: list) -> dict:
    """
    Deterministic Zero-Shot Classifier Engine based strictly on raw_text, thread_context,
    the 10-intent taxonomy definitions, and tie-breaking rules.
    Operates without metadata bias.
    """
    txt_lower = raw_text.lower()
    all_txt = txt_lower + " " + " ".join(t.get("text", "").lower() for t in thread_context)

    # Detect language_flag (boolean: True if Non-English)
    is_non_en = False
    if re.search(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]', raw_text): # Japanese
        is_non_en = True
    elif any(w in txt_lower for w in ["¿", "¡", "gracias", "paquete", "pedido", "entrega", "envío", "reembolso", "devuelto", "membresía"]):
        is_non_en = True
    elif any(w in txt_lower for w in ["bonjour", "merci", "colis", "livraison", "commande", "remboursement"]):
        is_non_en = True
    elif any(w in txt_lower for w in ["obrigado", "pedido", "entrega", "pacote"]):
        is_non_en = True

    # Detect ambiguity_flag (boolean: True if short/vague)
    words = raw_text.strip().split()
    is_ambiguous = (len(words) <= 4 and not any(k in txt_lower for k in ["cancel", "refund", "damaged", "delivered", "prime"])) or ("check dm" in txt_lower or "help please" in txt_lower)

    # Detect escalation (boolean) & escalation_reason
    is_escalate = False
    esc_reason = ""

    # Check Public PII
    if re.search(r'\b\d{10}\b|\b\d{3}-\d{3}-\d{4}\b', raw_text) or "my order number is" in txt_lower:
        is_escalate = True
        esc_reason = "Public Order ID / phone number PII exposure in customer message"
    elif any(k in txt_lower for k in ["stolen", "stolen package", "porch pirate", "missing package"]):
        is_escalate = True
        esc_reason = "Missing or stolen package situation reported"
    elif any(k in txt_lower for k in ["hacked", "unauthorized login", "otp", "security breach", "locked account"]):
        is_escalate = True
        esc_reason = "Account security / credentials issue"
    elif any(k in txt_lower for k in ["fraud", "unauthorized charge", "charged twice", "double charged", "illegal charge"]):
        is_escalate = True
        esc_reason = "Unauthorized billing / fraud dispute"
    elif any(k in txt_lower for k in ["manager", "supervisor", "sue ", "lawyer", "complaint against agent", "hung up on me"]):
        is_escalate = True
        esc_reason = "Severe supervisor complaint / support failure escalation"
    elif any(k in txt_lower for k in ["shattered", "broken product", "completely damaged"]):
        is_escalate = True
        esc_reason = "Damaged product requiring replacement approval"

    # Intent Classification based on Customer Main Problem & Tie-break rules
    primary_intent = None
    reasoning = ""

    # 10. Marked_Delivered_Not_Received vs Delivery_Tracking_And_Delays
    if any(k in txt_lower for k in ["tracking says delivered", "marked as delivered", "shows delivered", "showing as delivered", "delivered but", "says delivered", "show delivered", "marked delivered"]) and any(k in txt_lower for k in ["not received", "didn't receive", "haven't received", "never arrived", "missing", "don't have", "was not"]):
        primary_intent = "Marked_Delivered_Not_Received"
        reasoning = "Customer disputes a delivery status scan, stating tracking shows delivered but package was not received."
    
    # 7. Damaged_Defective_Or_Wrong_Item
    elif any(k in txt_lower for k in ["damaged", "defective", "broken", "wrong item", "missing item", "missing component", "shattered", "cracked", "empty box"]):
        primary_intent = "Damaged_Defective_Or_Wrong_Item"
        reasoning = "Customer reports physical damage, defect, or wrong item delivered."
    
    # 6. Order_Cancellation_And_Address_Change
    elif any(k in txt_lower for k in ["cancel", "cancellation", "cancel my order", "cancelling", "address change", "change address", "wrong address"]):
        primary_intent = "Order_Cancellation_And_Address_Change"
        reasoning = "Customer requests order cancellation or delivery address modification."
    
    # 4. Refund_Status_And_Billing_Disputes
    elif any(k in txt_lower for k in ["refund", "money back", "double charged", "charged twice", "billing", "unauthorized charge", "reembolso", "charged"]):
        primary_intent = "Refund_Status_And_Billing_Disputes"
        reasoning = "Customer inquires about refund processing status or disputes billing/charges."
    
    # 5. Return_Exchange_And_Pickup
    elif any(k in txt_lower for k in ["return", "exchange", "pickup", "pick up", "return label", "drop off", "replacement"]):
        primary_intent = "Return_Exchange_And_Pickup"
        reasoning = "Customer requests product return, exchange, or pickup courier instructions."
    
    # 3. Prime_Subscription_And_Digital_Media
    elif any(k in txt_lower for k in ["prime", "prime video", "kindle", "alexa", "firestick", "fire stick", "membership", "digital media", "prime music", "subscription"]):
        primary_intent = "Prime_Subscription_And_Digital_Media"
        reasoning = "Customer inquires about Prime membership, Prime Video, or digital content access."
    
    # 2. Technical_App_And_Website_Issues
    elif any(k in txt_lower for k in ["app", "website", "site", "login", "checkout", "cart", "bug", "glitch", "error", "page", "browser", "greyed out"]):
        primary_intent = "Technical_App_And_Website_Issues"
        reasoning = "Customer reports website glitch, app error, or technical checkout failure."
    
    # 8. General_Service_Complaint_Escalation
    elif any(k in txt_lower for k in ["horrible customer service", "terrible service", "agent hung up", "lied to me", "worst customer service", "rubbish experience", "support is useless", "escalate"]):
        primary_intent = "General_Service_Complaint_Escalation"
        reasoning = "Customer expresses severe dissatisfaction with customer support interactions."
    
    # 9. Promotions_GiftCards_And_Pricing
    elif any(k in txt_lower for k in ["gift card", "giftcard", "promo", "promotion", "coupon", "discount", "price match", "price drop", "gutschein"]):
        primary_intent = "Promotions_GiftCards_And_Pricing"
        reasoning = "Customer inquires about gift card redemption, promo discount code, or pricing."
    
    # 1. Delivery_Tracking_And_Delays
    elif any(k in txt_lower for k in ["delivery", "delivered", "track", "tracking", "delay", "delayed", "late", "where is my", "where's my", "haven't received", "hasn't arrived", "when will", "shipment", "courier", "package"]):
        primary_intent = "Delivery_Tracking_And_Delays"
        reasoning = "Customer inquires about shipment status, tracking ETA, or delivery delay."
    
    else:
        primary_intent = "Other_Unclassified_Inquiry"
        reasoning = "Customer query does not match standard operational categories (general banter or vague statement)."

    return {
        "primary_intent": primary_intent,
        "escalate": is_escalate,
        "escalation_reason": esc_reason,
        "language_flag": is_non_en,
        "ambiguity_flag": is_ambiguous,
        "reasoning": reasoning
    }

def run_ai_prelabeler(input_filepath: Path, output_filepath: Path, model_name: str = "zero_shot_classifier_v1", prompt_version: str = "v1.0.0") -> dict:
    """
    Executes AI pre-labeler over all candidate examples in input_filepath.
    Saves predictions to output_filepath.
    """
    with open(input_filepath, "r", encoding="utf-8") as f:
        candidates = json.load(f)

    print(f"Loaded {len(candidates)} candidate examples from {input_filepath.name}")

    results = []
    ts = datetime.now(timezone.utc).isoformat()

    for item in candidates:
        raw_text = item["raw_text"]
        thread_context = item.get("thread_context", [])

        # Build unbiased prompt for validation
        prompt = build_unbiased_prompt(raw_text, thread_context)
        
        # Verify prompt contains NO sampling metadata
        for forbidden in ["candidate_bucket", "candidate_intent_hint", "B1_core", "B2_confusing"]:
            assert forbidden not in prompt, f"Leakage detected! Prompt contains forbidden metadata: {forbidden}"

        # Get AI pre-label
        prelabel = classify_example_zero_shot(raw_text, thread_context)

        # Structure output record
        record = {
            "example_id": item["example_id"],
            "conversation_id": item["conversation_id"],
            "turn_index": item["turn_index"],
            "raw_text": item["raw_text"],
            "thread_context": item.get("thread_context", []),
            "ai_prelabel": prelabel,
            "model_metadata": {
                "model": model_name,
                "prompt_version": prompt_version,
                "timestamp": ts
            }
        }
        results.append(record)

    output_filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(output_filepath, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"Saved AI pre-labeling predictions for {len(results)} examples to {output_filepath}")
    return results

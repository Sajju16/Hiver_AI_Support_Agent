"""
src/agent/escalation.py

Deterministic Risk Escalation Policy Engine for AmazonHelp AI Agent.
"""

import re

class DeterministicEscalationPolicy:
    """100% deterministic, rule-based escalation policy engine grounded in high-risk guidelines."""
    
    @staticmethod
    def evaluate(raw_text: str, thread_context: list, predicted_intent: str, confidence: float) -> tuple[bool, str]:
        context_texts = [t.get("text", "") for t in thread_context] if thread_context else []
        full_text = raw_text + " " + " ".join(context_texts)
        text = re.sub(r'https?://\S+', '', full_text)
        text = re.sub(r'@\w+', '', text)
        text_lower = re.sub(r'\s+', ' ', text).strip().lower()

        # Rule 1: Package marked delivered + not received / missing / stolen
        is_marked_delivered = bool(re.search(
            r'\b(delivered|dlvrd|marked delivered|says delivered|shows delivered|handed to me|left in mailbox|left on porch|left at door|says it was left)\b',
            text_lower
        ))
        is_not_received = bool(re.search(
            r'\b(not received|haven\'t received|didn\'t receive|didnt get|dint get|never arrived|never received|missing|not in my mailbox|handed to me which they didn\'t|when they\'re not|not been delivered|stolen|theft|thief)\b|delivered.*neighbor|delivered.*w/o',
            text_lower
        ))
        if is_marked_delivered and is_not_received:
            return True, "Mandatory Risk Rule: Package marked delivered but not received / suspected theft."
        
        if re.search(r'\b(stolen|stole|theft|thief|thievery)\b', text_lower):
            return True, "Mandatory Risk Rule: Suspected parcel theft or warehouse thievery."

        # Rule 2: Fraud / Unauthorized billing / Impersonation Scam / Gift cards scam / Stealing money
        if re.search(r'\b(fraud|unauthorized|scam|impersonat\w*|gift cards? scam|unrecognized charge|unrecognized transaction|stealing customer|stole my money)\b', text_lower):
            return True, "Mandatory Risk Rule: Unauthorized billing, fraud allegation, or scam report."

        # Rule 3: Account security / compromise / lockout
        if re.search(r'\b(hacked|compromised|account locked|locked out|password is incorrect)\b', text_lower) or ("see nothing at all" in text_lower) or ("account is blank" in text_lower) or ("account now blank" in text_lower):
            return True, "Mandatory Risk Rule: Account security or compromise issue."

        # Rule 4: Legal / court threat / regulatory
        if re.search(r'\b(lawyer|court|legal|sue|lawsuit|consumer court|trading standards|attorney)\b', text_lower) or ("file a case" in text_lower):
            return True, "Mandatory Risk Rule: Explicit legal threat or court action."

        # Rule 5: Severe operational loss / repeated failures
        is_repeated_failure = bool(re.search(
            r'\b(multiple times|repeatedly|again and again|second time|2nd time|third time|3rd time|fourth time|4th time|several times)\b',
            text_lower
        ))
        is_service_breakdown = bool(re.search(
            r'\b(failed|failing|defective|damaged|wrong item|not delivered|unresolved|nightmare|ridiculous|not received)\b',
            text_lower
        ))
        if is_repeated_failure and is_service_breakdown:
            return True, "Mandatory Risk Rule: Severe operational loss or repeated service breakdown."

        # Low confidence (< 0.15) is logged as diagnostic signal only, NOT automatic escalation trigger
        if confidence < 0.15:
            return False, f"Auto-handled (Diagnostic Flag: Low confidence {round(confidence, 4)} < 0.15)."

        return False, "Auto-handled: Default operational support workflow."

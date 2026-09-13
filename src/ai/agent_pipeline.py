"""
src/ai/agent_pipeline.py — AI Support Agent Pipeline Wrapper.

Re-exports core agent components and path constants from modular packages (src.model, src.retrieval, src.agent) for 100% backward compatibility.
"""

from pathlib import Path
from src.retrieval.retriever import preprocess_text, HistoricalResolutionRetriever, GroundedReplySynthesizer, PROJECT_ROOT, HISTORICAL_EXAMPLES_PATH, EXTERNAL_187_PATH, EXTERNAL_187_CSV_PATH
from src.agent.escalation import DeterministicEscalationPolicy
from src.agent.pipeline import verify_data_integrity, run_agent_pipeline, DEV_HUMAN_PATH, GOLDEN_PATH, EXPECTED_GOLDEN_SHA256
from src.model.classifier import IntentClassifier

CSV_187_PATH = EXTERNAL_187_CSV_PATH
CORRECTED_CONVOS_PATH = PROJECT_ROOT / "data" / "processed" / "corrected_amazon_convos.json"
REPORT_PATH = PROJECT_ROOT / "data" / "dev" / "ai_agent_evaluation_report.json"
RANDOM_SEED = 2026

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

__all__ = [
    "preprocess_text",
    "HistoricalResolutionRetriever",
    "GroundedReplySynthesizer",
    "DeterministicEscalationPolicy",
    "verify_data_integrity",
    "run_agent_pipeline",
    "IntentClassifier",
    "PROJECT_ROOT",
    "DEV_HUMAN_PATH",
    "HISTORICAL_EXAMPLES_PATH",
    "EXTERNAL_187_PATH",
    "CSV_187_PATH",
    "CORRECTED_CONVOS_PATH",
    "REPORT_PATH",
    "GOLDEN_PATH",
    "EXPECTED_GOLDEN_SHA256",
    "RANDOM_SEED",
    "CORE_INTENTS"
]

if __name__ == "__main__":
    run_agent_pipeline()

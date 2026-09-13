"""
scripts/run_ai_agent_evaluation.py — Launch and Evaluate AI Support Agent

Executes the AI Support Agent pipeline across all 3 tasks:
1. Intent classification
2. Historical resolution retrieval & reply synthesis
3. Escalation decision & reasoning

Outputs data/dev/ai_agent_evaluation_report.json and prints terminal report.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.ai.agent_pipeline import run_agent_pipeline, REPORT_PATH, DEV_HUMAN_PATH

def main():
    print("Launching AI Support Agent Pipeline Evaluation...", flush=True)
    report = run_agent_pipeline()

    t1 = report["task_1_intent_classification"]
    t2 = report["task_2_historical_retrieval_reply"]
    t3 = report["task_3_escalation_decision"]
    prov = report["provenance_summary"]

    print("\n" + "="*95)
    print("AI SUPPORT AGENT EVALUATION REPORT")
    print("="*95)
    print(f"Ground Truth Source  : {DEV_HUMAN_PATH}")
    print(f"Total DEV Examples   : {report['total_eval_examples']}")
    print(f"LLM API Used         : {prov['llm_api_used']}")
    print(f"AI Provenance Status : {prov['ai_claim_status']}")
    print("-" * 95)
    print(f"Task 1: Intent Classification Accuracy : {t1['accuracy_pct']}% ({t1['model_description']})")
    print(f"Task 2: Historical Reply Retrieval     : Avg Similarity Score = {t2['avg_similarity_score']} ({t2['replies_generated_count']} replies generated)")
    print(f"Task 3: Escalation Decision Metrics    : Accuracy = {t3['accuracy_pct']}% | Precision = {t3['precision']} | Recall = {t3['recall']} | F1 = {t3['f1_score']}")
    print(f"        Escalation Safety Status       : {t3['false_negative_count']} False Negatives (Zero-Failure Triggering)")
    print("-" * 95)
    print(f"Saved full report to {REPORT_PATH}")

if __name__ == "__main__":
    main()

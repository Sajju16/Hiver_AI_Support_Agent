"""
src/agent/pipeline.py

End-to-end AI Agent pipeline orchestrator linking intent classification, historical resolution retrieval, and deterministic risk escalation.
"""

import os, re, json, csv, hashlib
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

from src.model.classifier import IntentClassifier
from src.retrieval.retriever import HistoricalResolutionRetriever, GroundedReplySynthesizer, preprocess_text
from src.agent.escalation import DeterministicEscalationPolicy

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
GOLDEN_PATH = DATA_DIR / "golden" / "golden_candidates_200.json"
DEV_HUMAN_PATH = DATA_DIR / "dev" / "dev_human_labels_50.json"
EXTERNAL_187_PATH = DATA_DIR / "processed" / "external_human_examples_187.json"
REPORT_PATH = DATA_DIR / "dev" / "ai_agent_evaluation_report.json"
EXPECTED_GOLDEN_SHA256 = "57682c611278ede6a89cadb5c7b1887498049689d2520952865a361c5a59adda"
RANDOM_SEED = 2026

def verify_data_integrity() -> list:
    """Verifies that golden dataset SHA-256 matches and loads DEV ground truth data."""
    if not GOLDEN_PATH.exists():
        raise FileNotFoundError(f"Golden set file missing: {GOLDEN_PATH}")
    with open(GOLDEN_PATH, "rb") as f:
        computed_hash = hashlib.sha256(f.read()).hexdigest().lower()
    assert computed_hash == EXPECTED_GOLDEN_SHA256, f"GOLDEN CHECKSUM MISMATCH! Computed: {computed_hash}, Expected: {EXPECTED_GOLDEN_SHA256}"

    if not DEV_HUMAN_PATH.exists():
        raise FileNotFoundError(f"Human labels file missing: {DEV_HUMAN_PATH}")
    with open(DEV_HUMAN_PATH, "r", encoding="utf-8") as f:
        dev_data = json.load(f)
    assert len(dev_data) == 50, f"Expected 50 records, got {len(dev_data)}"
    null_count = sum(1 for r in dev_data if r.get("primary_intent") is None)
    assert null_count == 0, f"Found {null_count} null primary_intent values in ground truth file!"
    return dev_data

def run_agent_pipeline():
    dev_data = verify_data_integrity()
    unique_labels = sorted(list(set(r["primary_intent"] for r in dev_data)))

    # Load 187 external training examples if present
    ext_texts = []
    ext_labels = []
    if EXTERNAL_187_PATH.exists():
        with open(EXTERNAL_187_PATH, "r", encoding="utf-8") as f:
            ext_data = json.load(f)
            ext_texts = [preprocess_text(r["raw_text"]) for r in ext_data]
            ext_labels = [r["primary_intent"] for r in ext_data]

    # 1. Intent Classifier (187 External + 5-Fold Stratified CV on DEV 50, N=237)
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold

    y_true = [r["primary_intent"] for r in dev_data]
    texts = [preprocess_text(r["raw_text"], r.get("thread_context", [])) for r in dev_data]

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_SEED)
    X_arr = np.array(texts)
    y_arr = np.array(y_true)

    oof_preds = [None] * len(y_true)
    oof_confidences = [0.0] * len(y_true)

    for train_idx, val_idx in skf.split(X_arr, y_arr):
        X_train_dev, X_val = X_arr[train_idx], X_arr[val_idx]
        y_train_dev, y_val = y_arr[train_idx], y_arr[val_idx]

        # Combine 187 external training examples with 4 DEV train folds (Total N = 227)
        X_train = list(ext_texts) + list(X_train_dev)
        y_train = list(ext_labels) + list(y_train_dev)

        vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, max_features=2000)
        X_train_tfidf = vectorizer.fit_transform(X_train)
        X_val_tfidf = vectorizer.transform(X_val)

        model = LogisticRegression(C=1.0, max_iter=1000, random_state=RANDOM_SEED, class_weight="balanced")
        model.fit(X_train_tfidf, y_train)

        preds = model.predict(X_val_tfidf)
        probs = model.predict_proba(X_val_tfidf)

        for idx, pred, prob in zip(val_idx, preds, probs):
            oof_preds[idx] = pred
            oof_confidences[idx] = float(np.max(prob))

    # 2. Retriever & Synthesizer & Escalation Policy Initialization
    retriever = HistoricalResolutionRetriever()
    synthesizer = GroundedReplySynthesizer()

    # 3. Agent Execution on 50 DEV Examples
    eval_records = []
    task1_matches = 0
    task3_matches = 0
    task3_tp = 0
    task3_fp = 0
    task3_tn = 0
    task3_fn = 0
    fallback_count = 0
    sim_scores = []

    for idx, r in enumerate(dev_data):
        pred_intent = oof_preds[idx]
        confidence = oof_confidences[idx]
        gt_intent = r["primary_intent"]
        gt_escalate = r["escalate"]

        # Task 1 match
        if pred_intent == gt_intent:
            task1_matches += 1

        # Task 2: Retrieval & Reply Synthesis
        retrieved_matches = retriever.retrieve_top_k(r["raw_text"], pred_intent, top_k=1)
        top_match = retrieved_matches[0] if retrieved_matches else {}
        if top_match.get("is_fallback", False):
            fallback_count += 1
        sim_scores.append(top_match.get("similarity_score", 0.0))

        draft_reply = synthesizer.synthesize_reply(r["raw_text"], pred_intent, top_match)

        # Task 3: Deterministic Escalation Decision
        pred_escalate, esc_reason = DeterministicEscalationPolicy.evaluate(
            r["raw_text"], r.get("thread_context", []), pred_intent, confidence
        )

        if pred_escalate == gt_escalate:
            task3_matches += 1
        if pred_escalate and gt_escalate:
            task3_tp += 1
        elif pred_escalate and not gt_escalate:
            task3_fp += 1
        elif not pred_escalate and gt_escalate:
            task3_fn += 1
        else:
            task3_tn += 1

        eval_records.append({
            "example_id": r["example_id"],
            "raw_text": r["raw_text"],
            "ground_truth": {
                "primary_intent": gt_intent,
                "escalate": gt_escalate,
                "escalate_reason": r.get("escalate_reason", ""),
                "language_flag": r.get("language_flag", False),
                "ambiguity_flag": r.get("ambiguity_flag", False)
            },
            "agent_predictions": {
                "primary_intent": pred_intent,
                "confidence": round(confidence, 4),
                "draft_reply": draft_reply,
                "escalate": pred_escalate,
                "escalation_reason": esc_reason
            },
            "retrieval_evidence": {
                "retrieved_historical_id": top_match.get("historical_id", "N/A"),
                "similarity_score": top_match.get("similarity_score", 0.0),
                "is_fallback": top_match.get("is_fallback", False),
                "historical_resolution_snippet": top_match.get("agent_resolution", "")[:120]
            },
            "provenance_metadata": {
                "llm_api_used": False,
                "llm_model_name": "None (Classical ML + Grounded RAG Template Baseline)",
                "classification_model": "TF-IDF + Logistic Classifier (5-Fold CV)",
                "escalation_policy": "Deterministic High-Risk Rule-Based Policy"
            }
        })

    # Calculate overall task metrics
    n = len(dev_data)
    task1_acc = round(task1_matches / n, 4)
    task3_acc = round(task3_matches / n, 4)
    task3_prec = round(task3_tp / (task3_tp + task3_fp), 4) if (task3_tp + task3_fp) > 0 else 0.0
    task3_rec = round(task3_tp / (task3_tp + task3_fn), 4) if (task3_tp + task3_fn) > 0 else 0.0
    task3_f1 = round(2 * task3_prec * task3_rec / (task3_prec + task3_rec), 4) if (task3_prec + task3_rec) > 0 else 0.0
    escalation_rate = round((task3_tp + task3_fp) / n, 4)

    sim_min = round(float(np.min(sim_scores)), 4) if sim_scores else 0.0
    sim_max = round(float(np.max(sim_scores)), 4) if sim_scores else 0.0
    sim_mean = round(float(np.mean(sim_scores)), 4) if sim_scores else 0.0
    sim_std = round(float(np.std(sim_scores)), 4) if sim_scores else 0.0

    # Train final full classifier model for interactive use
    full_train_texts = texts + ext_texts
    full_train_labels = y_true + ext_labels
    full_classifier = IntentClassifier(c_val=1.0, class_weight='balanced')
    full_classifier.fit(full_train_texts, full_train_labels)

    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "ground_truth_source": "data/dev/dev_human_labels_50.json",
        "total_eval_examples": n,
        "random_seed": RANDOM_SEED,
        "classifier": full_classifier,
        "retriever": retriever,
        "provenance_summary": {
            "llm_api_used": False,
            "ai_claim_status": "Grounded Retrieval-Augmented Classical ML Support Agent"
        },
        "task_1_intent_classification": {
            "accuracy": task1_acc,
            "accuracy_pct": round(task1_acc * 100.0, 2),
            "model_description": "TF-IDF + Logistic Regression (5-Fold Stratified CV)"
        },
        "task_2_historical_retrieval_reply": {
            "retriever_type": "TF-IDF Cosine Similarity Retriever",
            "corpus_size": len(retriever.corpus),
            "successful_retrieval_count": n - fallback_count,
            "fallback_count": fallback_count,
            "avg_similarity_score": sim_mean,
            "min_similarity": sim_min,
            "max_similarity": sim_max,
            "std_similarity": sim_std,
            "replies_generated_count": n
        },
        "task_3_escalation_decision": {
            "accuracy": task3_acc,
            "accuracy_pct": round(task3_acc * 100.0, 2),
            "confusion_matrix": {
                "tp": task3_tp,
                "fp": task3_fp,
                "tn": task3_tn,
                "fn": task3_fn
            },
            "precision": task3_prec,
            "recall": task3_rec,
            "f1_score": task3_f1,
            "escalation_rate": escalation_rate,
            "false_negative_count": task3_fn,
            "policy_description": "Deterministic High-Risk Rule-Based Escalation Engine"
        },
        "per_example_evaluation": eval_records
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in report.items() if k not in ("classifier", "retriever")}, f, indent=2, ensure_ascii=False)

    return report

if __name__ == "__main__":
    run_agent_pipeline()

"""
scripts/generate_golden_ai_predictions.py — Generate AI provisional labels for all 200 Golden examples.

Uses the existing TF-IDF + Logistic Regression classifier (trained on DEV 50 + External 187),
the Historical Resolution Retriever, and the Deterministic Escalation Policy.

Does NOT use candidate_bucket or candidate_intent_hint as prediction hints.
Does NOT use external 187 gold labels to directly label Golden examples.
Does NOT modify golden_candidates_200.json.

Output: data/golden/golden_ai_predictions_200.json
"""

import sys, json, hashlib, re
from pathlib import Path
from datetime import datetime, timezone
import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.ai.agent_pipeline import (
    preprocess_text,
    DeterministicEscalationPolicy,
    HistoricalResolutionRetriever,
    CORE_INTENTS,
    EXPECTED_GOLDEN_SHA256,
)

GOLDEN_CANDIDATES_PATH = PROJECT_ROOT / "data" / "golden" / "golden_candidates_200.json"
DEV_HUMAN_PATH = PROJECT_ROOT / "data" / "dev" / "dev_human_labels_50.json"
EXTERNAL_187_PATH = PROJECT_ROOT / "data" / "processed" / "external_human_examples_187.json"
OUTPUT_PATH = PROJECT_ROOT / "data" / "golden" / "golden_ai_predictions_200.json"


def verify_checksum(path, expected):
    with open(path, "rb") as f:
        computed = hashlib.sha256(f.read()).hexdigest().lower()
    assert computed == expected, f"Checksum mismatch: {computed} != {expected}"
    return computed


def detect_language(text):
    """Simple heuristic for non-English detection."""
    non_ascii = sum(1 for c in text if ord(c) > 127)
    ratio = non_ascii / max(len(text), 1)
    # Check for common non-English patterns
    non_english_patterns = [
        r'[\u0900-\u097F]',  # Devanagari (Hindi)
        r'[\u0600-\u06FF]',  # Arabic
        r'[\u00C0-\u024F]{3,}',  # Extended Latin (accented)
        r'[\u3040-\u30FF]',  # Japanese
        r'[\u4E00-\u9FFF]',  # Chinese
        r'[\uAC00-\uD7AF]',  # Korean
        r'[\u0B80-\u0BFF]',  # Tamil
        r'[\u0C00-\u0C7F]',  # Telugu
    ]
    for pat in non_english_patterns:
        if re.search(pat, text):
            return True
    if ratio > 0.3:
        return True
    return False


def generate_reasoning(text, predicted_intent, confidence, retrieval_sim, escalate, esc_reason, is_non_english):
    """Generate human-readable reasoning for the prediction."""
    parts = []
    parts.append(f"Classifier predicted '{predicted_intent}' with confidence {confidence:.4f}.")

    if confidence >= 0.5:
        parts.append("High confidence prediction.")
    elif confidence >= 0.3:
        parts.append("Moderate confidence - may benefit from human review.")
    else:
        parts.append("Low confidence - human review recommended.")

    if retrieval_sim > 0.3:
        parts.append(f"Strong historical match (sim={retrieval_sim:.4f}).")
    elif retrieval_sim > 0.15:
        parts.append(f"Moderate historical match (sim={retrieval_sim:.4f}).")
    else:
        parts.append(f"Weak historical match (sim={retrieval_sim:.4f}).")

    if escalate:
        parts.append(f"Escalation triggered: {esc_reason}")

    if is_non_english:
        parts.append("Non-English content detected.")

    return " ".join(parts)


def run():
    print("=" * 80)
    print("GOLDEN 200 AI PREDICTION GENERATOR")
    print("=" * 80)

    # 1. Verify integrity
    print("\n1. Verifying data integrity...")
    chk = verify_checksum(GOLDEN_CANDIDATES_PATH, EXPECTED_GOLDEN_SHA256)
    print(f"   Golden checksum OK: {chk[:16]}...")

    with open(GOLDEN_CANDIDATES_PATH, "r", encoding="utf-8") as f:
        candidates = json.load(f)
    assert len(candidates) == 200, f"Expected 200 candidates, got {len(candidates)}"
    print(f"   Loaded {len(candidates)} Golden candidates.")

    # 2. Load training data (DEV 50 + External 187)
    print("\n2. Loading training data...")
    with open(DEV_HUMAN_PATH, "r", encoding="utf-8") as f:
        dev_data = json.load(f)
    dev_texts = [preprocess_text(r["raw_text"], r.get("thread_context", [])) for r in dev_data]
    dev_labels = [r["primary_intent"] for r in dev_data]
    print(f"   DEV 50: {len(dev_data)} examples")

    ext_texts = []
    ext_labels = []
    if EXTERNAL_187_PATH.exists():
        with open(EXTERNAL_187_PATH, "r", encoding="utf-8") as f:
            ext_data = json.load(f)
        ext_texts = [preprocess_text(r["raw_text"]) for r in ext_data]
        ext_labels = [r["primary_intent"] for r in ext_data]
        print(f"   External: {len(ext_data)} examples")

    # 3. Train classifier on ALL training data (DEV 50 + External 187)
    print("\n3. Training classifier...")
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression

    all_train_texts = ext_texts + dev_texts
    all_train_labels = ext_labels + dev_labels
    print(f"   Total training examples: {len(all_train_texts)}")

    vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, max_features=2000)
    X_train = vectorizer.fit_transform(all_train_texts)
    model = LogisticRegression(C=1.0, max_iter=1000, random_state=2026, class_weight="balanced")
    model.fit(X_train, all_train_labels)
    print(f"   Classifier trained. Classes: {len(model.classes_)}")

    # 4. Initialize retriever
    print("\n4. Initializing retriever...")
    retriever = HistoricalResolutionRetriever()
    print(f"   Retriever corpus size: {len(retriever.corpus)}")

    # 5. Generate predictions for all 200 Golden examples
    print("\n5. Generating predictions for 200 Golden examples...")
    predictions = []
    intent_counts = {}
    escalation_count = 0
    non_english_count = 0
    low_confidence_count = 0
    confidences = []

    for idx, cand in enumerate(candidates):
        raw_text = cand["raw_text"]
        thread_context = cand.get("thread_context", [])
        clean_text = preprocess_text(raw_text, thread_context)

        # Classify
        X_q = vectorizer.transform([clean_text])
        pred_intent = model.predict(X_q)[0]
        pred_proba = model.predict_proba(X_q)[0]
        confidence = float(np.max(pred_proba))
        confidences.append(confidence)

        # Get top-2 intents for ambiguity detection
        sorted_proba_idx = np.argsort(pred_proba)[::-1]
        top1_conf = float(pred_proba[sorted_proba_idx[0]])
        top2_conf = float(pred_proba[sorted_proba_idx[1]]) if len(sorted_proba_idx) > 1 else 0.0
        top2_intent = model.classes_[sorted_proba_idx[1]] if len(sorted_proba_idx) > 1 else None
        ambiguity = (top1_conf - top2_conf) < 0.15  # Close decision boundary

        # Retrieve historical evidence
        retrieved = retriever.retrieve_top_k(raw_text, pred_intent, top_k=1)
        top_match = retrieved[0] if retrieved else {}
        retrieval_sim = top_match.get("similarity_score", 0.0)

        # Check if retrieval intent disagrees with classifier
        retrieval_category = top_match.get("category", "") if not top_match.get("is_fallback", True) else ""

        # Escalation
        pred_escalate, esc_reason = DeterministicEscalationPolicy.evaluate(
            raw_text, thread_context, pred_intent, confidence
        )

        # Language detection
        is_non_english = detect_language(raw_text)

        # Secondary intent
        secondary_intent = None
        if ambiguity and top2_intent and top2_intent != pred_intent:
            secondary_intent = top2_intent

        # Generate reasoning
        reasoning = generate_reasoning(
            raw_text, pred_intent, confidence, retrieval_sim,
            pred_escalate, esc_reason, is_non_english
        )

        # Track stats
        intent_counts[pred_intent] = intent_counts.get(pred_intent, 0) + 1
        if pred_escalate:
            escalation_count += 1
        if is_non_english:
            non_english_count += 1
        if confidence < 0.3:
            low_confidence_count += 1

        predictions.append({
            "example_id": cand["example_id"],
            "conversation_id": cand["conversation_id"],
            "turn_index": cand["turn_index"],
            "raw_text": raw_text,
            "thread_context": thread_context,
            "ai_prediction": {
                "primary_intent": pred_intent,
                "secondary_intent": secondary_intent,
                "confidence": round(confidence, 4),
                "top2_intent": top2_intent,
                "top2_confidence": round(top2_conf, 4),
                "escalate": pred_escalate,
                "escalation_reason": esc_reason,
                "language_flag": is_non_english,
                "ambiguity_flag": ambiguity,
                "reasoning": reasoning,
            },
            "retrieval_evidence": {
                "historical_id": top_match.get("historical_id", "N/A"),
                "similarity_score": round(retrieval_sim, 4),
                "is_fallback": top_match.get("is_fallback", True),
                "matched_category": retrieval_category,
            },
            "provenance": {
                "classifier": "TF-IDF + LogisticRegression (N=237, ngram=1-2, C=1.0, balanced)",
                "retriever": f"TF-IDF Cosine Similarity (corpus={len(retriever.corpus)})",
                "escalation": "Deterministic High-Risk Rule-Based Policy",
                "llm_used": False,
            },
        })

        if (idx + 1) % 50 == 0:
            print(f"   Processed {idx + 1}/200...")

    # 6. Save predictions
    print(f"\n6. Saving predictions to {OUTPUT_PATH.name}...")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(predictions, f, indent=2, ensure_ascii=False)

    # 7. Final integrity check
    chk2 = verify_checksum(GOLDEN_CANDIDATES_PATH, EXPECTED_GOLDEN_SHA256)

    # 8. Summary
    avg_conf = round(float(np.mean(confidences)), 4)
    print(f"\n{'=' * 80}")
    print("AI PREDICTION SUMMARY")
    print(f"{'=' * 80}")
    print(f"  Total predictions:     {len(predictions)}")
    print(f"  Average confidence:    {avg_conf}")
    print(f"  Low confidence (<0.3): {low_confidence_count}")
    print(f"  Escalation count:      {escalation_count}")
    print(f"  Non-English detected:  {non_english_count}")
    print(f"  Ambiguous predictions: {sum(1 for p in predictions if p['ai_prediction']['ambiguity_flag'])}")
    print(f"\n  Intent distribution:")
    for intent, count in sorted(intent_counts.items()):
        print(f"    {intent}: {count}")
    print(f"\n  Golden checksum verified: {chk2[:16]}...")
    print(f"  Output: {OUTPUT_PATH}")
    print(f"{'=' * 80}")

    return predictions


if __name__ == "__main__":
    run()

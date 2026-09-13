"""
scripts/run_agent.py

Quick Interactive Agent Demo CLI using the Production AI Support Agent Pipeline.

Usage:
    py scripts/run_agent.py
"""

import sys, os, json, re
from pathlib import Path
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.ai.agent_pipeline import (
    preprocess_text,
    DeterministicEscalationPolicy,
    HistoricalResolutionRetriever,
    GroundedReplySynthesizer,
    DEV_HUMAN_PATH,
    EXTERNAL_187_PATH
)
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression


def train_production_classifier():
    """Trains TF-IDF (1,2) + LogisticRegression on 237 human-labelled reference examples."""
    texts = []
    labels = []

    if DEV_HUMAN_PATH.exists():
        with open(DEV_HUMAN_PATH, "r", encoding="utf-8") as f:
            dev_data = json.load(f)
        for item in dev_data:
            t = preprocess_text(item.get("raw_text", ""), item.get("thread_context", []))
            texts.append(t)
            labels.append(item["primary_intent"])

    if EXTERNAL_187_PATH.exists():
        with open(EXTERNAL_187_PATH, "r", encoding="utf-8") as f:
            ext_data = json.load(f)
        for item in ext_data:
            t = preprocess_text(item.get("raw_text", ""))
            texts.append(t)
            labels.append(item["primary_intent"])

    vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1)
    X_train = vectorizer.fit_transform(texts)

    classifier = LogisticRegression(C=1.0, solver='lbfgs', max_iter=500, random_state=2026, class_weight='balanced')
    classifier.fit(X_train, labels)

    return vectorizer, classifier


def run_interactive_demo():
    print("==================================================")
    print("  AMAZONHELP AI SUPPORT AGENT — DEMO INTERFACE    ")
    print("==================================================")
    print("Initializing production classifier and retriever...")

    vectorizer, classifier = train_production_classifier()
    retriever = HistoricalResolutionRetriever()
    classes = list(classifier.classes_)

    print("Agent ready! Type your customer query below (or 'q' to quit).\n")

    sample_queries = [
        "Where is my package? It was supposed to arrive yesterday.",
        "My account was hacked and someone changed my password!",
        "I was charged twice for my Prime membership subscription.",
        "How do I return a damaged pair of shoes I received today?"
    ]

    print("Sample Queries to Try:")
    for idx, sq in enumerate(sample_queries, 1):
        print(f"  {idx}. {sq}")
    print()

    while True:
        try:
            user_input = input("Customer Message > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting agent demo.")
            break

        if not user_input:
            continue
        if user_input.lower() in ["q", "quit", "exit"]:
            print("Exiting agent demo.")
            break

        # Check if user typed a number 1-4 for sample query
        if user_input.isdigit() and 1 <= int(user_input) <= len(sample_queries):
            query = sample_queries[int(user_input) - 1]
            print(f"Selected Sample: '{query}'")
        else:
            query = user_input

        cleaned = preprocess_text(query)

        # 1. Intent Classification
        vec = vectorizer.transform([cleaned])
        probs = classifier.predict_proba(vec)[0]
        top_idx = np.argmax(probs)
        pred_intent = classes[top_idx]
        confidence = float(probs[top_idx])

        # 2. Escalation Evaluation
        escalate, escalate_reason = DeterministicEscalationPolicy.evaluate(
            query, [], pred_intent, confidence
        )

        # 3. Retrieval
        top_matches = retriever.retrieve_top_k(cleaned, pred_intent, top_k=1)
        match = top_matches[0]
        sim_score = match["similarity_score"]

        # Guardrail: If similarity score < 0.15, use safe fallback
        is_low_similarity = (sim_score < 0.15 or match.get("is_fallback", False))

        # 4. Reply Synthesis
        if is_low_similarity:
            draft_reply = (
                f"Hello! Thank you for contacting AmazonHelp regarding {pred_intent.replace('_', ' ')}. "
                f"To assist you safely and accurately, please share your order number and email address via Direct Message "
                f"so our support team can inspect your account details and provide immediate assistance."
            )
            evidence_str = f"Low similarity ({sim_score:.4f} < 0.15) -> Safe Bounded Fallback"
        else:
            draft_reply = GroundedReplySynthesizer.synthesize_reply(cleaned, pred_intent, match)
            evidence_str = f"Historical ID: {match['historical_id']} (Category: {match.get('category')}, Sim: {sim_score:.4f})"

        # Output Results
        print("\n" + "-"*50)
        print(f"Customer Message  : {query}")
        print(f"Predicted Intent  : {pred_intent}")
        print(f"Confidence        : {confidence:.2%}")
        print(f"Escalate          : {'YES' if escalate else 'NO'}")
        if escalate:
            print(f"Escalation Reason : {escalate_reason}")
        print(f"Retrieved Evidence: {evidence_str}")
        print(f"\nDraft Reply:\n{draft_reply}")
        print("-" * 50 + "\n")


if __name__ == "__main__":
    run_interactive_demo()

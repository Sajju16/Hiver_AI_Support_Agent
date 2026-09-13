"""
scripts/build_evidence_assisted_golden_annotation.py

AI-Assisted Annotation System for Golden 200 using 237 Human-Labelled Reference Examples.

Features:
1. Loads 237 human-labelled reference examples (187 external + 50 dev).
2. TF-IDF word (1,2) + char (3,5) feature union + cosine similarity nearest-neighbour retrieval.
3. Nearest-neighbour intent voting among human-labelled reference examples.
4. Combination of nearest-neighbour vote, TF-IDF + LogReg classifier, historical retrieval, and deterministic escalation rules.
5. Strict confidence categorization (HIGH_CONFIDENCE vs LOW_CONFIDENCE).
   - High confidence ONLY if:
     - Top human-labelled neighbours strongly agree on intent
     - Classifier agrees OR retrieval evidence agrees
     - No escalation risk ambiguity
     - Candidate bucket is NOT B2/B3/B4/B5
6. Generates:
   - data/golden/golden_ai_assisted_high_confidence_200.json
   - data/golden/golden_manual_review_queue.json
7. Full evidence logging for every decision.
8. Ensures data integrity (zero modifications to golden_candidates_200.json, dev_human_labels_50.json, external_human_examples_187.json).
"""

import sys, os, json, re, hashlib
from pathlib import Path
from collections import Counter
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import FeatureUnion
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import cosine_similarity

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.ai.agent_pipeline import (
    verify_data_integrity,
    preprocess_text,
    DeterministicEscalationPolicy,
    HistoricalResolutionRetriever,
    DEV_HUMAN_PATH,
    EXTERNAL_187_PATH,
    GOLDEN_PATH,
    EXPECTED_GOLDEN_SHA256,
    CORE_INTENTS
)

HIGH_CONFIDENCE_FILE = PROJECT_ROOT / "data" / "golden" / "golden_ai_assisted_high_confidence_200.json"
MANUAL_REVIEW_FILE = PROJECT_ROOT / "data" / "golden" / "golden_manual_review_queue.json"


def load_human_reference_dataset():
    """Loads 237 human-labelled reference examples from 187 external + 50 DEV."""
    ref_examples = []
    
    # 1. DEV 50 human labels
    with open(DEV_HUMAN_PATH, "r", encoding="utf-8") as f:
        dev_data = json.load(f)
    for item in dev_data:
        raw = item.get("raw_text", "")
        context = item.get("thread_context", [])
        cleaned = preprocess_text(raw, context)
        ref_examples.append({
            "example_id": item["example_id"],
            "raw_text": raw,
            "cleaned_text": cleaned,
            "primary_intent": item["primary_intent"],
            "source": "dev_human_labels_50",
            "candidate_bucket": item.get("candidate_bucket", "DEV_core")
        })

    # 2. External 187 human labels
    with open(EXTERNAL_187_PATH, "r", encoding="utf-8") as f:
        ext_data = json.load(f)
    for item in ext_data:
        raw = item.get("raw_text", "")
        cleaned = preprocess_text(raw, [])
        ref_examples.append({
            "example_id": item["example_id"],
            "raw_text": raw,
            "cleaned_text": cleaned,
            "primary_intent": item["primary_intent"],
            "source": "external_human_examples_187",
            "candidate_bucket": "EXT_187"
        })
        
    print(f"Loaded {len(ref_examples)} reference human-labelled examples (50 DEV + {len(ext_data)} External).")
    return ref_examples


def build_evidence_assisted_annotations():
    """Main pipeline for evidence-assisted Golden annotation."""
    # 1. Verify Golden Checksum
    verify_data_integrity()
    
    with open(GOLDEN_PATH, "rb") as f:
        pre_hash = hashlib.sha256(f.read()).hexdigest().lower()
    assert pre_hash == EXPECTED_GOLDEN_SHA256, "Golden checksum mismatch before pipeline execution!"

    # 2. Load Reference Human Examples (237)
    ref_examples = load_human_reference_dataset()
    ref_texts = [r["cleaned_text"] for r in ref_examples]
    ref_intents = [r["primary_intent"] for r in ref_examples]

    # 3. Fit TF-IDF Feature Union (Word + Char features)
    feature_union = FeatureUnion([
        ('word', TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True)),
        ('char', TfidfVectorizer(ngram_range=(3, 5), analyzer='char_wb', min_df=1, sublinear_tf=True))
    ])
    
    ref_vectors = feature_union.fit_transform(ref_texts)
    
    # 4. Train Classifier on 237 human-labelled reference examples
    classifier = LogisticRegression(C=1.0, solver='lbfgs', max_iter=500, random_state=2026, class_weight='balanced')
    classifier.fit(ref_vectors, ref_intents)
    clf_classes = list(classifier.classes_)

    # 5. Load Historical Resolution Retriever (352 historical examples)
    retriever = HistoricalResolutionRetriever()

    # 6. Load Golden Candidates (200 unlabelled)
    with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
        golden_candidates = json.load(f)

    print(f"Processing {len(golden_candidates)} Golden candidates for evidence-assisted annotation...")

    high_confidence_records = []
    manual_review_records = []
    all_annotated_records = []

    high_conf_count = 0
    low_conf_count = 0
    escalation_uncertainty_count = 0
    agreement_stats = {
        "nn_and_clf_agree": 0,
        "nn_and_retrieval_agree": 0,
        "all_three_agree": 0,
        "disagreement": 0
    }

    intent_counter = Counter()

    for idx, candidate in enumerate(golden_candidates):
        cid = candidate.get("conversation_id", "")
        turn_idx = candidate.get("turn_index", 0)
        raw_text = candidate.get("raw_text", "")
        context = candidate.get("thread_context", [])
        cleaned_text = preprocess_text(raw_text, context)
        bucket = candidate.get("candidate_bucket", "B1_core")
        candidate_hint = candidate.get("candidate_intent_hint", "")
        example_id = f"GOLDEN_{idx+1:03d}"

        # Vectorize golden query
        golden_vector = feature_union.transform([cleaned_text])

        # A. Nearest-Neighbour Retrieval from 237 Human Examples
        sims = cosine_similarity(golden_vector, ref_vectors)[0]
        top_k_indices = np.argsort(sims)[::-1][:5]
        
        top3_indices = top_k_indices[:3]
        top3_ref_ids = [ref_examples[i]["example_id"] for i in top3_indices]
        top3_ref_intents = [ref_examples[i]["primary_intent"] for i in top3_indices]
        top3_sim_scores = [round(float(sims[i]), 4) for i in top3_indices]

        # NN Voting (top 5)
        top5_intents = [ref_examples[i]["primary_intent"] for i in top_k_indices]
        vote_dist = dict(Counter(top5_intents))
        nn_top_intent, nn_top_votes = Counter(top5_intents).most_common(1)[0]
        nn_vote_fraction = round(nn_top_votes / 5.0, 2)

        # B. Classifier Prediction
        clf_probs = classifier.predict_proba(golden_vector)[0]
        clf_top_idx = np.argmax(clf_probs)
        clf_intent = clf_classes[clf_top_idx]
        clf_prob = round(float(clf_probs[clf_top_idx]), 4)

        # C. Historical Retrieval Evidence
        retrieval_matches = retriever.retrieve_top_k(cleaned_text, candidate_hint, top_k=1)
        retrieval_match = retrieval_matches[0]
        retrieval_intent = retrieval_match["category"]
        retrieval_sim = round(float(retrieval_match["similarity_score"]), 4)

        # D. Deterministic Escalation Policy
        escalate, escalate_reason = DeterministicEscalationPolicy.evaluate(
            raw_text, context, nn_top_intent, clf_prob
        )

        # Evidence agreement check
        clf_agrees = (clf_intent == nn_top_intent)
        retrieval_agrees = (retrieval_intent == nn_top_intent)
        all_agree = (clf_agrees and retrieval_agrees)

        if clf_agrees:
            agreement_stats["nn_and_clf_agree"] += 1
        if retrieval_agrees:
            agreement_stats["nn_and_retrieval_agree"] += 1
        if all_agree:
            agreement_stats["all_three_agree"] += 1
        if not (clf_agrees or retrieval_agrees):
            agreement_stats["disagreement"] += 1

        # Check escalation ambiguity
        # Escalation ambiguity occurs if deterministic escalation policy flags safety risk but intent isn't an escalation intent,
        # or if candidate bucket is B3_escalation
        escalation_ambiguous = False
        if bucket == "B3_escalation":
            escalation_ambiguous = True
        elif escalate and nn_top_intent not in ["General_Service_Complaint_Escalation", "Marked_Delivered_Not_Received", "Refund_Status_And_Billing_Disputes"]:
            escalation_ambiguous = True

        if escalation_ambiguous:
            escalation_uncertainty_count += 1

        # E. Evaluate Confidence Rules according to Requirement 7:
        # HIGH_CONFIDENCE if:
        # 1. top human-labelled neighbours strongly agree on intent (e.g. nn_top_votes >= 3/5 and top sim >= 0.15)
        # 2. classifier agrees OR retrieval evidence agrees
        # 3. no escalation ambiguity
        # 4. not B2/B3/B4/B5 (must be B1_core candidate bucket)
        
        is_high_confidence = False
        reasons = []

        if bucket != "B1_core":
            reasons.append(f"Candidate bucket is {bucket} (requires manual review as per taxonomy rule)")
        
        if nn_top_votes < 3 or top3_sim_scores[0] < 0.12:
            reasons.append(f"Top human neighbours do not strongly agree (votes: {nn_top_votes}/5, top_sim: {top3_sim_scores[0]})")
        
        if not (clf_agrees or retrieval_agrees):
            reasons.append(f"Neither classifier ({clf_intent}) nor retrieval ({retrieval_intent}) agrees with NN vote ({nn_top_intent})")
        
        if escalation_ambiguous:
            reasons.append(f"Escalation ambiguity present (bucket={bucket}, policy_escalate={escalate}, reason='{escalate_reason}')")

        if len(reasons) == 0:
            is_high_confidence = True
            decision_reason = f"ACCEPTED_HIGH_CONFIDENCE: Top human neighbours strongly agree ({nn_top_votes}/5 votes, top sim {top3_sim_scores[0]}), classifier/retrieval agrees, bucket B1_core, no escalation ambiguity."
        else:
            decision_reason = f"REJECTED_LOW_CONFIDENCE: " + "; ".join(reasons)

        final_intent = nn_top_intent

        evidence_payload = {
            "example_id": example_id,
            "conversation_id": cid,
            "turn_index": turn_idx,
            "raw_text": raw_text,
            "thread_context": context,
            "candidate_bucket": bucket,
            "candidate_intent_hint": candidate_hint,

            # Annotation output
            "primary_intent": final_intent,
            "secondary_intent": None,
            "escalate": escalate,
            "escalation_reason": escalate_reason,
            "language_flag": (bucket == "B4_non_english"),
            "ambiguity_flag": (bucket in ["B2_confusing", "B5_edge_cases"] or nn_top_votes < 3),
            "annotation_source": "AI_ASSISTED_PROVISIONAL",
            
            # Evidence breakdown
            "confidence_status": "HIGH_CONFIDENCE" if is_high_confidence else "LOW_CONFIDENCE",
            "decision_reason": decision_reason,
            "predicted_intent": final_intent,
            "top_3_reference_example_ids": top3_ref_ids,
            "top_3_reference_human_intents": top3_ref_intents,
            "top_3_similarity_scores": top3_sim_scores,
            "vote_distribution": vote_dist,
            "classifier_prediction": {
                "predicted_intent": clf_intent,
                "probability": clf_prob,
                "agrees_with_nn": clf_agrees
            },
            "retrieval_prediction": {
                "predicted_intent": retrieval_intent,
                "similarity_score": retrieval_sim,
                "agrees_with_nn": retrieval_agrees
            },
            "escalation_ambiguity": escalation_ambiguous
        }

        all_annotated_records.append(evidence_payload)
        intent_counter[final_intent] += 1

        if is_high_confidence:
            high_conf_count += 1
            high_confidence_records.append(evidence_payload)
        else:
            low_conf_count += 1
            manual_review_records.append(evidence_payload)

    # 7. Write Output Files
    HIGH_CONFIDENCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(HIGH_CONFIDENCE_FILE, "w", encoding="utf-8") as f:
        json.dump(high_confidence_records, f, indent=2, ensure_ascii=False)
    
    with open(MANUAL_REVIEW_FILE, "w", encoding="utf-8") as f:
        json.dump(manual_review_records, f, indent=2, ensure_ascii=False)

    # Also save the complete 200 evidence predictions file
    full_evidence_file = PROJECT_ROOT / "data" / "golden" / "golden_ai_assisted_evidence_200.json"
    with open(full_evidence_file, "w", encoding="utf-8") as f:
        json.dump(all_annotated_records, f, indent=2, ensure_ascii=False)

    # 8. Post-Run Data Integrity Check
    with open(GOLDEN_PATH, "rb") as f:
        post_hash = hashlib.sha256(f.read()).hexdigest().lower()
    assert post_hash == EXPECTED_GOLDEN_SHA256, "GOLDEN CHECKSUM MISMATCH AFTER PIPELINE!"

    print("\n==================================================")
    print("EVIDENCE-ASSISTED GOLDEN ANNOTATION REPORT")
    print("==================================================")
    print(f"Total Golden Examples Processed: {len(golden_candidates)}")
    print(f"High-Confidence Count (Auto-Accepted): {high_conf_count}")
    print(f"Low-Confidence Count (Manual Review): {low_conf_count}")
    print(f"Manual Review Queue Size: {len(manual_review_records)}")
    print(f"Escalation Uncertainty Count: {escalation_uncertainty_count}")
    print("\nEvidence Agreement Statistics:")
    print(f"  - NN & Classifier Agree: {agreement_stats['nn_and_clf_agree']} ({agreement_stats['nn_and_clf_agree']/200:.1%})")
    print(f"  - NN & Retrieval Agree: {agreement_stats['nn_and_retrieval_agree']} ({agreement_stats['nn_and_retrieval_agree']/200:.1%})")
    print(f"  - All Three Agree (Unanimous): {agreement_stats['all_three_agree']} ({agreement_stats['all_three_agree']/200:.1%})")
    print(f"  - Disagreement (NN != Clf AND NN != Retr): {agreement_stats['disagreement']} ({agreement_stats['disagreement']/200:.1%})")
    print("\nIntent Distribution (Across All 200 Provisional Labels):")
    for intent, cnt in sorted(intent_counter.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {intent}: {cnt}")
    print(f"\nGolden Candidates SHA-256 Checksum: {post_hash} (VERIFIED MATCH)")

    return {
        "high_confidence_count": high_conf_count,
        "low_confidence_count": low_conf_count,
        "manual_review_count": len(manual_review_records),
        "escalation_uncertainty_count": escalation_uncertainty_count,
        "agreement_stats": agreement_stats,
        "intent_distribution": dict(intent_counter),
        "checksum": post_hash
    }

if __name__ == "__main__":
    build_evidence_assisted_annotations()

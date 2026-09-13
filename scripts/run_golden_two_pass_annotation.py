"""
scripts/run_golden_two_pass_annotation.py — Two-Pass AI-Assisted Annotation for Golden 200

Pass 1: TF-IDF (word n-grams 1-2) + Logistic Regression classifier
Pass 2: TF-IDF (char n-grams 3-5) + Logistic Regression (different C, no balancing)
         + retrieval-based category voting as tiebreaker

Then: cross-pass consistency check, adjudication, review queue, and summary.

All outputs are marked "AI_ASSISTED_PROVISIONAL" — never "human-labelled".
golden_candidates_200.json is NEVER modified.
"""

import sys, json, hashlib, re, copy
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

# === PATHS ===
GOLDEN_CANDIDATES = PROJECT_ROOT / "data" / "golden" / "golden_candidates_200.json"
DEV_HUMAN = PROJECT_ROOT / "data" / "dev" / "dev_human_labels_50.json"
EXTERNAL_187 = PROJECT_ROOT / "data" / "processed" / "external_human_examples_187.json"

OUT_PASS1 = PROJECT_ROOT / "data" / "golden" / "golden_ai_predictions_200.json"
OUT_PASS2 = PROJECT_ROOT / "data" / "golden" / "golden_ai_second_pass_200.json"
OUT_CONSISTENCY = PROJECT_ROOT / "data" / "golden" / "golden_annotation_consistency_report.json"
OUT_PROVISIONAL = PROJECT_ROOT / "data" / "golden" / "golden_provisional_labels_200.json"
OUT_REVIEW_QUEUE = PROJECT_ROOT / "data" / "golden" / "golden_manual_review_queue.json"
OUT_SUMMARY = PROJECT_ROOT / "data" / "golden" / "golden_annotation_summary.json"


def verify_checksum():
    with open(GOLDEN_CANDIDATES, "rb") as f:
        h = hashlib.sha256(f.read()).hexdigest().lower()
    assert h == EXPECTED_GOLDEN_SHA256, f"CHECKSUM MISMATCH: {h}"
    return h


def detect_language(text):
    """Heuristic non-English detection."""
    patterns = [
        r'[\u0900-\u097F]', r'[\u0600-\u06FF]', r'[\u3040-\u30FF]',
        r'[\u4E00-\u9FFF]', r'[\uAC00-\uD7AF]', r'[\u0B80-\u0BFF]',
        r'[\u0C00-\u0C7F]', r'[\u0980-\u09FF]',
    ]
    for pat in patterns:
        if re.search(pat, text):
            return True
    non_ascii = sum(1 for c in text if ord(c) > 127)
    if non_ascii / max(len(text), 1) > 0.3:
        return True
    return False


def load_training_data():
    """Load DEV 50 + External 187 training data."""
    with open(DEV_HUMAN, "r", encoding="utf-8") as f:
        dev = json.load(f)
    dev_texts = [preprocess_text(r["raw_text"], r.get("thread_context", [])) for r in dev]
    dev_labels = [r["primary_intent"] for r in dev]

    ext_texts, ext_labels = [], []
    if EXTERNAL_187.exists():
        with open(EXTERNAL_187, "r", encoding="utf-8") as f:
            ext = json.load(f)
        ext_texts = [preprocess_text(r["raw_text"]) for r in ext]
        ext_labels = [r["primary_intent"] for r in ext]

    return dev_texts, dev_labels, ext_texts, ext_labels


# ========================================================================
# PASS 1: Word n-gram TF-IDF + Logistic Regression (balanced)
# ========================================================================
def run_pass1(candidates, all_texts, all_labels, retriever):
    """Pass 1: Word-level TF-IDF (1,2) + LogReg (C=1.0, balanced)."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression

    vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, max_features=2000)
    X_train = vectorizer.fit_transform(all_texts)
    model = LogisticRegression(C=1.0, max_iter=1000, random_state=2026, class_weight="balanced")
    model.fit(X_train, all_labels)

    predictions = []
    for cand in candidates:
        raw = cand["raw_text"]
        ctx = cand.get("thread_context", [])
        clean = preprocess_text(raw, ctx)

        X_q = vectorizer.transform([clean])
        pred = model.predict(X_q)[0]
        proba = model.predict_proba(X_q)[0]
        conf = float(np.max(proba))

        sorted_idx = np.argsort(proba)[::-1]
        top2_intent = model.classes_[sorted_idx[1]] if len(sorted_idx) > 1 else None
        top2_conf = float(proba[sorted_idx[1]]) if len(sorted_idx) > 1 else 0.0
        ambiguity = (conf - top2_conf) < 0.15

        secondary = top2_intent if ambiguity and top2_intent != pred else None

        # Retrieval evidence
        retrieved = retriever.retrieve_top_k(raw, pred, top_k=3)
        top_match = retrieved[0] if retrieved else {}

        # Escalation
        esc, esc_reason = DeterministicEscalationPolicy.evaluate(raw, ctx, pred, conf)

        # Language
        is_non_en = detect_language(raw)

        # Reasoning
        parts = [f"Word-ngram classifier: '{pred}' (conf={conf:.4f})."]
        if ambiguity:
            parts.append(f"Close runner-up: '{top2_intent}' ({top2_conf:.4f}).")
        if retrieved and not top_match.get("is_fallback"):
            parts.append(f"Top retrieval match: category='{top_match.get('category','')}' (sim={top_match.get('similarity_score',0):.4f}).")
        if esc:
            parts.append(f"Escalation: {esc_reason}")
        if is_non_en:
            parts.append("Non-English detected.")

        predictions.append({
            "example_id": cand["example_id"],
            "conversation_id": cand["conversation_id"],
            "turn_index": cand["turn_index"],
            "raw_text": raw,
            "thread_context": ctx,
            "ai_prediction": {
                "primary_intent": pred,
                "secondary_intent": secondary,
                "confidence": round(conf, 4),
                "top2_intent": top2_intent,
                "top2_confidence": round(top2_conf, 4),
                "escalate": esc,
                "escalation_reason": esc_reason,
                "language_flag": is_non_en,
                "ambiguity_flag": ambiguity,
                "reasoning": " ".join(parts),
            },
            "retrieval_evidence": {
                "top1_id": top_match.get("historical_id", "N/A"),
                "top1_sim": round(top_match.get("similarity_score", 0), 4),
                "top1_category": top_match.get("category", ""),
                "top1_fallback": top_match.get("is_fallback", True),
                "top3_categories": [r.get("category", "") for r in retrieved[:3]] if retrieved else [],
            },
            "evidence_used": {
                "classifier": "TF-IDF word(1,2) + LogReg(C=1.0, balanced, N=237)",
                "retrieval": f"TF-IDF cosine (corpus={len(retriever.corpus)})",
                "escalation": "Deterministic high-risk rule-based",
                "language": "Heuristic script detection",
            },
            "provenance": {
                "pass": "PASS_1",
                "method": "WORD_NGRAM_CLASSIFIER",
                "annotation_source": "AI_ASSISTED_PROVISIONAL",
                "llm_used": False,
            },
        })

    return predictions


# ========================================================================
# PASS 2: Char n-gram TF-IDF + LogReg (different config) + retrieval vote
# ========================================================================
def run_pass2(candidates, all_texts, all_labels, retriever):
    """Pass 2: Character-level TF-IDF (3,5) + LogReg (C=0.5, no balancing) + retrieval vote."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression

    # Different vectorizer: character n-grams instead of word n-grams
    vectorizer = TfidfVectorizer(
        analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, max_features=3000
    )
    X_train = vectorizer.fit_transform(all_texts)
    # Different model: different C, no class_weight, different seed
    model = LogisticRegression(C=0.5, max_iter=1000, random_state=42)
    model.fit(X_train, all_labels)

    predictions = []
    for cand in candidates:
        raw = cand["raw_text"]
        ctx = cand.get("thread_context", [])
        clean = preprocess_text(raw, ctx)

        X_q = vectorizer.transform([clean])
        char_pred = model.predict(X_q)[0]
        char_proba = model.predict_proba(X_q)[0]
        char_conf = float(np.max(char_proba))

        sorted_idx = np.argsort(char_proba)[::-1]
        top2_intent = model.classes_[sorted_idx[1]] if len(sorted_idx) > 1 else None
        top2_conf = float(char_proba[sorted_idx[1]]) if len(sorted_idx) > 1 else 0.0

        # Retrieval-based voting (top-3 historical matches)
        retrieved = retriever.retrieve_top_k(raw, None, top_k=5)  # No intent bias
        retr_votes = {}
        for r in retrieved[:5]:
            if not r.get("is_fallback"):
                cat = r.get("category", "")
                if cat:
                    sim = r.get("similarity_score", 0)
                    retr_votes[cat] = retr_votes.get(cat, 0) + sim

        retr_pred = max(retr_votes, key=retr_votes.get) if retr_votes else None

        # Combine: if char classifier and retrieval agree, use that; otherwise use char classifier
        if retr_pred and retr_pred == char_pred:
            final_pred = char_pred
            combined_conf = min(1.0, char_conf + 0.05)  # Small boost for agreement
            method_note = "Char-ngram + retrieval agreement"
        elif retr_pred and retr_pred != char_pred and char_conf < 0.15:
            # Low char confidence but retrieval has a clear signal
            top_retr_sim = max(retr_votes.values()) if retr_votes else 0
            if top_retr_sim > 0.2:
                final_pred = retr_pred
                combined_conf = char_conf
                method_note = "Retrieval override (low classifier confidence)"
            else:
                final_pred = char_pred
                combined_conf = char_conf
                method_note = "Char-ngram (weak retrieval)"
        else:
            final_pred = char_pred
            combined_conf = char_conf
            method_note = "Char-ngram classifier primary"

        ambiguity = (char_conf - top2_conf) < 0.12
        secondary = top2_intent if ambiguity and top2_intent != final_pred else None

        # Independent escalation evaluation
        esc, esc_reason = DeterministicEscalationPolicy.evaluate(raw, ctx, final_pred, combined_conf)

        is_non_en = detect_language(raw)

        # Reasoning
        parts = [f"Char-ngram classifier: '{char_pred}' (conf={char_conf:.4f})."]
        if retr_pred:
            parts.append(f"Retrieval vote: '{retr_pred}'.")
        parts.append(f"Combined decision: '{final_pred}' via {method_note}.")
        if ambiguity:
            parts.append(f"Ambiguous: runner-up '{top2_intent}' ({top2_conf:.4f}).")
        if esc:
            parts.append(f"Escalation: {esc_reason}")

        predictions.append({
            "example_id": cand["example_id"],
            "conversation_id": cand["conversation_id"],
            "turn_index": cand["turn_index"],
            "ai_prediction": {
                "primary_intent": final_pred,
                "secondary_intent": secondary,
                "confidence": round(combined_conf, 4),
                "char_classifier_intent": char_pred,
                "char_classifier_confidence": round(char_conf, 4),
                "retrieval_voted_intent": retr_pred,
                "escalate": esc,
                "escalation_reason": esc_reason,
                "language_flag": is_non_en,
                "ambiguity_flag": ambiguity,
                "reasoning": " ".join(parts),
                "method_note": method_note,
            },
            "provenance": {
                "pass": "PASS_2",
                "method": "CHAR_NGRAM_CLASSIFIER_PLUS_RETRIEVAL_VOTE",
                "annotation_source": "AI_ASSISTED_PROVISIONAL",
                "llm_used": False,
            },
        })

    return predictions


# ========================================================================
# Consistency comparison
# ========================================================================
def compare_passes(pass1, pass2, candidates):
    """Compare Pass 1 and Pass 2 predictions."""
    bucket_map = {c["example_id"]: c.get("candidate_bucket", "B1_core") for c in candidates}

    intent_agree = 0
    esc_agree = 0
    lang_agree = 0
    amb_agree = 0
    disagreements = []
    per_intent_disagree = {}

    for p1, p2 in zip(pass1, pass2):
        ai1 = p1["ai_prediction"]
        ai2 = p2["ai_prediction"]
        eid = p1["example_id"]
        bucket = bucket_map.get(eid, "B1_core")

        i_agree = ai1["primary_intent"] == ai2["primary_intent"]
        e_agree = ai1["escalate"] == ai2["escalate"]
        l_agree = ai1["language_flag"] == ai2["language_flag"]
        a_agree = ai1["ambiguity_flag"] == ai2["ambiguity_flag"]

        if i_agree:
            intent_agree += 1
        else:
            disagreements.append({
                "example_id": eid,
                "bucket": bucket,
                "pass1_intent": ai1["primary_intent"],
                "pass1_confidence": ai1["confidence"],
                "pass2_intent": ai2["primary_intent"],
                "pass2_confidence": ai2["confidence"],
                "escalation_disagree": not e_agree,
                "pass1_escalate": ai1["escalate"],
                "pass2_escalate": ai2["escalate"],
            })
            # Track per-intent disagreement
            key = f"{ai1['primary_intent']} vs {ai2['primary_intent']}"
            per_intent_disagree[key] = per_intent_disagree.get(key, 0) + 1

        if e_agree:
            esc_agree += 1
        if l_agree:
            lang_agree += 1
        if a_agree:
            amb_agree += 1

    n = len(pass1)
    p1_confs = [p["ai_prediction"]["confidence"] for p in pass1]
    p2_confs = [p["ai_prediction"]["confidence"] for p in pass2]

    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "total_examples": n,
        "intent_agreement": {
            "count": intent_agree,
            "rate": round(intent_agree / n, 4),
        },
        "escalation_agreement": {
            "count": esc_agree,
            "rate": round(esc_agree / n, 4),
        },
        "language_agreement": {
            "count": lang_agree,
            "rate": round(lang_agree / n, 4),
        },
        "ambiguity_agreement": {
            "count": amb_agree,
            "rate": round(amb_agree / n, 4),
        },
        "disagreement_count": len(disagreements),
        "disagreement_examples": disagreements,
        "per_intent_disagreement": dict(sorted(per_intent_disagree.items(), key=lambda x: -x[1])),
        "confidence_statistics": {
            "pass1_mean": round(float(np.mean(p1_confs)), 4),
            "pass1_min": round(float(np.min(p1_confs)), 4),
            "pass1_max": round(float(np.max(p1_confs)), 4),
            "pass1_std": round(float(np.std(p1_confs)), 4),
            "pass2_mean": round(float(np.mean(p2_confs)), 4),
            "pass2_min": round(float(np.min(p2_confs)), 4),
            "pass2_max": round(float(np.max(p2_confs)), 4),
            "pass2_std": round(float(np.std(p2_confs)), 4),
        },
        "pass1_method": "TF-IDF word(1,2) + LogReg(C=1.0, balanced)",
        "pass2_method": "TF-IDF char_wb(3,5) + LogReg(C=0.5) + retrieval vote",
    }

    return report, disagreements


# ========================================================================
# Adjudication → provisional labels
# ========================================================================
def adjudicate(pass1, pass2, consistency_report, candidates, retriever):
    """Produce final provisional labels by adjudicating between passes."""
    bucket_map = {c["example_id"]: c.get("candidate_bucket", "B1_core") for c in candidates}
    disagree_ids = set(d["example_id"] for d in consistency_report["disagreement_examples"])

    provisional = []
    review_queue = []
    consensus_count = 0
    adjudicated_count = 0
    review_count = 0

    for p1, p2, cand in zip(pass1, pass2, candidates):
        ai1 = p1["ai_prediction"]
        ai2 = p2["ai_prediction"]
        eid = p1["example_id"]
        bucket = bucket_map.get(eid, "B1_core")

        rec = {
            "example_id": eid,
            "conversation_id": p1["conversation_id"],
            "turn_index": p1["turn_index"],
            "raw_text": p1["raw_text"],
            "thread_context": p1.get("thread_context", []),
            "annotation_source": "AI_ASSISTED_PROVISIONAL",
        }

        # --- Intent adjudication ---
        if ai1["primary_intent"] == ai2["primary_intent"]:
            # Consensus
            rec["primary_intent"] = ai1["primary_intent"]
            rec["secondary_intent"] = ai1.get("secondary_intent") or ai2.get("secondary_intent")
            rec["confidence"] = round(max(ai1["confidence"], ai2["confidence"]), 4)
            rec["adjudication_method"] = "TWO_PASS_CONSENSUS"
            consensus_count += 1
        else:
            # Disagreement -> adjudicate
            # IMPORTANT: Pass 1 (word n-gram, 11 classes) is the PRIMARY classifier.
            # Pass 2 (char n-gram) tends to collapse to fewer classes with artificially
            # higher confidence, so raw confidence comparison is misleading.
            # Strategy: retrieval tiebreak first, then prefer Pass 1 unless
            # retrieval specifically supports Pass 2.
            retr_cat = p1.get("retrieval_evidence", {}).get("top1_category", "")
            retr_sim = p1.get("retrieval_evidence", {}).get("top1_sim", 0)
            retr_fallback = p1.get("retrieval_evidence", {}).get("top1_fallback", True)
            retr_top3 = p1.get("retrieval_evidence", {}).get("top3_categories", [])

            # Check retrieval agreement (check top-3 categories)
            retr_agrees_p1 = False
            retr_agrees_p2 = False
            if not retr_fallback and retr_cat:
                retr_agrees_p1 = retr_cat.lower() in ai1["primary_intent"].lower()
                retr_agrees_p2 = retr_cat.lower() in ai2["primary_intent"].lower()
            # Also check top-3 vote
            if retr_top3:
                p1_votes = sum(1 for c in retr_top3 if c and c.lower() in ai1["primary_intent"].lower())
                p2_votes = sum(1 for c in retr_top3 if c and c.lower() in ai2["primary_intent"].lower())
                if p1_votes > p2_votes:
                    retr_agrees_p1 = True
                elif p2_votes > p1_votes:
                    retr_agrees_p2 = True

            if retr_agrees_p1 and not retr_agrees_p2:
                rec["primary_intent"] = ai1["primary_intent"]
                rec["adjudication_method"] = "RETRIEVAL_TIEBREAK_PASS1"
            elif retr_agrees_p2 and not retr_agrees_p1:
                rec["primary_intent"] = ai2["primary_intent"]
                rec["adjudication_method"] = "RETRIEVAL_TIEBREAK_PASS2"
            else:
                # Default: prefer Pass 1 (diverse 11-class classifier)
                # Pass 2 char-ngram has class collapse bias
                rec["primary_intent"] = ai1["primary_intent"]
                rec["adjudication_method"] = "PASS1_PRIMARY_DEFAULT"

            rec["secondary_intent"] = (
                ai2["primary_intent"] if rec["primary_intent"] == ai1["primary_intent"]
                else ai1["primary_intent"]
            )
            rec["confidence"] = round(max(ai1["confidence"], ai2["confidence"]), 4)
            rec["ambiguity_flag"] = True  # Disagreement = ambiguous
            adjudicated_count += 1

            # Add to review queue
            review_priority = 1  # disagreement
            if ai1["escalate"] != ai2["escalate"]:
                review_priority = 0  # escalation disagreement = highest
            elif "B2" in bucket:
                review_priority = 2
            elif "B3" in bucket:
                review_priority = 3
            elif ai1["confidence"] < 0.15 or ai2["confidence"] < 0.15:
                review_priority = 4
            elif "B4" in bucket:
                review_priority = 5
            elif "B5" in bucket:
                review_priority = 6

            review_queue.append({
                "example_id": eid,
                "bucket": bucket,
                "priority": review_priority,
                "reason": rec["adjudication_method"],
                "pass1_intent": ai1["primary_intent"],
                "pass1_confidence": ai1["confidence"],
                "pass2_intent": ai2["primary_intent"],
                "pass2_confidence": ai2["confidence"],
                "provisional_intent": rec["primary_intent"],
                "escalation_disagree": ai1["escalate"] != ai2["escalate"],
                "raw_text_preview": p1["raw_text"][:120],
            })

        # --- Escalation adjudication ---
        # Prioritize explicit high-risk evidence: if EITHER pass flags escalation, escalate
        if ai1["escalate"] or ai2["escalate"]:
            rec["escalate"] = True
            rec["escalate_reason"] = ai1["escalation_reason"] if ai1["escalate"] else ai2["escalation_reason"]
        else:
            rec["escalate"] = False
            rec["escalate_reason"] = ""

        # --- Language flag: either flags = flagged ---
        rec["language_flag"] = ai1["language_flag"] or ai2["language_flag"]

        # --- Ambiguity: set if not already set ---
        if "ambiguity_flag" not in rec:
            rec["ambiguity_flag"] = ai1["ambiguity_flag"] or ai2["ambiguity_flag"]

        rec["annotator_notes"] = None
        rec["pass1_prediction"] = ai1["primary_intent"]
        rec["pass2_prediction"] = ai2["primary_intent"]

        provisional.append(rec)

    # Also add non-disagreement high-risk cases to review queue
    for p1, p2, cand in zip(pass1, pass2, candidates):
        eid = p1["example_id"]
        bucket = bucket_map.get(eid, "B1_core")
        ai1 = p1["ai_prediction"]

        if eid in disagree_ids:
            continue  # Already in queue

        needs_review = False
        priority = 99
        reason = ""

        if "B2" in bucket:
            needs_review = True
            priority = 2
            reason = "B2_confusing_pair"
        elif "B3" in bucket:
            needs_review = True
            priority = 3
            reason = "B3_escalation_case"
        elif ai1["confidence"] < 0.12:
            needs_review = True
            priority = 4
            reason = "very_low_confidence"
        elif "B4" in bucket:
            needs_review = True
            priority = 5
            reason = "B4_non_english"
        elif "B5" in bucket:
            needs_review = True
            priority = 6
            reason = "B5_edge_case"

        if needs_review:
            review_queue.append({
                "example_id": eid,
                "bucket": bucket,
                "priority": priority,
                "reason": reason,
                "pass1_intent": ai1["primary_intent"],
                "pass1_confidence": ai1["confidence"],
                "pass2_intent": p2["ai_prediction"]["primary_intent"],
                "pass2_confidence": p2["ai_prediction"]["confidence"],
                "provisional_intent": next(
                    (r["primary_intent"] for r in provisional if r["example_id"] == eid), None
                ),
                "escalation_disagree": False,
                "raw_text_preview": p1["raw_text"][:120],
            })
            review_count += 1

    # Sort review queue by priority
    review_queue.sort(key=lambda x: x["priority"])

    return provisional, review_queue, consensus_count, adjudicated_count


# ========================================================================
# Summary
# ========================================================================
def generate_summary(provisional, review_queue, consistency_report):
    n = len(provisional)
    consensus = sum(1 for r in provisional if r.get("adjudication_method") == "TWO_PASS_CONSENSUS")
    disagreement = n - consensus

    intent_dist = {}
    esc_dist = {"escalate": 0, "no_escalate": 0}
    amb_dist = {"ambiguous": 0, "clear": 0}
    lang_dist = {"non_english": 0, "english": 0}

    for r in provisional:
        p = r["primary_intent"]
        intent_dist[p] = intent_dist.get(p, 0) + 1
        if r.get("escalate"):
            esc_dist["escalate"] += 1
        else:
            esc_dist["no_escalate"] += 1
        if r.get("ambiguity_flag"):
            amb_dist["ambiguous"] += 1
        else:
            amb_dist["clear"] += 1
        if r.get("language_flag"):
            lang_dist["non_english"] += 1
        else:
            lang_dist["english"] += 1

    esc_disagree = sum(1 for q in review_queue if q.get("escalation_disagree"))

    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "annotation_source": "AI_ASSISTED_PROVISIONAL",
        "total": n,
        "consensus_count": consensus,
        "disagreement_count": disagreement,
        "consensus_rate": round(consensus / n, 4),
        "manual_review_required": len(review_queue),
        "escalation_disagreements": esc_disagree,
        "intent_distribution": dict(sorted(intent_dist.items())),
        "escalation_distribution": esc_dist,
        "ambiguity_distribution": amb_dist,
        "language_distribution": lang_dist,
        "confidence_stats": consistency_report.get("confidence_statistics", {}),
        "adjudication_methods": {},
    }

    # Count adjudication methods
    for r in provisional:
        m = r.get("adjudication_method", "UNKNOWN")
        summary["adjudication_methods"][m] = summary["adjudication_methods"].get(m, 0) + 1

    return summary


# ========================================================================
# Main
# ========================================================================
def main():
    print("=" * 80)
    print("GOLDEN 200 TWO-PASS AI-ASSISTED ANNOTATION")
    print("=" * 80)

    # 1. Verify integrity
    print("\n[1/8] Verifying data integrity...")
    chk = verify_checksum()
    print(f"  Golden checksum OK: {chk[:20]}...")

    with open(GOLDEN_CANDIDATES, "r", encoding="utf-8") as f:
        candidates = json.load(f)
    assert len(candidates) == 200
    print(f"  Loaded {len(candidates)} Golden candidates.")

    # Verify DEV 50 and External 187 exist
    with open(DEV_HUMAN, "r", encoding="utf-8") as f:
        dev_check = json.load(f)
    assert len(dev_check) == 50 and all(r.get("primary_intent") for r in dev_check)
    print(f"  DEV 50: OK ({len(dev_check)} labelled)")

    ext_count = 0
    if EXTERNAL_187.exists():
        with open(EXTERNAL_187, "r", encoding="utf-8") as f:
            ext_count = len(json.load(f))
    print(f"  External: OK ({ext_count} examples)")

    # 2. Load training data
    print("\n[2/8] Loading training data...")
    dev_texts, dev_labels, ext_texts, ext_labels = load_training_data()
    all_texts = ext_texts + dev_texts
    all_labels = ext_labels + dev_labels
    print(f"  Training set: {len(all_texts)} examples")

    # 3. Initialize retriever
    print("\n[3/8] Initializing retriever...")
    retriever = HistoricalResolutionRetriever()
    print(f"  Retriever corpus: {len(retriever.corpus)} examples")

    # 4. Pass 1
    print("\n[4/8] Running Pass 1 (word n-gram classifier)...")
    pass1 = run_pass1(candidates, all_texts, all_labels, retriever)
    OUT_PASS1.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PASS1, "w", encoding="utf-8") as f:
        json.dump(pass1, f, indent=2, ensure_ascii=False)
    print(f"  Pass 1 complete: {len(pass1)} predictions saved.")

    # 5. Pass 2
    print("\n[5/8] Running Pass 2 (char n-gram + retrieval vote)...")
    pass2 = run_pass2(candidates, all_texts, all_labels, retriever)
    with open(OUT_PASS2, "w", encoding="utf-8") as f:
        json.dump(pass2, f, indent=2, ensure_ascii=False)
    print(f"  Pass 2 complete: {len(pass2)} predictions saved.")

    # 6. Consistency comparison
    print("\n[6/8] Comparing Pass 1 vs Pass 2...")
    consistency, disagreements = compare_passes(pass1, pass2, candidates)
    with open(OUT_CONSISTENCY, "w", encoding="utf-8") as f:
        json.dump(consistency, f, indent=2, ensure_ascii=False)
    print(f"  Intent agreement: {consistency['intent_agreement']['count']}/200 ({consistency['intent_agreement']['rate']:.2%})")
    print(f"  Escalation agreement: {consistency['escalation_agreement']['count']}/200 ({consistency['escalation_agreement']['rate']:.2%})")
    print(f"  Disagreements: {consistency['disagreement_count']}")

    # 7. Adjudicate → provisional labels + review queue
    print("\n[7/8] Adjudicating and creating provisional labels...")
    provisional, review_queue, consensus_cnt, adjudicated_cnt = adjudicate(
        pass1, pass2, consistency, candidates, retriever
    )
    with open(OUT_PROVISIONAL, "w", encoding="utf-8") as f:
        json.dump(provisional, f, indent=2, ensure_ascii=False)
    with open(OUT_REVIEW_QUEUE, "w", encoding="utf-8") as f:
        json.dump(review_queue, f, indent=2, ensure_ascii=False)
    print(f"  Consensus: {consensus_cnt}")
    print(f"  Adjudicated: {adjudicated_cnt}")
    print(f"  Review queue: {len(review_queue)} examples")

    # 8. Summary
    print("\n[8/8] Generating summary...")
    summary = generate_summary(provisional, review_queue, consistency)
    with open(OUT_SUMMARY, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # Final integrity check
    chk2 = verify_checksum()

    # === FINAL REPORT ===
    print(f"\n{'=' * 80}")
    print("FINAL REPORT")
    print(f"{'=' * 80}")
    print(f"  Annotation source:         AI_ASSISTED_PROVISIONAL")
    print(f"  Total examples:            200")
    print(f"  Two-pass consensus:        {consensus_cnt} ({consensus_cnt/200:.1%})")
    print(f"  Disagreements adjudicated: {adjudicated_cnt}")
    print(f"  Manual review required:    {len(review_queue)}")
    esc_disagree = sum(1 for q in review_queue if q.get("escalation_disagree"))
    print(f"  Escalation disagreements:  {esc_disagree}")
    print(f"\n  Intent distribution:")
    for intent, count in sorted(summary["intent_distribution"].items()):
        print(f"    {intent}: {count}")
    print(f"\n  Escalation: {summary['escalation_distribution']}")
    print(f"  Ambiguity:  {summary['ambiguity_distribution']}")
    print(f"  Language:   {summary['language_distribution']}")
    print(f"\n  Adjudication methods:")
    for method, count in sorted(summary["adjudication_methods"].items()):
        print(f"    {method}: {count}")
    print(f"\n  Golden checksum: {chk2}")
    print(f"{'=' * 80}")

    print("\nFiles created:")
    for p in [OUT_PASS1, OUT_PASS2, OUT_CONSISTENCY, OUT_PROVISIONAL, OUT_REVIEW_QUEUE, OUT_SUMMARY]:
        print(f"  {p.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()

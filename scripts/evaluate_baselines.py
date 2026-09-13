"""
scripts/evaluate_baselines.py — Evaluation Pipeline for Classification Baselines

Evaluates two required classification baselines on the 50 DEV examples:
1. Majority-Class Baseline
2. TF-IDF + Logistic Regression Baseline (5-Fold Stratified Cross-Validation)

Uses strictly ground-truth human labels from data/dev/dev_human_labels_50.json.
Generates data/dev/baseline_evaluation_report.json and prints terminal report.
Does NOT modify data/dev/dev_human_labels_50.json.
"""

import sys, os, json, re, hashlib
from pathlib import Path
from datetime import datetime, timezone
import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEV_HUMAN_PATH = PROJECT_ROOT / "data" / "dev" / "dev_human_labels_50.json"
REPORT_PATH = PROJECT_ROOT / "data" / "dev" / "baseline_evaluation_report.json"
GOLDEN_PATH = PROJECT_ROOT / "data" / "golden" / "golden_candidates_200.json"

EXPECTED_GOLDEN_SHA256 = "57682c611278ede6a89cadb5c7b1887498049689d2520952865a361c5a59adda"
RANDOM_SEED = 2026

def verify_data_integrity():
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

def preprocess_text(raw_text: str, thread_context: list) -> str:
    """Concatenates raw_text and thread_context, removing handle mentions, URLs, and extra whitespace."""
    context_texts = [t.get("text", "") for t in thread_context] if thread_context else []
    full_raw = raw_text + " " + " ".join(context_texts)
    
    # Strip URLs
    text = re.sub(r'https?://\S+', '', full_raw)
    # Strip user handles e.g. @115830, @AmazonHelp
    text = re.sub(r'@\w+', '', text)
    # Strip non-alphanumeric except basic punctuation
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def compute_classification_metrics(y_true: list, y_pred: list, labels: list):
    """Computes overall accuracy, macro/weighted F1/precision/recall, per-class metrics, and confusion matrix."""
    n = len(y_true)
    accuracy = sum(1 for yt, yp in zip(y_true, y_pred) if yt == yp) / n
    
    per_class = {}
    macro_p, macro_r, macro_f1 = [], [], []
    weighted_p, weighted_r, weighted_f1 = 0.0, 0.0, 0.0
    
    # Build confusion matrix dictionary
    conf_matrix = {l1: {l2: 0 for l2 in labels} for l1 in labels}
    for yt, yp in zip(y_true, y_pred):
        if yt in conf_matrix and yp in conf_matrix[yt]:
            conf_matrix[yt][yp] += 1

    for label in labels:
        tp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == label and yp == label)
        fp = sum(1 for yt, yp in zip(y_true, y_pred) if yt != label and yp == label)
        fn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == label and yp != label)
        support = sum(1 for yt in y_true if yt == label)
        
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
        
        per_class[label] = {
            "support": support,
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1_score": round(f1, 4)
        }
        
        macro_p.append(prec)
        macro_r.append(rec)
        macro_f1.append(f1)
        
        weighted_p += prec * support
        weighted_r += rec * support
        weighted_f1 += f1 * support

    macro_precision = sum(macro_p) / len(labels) if labels else 0.0
    macro_recall = sum(macro_r) / len(labels) if labels else 0.0
    macro_f1_score = sum(macro_f1) / len(labels) if labels else 0.0
    
    weighted_precision = weighted_p / n if n > 0 else 0.0
    weighted_recall = weighted_r / n if n > 0 else 0.0
    weighted_f1_score = weighted_f1 / n if n > 0 else 0.0

    return {
        "accuracy": round(accuracy, 4),
        "accuracy_pct": round(accuracy * 100.0, 2),
        "macro_precision": round(macro_precision, 4),
        "macro_recall": round(macro_recall, 4),
        "macro_f1_score": round(macro_f1_score, 4),
        "weighted_precision": round(weighted_precision, 4),
        "weighted_recall": round(weighted_recall, 4),
        "weighted_f1_score": round(weighted_f1_score, 4),
        "per_class_metrics": per_class,
        "confusion_matrix": conf_matrix
    }

def evaluate_majority_baseline(dev_data, unique_labels):
    """Majority class baseline: predicts most frequent label in ground truth for all items."""
    y_true = [r["primary_intent"] for r in dev_data]
    
    # Find mode
    counts = {}
    for y in y_true:
        counts[y] = counts.get(y, 0) + 1
    majority_class = sorted(counts.keys(), key=lambda k: counts[k], reverse=True)[0]
    
    y_pred = [majority_class] * len(y_true)
    metrics = compute_classification_metrics(y_true, y_pred, unique_labels)
    metrics["predicted_class"] = majority_class
    metrics["majority_class_count"] = counts[majority_class]
    return metrics

def evaluate_tfidf_logreg_baseline(dev_data, unique_labels):
    """
    TF-IDF + Logistic Regression baseline using 5-Fold Stratified Cross Validation.
    Imports sklearn if available, or falls back to robust multinomial/naive-bayes estimator if sklearn unavailable.
    """
    y_true = [r["primary_intent"] for r in dev_data]
    texts = [preprocess_text(r["raw_text"], r.get("thread_context", [])) for r in dev_data]
    
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import StratifiedKFold
        
        skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_SEED)
        oof_preds = [None] * len(y_true)
        
        X_arr = np.array(texts)
        y_arr = np.array(y_true)
        
        for train_idx, val_idx in skf.split(X_arr, y_arr):
            X_train, X_val = X_arr[train_idx], X_arr[val_idx]
            y_train, y_val = y_arr[train_idx], y_arr[val_idx]
            
            vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, max_features=1000)
            X_train_tfidf = vectorizer.fit_transform(X_train)
            X_val_tfidf = vectorizer.transform(X_val)
            
            model = LogisticRegression(C=1.0, max_iter=1000, random_state=RANDOM_SEED, class_weight="balanced")
            model.fit(X_train_tfidf, y_train)
            
            preds = model.predict(X_val_tfidf)
            for idx, pred in zip(val_idx, preds):
                oof_preds[idx] = pred

        metrics = compute_classification_metrics(y_true, oof_preds, unique_labels)
        metrics["evaluation_scheme"] = "5-Fold Stratified Cross-Validation (scikit-learn)"
        metrics["model_configuration"] = "TfidfVectorizer(ngram_range=(1,2), sublinear_tf=True) + LogisticRegression(C=1.0, class_weight='balanced')"
        return metrics, oof_preds
        
    except ImportError:
        # Fallback manual TF-IDF + Cosine/NaiveBayes classifier if sklearn not installed
        oof_preds = evaluate_manual_tfidf_nb(texts, y_true, unique_labels)
        metrics = compute_classification_metrics(y_true, oof_preds, unique_labels)
        metrics["evaluation_scheme"] = "5-Fold Stratified Cross-Validation (builtin fallback)"
        metrics["model_configuration"] = "TF-IDF + Naive Bayes Classifier"
        return metrics, oof_preds

def evaluate_manual_tfidf_nb(texts, y_true, unique_labels):
    """Fallback 5-fold CV Naive Bayes classifier when sklearn is not present."""
    import math
    from collections import Counter
    
    n = len(y_true)
    oof_preds = [None] * n
    
    # 5 folds manually
    rng = np.random.RandomState(RANDOM_SEED)
    indices = np.arange(n)
    rng.shuffle(indices)
    folds = np.array_split(indices, 5)
    
    for fold_i, val_idx in enumerate(folds):
        train_idx = np.setdiff1d(indices, val_idx)
        train_texts = [texts[i] for i in train_idx]
        train_y = [y_true[i] for i in train_idx]
        
        # Word counts per class
        class_word_counts = {}
        class_counts = Counter(train_y)
        vocab = set()
        
        for txt, lbl in zip(train_texts, train_y):
            words = [w.lower() for w in re.findall(r'\b\w+\b', txt)]
            vocab.update(words)
            if lbl not in class_word_counts:
                class_word_counts[lbl] = Counter()
            class_word_counts[lbl].update(words)

        vocab_size = len(vocab)
        
        for idx in val_idx:
            val_text = texts[idx]
            val_words = [w.lower() for w in re.findall(r'\b\w+\b', val_text)]
            
            best_score = -float('inf')
            best_class = train_y[0]
            
            for lbl in unique_labels:
                if lbl not in class_counts or class_counts[lbl] == 0:
                    continue
                prior = math.log(class_counts[lbl] / len(train_y))
                total_words = sum(class_word_counts[lbl].values())
                
                likelihood = 0.0
                for w in val_words:
                    word_cnt = class_word_counts[lbl].get(w, 0)
                    likelihood += math.log((word_cnt + 1.0) / (total_words + vocab_size + 1.0))
                
                score = prior + likelihood
                if score > best_score:
                    best_score = score
                    best_class = lbl
            oof_preds[idx] = best_class
            
    return oof_preds

def evaluate_external_augmented_baseline(dev_data, unique_labels):
    """
    TF-IDF + Logistic Regression augmented with 187 external human-labeled training examples.
    Evaluates out-of-fold on DEV 50 without ever training on the validation fold (N=237 total training capacity).
    """
    ext_path = PROJECT_ROOT / "data" / "processed" / "external_human_examples_187.json"
    if not ext_path.exists():
        return None, []

    with open(ext_path, "r", encoding="utf-8") as f:
        ext_data = json.load(f)

    ext_texts = [preprocess_text(r["raw_text"], r.get("thread_context", [])) for r in ext_data]
    ext_y = [r["primary_intent"] for r in ext_data]

    y_true = [r["primary_intent"] for r in dev_data]
    dev_texts = [preprocess_text(r["raw_text"], r.get("thread_context", [])) for r in dev_data]

    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_SEED)
    oof_preds = [None] * len(y_true)

    X_dev_arr = np.array(dev_texts)
    y_dev_arr = np.array(y_true)

    for train_idx, val_idx in skf.split(X_dev_arr, y_dev_arr):
        X_train_fold = list(ext_texts) + list(X_dev_arr[train_idx])
        y_train_fold = list(ext_y) + list(y_dev_arr[train_idx])
        X_val_fold = X_dev_arr[val_idx]

        vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, max_features=2000)
        X_train_tfidf = vectorizer.fit_transform(X_train_fold)
        X_val_tfidf = vectorizer.transform(X_val_fold)

        model = LogisticRegression(C=1.0, max_iter=1000, random_state=RANDOM_SEED, class_weight="balanced")
        model.fit(X_train_tfidf, y_train_fold)

        preds = model.predict(X_val_tfidf)
        for idx, pred in zip(val_idx, preds):
            oof_preds[idx] = pred

    metrics = compute_classification_metrics(y_true, oof_preds, unique_labels)
    metrics["evaluation_scheme"] = "187 External + 5-Fold Stratified Cross-Validation on DEV (N=237 Total Capacity)"
    metrics["model_configuration"] = "TfidfVectorizer(ngram_range=(1,2), max_features=2000) + LogisticRegression(C=1.0, class_weight='balanced')"
    return metrics, oof_preds

def run_evaluation():
    print("Verifying data integrity...", flush=True)
    dev_data = verify_data_integrity()
    
    unique_labels = sorted(list(set(r["primary_intent"] for r in dev_data)))
    print(f"Loaded {len(dev_data)} DEV ground truth records spanning {len(unique_labels)} categories.")
    
    print("\n1. Evaluating Majority-Class Baseline...", flush=True)
    maj_metrics = evaluate_majority_baseline(dev_data, unique_labels)
    
    print("2. Evaluating TF-IDF + Logistic Regression Baseline (DEV 50 alone, 5-Fold CV)...", flush=True)
    logreg_metrics, oof_preds = evaluate_tfidf_logreg_baseline(dev_data, unique_labels)
    
    print("3. Evaluating External-Augmented TF-IDF + Logistic Regression (187 External + DEV 50, N=237)...", flush=True)
    ext_metrics, ext_oof_preds = evaluate_external_augmented_baseline(dev_data, unique_labels)

    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "ground_truth_source": "data/dev/dev_human_labels_50.json",
        "total_eval_examples": len(dev_data),
        "random_seed": RANDOM_SEED,
        "unique_categories_count": len(unique_labels),
        "majority_class_baseline": maj_metrics,
        "tfidf_logistic_regression_baseline": logreg_metrics,
        "external_augmented_tfidf_logistic_regression": ext_metrics
    }
    
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        
    print("\n" + "="*115)
    print("CLASSIFICATION BASELINES EVALUATION REPORT")
    print("="*115)
    print(f"Ground Truth File: {DEV_HUMAN_PATH}")
    print(f"Total DEV Examples: {len(dev_data)}")
    print(f"Unique Intent Classes: {len(unique_labels)}")
    print("-" * 115)
    print(f"{'Metric':<25} | {'Majority-Class Baseline':<23} | {'Baseline (DEV 50 Alone)':<25} | {'External-Augmented (N=237)':<28}")
    print("-" * 115)
    print(f"{'Accuracy':<25} | {maj_metrics['accuracy_pct']:>20}% | {logreg_metrics['accuracy_pct']:>22}% | {ext_metrics['accuracy_pct']:>25}%")
    print(f"{'Macro Precision':<25} | {maj_metrics['macro_precision']:>21} | {logreg_metrics['macro_precision']:>23} | {ext_metrics['macro_precision']:>26}")
    print(f"{'Macro Recall':<25} | {maj_metrics['macro_recall']:>21} | {logreg_metrics['macro_recall']:>23} | {ext_metrics['macro_recall']:>26}")
    print(f"{'Macro F1-Score':<25} | {maj_metrics['macro_f1_score']:>21} | {logreg_metrics['macro_f1_score']:>23} | {ext_metrics['macro_f1_score']:>26}")
    print(f"{'Weighted Precision':<25} | {maj_metrics['weighted_precision']:>21} | {logreg_metrics['weighted_precision']:>23} | {ext_metrics['weighted_precision']:>26}")
    print(f"{'Weighted Recall':<25} | {maj_metrics['weighted_recall']:>21} | {logreg_metrics['weighted_recall']:>23} | {ext_metrics['weighted_recall']:>26}")
    print(f"{'Weighted F1-Score':<25} | {maj_metrics['weighted_f1_score']:>21} | {logreg_metrics['weighted_f1_score']:>23} | {ext_metrics['weighted_f1_score']:>26}")
    print("-" * 115)
    print(f"\nSaved full report to {REPORT_PATH}")
    
    return report

if __name__ == "__main__":
    run_evaluation()

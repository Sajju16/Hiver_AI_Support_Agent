"""
tests/test_evaluate_baselines.py — Unit tests for Classification Baselines Evaluation Pipeline

Proves:
1. Ground truth data loading and integrity from data/dev/dev_human_labels_50.json
2. Text preprocessing and feature preparation
3. Majority class baseline accuracy computation
4. TF-IDF + Logistic Regression 5-fold cross validation output structure
5. Metric computation correctness
6. Ground truth file and Golden set immutability
"""

import sys
import json
import hashlib
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate_baselines import (
    verify_data_integrity,
    preprocess_text,
    compute_classification_metrics,
    evaluate_majority_baseline,
    evaluate_tfidf_logreg_baseline,
    DEV_HUMAN_PATH,
    GOLDEN_PATH,
    EXPECTED_GOLDEN_SHA256
)

class TestEvaluateBaselines(unittest.TestCase):

    def test_1_data_integrity_and_file_protection(self):
        """Proves dev_human_labels_50.json contains 50 valid ground truth records and Golden set is sealed."""
        dev_data = verify_data_integrity()
        self.assertEqual(len(dev_data), 50)
        
        # Verify no null primary_intent
        for r in dev_data:
            self.assertIsNotNone(r.get("primary_intent"))
            
        # Golden SHA-256 verification
        with open(GOLDEN_PATH, "rb") as f:
            computed_hash = hashlib.sha256(f.read()).hexdigest().lower()
        self.assertEqual(computed_hash, EXPECTED_GOLDEN_SHA256)

    def test_2_preprocess_text(self):
        """Proves text preprocessing strips handle mentions, URLs, and combines thread context."""
        raw_text = "@AmazonHelp hi my order is late https://t.co/123xyz"
        thread_ctx = [{"author": "12345", "text": "Where is package?"}]
        cleaned = preprocess_text(raw_text, thread_ctx)
        self.assertNotIn("https://", cleaned)
        self.assertNotIn("@AmazonHelp", cleaned)
        self.assertIn("hi my order is late", cleaned)
        self.assertIn("Where is package?", cleaned)

    def test_3_majority_baseline_metrics(self):
        """Proves majority class baseline predicts mode class and computes metrics."""
        dev_data = verify_data_integrity()
        unique_labels = sorted(list(set(r["primary_intent"] for r in dev_data)))
        maj_metrics = evaluate_majority_baseline(dev_data, unique_labels)
        
        self.assertEqual(maj_metrics["predicted_class"], "Delivery_Tracking_And_Delays")
        self.assertEqual(maj_metrics["majority_class_count"], 14)
        self.assertEqual(maj_metrics["accuracy_pct"], 28.0) # 14 / 50 = 28%

    def test_4_tfidf_logreg_baseline_cross_validation(self):
        """Proves 5-fold CV generates out-of-fold predictions for all 50 DEV items."""
        dev_data = verify_data_integrity()
        unique_labels = sorted(list(set(r["primary_intent"] for r in dev_data)))
        metrics, oof_preds = evaluate_tfidf_logreg_baseline(dev_data, unique_labels)
        
        self.assertEqual(len(oof_preds), 50)
        self.assertNotIn(None, oof_preds)
        self.assertGreater(metrics["accuracy_pct"], 0.0)

    def test_5_compute_metrics_correctness(self):
        """Proves classification metrics calculation logic."""
        y_true = ["A", "A", "B", "B"]
        y_pred = ["A", "B", "B", "B"]
        labels = ["A", "B"]
        
        m = compute_classification_metrics(y_true, y_pred, labels)
        self.assertEqual(m["accuracy"], 0.75)
        self.assertEqual(m["accuracy_pct"], 75.0)

if __name__ == "__main__":
    unittest.main()

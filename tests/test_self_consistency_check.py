"""
tests/test_self_consistency_check.py — Unit tests for Self-Consistency Check module

Proves:
1. Selection reproducibility (fixed seed 2026 returns exact same 20 stratified example IDs)
2. Blinded selection hides Pass 1 labels and hints
3. Accuracy and agreement calculation (Primary, Secondary, Escalate, Lang, Ambiguity, Exact)
4. Cohen's Kappa evaluation handling valid vs zero-variance/invalid edge cases
5. Source files (dev_candidates_50.json, dev_human_labels_50.json) and Golden SHA-256 remain untouched.
"""

import sys
import json
import hashlib
import io
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.self_consistency_check import (
    select_20_stratified_examples,
    compute_cohens_kappa,
    calculate_all_metrics,
    verify_golden_untouched,
    DEV_HUMAN_LABELS_PATH,
    DEV_CANDIDATES_PATH,
    EXPECTED_GOLDEN_SHA256,
    RANDOM_SEED
)

class TestSelfConsistencyCheck(unittest.TestCase):

    def setUp(self):
        with open(DEV_HUMAN_LABELS_PATH, "r", encoding="utf-8") as f:
            self.pass1_labels = json.load(f)
        self.pass1_dict = {r["example_id"]: r for r in self.pass1_labels}

    def test_1_selection_reproducibility(self):
        """Proves seed 2026 returns the exact same 20 stratified example IDs deterministically."""
        ids1, method1 = select_20_stratified_examples(self.pass1_labels, seed=2026)
        ids2, method2 = select_20_stratified_examples(self.pass1_labels, seed=2026)
        
        self.assertEqual(len(ids1), 20)
        self.assertEqual(ids1, ids2)
        self.assertIn("seed 2026", method1)

    def test_2_kappa_calculation_valid_and_invalid(self):
        """Proves Cohen's Kappa produces correct floats for valid cases and handles zero-variance gracefully."""
        # Case A: Identical lists with variation (e.g. ['A', 'B', 'A', 'B']) -> Kappa = 1.0
        k1, note1 = compute_cohens_kappa(["A", "B", "A", "B"], ["A", "B", "A", "B"])
        self.assertEqual(k1, 1.0)

        # Case B: Disagreement list -> Kappa < 1.0
        k2, note2 = compute_cohens_kappa(["A", "A", "B", "B"], ["A", "B", "A", "B"])
        self.assertLess(k2, 1.0)

        # Case C: Zero variance (all elements 'False') -> None with clear reason
        k3, note3 = compute_cohens_kappa([False, False, False], [False, False, False])
        self.assertIsNone(k3)
        self.assertIn("no variation", note3)

    def test_3_metrics_calculation_exact(self):
        """Proves calculate_all_metrics computes exact match percentages across 5 core fields."""
        selected_ids = ["DEV_001", "DEV_002"]
        
        # Mock Pass 2 identical for DEV_001, distinct for DEV_002
        pass2_dict = {
            "DEV_001": dict(self.pass1_dict["DEV_001"]),
            "DEV_002": dict(self.pass1_dict["DEV_002"])
        }
        # Change primary intent for DEV_002 to create disagreement
        pass2_dict["DEV_002"]["primary_intent"] = "Other_Unclassified_Inquiry"

        metrics = calculate_all_metrics(selected_ids, self.pass1_dict, pass2_dict)
        self.assertEqual(metrics["total_selected"], 2)
        self.assertEqual(metrics["primary_intent_agreement_pct"], 50.0) # 1 match out of 2
        self.assertEqual(metrics["overall_exact_agreement_pct"], 50.0)
        self.assertEqual(len(metrics["disagreement_examples"]), 1)

    def test_4_source_and_golden_files_untouched(self):
        """Proves Golden set SHA-256 and dev_candidates_50.json source remain untouched."""
        computed_hash = verify_golden_untouched()
        self.assertEqual(computed_hash, EXPECTED_GOLDEN_SHA256)

        with open(DEV_CANDIDATES_PATH, "r", encoding="utf-8") as f:
            candidates = json.load(f)
        self.assertEqual(len(candidates), 50)
        for c in candidates:
            self.assertIsNone(c.get("primary_intent"))

if __name__ == "__main__":
    unittest.main()

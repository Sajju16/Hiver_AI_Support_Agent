"""
tests/test_evidence_assisted_annotation.py — Unit tests for Evidence-Assisted Golden Annotation System
"""

import sys, os, json, hashlib, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_evidence_assisted_golden_annotation import (
    load_human_reference_dataset,
    HIGH_CONFIDENCE_FILE,
    MANUAL_REVIEW_FILE,
    PROJECT_ROOT
)
from src.ai.agent_pipeline import (
    GOLDEN_PATH,
    DEV_HUMAN_PATH,
    EXTERNAL_187_PATH,
    EXPECTED_GOLDEN_SHA256
)

class TestEvidenceAssistedAnnotation(unittest.TestCase):

    def test_1_reference_dataset_count_and_integrity(self):
        """Proves 237 human-labelled reference examples are loaded cleanly without touching Golden candidates."""
        ref_examples = load_human_reference_dataset()
        self.assertEqual(len(ref_examples), 237)
        
        dev_count = sum(1 for r in ref_examples if r["source"] == "dev_human_labels_50")
        ext_count = sum(1 for r in ref_examples if r["source"] == "external_human_examples_187")
        self.assertEqual(dev_count, 50)
        self.assertEqual(ext_count, 187)

    def test_2_golden_checksum_integrity(self):
        """Proves Golden candidate 200 file checksum remains completely untampered."""
        with open(GOLDEN_PATH, "rb") as f:
            computed_hash = hashlib.sha256(f.read()).hexdigest().lower()
        self.assertEqual(computed_hash, EXPECTED_GOLDEN_SHA256)

    def test_3_output_files_and_evidence_schema(self):
        """Verifies generated output files exist and contain full required evidence structure."""
        self.assertTrue(HIGH_CONFIDENCE_FILE.exists())
        self.assertTrue(MANUAL_REVIEW_FILE.exists())

        with open(HIGH_CONFIDENCE_FILE, "r", encoding="utf-8") as f:
            high_conf = json.load(f)
        with open(MANUAL_REVIEW_FILE, "r", encoding="utf-8") as f:
            manual_queue = json.load(f)

        total_processed = len(high_conf) + len(manual_queue)
        self.assertEqual(total_processed, 200)

        # Check evidence schema on first item in manual queue
        sample = manual_queue[0] if manual_queue else high_conf[0]
        self.assertIn("predicted_intent", sample)
        self.assertIn("top_3_reference_example_ids", sample)
        self.assertIn("top_3_reference_human_intents", sample)
        self.assertIn("top_3_similarity_scores", sample)
        self.assertIn("vote_distribution", sample)
        self.assertIn("classifier_prediction", sample)
        self.assertIn("retrieval_prediction", sample)
        self.assertIn("confidence_status", sample)
        self.assertIn("decision_reason", sample)
        self.assertEqual(sample["annotation_source"], "AI_ASSISTED_PROVISIONAL")

    def test_4_no_b2_b3_b4_b5_in_high_confidence(self):
        """Verifies that high-confidence auto-accepted set contains ZERO B2/B3/B4/B5 examples."""
        with open(HIGH_CONFIDENCE_FILE, "r", encoding="utf-8") as f:
            high_conf = json.load(f)

        for record in high_conf:
            bucket = record["candidate_bucket"]
            self.assertEqual(bucket, "B1_core", f"Example {record['example_id']} has bucket {bucket} in high confidence!")

if __name__ == "__main__":
    unittest.main()

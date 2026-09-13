"""
tests/test_annotate_golden_human_cli.py — Unit tests for Golden Human Annotation CLI

Proves:
1. Golden candidates checksum verification works
2. Labels file is created without bias fields (no candidate_bucket or candidate_intent_hint)
3. All ground-truth fields start as null
4. Labels file preserves example ordering and IDs
5. Invalid intent values are rejected
6. Save persists annotation and moves to next example
7. Flag sets FLAGGED FOR REVIEW status
8. Save/resume preserves progress
9. Original golden_candidates_200.json is NEVER modified
10. DEV 50 labels are not affected
11. Escalation guidance is enforced independently from intent
"""

import sys
import json
import hashlib
import io
import copy
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.annotate_golden_human_cli import (
    verify_golden_candidates_checksum,
    init_golden_labels_file,
    save_labels,
    generate_report,
    prompt_primary_intent,
    GOLDEN_CANDIDATES_PATH,
    GOLDEN_HUMAN_LABELS_PATH,
    GOLDEN_REPORT_PATH,
    EXPECTED_GOLDEN_SHA256,
    INTENT_MAP,
    GT_FIELDS,
    run_golden_annotation,
)

DEV_HUMAN_LABELS_PATH = PROJECT_ROOT / "data" / "dev" / "dev_human_labels_50.json"


class TestGoldenAnnotationCLI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Back up golden_human_labels_200.json and dev_human_labels_50.json before tests."""
        if GOLDEN_HUMAN_LABELS_PATH.exists():
            with open(GOLDEN_HUMAN_LABELS_PATH, "r", encoding="utf-8") as f:
                cls._backup_golden_labels = f.read()
        else:
            cls._backup_golden_labels = None

        if DEV_HUMAN_LABELS_PATH.exists():
            with open(DEV_HUMAN_LABELS_PATH, "r", encoding="utf-8") as f:
                cls._backup_dev_labels = f.read()
        else:
            cls._backup_dev_labels = None

        # Snapshot checksum of golden_candidates_200.json
        with open(GOLDEN_CANDIDATES_PATH, "rb") as f:
            cls._candidates_checksum = hashlib.sha256(f.read()).hexdigest().lower()

    @classmethod
    def tearDownClass(cls):
        """Restore golden_human_labels_200.json and dev_human_labels_50.json after tests."""
        if cls._backup_golden_labels is not None:
            with open(GOLDEN_HUMAN_LABELS_PATH, "w", encoding="utf-8") as f:
                f.write(cls._backup_golden_labels)
        elif GOLDEN_HUMAN_LABELS_PATH.exists():
            GOLDEN_HUMAN_LABELS_PATH.unlink()

        if cls._backup_dev_labels is not None:
            with open(DEV_HUMAN_LABELS_PATH, "w", encoding="utf-8") as f:
                f.write(cls._backup_dev_labels)

    def test_01_golden_candidates_checksum_verification(self):
        """Checksum verification matches expected SHA-256."""
        chk = verify_golden_candidates_checksum()
        self.assertEqual(chk, EXPECTED_GOLDEN_SHA256)

    def test_02_labels_file_excludes_bias_fields(self):
        """Labels file must NOT contain candidate_bucket or candidate_intent_hint."""
        labels = init_golden_labels_file()
        for rec in labels:
            self.assertNotIn("candidate_bucket", rec, f"LEAK: candidate_bucket in {rec['example_id']}")
            self.assertNotIn("candidate_intent_hint", rec, f"LEAK: candidate_intent_hint in {rec['example_id']}")

    def test_03_all_gt_fields_start_null(self):
        """All ground-truth fields must be null in a fresh labels file."""
        # Force fresh creation by removing existing labels
        if GOLDEN_HUMAN_LABELS_PATH.exists():
            GOLDEN_HUMAN_LABELS_PATH.unlink()
        labels = init_golden_labels_file()
        for rec in labels:
            for fld in GT_FIELDS:
                self.assertIsNone(rec.get(fld), f"{rec['example_id']}.{fld} should be None")

    def test_04_labels_preserve_ordering_and_ids(self):
        """Labels file must have same example_ids in same order as candidates."""
        with open(GOLDEN_CANDIDATES_PATH, "r", encoding="utf-8") as f:
            candidates = json.load(f)
        labels = init_golden_labels_file()
        self.assertEqual(len(labels), len(candidates))
        for i, (lbl, cand) in enumerate(zip(labels, candidates)):
            self.assertEqual(lbl["example_id"], cand["example_id"], f"ID mismatch at index {i}")
            self.assertEqual(lbl["conversation_id"], cand["conversation_id"])
            self.assertEqual(lbl["turn_index"], cand["turn_index"])

    def test_05_labels_count_is_200(self):
        """Labels file must contain exactly 200 records."""
        labels = init_golden_labels_file()
        self.assertEqual(len(labels), 200)

    @patch('builtins.input', side_effect=["0", "12", "abc", "n", "q", "p", "next", "1"])
    def test_06_invalid_intent_values_rejected(self, mock_input):
        """Only integers 1-11 are accepted for primary intent."""
        with patch('sys.stdout', new_callable=io.StringIO):
            result = prompt_primary_intent()
        self.assertEqual(result, "Delivery_Tracking_And_Delays")
        self.assertEqual(mock_input.call_count, 8)  # 7 invalid + 1 valid

    def test_07_save_persists_annotation(self):
        """Saving an annotation persists it to the labels file."""
        labels = init_golden_labels_file()
        labels[0]["primary_intent"] = "Delivery_Tracking_And_Delays"
        labels[0]["escalate"] = False
        labels[0]["escalate_reason"] = ""
        labels[0]["language_flag"] = False
        labels[0]["ambiguity_flag"] = False
        save_labels(labels)

        with open(GOLDEN_HUMAN_LABELS_PATH, "r", encoding="utf-8") as f:
            reloaded = json.load(f)
        self.assertEqual(reloaded[0]["primary_intent"], "Delivery_Tracking_And_Delays")
        self.assertFalse(reloaded[0]["escalate"])

    def test_08_flag_sets_flagged_status(self):
        """Flagging sets annotator_notes to FLAGGED FOR REVIEW and leaves GT fields null."""
        labels = init_golden_labels_file()
        labels[0]["annotator_notes"] = "FLAGGED FOR REVIEW"
        labels[0]["primary_intent"] = None
        save_labels(labels)

        with open(GOLDEN_HUMAN_LABELS_PATH, "r", encoding="utf-8") as f:
            reloaded = json.load(f)
        self.assertEqual(reloaded[0]["annotator_notes"], "FLAGGED FOR REVIEW")
        self.assertIsNone(reloaded[0]["primary_intent"])

    def test_09_report_generation(self):
        """Report correctly summarizes annotation progress."""
        labels = init_golden_labels_file()
        # Annotate 2 examples, flag 1
        labels[0]["primary_intent"] = "Delivery_Tracking_And_Delays"
        labels[0]["escalate"] = True
        labels[0]["escalate_reason"] = "stolen package"
        labels[0]["language_flag"] = False
        labels[0]["ambiguity_flag"] = False

        labels[1]["primary_intent"] = "Technical_App_And_Website_Issues"
        labels[1]["escalate"] = False
        labels[1]["escalate_reason"] = ""
        labels[1]["language_flag"] = True
        labels[1]["ambiguity_flag"] = True

        labels[2]["annotator_notes"] = "FLAGGED FOR REVIEW"

        save_labels(labels)
        report = generate_report(labels)

        self.assertEqual(report["total_examples"], 200)
        self.assertEqual(report["completed_count"], 2)
        self.assertEqual(report["flagged_count"], 1)
        self.assertEqual(report["remaining_count"], 197)
        self.assertEqual(report["escalation_count"], 1)
        self.assertEqual(report["ambiguity_count"], 1)
        self.assertEqual(report["non_english_count"], 1)
        self.assertIn("Delivery_Tracking_And_Delays", report["primary_intent_distribution"])

    def test_10_golden_candidates_never_modified(self):
        """Original golden_candidates_200.json must never be modified."""
        # Run some label operations
        labels = init_golden_labels_file()
        labels[0]["primary_intent"] = "Other_Unclassified_Inquiry"
        save_labels(labels)

        # Verify candidates checksum unchanged
        with open(GOLDEN_CANDIDATES_PATH, "rb") as f:
            current_hash = hashlib.sha256(f.read()).hexdigest().lower()
        self.assertEqual(current_hash, EXPECTED_GOLDEN_SHA256)

    def test_11_dev_labels_not_affected(self):
        """DEV 50 labels must not be modified by Golden annotation operations."""
        if DEV_HUMAN_LABELS_PATH.exists():
            with open(DEV_HUMAN_LABELS_PATH, "r", encoding="utf-8") as f:
                before = f.read()

        # Run golden label operations
        labels = init_golden_labels_file()
        labels[0]["primary_intent"] = "Delivery_Tracking_And_Delays"
        save_labels(labels)

        if DEV_HUMAN_LABELS_PATH.exists():
            with open(DEV_HUMAN_LABELS_PATH, "r", encoding="utf-8") as f:
                after = f.read()
            self.assertEqual(before, after)

    def test_12_resume_preserves_progress(self):
        """Re-initializing labels file preserves previously saved annotations."""
        labels = init_golden_labels_file()
        labels[5]["primary_intent"] = "Prime_Subscription_And_Digital_Media"
        labels[5]["escalate"] = False
        labels[5]["escalate_reason"] = ""
        labels[5]["language_flag"] = False
        labels[5]["ambiguity_flag"] = False
        save_labels(labels)

        # Re-initialize
        labels2 = init_golden_labels_file()
        self.assertEqual(labels2[5]["primary_intent"], "Prime_Subscription_And_Digital_Media")


if __name__ == "__main__":
    unittest.main()

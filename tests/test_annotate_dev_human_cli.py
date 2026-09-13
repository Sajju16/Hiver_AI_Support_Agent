"""
tests/test_annotate_dev_human_cli.py — Unit tests for Human Annotation CLI

Proves:
1. Invalid intent values are rejected (n, next, q, quit, p, prev, 0, 12, etc.)
2. No annotation can be saved without a valid primary intent
3. Save moves to the next example
4. Flagging a record sets annotator_notes="FLAGGED FOR REVIEW" and leaves all ground-truth fields null
5. Flagged record resumes correctly (queue jumps to next unprocessed record)
6. Flagged count is reported separately in counts and completion report
7. Reviewing a flagged record via 'r' mode and saving a real annotation removes its flagged status
8. Quit preserves existing progress (both completed and flagged)
9. Source dev_candidates_50.json remains unchanged
10. Golden SHA-256 remains unchanged
11. candidate_bucket and candidate_intent_hint are not displayed
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

from scripts.annotate_dev_human_cli import (
    prompt_primary_intent,
    verify_golden_untouched,
    init_human_labels_file,
    generate_completion_report,
    DEV_CANDIDATES_PATH,
    DEV_HUMAN_LABELS_PATH,
    DEV_REPORT_PATH,
    GOLDEN_PATH,
    EXPECTED_GOLDEN_SHA256,
    INTENT_MAP,
    run_labeling_session
)

class TestHumanAnnotationCLI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Back up dev_human_labels_50.json before tests run."""
        if DEV_HUMAN_LABELS_PATH.exists():
            with open(DEV_HUMAN_LABELS_PATH, "r", encoding="utf-8") as f:
                cls._backup_labels = f.read()
        else:
            cls._backup_labels = None

    @classmethod
    def tearDownClass(cls):
        """Restore dev_human_labels_50.json after tests complete."""
        if cls._backup_labels is not None:
            with open(DEV_HUMAN_LABELS_PATH, "w", encoding="utf-8") as f:
                f.write(cls._backup_labels)

    def setUp(self):
        """Reset dev_human_labels_50.json to fresh state before each test."""
        if DEV_HUMAN_LABELS_PATH.exists():
            try:
                DEV_HUMAN_LABELS_PATH.unlink()
            except Exception:
                pass
        if DEV_REPORT_PATH.exists():
            try:
                DEV_REPORT_PATH.unlink()
            except Exception:
                pass
        init_human_labels_file()

    def tearDown(self):
        """Clean up report path after test."""
        if DEV_REPORT_PATH.exists():
            DEV_REPORT_PATH.unlink()

    def test_1_invalid_intent_values_rejected(self):
        """Test that invalid intent inputs (n, next, q, quit, p, prev, 0, 12, text) are all rejected until 1-11 is provided."""
        invalid_inputs = ["n", "next", "q", "quit", "p", "prev", "0", "12", "invalid_text", "", "  ", "1"]
        with patch("builtins.input", side_effect=invalid_inputs):
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                result = prompt_primary_intent()
                output = mock_stdout.getvalue()
                
                self.assertIn("ERROR: Invalid input", output)
                error_count = output.count("ERROR: Invalid input")
                self.assertEqual(error_count, 11)
                self.assertEqual(result, INTENT_MAP[1])

    def test_2_no_annotation_saved_without_valid_primary_intent(self):
        """Proves that primary intent prompt blocks until valid int 1-11 is returned."""
        with patch("builtins.input", side_effect=["invalid", "99", "10"]):
            intent = prompt_primary_intent()
            self.assertEqual(intent, INTENT_MAP[10])

    def test_3_save_moves_to_next_example_and_n_reprompts(self):
        """Proves saving advances index, while N discards and re-prompts."""
        inputs = [
            "c", "1", "", "n", "n", "n", "", "n",  # Example 0: input 'n' at save confirmation -> discard
            "c", "1", "", "n", "n", "n", "", "y",  # Example 0: input 'y' at save confirmation -> save
            "q"                                    # Example 1: quit session
        ]
        with patch("builtins.input", side_effect=inputs):
            human_queue = run_labeling_session(auto_start=True)
            self.assertIsNotNone(human_queue)
            self.assertEqual(human_queue[0]["primary_intent"], INTENT_MAP[1])

    def test_4_flag_record_sets_null_fields_and_notes(self):
        """Proves choosing 'f' sets annotator_notes='FLAGGED FOR REVIEW' and leaves ground-truth fields null."""
        inputs = ["f", "q"]
        with patch("builtins.input", side_effect=inputs):
            human_queue = run_labeling_session(auto_start=True)
            rec = human_queue[0]
            self.assertEqual(rec["annotator_notes"], "FLAGGED FOR REVIEW")
            self.assertIsNone(rec["primary_intent"])
            self.assertIsNone(rec["secondary_intent"])
            self.assertIsNone(rec["escalate"])
            self.assertIsNone(rec["escalate_reason"])
            self.assertIsNone(rec["language_flag"])
            self.assertIsNone(rec["ambiguity_flag"])

    def test_5_flagged_record_resumes_correctly(self):
        """Proves session relaunch skips past flagged records to next unprocessed example."""
        # Session 1: Flag Example 0
        inputs1 = ["f", "q"]
        with patch("builtins.input", side_effect=inputs1):
            run_labeling_session(auto_start=True)

        # Session 2: Check startup resume and option for Example 1
        inputs2 = ["c", "2", "", "n", "n", "n", "", "y", "q"]
        with patch("builtins.input", side_effect=inputs2):
            human_queue = run_labeling_session(auto_start=True)
            self.assertEqual(human_queue[0]["annotator_notes"], "FLAGGED FOR REVIEW")
            self.assertEqual(human_queue[1]["primary_intent"], INTENT_MAP[2])

    def test_6_flagged_count_reported_separately(self):
        """Proves counts report Completed, Flagged for review, and Remaining separately."""
        # Step 1: Complete Ex 0 and Flag Ex 1
        inputs = [
            "c", "1", "", "n", "n", "n", "", "y",  # Complete Ex 0
            "f",                                  # Flag Ex 1
            "q"                                    # Quit
        ]
        with patch("builtins.input", side_effect=inputs):
            human_queue = run_labeling_session(auto_start=True)
            report = generate_completion_report(human_queue)

            self.assertEqual(report["total_examples"], 50)
            self.assertEqual(report["completed_count"], 1)
            self.assertEqual(report["flagged_count"], 1)
            self.assertEqual(report["remaining_count"], 48)

        # Step 2: Relaunch and check startup stdout report
        with patch("builtins.input", side_effect=["q"]):
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                run_labeling_session(auto_start=True)
                out = mock_stdout.getvalue()
                self.assertIn("Completed         : 1", out)
                self.assertIn("Flagged for review: 1", out)
                self.assertIn("Remaining         : 48", out)

    def test_7_review_flagged_and_label_removes_flagged_status(self):
        """Proves reviewing a flagged record via 'r' mode and adding a real label removes its flagged status."""
        # 1. Flag Ex 0
        inputs_flag = ["f", "q"]
        with patch("builtins.input", side_effect=inputs_flag):
            run_labeling_session(auto_start=True)

        # 2. Relaunch session, select 'r', label Ex 0, and save
        inputs_review = [
            "r",        # Select review flagged
            "l",        # Label now
            "5", "", "n", "n", "n", "Resolved ambiguity", "y", # Label Ex 0
            "q"         # Quit main session
        ]
        with patch("builtins.input", side_effect=inputs_review):
            human_queue = run_labeling_session(auto_start=True)
            rec = human_queue[0]
            self.assertEqual(rec["primary_intent"], INTENT_MAP[5])
            self.assertEqual(rec["annotator_notes"], "Resolved ambiguity")
            self.assertNotEqual(rec["annotator_notes"], "FLAGGED FOR REVIEW")

    def test_8_quit_preserves_existing_progress(self):
        """Proves quitting exits cleanly without clearing previously saved annotations."""
        inputs_save = ["c", "1", "", "n", "n", "n", "", "y", "q"]
        with patch("builtins.input", side_effect=inputs_save):
            run_labeling_session(auto_start=True)

        inputs_quit = ["q"]
        with patch("builtins.input", side_effect=inputs_quit):
            human_queue = run_labeling_session(auto_start=True)
            self.assertIsNotNone(human_queue)
            self.assertEqual(human_queue[0]["primary_intent"], INTENT_MAP[1])

    def test_9_source_dev_candidates_remains_unchanged(self):
        """Proves data/dev/dev_candidates_50.json source is untouched."""
        with open(DEV_CANDIDATES_PATH, "r", encoding="utf-8") as f:
            candidates = json.load(f)
        self.assertEqual(len(candidates), 50)
        for c in candidates:
            self.assertIsNone(c.get("primary_intent"))

    def test_10_golden_sha256_remains_unchanged(self):
        """Proves Golden set hash matches exact expected hash."""
        computed_hash = verify_golden_untouched()
        self.assertEqual(computed_hash, EXPECTED_GOLDEN_SHA256)

    def test_11_hints_not_displayed(self):
        """Proves candidate_bucket and candidate_intent_hint are never displayed to annotator."""
        inputs = ["q"]
        with patch("builtins.input", side_effect=inputs):
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                run_labeling_session(auto_start=True)
                out = mock_stdout.getvalue()
                self.assertNotIn("candidate_bucket", out)
                self.assertNotIn("candidate_intent_hint", out)

if __name__ == "__main__":
    unittest.main()

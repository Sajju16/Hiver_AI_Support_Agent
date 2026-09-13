"""
tests/test_golden_150_verification.py — Comprehensive Unit Tests for Golden 150 Verification Pipeline

Proves:
1. Exactly 150 official candidates in golden_official_candidates_150.json.
2. No duplicate example IDs.
3. No duplicate (conversation_id, turn_index) pairs.
4. Sealed 200 candidate pool checksum remains untouched (57682c611278ede6a89cadb5c7b1887498049689d2520952865a361c5a59adda).
5. Golden 150 has zero overlap with DEV 50.
6. Golden 150 has zero overlap with external reference 187 data.
7. Deterministic stratified sampling allocation (B1: 75, B2: 25, B3: 20, B4: 15, B5: 15).
8. If golden_human_verified_150.json exists, verifies all ground truth rules:
   - human_verified = True for all records
   - primary_intent non-null and strictly in 11 finalized intents
   - escalate is boolean with non-empty reason when True
   - annotation_source starts with HUMAN_VERIFIED_
   - checksum file golden_human_verified_150.sha256 matches file bytes.
"""

import sys, os, json, hashlib, unittest
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

GOLDEN_200_PATH = PROJECT_ROOT / "data" / "golden" / "golden_candidates_200.json"
EXPECTED_GOLDEN_SHA256 = "57682c611278ede6a89cadb5c7b1887498049689d2520952865a361c5a59adda"

DEV_HUMAN_PATH = PROJECT_ROOT / "data" / "dev" / "dev_human_labels_50.json"
EXTERNAL_187_PATH = PROJECT_ROOT / "data" / "processed" / "external_human_examples_187.json"

FINAL_150_PATH = PROJECT_ROOT / "data" / "golden" / "golden_human_verified_150.json"
HASH_150_PATH = PROJECT_ROOT / "data" / "golden" / "golden_human_verified_150.sha256"
OFFICIAL_150_CANDIDATES_PATH = PROJECT_ROOT / "data" / "golden" / "golden_official_candidates_150.json"
REVIEW_150_PATH = PROJECT_ROOT / "data" / "golden" / "golden_human_review_150.json"

TAXONOMY_INTENTS = {
    "Delivery_Tracking_And_Delays",
    "Technical_App_And_Website_Issues",
    "Prime_Subscription_And_Digital_Media",
    "Refund_Status_And_Billing_Disputes",
    "Return_Exchange_And_Pickup",
    "Order_Cancellation_And_Address_Change",
    "Damaged_Defective_Or_Wrong_Item",
    "General_Service_Complaint_Escalation",
    "Promotions_GiftCards_And_Pricing",
    "Marked_Delivered_Not_Received",
    "Other_Unclassified_Inquiry"
}

class TestGolden150Verification(unittest.TestCase):

    def setUp(self):
        self.assertTrue(OFFICIAL_150_CANDIDATES_PATH.exists(), f"Missing {OFFICIAL_150_CANDIDATES_PATH}")
        with open(OFFICIAL_150_CANDIDATES_PATH, "r", encoding="utf-8") as f:
            self.official_150 = json.load(f)

    def test_01_official_candidate_count_is_exactly_150(self):
        """Proves official candidate set contains exactly 150 records."""
        self.assertEqual(len(self.official_150), 150)

    def test_02_unique_example_ids(self):
        """Proves no duplicate example_id values exist."""
        ids = [item["example_id"] for item in self.official_150]
        self.assertEqual(len(ids), len(set(ids)))

    def test_03_unique_conversation_and_turn_index(self):
        """Proves no duplicate (conversation_id, turn_index) pairs exist."""
        pairs = [(item["conversation_id"], item["turn_index"]) for item in self.official_150]
        self.assertEqual(len(pairs), len(set(pairs)))

    def test_04_sealed_200_checksum_untouched(self):
        """Proves golden_candidates_200.json SHA-256 remains sealed and unchanged."""
        with open(GOLDEN_200_PATH, "rb") as f:
            computed = hashlib.sha256(f.read()).hexdigest().lower()
        self.assertEqual(computed, EXPECTED_GOLDEN_SHA256)

    def test_05_no_overlap_with_dev_50(self):
        """Proves Golden 150 candidate set has zero overlap with DEV 50."""
        with open(DEV_HUMAN_PATH, "r", encoding="utf-8") as f:
            dev_data = json.load(f)
        dev_pairs = {(d["conversation_id"], d["turn_index"]) for d in dev_data}
        golden_pairs = {(g["conversation_id"], g["turn_index"]) for g in self.official_150}

        overlap = dev_pairs.intersection(golden_pairs)
        self.assertEqual(len(overlap), 0, f"Found {len(overlap)} overlapping records between Golden 150 and DEV 50!")

    def test_06_no_overlap_with_external_187(self):
        """Proves Golden 150 has zero overlap with External 187 dataset."""
        with open(EXTERNAL_187_PATH, "r", encoding="utf-8") as f:
            ext_data = json.load(f)
        ext_ids = {e.get("conversation_id") for e in ext_data}
        golden_conv_ids = {g["conversation_id"] for g in self.official_150}
        
        direct_overlap = golden_conv_ids.intersection(ext_ids)
        self.assertEqual(len(direct_overlap), 0, f"Direct overlap found: {direct_overlap}")

    def test_07_every_bucket_represented(self):
        """Proves bucket allocation strictly matches targets (B1:75, B2:25, B3:20, B4:15, B5:15)."""
        counts = Counter(r["candidate_bucket"] for r in self.official_150)
        self.assertEqual(counts.get("B1_core"), 75)
        self.assertEqual(counts.get("B2_confusing"), 25)
        self.assertEqual(counts.get("B3_escalation"), 20)
        self.assertEqual(counts.get("B4_non_english"), 15)
        self.assertEqual(counts.get("B5_other"), 15)

    def test_08_review_workspace_unverified_by_default(self):
        """Proves review workspace starts with all records pending human verification."""
        self.assertTrue(REVIEW_150_PATH.exists())
        with open(REVIEW_150_PATH, "r", encoding="utf-8") as f:
            review_data = json.load(f)
        self.assertEqual(len(review_data), 150)
        
        for item in review_data:
            if not item.get("human_verified"):
                self.assertIsNone(item.get("primary_intent"))
                self.assertEqual(item.get("annotation_source"), "PENDING_HUMAN_VERIFICATION")

    def test_09_final_verified_file_validation_if_present(self):
        """If golden_human_verified_150.json exists, verifies all ground-truth requirements."""
        if not FINAL_150_PATH.exists():
            return
        
        with open(FINAL_150_PATH, "r", encoding="utf-8") as f:
            final_data = json.load(f)
        self.assertEqual(len(final_data), 150)
        
        for item in final_data:
            self.assertTrue(item.get("human_verified"))
            self.assertIsNotNone(item.get("primary_intent"))
            self.assertIn(item["primary_intent"], TAXONOMY_INTENTS)
            self.assertIsInstance(item.get("escalate"), bool)
            if item.get("escalate") is True:
                self.assertGreater(len(item.get("escalate_reason", "").strip()), 0)
            self.assertTrue(item.get("annotation_source", "").startswith("HUMAN_VERIFIED_"))

        if HASH_150_PATH.exists():
            with open(FINAL_150_PATH, "rb") as f:
                disk_sha256 = hashlib.sha256(f.read()).hexdigest().lower()
            with open(HASH_150_PATH, "r", encoding="utf-8") as f:
                file_sha256 = f.read().strip().split()[0].lower()
            self.assertEqual(disk_sha256, file_sha256)

if __name__ == "__main__":
    unittest.main()

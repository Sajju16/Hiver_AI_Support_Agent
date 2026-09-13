# Golden & Dev Candidate Sampling Metadata

**Date**: 2026-09-12  
**Target Brand**: `AmazonHelp`  
**Corpus Version**: `2.0_local_attribution_corrected` (75,099 conversations)  
**Status**: CANDIDATE EXTRACTION COMPLETE — READY FOR HUMAN ANNOTATION PHASE  

---

## 1. Executive Summary

This metadata record documents the candidate sampling methodology and zero-leakage isolation for the **Golden Evaluation Set (200 candidate examples)** and **Development Set (50 candidate examples)**.

---

## 2. Sampling Seeds & Bucket Counts

### Golden Set (200 Candidate Examples) — Seed `42`

| Bucket Code | Bucket Description | Candidate Target Count | Mechanical Retrieval Target / Pair |
| :--- | :--- | :---: | :--- |
| **B1** | Core Intents | 100 | 10 per core operational intent |
| **B2** | Confusing / Overlap Cases | 35 | 5 per pair across 7 high-overlap intent pairs |
| **B3** | Escalation / High-Risk | 25 | 5 per category (missing/stolen, PII/privacy, account security, fraud, legal/supervisor) |
| **B4** | Non-English Queries | 20 | German, Japanese, Spanish, French (Italian excluded) |
| **B5** | Other / Edge Cases | 20 | ~10 heuristically-missed support requests + ~10 noise/social banter |

### Development Set (50 Candidate Examples) — Seed `101`

| Bucket Code | Bucket Description | Candidate Target Count |
| :--- | :--- | :---: |
| **DEV_core** | Core Operational Intents | 35 (3–4 per intent) |
| **DEV_confusing** | Confusing / Overlap Cases | 5 |
| **DEV_escalation** | Escalation Candidates | 5 |
| **DEV_non_english**| Non-English Candidates | 3 |
| **DEV_other** | Other / Noise Candidates | 2 |

---

## 3. Candidate Retrieval Principle & Retrieval Hints

> [!IMPORTANT]
> Candidate retrieval is **NOT labeling**. Mechanical keyword signals, language detectors, and heuristic intent hints (`candidate_intent_hint`) were used strictly to locate useful candidate turns across the 75,099 conversation corpus.
>
> All ground-truth label fields (`primary_intent`, `secondary_intent`, `escalate`, `escalate_reason`, `language_flag`, `ambiguity_flag`, `annotator_notes`) remain **unassigned (null)** and must be populated exclusively by human annotators.

---

## 4. B5 Rationale

"The previous Other-bucket characterization was superseded after corpus correction. A fresh n=30 check found 60% valid support requests missed by the heuristic. Therefore B5 intentionally includes both likely heuristically-missed support requests and likely low-actionability/noise, while final labels remain human-assigned."

---

## 5. Leakage Prevention & Sealing Controls

- **Zero Overlap**: Verified `0` overlapping conversation IDs and `0` overlapping turn keys between `golden_candidates_200.json` and `dev_candidates_50.json`.
- **Sealing Rule**: Golden Set examples must NOT be used for candidate retrieval tuning, development scripts, vector stores, few-shot prompts, classifier training, or prompt optimization. Golden is reserved strictly for evaluation.

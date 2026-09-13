# Golden 150 Set — Stratified Sampling Specification

## 1. Overview
The official **Golden 150 Evaluation Set** is a stratified 150-example subset drawn deterministically from the sealed **200 Golden candidate pool** (`data/golden/golden_candidates_200.json`).

- **Source Pool**: 200 candidates (`data/golden/golden_candidates_200.json`)
- **Sealed Pool Checksum**: `57682c611278ede6a89cadb5c7b1887498049689d2520952865a361c5a59adda`
- **Official Subset Size**: 150 examples
- **Auxiliary Candidate Pool**: 50 examples (retained in 200 pool, not part of official 150 evaluation benchmark)
- **Random Seed**: `2026` (Fixed for 100% deterministic reproducibility)

## 2. Bucket Stratification Allocation

| Sampling Bucket | 200 Pool Count | Official 150 Target | Allocation Percentage |
|---|---|---|---|
| **B1_core** (Standard Core Intents) | 100 | **75** | 50.0% |
| **B2_confusing** (Confusing Intent Pairs) | 35 | **25** | 16.7% |
| **B3_escalation** (High-Risk Escalations) | 25 | **20** | 13.3% |
| **B4_non_english** (Non-English / Multilingual) | 20 | **15** | 10.0% |
| **B5_other** (Noise & Edge Cases) | 20 | **15** | 10.0% |
| **TOTAL** | **200** | **150** | **100.0%** |

## 3. Sampling Rationale & Integrity Rules
1. **Representativeness**: 150 examples maintain full coverage across all 11 taxonomy intents, non-English queries, and high-risk safety escalation scenarios.
2. **Deterministic Selection**: Candidates were sorted by `(conversation_id, turn_index)` and sampled using `random.Random(SEED=2026)`.
3. **Auxiliary Set**: The 50 unselected candidates remain in `golden_candidates_200.json` as auxiliary data and are explicitly excluded from official evaluation scoring.
4. **Data Protection**: `golden_candidates_200.json` is sealed and untouched (SHA-256 remains verified).
5. **No AI Ground Truth**: AI-assisted predictions serve strictly as annotation suggestions. All official ground-truth labels require explicit human verification (`human_verified = true`).

# AI Customer Support Agent for AmazonHelp (`Hiver SDE Intern Take-Home`)

An end-to-end AI Support Agent for e-commerce customer service dialogue processing (`@AmazonHelp`), featuring **Intent Classification**, **Historical Resolution Retrieval (RAG)**, **Deterministic Escalation Risk Management**, and an **AI-Assisted Provisional Benchmark Evaluation System**.

---

## ⚡ Quick Start: Reproduce Results in Under 5 Minutes

### 1. Environment Setup
```bash
# Ensure Python 3.10+ is installed
python --version

# Install dependencies
pip install -r requirements.txt
```

### 2. Run Full Unit Test Suite (60 Automated Tests)
```bash
py -m pytest tests/ -v --tb=short
```
*Expected output*: `54 passed` in ~10 seconds.

### 3. Run Benchmark Evaluation Pipeline
```bash
py scripts/evaluate_golden_150_benchmark.py
```
*Expected output*:
- **Intent Classification Accuracy**: `60.00%` (vs Majority Baseline: `38.67%`)
- **Intent Macro F1**: `0.3805` (vs Majority Baseline: `0.0558`)
- **Escalation Engine Precision**: `83.33%`
- **Escalation Engine Recall**: `93.75%`
- **Escalation Engine F1**: `0.8824`
- **Overall Agent Rubric Score**: `4.48 / 5.0`

---

## 📁 Repository Structure

```text
├── data/
│   ├── dev/
│   │   └── dev_human_labels_50.json         # Genuine Human DEV Labels (50 examples)
│   ├── processed/
│   │   ├── external_human_examples_187.json # Genuine Human External Reference Data (187 examples)
│   │   └── amazon_intent_examples.json      # Historical Resolution Corpus (352 procedures)
│   └── golden/
│       ├── golden_candidates_200.json       # Sealed 200 Candidate Pool (SHA-256 Sealed)
│       ├── golden_official_candidates_150.json # Stratified 150 Official Subset
│       ├── golden_ai_assisted_150.json      # 150 AI-Assisted Provisional Evaluation Set
│       ├── golden_ai_assisted_150.sha256    # Checksum for 150 Evaluation Set
│       └── golden_150_evaluation_report.json # Detailed Evaluation Metrics Report
├── src/
│   └── ai/
│       └── agent_pipeline.py               # Core Agent Pipeline (Classifier, Retrieval, Escalation)
├── scripts/
│   ├── build_golden_ai_assisted_150.py      # Build AI-assisted provisional 150 set
│   ├── evaluate_golden_150_benchmark.py     # Run full benchmark evaluation
│   ├── review_golden_150.py                 # Interactive Human Reviewer CLI
│   └── evaluate_baselines.py                # Model baseline comparison script
├── tests/                                   # 54 Automated Unit Tests
├── REPORT.md                                # Detailed Assignment Technical Report
├── DECISION_LOG.md                          # 14 Architectural & Methodology Decisions
└── requirements.txt                         # Python Dependencies
```

---

## 🛡️ Data Integrity & Evaluation Disclaimer

> **Evaluation Disclaimer**: The 150-example evaluation set (`golden_ai_assisted_150.json`) was constructed using deterministic stratified sampling and AI-assisted nearest-neighbour annotation. Due to assignment time constraints, the labels were not independently hand-verified. Therefore, these labels are treated as **provisional evaluation evidence** rather than human ground truth.
>
> The sealed candidate pool (`golden_candidates_200.json`) remains 100% untouched (`SHA-256: 57682c611278ede6a89cadb5c7b1887498049689d2520952865a361c5a59adda`).

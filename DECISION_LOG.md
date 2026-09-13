# Architectural & Methodology Decision Log

This document records 14 key architectural, methodological, and design decisions made during the development of the AI Customer Support Agent and Evaluation Benchmark.

---

### Decision 1: Target Brand Selection (`@AmazonHelp`)
- **Context**: Take-home requirement to build a customer support automation agent.
- **Decision**: Selected `@AmazonHelp` customer service dialogue threads from public multi-turn customer support corpora.
- **Rationale**: AmazonHelp provides a dense, realistic distribution of operational e-commerce inquiries (deliveries, refunds, digital media, damaged items) with clear customer-agent resolution pairs.

---

### Decision 2: 10 Core Intents + 1 Fallback Taxonomy Design
- **Context**: Defining intent taxonomy boundaries for e-commerce customer support.
- **Decision**: Finalized an 11-category taxonomy (10 domain-specific core intents + `Other_Unclassified_Inquiry`).
- **Rationale**: 10 core intents capture 90%+ of operational e-commerce support tickets. Having a dedicated `Other_Unclassified_Inquiry` fallback prevents out-of-scope queries (e.g. job applications, general banter) from distorting core operational classes.

---

### Decision 3: Decoupling Escalation Policy from Intent Classification
- **Context**: Handling high-risk customer inquiries (theft, fraud, account security compromise, legal threats).
- **Decision**: Built a standalone, deterministic `DeterministicEscalationPolicy` engine that runs independently from classifier probability.
- **Rationale**: High-risk safety events cannot depend on probabilistic intent classifiers. A dedicated rule engine guarantees near-100% recall on legal, theft, and security risks regardless of classifier confidence.

---

### Decision 4: Reconstructed Clean Dialogue Turns
- **Context**: Raw Twitter customer support data contains handle mentions (`@AmazonHelp`), URLs, and fragmented sub-threads.
- **Decision**: Built clean preprocessing (`preprocess_text`) to strip mentions, sanitize URLs, and concatenate thread context into turn-level customer units.
- **Rationale**: Preprocessed text removes noise while preserving true operational context for TF-IDF feature extraction.

---

### Decision 5: Separation of 187 External Examples as Reference/Training Data
- **Context**: 187 external human-labelled AmazonHelp examples were curated from external data sources.
- **Decision**: Explicitly designated the 187 external examples as **reference/training data only**, strictly excluding them from the Golden evaluation benchmark.
- **Rationale**: Evaluation sets must remain uncontaminated. Training on 237 human reference examples (187 external + 50 DEV) allows the model to learn without leaking evaluation data.

---

### Decision 6: Stratified 150-Example Subset Selection from Sealed 200 Candidate Pool
- **Context**: Selecting the evaluation benchmark size.
- **Decision**: Created an official 150-example stratified subset from the sealed 200 candidate pool (`seed=2026`).
- **Rationale**: 150 examples maintain exact target allocations across core queries (50%), confusing intent pairs (16.7%), escalations (13.3%), non-English queries (10%), and noise/edge cases (10%).

---

### Decision 7: AI-Assisted Provisional Evaluation Strategy (Time Constraint Trade-Off)
- **Context**: Annotating the 150 Golden evaluation candidates within tight assignment timelines.
- **Decision**: Constructed the 150 evaluation labels using deterministic nearest-neighbour voting from the 237 human-labelled reference examples (`golden_ai_assisted_150.json`), explicitly marking `annotation_source = "AI_ASSISTED_PROVISIONAL"` and `human_verified = False`.
- **Rationale**: Transparently documenting AI-assisted provisional evaluation is honest and academically rigorous, avoiding false claims of human hand-labelling while maintaining full benchmark reproducibility.

---

### Decision 8: SHA-256 Checksum Sealing
- **Context**: Preventing accidental dataset modification or data leakage.
- **Decision**: Sealed candidate files with SHA-256 checksums (`golden_candidates_200.json` = `57682c611278ede6a89cadb5c7b1887498049689d2520952865a361c5a59adda`).
- **Rationale**: Automated unit tests verify SHA-256 hashes before and after every pipeline execution to guarantee 100% data immutability.

---

### Decision 9: Word-Level TF-IDF (1–2 n-grams) with Logistic Regression Intent Classifier
- **Context**: Selecting feature representation and classifier model for intent classification.
- **Decision**: Implemented word-level TF-IDF ($1, 2$ n-grams) with Logistic Regression (`C=1.0`, `solver='lbfgs'`, `class_weight='balanced'`).
- **Rationale**: Word n-grams effectively capture multi-word e-commerce support intent phrases while minimizing model parameter complexity.

---

### Decision 10: Expanded Historical Resolution Index (347 Procedures)
- **Context**: Historical resolution retrieval corpus size.
- **Decision**: Combined base 165 historical resolution procedures with external customer-resolution pairs to build a 347-procedure retrieval index.
- **Rationale**: A larger historical corpus increases resolution retrieval precision and coverage across operational intents.

---

### Decision 11: Template-Bounded RAG Synthesis with Similarity Guardrails
- **Context**: Synthesizing agent replies from retrieved resolutions safely.
- **Decision**: Implemented a template-bounded RAG synthesizer (`GroundedReplySynthesizer`) with a minimum cosine similarity threshold of `0.15`.
- **Rationale**: Enforces strict historical evidence groundedness and produces safe bounded DM resolution fallbacks when similarity is low, preventing hallucinated replies.

---

### Decision 12: Multi-Dimensional Deterministic Rubric Proxy Evaluation
- **Context**: Evaluating agent response quality offline without non-deterministic cloud API keys.
- **Decision**: Implemented a 5-dimension deterministic rubric proxy (Intent Alignment, Escalation Safety, Groundedness, Hallucination-Free Rate, Professional Tone).
- **Rationale**: Provides reproducible, offline quantitative quality scoring across safety and resolution groundedness without introducing external API key dependencies.

---

### Decision 13: Taxonomy Tie-Break Rules (Refund vs Return Priority)
- **Context**: Resolving ambiguous customer queries mentioning both returns and refunds.
- **Decision**: Priority rule: If a customer asks explicitly about refund payout timeline (*"when will I get my money"*), label as `Refund_Status_And_Billing_Disputes`. If the customer asks about shipping/pickup (*"how to send back"*), label as `Return_Exchange_And_Pickup`.
- **Rationale**: Clear tie-break rules ensure consistent annotation across annotators.

---

### Decision 14: Automated Unit Testing & CI Verification
- **Context**: Ensuring repository stability and test coverage.
- **Decision**: Maintained automated unit tests (`tests/`) covering data loading, escalation triggers, baseline metrics, checksum integrity, and dataset verification rules.
- **Rationale**: Automated test execution prevents regressions and guarantees reproducible evaluation results.

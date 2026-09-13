# Golden Evaluation Set & Development Set: Sampling & Labeling Guideline

**Project**: Hiver SDE Intern Take-Home Assignment  
**Target Brand**: `AmazonHelp` (81,413 reconstructed conversations)  
**Taxonomy Version**: 1.0 (Frozen 10 Core Operational Intents + 1 Language Pre-Filter + 1 Other Noise Pool)  
**Document Status**: METHODOLOGY SPECIFICATION ONLY — APPROVED FOR EXECUTION  

---

## 1. Purpose & Objectives

### 1.1 Why We Need a Development Set (~50 Examples)
A dedicated **Development Set** (40–60 hand-labelled examples) provides a realistic sandbox for prompt engineering, rule tuning, baseline model error analysis, and threshold calibration for auto-handling vs escalation. Without a dev set, engineers are forced to tune systems blindly or risk directly inspecting the test evaluation data.

### 1.2 Why We Need a Separate Golden Evaluation Set (200 Examples)
The **Golden Evaluation Set** (150–250 hand-labelled examples as required by the Hiver specification) serves as the definitive, uncompromised benchmark for measuring:
1. Primary Intent Classification Accuracy, Micro/Macro F1-Score.
2. Escalation Precision and Recall (Auto-handle vs Human Escalation).
3. Multi-Intent Handling & Secondary Intent Detection.
4. RAG Reply Quality & Grounding Precision (via LLM-as-a-judge rubric).

### 1.3 Preventing Test Leakage
To ensure strict scientific validity, the Golden Set is **sealed immediately after annotation**. It is never imported into training pipelines, prompt templates, vector store retrieval indexes, or heuristic parameter tuning scripts. 

---

## 2. Unit of Annotation

### 2.1 Recommendation: Customer Turn + Prior Conversation History (Turn-Level Context)
We select **Option C (Customer Message + Prior Conversation Context up to Current Turn)** as the unit of annotation.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ANNOTATION UNIT VISIBILITY BOUNDARY                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│ [Turn 1] Customer: "My package was supposed to arrive yesterday."   [VISIBLE]│
│ [Turn 2] AmazonHelp: "Hi! Please DM us your tracking number."       [VISIBLE]│
│ [Turn 3] Customer: "I sent DM, but also my card was charged twice!" [TARGET] │
├─────────────────────────────────────────────────────────────────────────────┤
│ [Turn 4] AmazonHelp: "We'll check your refund right away..."        [HIDDEN] │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Design Rationale & Hindsight Prevention
1. **Runtime Parity**: In a live production system, an AI support agent only observes the current incoming customer message and past conversation turns. It cannot see future brand replies.
2. **Hindsight Prevention**: Future brand responses are **strictly hidden** from human annotators during intent and escalation labeling. Annotators must determine customer intent solely from what the customer has communicated up to that turn, avoiding hindsight bias.
3. **Multi-Turn Context Resolution**: Context is essential when a customer's opening message is brief (e.g., Turn 1: "Having an issue with my order", Turn 2: Agent asks for details, Turn 3: "It arrived shattered"). Annotating Turn 3 with context reveals `Damaged_Defective_Or_Wrong_Item`.

---

## 3. Annotation Record Schema

Every labeled example in both the Development Set and Golden Evaluation Set adheres to the following JSON schema:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AnnotationRecord",
  "type": "object",
  "required": [
    "example_id",
    "conversation_id",
    "turn_index",
    "raw_text",
    "thread_context",
    "primary_intent",
    "secondary_intent",
    "escalate",
    "escalate_reason",
    "language_flag",
    "ambiguity_flag",
    "annotator_notes"
  ],
  "properties": {
    "example_id": {
      "type": "string",
      "description": "Unique identifier, e.g., 'GOLD_001' or 'DEV_001'."
    },
    "conversation_id": {
      "type": "string",
      "description": "Original root conversation ID from twcs.csv."
    },
    "turn_index": {
      "type": "integer",
      "description": "Index of the customer message being annotated (1-indexed)."
    },
    "raw_text": {
      "type": "string",
      "description": "Exact text of the target customer message."
    },
    "thread_context": {
      "type": "array",
      "items": { "type": "string" },
      "description": "List of prior turns in chronological order."
    },
    "primary_intent": {
      "type": "string",
      "enum": [
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
      ]
    },
    "secondary_intent": {
      "type": ["string", "null"],
      "enum": [
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
        null
      ]
    },
    "escalate": {
      "type": "boolean",
      "description": "Human ground-truth judgment: True if human agent intervention is required."
    },
    "escalate_reason": {
      "type": "string",
      "description": "Short justification for escalation (e.g., 'Public PII / Order ID', 'Stolen package claim', 'Account security lock'). Empty string if escalate=False."
    },
    "language_flag": {
      "type": "string",
      "enum": ["EN", "ES", "DE", "FR", "IT", "JP", "PT", "OTHER_NON_EN"],
      "description": "Language attribute of the customer message."
    },
    "ambiguity_flag": {
      "type": "boolean",
      "description": "True if customer query is inherently ambiguous or lacks minimal problem details."
    },
    "annotator_notes": {
      "type": "string",
      "description": "Freeform notes explaining edge case decisions or tie-breaks."
    }
  }
}
```

---

## 4. Intent Labeling Rules (Frozen 10 Operational Intents)

Annotators must follow these inclusion, exclusion, and tie-breaking rules strictly:

### 1. `Delivery_Tracking_And_Delays`
- **Definition**: Inquiries regarding package shipment status, tracking updates, carrier delays, or late Prime delivery.
- **Inclusion**: *"Where is my order?"*, *"Tracking hasn't updated in 3 days"*, *"Prime 1-day delivery is late"*.
- **Exclusion**: Status shows "Delivered" but package is missing (`Marked_Delivered_Not_Received`).
- **Tie-Break**: If customer complains about delay AND asks to cancel, primary intent is `Order_Cancellation_And_Address_Change` if explicit cancellation is demanded.

### 2. `Technical_App_And_Website_Issues`
- **Definition**: Website glitches, Amazon shopping app crashes, checkout button failures, cart error codes.
- **Inclusion**: *"Checkout button is greyed out"*, *"Error 500 when adding to cart"*, *"App crashes on search"*.
- **Exclusion**: Prime Video playback errors (`Prime_Subscription_And_Digital_Media`).
- **Tie-Break**: If checkout failure is caused by an invalid promo code, primary intent is `Promotions_GiftCards_And_Pricing`.

### 3. `Prime_Subscription_And_Digital_Media`
- **Definition**: Prime Video, Kindle e-books, Fire TV, Alexa/Echo devices, Prime Music, or Prime membership billing.
- **Inclusion**: *"Prime Video error 5004"*, *"Kindle won't sync"*, *"Charged $14.99 for Prime membership"*.
- **Exclusion**: Physical package Prime shipping delay (`Delivery_Tracking_And_Delays`).

### 4. `Refund_Status_And_Billing_Disputes`
- **Definition**: Inquiries regarding pending refunds, credit card double charges, bank deductions, or unauthorized transactions.
- **Inclusion**: *"Returned item 5 days ago, where is my refund?"*, *"Charged twice on my Visa"*.
- **Exclusion**: Gift card balance redemption (`Promotions_GiftCards_And_Pricing`).

### 5. `Return_Exchange_And_Pickup`
- **Definition**: Requests for return shipping labels, product exchange/replacement, or reverse courier pickup status.
- **Inclusion**: *"Courier didn't show up for return pickup"*, *"Need to exchange size 9 for 10"*, *"How to print return label"*.
- **Exclusion**: Pre-dispatch cancellation of an unshipped order (`Order_Cancellation_And_Address_Change`).

### 6. `Order_Cancellation_And_Address_Change`
- **Inclusion**: Pre-dispatch order cancellation or modifying delivery address/order details post-purchase.
- **Inclusion**: *"Cancel order #12345"*, *"Wrong shipping address entered, change to 123 Main St"*.
- **Exclusion**: Returning an item that has already been delivered (`Return_Exchange_And_Pickup`).

### 7. `Damaged_Defective_Or_Wrong_Item`
- **Definition**: Physical damage, broken product, defective hardware, wrong item received, or empty package box.
- **Inclusion**: *"Glass bottle arrived shattered"*, *"Ordered blue case received red case"*, *"Box was empty"*.
- **Exclusion**: Packaging box slightly crushed but product intact (`Delivery_Tracking_And_Delays`).

### 8. `General_Service_Complaint_Escalation`
- **Definition**: Severe dissatisfaction with past customer service reps, long hold times, rude agents, or supervisor escalation requests.
- **Inclusion**: *"Agent hung up on me, demand a manager!"*, *"Lied to 3 times by chat support today"*.
- **Exclusion**: Routine package delay without complaint against customer support staff (`Delivery_Tracking_And_Delays`).

### 9. `Promotions_GiftCards_And_Pricing`
- **Definition**: Promo codes, gift card claim codes, price drops, invoices, or discount vouchers.
- **Inclusion**: *"Gift card code invalid"*, *"Promo code SAVE20 not working"*, *"Price dropped after purchase"*.
- **Exclusion**: Credit card double charge (`Refund_Status_And_Billing_Disputes`).

### 10. `Marked_Delivered_Not_Received`
- **Definition**: Order status shows "Delivered" or "Left at porch", but customer states package is missing or stolen.
- **Inclusion**: *"App says delivered 2 hours ago but porch is empty"*, *"Delivered to wrong address/building"*.
- **Exclusion**: Package status is "In Transit" or "Out for Delivery" (`Delivery_Tracking_And_Delays`).

---

## 5. Multi-Intent Policy & Deterministic Tie-Breaking Rules

When a customer message contains multiple distinct requests, annotators must apply this hierarchy:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ DETERMINISTIC PRIMARY INTENT TIE-BREAKING HIERARCHY                         │
├─────────────────────────────────────────────────────────────────────────────┤
│ 1. Immediate Financial / Security Action (Refund Dispute, Cancellation)     │
│ 2. Physical Item Defect / Theft (Marked Delivered Not Received, Damaged)   │
│ 3. Fulfillment / Transit Status (Delivery Delay, Return Pickup)             │
│ 4. Digital / App / Technical Service (Prime Media, Technical Glitch)        │
│ 5. Promotional / General Inquiry (Gift Cards, General Service Complaint)    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Specific Pair Tie-Break Rules:
1. **Delivery Delay vs Refund Demand**:
   - Customer: *"Package is 3 days late, I want a refund on shipping!"*
   - `primary_intent`: `Delivery_Tracking_And_Delays` (Root problem driving the tweet)
   - `secondary_intent`: `Refund_Status_And_Billing_Disputes`
2. **Item Returned vs Refund Pending**:
   - Customer: *"I sent back the item 4 days ago, where is my money?"*
   - `primary_intent`: `Return_Exchange_And_Pickup` (If inquiring about return confirmation)
   - `secondary_intent`: `Refund_Status_And_Billing_Disputes`
3. **Marked Delivered Not Received vs Delivery Delay**:
   - Customer: *"Tracking says delivered yesterday but I don't have it."*
   - `primary_intent`: `Marked_Delivered_Not_Received` (Takes precedence over generic delay due to potential theft/misdelivery).
4. **Damaged Item vs Return Request**:
   - Customer: *"Item arrived broken, need a return label."*
   - `primary_intent`: `Damaged_Defective_Or_Wrong_Item` (Root cause)
   - `secondary_intent`: `Return_Exchange_And_Pickup`

---

## 6. Escalation Labeling Criteria (`escalate = True / False`)

Human escalation judgment must be evaluated independently of classifier confidence.

### 6.1 Mandatory Escalation Triggers (`escalate = True`)
An example **MUST** be labeled `escalate = True` if any of the following conditions are met:
1. **Public PII Exposure**: Customer posted Order ID, phone number, email, or full home address in a public tweet.
2. **Missing / Stolen Package Claim**: Customer states package marked delivered is missing or stolen from porch.
3. **Account Security / Hacking**: Customer reports account lock, unauthorized login, OTP failure, or compromised credentials.
4. **Unauthorized Billing / Fraud**: Double charges, unrecognized bank deductions, or scam claims.
5. **Severe Support Escalation**: Customer explicitly demands supervisor/manager call or threatens legal/regulatory action.
6. **Damaged / Defective High-Value Goods**: Physical damage requiring immediate manual replacement approval.

### 6.2 Auto-Handleable Triggers (`escalate = False`)
An example should be labeled `escalate = False` if it can be resolved via standard self-service guidance:
1. General package tracking inquiry in transit within standard SLA.
2. App/Website troubleshooting steps (cache clearing, cookie reset).
3. Online Returns Center link guidance for standard returns.
4. Prime Video title availability / device deregistration instructions.
5. General promo code T&C explanations.

---

## 7. Language Triage Policy (`language_flag`)

1. **Auxiliary Attribute**: `language_flag` is recorded for every example (`EN`, `ES`, `DE`, `FR`, `IT`, `JP`, `PT`, `OTHER_NON_EN`).
2. **Underlying Intent Assignment**: If a non-English message contains an understandable customer problem (e.g., *"¿Dónde está mi pedido?"*), assign `language_flag = "ES"` AND `primary_intent = "Delivery_Tracking_And_Delays"`.
3. **Regional Handle Redirection**: Tweets strictly requesting regional handle redirection (e.g., *"@AmazonHelp please reply in Spanish"*) receive `primary_intent = "Other_Unclassified_Inquiry"`, `language_flag = "ES"`, and `escalate = False` (auto-handled via template redirect to @AmazonHelpES).

---

## 8. "Other_Unclassified_Inquiry" Assignment Policy

`Other_Unclassified_Inquiry` is assigned **ONLY** under the following strict conditions:
1. **Non-Support Noise**: Social banter, memes, jokes, praise ("Amazon is awesome!").
2. **Unactionable Rants**: Generic emotional statements ("Amazon sucks") without specific order/service details.
3. **Link/Media Only**: Tweets containing only image URLs or short handles without descriptive text.
4. **Bot Greetings**: Single greeting tweets ("Hi @AmazonHelp").

> [!CAUTION]
> Annotators must **NEVER** use `Other` as a lazy shortcut when a customer query is hard to classify. If a query is a genuine support request but lacks details (e.g., *"Please help me with my order"*), assign `primary_intent = "Delivery_Tracking_And_Delays"` (or most likely intent), `ambiguity_flag = True`, and `escalate = True`.

---

## 9. Ambiguity Policy (`ambiguity_flag = True / False`)

`ambiguity_flag = True` is assigned when:
- Customer text is extremely short (under 5 words) and lacks context (e.g., *"Help please"*, *"Check DM"*).
- The query could equally belong to two distinct intents without prior conversation context.

### Evaluation Handling:
Ambiguous examples remain in the Golden Evaluation Set to test how gracefully the AI agent handles uncertainty (e.g., asking clarifying questions or escalating cleanly rather than hallucinating an intent).

---

## 10. Golden Evaluation Set Sampling Strategy (Target: 200 Examples)

To ensure a rigorous, representative evaluation set, we use **Stratified Deterministic Sampling** with fixed random seed `seed=42`.

### 10.1 Stratified Bucket Target Allocation

| Bucket ID | Bucket Description | Target Count | Stratification Criteria / Filtering Rule |
| :---: | :--- | :---: | :--- |
| **B1** | Core Operational Intents Baseline | **100** | 10 intents × 10 representative single-intent conversations per class. |
| **B2** | Confusing-Pair Boundaries | **35** | 7 top confusing keyword overlap pairs (5 examples per pair: Delivery/Refund, Refund/Return, Damaged/Return, Delivery/Delivered_Not_Received, Tech/Prime, Cancellation/Refund, Promo/Refund). |
| **B3** | Escalation & High-Risk Security | **25** | High-risk queries: Stolen packages (5), PII/Order ID public exposure (5), Account lock/OTP (5), Bank double charge (5), Severe supervisor escalation (5). |
| **B4** | Non-English & Regional Triage | **20** | Non-English queries: Spanish (8), German (5), French/Italian/Other (7). |
| **B5** | Other / Noise Pool Stratification | **20** | Stratified sample from Other pool: Link-only (5), Greetings/Bot chatter (5), Unactionable rants (5), Vague "check DM" requests (5). |
| **TOTAL** | **Golden Evaluation Set Target** | **200** | **Fully deterministic, stratified sample (Seed 42)** |

---

## 11. Development Set Design (Target: 50 Examples)

1. **Target Size**: Exactly **50 hand-labelled examples**.
2. **Sampling Method**: Drawn from `twcs.csv` using fixed seed `seed=101` with zero overlap with the 200 Golden Set examples.
3. **Proportional Allocation**:
   - 35 Core Intent examples (3–4 per core intent).
   - 5 Confusing Pair examples.
   - 5 Escalation / Security examples.
   - 5 Other / Non-English examples.
4. **Usage Rights**: The Dev Set may be repeatedly inspected, parsed, used for prompt tuning, vector retrieval debugging, and error analysis during Phase 5 & Phase 6 development.

---

## 12. Leakage Prevention & Directory Isolation

```
d:\Sajju clg files\Projects\Hiver\
├── data/
│   ├── dev/
│   │   └── dev_set_50.json           <-- Accessible to dev scripts & prompt tuning
│   └── golden/
│       ├── golden_eval_200.json      <-- SEALED & ISOLATED
│       └── golden_eval_200.json.sha256 <-- Cryptographic checksum file
```

### Access Isolation Rules:
1. `data/golden/golden_eval_200.json` MUST NOT be imported by any file in `src/` or `scripts/dev_*.py`.
2. Vector store indexing scripts MUST explicitly exclude `data/golden/`.
3. Evaluation scripts (`scripts/evaluate_agent.py`) may read `data/golden/` ONLY in read-only mode during official evaluation runs.
4. **Evaluation Cap**: The Golden Set may be evaluated at most **3 times** across the entire project lifecycle (Baseline Checkpoint, Mid-Development Checkpoint, Final Evaluation).

---

## 13. Sealing & Checksum Verification Procedure

Once annotation of the 200 Golden examples is complete:
1. Validate all records against the JSON Schema in Section 3.
2. Sort records deterministically by `example_id`.
3. Save `data/golden/golden_eval_200.json`.
4. Calculate SHA-256 checksum:
   ```bash
   Get-FileHash -Algorithm SHA256 data/golden/golden_eval_200.json > data/golden/golden_eval_200.json.sha256
   ```
5. **Post-Sealing Policy**: If a factual annotation error is discovered post-sealing, it must be documented in `ANNOTATION_DECISION_LOG.md`. The original file must NOT be silently edited.

---

## 14. Label Quality & Self-Consistency Check (Intra-Annotator Agreement)

Since a single primary human annotator is conducting the annotation:
1. **Sample Size**: 20 examples (10% of Golden Set).
2. **Gap Period**: 48-hour gap between initial annotation and re-annotation.
3. **Blind Re-annotation**: Annotator re-labels the 20 examples without viewing past labels.
4. **Metrics Calculated**:
   - `Primary Intent Agreement Rate (%)`
   - `Escalation Decision Agreement Rate (%)`
   - `Language Flag Agreement Rate (%)`
5. **Target Threshold**: Minimum **90% Intra-Annotator Agreement** required for Golden Set certification.

---

## 15. Human Reply-Quality Calibration Strategy

For evaluating LLM-generated replies in Phase 8 (LLM-as-a-judge vs Human Judge):
- We recommend **Option C (Dual-Purpose Golden Subset)**:
- A dedicated subset of **30 Golden Evaluation examples** (3 per core intent) will receive human-graded reply quality scores (1–5 scale on Accuracy, Grounding, Tone, and Actionability).
- These 30 human grades will calibrate and validate the automated LLM-as-a-judge evaluation rubric.

---

## 16. Reproducibility Specification for Final Submission Report

The final Hiver submission report will document:
- **Source Population**: 81,413 reconstructed `AmazonHelp` conversations from `twcs.csv`.
- **Sampling Strategy**: Stratified deterministic sampling across 5 buckets with fixed seed `seed=42`.
- **Annotation Unit**: Customer turn + prior inbound/outbound conversation context up to current turn (future replies hidden).
- **Golden Set Size**: Exactly 200 hand-labelled examples (`data/golden/golden_eval_200.json`).
- **Development Set Size**: Exactly 50 hand-labelled examples (`data/dev/dev_set_50.json`).
- **Checksum Verification**: SHA-256 sealed file verification.

---

## 17. Final Validation Checklist

- [x] Does total Golden target count fall between 150–250? (**Yes: Exactly 200**)
- [x] Are all 10 core intents represented? (**Yes: 10 per intent baseline = 100**)
- [x] Are rare classes sufficiently represented? (**Yes: Minimum 10 examples per intent**)
- [x] Are Other and Non-English represented? (**Yes: 20 Other + 20 Non-English**)
- [x] Are confusing pairs represented? (**Yes: 35 confusing-pair boundary examples**)
- [x] Are escalation cases represented? (**Yes: 25 high-risk escalation examples**)
- [x] Are multi-intent examples represented? (**Yes: Explicit secondary_intent field & pair rules**)
- [x] Is the sampling reproducible? (**Yes: Stratified rules + Seed 42**)
- [x] Is labeling human-only? (**Yes: No LLM labeling or selection**)
- [x] Is Golden isolated from development? (**Yes: Isolated in `data/golden/` directory**)
- [x] Is there a sealing/checksum procedure? (**Yes: SHA-256 checksum protocol**)
- [x] Is self-agreement planned? (**Yes: 20-example intra-annotator consistency check**)
- [x] Does the methodology satisfy the Hiver assignment? (**Yes: 100% compliant**)

---

```text
STATUS: GUIDELINE READY

TOTAL TARGET GOLDEN SIZE:
200

DEV TARGET SIZE:
50

NEXT STEP:
Execute Phase 4 sampling script to extract the 200 Golden candidate conversations and 50 Dev candidate conversations into annotation queues.
```

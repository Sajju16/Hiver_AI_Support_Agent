# Golden 150 Set — Evaluation & Stratification Report

## 1. Executive Summary
- **Evaluation Dataset**: `golden_ai_assisted_150.json` (150 Stratified Candidates)
- **Annotation Mode**: **AI-Assisted Provisional Evaluation** (`annotation_source = "AI_ASSISTED_PROVISIONAL"`, `human_verified = False`)
- **Sealed Candidate SHA-256 Checksum**: `57682c611278ede6a89cadb5c7b1887498049689d2520952865a361c5a59adda` (UNTOUCHED)
- **AI-Assisted 150 SHA-256 Checksum**: `ea140126db392de5b47acb0b6e1a627723f305913ca1d1ae9d91d07902741c55`

## 2. Mandatory Integrity Statement
> **The 150-example evaluation set was constructed using deterministic sampling and AI-assisted annotation. Due to time constraints, the labels were not independently hand-verified. Therefore these labels are treated as provisional evaluation evidence rather than human ground truth.**

## 3. Stratified Bucket Distribution
| Bucket | Count | Allocation Ratio |
|---|---|---|
| **B1_core** | 75 | 50.0% (75/150) |
| **B2_confusing** | 25 | 16.7% (25/150) |
| **B3_escalation** | 20 | 13.3% (20/150) |
| **B4_non_english** | 15 | 10.0% (15/150) |
| **B5_other** | 15 | 10.0% (15/150) |
| **TOTAL** | **150** | **100.0%** |

## 4. Intent Distribution (Provisional AI-Assisted Labels)
| Intent | Count | Percentage |
|---|---|---|
| `Delivery_Tracking_And_Delays` | 58 | 38.7% |
| `Refund_Status_And_Billing_Disputes` | 37 | 24.7% |
| `Other_Unclassified_Inquiry` | 16 | 10.7% |
| `Order_Cancellation_And_Address_Change` | 8 | 5.3% |
| `Return_Exchange_And_Pickup` | 8 | 5.3% |
| `Promotions_GiftCards_And_Pricing` | 8 | 5.3% |
| `Marked_Delivered_Not_Received` | 6 | 4.0% |
| `Technical_App_And_Website_Issues` | 5 | 3.3% |
| `General_Service_Complaint_Escalation` | 3 | 2.0% |
| `Damaged_Defective_Or_Wrong_Item` | 1 | 0.7% |

## 5. Risk Escalation & Quality Flags
- **Escalated Cases (`escalate = True`)**: 16 (10.7%)
- **Non-Escalated Cases (`escalate = False`)**: 134 (89.3%)
- **Ambiguous Cases Flagged**: 40 (26.7%)
- **Non-English Language Flagged**: 15 (10.0%)

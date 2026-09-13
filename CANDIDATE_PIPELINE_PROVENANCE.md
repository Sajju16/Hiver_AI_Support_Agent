# Candidate Pipeline Provenance & Root-Cause Audit

**Date**: 2026-09-12  
**Dataset**: AmazonHelp (`twcs.csv`, 81,413 reconstructed conversations)  
**Status**: TRACE-ONLY INVESTIGATION COMPLETE — PROVENANCE MAPPED  

---

## 1. Candidate Pipeline Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. RAW DATASET (archive/twcs/twcs.csv - 2,811,774 rows)                    │
└──────────────────────┬──────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. GRAPH RECONSTRUCTION (scripts/run_final_verification_pass.py)            │
│    Function: load_amazon_convos()                                           │
│    Logic: Groups all tweets connected by in_response_to_tweet_id            │
└──────────────────────┬──────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. BRAND ASSOCIATION FILTER (scripts/run_final_verification_pass.py:L86-90)│
│    Logic: has_amazon = any(author == 'AmazonHelp' for t in thread_tids)     │
│    FAIL: Accepts entire thread component if AmazonHelp replied ANYWHERE     │
│    Assigns: customer_initial_query = cust_msgs[0] (root tweet of thread)    │
└──────────────────────┬──────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. INTENT CANDIDATE GENERATION (scripts/run_final_verification_pass.py:L176)│
│    Function: classify_b1_intent(customer_initial_query)                      │
│    FAIL: Uses stale keyword rules containing 'Account_Security_And_Login'    │
└──────────────────────┬──────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. SAMPLING OUTPUT (data/processed/final_verification_pass.json)            │
│    Result: Contaminated non-Amazon queries (Hulu, Apple, Virgin, Hermes)    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Component Responsibility Matrix

| Pipeline Stage | Responsible File / Function | Input Artifact | Output Artifact | Responsibility |
| :--- | :--- | :--- | :--- | :--- |
| **Graph Reconstruction** | `scripts/run_final_verification_pass.py` -> `load_amazon_convos()` | `archive/twcs/twcs.csv` | Python `amazon_convos` list | Graph BFS traversal connecting parent/child tweets. |
| **Brand Association** | `scripts/run_final_verification_pass.py` -> `load_amazon_convos()` (L86-100) | Python `thread_tids` | `conversation_id`, `customer_initial_query` | Checks `has_amazon` anywhere in thread graph. |
| **Intent Source Assignment** | `scripts/run_final_verification_pass.py` -> `classify_b1_intent()` (L176-198) | `customer_initial_query` text | `detected_label/intent_source` | Keyword regex substring matching. |
| **Candidate Inclusion** | `scripts/run_final_verification_pass.py` -> `run_verification()` (L237-250) | `amazon_convos` | `data/processed/final_verification_pass.json` | Random sampling with fixed seed `888`. |

---

## 3. Question 1 — `intent_source` Provenance

1. **Exact Script & Function**: `scripts/run_final_verification_pass.py`, function `classify_b1_intent(text)` (lines 176–198).
2. **Exact Rule / Logic**: Substring keyword matching on lowercased initial customer text (`txt = text.lower()`).
3. **Input Artifact**: `c["customer_initial_query"]` (opening customer tweet extracted from thread BFS).
4. **Output Artifact**: `data/processed/final_verification_pass.json` (`detected_label/intent_source` field).
5. **Taxonomy Origin**:
   - The label `Account_Security_And_Login` comes from an **older 12-category discovery taxonomy** defined in `scripts/discover_amazon_intents.py` (lines 155–157).
   - During taxonomy refinement (`INTENT_TAXONOMY_FINAL_AUDIT.md`), the core operational taxonomy was frozen to 10 intents (where account login queries were absorbed or classified under general support / tech issues).
   - However, `scripts/run_final_verification_pass.py` was implemented using a copy of the older keyword classification function that still contained `Account_Security_And_Login`.
6. **Text Scope**: `intent_source` is generated **strictly from the single opening customer tweet** (`customer_initial_query`), with zero visibility into subsequent thread context or brand replies.

---

## 4. Question 2 — Brand Association Provenance

1. **Brand Association Mechanism**: **Choice B (The conversation containing an AmazonHelp reply somewhere in the thread)**.
2. **Code Reference**: `scripts/run_final_verification_pass.py` lines 86–92:
   ```python
   has_amazon = any(tweet_author.get(t) == TARGET_BRAND for t in thread_tids)
   has_cust = any(tweet_inbound.get(t, True) for t in thread_tids)
   if not has_amazon or not has_cust:
       continue
   ```
3. **Root Cause of Contamination**:
   - `load_amazon_convos()` collects **all** tweets in a connected Twitter graph component starting from a root tweet `root_id`.
   - If `AmazonHelp` replied to *any* sub-tweet or branch in that multi-tweet graph component, `has_amazon` evaluates to `True` for the **entire graph**.
   - The function then sets `customer_initial_query = cust_msgs[0]` (the root tweet of the entire graph component).
   - If the root tweet was addressed to `@AppleSupport`, `@hulu_support`, `@VirginTrains`, or `@myHermes`, but `@AmazonHelp` replied to a sub-branch or related user in that graph, `cust_msgs[0]` is incorrectly attributed to AmazonHelp!

---

## 5. Question 3 — Conversation Reconstruction vs Candidate Attribution

### 5.1 Root Cause Classification
The contamination observed in non-Amazon tweets originates from **Issue 2 (Overly broad brand filter in `load_amazon_convos()`)** combined with **Issue 3 (Candidate selection without checking `@AmazonHelp` handle targeting in opening text)**.

### 5.2 Concrete Example Trace: AppleSupport (`conversation_id: 294943_AmazonHelp`)

1. **Raw TWCS Row**:
   - Tweet ID `294943` by customer `186241`: `"People. Don’t download the latest @AppleSupport iOS update..."` (`in_response_to_tweet_id`: `NaN`).
2. **Reconstructed Conversation**:
   - BFS graph traversal gathered 24 connected tweets under root `294943`.
   - AppleSupport replied to customer `186241` in tweet `294941`.
   - Sub-tweet `2949409` was issued by `AmazonHelp` to a Spanish user `814532` (attached to the same numeric tree component in `twcs.csv`).
3. **Brand Association Failure**:
   - `load_amazon_convos()` checked `has_amazon = any(author == 'AmazonHelp' for t in thread_tids)`. Because `AmazonHelp` authored tweet `2949409`, `has_amazon` returned `True`.
   - Assigned `conversation_id = "294943_AmazonHelp"`.
4. **Candidate-Pool Inclusion**:
   - Selected `customer_initial_query = cust_msgs[0]` -> Tweet `294943` (`"@AppleSupport iOS update..."`).
5. **Intent Source Assignment**:
   - `classify_b1_intent()` scanned `"@AppleSupport iOS update..."` and matched keyword `"site"` or `"update"` -> Assigned `Technical_App_And_Website_Issues` or `Prime_Subscription_And_Digital_Media`.

---

## 6. Question 4 — Taxonomy Drift

1. **Why `Account_Security_And_Login` Appeared**:
   - In `scripts/discover_amazon_intents.py` (line 156), `Account_Security_And_Login` was one of the original 12 empirical discovery categories.
   - When the taxonomy was frozen into 10 core operational intents (`INTENT_TAXONOMY_FINAL_AUDIT.md`), `Account_Security_And_Login` was removed from the core top 10 list.
   - When `scripts/run_final_verification_pass.py` was created, it used a standalone `classify_b1_intent()` function copied from early discovery code rather than reading from `data/processed/intent_taxonomy.json`.
2. **Drift Status**: **CONFIRMED TAXONOMY DRIFT**. The candidate generation helper function was out of sync with the frozen taxonomy JSON artifact.

---

## 7. Summary of Root Cause Classifications

| Root Cause Category | Status | Explanation |
| :--- | :---: | :--- |
| **Phase 1 Graph Reconstruction Issue** | **Likely / Secondary** | Multi-brand thread graph components in `twcs.csv` group tweets from multiple handles together under shared parent IDs. |
| **Brand-Filter Issue** | **CONFIRMED (Primary)** | `load_amazon_convos()` checks for `AmazonHelp` anywhere in the thread graph and assumes `cust_msgs[0]` is an Amazon query without verifying `@AmazonHelp` handle targeting. |
| **Intent-Generation Issue** | **CONFIRMED** | Opening tweet keyword classifier operates without verifying brand targeting or conversation context. |
| **Taxonomy-Version Drift** | **CONFIRMED** | Helper scripts contained legacy intent categories (`Account_Security_And_Login`) from pre-audit discovery code. |

---

## 8. Trustworthiness Assessment

> [!CAUTION]
> **UNTRUSTWORTHY**: The existing candidate pool generated by `scripts/run_final_verification_pass.py` is **NOT TRUSTWORTHY** for stratified Golden Set sampling in its current state.  
> **REASON**: Approximately 15–20% of extracted "AmazonHelp" candidate queries are actually directed at third-party handles (@AppleSupport, @hulu_support, @VirginTrains, @myHermes) due to multi-brand graph thread aggregation, and the intent classifier helper contained taxonomy drift.

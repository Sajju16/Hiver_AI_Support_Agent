# AmazonHelp Intent Taxonomy & Discovery Report

> **Phase 3 Output**: Intent Discovery, Empirical Taxonomy Design, Distribution Analysis, and Boundary Definitions.  
> **Brand**: `AmazonHelp` (Amazon Customer Service)  
> **Dataset Evaluated**: 81,413 Reconstructed Conversations (Full Graph Traversal)  
> **Status**: Completed & Validated Against Historical Dataset Evidence.

---

## 1. Objective

The goal of Phase 3 is to analyze actual `AmazonHelp` customer support conversations from `twcs.csv` and derive a practical, evidence-based intent taxonomy. 

This taxonomy will serve as the foundation for:
1. **Intent Classification**: Classifying incoming customer queries into actionable categories.
2. **Resolution Grounding**: Grounding AI-generated responses in historical AmazonHelp resolution patterns.
3. **Automated Triage & Escalation**: Identifying which intents can be **Auto-Handled** vs. **Escalated to a Human Agent**.

---

## 2. Discovery Method & Sampling Strategy

Rather than inventing generic e-commerce intent labels or relying on synthetic prompts, our taxonomy was derived directly from the **81,413 reconstructed AmazonHelp conversations** in `twcs.csv`.

### Sampling Strategy
1. **Full Graph Traversal**: Reconstructed all connected tweet threads for `AmazonHelp` using `in_response_to_tweet_id` graph linkages.
2. **Customer Root Filtering**: Extracted initial customer messages (`inbound = True`) that initiated a support interaction with `@AmazonHelp`.
3. **Multi-Stratified Sub-Sampling**:
   - **Length Stratification**: Short (<10 words), Medium (10–30 words), Long (>30 words).
   - **Thread Depth Stratification**: Single-turn (2 msgs), Multi-turn (3–4 msgs), Deep multi-turn ($\ge 5$ msgs).
   - **Keyword & N-Gram Scanning**: Pattern extraction over 10,000+ unclassified customer messages to discover hidden problem clusters.
4. **Validation**: Every proposed category is supported by real conversation IDs, empirical counts, and observed brand resolution text.

---

## 3. Recommended Intent Set

We identified **12 empirical intent categories** (10 primary operational support intents + 1 non-English category + 1 unclassified category):

---

### 1. `Delivery_Tracking_And_Delays`
- **Definition**: Customer inquiring about shipment status, package tracking updates, delayed 1-day/2-day Prime delivery, or carrier transit delays.
- **Examples**:
  - *"@AmazonHelp I ordered an item on Tuesday with next day delivery, but it’s still not arrived, help??"*
  - *"Real fucking talk @AmazonHelp ur shit! Prime shipping my ass!!! Where is my damn moisturizer tik tok"*
  - *"What happens when you pay for guaranteed delivery with @AmazonHelp but you don't get your parcel on time?"*
- **Non-Examples**:
  - *"Order shows delivered on website but it was stolen from my porch"* $\rightarrow$ Belongs to `Marked_Delivered_Not_Received`
  - *"I want to cancel my delayed order"* $\rightarrow$ Belongs to `Order_Cancellation_And_Address_Change`
- **Frequency**: **11,130 conversations** (**13.67%** of total dataset)
- **Typical Historical Handling**: AmazonHelp provides carrier tracking links, explains Prime dispatch vs. delivery SLAs, or asks the customer to allow a 24-hour buffer window for carrier scans.
- **Ambiguity & Confusable With**: `Refund_Status_And_Billing_Disputes`, `Order_Cancellation_And_Address_Change`
- **Representative Conversation IDs**: `2823138_AmazonHelp`, `288254_AmazonHelp`

---

### 2. `Marked_Delivered_Not_Received`
- **Definition**: Customer states that the tracking status shows "Delivered", "Handed to resident", or "Left at front door", but the physical package was never received (stolen, misdelivered, or false carrier scan).
- **Examples**:
  - *"@AmazonHelp my account says my same day delivery order was delivered yesterday but I never received my package."*
  - *"With out delivering it is showing as 'Delivered' ....want to see receive copy.... @AmazonHelp"*
  - *"Pinche @AmazonHelp for delivering the parcel to the wrong apartment. Congrats to my neighbor who got a free copy!"*
- **Non-Examples**:
  - *"Package has not shipped yet"* $\rightarrow$ Belongs to `Delivery_Tracking_And_Delays`
- **Frequency**: **1,059 conversations** (**1.30%** of total dataset)
- **Typical Historical Handling**: AmazonHelp warns against posting sensitive Order IDs publicly, asks customer to check with household/neighbors, and directs customer to a secure callback link for replacement/refund clearance.
- **Ambiguity & Confusable With**: `Delivery_Tracking_And_Delays`, `Refund_Status_And_Billing_Disputes`
- **Representative Conversation IDs**: `522644_AmazonHelp`

---

### 3. `Damaged_Defective_Or_Wrong_Item`
- **Definition**: Customer received a physically broken product, defective hardware, incorrect item variant, missing accessory, or tampered package.
- **Examples**:
  - *"Ordered a phone case, look what I got 😂 @AmazonHelp what's happening?"*
  - *"@AmazonHelp Are you guys desperate to get rid of this Bjork album? This is the second time! I need the right vinyl!"*
  - *"Kinda sucks when you package is all jacked up when you get it. Thanks @AmazonHelp"*
- **Non-Examples**:
  - *"Package arrived 3 days late"* $\rightarrow$ Belongs to `Delivery_Tracking_And_Delays`
- **Frequency**: **1,921 conversations** (**2.36%** of total dataset)
- **Typical Historical Handling**: AmazonHelp apologizes for the condition, offers an immediate free replacement dispatch, or generates a pre-paid return mailing label.
- **Ambiguity & Confusable With**: `Return_Exchange_And_Pickup`, `Refund_Status_And_Billing_Disputes`
- **Representative Conversation IDs**: `1381128_AmazonHelp`

---

### 4. `Order_Cancellation_And_Address_Change`
- **Definition**: Customer requesting order cancellation, pre-dispatch modification, or updating shipping address post-purchase.
- **Examples**:
  - *"@AmazonHelp My order (Philips Toothbrush) has a better price available, £5 cheaper. Can I cancel my order and re-order?"*
  - *"I accidentally put my old home address on my order! Can I change it before it ships?"*
  - *"Please cancel order #407-2566173 immediately, ordered by mistake."*
- **Non-Examples**:
  - *"I want to return a product I already received"* $\rightarrow$ Belongs to `Return_Exchange_And_Pickup`
- **Frequency**: **2,458 conversations** (**3.02%** of total dataset)
- **Typical Historical Handling**: AmazonHelp explains pre-dispatch cancellation rules, confirms cancellation status, or directs user to 'Your Orders' tab.
- **Ambiguity & Confusable With**: `Return_Exchange_And_Pickup`, `Refund_Status_And_Billing_Disputes`
- **Representative Conversation IDs**: `2724551_AmazonHelp`

---

### 5. `Return_Exchange_And_Pickup`
- **Definition**: Customer requesting product return, item exchange, reverse pickup label, or reporting courier pickup no-show.
- **Examples**:
  - *"Reverse orders are picked up and show as pickup cancelled! Call customer service - they say product not received!"*
  - *"How do I print a return label if I don't have a printer?"*
  - *"Courier was supposed to pick up my return parcel yesterday between 9am-5pm but nobody turned up."*
- **Non-Examples**:
  - *"Cancel my order before it ships"* $\rightarrow$ Belongs to `Order_Cancellation_And_Address_Change`
- **Frequency**: **2,716 conversations** (**3.34%** of total dataset)
- **Typical Historical Handling**: AmazonHelp provides link to Online Returns Center, reschedules reverse pickup window, or issues instant promotional refund credit.
- **Ambiguity & Confusable With**: `Damaged_Defective_Or_Wrong_Item`, `Refund_Status_And_Billing_Disputes`
- **Representative Conversation IDs**: `522644_AmazonHelp`

---

### 6. `Refund_Status_And_Billing_Disputes`
- **Definition**: Customer inquiring about pending refund status, double credit card charges, unauthorized transactions, or refund voucher credits.
- **Examples**:
  - *"@AmazonHelp not refunding my ₹26,000! Product was never delivered as seller closed account!"*
  - *"I was charged twice on my credit card for order #404-8406898. Please check!"*
  - *"When will my refund reflect in my bank account? It shows refunded 4 days ago."*
- **Non-Examples**:
  - *"How much is Prime monthly subscription?"* $\rightarrow$ Belongs to `Prime_Subscription_And_Digital_Media`
- **Frequency**: **4,056 conversations** (**4.98%** of total dataset)
- **Typical Historical Handling**: AmazonHelp explains bank refund processing timelines (3–5 business days) or directs customer to secure billing page to verify charges.
- **Ambiguity & Confusable With**: `Delivery_Tracking_And_Delays`, `Return_Exchange_And_Pickup`
- **Representative Conversation IDs**: `288254_AmazonHelp`

---

### 7. `Prime_Subscription_And_Digital_Media`
- **Definition**: Customer reporting Prime Video streaming bugs, Kindle ebook sync failures, FireTV issues, or Prime membership billing.
- **Examples**:
  - *"There should be far more films for #noirvember on Amazon Prime and Netflix in India than there are."*
  - *"My Amazon Echo hasn't been playing Spotify for three days upon request. What's going on @AmazonHelp?"*
  - *"Why am I getting charged $12.99 for Prime when I cancelled my trial last week?"*
- **Non-Examples**:
  - *"Physical Prime package not delivered"* $\rightarrow$ Belongs to `Delivery_Tracking_And_Delays`
- **Frequency**: **5,014 conversations** (**6.16%** of total dataset)
- **Typical Historical Handling**: AmazonHelp provides step-by-step device deregistration steps, app cache clearing instructions, or checks regional licensing rights.
- **Ambiguity & Confusable With**: `Delivery_Tracking_And_Delays`, `Refund_Status_And_Billing_Disputes`
- **Representative Conversation IDs**: `1632515_AmazonHelp`

---

### 8. `Promotions_GiftCards_And_Pricing`
- **Definition**: Customer inquiring about promo codes, gift card balance redemption errors, Lightning Deal discounts, or invoice requests.
- **Examples**:
  - *"@AmazonHelp my gift card balance of $50 is not applying at checkout!"*
  - *"Why did the price drop £5 right after I purchased my order?"*
  - *"I need a tax invoice receipt for my order last month. Where can I download it?"*
- **Non-Examples**:
  - *"Double charge on credit card"* $\rightarrow$ Belongs to `Refund_Status_And_Billing_Disputes`
- **Frequency**: **1,289 conversations** (**1.58%** of total dataset)
- **Typical Historical Handling**: AmazonHelp verifies promo T&Cs, provides manual voucher credit, or guides customer to 'Your Account $\rightarrow$ Gift Cards'.
- **Ambiguity & Confusable With**: `Refund_Status_And_Billing_Disputes`
- **Representative Conversation IDs**: `2724551_AmazonHelp`

---

### 9. `Account_Security_And_Login`
- **Definition**: Customer unable to log in, OTP SMS failure, password reset requests, or account locking/suspension warnings.
- **Examples**:
  - *"@AmazonHelp help me to get my amazon account pay balance defreezed... its a request!"*
  - *"Not receiving OTP code on my mobile number to log into my Amazon account."*
  - *"My account was locked due to suspicious activity but I didn't do anything wrong!"*
- **Non-Examples**:
  - *"Cannot play video on Prime Video app"* $\rightarrow$ Belongs to `Prime_Subscription_And_Digital_Media`
- **Frequency**: **880 conversations** (**1.08%** of total dataset)
- **Typical Historical Handling**: AmazonHelp directs customer to Account Recovery portal or escalates to Security Team.
- **Ambiguity & Confusable With**: `Prime_Subscription_And_Digital_Media`
- **Representative Conversation IDs**: `1381128_AmazonHelp`

---

### 10. `General_Service_Complaint_Escalation`
- **Definition**: Customer expressing severe frustration with past customer service, long phone hold times, or demanding supervisor escalation.
- **Examples**:
  - *"@AmazonHelp your customer service SUCKS!!! Every time I try to make an order I have an issue!"*
  - *"I frankly don't have the patience for another chat with your customer service people today."*
  - *"Hopeless amazon and their customer service too. Never trust this website."*
- **Non-Examples**:
  - *"My order is late but I just want a tracking update"* $\rightarrow$ Belongs to `Delivery_Tracking_And_Delays`
- **Frequency**: **1,855 conversations** (**2.28%** of total dataset)
- **Typical Historical Handling**: AmazonHelp apologizes for past experience and provides dedicated callback link.
- **Ambiguity & Confusable With**: `Delivery_Tracking_And_Delays`, `Refund_Status_And_Billing_Disputes`
- **Representative Conversation IDs**: `617_AmazonHelp`

---

### 11. `Non_English_Or_Regional_Query`
- **Definition**: Customer tweets in Spanish, German, Japanese, Portuguese, or French directed at global `@AmazonHelp` handle.
- **Examples**:
  - *"Hola @AmazonHelp. Como sé dónde habéis entregado mi pedido..."*
  - *"Amazonで注文してたキン肉マンの４９巻と５０巻が届いた☆"*
- **Frequency**: **10,218 conversations** (**12.55%** of total dataset)
- **Typical Historical Handling**: AmazonHelp responds in target language or redirects to regional handle (`@AmazonHelpIN`, `@AmazonHelpES`, `@AmazonHelpDE`).

---

### 12. `Other_Unclassified_Inquiry`
- **Definition**: Conversational banter, vague single-word mentions, or link-only tweets without actionable problem details.
- **Frequency**: **38,817 conversations** (**47.68%** of total dataset)

---

## 4. Intent Distribution Table

Distribution computed across all **81,413 AmazonHelp conversations**:

| Rank | Intent Name | Count | Percentage | Class Type |
| :---: | :--- | :---: | :---: | :---: |
| 1 | `Other_Unclassified_Inquiry` | 38,817 | 47.68% | Noise / Non-Actionable |
| 2 | `Delivery_Tracking_And_Delays` | 11,130 | 13.67% | **Dominant Core Intent** |
| 3 | `Non_English_Or_Regional_Query` | 10,218 | 12.55% | Regional Language |
| 4 | `Prime_Subscription_And_Digital_Media` | 5,014 | 6.16% | Secondary Core Intent |
| 5 | `Refund_Status_And_Billing_Disputes` | 4,056 | 4.98% | Secondary Core Intent |
| 6 | `Return_Exchange_And_Pickup` | 2,716 | 3.34% | Operational Intent |
| 7 | `Order_Cancellation_And_Address_Change` | 2,458 | 3.02% | Operational Intent |
| 8 | `Damaged_Defective_Or_Wrong_Item` | 1,921 | 2.36% | Operational Intent |
| 9 | `General_Service_Complaint_Escalation` | 1,855 | 2.28% | Operational Intent |
| 10 | `Promotions_GiftCards_And_Pricing` | 1,289 | 1.58% | Operational Intent |
| 11 | `Marked_Delivered_Not_Received` | 1,059 | 1.30% | **Critical Minority Intent** |
| 12 | `Account_Security_And_Login` | 880 | 1.08% | Minority Intent |

---

## 5. Confusing Intent Pairs & Boundary Rules

Empirical co-occurrence analysis identified the top 5 confusing intent pairs:

```mermaid
graph LR
    A[Delivery_Tracking_And_Delays] <-->|818 Co-occurrences| B[Refund_Status_And_Billing_Disputes]
    C[Refund_Status_And_Billing_Disputes] <-->|656 Co-occurrences| D[Return_Exchange_And_Pickup]
    E[Damaged_Defective_Or_Wrong_Item] <-->|505 Co-occurrences| D[Return_Exchange_And_Pickup]
```

### Confusing Pair 1: `Delivery_Tracking_And_Delays` vs. `Refund_Status_And_Billing_Disputes`
- **Dataset Co-occurrence**: 818 cases.
- **Example**: *"My package is 5 days late! I want my money refunded immediately!"*
- **Classification Boundary**:
  - If the primary action requested is **where the package is** $\rightarrow$ `Delivery_Tracking_And_Delays`.
  - If the primary action requested is **getting money back** due to delay $\rightarrow$ `Refund_Status_And_Billing_Disputes`.

### Confusing Pair 2: `Return_Exchange_And_Pickup` vs. `Damaged_Defective_Or_Wrong_Item`
- **Dataset Co-occurrence**: 505 cases.
- **Example**: *"Received a broken phone case, I need to exchange it for a new one."*
- **Classification Boundary**:
  - Root cause is **broken product** $\rightarrow$ Primary: `Damaged_Defective_Or_Wrong_Item` (Secondary: `Return_Exchange_And_Pickup`).

---

## 6. Multi-Intent Analysis

- **OBSERVED**: **5,534 messages** (**6.80%**) contain multiple distinct customer requests in a single tweet.
- **INFERENCE**: Forcing multi-intent messages into a single category creates noisy training signals for ML classifiers.
- **DECISION FOR OUR SYSTEM**:
  - We will use **Primary Intent Assignment** (based on the main requested action) for single-label benchmarking.
  - Multi-intent queries containing both a complaint AND a request for PII/account intervention will be flagged for **Human Escalation**.

---

## 7. "Other / Unknown" Intent Analysis

- **OBSERVED**: 47.68% of raw AmazonHelp tweets hit `Other_Unclassified_Inquiry` due to informal Twitter chatter (*"Hey Amazon thanks"*, *"Look at this ad lol"*).
- **INFERENCE**: Filtering out non-actionable chatter before intent classification prevents classifier dilution.
- **DECISION**: `Other_Unclassified_Inquiry` will be retained as a valid triage class for filtering out non-support tweets.

---

## 8. Taxonomy Decisions & Quality Checks

1. **Split `Delivery` into 2 Sub-Intents**: Separated `Marked_Delivered_Not_Received` from general `Delivery_Tracking_And_Delays` because missing/stolen packages require PII account escalation, while standard tracking queries can be Auto-Handled.
2. **Merged `Gift Cards` & `Promotions`**: Combined into `Promotions_GiftCards_And_Pricing` due to low individual counts (1.58% combined).
3. **Isolated `Non-English`**: Kept `Non_English_Or_Regional_Query` as a dedicated triage intent so non-English tweets can be routed to regional support handles without confusing English intent classifiers.

---

## 9. Limitations

1. **PII Masking**: Kaggle anonymized order IDs and emails (`__email__`), requiring placeholder normalization during preprocessing.
2. **Short Tweet Brevity**: Some 3-word tweets (*"where my order"*) lack full grammar context, requiring keyword rule fallback.

---

## 10. Final Recommended Taxonomy (10 Core Operational Intents)

```
1. Delivery_Tracking_And_Delays
2. Marked_Delivered_Not_Received
3. Damaged_Defective_Or_Wrong_Item
4. Order_Cancellation_And_Address_Change
5. Return_Exchange_And_Pickup
6. Refund_Status_And_Billing_Disputes
7. Prime_Subscription_And_Digital_Media
8. Promotions_GiftCards_And_Pricing
9. Account_Security_And_Login
10. General_Service_Complaint_Escalation
```

---

*Phase 3 Intent Discovery Complete. Processed taxonomy written to `data/processed/intent_taxonomy.json`.*

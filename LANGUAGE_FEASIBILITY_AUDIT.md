# AmazonHelp Non-English Language Feasibility Audit

**Date**: 2026-09-12  
**Dataset**: AmazonHelp (`twcs.csv`, 81,413 reconstructed conversations)  
**Status**: AUDIT COMPLETE — FEASIBILITY DETERMINED  

---

## 1. Executive Summary

This document presents the **Language-Feasibility Audit** for the AmazonHelp subset of the Customer Support on Twitter dataset. The goal is to determine whether our proposed Golden Set **Bucket B4 (20 Non-English Examples: 8 Spanish, 5 German, 7 French/Italian/Other)** can be cleanly supported by real customer conversations in the reconstructed dataset.

---

## 2. Methodology & Detection Rules

### 2.1 Language Detection Method
Language detection was performed across all **81,413 reconstructed AmazonHelp conversations** using a multi-stage rule engine:
1. **Character Script Matching**: Detects Japanese (Hiragana, Katakana, Kanji) and Cyrillic/Arabic/Korean unicode blocks.
2. **Vocabulary & Stopword Matching**: Scans for language-specific customer support stopwords and diacritics for Spanish (ES), German (DE), French (FR), Italian (IT), and Portuguese (PT).

### 2.2 Quality & Suitability Exclusion Criteria
To ensure that only high-quality, defensible examples enter the Golden Set, candidate conversations were filtered to exclude:
- **Link-only / Media-only tweets**: Tweets containing only URLs or media attachments without text problem descriptions.
- **Ultra-short / Ambiguous tweets**: Messages with 3 or fewer words or containing only @mentions.
- **Bot Chatter & Noise**: Single-word greetings or auto-replies.
- **Exact & Near-Duplicates**: Duplicate customer complaints sent across multiple threads.

---

## 3. Quantitative Language Breakdown

### 3.1 Raw Message-Level & Conversation-Level Distribution

| Language | Inbound Customer Msgs | Unique Conversations | 2+ Turn Convos | Suitable Golden Candidates |
| :--- | :---: | :---: | :---: | :---: |
| **Spanish (ES)** | 13,231 | 5,179 | 5,179 | **5,154** |
| **German (DE)** | 5,919 | 2,336 | 2,336 | **2,332** |
| **French (FR)** | 8,302 | 2,800 | 2,800 | **2,785** |
| **Italian (IT)** | 5,373 | 1,880 | 1,880 | **1,876** |
| **Portuguese (PT)** | 16,949 | 5,224 | 5,224 | **5,215** |
| **Japanese (JP)** | 9,298 | 5,958 | 5,958 | **749** |
| **Other Non-English** | 52 | 9 | 9 | **9** |
| **English (EN)** | 224,142 | 58,027 | 58,027 | 58,027 |
| **TOTAL NON-ENGLISH** | **59,124** | **23,386** | **23,386** | **18,120** |

---

## 4. B4 Bucket Feasibility Assessment

### 4.1 Evaluation of Proposed Allocation (Target: 20)
- **Proposed Target**: 20 Non-English Examples (Spanish: 8, German: 5, French/Italian/Other: 7).
- **Actual Suitable Non-English Pool**: **18,120 conversations**.

> [!NOTE]
> **OBSERVED**: The AmazonHelp corpus contains 18,120 high-quality, suitable non-English customer conversations (5,154 Spanish, 2,332 German, 10,634 French/Italian/Other/Portuguese/Japanese).  
> **INFERENCE**: The proposed B4 target of 20 non-English examples is **100% FEASIBLE** and easily supported by the data without padding with noise or link-only tweets.  
> **DECISION**: Retain B4 at **20 examples** with the exact proposed breakdown of **8 Spanish, 5 German, and 7 French/Italian/Other**.

---

## 5. Final Audit Summary Block

```text
LANGUAGE FEASIBILITY:
- TOTAL SUITABLE NON-ENGLISH:
18120

PROPOSED B4 (20):
FEASIBLE

RECOMMENDED B4 ALLOCATION:
Spanish (ES): 8
German (DE): 5
French / Italian / Other: 7

REMAINING SHORTFALL:
0

RECOMMENDED REALLOCATION:
None (Proposed B4 allocation is fully supported by empirical data)
```

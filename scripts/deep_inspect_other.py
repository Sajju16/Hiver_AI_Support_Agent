"""
deep_inspect_other.py — Uncover patterns inside unclassified AmazonHelp tweets.

Extracts customer messages currently hitting 'Other_Or_General_Inquiry'
and analyzes top n-grams, common phrases, and sub-intents to improve taxonomy coverage.

Usage:
    py -u scripts/deep_inspect_other.py
"""

import sys, json, re
from pathlib import Path
from collections import Counter, defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.discover_amazon_intents import extract_amazon_conversations, classify_intent_rules


def inspect_other():
    convos, _, _, _, _ = extract_amazon_conversations()
    
    other_convos = []
    classified_convos = defaultdict(list)

    for c in convos:
        txt = c["customer_initial_query"]
        intents = classify_intent_rules(txt)
        if intents == ["Other_Or_General_Inquiry"]:
            other_convos.append(c)
        else:
            for i in intents:
                classified_convos[i].append(c)

    print(f"\nTotal AmazonHelp Convos: {len(convos):,}")
    print(f"Classified: {len(convos) - len(other_convos):,} ({(len(convos) - len(other_convos))/len(convos)*100:.2f}%)")
    print(f"Unclassified (Other): {len(other_convos):,} ({len(other_convos)/len(convos)*100:.2f}%)")

    # Analyze n-grams in unclassified
    word_counts = Counter()
    phrase_counts = Counter()

    for c in other_convos[:10000]:
        t = re.sub(r'@\S+', '', c["customer_initial_query"]).lower()
        t = re.sub(r'https?://\S+', '', t)
        words = [w for w in re.findall(r'\b[a-z]{3,}\b', t) if w not in {'the', 'and', 'for', 'you', 'this', 'that', 'with', 'have', 'your', 'are', 'was', 'not', 'can', 'out', 'get', 'from', 'but', 'all', 'what', 'how', 'has', 'will', 'just', 'when', 'one', 'been', 'there', 'would', 'could'}]
        word_counts.update(words)
        
        # 2-grams
        for i in range(len(words)-1):
            phrase_counts[f"{words[i]} {words[i+1]}"] += 1

    print("\n--- Top Words in 'Other' ---")
    for w, c in word_counts.most_common(25):
        print(f"  {w:20s}: {c:,}")

    print("\n--- Top 2-Grams in 'Other' ---")
    for p, c in phrase_counts.most_common(25):
        print(f"  {p:25s}: {c:,}")

    print("\n--- Sample 20 Unclassified Customer Messages ---")
    for i, c in enumerate(other_convos[:20]):
        print(f"  {i+1}. {c['customer_initial_query'][:120]}")


if __name__ == "__main__":
    inspect_other()

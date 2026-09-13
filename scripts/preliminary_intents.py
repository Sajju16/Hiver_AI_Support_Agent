"""
preliminary_intents.py — Sample customer messages for top brands and identify
recurring issue categories. PRELIMINARY only — not the final taxonomy.

Usage:
    $env:PYTHONIOENCODING='utf-8'; py scripts/preliminary_intents.py
"""

import sys, json, time, re
from pathlib import Path
from collections import Counter, defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from src.data.data_utils import iter_chunks, CHUNK_SIZE

OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Brands to analyze
TARGET_BRANDS = [
    "AmazonHelp", "AppleSupport", "SpotifyCares", "Uber_Support",
    "TMobileHelp", "comcastcares", "Delta", "AmericanAir",
]

# Keyword-based heuristic categories for preliminary intent discovery
KEYWORD_PATTERNS = {
    "account_access": r"can.?t (log|sign)|locked out|password|reset|account.*(access|locked|hack|suspend)",
    "billing_charge": r"charge|bill|refund|overcharge|fee|payment|credit|invoice|money|promo code|coupon",
    "service_outage": r"down|outage|not work|broken|crash|error|can.?t (use|access|connect|open|load)",
    "delivery_shipping": r"deliver|ship|package|tracking|order|arrival|late|missing.*order",
    "cancellation": r"cancel|unsubscribe|stop.*service|close.*account|remove.*account",
    "speed_performance": r"slow|buffer|lag|speed|loading|performance|freeze|hang",
    "connectivity": r"connect|wifi|wi-fi|signal|network|coverage|no service|dropped call",
    "app_update": r"update|upgrade|version|ios|android|latest.*version|app.*crash|app.*bug",
    "device_hardware": r"battery|screen|speaker|microphone|camera|charger|headphone|bluetooth",
    "customer_service_complaint": r"worst|terrible|horrible|awful|pathetic|useless|incompetent|worst.*service|hate",
    "flight_travel": r"flight|delay|cancel.*flight|book|reservation|boarding|gate|luggage|baggage",
    "data_plan": r"data.*plan|data.*usage|throttle|unlimited|roaming|international",
    "transfer_dm": r"DM|direct message|private message|send.*message",
    "positive_feedback": r"thank|love|great|awesome|excellent|amazing|appreciate|kudos",
}


def classify_preliminary(text):
    """
    Apply keyword heuristics to classify a customer message.
    Returns a list of matching categories (can be multi-label).
    """
    text_lower = text.lower()
    matches = []
    for cat, pattern in KEYWORD_PATTERNS.items():
        if re.search(pattern, text_lower):
            matches.append(cat)
    if not matches:
        matches.append("other")
    return matches


def analyze_intents():
    print("=" * 70)
    print("PRELIMINARY INTENT ANALYSIS")
    print("=" * 70)

    # Collect inbound (customer) messages that mention target brands
    brand_messages = defaultdict(list)
    t0 = time.time()
    row_count = 0

    # We'll collect up to 2000 inbound messages per brand
    MAX_PER_BRAND = 2000

    print("Scanning for customer messages directed at target brands...")
    for chunk in iter_chunks():
        inbound = chunk[chunk["inbound"] == True]

        for _, row in inbound.iterrows():
            text = str(row["text"]) if pd.notna(row["text"]) else ""

            # Check which brand is mentioned via @mention in text
            for brand in TARGET_BRANDS:
                if f"@{brand}" in text or f"@{brand.lower()}" in text.lower():
                    if len(brand_messages[brand]) < MAX_PER_BRAND:
                        brand_messages[brand].append({
                            "tweet_id": str(row["tweet_id"]),
                            "author_id": str(row["author_id"]),
                            "text": text,
                            "created_at": str(row["created_at"]),
                        })
                    break  # Only assign to one brand

            row_count += 1

        # Check if we have enough for all brands
        all_full = all(
            len(brand_messages[b]) >= MAX_PER_BRAND for b in TARGET_BRANDS
        )
        if all_full:
            print(f"  Collected {MAX_PER_BRAND} per brand after {row_count:,} rows")
            break

        if row_count % 500_000 < CHUNK_SIZE:
            counts = {b: len(msgs) for b, msgs in brand_messages.items()}
            print(f"  ... {row_count:,} rows, collected: {counts}")

    elapsed = time.time() - t0
    print(f"  Collection done ({elapsed:.1f}s)")

    # ── Classify and summarize ──────────────────────────────────────────
    results = {}

    for brand in TARGET_BRANDS:
        msgs = brand_messages.get(brand, [])
        if not msgs:
            print(f"\n{brand}: No messages collected!")
            continue

        print(f"\n{'=' * 60}")
        print(f"BRAND: {brand} ({len(msgs)} customer messages)")
        print(f"{'=' * 60}")

        cat_counter = Counter()
        cat_examples = defaultdict(list)

        for msg in msgs:
            cats = classify_preliminary(msg["text"])
            for cat in cats:
                cat_counter[cat] += 1
                if len(cat_examples[cat]) < 3:
                    cat_examples[cat].append(msg["text"][:200])

        print(f"\n  Preliminary categories:")
        for cat, count in cat_counter.most_common():
            pct = count / len(msgs) * 100
            print(f"    {cat:35s}  {count:>5}  ({pct:.1f}%)")
            for ex in cat_examples[cat][:2]:
                print(f"      → {ex[:150]}")

        results[brand] = {
            "message_count": len(msgs),
            "categories": {
                cat: {
                    "count": count,
                    "percentage": round(count / len(msgs) * 100, 1),
                    "examples": cat_examples[cat],
                }
                for cat, count in cat_counter.most_common()
            },
        }

    # Save
    out_path = OUTPUT_DIR / "preliminary_intents.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str, ensure_ascii=False)
    print(f"\nSaved to {out_path}")

    return results


if __name__ == "__main__":
    analyze_intents()

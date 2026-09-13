"""
scripts/find_spanish_replacements.py — Find 5 verified Spanish replacement candidates for Golden B4
"""

import sys, json, re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from src.data.data_utils import get_raw_csv_path

GOLDEN_PATH = PROJECT_ROOT / "data" / "golden" / "golden_candidates_200.json"
DEV_PATH = PROJECT_ROOT / "data" / "dev" / "dev_candidates_50.json"

TARGET_BRAND = "AmazonHelp"
amazon_numeric_aids = {"115821", "115830", "115850", "116875", "116928", "117086", "116316", "115825", "120533", "116062"}

def main():
    with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
        golden = json.load(f)
    with open(DEV_PATH, "r", encoding="utf-8") as f:
        dev = json.load(f)

    used_convos = set(c["conversation_id"] for c in golden).union(set(c["conversation_id"] for c in dev))
    used_turn_keys = set((c["conversation_id"], c["turn_index"]) for c in golden).union(set((c["conversation_id"], c["turn_index"]) for c in dev))

    print(f"Loaded Golden ({len(golden)}) and Dev ({len(dev)}). Used conversation IDs: {len(used_convos):,}")

    csv_path = get_raw_csv_path()
    df = pd.read_csv(
        csv_path,
        dtype={'tweet_id': str, 'author_id': str, 'inbound': str, 'in_response_to_tweet_id': str, 'response_tweet_id': str},
        low_memory=False
    )
    tids = df['tweet_id'].astype(str).str.strip().values
    authors = df['author_id'].fillna('').astype(str).str.strip().values
    inbounds = (df['inbound'].astype(str).str.upper() == 'TRUE').values
    texts = df['text'].fillna('').astype(str).values
    parent_series = df['in_response_to_tweet_id'].astype(str).str.strip().str.rstrip('.0')
    parents = parent_series.replace(['nan', 'None', '', 'NaN', '<NA>'], None).values

    tweet_author = dict(zip(tids, authors))
    tweet_inbound = dict(zip(tids, [bool(x) for x in inbounds]))
    tweet_text = dict(zip(tids, texts))
    tweet_parent = dict(zip(tids, parents))

    parent_children = defaultdict(list)
    for tid, parent in zip(tids, parents):
        if parent:
            parent_children[parent].append(tid)

    # Spanish keywords for high precision candidates
    spanish_keywords = ["hola", "paquete", "pedido", "entrega", "compré", "mi cuenta", "gracias", "envío", "factura", "devuelto", "reembolso", "llegó", "comprar"]

    spanish_candidates = []

    for tid, author in tweet_author.items():
        is_cust = tweet_inbound.get(tid, True)
        if not is_cust:
            continue

        txt = tweet_text[tid]
        txt_lower = txt.lower()

        # Must contain clear Spanish words and NOT Portuguese specific words (nao, voce, obrigado, os precos, fiz, esta)
        if any(w in txt_lower for w in [" nao ", " você", " obrigado", " precos", " fiz ", " estou "]):
            continue

        # Check Spanish keywords
        if not any(k in txt_lower for k in spanish_keywords):
            continue

        # Check local association with AmazonHelp
        direct_children_authors = [tweet_author.get(child) for child in parent_children.get(tid, [])]
        is_direct_child = TARGET_BRAND in direct_children_authors
        handles = re.findall(r'@(\w+)', txt)
        has_amazon_handle = any(h.lower() in ["amazonhelp", "amazon", "amazones", "amazonmexico"] for h in handles)
        has_mapped_numeric = any(h in {"116875", "116928"} for h in handles) # 116875 = AmazonMX, 116928 = AmazonES

        if is_direct_child or has_amazon_handle or has_mapped_numeric:
            # Build linear ancestor chain
            ancestors = []
            curr_parent = tweet_parent.get(tid)
            visited_ancestors = set()
            while curr_parent and curr_parent in tweet_author and curr_parent not in visited_ancestors:
                visited_ancestors.add(curr_parent)
                ancestors.append({
                    "author": tweet_author[curr_parent],
                    "text": tweet_text[curr_parent],
                    "is_customer": tweet_inbound.get(curr_parent, True),
                    "tweet_id": curr_parent
                })
                curr_parent = tweet_parent.get(curr_parent)

            ancestors.reverse()
            root_id = ancestors[0]["tweet_id"] if ancestors else tid
            cid = f"{root_id}_{TARGET_BRAND}"
            turn_idx = len([m for m in ancestors if m["is_customer"]])

            if cid in used_convos or (cid, turn_idx) in used_turn_keys:
                continue

            spanish_candidates.append({
                "conversation_id": cid,
                "root_tweet_id": root_id,
                "turn_index": turn_idx,
                "raw_text": txt,
                "tweet_id": tid,
                "prior_context": [
                    {"author": m["author"], "text": m["text"], "is_customer": m["is_customer"]}
                    for m in ancestors
                ]
            })

    print(f"Found {len(spanish_candidates)} eligible clean Spanish candidate turns.")

    with open(PROJECT_ROOT / "data" / "processed" / "spanish_replacements_pool.json", "w", encoding="utf-8") as f:
        json.dump(spanish_candidates[:15], f, indent=2, ensure_ascii=False)

    print("Exported top 15 candidate turns to data/processed/spanish_replacements_pool.json")

if __name__ == "__main__":
    from collections import defaultdict
    main()

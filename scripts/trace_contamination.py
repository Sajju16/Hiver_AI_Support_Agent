"""
trace_contamination.py — Optimized exact provenance tracer for contamination examples
"""

import pandas as pd
import json
from pathlib import Path
from collections import defaultdict

csv_path = Path("archive/twcs/twcs.csv")
print(f"Loading raw dataset from {csv_path}...")

df = pd.read_csv(
    csv_path,
    dtype={'tweet_id': str, 'author_id': str, 'inbound': str, 'in_response_to_tweet_id': str, 'response_tweet_id': str},
    low_memory=False
)

tids = df['tweet_id'].astype(str).str.strip().values
authors = df['author_id'].fillna('').astype(str).str.strip().values
inbounds = (df['inbound'].astype(str).str.upper() == 'TRUE').values
created_ats = df['created_at'].fillna('').astype(str).values
texts = df['text'].fillna('').astype(str).values
parents = df['in_response_to_tweet_id'].astype(str).str.strip().str.rstrip('.0').replace(['nan', 'None', '', 'NaN', '<NA>'], None).values

tweet_dict = {}
parent_children = defaultdict(list)

for tid, auth, inb, cat, txt, par in zip(tids, authors, inbounds, created_ats, texts, parents):
    tweet_dict[tid] = {
        'tweet_id': tid, 'author_id': auth, 'inbound': inb, 'created_at': cat, 'text': txt, 'parent': par
    }
    if par:
        parent_children[par].append(tid)

print("Indexed tree graph. Tracing specific conversation roots...")

def trace_root(root_id, label_tag):
    print(f"\n=======================================================")
    print(f" TRACING [{label_tag}] ROOT TWEET ID: {root_id}")
    print(f"=======================================================")

    queue = [root_id]
    visited = set()
    thread = []

    while queue:
        curr = queue.pop(0)
        if curr in visited: continue
        visited.add(curr)
        if curr in tweet_dict:
            thread.append(tweet_dict[curr])
        for child in parent_children.get(curr, []):
            if child not in visited:
                queue.append(child)

    print(f"Total connected tweets in thread: {len(thread)}")
    authors_in_thread = set()
    for tr in thread:
        authors_in_thread.add(tr['author_id'])
        print(f"  [TID: {tr['tweet_id']}] Author: {tr['author_id']} | Inbound: {tr['inbound']} | InRespTo: {tr['parent']}")
        print(f"     Text: {repr(tr['text'])}\n")
    print(f"Unique authors in thread graph: {authors_in_thread}")


val_path = Path("data/processed/final_verification_pass.json")
if val_path.exists():
    with open(val_path, "r", encoding="utf-8") as f:
        vdata = json.load(f)
    
    rows = vdata["task_a_language_spot_check"]["rows"] + vdata["task_b_directed_at_brand_check"]["rows"]
    
    traced = set()
    for r in rows:
        t = r["text"].lower()
        cid = r["conversation_id"]
        rid = cid.split("_")[0]

        if "hulu" in t and "hulu" not in traced:
            traced.add("hulu")
            trace_root(rid, "Hulu Example")

        if ("apple" in t or "applesupport" in t) and "apple" not in traced:
            traced.add("apple")
            trace_root(rid, "AppleSupport Example")

        if ("virgin" in t or "virgintrains" in t) and "virgin" not in traced:
            traced.add("virgin")
            trace_root(rid, "VirginTrains Example")

        if ("hermes" in t or "myhermes" in t) and "hermes" not in traced:
            traced.add("hermes")
            trace_root(rid, "myHermes Example")

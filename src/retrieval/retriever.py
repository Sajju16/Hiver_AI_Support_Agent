"""
src/retrieval/retriever.py

Retrieval-Augmented Generation (RAG) module for historical AmazonHelp resolutions with similarity confidence guardrails.
"""

import os, re, json, csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
HISTORICAL_EXAMPLES_PATH = PROJECT_ROOT / "data" / "processed" / "amazon_intent_examples.json"
EXTERNAL_187_PATH = PROJECT_ROOT / "data" / "processed" / "external_human_examples_187.json"
EXTERNAL_187_CSV_PATH = PROJECT_ROOT / "amazonhelp_golden_set.csv"

def preprocess_text(raw_text: str, thread_context: list = None) -> str:
    """Cleans handle mentions, URLs, extra whitespace, and combines text."""
    context_texts = [t.get("text", "") for t in thread_context] if thread_context else []
    full_raw = raw_text + " " + " ".join(context_texts)
    
    text = re.sub(r'https?://\S+', '', full_raw)
    text = re.sub(r'@\w+', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

class HistoricalResolutionRetriever:
    """TF-IDF Cosine Similarity Retriever for historical AmazonHelp resolutions."""
    
    def __init__(self):
        self.corpus = []
        self.vectorizer = None
        self.corpus_tfidf = None
        self.index_loaded = False
        self._load_corpus()

    def _load_corpus(self):
        # 1. Load base historical examples
        if HISTORICAL_EXAMPLES_PATH.exists():
            with open(HISTORICAL_EXAMPLES_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                for cat, examples in data.items():
                    for ex in examples:
                        q = ex.get("customer_text", ex.get("customer_message", ex.get("raw_text", "")))
                        a = ex.get("amazon_response", ex.get("agent_resolution", ex.get("resolution", "")))
                        cid = ex.get("conversation_id", ex.get("convo_id", f"HIST_{len(self.corpus)+1}"))
                        if q and a:
                            self.corpus.append({
                                "historical_id": cid,
                                "category": cat,
                                "customer_query": q,
                                "agent_resolution": a,
                                "clean_text": preprocess_text(q)
                            })

        # 2. Load 187 external customer-resolution pairs
        if EXTERNAL_187_PATH.exists() and EXTERNAL_187_CSV_PATH.exists():
            with open(EXTERNAL_187_PATH, "r", encoding="utf-8") as f_json, \
                 open(EXTERNAL_187_CSV_PATH, "r", encoding="utf-8", errors="replace") as f_csv:
                ext_items = json.load(f_json)
                csv_rows = list(csv.DictReader(f_csv))
                for idx, row in enumerate(csv_rows):
                    txt = row.get("conversation_text", "")
                    cid = row.get("conversation_id", f"EXT_{idx+1}").strip()
                    cat = ext_items[idx]["primary_intent"] if idx < len(ext_items) else "Other_Unclassified_Inquiry"
                    if "AmazonHelp:" in txt:
                        parts = txt.split("AmazonHelp:", 1)
                        q = parts[0].replace("Customer:", "").strip()
                        a = parts[1].strip()
                    else:
                        q = txt.replace("Customer:", "").strip()
                        a = "Please send us a Direct Message with your order details so our support team can investigate and assist you."
                    if q and a:
                        self.corpus.append({
                            "historical_id": f"EXT_{cid}",
                            "category": cat,
                            "customer_query": q,
                            "agent_resolution": a,
                            "clean_text": preprocess_text(q)
                        })

        if self.corpus:
            from sklearn.feature_extraction.text import TfidfVectorizer
            texts = [item["clean_text"] for item in self.corpus]
            self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)
            self.corpus_tfidf = self.vectorizer.fit_transform(texts)
            self.index_loaded = True

    def retrieve_top_k(self, query_text: str, target_intent: str = None, top_k: int = 1) -> list:
        if not self.corpus or self.corpus_tfidf is None:
            return [{
                "historical_id": "DEFAULT_REF_001",
                "category": "Other_Unclassified_Inquiry",
                "similarity_score": 0.0,
                "is_fallback": True,
                "customer_query": query_text,
                "agent_resolution": "Please send us a Direct Message with your order details so our support team can investigate and assist you."
            }]

        from sklearn.metrics.pairwise import cosine_similarity
        clean_q = preprocess_text(query_text)
        q_vec = self.vectorizer.transform([clean_q])
        sims = cosine_similarity(q_vec, self.corpus_tfidf)[0]

        scored = []
        for idx, item in enumerate(self.corpus):
            base_sim = float(sims[idx])
            intent_boost = 0.1 if (target_intent and target_intent.lower() in item["category"].lower()) else 0.0
            total_score = round(min(1.0, base_sim + intent_boost), 4)

            scored.append({
                "historical_id": item["historical_id"],
                "category": item["category"],
                "similarity_score": total_score,
                "is_fallback": False,
                "customer_query": item["customer_query"],
                "agent_resolution": item["agent_resolution"]
            })

        scored.sort(key=lambda x: x["similarity_score"], reverse=True)
        return scored[:top_k]

class GroundedReplySynthesizer:
    """Retrieval-Augmented Synthesis Engine (RAG-Template Fallback)."""
    
    SIMILARITY_THRESHOLD = 0.15

    @staticmethod
    def synthesize_reply(query_text: str, predicted_intent: str, retrieved_match: dict) -> str:
        res = retrieved_match.get("agent_resolution", "")
        sim_score = float(retrieved_match.get("similarity_score", 0.0))
        is_fallback = bool(retrieved_match.get("is_fallback", False))

        # Sanitize any legacy handles or URLs from historical resolution
        res_clean = re.sub(r'@\w+', '', res)
        res_clean = re.sub(r'https?://\S+', '', res_clean).strip()

        # Similarity Guardrail: If similarity is low (< 0.15) or explicit fallback, return safe bounded resolution prompt
        if sim_score < GroundedReplySynthesizer.SIMILARITY_THRESHOLD or is_fallback or not res_clean:
            return (
                f"Hello! Thank you for contacting AmazonHelp regarding {predicted_intent.replace('_', ' ')}. "
                f"Please send us a Direct Message with your order details so our support team can investigate and assist you."
            )

        reply = (
            f"Hello! Thank you for reaching out to AmazonHelp regarding {predicted_intent.replace('_', ' ')}. "
            f"Based on our historical resolution procedure: {res_clean}"
        )
        return reply

"""
run_final_verification_pass.py — Final Verification Pass for Golden Set Sourcing

Executes:
Task A: Language Pool Spot-Check (15 additional suitable candidates for ES, DE, FR, IT, JP; seed=777)
Task B: Directed-at-Brand Sanity Check (20 English core-intent candidates from B1 pool; seed=888)

Usage:
    py -u scripts/run_final_verification_pass.py
"""

import sys, json, time, re, random
from pathlib import Path
from collections import defaultdict, Counter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from src.data.data_utils import get_raw_csv_path

OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TARGET_BRAND = "AmazonHelp"

def load_amazon_convos():
    csv_path = get_raw_csv_path()
    print(f"Loading AmazonHelp dataset from {csv_path}...", flush=True)
    t0 = time.time()

    df = pd.read_csv(
        csv_path,
        dtype={'tweet_id': str, 'author_id': str, 'inbound': str, 'in_response_to_tweet_id': str},
        usecols=['tweet_id', 'author_id', 'inbound', 'created_at', 'text', 'in_response_to_tweet_id'],
        low_memory=False
    )

    tids = df['tweet_id'].astype(str).str.strip().values
    authors = df['author_id'].fillna('').astype(str).str.strip().values
    inbounds = (df['inbound'].astype(str).str.upper() == 'TRUE').values
    created_ats = df['created_at'].fillna('').astype(str).values
    texts = df['text'].fillna('').astype(str).values
    
    parent_series = df['in_response_to_tweet_id'].astype(str).str.strip().str.rstrip('.0')
    parents = parent_series.replace(['nan', 'None', '', 'NaN', '<NA>'], None).values

    tweet_author = dict(zip(tids, authors))
    tweet_inbound = dict(zip(tids, [bool(x) for x in inbounds]))
    tweet_created = dict(zip(tids, created_ats))
    tweet_text = dict(zip(tids, texts))

    parent_children = defaultdict(list)
    roots = set()

    for tid, parent in zip(tids, parents):
        if parent:
            parent_children[parent].append(tid)
        else:
            roots.add(tid)

    amazon_convos = []
    
    for root_id in roots:
        queue = [root_id]
        visited = set()
        thread_tids = []

        while queue:
            curr = queue.pop(0)
            if curr in visited:
                continue
            visited.add(curr)
            if curr in tweet_author:
                thread_tids.append(curr)
            for child in parent_children.get(curr, []):
                if child not in visited:
                    queue.append(child)

        if not thread_tids:
            continue

        has_amazon = any(tweet_author.get(t) == TARGET_BRAND for t in thread_tids)
        has_cust = any(tweet_inbound.get(t, True) for t in thread_tids)

        if not has_amazon or not has_cust:
            continue

        cust_msgs = [tweet_text[t] for t in thread_tids if tweet_inbound.get(t, True)]
        amazon_msgs = [tweet_text[t] for t in thread_tids if not tweet_inbound.get(t, True) and tweet_author.get(t) == TARGET_BRAND]

        amazon_convos.append({
            "conversation_id": f"{root_id}_{TARGET_BRAND}",
            "root_tweet_id": root_id,
            "message_count": len(thread_tids),
            "customer_initial_query": cust_msgs[0] if cust_msgs else "",
            "all_customer_messages": cust_msgs,
            "amazon_responses": amazon_msgs,
            "thread_tids": thread_tids
        })

    print(f"Loaded {len(amazon_convos):,} AmazonHelp conversations in {time.time()-t0:.1f}s", flush=True)
    return amazon_convos


def detect_language(text):
    txt_lower = text.lower()

    if re.search(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]', text):
        return "JP"

    es_keywords = [
        " por favor", " gracias", "hola ", "buenos dias", "buenas tardes", "pedido", "paquete",
        "envio", "entrega", "mi cuenta", "reembolso", "cancelar", "compras", "direccion", "solucion",
        "ayuda", "vuestro", "nuestro", "estoy", "tengo", "hacer", "quiero", "donde esta", "que pasa",
        "españa", "mexico", "colombia", "chile", "argentina", "madrid", "barcelona"
    ]
    if any(k in txt_lower for k in es_keywords) or re.search(r'\b(que|por|para|con|del|las|los|una|uno|este|esta|como|pero|mas|mi|su|al)\b', txt_lower):
        if not any(k in txt_lower for k in [" mon ", " ma ", " votre ", " notre ", " avec ", " dans ", " suez ", " il mio ", " la mia ", " non ", " perche "]):
            return "ES"

    de_keywords = [
        " gutschein", " nicht", " danke", " bitte", " lieferung", " paket", " bestellung", "versand",
        " erhalten", " kunde", " hilfe", " wo ist", " wann kommt", " erstattet", " zurueck", " zurück",
        " deutschland", " österreich", " schweiz", " haendler", " verkaeufer"
    ]
    if any(k in txt_lower for k in de_keywords) or re.search(r'\b(und|das|der|die|ist|nicht|mit|für|einen|eine|einer|ich|du|wir|sie|habe|hat)\b', txt_lower):
        return "DE"

    fr_keywords = [
        " bonjour", " merci", " s'il vous plait", " sil vous plait", " colis", " commande", " livraison",
        " rembourser", " annuler", " mon compte", " votre service", " france", " paris", " belgique",
        " est ce que", " ou est", " quand est ce", " probleme"
    ]
    if any(k in txt_lower for k in fr_keywords) or re.search(r'\b(est|que|pour|avec|dans|sur|mon|ma|mes|votre|vos|nous|vous|pas|plus|fait)\b', txt_lower):
        return "FR"

    it_keywords = [
        " buongiorno", " grazie", " per favore", " pacco", " ordine", " spedizione", " consegna",
        " rimborso", " annullare", " il mio", " la mia", " italia", " roma", " milano", " perche",
        " dove si trova", " quando arriva", " problema"
    ]
    if any(k in txt_lower for k in it_keywords) or re.search(r'\b(che|per|con|del|della|delle|degli|il|la|le|gli|un|una|questo|questa|come|ma|piu|mio|mia)\b', txt_lower):
        return "IT"

    pt_keywords = [
        " bom dia", " obrigado", " obrigada", " por favor", " encomenda", " entrega", " produto",
        " reembolsar", " cancelar", " minha conta", " brasil", " portugal", " nao ", " voce "
    ]
    if any(k in txt_lower for k in pt_keywords) or re.search(r'\b(que|para|com|do|da|dos|das|um|uma|este|esta|como|mas|mais|meu|minha|nao)\b', txt_lower):
        return "PT"

    if re.search(r'[\u0400-\u04ff\u0600-\u06ff\uac00-\ud7af]', text):
        return "OTHER_NON_EN"

    return "EN"


def evaluate_suitability(text):
    clean = re.sub(r'https?://\S+', '', text).strip()
    clean_no_mentions = re.sub(r'@\w+', '', clean).strip()

    if not clean_no_mentions:
        return False, "Link-only or handles-only tweet"

    words = clean_no_mentions.split()
    if len(words) <= 3:
        return False, "Ultra-short (<= 3 words)"

    if len(clean_no_mentions) < 15:
        return False, "Text length under 15 characters"

    return True, "SUITABLE"


def classify_b1_intent(text):
    txt = text.lower()
    if any(k in txt for k in ["delivered but", "says delivered", "show delivered", "marked delivered", "shows delivered", "showing as delivered", "delivered yesterday", "never received", "didn't receive my package", "stolen"]):
        return "Marked_Delivered_Not_Received"
    if any(k in txt for k in ["track", "tracking", "delay", "delayed", "late", "where is my", "where's my", "haven't received", "hasn't arrived", "not arrived", "when will", "out for delivery", "dispatch", "shipment"]):
        return "Delivery_Tracking_And_Delays"
    if any(k in txt for k in ["app", "website", "site", "cart", "checkout", "bug", "glitch", "error", "page", "browser", "greyed out"]):
        return "Technical_App_And_Website_Issues"
    if any(k in txt for k in ["damaged", "broken", "defective", "wrong item", "wrong product", "wrong case", "faulty", "expired", "missing item", "missing part", "empty box"]):
        return "Damaged_Defective_Or_Wrong_Item"
    if any(k in txt for k in ["cancel", "cancellation", "change address", "wrong address", "update address", "modify order"]):
        return "Order_Cancellation_And_Address_Change"
    if any(k in txt for k in ["return", "exchange", "pickup", "pick up", "pick-up", "replace", "replacement", "send back", "return label"]):
        return "Return_Exchange_And_Pickup"
    if any(k in txt for k in ["refund", "money back", "charged twice", "double charge", "charged me", "overcharged", "billing", "bank", "card"]):
        return "Refund_Status_And_Billing_Disputes"
    if any(k in txt for k in ["prime video", "kindle", "prime music", "firestick", "fire stick", "alexa", "echo", "movie", "film", "stream", "subscription"]):
        return "Prime_Subscription_And_Digital_Media"
    if any(k in txt for k in ["promo", "coupon", "discount", "gift card", "giftcard", "voucher", "deal", "price drop", "invoice"]):
        return "Promotions_GiftCards_And_Pricing"
    if any(k in txt for k in ["sign in", "login", "log in", "password", "otp", "account locked", "verification code", "hacked", "suspended"]):
        return "Account_Security_And_Login"
    return None


def run_verification():
    convos = load_amazon_convos()
    
    # Load previously sampled 5 examples per language to exclude them
    existing_audit_json = OUTPUT_DIR / "language_feasibility_audit.json"
    excluded_ids = set()
    if existing_audit_json.exists():
        with open(existing_audit_json, "r", encoding="utf-8") as f:
            aud_data = json.load(f)
            for l_key, l_val in aud_data.get("language_breakdown", {}).items():
                for ex in l_val.get("representative_examples", []):
                    excluded_ids.add(ex["conversation_id"])

    # -------------------------------------------------------------
    # TASK A: LANGUAGE POOL SPOT-CHECK (ES, DE, FR, IT, JP)
    # -------------------------------------------------------------
    target_langs = ["ES", "DE", "FR", "IT", "JP"]
    lang_candidates = defaultdict(list)
    seen_hashes = set()

    for c in convos:
        if c["conversation_id"] in excluded_ids:
            continue

        txt = c["customer_initial_query"]
        lang = detect_language(txt)

        if lang in target_langs:
            suitable, _ = evaluate_suitability(txt)
            if suitable:
                h = re.sub(r'\W+', '', txt.lower())
                if h not in seen_hashes:
                    seen_hashes.add(h)
                    lang_candidates[lang].append({
                        "language": lang,
                        "conversation_id": c["conversation_id"],
                        "turn_index": 1,
                        "detected_label": lang,
                        "text": txt
                    })

    random.seed(777)
    task_a_rows = []
    for lang in target_langs:
        pool = lang_candidates[lang]
        sampled = random.sample(pool, min(15, len(pool)))
        task_a_rows.extend(sampled)

    print(f"Task A sampled {len(task_a_rows)} rows across 5 languages (Seed=777)")

    # -------------------------------------------------------------
    # TASK B: DIRECTED-AT-BRAND SANITY CHECK (20 English Core Intent)
    # -------------------------------------------------------------
    b1_candidates = []
    seen_b1_hashes = set()

    for c in convos:
        txt = c["customer_initial_query"]
        lang = detect_language(txt)
        if lang == "EN":
            intent = classify_b1_intent(txt)
            if intent:
                suitable, _ = evaluate_suitability(txt)
                if suitable:
                    h = re.sub(r'\W+', '', txt.lower())
                    if h not in seen_b1_hashes:
                        seen_b1_hashes.add(h)
                        b1_candidates.append({
                            "conversation_id": c["conversation_id"],
                            "turn_index": 1,
                            "detected_label/intent_source": intent,
                            "text": txt
                        })

    random.seed(888)
    task_b_rows = random.sample(b1_candidates, 20)
    print(f"Task B sampled {len(task_b_rows)} English core-intent rows (Seed=888)")

    # Save JSON artifact
    json_data = {
        "task_a_language_spot_check": {
            "seed": 777,
            "target_languages": target_langs,
            "rows_count": len(task_a_rows),
            "rows": task_a_rows
        },
        "task_b_directed_at_brand_check": {
            "seed": 888,
            "rows_count": len(task_b_rows),
            "rows": task_b_rows
        },
        "japanese_observation": "Japanese has an unusually high suitability-filter exclusion rate; the cause is not established by this audit."
    }

    out_json = OUTPUT_DIR / "final_verification_pass.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2)
    print(f"Saved JSON artifact to {out_json}")

    # Generate FINAL_VERIFICATION_PASS.md
    md_lines = []
    md_lines.append("# Final Verification Pass: Language Spot-Check & Brand Alignment")
    md_lines.append("")
    md_lines.append("**Date**: 2026-09-12  ")
    md_lines.append("**Dataset**: AmazonHelp (`twcs.csv`, 81,413 reconstructed conversations)  ")
    md_lines.append("**Status**: FINAL VERIFICATION TABLES GENERATED — READY FOR HUMAN REVIEW  ")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")
    md_lines.append("## Task A — Language Pool Spot-Check (N=75)")
    md_lines.append("")
    md_lines.append("Randomly sampled 15 additional suitable candidate conversations for each of **ES, DE, FR, IT, JP** (Seed=777), excluding the 5 initial examples from the language feasibility audit. Preserved original detected language label without automatic precision judgments.")
    md_lines.append("")
    md_lines.append("| language | conversation_id | turn_index | detected_label | text |")
    md_lines.append("| :--- | :--- | :---: | :--- | :--- |")

    for r in task_a_rows:
        clean_t = r["text"].replace("\n", " ").replace("|", "\\|")
        md_lines.append(f"| {r['language']} | {r['conversation_id']} | {r['turn_index']} | {r['detected_label']} | {clean_t} |")

    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")
    md_lines.append("## Task B — Directed-at-Brand Sanity Check (N=20)")
    md_lines.append("")
    md_lines.append("Randomly sampled 20 English candidates from the B1 core-intent pool (Seed=888). Prepared for human reviewer inspection to verify whether messages represent genuine customer support requests directed at AmazonHelp.")
    md_lines.append("")
    md_lines.append("| conversation_id | turn_index | detected_label/intent_source | text |")
    md_lines.append("| :--- | :---: | :--- | :--- |")

    for r in task_b_rows:
        clean_t = r["text"].replace("\n", " ").replace("|", "\\|")
        md_lines.append(f"| {r['conversation_id']} | {r['turn_index']} | {r['detected_label/intent_source']} | {clean_t} |")

    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")
    md_lines.append("## Japanese Observation Note")
    md_lines.append("")
    md_lines.append("> [!NOTE]")
    md_lines.append("> Japanese has an unusually high suitability-filter exclusion rate; the cause is not established by this audit.")
    md_lines.append("")

    out_md = PROJECT_ROOT / "FINAL_VERIFICATION_PASS.md"
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    print(f"Saved Markdown report to {out_md}")

    return len(task_a_rows), len(task_b_rows)


if __name__ == "__main__":
    run_verification()

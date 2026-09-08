import json
from engine import config, llm


def load_index():
    if config.INDEX_FILE.exists():
        return json.loads(config.INDEX_FILE.read_text(encoding="utf-8"))
    return {}


def save_index(index):
    config.INDEX_FILE.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")


def similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def update_entry(slug, title, summary, category="00 Inbox"):
    index = load_index()
    index[slug] = {
        "vector": llm.embed(f"{title}\n{summary}"),
        "title": title,
        "category": category,
    }
    save_index(index)

def remove_entry(slug):
    index = load_index()
    if slug in index:
        del index[slug]
        save_index(index)


def find_top_matches(text, limit=5):
    index = load_index()
    if not index:
        return []
    query_vec = llm.embed(text)
    scored = []
    for slug, entry in index.items():
        score = similarity(query_vec, entry["vector"])
        scored.append((slug, entry.get("title", slug), entry.get("category", "?"), score))
    scored.sort(key=lambda x: x[3], reverse=True)
    relevant = [row for row in scored if row[3] >= config.CANDIDATE_THRESHOLD]
    return relevant[:limit]

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


def find_best_match(text):
    index = load_index()
    if not index:
        return None, 0.0, None
    query_vec = llm.embed(text)
    best_slug, best_score = None, 0.0
    for slug, entry in index.items():
        score = similarity(query_vec, entry["vector"])
        if score > best_score:
            best_slug, best_score = slug, score
    title = index[best_slug]["title"] if best_slug else None
    return best_slug, best_score, title


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

import requests
import json
from engine import config


def embed(text):
    r = requests.post(
        config.OLLAMA_EMB,
        json={"model": config.EMBED_MODEL, "prompt": text},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["embedding"]


def ask_json(system, prompt):
    r = requests.post(
        config.OLLAMA_GEN,
        json={
            "model": config.CHAT_MODEL,
            "system": system,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2},
        },
        timeout=600,
    )
    r.raise_for_status()
    raw = r.json()["response"]
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in model response")
    return json.loads(raw[start:end + 1])

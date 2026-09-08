import requests
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from engine import config

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

_api_client = None


def get_api_client():
    global _api_client
    if _api_client is None:
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY not found. Check your .env file.")
        _api_client = OpenAI(base_url=config.API_BASE_URL, api_key=api_key, timeout=config.API_TIMEOUT)
    return _api_client


def embed(text):
    truncated = text[:6000]
    r = requests.post(
        config.OLLAMA_EMB,
        json={"model": config.EMBED_MODEL, "prompt": truncated},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["embedding"]


def _ask_json_local(system, prompt):
    r = requests.post(
        config.OLLAMA_GEN,
        json={
            "model": config.CHAT_MODEL,
            "system": system,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_ctx": config.NUM_CTX,
            },
        },
        timeout=config.REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    raw = r.json()["response"]
    return _extract_json(raw)


def _ask_json_api(system, prompt):
    client = get_api_client()
    completion = client.chat.completions.create(
        model=config.API_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        top_p=0.95,
        max_tokens=32768,
        stream=False,
    )
    raw = completion.choices[0].message.content
    return _extract_json(raw)


def _extract_json(raw):
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in model response")
    return json.loads(raw[start:end + 1])


def ask_json(system, prompt, backend=None):
    if backend is None:
        backend = config.DEFAULT_BACKEND
    if backend == "api":
        return _ask_json_api(system, prompt)
    return _ask_json_local(system, prompt)

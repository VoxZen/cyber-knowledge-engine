import requests
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from engine import config

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

_api_client = None

# Usage of every API call this process made, oldest first. Also appended to config.USAGE_LOG.
usage_records = []


class OutputTruncatedError(RuntimeError):
    """The model stopped at max_tokens. Not a ValueError, so generate_validated does not retry it."""


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
        max_tokens=32768,
        stream=False,
        # deepseek-flash thinks by default, and in thinking mode temperature is silently ignored.
        # top_p is not sent: outside thinking mode deepseek-flash fixes it at 1.0.
        extra_body={"thinking": {"type": "disabled"}},
    )
    record = record_usage(completion)
    if record["finish_reason"] == "length":
        # The JSON is cut off. A retry would cost the same and be cut off again.
        raise OutputTruncatedError(
            f"model output hit max_tokens after {record['completion_tokens']:,} tokens; "
            f"the JSON is incomplete. Not retrying.")
    raw = completion.choices[0].message.content
    return _extract_json(raw)


def record_usage(completion):
    """Keep the token counts of one API call, in memory and as one JSON line in the usage log."""
    def tokens(name):
        return getattr(completion.usage, name, None) or 0

    record = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": completion.model,
        "prompt_cache_hit_tokens": tokens("prompt_cache_hit_tokens"),
        "prompt_cache_miss_tokens": tokens("prompt_cache_miss_tokens"),
        "completion_tokens": tokens("completion_tokens"),
        "finish_reason": completion.choices[0].finish_reason,
    }
    usage_records.append(record)
    with open(config.USAGE_LOG, "a", encoding="utf-8") as log:
        log.write(json.dumps(record) + "\n")
    return record


def usage_summary(records):
    """One line: calls, input tokens (cache hit / miss), output tokens, cost at off-peak prices."""
    hit = sum(r["prompt_cache_hit_tokens"] for r in records)
    miss = sum(r["prompt_cache_miss_tokens"] for r in records)
    out = sum(r["completion_tokens"] for r in records)
    cost = (hit * config.PRICE_CACHE_HIT + miss * config.PRICE_CACHE_MISS
            + out * config.PRICE_OUTPUT) / 1_000_000
    calls = f"{len(records)} call" + ("" if len(records) == 1 else "s")
    return f"{calls}, {hit:,} hit / {miss:,} miss, {out:,} output, ~${cost:.4f}"


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

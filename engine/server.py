import hmac
import os
from flask import Flask, request, jsonify
from engine import config
from engine.main import process

app = Flask(__name__)

# Read after the engine import: llm.py loads .env when it is imported
TOKEN = os.environ.get("CKE_SERVER_TOKEN", "")
LOCAL_ONLY = config.SERVER_HOST in ("127.0.0.1", "localhost", "::1")


def authorized():
    """On localhost no token is needed. Otherwise the request must send the shared token
    as "Authorization: Bearer <token>". With no token configured, nothing is accepted."""
    if LOCAL_ONLY:
        return True
    sent = request.headers.get("Authorization", "").removeprefix("Bearer ")
    return bool(TOKEN) and hmac.compare_digest(sent.encode(), TOKEN.encode())


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/note", methods=["POST"])
def add_note():
    if not authorized():
        return jsonify({"error": "unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()

    if len(text) < 30:
        return jsonify({"error": f"Input too short ({len(text)} chars)"}), 400

    try:
        print(f"\n[note received] {len(text)} characters, processing...")
        slug = process(text)
        from engine import vault
        _, category = vault.find_note(slug)
        print(f"[done] saved as {category}/{slug}.md")
        return jsonify({"status": "ok", "slug": slug, "category": category or "?"})
    except Exception as e:
        print(f"[error] {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print("=" * 50)
    print("Cyber Knowledge Engine server")
    print(f"Listening on {config.SERVER_HOST}, port {config.SERVER_PORT}")
    if not LOCAL_ONLY and not TOKEN:
        print("WARNING: CKE_SERVER_TOKEN is not set in .env, so every /note request is refused (401).")
    print("Keep this window open. Press Ctrl+C to stop.")
    print("=" * 50)
    app.run(host=config.SERVER_HOST, port=config.SERVER_PORT)

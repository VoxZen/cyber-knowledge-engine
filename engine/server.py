from flask import Flask, request, jsonify
from engine.main import process

app = Flask(__name__)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/note", methods=["POST"])
def add_note():
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
    print("Listening on all interfaces, port 8000")
    print("Keep this window open. Press Ctrl+C to stop.")
    print("=" * 50)
    app.run(host="0.0.0.0", port=8000)

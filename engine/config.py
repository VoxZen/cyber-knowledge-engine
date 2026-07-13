from pathlib import Path

VAULT = Path.home() / "Documents" / "CyberKB"
INDEX_FILE = VAULT / ".kb_index.json"

OLLAMA_BASE = "http://localhost:11434"
OLLAMA_GEN = "http://localhost:11434/api/generate"
OLLAMA_EMB = "http://localhost:11434/api/embeddings"

CHAT_MODEL = "qwen3:14b"
EMBED_MODEL = "nomic-embed-text"

CANDIDATE_THRESHOLD = 0.60
MAX_RETRIES = 2


import os
from pathlib import Path

# CKE_VAULT overrides the vault location (per machine, and for the tests)
VAULT = Path(os.environ.get("CKE_VAULT") or Path.home() / "Documents" / "CyberKB").expanduser()
INDEX_FILE = VAULT / ".kb_index.json"

OLLAMA_BASE = "http://localhost:11434"
OLLAMA_GEN = "http://localhost:11434/api/generate"
OLLAMA_EMB = "http://localhost:11434/api/embeddings"

CHAT_MODEL = "qwen3:14b"
EMBED_MODEL = "nomic-embed-text"

CANDIDATE_THRESHOLD = 0.60
MAX_RETRIES = 2
NUM_CTX = 8192
REQUEST_TIMEOUT = 2400

# --- Backend selection ---
# "local" = Ollama (14B, offline), "api" = DeepSeek cloud
DEFAULT_BACKEND = "api"

# --- DeepSeek API settings ---
API_BASE_URL = "https://api.deepseek.com"
API_MODEL = "deepseek-flash"
API_TIMEOUT = 600

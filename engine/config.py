import os
from pathlib import Path

# CKE_VAULT overrides the vault location (per machine, and for the tests)
VAULT = Path(os.environ.get("CKE_VAULT") or Path.home() / "Documents" / "CyberKB").expanduser()
INDEX_FILE = VAULT / ".kb_index.json"

# --- Categories ---
# Folders the classifier may choose (brain.choose_category accepts only these)
CLASSIFIER_CATEGORIES = [
    "00 Inbox", "01 Networking", "02 Linux", "03 Windows", "04 Web",
    "05 Active Directory", "06 Cloud", "07 Programming", "08 Tools", "09 Methodology",
]
# Every top-level folder that holds notes: the classifier's folders plus the ones
# filled by hand or by a mode (kb --writeup writes to 90 Writeups). Other folders are ignored.
VAULT_CATEGORIES = CLASSIFIER_CATEGORIES + ["90 Writeups", "91 Templates", "99 Archive"]

OLLAMA_BASE = "http://localhost:11434"
OLLAMA_GEN = "http://localhost:11434/api/generate"
OLLAMA_EMB = "http://localhost:11434/api/embeddings"

CHAT_MODEL = "qwen3:14b"
EMBED_MODEL = "qwen3-embedding:8b"

CANDIDATE_THRESHOLD = 0.62
MAX_RETRIES = 2
NUM_CTX = 8192
REQUEST_TIMEOUT = 2400

# --- Backend selection ---
# "local" = Ollama (14B, offline), "api" = DeepSeek cloud
DEFAULT_BACKEND = "api"

# --- Server (engine/server.py) ---
# "127.0.0.1" = this machine only. "0.0.0.0" accepts requests from the network;
# then every /note request must carry CKE_SERVER_TOKEN (set in .env).
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8000

# --- DeepSeek API settings ---
API_BASE_URL = "https://api.deepseek.com"
API_MODEL = "deepseek-flash"
API_TIMEOUT = 600
# Every API call is appended here as one JSON line (gitignored)
USAGE_LOG = Path(__file__).resolve().parent.parent / "usage.log"
# deepseek-flash prices in USD per 1M tokens, off-peak. Peak hours
# (01:00-04:00 and 06:00-10:00 UTC, Monday to Friday) cost twice as much.
PRICE_CACHE_HIT = 0.003
PRICE_CACHE_MISS = 0.15
PRICE_OUTPUT = 0.6

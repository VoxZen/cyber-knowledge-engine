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
NUM_CTX = 8192
REQUEST_TIMEOUT = 2400

# --- Backend selection ---
# "local" = Ollama (14B, offline), "api" = NVIDIA cloud (DeepSeek)
DEFAULT_BACKEND = "api"

# --- NVIDIA API settings ---
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
API_MODEL = "deepseek-ai/deepseek-v4-flash"
API_NUM_CTX = 131072
API_TIMEOUT = 600

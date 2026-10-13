# Cyber Knowledge Engine

A self-hosted, AI-powered pipeline that turns raw cybersecurity learning material — Hack The Box modules, lab writeups, and technical notes — into a clean, atomic, well-organized personal knowledge base in Obsidian.

Instead of accumulating dozens of messy, overlapping files, the engine reads source material, decides how it should be split into focused notes (with the user confirming), and writes each note as a professional reference page. It is designed to be a long-lived "second brain" for offensive security study.

## Motivation

Cybersecurity is a vast field, and no one can hold every command, technique, and tool in memory. Most learners end up with fragmented notes (`SQLi.md`, `SQL Injection final.md`, `SQLi notes 2.md`) that become impossible to search six months later.

This project solves that by enforcing two principles:

- **One topic = one atomic note.** Each tool, technique, or concept gets its own focused page, so future lookup is fast and precise.
- **The human decides the structure; the AI does the writing.** Grouping is a subjective judgment, so the tool proposes an atomic split and the user approves or adjusts it, rather than letting the model guess.

## Architecture

The system runs across two machines on a local network, with the knowledge base stored locally in Obsidian.

```text
┌──────────────────┐         ┌──────────────────────┐         ┌─────────────────┐
│   Client (M1)    │  HTTP   │     Server (M4)      │  files  │    Obsidian     │
│  paste notes /   ├────────►│  Python engine +     ├────────►│  vault, sorted  │
│  send via CLI    │         │  LLM backends        │         │  by category    │
└──────────────────┘         └──────────────────────┘         └─────────────────┘
```

The engine, the vault and the `kb` command live on the server machine. The HTTP path from the client goes through `engine/server.py`, a small server that only creates plain notes (no `--split` or `--writeup`). It listens on `127.0.0.1` by default; see [Optional: HTTP server](#optional-http-server) to accept requests from the network.

## Tech stack

| Component | Role |
|---|---|
| Python | Core engine (parsing, orchestration, validation) |
| DeepSeek V4 (via API, model `deepseek-flash`) | Primary model — 128K context, strong at long technical text |
| Ollama + Qwen 14B (`qwen3:14b`) | Local fallback model for offline use |
| Ollama + `nomic-embed-text` | Embeddings for finding similar notes — required by every mode except `--delete` |
| Obsidian | Knowledge base (local, category-organized Markdown) |
| Pydantic | Schema validation with automatic retry on malformed output |
| Flask | Optional HTTP endpoint (`engine/server.py`) |

## Setup

You need Python 3.11 or newer (developed on 3.14), [Ollama](https://ollama.com), and a DeepSeek API key.

**1. Clone and install.** The `kb` launcher runs `cd ~/cke`, so clone to `~/cke` (or edit the script).

```bash
git clone https://github.com/VoxZen/cyber-knowledge-engine.git ~/cke
cd ~/cke
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**2. Install Ollama and pull the models.**

```bash
ollama pull nomic-embed-text   # embeddings: required by every mode except --delete
ollama pull qwen3:14b          # chat model: only needed for kb --local
```

**3. Create `.env`** in the project root (it is gitignored):

```bash
echo 'DEEPSEEK_API_KEY=your-key-here' > .env
```

**4. Choose the vault.** The default is `~/Documents/CyberKB`. To use another folder, set `CKE_VAULT` in your shell, for example in `~/.zshrc`. It must be a real environment variable; it is not read from `.env`.

```bash
export CKE_VAULT="$HOME/path/to/your/vault"
```

**5. Add the `kb` alias** to `~/.zshrc`:

```bash
alias kb="$HOME/cke/kb"
```

`kb` is a four-line script: it changes to `~/cke`, activates the virtual environment and runs `python3 -m engine.cli` with your arguments.

To write a long note in an editor first, save it to a file and pass the path with `--file`. This works with `--split`, `--writeup` and `--merge` too:

```bash
kb --split --file ~/Desktop/module.md
```

### Optional: HTTP server

```bash
python -m engine.server      # listens on 127.0.0.1:8000
```

To accept requests from other machines, set `SERVER_HOST = "0.0.0.0"` in `engine/config.py` and add `CKE_SERVER_TOKEN=<long random string>` to `.env`. Every `POST /note` must then send `Authorization: Bearer <token>`, or it gets `401`. If the server runs under launchd with its output written to `server.log`, rotate the log by hand: stop the agent, move the file, start the agent again.

## How It Works

Material is sent to the engine from the command line. Depending on the type of source, a different mode is used. Every mode except `--delete` first checks that Ollama is running and has the embedding model, so nothing is written if it is not.

### `kb --split` — Academy modules → atomic notes

Given a block of course material (one or more sections), the engine:

1. Asks the model to propose an atomic split — one note per tool, technique, or concept.
2. Shows the proposed notes to the user, who can approve, merge, or drop any of them. A title that is already a note in the vault is marked `[exists: <category>]`.
3. Writes each confirmed note as a focused reference page and files it under the correct category. A note that already exists is skipped, never overwritten, and listed at the end.

A single reconnaissance module, for example, becomes ~40–50 clean atomic notes (`dig.md`, `gobuster.md`, `subdomain-enumeration.md`, …) instead of one giant unreadable file.

### `kb --writeup` — machine solutions → writeups

Lab writeups follow a different philosophy. Here the engine does not add general theory or expand the topic, because every machine is unique. It documents only what was done to solve this box, in order, producing three sections:

- **Overview** — platform, difficulty, main techniques
- **Solution Walkthrough** — the step-by-step path from recon to root
- **Key Takeaways** — concrete, reusable recognition patterns from this specific box

### Other modes

| Command | Purpose |
|---|---|
| `kb` | Create a single new note. If a note with the same filename already exists, nothing is written and `kb --merge` is suggested |
| `kb --merge` | Merge new information into an existing note. Similar notes are found by embedding similarity (cosine ≥ 0.60) and the user selects the target; if the merged title would rename the file, the user is asked first |
| `kb --delete` | List and delete a note (keeps the search index in sync) |
| `kb --reindex` | Report where the search index and the files on disk disagree; repair the index only after you type `yes` |
| `kb --local` | Use the local 14B model instead of the API (offline) |
| `kb --file <path>` | Read the note text from a file instead of pasting it |

Without text or `--file`, `kb` asks you to paste the note and press Ctrl+D. The default backend is `DEFAULT_BACKEND` in `engine/config.py`.

### Tests

```bash
cd ~/cke && source venv/bin/activate
python -m unittest discover -s tests -v
```

The suite runs against a temporary vault and never calls a model. One extra check reads your real vault, read-only, when you point `CKE_VAULT` at it:

```bash
CKE_VAULT=~/Documents/CyberKB python -m unittest discover -s tests -v
```

## Design Decisions

A few deliberate choices shaped the project:

- **"Most capable" is not "most suitable."** DeepSeek V4 was chosen over larger models because the task is long-text structuring, where context window and speed matter more than raw reasoning power.
- **Two opposite AI philosophies for two kinds of source.** Academy notes use responsible enrichment (the model may add accurate, relevant detail to teach more fully). Writeups use strict fidelity (no additions — only what solved that machine), so writeups stay specific and never blur together.
- **Backend switching.** The same prompts and validation run against either the cloud API or the local model, so the system keeps working offline and can move to fully local inference in the future.
- **Validation with retry.** Model output (notes and `--split` plans) is validated against a schema; a malformed response is sent back to the model with the validation error and retried, up to two times, keeping the pipeline robust.
- **Never lose a note.** Creating a note never replaces an existing one (`kb` stops, `--split` skips it). A merge writes the merged note before it removes anything, a merge that would rename a file asks first, and the search index is only updated after the note file is written.

## Knowledge Base Structure

Notes are organized into numbered category folders so Obsidian keeps them ordered:

```text
00 Inbox          05 Active Directory   90 Writeups
01 Networking     06 Cloud              91 Templates
02 Linux          07 Programming        99 Archive
03 Windows        08 Tools
04 Web            09 Methodology
```

The folder list lives in one place, `engine/config.py`. The classifier only chooses from `00`–`09`; `90 Writeups` is filled by `kb --writeup`. Any other folder in the vault is ignored by the engine.

Each note is plain Markdown: a `# Title`, a one-line summary, then `## Section` blocks. The search index, `.kb_index.json` in the vault root, stores one 768-dimensional embedding per note, keyed by the note's filename.

The finished notes integrate with an Obsidian AI plugin, which lets the knowledge base be studied back in a tutor/student format — turning the collected notes into an active learning loop.

## Status

The engine is functional end-to-end: multi-mode note creation, atomic splitting with human confirmation, writeup mode, merging, deletion, index repair, and local/cloud backend switching all work. The HTTP server supports plain note creation only. Ongoing work includes extending the full pipeline to the networked client and refining how repeated tools across writeups are handled.

## About

I built this as a third-year IT student focused on cybersecurity, both to support my own Hack The Box study and to have a real, self-directed engineering project. It sits at the intersection of three things I care about: building software systems (Python, APIs, multi-machine architecture), learning offensive security, and taking the initiative to build my own tools rather than rely on existing ones.

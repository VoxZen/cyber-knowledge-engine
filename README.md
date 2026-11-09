# Cyber Knowledge Engine

A self-hosted, AI-powered pipeline that turns cybersecurity learning material (course modules, technical documentation, lab writeups and personal notes) into a clean, atomic, well-organized personal knowledge base in Obsidian.

Instead of accumulating dozens of messy, overlapping files, the engine reads source material, decides how it should be split into focused notes (with the user confirming), and writes each note as a professional reference page. It is designed to be a long-lived "second brain" for offensive security study.

## Motivation

Cybersecurity is a vast field, and no one can hold every command, technique, and tool in memory. Most learners end up with fragmented notes (`SQLi.md`, `SQL Injection final.md`, `SQLi notes 2.md`) that become impossible to search six months later.

This project solves that by enforcing two principles:

- **One topic = one atomic note.** Each tool, technique, or concept gets its own focused page, so future lookup is fast and precise.
- **The human decides the structure; the AI does the writing.** Grouping is a subjective judgment, so the tool proposes an atomic split and the user approves or adjusts it, rather than letting the model guess.

## Architecture

The system is designed to run across two machines on a local network, with the knowledge base stored locally in Obsidian.

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
| DeepSeek-V4.1-Flash (via API, model `deepseek-flash`) | Primary model — 1M context, up to 384K output tokens, strong at long technical text |
| Ollama + Qwen 14B (`qwen3:14b`) | Local fallback model for offline use |
| Ollama + `qwen3-embedding:8b` | Embeddings for finding similar notes — required by every mode except `--delete`, `--organize` and `--taxonomy` |
| Obsidian | Knowledge base (local, category-organized Markdown) |
| Pydantic | Schema validation with automatic retry on malformed output |
| Flask | Optional HTTP endpoint (`engine/server.py`) |

## Setup

Developed and tested on Python 3.14; the test suite also passes on Python 3.12. You also need [Ollama](https://ollama.com) and a DeepSeek API key.

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
ollama pull qwen3-embedding:8b # embeddings (~5 GB): required by every mode except --delete
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

Material is sent to the engine from the command line. Depending on the type of source, a different mode is used. Every mode except `--delete`, `--organize` and `--taxonomy` first checks that Ollama is running and has the embedding model, so nothing is written if it is not.

### `kb --split` — course material → atomic notes

Given a block of course material (one or more sections), the engine:

1. Asks the model to propose an atomic split — one note per tool, technique, or concept.
2. Shows the proposed notes to the user, who can approve, merge, or drop any of them. A title that is already a note in the vault is marked `[exists: <category>]`; otherwise the most similar existing note, if any, is shown next to it (`≈ hashcat (0.83, 08 Tools)`). Nothing is merged or dropped automatically.
3. Writes each confirmed note as a focused reference page and files it under the correct category. A note that already exists is skipped, never overwritten, and listed at the end.
4. Prints the API usage of the run: calls, input tokens (cache hit / miss), output tokens and an estimated cost. Every API call is also appended to `usage.log` as one JSON line.
5. Appends one line to the split journal, `.kb_split_log.jsonl` in the vault: the time, the module (the name of the `--file`, or none for pasted text), and the notes created and skipped. `kb --organize` reads each note's module from it.

New notes are written to `Category/<slug>.md` without frontmatter; `--split` never assigns a topic. Topics and topic folders come afterwards, from `kb --organize`.

A long document becomes a set of focused notes instead of one giant unreadable file. In the open-licensed evaluation corpus (see [Evaluation](#evaluation)), 73 documents produced 722 atomic notes.

### `kb --writeup` — machine solutions → writeups

Lab writeups follow a different philosophy. Here the engine does not add general theory or expand the topic, because every machine is unique. It documents only what was done to solve this box, in order, producing three sections:

- **Overview** — platform, difficulty, main techniques
- **Solution Walkthrough** — the step-by-step path from recon to root
- **Key Takeaways** — concrete, reusable recognition patterns from this specific box

### Other modes

| Command | Purpose |
|---|---|
| `kb` | Create a single new note. If a note with the same filename already exists, nothing is written and `kb --merge` is suggested |
| `kb --merge` | Merge new information into an existing note. Similar notes are found by embedding similarity (cosine ≥ 0.62) and the user selects the target; if the merged title would rename the file, the user is asked first |
| `kb --delete` | List and delete a note (keeps the search index in sync) |
| `kb --reindex` | Report where the search index and the files on disk disagree; repair the index only after you type `yes` |
| `kb --reembed` | Recompute every vector in the search index with the current `EMBED_MODEL` (needed once after changing it); backs up the old index first and asks for `yes` |
| `kb --organize` | Give every note in `01`–`09` a topic and a type, and move it to its topic folder (see [Knowledge Base Structure](#knowledge-base-structure)). Builds a plan, prints it and applies it after `yes` |
| `kb --organize --dry-run [--plan-out FILE]` | Build and print the plan, optionally save it; change nothing |
| `kb --organize --apply FILE` | Apply a saved plan (no model calls). Refused if notes were added, removed or moved since the plan was built |
| `--yes`, `--set-source WORD` | With `--organize`: apply without asking and skip manual moves; set `source` on notes that have none |
| `kb --taxonomy` | Read-only report: topics per category with note counts, folders and definitions; flags topics over 40 notes, `General` over 25% of a category, and notes without a topic or not in their folder |
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
- **Two opposite AI philosophies for two kinds of source.** Reference notes (`kb` and `--split`) use responsible enrichment (the model may add accurate, relevant detail to teach more fully). Writeups use strict fidelity (no additions — only what solved that machine), so writeups stay specific and never blur together.
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

Each note is plain Markdown: a `# Title`, a one-line summary, then `## Section` blocks. After `kb --organize` it also has a frontmatter block with four keys that CKE owns; other properties added in Obsidian are kept:

```yaml
---
topic: "SQL Injection"
type: technique        # concept, technique, defense, tool, process or reference
module: "SQL Injection Fundamentals"
source: htb
---
```

A note is identified by its filename, not its location. The top-level folder is its category; the frontmatter is the truth for topic and type, and topic subfolders are derived from it: a topic with 5 or more notes gets `Category/<Topic>/`, smaller topics share `Category/Other/`, and a category where no topic reaches 5 notes has no subfolders. The topics of each category are kept in `.kb_taxonomy.json` in the vault, with a one-sentence definition and aliases. To rename a topic, change its `name` and add the old name to `aliases`; to merge topic B into A, delete B and add `"B"` to A's aliases; then run `kb --organize`. A note moved by hand in Obsidian to another topic folder is detected, and `kb --organize` asks whether the folder or the metadata wins. The frontmatter never reaches the model or the search index.

The search index, `.kb_index.json` in the vault root, stores one embedding per note (4096 numbers with `qwen3-embedding:8b`), keyed by the note's filename. Vectors from different embedding models cannot be compared, so after changing `EMBED_MODEL` run `kb --reembed` once.

The finished notes integrate with an Obsidian AI plugin, which lets the knowledge base be studied back in a tutor/student format — turning the collected notes into an active learning loop.

## Evaluation

A human-labelled evaluation of the engine is in progress. CKE was run, unchanged, on 73 openly licensed documents (Wikipedia, OWASP Cheat Sheet Series, OWASP Web Security Testing Guide, PayloadsAllTheThings, Nmap Reference Guide and Microsoft documentation), producing 722 notes. Pairs of these notes are labelled *same*, *related* or *different* by human annotators, to measure how well embedding similarity and the 0.62 candidate threshold match human judgement across four local embedding models. Because enrichment can add content that is not in the source, a sample of notes is also checked against its source documents. The corpus, labels and analysis scripts will be published with the results.

## Status

The engine is functional end-to-end: multi-mode note creation, atomic splitting with human confirmation, writeup mode, merging, deletion, index repair, re-embedding with a new model, and local/cloud backend switching all work. Organisation (topics, types, topic folders, `kb --taxonomy`) is a separate step after splitting. `scripts/coverage.py` writes a one-page HTML overview of a vault: a map of categories and topics sized by note count, and a topic table that flags thin, large and weakly linked topics (`python scripts/coverage.py --lang en|az`; default output `<vault>/.kb_coverage.html`). The HTTP server supports plain note creation only. Ongoing work includes extending the full pipeline to the networked client and refining how repeated tools across writeups are handled.

## About

I built this as a third-year IT student focused on cybersecurity, both to support my own cybersecurity study and to have a real, self-directed engineering project. It sits at the intersection of three things I care about: building software systems (Python, APIs, multi-machine architecture), learning offensive security, and taking the initiative to build my own tools rather than rely on existing ones.

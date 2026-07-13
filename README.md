# Cyber Knowledge Engine

A self-hosted engine that turns messy cybersecurity notes into a clean, non-duplicated personal encyclopedia — powered entirely by a local LLM, running fully offline.

Feed it raw text from anywhere: Hack The Box, PortSwigger, documentation, your own research. It figures out the topic, finds any existing note on that topic, and **enriches it instead of creating a duplicate**. Over time you get one canonical, professional reference note per topic — not a graveyard of `nmap-1.md`, `nmap-notes.md`, `nmap-final.md`.

## The Core Idea

Most note systems fail the same way: the same topic ends up scattered across a dozen files written at different times. This engine is built around a single rule — **one topic, one note** — and everything in the pipeline exists to enforce it.

## Pipeline

Every incoming note passes through six stages:

1. **Search** — an embedding model finds semantically similar existing notes. Pure math, no LLM, so it's fast and deterministic.
2. **Decide** — the LLM judges whether the new text is the *same topic* as a candidate, or genuinely *different*. This catches cases where two topics look similar to an embedding model but shouldn't be merged (e.g. Nmap vs Gobuster — both recon, different tools).
3. **Structure** — the LLM rewrites raw text into a structured note. It preserves methodology, commands, and reasoning, but replaces one-time lab values (uuids, flags, target IPs) with placeholders like `<target_ip>` — because those values are never reused, but the *method* is.
4. **Merge** — when the topic already exists, the new structured note is merged into the old one. Done in two steps (structure first, then merge two clean notes) to stop the model from garbling details.
5. **Validate** — the LLM's output is checked against a strict schema. If it's malformed, it's rejected and regenerated. Bad output is never silently written to the vault.
6. **Categorize** — the note is filed into the right topic folder automatically. If the model isn't confident, it goes to an inbox instead of being misfiled.

## Design Principles

- **The LLM proposes, the system decides.** Every model output is validated. Nothing reaches the vault unchecked.
- **Methodology over lab values.** A note should teach you *how* an attack works years later, not what one throwaway uuid was.
- **Fully local.** Everything runs through Ollama on your own hardware. No note ever leaves the machine.
- **Modular by design.** Each module has one job, so swapping the model, changing the storage format, or adjusting the logic each touches exactly one file.

## Architecture

The engine is split so that each concern lives in one place:

| Module | Responsibility |
|--------|----------------|
| `config` | Central settings — model names, paths, thresholds |
| `schema` | The note structure and its validation rules |
| `llm` | Every call to the local model. Swap models here and nowhere else. |
| `vault` | Reading and writing notes on disk |
| `memory` | The embedding index and similarity search |
| `brain` | Decision logic, prompts, and category selection |
| `main` | The orchestrator that runs the pipeline |
| `server` | Receives notes over the network so any device can send to it |

## Setup

Requires Python and [Ollama](https://ollama.com/) with a chat model and an embedding model.

```bash
ollama pull qwen3:14b
ollama pull nomic-embed-text
pip install flask requests pydantic pyyaml
python3 -m engine.server
```

Set your vault path in `config`, start the server, and send notes to it from any machine on the network.

## Vault Layout

Notes are filed by topic into numbered folders (`01 Networking`, `04 Web`, `05 Active Directory`, `08 Tools`, and so on), with a `00 Inbox` for anything uncertain and a `90 Writeups` for raw box notes that aren't encyclopedia material.

## Status

Working, and actively used for real note-taking. Planned next: semantic search across the vault, knowledge-gap detection, and remote access over VPN.

Cyber Knowledge Engine

A self-hosted, AI-powered pipeline that turns raw cybersecurity learning material — Hack The Box modules, lab writeups, and technical notes — into a clean, atomic, well-organized personal knowledge base in Obsidian.

Instead of accumulating dozens of messy, overlapping files, the engine reads source material, decides how it should be split into focused notes (with the user confirming), and writes each note as a professional reference page. It is designed to be a long-lived "second brain" for offensive security study.

Motivation

Cybersecurity is a vast field, and no one can hold every command, technique, and tool in memory. Most learners end up with fragmented notes (SQLi.md, SQL Injection final.md, SQLi notes 2.md) that become impossible to search six months later.

This project solves that by enforcing two principles:

One topic = one atomic note. Each tool, technique, or concept gets its own focused page, so future lookup is fast and precise.
The human decides the structure; the AI does the writing. Grouping is a subjective judgment, so the tool proposes an atomic split and the user approves or adjusts it, rather than letting the model guess.
Architecture

The system runs across two machines on a local network, with the knowledge base stored locally in Obsidian.

┌──────────────────┐         ┌──────────────────────┐         ┌─────────────────┐
│   Client (M1)    │  HTTP   │     Server (M4)      │  files  │    Obsidian     │
│  paste notes /   ├────────►│  Python engine +     ├────────►│  vault, sorted  │
│  send via CLI    │         │  LLM backends        │         │  by category    │
└──────────────────┘         └──────────────────────┘         └─────────────────┘

Tech stack

Component	Role
Python	Core engine (parsing, orchestration, validation)
DeepSeek V4 (via API)	Primary model — 128K context, strong at long technical text
Ollama + Qwen 14B	Local fallback model for offline use
Obsidian	Knowledge base (local, category-organized Markdown)
Pydantic	Schema validation with automatic retry on malformed output
How It Works

Material is sent to the engine from the command line. Depending on the type of source, a different mode is used.

kb --split — Academy modules → atomic notes

Given a block of course material (one or more sections), the engine:

Asks the model to propose an atomic split — one note per tool, technique, or concept.
Shows the proposed notes to the user, who can approve, merge, or drop any of them.
Writes each confirmed note as a focused reference page and files it under the correct category.

A single reconnaissance module, for example, becomes ~40–50 clean atomic notes (dig.md, gobuster.md, subdomain-enumeration.md, …) instead of one giant unreadable file.

kb --writeup — machine solutions → writeups

Lab writeups follow a different philosophy. Here the engine does not add general theory or expand the topic, because every machine is unique. It documents only what was done to solve this box, in order, producing three sections:

Overview — platform, difficulty, main techniques
Solution Walkthrough — the step-by-step path from recon to root
Key Takeaways — concrete, reusable recognition patterns from this specific box
Other modes
Command	Purpose
kb	Create a single new note
kb --merge	Merge new information into an existing note (user selects the target)
kb --delete	List and delete a note (keeps the search index in sync)
kb --local	Use the local 14B model instead of the API (offline)
Design Decisions

A few deliberate choices shaped the project:

"Most capable" is not "most suitable." DeepSeek V4 was chosen over larger models because the task is long-text structuring, where context window and speed matter more than raw reasoning power.
Two opposite AI philosophies for two kinds of source. Academy notes use responsible enrichment (the model may add accurate, relevant detail to teach more fully). Writeups use strict fidelity (no additions — only what solved that machine), so writeups stay specific and never blur together.
Backend switching. The same prompts and validation run against either the cloud API or the local model, so the system keeps working offline and can move to fully local inference in the future.
Validation with retry. Model output is validated against a schema; malformed responses are automatically corrected on retry, keeping the pipeline robust.
Knowledge Base Structure

Notes are organized into numbered category folders so Obsidian keeps them ordered:

00 Inbox          05 Active Directory   90 Writeups
01 Networking     06 Cloud              91 Templates
02 Linux          07 Programming        99 Archive
03 Windows        08 Tools
04 Web            09 Methodology

The finished notes integrate with an Obsidian AI plugin, which lets the knowledge base be studied back in a tutor/student format — turning the collected notes into an active learning loop.

Status

The engine is functional end-to-end: multi-mode note creation, atomic splitting with human confirmation, writeup mode, merging, deletion, and local/cloud backend switching all work. Ongoing work includes extending the full pipeline to the networked client and refining how repeated tools across writeups are handled.

About

I built this as a third-year IT student focused on cybersecurity, both to support my own Hack The Box study and to have a real, self-directed engineering project. It sits at the intersection of three things I care about: building software systems (Python, APIs, multi-machine architecture), learning offensive security, and taking the initiative to build my own tools rather than rely on existing ones.

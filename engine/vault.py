from engine import config


def note_path(slug, category):
    return config.VAULT / category / f"{slug}.md"


def find_note(slug):
    for category_dir in config.VAULT.iterdir():
        if category_dir.is_dir():
            candidate = category_dir / f"{slug}.md"
            if candidate.exists():
                return candidate, category_dir.name
    return None, None


def note_exists(slug):
    path, _ = find_note(slug)
    return path is not None


def read_note(slug):
    path, _ = find_note(slug)
    if path is None:
        return ""
    return path.read_text(encoding="utf-8")


def write_note(slug, category, markdown):
    category_path = config.VAULT / category
    category_path.mkdir(parents=True, exist_ok=True)
    (category_path / f"{slug}.md").write_text(markdown, encoding="utf-8")


def delete_note(slug):
    path, _ = find_note(slug)
    if path is not None:
        path.unlink()


def slugify(title):
    import re
    text = title.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s-]+", "-", text)
    text = text.strip("-")
    words = text.split("-")
    if len(words) > 8:
        words = words[:8]
    return "-".join(words)


def to_markdown(note):
    lines = [f"# {note.title}", "", note.summary, ""]
    for section in note.sections:
        lines.append(f"## {section.heading}")
        lines.append("")
        lines.append(section.content)
        lines.append("")
    return "\n".join(lines)


def markdown_to_json(markdown):
    lines = markdown.split("\n")
    data = {"title": "", "summary": "", "sections": []}
    current = None
    summary_lines = []
    for line in lines:
        if line.startswith("# "):
            data["title"] = line[2:].strip()
        elif line.startswith("## "):
            if current:
                current["content"] = current["content"].strip()
                data["sections"].append(current)
            current = {"heading": line[3:].strip(), "content": ""}
        elif current is not None:
            current["content"] += line + "\n"
        elif line.strip() and not data["summary"]:
            summary_lines.append(line.strip())
    if current:
        current["content"] = current["content"].strip()
        data["sections"].append(current)
    data["summary"] = " ".join(summary_lines)
    return data

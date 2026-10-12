from engine import config


def category_dirs():
    """Existing top-level category folders, in config order. Other folders hold no notes."""
    return [config.VAULT / name for name in config.VAULT_CATEGORIES if (config.VAULT / name).is_dir()]


def check_layout():
    """Return (missing, nested): classifier categories with no top-level folder, and
    category folders found inside another category, e.g. "03 Windows/02 Linux"."""
    missing = [name for name in config.CLASSIFIER_CATEGORIES if not (config.VAULT / name).is_dir()]
    nested = []
    for category_dir in category_dirs():
        for child in sorted(category_dir.iterdir()):
            if child.is_dir() and child.name in config.VAULT_CATEGORIES:
                nested.append(f"{category_dir.name}/{child.name}")
    return missing, nested


def find_note(slug):
    matches = []
    for category_dir in category_dirs():
        candidate = category_dir / f"{slug}.md"
        if candidate.exists():
            matches.append(candidate)
    if len(matches) > 1:
        folders = ", ".join(path.parent.name for path in matches)
        raise RuntimeError(f"Note '{slug}' exists in more than one category ({folders}). "
                           f"Keep one file and remove the others.")
    if not matches:
        return None, None
    return matches[0], matches[0].parent.name


def read_note(slug):
    path, _ = find_note(slug)
    if path is None:
        return ""
    return path.read_text(encoding="utf-8")


def write_note(slug, category, markdown):
    old_path, old_category = find_note(slug)
    category_path = config.VAULT / category
    category_path.mkdir(parents=True, exist_ok=True)
    (category_path / f"{slug}.md").write_text(markdown, encoding="utf-8")
    # One slug, one file: if the note was in another category, it has now moved here
    if old_category is not None and old_category != category:
        old_path.unlink()


def delete_note(slug):
    path, _ = find_note(slug)
    if path is not None:
        path.unlink()


def slugify(title, fallback=True):
    import hashlib
    import re
    text = title.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s-]+", "-", text)
    text = text.strip("-")
    words = text.split("-")
    if len(words) > 8:
        words = words[:8]
    slug = "-".join(words)
    if not slug and fallback:
        # Nothing usable left (e.g. "日本語" or "!!!"). Derive a stable name from the title,
        # so the same title always maps to the same file and the name can be traced back.
        slug = "untitled-" + hashlib.sha256(title.encode("utf-8")).hexdigest()[:8]
    return slug


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
    fence = None  # "```" or "~~~" while inside a fenced code block
    for line in lines:
        marker = line.lstrip()[:3]
        if fence:
            # Inside a code block every line is content; only the same marker closes it
            if marker == fence:
                fence = None
        elif marker in ("```", "~~~"):
            fence = marker
        elif line.startswith("# ") and not data["title"]:
            # Only the first level-1 heading is the title; a later "# " is content
            data["title"] = line[2:].strip()
            continue
        elif line.startswith("## "):
            if current:
                current["content"] = current["content"].strip()
                data["sections"].append(current)
            current = {"heading": line[3:].strip(), "content": ""}
            continue
        if current is not None:
            current["content"] += line + "\n"
        elif line.strip() and not data["summary"]:
            summary_lines.append(line.strip())
    if current:
        current["content"] = current["content"].strip()
        data["sections"].append(current)
    data["summary"] = " ".join(summary_lines)
    return data

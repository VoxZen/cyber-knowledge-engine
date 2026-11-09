from pathlib import Path

from engine import config, meta


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


class NoteExistsError(RuntimeError):
    """A write would replace a note that is already in the vault."""

    def __init__(self, slug, category, path=None):
        super().__init__(f"Note '{slug}' already exists in {category}. Nothing was written.")
        self.slug = slug
        self.category = category
        # Where the existing note is, relative to the vault (it may sit in a topic subfolder)
        self.path = path or f"{category}/{slug}.md"


def iter_note_files():
    """(slug, category, path) for every note, sorted by path within each category.

    A note is identified by its file name, not its location: it may sit anywhere under its
    top-level category folder (normally in a topic subfolder made by kb --organize). The
    category is always the top-level folder. Hidden folders are skipped.
    """
    for category_dir in category_dirs():
        for path in sorted(category_dir.rglob("*.md")):
            relative = path.relative_to(category_dir)
            if any(part.startswith(".") for part in relative.parts):
                continue
            yield path.stem, category_dir.name, path


def note_paths():
    """{slug: [paths]} from a folder scan. More than one path means a duplicate slug.

    Unlike find_note this never raises on a duplicate, so callers can still report it.
    """
    paths = {}
    for slug, _, path in iter_note_files():
        paths.setdefault(slug, []).append(path)
    return paths


def relative(path):
    return path.relative_to(config.VAULT).as_posix()


def category_of(path):
    """The category of a note file: the top-level folder it sits under."""
    return path.relative_to(config.VAULT).parts[0]


def find_note(slug):
    matches = note_paths().get(slug, [])
    if len(matches) > 1:
        folders = ", ".join(relative(path.parent) for path in matches)
        raise RuntimeError(f"Note '{slug}' exists in more than one place ({folders}). "
                           f"Keep one file and remove the others.")
    if not matches:
        return None, None
    return matches[0], category_of(matches[0])


def read_note(slug):
    path, _ = find_note(slug)
    if path is None:
        return ""
    return path.read_text(encoding="utf-8")


def ensure_new(slug):
    """Raise NoteExistsError if a note with this slug is already in the vault."""
    path, category = find_note(slug)
    if category is not None:
        raise NoteExistsError(slug, category, relative(path))


def write_note(slug, category, markdown, replace=False, folder=None):
    """Write a note. A new note goes to Category/<slug>.md.

    A note that replaces itself in the same category (a merge) is rewritten where it is,
    so a note in a topic subfolder stays there. `folder` puts the file in another folder
    of the same category (a merge that renames the note keeps the old note's folder).
    """
    old_path, old_category = find_note(slug)
    # Only a merge, which has read the old note into the new text, may replace it. Any other
    # write would lose the old text: overwritten in the same folder, removed from another one.
    if old_path is not None and not replace:
        raise NoteExistsError(slug, old_category, relative(old_path))
    category_path = config.VAULT / category
    if old_path is not None and old_category == category:
        target_dir = old_path.parent
    elif folder is not None and Path(folder).resolve().is_relative_to(category_path.resolve()):
        target_dir = Path(folder)
    else:
        target_dir = category_path
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / f"{slug}.md").write_text(markdown, encoding="utf-8")
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
    # The frontmatter block (topic, type, ...) is metadata, not note text: it must never
    # reach the summary, and through it the embedding or a merge prompt
    _, markdown = meta.split(markdown)
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

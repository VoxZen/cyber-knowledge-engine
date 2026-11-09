import shutil
from datetime import datetime

from engine import config, memory, meta, vault, brain


def save_note(slug, category, note, replace=False, block="", folder=None):
    # 1) embedding (network: Ollama may be down)  2) note file  3) index entry.
    # If the network step fails nothing is written; the two disk writes happen side by side.
    # A new note has no frontmatter block; a merge passes the old note's block and folder.
    entry = memory.embed_entry(note.title, note.summary, category)
    vault.write_note(slug, category, block + vault.to_markdown(note), replace=replace, folder=folder)
    memory.save_entry(slug, entry)


def process(text, backend=None):
    print("Creating new note...")
    note = brain.create_note(text, backend=backend)
    slug = vault.slugify(note.title)
    # Creating never replaces a note (that is what --merge is for). Stop before the category call.
    vault.ensure_new(slug)

    print("Choosing category...")
    category = brain.choose_category(note.title, note.summary, backend=backend)
    print(f"Category: {category}")

    save_note(slug, category, note)

    print(f"create: {category}/{slug}.md")
    return slug


def find_merge_candidates(text):
    return memory.find_top_matches(text, limit=5)


def merge_into(text, target_slug, backend=None, confirm_rename=None):
    existing_md = vault.read_note(target_slug)
    if not existing_md:
        raise RuntimeError(f"Note '{target_slug}' not found")
    # markdown_to_json leaves the frontmatter out, so the model never sees it;
    # the block is put back unchanged on the merged note
    existing_json = vault.markdown_to_json(existing_md)
    block, _ = meta.split(existing_md)
    existing_path, existing_category = vault.find_note(target_slug)

    print("Step 1/2: structuring new text...")
    new_note = brain.create_note(text, backend=backend)
    print("Step 2/2: merging into existing note...")
    merged = brain.merge_two_notes(existing_json, new_note.model_dump(), backend=backend)

    # fallback=False: an unusable title must stop the merge, not rename the note to untitled-...
    new_slug = vault.slugify(merged.title, fallback=False)
    if not new_slug:
        raise RuntimeError(f"Merged title '{merged.title}' gives an empty filename. Nothing was changed.")
    # A new slug means the old file will be removed, so only rename when the user said yes.
    # Without a confirm_rename callback (server, piped input) the filename stays the same.
    # A filename that another note already uses is never offered: that note would be replaced.
    if new_slug != target_slug:
        _, taken_by = vault.find_note(new_slug)
        if taken_by is not None:
            print(f"Title changed to '{merged.title}', but {taken_by}/{new_slug}.md is another note; "
                  f"keeping the filename {target_slug}.md")
            new_slug = target_slug
        elif not (confirm_rename and confirm_rename(target_slug, new_slug)):
            print(f"Title changed to '{merged.title}'; keeping the filename {target_slug}.md")
            new_slug = target_slug
    category = existing_category or "00 Inbox"

    # Save the merged note and its index entry first; remove the old one only after that succeeded.
    # Only the note being merged into may be replaced.
    save_note(new_slug, category, merged, replace=new_slug == target_slug,
              block=block, folder=existing_path.parent)
    if new_slug != target_slug:
        vault.delete_note(target_slug)
        memory.remove_entry(target_slug)

    print(f"merge: {category}/{new_slug}.md")
    return new_slug

def list_all_notes():
    """(slug, category) for every note, including notes in topic subfolders."""
    return [(slug, category) for slug, category, _ in vault.iter_note_files()]


def notes_on_disk():
    """{slug: [categories]} from a folder scan. More than one category means a duplicate slug.

    Unlike find_note this never raises on a duplicate, so callers can still report it.
    """
    on_disk = {}
    for slug, category in list_all_notes():
        on_disk.setdefault(slug, []).append(category)
    return on_disk


def find_index_drift():
    """Compare the index with the notes on disk. Read-only; the disk is the source of truth.

    Uses its own folder scan (notes_on_disk), not find_note: find_note stops on a
    duplicate slug, and this check must still work so the duplicate can be reported.
    """
    index = memory.load_index()
    paths = vault.note_paths()
    on_disk = notes_on_disk()
    drift = {"missing_file": [], "wrong_category": [], "not_indexed": [], "duplicate": []}
    for slug, categories in on_disk.items():
        if len(categories) > 1:
            # The folders, so that two copies in one category (two topic subfolders) are told apart
            drift["duplicate"].append((slug, [vault.relative(path.parent) for path in paths[slug]]))
        elif slug not in index:
            drift["not_indexed"].append((slug, categories[0]))
        elif index[slug].get("category") != categories[0]:
            drift["wrong_category"].append((slug, index[slug].get("category"), categories[0]))
    drift["missing_file"] = sorted(slug for slug in index if slug not in on_disk)
    return drift


def repair_index(drift):
    """Make the index match the disk. Duplicates are left for the user to resolve by hand."""
    # Embeddings first (network): if Ollama fails here, the index is not touched at all
    new_entries = {}
    paths = vault.note_paths()
    for slug, category in drift["not_indexed"]:
        data = vault.markdown_to_json(paths[slug][0].read_text(encoding="utf-8"))
        new_entries[slug] = memory.embed_entry(data["title"] or slug, data["summary"], category)
    index = memory.load_index()
    for slug in drift["missing_file"]:
        del index[slug]
    for slug, _, disk_category in drift["wrong_category"]:
        index[slug]["category"] = disk_category
    index.update(new_entries)
    memory.save_index(index)


def reembed_index(progress=None):
    """Recompute every vector in the index with the current config.EMBED_MODEL.

    kb --reindex only adds and removes entries; it never recomputes a vector. After
    EMBED_MODEL changes the old vectors stay, and vectors from two models cannot be
    compared. Each note is re-embedded from its title and summary on disk, the same
    text save_note and repair_index use; the index title and category are kept.

    Every indexed note must have its file in its category (run kb --reindex first).
    The old index is copied to a backup file, and the new one is written only after
    every note has a new vector: if Ollama fails half way, the index is left as it was.
    Returns (number of notes re-embedded, backup path).
    """
    index = memory.load_index()
    if not index:
        return 0, None
    paths = vault.note_paths()
    missing = [slug for slug, entry in index.items()
               if len(paths.get(slug, [])) != 1 or vault.category_of(paths[slug][0]) != entry["category"]]
    if missing:
        raise ValueError(f"{len(missing)} indexed note(s) have no file where the index expects it "
                         f"(first: {missing[0]}); run kb --reindex first")
    backup = config.INDEX_FILE.with_name(f".kb_index.backup-{datetime.now():%Y%m%d-%H%M%S}.json")
    shutil.copy2(config.INDEX_FILE, backup)
    new_index = {}
    for n, (slug, entry) in enumerate(index.items(), 1):
        category = entry["category"]
        data = vault.markdown_to_json(paths[slug][0].read_text(encoding="utf-8"))
        new_index[slug] = memory.embed_entry(data["title"] or slug, data["summary"], category)
        if progress:
            progress(n, len(index))
    memory.save_index(new_index)
    return len(new_index), backup


def delete_note_by_slug(slug):
    existing = vault.find_note(slug)
    if not existing or not existing[0]:
        raise RuntimeError(f"Note '{slug}' not found")
    vault.delete_note(slug)
    memory.remove_entry(slug)
    return slug

def propose_split_plan(text, backend=None):
    return brain.propose_split(text, backend=backend)

def process_from_plan(text, note_plan, backend=None):
    """
    Given the original text and ONE note-plan entry, create a single atomic note.
    The note_plan entry has: title, type, covers, source_hint.
    We pass the model the full source text plus instructions on which slice to focus on.
    """
    # The plan title becomes the filename, so an existing note is known before any model call.
    # NoteExistsError tells the caller to skip this entry; the existing note is not touched.
    slug = vault.slugify(note_plan["title"])
    vault.ensure_new(slug)
    focus_prompt = (
        f"{text}\n\n"
        f"---\n"
        f"From the source above, write ONE atomic encyclopedia note focused ONLY on: "
        f"{note_plan['title']} ({note_plan.get('type', '')}).\n"
        f"This note should cover: {note_plan.get('covers', '')}\n"
        f"Relevant part of the source: {note_plan.get('source_hint', '')}\n"
        f"Include only what belongs to this specific topic. Ignore parts of the source about other topics."
    )
    note = brain.create_note(focus_prompt, backend=backend)
    # Use the plan's title (short, atomic, user-approved), not the model's generated title
    note.title = note_plan["title"]
    category = brain.choose_category(note.title, note.summary, backend=backend)
    save_note(slug, category, note)
    return slug, category

def process_writeup(text, backend=None):
    print("Creating writeup...")
    note = brain.create_writeup(text, backend=backend)
    category = "90 Writeups"
    slug = vault.slugify(note.title)
    save_note(slug, category, note)
    print(f"writeup: {category}/{slug}.md")
    return slug

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        input_text = sys.argv[1]
    else:
        input_text = sys.stdin.read()
    process(input_text)

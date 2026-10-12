from engine import config, memory, vault, brain


def process(text, backend=None):
    print("Creating new note...")
    note = brain.create_note(text, backend=backend)

    print("Choosing category...")
    category = brain.choose_category(note.title, note.summary, backend=backend)
    print(f"Category: {category}")

    slug = vault.slugify(note.title)
    vault.write_note(slug, category, vault.to_markdown(note))
    memory.update_entry(slug, note.title, note.summary, category)

    print(f"create: {category}/{slug}.md")
    return slug


def find_merge_candidates(text):
    return memory.find_top_matches(text, limit=5)


def merge_into(text, target_slug, backend=None, confirm_rename=None):
    existing_md = vault.read_note(target_slug)
    if not existing_md:
        raise RuntimeError(f"Note '{target_slug}' not found")
    existing_json = vault.markdown_to_json(existing_md)
    _, existing_category = vault.find_note(target_slug)

    print("Step 1/2: structuring new text...")
    new_note = brain.create_note(text, backend=backend)
    print("Step 2/2: merging into existing note...")
    merged = brain.merge_two_notes(existing_json, new_note.model_dump(), backend=backend)

    new_slug = vault.slugify(merged.title)
    if not new_slug:
        raise RuntimeError(f"Merged title '{merged.title}' gives an empty filename. Nothing was changed.")
    # A new slug means the old file will be removed, so only rename when the user said yes.
    # Without a confirm_rename callback (server, piped input) the filename stays the same.
    if new_slug != target_slug and not (confirm_rename and confirm_rename(target_slug, new_slug)):
        print(f"Title changed to '{merged.title}'; keeping the filename {target_slug}.md")
        new_slug = target_slug
    category = existing_category or "00 Inbox"

    # Write the new note and its index entry first; remove the old one only after both succeeded
    vault.write_note(new_slug, category, vault.to_markdown(merged))
    memory.update_entry(new_slug, merged.title, merged.summary, category)
    if new_slug != target_slug:
        vault.delete_note(target_slug)
        memory.remove_entry(target_slug)

    print(f"merge: {category}/{new_slug}.md")
    return new_slug

def list_all_notes():
    from engine import config
    notes = []
    for category_dir in sorted(config.VAULT.iterdir()):
        if not category_dir.is_dir() or category_dir.name.startswith("."):
            continue
        for md_file in sorted(category_dir.glob("*.md")):
            slug = md_file.stem
            notes.append((slug, category_dir.name))
    return notes


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
    slug = vault.slugify(note.title)
    vault.write_note(slug, category, vault.to_markdown(note))
    memory.update_entry(slug, note.title, note.summary, category)
    return slug, category

def process_writeup(text, backend=None):
    print("Creating writeup...")
    note = brain.create_writeup(text, backend=backend)
    category = "90 Writeups"
    slug = vault.slugify(note.title)
    vault.write_note(slug, category, vault.to_markdown(note))
    memory.update_entry(slug, note.title, note.summary, category)
    print(f"writeup: {category}/{slug}.md")
    return slug

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        input_text = sys.argv[1]
    else:
        input_text = sys.stdin.read()
    process(input_text)

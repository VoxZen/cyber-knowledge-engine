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


def merge_into(text, target_slug, backend=None):
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
    category = existing_category or "00 Inbox"

    if target_slug != new_slug:
        vault.delete_note(target_slug)
        memory.remove_entry(target_slug)

    vault.write_note(new_slug, category, vault.to_markdown(merged))
    memory.update_entry(new_slug, merged.title, merged.summary, category)

    print(f"merge: {category}/{new_slug}.md")
    return new_slug


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        input_text = sys.argv[1]
    else:
        input_text = sys.stdin.read()
    process(input_text)

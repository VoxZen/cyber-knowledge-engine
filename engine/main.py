from engine import config, memory, vault, brain


def process(text):
    slug, score, title = memory.find_best_match(text)

    do_merge = False
    existing_json = None
    existing_category = None

    if slug and score >= config.CANDIDATE_THRESHOLD:
        print(f"Candidate: '{slug}' (score {score:.3f}) -> asking AI to decide")
        existing_md = vault.read_note(slug)
        existing_json = vault.markdown_to_json(existing_md)
        _, existing_category = vault.find_note(slug)
        if brain.decide_same_topic(title, existing_json["summary"], text):
            print("AI decision: SAME -> merging")
            do_merge = True
        else:
            print("AI decision: DIFFERENT -> new note")
    elif slug:
        print(f"Closest '{slug}' scored {score:.3f}, below threshold -> new note")
    else:
        print("No existing notes -> new note")

    if do_merge:
        print("Step 1/2: structuring new text...")
        new_note = brain.create_note(text)
        print("Step 2/2: merging into existing note...")
        note = brain.merge_two_notes(existing_json, new_note.model_dump())
        action = "merge"
        category = existing_category or "00 Inbox"
    else:
        note = brain.create_note(text)
        action = "create"
        print("Choosing category...")
        category = brain.choose_category(note.title, note.summary)
        print(f"Category: {category}")

    new_slug = vault.slugify(note.title)

    if action == "merge" and slug != new_slug:
        vault.delete_note(slug)
        memory.remove_entry(slug)

    vault.write_note(new_slug, category, vault.to_markdown(note))
    memory.update_entry(new_slug, note.title, note.summary, category)

    print(f"{action}: {category}/{new_slug}.md")
    return new_slug


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        input_text = sys.argv[1]
    else:
        input_text = sys.stdin.read()
    process(input_text)

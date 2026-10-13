import sys
import threading
import time
from pathlib import Path
import requests
from engine import main, config, vault
from engine.main import process, find_merge_candidates, merge_into
from engine.vault import NoteExistsError


def with_tag(model):
    # Ollama treats "nomic-embed-text" and "nomic-embed-text:latest" as the same model
    return model if ":" in model else model + ":latest"


def check_ollama():
    """True only if Ollama answers 200 and has the embedding model pulled."""
    try:
        r = requests.get(config.OLLAMA_BASE + "/api/tags", timeout=5)
        if r.status_code != 200:
            return False
        pulled = {with_tag(m["name"]) for m in r.json()["models"]}
    except (requests.exceptions.RequestException, ValueError, KeyError):
        return False
    return with_tag(config.EMBED_MODEL) in pulled


def require_ollama():
    if not check_ollama():
        print(f"ERROR: Ollama is not reachable at {config.OLLAMA_BASE}, or the embedding model "
              f"'{config.EMBED_MODEL}' is not pulled. Start Ollama, then run: ollama pull {config.EMBED_MODEL}")
        sys.exit(1)


def confirm_rename(old_slug, new_slug):
    """Ask before a merge renames a note. Without a terminal to ask in, the answer is no."""
    if not sys.stdin.isatty():
        return False
    print(f"\nThe merged title gives a new filename:\n  old: {old_slug}.md\n  new: {new_slug}.md")
    answer = input("Rename the note? The old file will be removed. (yes/no): ").strip().lower()
    return answer == "yes"


def report_existing(error):
    """Plain `kb` stopped because the note is already there. Show it and how to add to it."""
    title = vault.markdown_to_json(vault.read_note(error.slug))["title"] or error.slug
    print("-" * 50)
    print("STOPPED: a note with this filename already exists. Nothing was written.")
    print(f"  title:    {title}")
    print(f"  category: {error.category}")
    print(f"  file:     {error.category}/{error.slug}.md")
    print("To add this text to that note, run kb --merge with the same text and pick it from the list.")


def get_input_text(args):
    if args and args[0] == "--file":
        if len(args) < 2:
            print("Usage: kb --file path/to/note.txt")
            sys.exit(1)
        path = Path(args[1]).expanduser()
        if not path.exists():
            print(f"File not found: {path}")
            sys.exit(1)
        return path.read_text(encoding="utf-8")
    if args:
        return " ".join(args)
    print("Paste your note text below.")
    print("When finished, press Enter then Ctrl+D:")
    print("-" * 50)
    return sys.stdin.read()


class Spinner:
    def __init__(self, message):
        self.message = message
        self.running = False
        self.thread = None

    def _spin(self):
        symbols = "|/-\\"
        i = 0
        while self.running:
            sys.stdout.write(f"\r{self.message} {symbols[i % 4]} ")
            sys.stdout.flush()
            i += 1
            time.sleep(0.15)
        sys.stdout.write("\r" + " " * (len(self.message) + 4) + "\r")
        sys.stdout.flush()

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._spin)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()

def handle_split(backend, text):
    from engine.main import propose_split_plan, process_from_plan

    text = text.strip()
    if len(text) < 100:
        print(f"\nInput too short ({len(text)} chars) for splitting. Nothing saved.")
        return

    label = "DeepSeek (API)" if backend == "api" else "local 14B"
    print("-" * 50)
    print(f"Analyzing {len(text)} characters with {label}...")

    spinner = Spinner(f"Proposing atomic notes with {label}")
    spinner.start()
    try:
        plan = propose_split_plan(text, backend=backend)
    except Exception as e:
        spinner.stop()
        print(f"ERROR during planning: {e}")
        return
    spinner.stop()

    if not plan:
        print("No notes proposed. Nothing saved.")
        return

    while True:
        # A plan title is its filename. Mark the ones already in the vault, so they can be dropped.
        on_disk = main.notes_on_disk()
        print("\nProposed atomic notes:")
        for i, note in enumerate(plan, 1):
            categories = on_disk.get(vault.slugify(note["title"]))
            exists = f"  [exists: {', '.join(categories)}]" if categories else ""
            print(f"  {i}. {note['title']}  [{note.get('type', '?')}]{exists}")
            print(f"       {note.get('covers', '')}")
        if any(vault.slugify(note["title"]) in on_disk for note in plan):
            print("\n  [exists] = a note with this filename is already in the vault. "
                  "It will be skipped, not overwritten.")
        print("\nOptions:")
        print("  - Press Enter to CREATE all notes as shown")
        print("  - Type 'merge 2 3' to combine notes 2 and 3 into one")
        print("  - Type 'drop 4' to remove note 4")
        print("  - Type 'cancel' to abort")
        choice = input("\nYour choice: ").strip().lower()

        if choice == "":
            break
        elif choice == "cancel":
            print("Cancelled. Nothing saved.")
            return
        elif choice.startswith("merge"):
            nums = [int(n) for n in choice.split()[1:] if n.isdigit()]
            if len(nums) >= 2:
                nums = sorted(set(nums), reverse=True)
                targets = [plan[n - 1] for n in sorted(nums) if 1 <= n <= len(plan)]
                if len(targets) >= 2:
                    merged_title = targets[0]["title"]
                    merged_covers = " ".join(t.get("covers", "") for t in targets)
                    merged_hint = " ".join(t.get("source_hint", "") for t in targets)
                    for n in nums:
                        if 1 <= n <= len(plan):
                            del plan[n - 1]
                    plan.insert(0, {"title": merged_title, "type": "technique",
                                     "covers": merged_covers, "source_hint": merged_hint})
                    print(f"Merged into: {merged_title}")
        elif choice.startswith("drop"):
            nums = [int(n) for n in choice.split()[1:] if n.isdigit()]
            for n in sorted(set(nums), reverse=True):
                if 1 <= n <= len(plan):
                    removed = plan.pop(n - 1)
                    print(f"Dropped: {removed['title']}")
        else:
            print("Did not understand. Try again.")

    print("-" * 50)
    print(f"Creating {len(plan)} note(s)...")
    created = []
    skipped = []
    for note in plan:
        spinner = Spinner(f"Writing '{note['title']}'")
        spinner.start()
        try:
            slug, category = process_from_plan(text, note, backend=backend)
            spinner.stop()
            print(f"  created: {category}/{slug}.md")
            created.append(slug)
        except NoteExistsError as e:
            # One existing note must not stop a 40-note plan: keep it as it is and go on
            spinner.stop()
            print(f"  skipped (already exists): {e.category}/{e.slug}.md")
            skipped.append(f"{e.category}/{e.slug}.md")
        except Exception as e:
            spinner.stop()
            print(f"  ERROR on '{note['title']}': {e}")
    print("-" * 50)
    print(f"Done. Created {len(created)} note(s).")
    if skipped:
        print(f"Skipped {len(skipped)} existing note(s), not overwritten:")
        for path in skipped:
            print(f"  {path}")

def handle_delete():
    from engine.main import list_all_notes, delete_note_by_slug
    notes = list_all_notes()
    if not notes:
        print("No notes found. Nothing to delete.")
        return
    print("-" * 50)
    print("All notes:")
    for i, (slug, category) in enumerate(notes, 1):
        print(f"  {i}. {slug}  ({category})")
    print("  0. Cancel")
    choice = input(f"\nDelete which note? (0-{len(notes)}): ").strip()
    try:
        choice = int(choice)
    except ValueError:
        choice = 0
    if choice == 0:
        print("Cancelled. Nothing deleted.")
        return
    if 1 <= choice <= len(notes):
        target_slug = notes[choice - 1][0]
        confirm = input(f"Delete '{target_slug}'? This cannot be undone. (yes/no): ").strip().lower()
        if confirm == "yes":
            try:
                delete_note_by_slug(target_slug)
            except RuntimeError as e:
                print(f"ERROR: {e}")
                return
            print(f"Deleted: {target_slug}.md")
        else:
            print("Cancelled. Nothing deleted.")
    else:
        print("Invalid choice. Nothing deleted.")


def handle_reindex():
    from engine.main import find_index_drift, repair_index, list_all_notes
    from engine.memory import load_index
    from engine.vault import check_layout
    drift = find_index_drift()
    print("-" * 50)
    print(f"Index entries: {len(load_index())}   Notes on disk: {len(list_all_notes())}")
    missing, nested = check_layout()
    for path in nested:
        print(f"  WARNING (fix by hand): category folder nested inside another: {path}")
    for name in missing:
        print(f"  WARNING: category folder missing at the top level: {name}")
    for slug, categories in drift["duplicate"]:
        print(f"  DUPLICATE (fix by hand, not changed): {slug} in {', '.join(categories)}")
    for slug in drift["missing_file"]:
        print(f"  remove from index (no file on disk): {slug}")
    for slug, index_category, disk_category in drift["wrong_category"]:
        print(f"  fix category: {slug}  {index_category} -> {disk_category}")
    for slug, category in drift["not_indexed"]:
        print(f"  add to index (embedding needed): {category}/{slug}.md")

    if not (drift["missing_file"] or drift["wrong_category"] or drift["not_indexed"]):
        print("Index matches the vault. Nothing to repair.")
        return
    confirm = input("\nApply these changes to the index? (yes/no): ").strip().lower()
    if confirm == "yes":
        repair_index(drift)
        print("Index repaired.")
    else:
        print("Cancelled. Nothing changed.")


def run():
    args = sys.argv[1:]

    if "--delete" in args:
        handle_delete()
        return

    # Every other mode needs an embedding, and embeddings always come from Ollama,
    # whichever backend writes the note. Check before any model call or write.
    require_ollama()

    if "--reindex" in args:
        handle_reindex()
        return

    backend = config.DEFAULT_BACKEND
    if "--local" in args:
        backend = "local"
        args = [a for a in args if a != "--local"]

    if "--split" in args:
        args = [a for a in args if a != "--split"]
        split_text = get_input_text(args)
        handle_split(backend, split_text)
        return

    if "--writeup" in args:
        args = [a for a in args if a != "--writeup"]
        from engine.main import process_writeup
        writeup_text = get_input_text(args).strip()
        if len(writeup_text) < 100:
            print(f"\nInput too short ({len(writeup_text)} chars) for a writeup. Nothing saved.")
            return
        label = "DeepSeek (API)" if backend == "api" else "local 14B"
        print("-" * 50)
        print(f"Processing writeup ({len(writeup_text)} chars) with {label}...")
        spinner = Spinner(f"Writing up with {label}")
        spinner.start()
        try:
            slug = process_writeup(writeup_text, backend=backend)
            spinner.stop()
            print("-" * 50)
            print(f"Done. Writeup saved as: {slug}.md")
        except Exception as e:
            spinner.stop()
            print(f"ERROR: {e}")
            sys.exit(1)
        return

    do_merge = False
    if "--merge" in args:
        do_merge = True
        args = [a for a in args if a != "--merge"]

    text = get_input_text(args).strip()
    if len(text) < 30:
        print(f"\nInput too short ({len(text)} chars). Nothing saved.")
        sys.exit(1)

    label = "DeepSeek (API)" if backend == "api" else "local 14B"
    print("-" * 50)
    print(f"Processing {len(text)} characters with {label}...")

    if do_merge:
        spinner = Spinner("Searching for similar notes")
        spinner.start()
        candidates = find_merge_candidates(text)
        spinner.stop()

        if not candidates:
            print("No sufficiently similar notes found. Creating a new note instead.")
            do_merge = False
        else:
            print("\nSimilar notes found:")
            for i, (slug, title, category, score) in enumerate(candidates, 1):
                print(f"  {i}. [{score:.2f}] {title}  ({category})")
            print("  0. None of these - create a new note")
            choice = input("\nMerge into which note? (0-{}): ".format(len(candidates))).strip()
            try:
                choice = int(choice)
            except ValueError:
                choice = 0
            if choice == 0:
                do_merge = False
            elif 1 <= choice <= len(candidates):
                target_slug = candidates[choice - 1][0]
                spinner = Spinner(f"Merging with {label}")
                spinner.start()

                def ask_rename(old_slug, new_slug):
                    spinner.stop()  # otherwise the spinner overwrites the question
                    return confirm_rename(old_slug, new_slug)

                try:
                    slug = merge_into(text, target_slug, backend=backend, confirm_rename=ask_rename)
                    spinner.stop()
                    print("-" * 50)
                    print(f"Done. Merged into: {slug}.md")
                    return
                except Exception as e:
                    spinner.stop()
                    print(f"ERROR: {e}")
                    sys.exit(1)
            else:
                print("Invalid choice. Nothing saved.")
                sys.exit(1)

    spinner = Spinner(f"Working with {label}")
    spinner.start()
    try:
        slug = process(text, backend=backend)
        spinner.stop()
        print("-" * 50)
        print(f"Done. Note saved as: {slug}.md")
    except NoteExistsError as e:
        spinner.stop()
        report_existing(e)
        sys.exit(1)
    except Exception as e:
        spinner.stop()
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run()

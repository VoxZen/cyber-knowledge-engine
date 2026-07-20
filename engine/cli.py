import sys
import threading
import time
from pathlib import Path
import requests
from engine import main, config
from engine.main import process, find_merge_candidates, merge_into


def check_ollama():
    try:
        requests.get(config.OLLAMA_BASE + "/api/tags", timeout=5)
        return True
    except requests.exceptions.RequestException:
        return False


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


def run():
    args = sys.argv[1:]

    backend = "api"
    if "--local" in args:
        backend = "local"
        args = [a for a in args if a != "--local"]
        if not check_ollama():
            print("ERROR: Cannot reach Ollama. Start the Ollama app first.")
            sys.exit(1)

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
            print("No existing notes found. Creating a new note instead.")
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
                try:
                    slug = merge_into(text, target_slug, backend=backend)
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
    except Exception as e:
        spinner.stop()
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run()

import sys
import threading
import time
from pathlib import Path
import requests
from engine.main import process
from engine import config


def check_ollama():
    try:
        requests.get(config.OLLAMA_BASE + "/api/tags", timeout=5)
        return True
    except requests.exceptions.RequestException:
        return False


def get_input_text():
    args = sys.argv[1:]

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


def main():
    if not check_ollama():
        print("ERROR: Cannot reach Ollama.")
        print("Make sure Ollama is running (open the Ollama app, or run 'ollama serve').")
        sys.exit(1)

    text = get_input_text().strip()
    if len(text) < 30:
        print(f"\nInput too short ({len(text)} chars). Nothing saved.")
        sys.exit(1)

    print("-" * 50)
    print(f"Processing {len(text)} characters...")

    spinner = Spinner("Working (this can take a minute with the 14B model)")
    spinner.start()
    try:
        slug = process(text)
        spinner.stop()
        print("-" * 50)
        print(f"Done. Note saved as: {slug}.md")
    except requests.exceptions.RequestException as e:
        spinner.stop()
        print("-" * 50)
        print(f"ERROR: Lost connection to Ollama: {e}")
        sys.exit(1)
    except Exception as e:
        spinner.stop()
        print("-" * 50)
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

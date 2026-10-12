"""Test suite for the Cyber Knowledge Engine (standard library unittest only).

Run:
    cd ~/cke && source venv/bin/activate && python -m unittest discover -s tests -v

Safety rules of this suite:
- CKE_VAULT is pointed at a fresh temporary folder *before* the engine is imported,
  so no test can touch the real vault.
- No test calls a real model: llm.embed is faked and llm.ask_json is blocked.
- Fixtures in tests/fixtures/ are synthetic. Real notes are never copied into the repo.

One test reads the real vault, read-only and in place. It runs only when CKE_VAULT
is set when the suite starts:
    CKE_VAULT=~/Documents/CyberKB python -m unittest discover -s tests -v
"""
import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Remember the real vault (read-only round-trip test), then redirect the engine.
# This must happen before any `engine` import, because config.VAULT is read at import time.
REAL_VAULT = Path(os.environ["CKE_VAULT"]).expanduser() if os.environ.get("CKE_VAULT") else None
TEST_VAULT = Path(tempfile.mkdtemp(prefix="cke-test-vault-"))
os.environ["CKE_VAULT"] = str(TEST_VAULT)

import requests
from pydantic import ValidationError

from engine import brain, cli, config, llm, main, memory, vault
from engine.schema import Note, Section

if config.VAULT != TEST_VAULT:
    raise RuntimeError(f"Refusing to run: engine points at {config.VAULT}, not the test vault")

FIXTURES = Path(__file__).parent / "fixtures"


def tearDownModule():
    shutil.rmtree(TEST_VAULT, ignore_errors=True)


def fake_embed(text):
    return [1.0, float(len(text) % 7), 0.5]


def make_note(title, content="Body text."):
    return Note.model_validate({
        "title": title,
        "summary": f"Summary of {title}.",
        "sections": [{"heading": "Usage", "content": content}],
    })


def outline(markdown):
    """Independent reading of a note: (title, '## ' headings, lines inside code fences).

    Only the first '# ' line outside a fence is the title. Lines inside ``` or ~~~
    fences are code, never headings; a fence closes only with the marker that opened it.
    """
    title, headings, code = None, [], []
    fence = None
    for line in markdown.split("\n"):
        marker = line.lstrip()[:3]
        if fence is None and marker in ("```", "~~~"):
            fence = marker
            code.append(line)
        elif fence is not None:
            code.append(line)
            if marker == fence:
                fence = None
        elif line.startswith("# ") and title is None:
            title = line[2:].strip()
        elif line.startswith("## "):
            headings.append(line[3:].strip())
    return title, headings, code


class FakeResponse:
    """The two parts of a requests.Response that check_ollama reads."""

    def __init__(self, status_code, models=()):
        self.status_code = status_code
        self.models = [{"name": name} for name in models]

    def json(self):
        return {"models": self.models}


class VaultTestCase(unittest.TestCase):
    """Every test gets an empty temporary vault, a fake embedding and no model access."""

    def setUp(self):
        shutil.rmtree(TEST_VAULT, ignore_errors=True)
        TEST_VAULT.mkdir()
        self.enterContext(mock.patch.object(llm, "embed", side_effect=fake_embed))
        self.enterContext(mock.patch.object(llm, "ask_json", side_effect=AssertionError("model called in a test")))
        self.out = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.out))

    def write(self, rel_path, text):
        path = TEST_VAULT / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def read(self, rel_path):
        return (TEST_VAULT / rel_path).read_text(encoding="utf-8")

    def seed_index(self, entries):
        """entries: {slug: category}"""
        index = {slug: {"vector": fake_embed(slug), "title": slug, "category": category}
                 for slug, category in entries.items()}
        config.INDEX_FILE.write_text(json.dumps(index), encoding="utf-8")

    def index(self):
        return memory.load_index()

    def md_files(self):
        return sorted(p.relative_to(TEST_VAULT).as_posix() for p in TEST_VAULT.rglob("*.md"))

    def raises(self, error, func, *args, **kwargs):
        """Call func and report whether it raised `error`.

        Lets a test check the vault first, so a failure shows the damage, not just
        "exception not raised".
        """
        try:
            func(*args, **kwargs)
        except error:
            return True
        return False


# ---------------------------------------------------------------- P0-1

class P0_1_ParserTests(unittest.TestCase):
    """P0-1: markdown_to_json must not read '#' inside code fences as a heading."""

    def parse(self, fixture):
        return vault.markdown_to_json((FIXTURES / fixture).read_text(encoding="utf-8"))

    def test_shell_comment_in_code_block_is_not_the_title(self):
        data = self.parse("code_comment.md")
        self.assertEqual(data["title"], "Nmap")
        first = data["sections"][0]
        self.assertEqual(first["heading"], "Full port scan")
        self.assertEqual(first["content"], "```bash\n# scan all ports\nnmap -p- <target_ip>\n```")

    def test_tilde_fence_hides_headings(self):
        data = self.parse("tilde_fence.md")
        self.assertEqual(data["title"], "Dig")
        self.assertEqual([s["heading"] for s in data["sections"]], ["Zone transfer", "Short output"])
        self.assertIn("## not a section heading\n# not a title either", data["sections"][0]["content"])

    def test_only_the_first_h1_is_the_title(self):
        data = self.parse("second_h1.md")
        self.assertEqual(data["title"], "HTTP Status Codes")
        self.assertIn("# Common codes", data["sections"][0]["content"])

    def test_fence_closes_only_with_its_own_marker(self):
        data = self.parse("nested_fence.md")
        self.assertEqual(data["title"], "Markdown Code Blocks")
        self.assertEqual([s["heading"] for s in data["sections"]], ["Example", "After"])
        self.assertIn("# this comment is inside the inner fence", data["sections"][0]["content"])

    def test_round_trip_keeps_title_headings_and_code(self):
        for path in sorted(FIXTURES.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            with self.subTest(fixture=path.name):
                rebuilt = vault.to_markdown(Note.model_validate(vault.markdown_to_json(text)))
                self.assertEqual(outline(rebuilt), outline(text))


class P0_1_RealVaultRoundTrip(unittest.TestCase):
    """P0-1 acceptance: every real note, read in place. Nothing is copied or written."""

    def test_every_real_note_round_trips(self):
        if REAL_VAULT is None or not REAL_VAULT.is_dir():
            raise unittest.SkipTest("set CKE_VAULT to the real vault to run this read-only check")
        notes = sorted(REAL_VAULT.glob("[0-9][0-9] */*.md"))
        passed = 0
        for path in notes:
            text = path.read_text(encoding="utf-8")
            title, headings, code = outline(text)
            with self.subTest(note=path.relative_to(REAL_VAULT).as_posix()):
                self.assertIsNotNone(title, "file has no '# ' title line at column 0")
                data = vault.markdown_to_json(text)
                self.assertEqual(data["title"], title)
                rebuilt = vault.to_markdown(Note.model_validate(data))
                self.assertEqual(outline(rebuilt), (title, headings, code))
                passed += 1
        print(f"\nreal vault round trip: {passed}/{len(notes)} notes keep title, "
              f"headings and every code line", file=sys.stderr)


class P0_1_MergeSafetyTests(VaultTestCase):
    """P0-1: a merge that changes the title must never lose the original note."""

    ORIGINAL = (FIXTURES / "code_comment.md").read_text(encoding="utf-8")

    def setUp(self):
        super().setUp()
        self.write("08 Tools/nmap.md", self.ORIGINAL)
        self.seed_index({"nmap": "08 Tools"})
        self.enterContext(mock.patch.object(brain, "create_note", return_value=make_note("New Text")))

    def merge(self, merged_title, **kwargs):
        with mock.patch.object(brain, "merge_two_notes", return_value=make_note(merged_title)):
            return main.merge_into("new text about nmap", "nmap", **kwargs)

    def test_unusable_title_aborts_and_leaves_vault_untouched(self):
        raised = self.raises(RuntimeError, self.merge, "!!!")
        self.assertEqual(self.md_files(), ["08 Tools/nmap.md"])
        self.assertEqual(self.read("08 Tools/nmap.md"), self.ORIGINAL)
        self.assertEqual(set(self.index()), {"nmap"})
        self.assertTrue(raised, "merge must stop with a clear error")

    def test_title_change_without_confirmation_keeps_filename(self):
        # Non-interactive callers (Flask server, piped stdin) pass no confirm_rename.
        self.merge("Nmap Port Scanning")
        self.assertEqual(self.md_files(), ["08 Tools/nmap.md"])
        self.assertTrue(self.read("08 Tools/nmap.md").startswith("# Nmap Port Scanning\n"))
        self.assertEqual(set(self.index()), {"nmap"})
        self.assertEqual(self.index()["nmap"]["title"], "Nmap Port Scanning")

    def test_declined_rename_keeps_filename(self):
        asked = []
        self.merge("Nmap Port Scanning", confirm_rename=lambda old, new: asked.append((old, new)) or False)
        self.assertEqual(asked, [("nmap", "nmap-port-scanning")])
        self.assertEqual(self.md_files(), ["08 Tools/nmap.md"])

    def test_confirmed_rename_writes_new_note_before_deleting_old(self):
        seen_at_delete = []
        real_delete = vault.delete_note

        def checked_delete(slug):
            # The moment the old note is removed, the new one must already be on disk and indexed
            seen_at_delete.append((self.md_files(), set(self.index())))
            real_delete(slug)

        with mock.patch.object(vault, "delete_note", checked_delete):
            self.merge("Nmap Port Scanning", confirm_rename=lambda old, new: True)
        self.assertEqual(seen_at_delete, [(["08 Tools/nmap-port-scanning.md", "08 Tools/nmap.md"],
                                           {"nmap", "nmap-port-scanning"})])
        self.assertEqual(self.md_files(), ["08 Tools/nmap-port-scanning.md"])
        self.assertEqual(set(self.index()), {"nmap-port-scanning"})

    def test_cli_never_confirms_without_a_terminal(self):
        with mock.patch.object(sys, "stdin", io.StringIO()), \
             mock.patch("builtins.input", side_effect=AssertionError("must not ask")):
            self.assertFalse(cli.confirm_rename("nmap", "nmap-port-scanning"))

    def test_crash_while_indexing_keeps_the_original_note(self):
        llm.embed.side_effect = requests.exceptions.ConnectionError("Ollama is down")
        raised = self.raises(requests.exceptions.ConnectionError,
                             self.merge, "Nmap Port Scanning", confirm_rename=lambda old, new: True)
        self.assertEqual(self.read("08 Tools/nmap.md"), self.ORIGINAL)
        self.assertTrue(raised)


# ---------------------------------------------------------------- P0-2

class P0_2_DuplicateSlugTests(VaultTestCase):
    """P0-2: one slug = one file = one index entry."""

    def test_find_note_reports_a_slug_in_two_categories(self):
        self.write("01 Networking/nmap.md", "# Nmap\n")
        self.write("08 Tools/nmap.md", "# Nmap\n")
        with self.assertRaises(RuntimeError) as ctx:
            vault.find_note("nmap")
        self.assertIn("01 Networking", str(ctx.exception))
        self.assertIn("08 Tools", str(ctx.exception))

    def test_delete_refuses_an_ambiguous_slug(self):
        self.write("01 Networking/nmap.md", "# Nmap\n")
        self.write("08 Tools/nmap.md", "# Nmap\n")
        self.seed_index({"nmap": "08 Tools"})
        raised = self.raises(RuntimeError, main.delete_note_by_slug, "nmap")
        self.assertEqual(self.md_files(), ["01 Networking/nmap.md", "08 Tools/nmap.md"])
        self.assertIn("nmap", self.index())
        self.assertTrue(raised, "an ambiguous delete must be refused, not guessed")

    def test_writing_into_a_new_category_moves_the_note(self):
        vault.write_note("nmap", "01 Networking", "# Nmap\n\nold\n")
        vault.write_note("nmap", "08 Tools", "# Nmap\n\nnew\n")
        self.assertEqual(self.md_files(), ["08 Tools/nmap.md"])
        self.assertIn("new", self.read("08 Tools/nmap.md"))

    def test_reclassified_topic_leaves_no_orphan(self):
        # A later plain `kb` run may classify the same topic into another category.
        for category in ("01 Networking", "08 Tools"):
            with mock.patch.object(brain, "create_note", return_value=make_note("Nmap")), \
                 mock.patch.object(brain, "choose_category", return_value=category):
                main.process("some text about nmap")
        self.assertEqual(self.md_files(), ["08 Tools/nmap.md"])
        self.assertEqual(self.index()["nmap"]["category"], "08 Tools")
        self.assertEqual({p.stem for p in TEST_VAULT.rglob("*.md")}, set(self.index()))


# ---------------------------------------------------------------- P1-1

class P1_1_ReindexTests(VaultTestCase):
    """P1-1: `kb --reindex` reports index/vault drift and repairs it only when asked."""

    def setUp(self):
        super().setUp()
        self.write("08 Tools/nmap.md", "# Nmap\n\nScanner.\n\n## Usage\n\nScan.\n")              # in sync
        self.write("04 Web/http.md", "# HTTP\n\nProtocol.\n\n## Methods\n\nGET.\n")              # index: 00 Inbox
        self.write("09 Methodology/recon.md", "# Recon\n\nFirst phase.\n\n## Steps\n\nLook.\n")  # not indexed
        self.write("Claude outputs/PLAN.md", "# Plan\n")                                        # not a note
        self.seed_index({"nmap": "08 Tools", "http": "00 Inbox", "ghost": "01 Networking"})

    def test_report_finds_every_kind_of_drift_and_writes_nothing(self):
        before = config.INDEX_FILE.read_bytes()
        drift = main.find_index_drift()
        self.assertEqual(drift, {
            "missing_file": ["ghost"],
            "wrong_category": [("http", "00 Inbox", "04 Web")],
            "not_indexed": [("recon", "09 Methodology")],
            "duplicate": [],
        })
        self.assertEqual(config.INDEX_FILE.read_bytes(), before)
        llm.embed.assert_not_called()

    def test_repair_makes_the_index_match_the_disk(self):
        main.repair_index(main.find_index_drift())
        index = self.index()
        self.assertEqual({slug: entry["category"] for slug, entry in index.items()},
                         {"nmap": "08 Tools", "http": "04 Web", "recon": "09 Methodology"})
        self.assertEqual(index["recon"]["title"], "Recon")
        self.assertEqual(main.find_index_drift(),
                         {"missing_file": [], "wrong_category": [], "not_indexed": [], "duplicate": []})

    def test_duplicate_slug_is_reported_not_guessed(self):
        # find_note refuses duplicates; the reindex scan must still work and report them
        self.write("01 Networking/nmap.md", "# Nmap\n")
        drift = main.find_index_drift()
        self.assertEqual(drift["duplicate"], [("nmap", ["01 Networking", "08 Tools"])])
        main.repair_index(drift)
        self.assertIn("01 Networking/nmap.md", self.md_files())
        self.assertIn("08 Tools/nmap.md", self.md_files())
        self.assertEqual(self.index()["nmap"]["category"], "08 Tools")

    def run_cli(self, answer, ollama_ok=True):
        with mock.patch.object(sys, "argv", ["kb", "--reindex"]), \
             mock.patch.object(cli, "check_ollama", return_value=ollama_ok), \
             mock.patch("builtins.input", return_value=answer):
            cli.run()

    def test_cli_writes_nothing_without_yes(self):
        before = config.INDEX_FILE.read_bytes()
        self.run_cli("no")
        self.assertEqual(config.INDEX_FILE.read_bytes(), before)

    def test_cli_repairs_after_yes(self):
        self.run_cli("yes")
        self.assertEqual(set(self.index()), {"nmap", "http", "recon"})

    def test_cli_stops_when_ollama_is_down(self):
        before = config.INDEX_FILE.read_bytes()
        with self.assertRaises(SystemExit):
            self.run_cli("yes", ollama_ok=False)
        self.assertIn("Ollama", self.out.getvalue())
        self.assertEqual(config.INDEX_FILE.read_bytes(), before)


# ---------------------------------------------------------------- P1-2

class P1_2_CategoryFolderTests(VaultTestCase):
    """P1-2: only real category folders hold notes; one category list, in config.py."""

    def test_list_all_notes_ignores_non_category_folders(self):
        self.write("08 Tools/x.md", "# X\n")
        self.write("90 Writeups/box.md", "# Box\n")
        self.write("Claude outputs/y.md", "# Y\n")
        self.assertEqual(main.list_all_notes(), [("x", "08 Tools"), ("box", "90 Writeups")])

    def test_find_note_ignores_non_category_folders(self):
        self.write("Claude outputs/y.md", "# Y\n")
        self.assertEqual(vault.find_note("y"), (None, None))

    def test_classifier_and_vault_category_lists(self):
        self.assertEqual(len(config.CLASSIFIER_CATEGORIES), 10)
        self.assertEqual(config.VAULT_CATEGORIES,
                         config.CLASSIFIER_CATEGORIES + ["90 Writeups", "91 Templates", "99 Archive"])

    def test_prompt_lists_the_same_categories_as_config(self):
        # CATEGORY_SYSTEM stays hand-written (prompt text is frozen); this keeps it in sync.
        in_prompt = re.findall(r"^- (\d\d [^(]+?)\s*\(", brain.CATEGORY_SYSTEM, re.MULTILINE)
        self.assertEqual(["00 Inbox"] + in_prompt, config.CLASSIFIER_CATEGORIES)

    def test_choose_category_only_accepts_classifier_targets(self):
        for answer, expected in [("08 Tools", "08 Tools"), ("90 Writeups", "00 Inbox"),
                                 ("Claude outputs", "00 Inbox")]:
            with self.subTest(answer=answer), \
                 mock.patch.object(llm, "ask_json", return_value={"category": answer}):
                self.assertEqual(brain.choose_category("title", "summary"), expected)


# ---------------------------------------------------------------- P1-3

class P1_3_LayoutCheckTests(VaultTestCase):
    """P1-3: every classifier category is top-level, and no category folder is nested."""

    def test_reports_nested_and_missing_category_folders(self):
        (TEST_VAULT / "03 Windows" / "02 Linux").mkdir(parents=True)
        missing, nested = vault.check_layout()
        self.assertIn("02 Linux", missing)
        self.assertEqual(nested, ["03 Windows/02 Linux"])

    def test_clean_layout_reports_nothing(self):
        for name in config.CLASSIFIER_CATEGORIES:
            (TEST_VAULT / name).mkdir()
        self.assertEqual(vault.check_layout(), ([], []))


# ---------------------------------------------------------------- P1-4

class P1_4_OllamaCheckTests(VaultTestCase):
    """P1-4: check_ollama is True only if Ollama answers 200 and has the embedding model."""

    def check(self, response):
        with mock.patch.object(cli.requests, "get", return_value=response):
            return cli.check_ollama()

    def test_http_error_is_not_ok(self):
        self.assertFalse(self.check(FakeResponse(404)))

    def test_missing_embedding_model_is_not_ok(self):
        self.assertFalse(self.check(FakeResponse(200, ["qwen3:14b"])))
        self.assertFalse(self.check(FakeResponse(200, ["nomic-embed-text-v2:latest"])))

    def test_embedding_model_is_found_with_or_without_tag(self):
        for configured, listed in [("nomic-embed-text", "nomic-embed-text:latest"),
                                   ("nomic-embed-text:latest", "nomic-embed-text:latest"),
                                   ("nomic-embed-text:latest", "nomic-embed-text")]:
            with self.subTest(configured=configured, listed=listed), \
                 mock.patch.object(config, "EMBED_MODEL", configured):
                self.assertTrue(self.check(FakeResponse(200, ["qwen3:14b", listed])))

    def test_unreachable_is_not_ok(self):
        with mock.patch.object(cli.requests, "get", side_effect=requests.exceptions.ConnectionError()):
            self.assertFalse(cli.check_ollama())


class P1_4_CliChecksOllamaFirstTests(VaultTestCase):
    """P1-4: every mode that writes checks Ollama before doing any work, on both backends."""

    LONG_TEXT = "nmap scans ports " * 10  # long enough for every mode (--split needs 100 chars)

    def test_every_write_mode_stops_before_any_work(self):
        for flags in ([], ["--merge"], ["--split"], ["--writeup"], ["--local"]):
            self.out.seek(0)
            self.out.truncate()
            with self.subTest(flags=flags), \
                 mock.patch.object(sys, "argv", ["kb", *flags, self.LONG_TEXT]), \
                 mock.patch.object(cli, "check_ollama", return_value=False), \
                 mock.patch.object(cli, "process") as process, \
                 mock.patch.object(cli, "find_merge_candidates", return_value=[]) as find, \
                 mock.patch.object(main, "propose_split_plan", return_value=[]) as split, \
                 mock.patch.object(main, "process_writeup") as writeup, \
                 mock.patch("builtins.input", return_value="0"):
                with self.assertRaises(SystemExit):
                    cli.run()
                for work in (process, find, split, writeup):
                    work.assert_not_called()
                self.assertIn(config.EMBED_MODEL, self.out.getvalue())

    def test_delete_does_not_need_ollama(self):
        with mock.patch.object(sys, "argv", ["kb", "--delete"]), \
             mock.patch.object(cli, "check_ollama", return_value=False), \
             mock.patch("builtins.input", return_value="0"):
            cli.run()
        self.assertIn("No notes found", self.out.getvalue())


class P1_4_NoUnindexedNoteTests(VaultTestCase):
    """P1-4 acceptance: when the embedding fails, no .md file is left behind unindexed."""

    def setUp(self):
        super().setUp()
        llm.embed.side_effect = requests.exceptions.ConnectionError("Ollama is down")
        self.enterContext(mock.patch.object(brain, "create_note", return_value=make_note("Nmap")))
        self.enterContext(mock.patch.object(brain, "create_writeup", return_value=make_note("Box One")))
        self.enterContext(mock.patch.object(brain, "choose_category", return_value="08 Tools"))

    def assert_fails_and_writes_nothing(self, func, *args):
        with self.assertRaises(requests.exceptions.ConnectionError):
            func(*args)
        self.assertEqual(self.md_files(), [])

    def test_process(self):
        self.assert_fails_and_writes_nothing(main.process, "text about nmap")

    def test_process_from_plan(self):
        entry = {"title": "Nmap", "type": "tool", "covers": "usage", "source_hint": "all"}
        self.assert_fails_and_writes_nothing(main.process_from_plan, "text about nmap", entry)

    def test_process_writeup(self):
        self.assert_fails_and_writes_nothing(main.process_writeup, "text about a box")

    def test_failed_file_write_leaves_no_ghost_index_entry(self):
        # Order is embedding -> file -> index, so a failed disk write never leaves an index
        # entry without a file (the drift that P1-1 cleans up)
        llm.embed.side_effect = fake_embed
        with mock.patch.object(vault, "write_note", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                main.process("text about nmap")
        self.assertEqual(self.index(), {})

    def test_merge_leaves_the_original_untouched(self):
        original = "# Nmap\n\nScanner.\n\n## Usage\n\nScan.\n"
        self.write("08 Tools/nmap.md", original)
        self.seed_index({"nmap": "08 Tools"})
        with mock.patch.object(brain, "merge_two_notes", return_value=make_note("Nmap", "merged")):
            raised = self.raises(requests.exceptions.ConnectionError, main.merge_into, "text", "nmap")
        self.assertEqual(self.md_files(), ["08 Tools/nmap.md"])
        self.assertEqual(self.read("08 Tools/nmap.md"), original)
        self.assertTrue(raised)


# ---------------------------------------------------------------- P1-5

class P1_5_SectionContentTests(unittest.TestCase):
    """P1-5: section content is a string or a list of strings/numbers, nothing else."""

    def section(self, content):
        return Section.model_validate({"heading": "Usage", "content": content})

    def test_rejects_non_text_content(self):
        for bad in (None, {"a": 1}, 42, 4.2, True):
            with self.subTest(content=bad):
                with self.assertRaises(ValidationError) as ctx:
                    self.section(bad)
                self.assertIn("content must be a string or a list of strings", str(ctx.exception))

    def test_rejects_bad_list_items(self):
        for bad in ([None], [{"a": 1}], [True], [["nested"]]):
            with self.subTest(content=bad):
                with self.assertRaises(ValidationError) as ctx:
                    self.section(bad)
                self.assertIn("list items must be strings or numbers", str(ctx.exception))

    def test_still_accepts_strings_and_lists(self):
        self.assertEqual(self.section("  some text  ").content, "some text")
        self.assertEqual(self.section(["one", "two"]).content, "- one\n- two")

    def test_numbers_in_a_list_become_bullets(self):
        # A model may return ports as numbers; retrying for that would only cost API calls
        self.assertEqual(self.section(["ssh", 22, 443, 1.5]).content, "- ssh\n- 22\n- 443\n- 1.5")

    def test_title_and_body_aliases_still_work(self):
        section = Section.model_validate({"title": "Usage", "body": "text"})
        self.assertEqual((section.heading, section.content), ("Usage", "text"))

    def test_still_rejects_empty_values(self):
        for data in ({"heading": "Usage", "content": "   "}, {"heading": "Usage", "content": []},
                     {"heading": "  ", "content": "text"}):
            with self.subTest(data=data), self.assertRaises(ValidationError):
                Section.model_validate(data)
        with self.assertRaises(ValidationError):
            Note.model_validate({"title": "Nmap", "summary": "s", "sections": []})

    def test_missing_summary_is_still_filled_from_title(self):
        note = Note.model_validate({"title": "Nmap", "sections": [{"heading": "Usage", "content": "x"}]})
        self.assertEqual(note.summary, "Nmap")


# ---------------------------------------------------------------- P1-6

class P1_6_SlugifyTests(unittest.TestCase):
    """P1-6: slugify never returns an empty or unsafe slug."""

    AUDITED = ["..", "日本語", "!!!", "   ", "-", "../../etc/passwd"]

    def test_slug_is_never_empty_or_unsafe(self):
        for title in self.AUDITED:
            slug = vault.slugify(title)
            with self.subTest(title=title, slug=slug):
                self.assertTrue(slug)
                self.assertNotIn("/", slug)
                self.assertFalse(slug.startswith("."))
                self.assertNotIn("..", slug)

    def test_fallback_is_deterministic_and_distinct(self):
        self.assertEqual(vault.slugify("日本語"), vault.slugify("日本語"))
        self.assertNotEqual(vault.slugify("日本語"), vault.slugify("!!!"))

    def test_normal_titles_are_unchanged(self):
        self.assertEqual(vault.slugify("Nmap Scanning Basics"), "nmap-scanning-basics")
        self.assertEqual(vault.slugify("HTTP/2 vs. HTTP/1.1"), "http2-vs-http11")
        self.assertEqual(vault.slugify("one two three four five six seven eight nine ten"),
                         "one-two-three-four-five-six-seven-eight")
        self.assertEqual(vault.slugify("../../etc/passwd"), "etcpasswd")

    def test_strict_mode_reports_an_unusable_title(self):
        # merge_into uses fallback=False so it can refuse instead of inventing a filename.
        self.assertEqual(vault.slugify("!!!", fallback=False), "")


# ---------------------------------------------------------------- P2-1

class P2_1_SplitPlanTests(VaultTestCase):
    """P2-1: the --split plan goes through schema validation and the retry loop."""

    def propose(self, *responses):
        with mock.patch.object(llm, "ask_json", side_effect=list(responses)) as ask:
            return brain.propose_split("source text"), ask

    def test_valid_plan_fills_optional_fields(self):
        plan, _ = self.propose({"notes": [{"title": "Dig", "type": "tool"}]})
        self.assertEqual(plan, [{"title": "Dig", "type": "tool", "covers": "", "source_hint": ""}])

    def test_a_retry_can_fix_the_plan(self):
        plan, ask = self.propose({"notes": [{"covers": "no title"}]}, {"notes": [{"title": "Dig"}]})
        self.assertEqual([entry["title"] for entry in plan], ["Dig"])
        self.assertEqual(ask.call_count, 2)

    def test_malformed_plans_are_reported_not_crashed_on(self):
        attempts = config.MAX_RETRIES + 1
        for bad in ({"notes": [{"covers": "no title"}]}, {"notes": [{"title": "  "}]},
                    {"notes": {"title": "Dig"}}, {"notes": ["Dig"]}, {}):
            with self.subTest(response=bad):
                with self.assertRaises(RuntimeError):
                    self.propose(*[bad] * attempts)

    def test_cli_prints_the_error_and_saves_nothing(self):
        bad = {"notes": [{"covers": "no title"}]}
        with mock.patch.object(sys, "argv", ["kb", "--split", "nmap scans ports " * 10]), \
             mock.patch.object(cli, "check_ollama", return_value=True), \
             mock.patch.object(llm, "ask_json", return_value=bad), \
             mock.patch("builtins.input", return_value="cancel"):
            cli.run()
        self.assertIn("ERROR during planning", self.out.getvalue())
        self.assertEqual(self.md_files(), [])


if __name__ == "__main__":
    unittest.main()

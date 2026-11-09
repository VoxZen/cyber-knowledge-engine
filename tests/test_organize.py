"""Tests for the organisation layer: frontmatter, notes in subfolders, kb --organize, kb --taxonomy.

The suite setup (temporary vault, fake embedding, blocked model) comes from test_cke, which
must be imported before any engine module. Every note here is synthetic. The model is a
scripted fake of llm.ask_json.
"""
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_cke import TEST_VAULT, VaultTestCase, fake_embed, make_note  # noqa: F401  (sets CKE_VAULT first)

from engine import brain, cli, config, llm, main, memory, meta, organize, vault


def tearDownModule():
    shutil.rmtree(TEST_VAULT, ignore_errors=True)


def note_text(title, summary=None, headings=("Usage",)):
    lines = [f"# {title}", "", summary or f"Summary of {title}.", ""]
    for heading in headings:
        lines += [f"## {heading}", "", f"Text about {heading.lower()}.", ""]
    return "\n".join(lines)


class FakeModel:
    """A scripted llm.ask_json. Topic proposals come from `proposal`; each classification
    answer comes from `answer(slug, system)`, which returns a dict for that note."""

    def __init__(self, answer=None, proposal=None):
        self.answer = answer or (lambda slug, system: {"slug": slug, "topic": "General", "type": "concept"})
        self.proposal = proposal or {"topics": []}
        self.calls = []

    def __call__(self, system, prompt, backend=None):
        self.calls.append((system, prompt))
        if system.startswith("You organise"):
            return self.proposal
        slugs = re.findall(r"^SLUG: (.+)$", prompt, re.MULTILINE)
        return {"notes": [self.answer(slug, system) for slug in slugs]}

    def classify_calls(self):
        return [call for call in self.calls if call[0].startswith("You file")]


def taxonomy(**categories):
    """taxonomy(web=["SQL Injection", ("XSS", ["Cross-Site Scripting"])]) for '04 Web', plus General."""
    names = {"web": "04 Web", "tools": "08 Tools", "linux": "02 Linux", "cloud": "06 Cloud"}
    result = {"version": 1, "categories": {}}
    for key, topics in categories.items():
        entries = []
        for topic in topics:
            name, aliases = (topic, []) if isinstance(topic, str) else topic
            entries.append({"name": name, "definition": f"Notes about {name}.", "aliases": aliases})
        entries.append(organize.general_topic())
        result["categories"][names[key]] = {"topics": entries}
    return result


# ---------------------------------------------------------------- metadata

class MetaTests(unittest.TestCase):
    """engine/meta.py: the frontmatter block is raw lines; only the owned keys change."""

    BLOCK = ('---\n'
             'aliases:\n'
             '  - SQLi\n'
             '# a comment the user wrote\n'
             'topic: "Old"\n'
             'tags: [web, injection]\n'
             'cssclass: wide\n'
             '---\n')

    def test_split_and_rebuild_is_lossless(self):
        for text in ["# T\n\nS.\n", self.BLOCK + "# T\n\nS.\n", "---\nk: v\n---", "", "---\n---\nbody",
                     "---\r\ntopic: x\r\n---\r\n# T\r\n"]:
            with self.subTest(text=text):
                block, body = meta.split(text)
                self.assertEqual(block + body, text)

    def test_a_block_that_never_closes_is_not_frontmatter(self):
        for text in ["---\ntopic: x\n# Title\n", "--- \ntopic: x\n---\n", "\n---\ntopic: x\n---\n"]:
            with self.subTest(text=text):
                self.assertEqual(meta.split(text), ("", text))

    def test_unknown_keys_lists_and_comments_survive_an_update(self):
        new = meta.set_keys(self.BLOCK, {"topic": "SQL Injection", "type": "technique"})
        self.assertEqual(new, ('---\n'
                               'aliases:\n'
                               '  - SQLi\n'
                               '# a comment the user wrote\n'
                               'topic: "SQL Injection"\n'
                               'tags: [web, injection]\n'
                               'cssclass: wide\n'
                               'type: technique\n'
                               '---\n'))

    def test_new_block_has_the_documented_shape(self):
        old = "# Title\n\nSummary.\n"
        block = meta.set_keys("", {"topic": "SQL Injection", "type": "technique",
                                   "module": "SQL Injection Fundamentals", "source": "htb"})
        self.assertEqual(block, '---\ntopic: "SQL Injection"\ntype: technique\n'
                                'module: "SQL Injection Fundamentals"\nsource: htb\n---\n')
        new_text = block + old
        self.assertEqual(meta.split(new_text), (block, old))

    def test_keys_are_written_in_owned_order_and_missing_values_left_out(self):
        block = meta.set_keys("", {"source": "htb", "topic": "DNS", "module": None})
        self.assertEqual(block, '---\ntopic: "DNS"\nsource: htb\n---\n')

    def test_quotes_backslashes_and_colons_round_trip(self):
        for value in ['Say "hi"', "C:\\Windows\\System32", "Module: Part 2", "a\\\"b", "it's"]:
            with self.subTest(value=value):
                block = meta.set_keys("", {"topic": value, "module": value})
                self.assertEqual(meta.read(block), {"topic": value, "module": value})

    def test_read_accepts_what_obsidian_writes(self):
        block = "---\ntopic: SQL Injection\ntype: 'technique'\nmodule:\nsource: htb\n---\n"
        self.assertEqual(meta.read(block), {"topic": "SQL Injection", "type": "technique", "source": "htb"})

    def test_removing_a_key_and_replacing_a_list_value(self):
        block = "---\ntopic:\n  - A\n  - B\nkeep: 1\ntype: tool\n---\n"
        self.assertEqual(meta.set_keys(block, {"topic": "C", "type": None}), '---\ntopic: "C"\nkeep: 1\n---\n')
        self.assertEqual(meta.set_keys("---\ntype: tool\n---\n", {"type": None}), "")

    def test_only_owned_keys(self):
        with self.assertRaises(ValueError):
            meta.set_keys("", {"tags": "x"})


# ---------------------------------------------------------------- parser

class FrontmatterParserTests(VaultTestCase):
    """The block never reaches the model, the embedding or the index."""

    BLOCK = '---\ntopic: "Port Scanning"\ntype: tool\nsource: htb\n---\n'
    TEXT = "# Nmap\n\nPort scanner.\nSecond summary line.\n\n## Usage\n\nnmap -sV <target_ip>\n\n## Flags\n\n-p-\n"

    def test_markdown_to_json_ignores_the_block(self):
        self.assertEqual(vault.markdown_to_json(self.BLOCK + self.TEXT), vault.markdown_to_json(self.TEXT))
        self.assertEqual(vault.markdown_to_json(self.BLOCK + self.TEXT)["summary"],
                         "Port scanner. Second summary line.")

    def test_the_embedding_gets_the_same_text(self):
        self.write("08 Tools/Port Scanning/nmap.md", self.BLOCK + self.TEXT)
        main.repair_index(main.find_index_drift())
        llm.embed.assert_called_once_with("Nmap\nPort scanner. Second summary line.")
        self.assertEqual(memory.load_index()["nmap"]["category"], "08 Tools")


# ---------------------------------------------------------------- lookup

class NestedLookupTests(VaultTestCase):
    """A note is found by its name anywhere under its category folder."""

    def setUp(self):
        super().setUp()
        self.write("04 Web/SQL Injection/sqlmap-basics.md", note_text("Sqlmap Basics"))
        self.write("04 Web/xss.md", note_text("XSS"))

    def test_nested_note_is_found_listed_once_and_counted(self):
        path, category = vault.find_note("sqlmap-basics")
        self.assertEqual((vault.relative(path), category), ("04 Web/SQL Injection/sqlmap-basics.md", "04 Web"))
        self.assertEqual(main.list_all_notes(), [("sqlmap-basics", "04 Web"), ("xss", "04 Web")])
        self.assertEqual(main.notes_on_disk(), {"sqlmap-basics": ["04 Web"], "xss": ["04 Web"]})
        self.assertIn("Sqlmap Basics", vault.read_note("sqlmap-basics"))

    def test_ensure_new_refuses_a_nested_slug(self):
        with self.assertRaises(vault.NoteExistsError) as ctx:
            vault.ensure_new("sqlmap-basics")
        self.assertEqual(ctx.exception.path, "04 Web/SQL Injection/sqlmap-basics.md")

    def test_same_slug_in_two_subfolders_is_a_duplicate(self):
        self.write("04 Web/Other/sqlmap-basics.md", note_text("Sqlmap Basics"))
        with self.assertRaises(RuntimeError) as ctx:
            vault.find_note("sqlmap-basics")
        self.assertIn("04 Web/Other", str(ctx.exception))
        self.assertIn("04 Web/SQL Injection", str(ctx.exception))
        self.assertEqual(main.find_index_drift()["duplicate"],
                         [("sqlmap-basics", ["04 Web/Other", "04 Web/SQL Injection"])])

    def test_index_drift_is_empty_for_a_correct_nested_vault(self):
        self.seed_index({"sqlmap-basics": "04 Web", "xss": "04 Web"})
        self.assertEqual(main.find_index_drift(),
                         {"missing_file": [], "wrong_category": [], "not_indexed": [], "duplicate": []})

    def test_repair_and_reembed_read_nested_notes(self):
        self.seed_index({"xss": "04 Web"})
        main.repair_index(main.find_index_drift())
        self.assertEqual(memory.load_index()["sqlmap-basics"]["title"], "Sqlmap Basics")
        count, _ = main.reembed_index()
        self.assertEqual(count, 2)
        self.assertEqual(memory.load_index()["sqlmap-basics"]["vector"],
                         fake_embed("Sqlmap Basics\nSummary of Sqlmap Basics."))

    def test_delete_removes_a_nested_note(self):
        self.seed_index({"sqlmap-basics": "04 Web", "xss": "04 Web"})
        main.delete_note_by_slug("sqlmap-basics")
        self.assertEqual(self.md_files(), ["04 Web/xss.md"])


# ---------------------------------------------------------------- merge

class NestedMergeTests(VaultTestCase):
    """A merge keeps the note's folder and its frontmatter block."""

    BLOCK = '---\ntopic: "Port Scanning"\ntype: tool\nmy-own-key: kept\n---\n'
    PATH = "08 Tools/Port Scanning/nmap.md"

    def setUp(self):
        super().setUp()
        self.write(self.PATH, self.BLOCK + note_text("Nmap"))
        self.seed_index({"nmap": "08 Tools"})
        self.enterContext(mock.patch.object(brain, "create_note", return_value=make_note("New Text")))

    def merge(self, title, confirm=None):
        with mock.patch.object(brain, "merge_two_notes", return_value=make_note(title, "merged")) as merge:
            slug = main.merge_into("more about nmap", "nmap", confirm_rename=confirm)
        return slug, merge.call_args.args[0]

    def test_merge_into_a_nested_note_keeps_path_and_block(self):
        slug, existing_json = self.merge("Nmap")
        self.assertEqual(slug, "nmap")
        self.assertEqual(self.md_files(), [self.PATH])
        self.assertEqual(self.read(self.PATH), self.BLOCK + vault.to_markdown(make_note("Nmap", "merged")))
        self.assertNotIn("topic", json.dumps(existing_json), "the block must not reach the merge prompt")

    def test_merge_with_rename_keeps_folder_and_block(self):
        slug, _ = self.merge("Nmap Port Scanning", confirm=lambda old, new: True)
        new_path = "08 Tools/Port Scanning/nmap-port-scanning.md"
        self.assertEqual(slug, "nmap-port-scanning")
        self.assertEqual(self.md_files(), [new_path])
        self.assertTrue(self.read(new_path).startswith(self.BLOCK + "# Nmap Port Scanning\n"))
        self.assertEqual(set(memory.load_index()), {"nmap-port-scanning"})

    def test_a_new_note_is_written_flat_and_without_frontmatter(self):
        with mock.patch.object(brain, "create_note", return_value=make_note("Masscan")), \
             mock.patch.object(brain, "choose_category", return_value="08 Tools"):
            main.process("text about masscan")
        self.assertEqual(self.read("08 Tools/masscan.md"), vault.to_markdown(make_note("Masscan")))


# ---------------------------------------------------------------- split journal

class SplitJournalTests(VaultTestCase):
    """kb --split appends one journal line per run that created notes; the notes are unchanged."""

    TEXT = "whois and dig look up domain names and records " * 4

    def run_split(self, args, plan):
        with mock.patch.object(sys, "argv", ["kb", "--split", *args]), \
             mock.patch.object(cli, "check_ollama", return_value=True), \
             mock.patch.object(memory, "find_top_matches", return_value=[]), \
             mock.patch.object(main, "propose_split_plan", return_value=plan), \
             mock.patch.object(brain, "create_note", side_effect=lambda *a, **k: make_note("model title")), \
             mock.patch.object(brain, "choose_category", return_value="01 Networking"), \
             mock.patch("builtins.input", return_value=""):
            cli.run()

    def journal(self):
        if not config.SPLIT_LOG.exists():
            return []
        return [json.loads(line) for line in config.SPLIT_LOG.read_text(encoding="utf-8").splitlines()]

    def source_file(self):
        folder = Path(tempfile.mkdtemp(prefix="cke-test-src-"))
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        path = folder / "DNS Basics.md"
        path.write_text(self.TEXT, encoding="utf-8")
        return path

    def test_created_notes_have_no_frontmatter_and_the_journal_names_the_module(self):
        self.write("01 Networking/Other/dig.md", note_text("Dig"))
        path = self.source_file()
        self.run_split(["--file", str(path)], [{"title": "Whois", "type": "tool"}, {"title": "dig", "type": "tool"}])
        note = make_note("model title")
        note.title = "Whois"
        self.assertEqual(self.read("01 Networking/whois.md"), vault.to_markdown(note))
        [record] = self.journal()
        self.assertEqual(record["module"], "DNS Basics")
        self.assertEqual(record["source_file"], str(path.resolve()))
        self.assertEqual(record["created"], ["whois"])
        self.assertEqual(record["skipped"], ["01 Networking/Other/dig.md"])
        self.assertRegex(record["at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$")

    def test_pasted_text_has_no_module_and_nothing_created_writes_no_line(self):
        self.run_split([self.TEXT], [{"title": "Whois", "type": "tool"}])
        self.run_split([self.TEXT], [{"title": "Whois", "type": "tool"}])  # skipped: exists now
        [record] = self.journal()
        self.assertEqual((record["module"], record["source_file"], record["created"]), (None, None, ["whois"]))

    def test_a_journal_write_error_does_not_fail_the_split(self):
        with mock.patch.object(config, "SPLIT_LOG", TEST_VAULT / "no-such-folder" / "log.jsonl"):
            self.run_split([self.TEXT], [{"title": "Whois", "type": "tool"}])
        self.assertEqual(self.md_files(), ["01 Networking/whois.md"])
        self.assertIn("WARNING: could not write the split journal", self.out.getvalue())
        self.assertIn("Created 1 note(s)", self.out.getvalue())


# ---------------------------------------------------------------- taxonomy

class TaxonomyTests(VaultTestCase):
    """Topic names are folder names; aliases rename and merge topics."""

    def test_name_rules(self):
        topics = [{"name": "SQL Injection", "aliases": ["SQLi"]}]
        for name in ["XSS", "Kerberos", "File Transfers", "C2 & Pivoting", "Living off the Land (LOLBAS)",
                     "Pass-the-Hash", "Server's Side", "A1", "x" * 40]:
            with self.subTest(name=name):
                self.assertIsNone(organize.name_problem(name, topics))
        for name, reason in [("A", "2 to 40"), ("x" * 41, "2 to 40"), ("SQL/Injection", "letters"),
                             ("-Leading", "letters"), ("Trailing ", "trailing"), ("Other", "reserved"),
                             ("other", "reserved"), ("04 Web", "category"), ("sql-injection", "same name"),
                             ("SQLi", "alias"), ("Ünicode", "letters")]:
            with self.subTest(name=name):
                self.assertIn(reason, organize.name_problem(name, topics) or "")

    def test_validate_taxonomy(self):
        self.assertEqual(organize.validate_taxonomy(taxonomy(web=["SQL Injection", ("XSS", ["Cross-Site Scripting"])])), [])
        bad = taxonomy(web=["SQL Injection", ("XSS", ["SQL Injection"])])
        bad["categories"]["04 Web"]["topics"].pop()  # no General
        bad["categories"]["90 Writeups"] = {"topics": []}
        problems = "\n".join(organize.validate_taxonomy(bad))
        self.assertIn("alias 'SQL Injection' of 'XSS'", problems)
        self.assertIn("no 'General' topic", problems)
        self.assertIn("90 Writeups: not a category", problems)

    def test_canonical_maps_names_and_aliases(self):
        tax = taxonomy(web=[("SQL Injection", ["SQLi"])])
        self.assertEqual(organize.canonical(tax, "04 Web", "sqli"), "SQL Injection")
        self.assertEqual(organize.canonical(tax, "04 Web", "sql injection"), "SQL Injection")
        self.assertIsNone(organize.canonical(tax, "04 Web", "XSS"))
        self.assertIsNone(organize.canonical(tax, "08 Tools", "SQLi"))

    def test_an_alias_in_a_note_is_rewritten_and_the_note_moves(self):
        tax = taxonomy(web=[("SQL Injection", ["SQLi"])])
        config.TAXONOMY_FILE.write_text(json.dumps(tax), encoding="utf-8")
        for i in range(5):
            self.write(f"04 Web/SQLi/n{i}.md", '---\ntopic: "SQLi"\ntype: technique\n---\n' + note_text(f"N{i}"))
        plan = organize.build_plan()
        self.assertEqual(plan["manual_moves"], [], "a renamed topic is not a manual move")
        organize.apply_plan(plan)
        self.assertEqual(self.md_files(), [f"04 Web/SQL Injection/n{i}.md" for i in range(5)])
        self.assertTrue(self.read("04 Web/SQL Injection/n0.md").startswith('---\ntopic: "SQL Injection"\n'))
        self.assertEqual(organize.check_vault(), [])


# ---------------------------------------------------------------- placement

class OrganizeCase(VaultTestCase):
    """A vault with notes and a taxonomy, and a fake model that files each note by its slug."""

    def setUp(self):
        super().setUp()
        self.model = FakeModel(self.answer)
        llm.ask_json.side_effect = self.model
        self.topic_of = {}

    def answer(self, slug, system):
        return {"slug": slug, "topic": self.topic_of.get(slug, "General"), "type": "technique"}

    def notes(self, category, topic, count, prefix=None):
        prefix = prefix or re.sub(r"[^a-z]", "", topic.lower())
        for i in range(count):
            slug = f"{prefix}-{i}"
            self.write(f"{category}/{slug}.md", note_text(f"{topic} {i}"))
            self.topic_of[slug] = topic

    def tmp_dir(self):
        folder = Path(tempfile.mkdtemp(prefix="cke-test-plan-"))
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        return folder

    def use(self, tax):
        config.TAXONOMY_FILE.write_text(json.dumps(tax), encoding="utf-8")

    def organize(self, **kwargs):
        plan = organize.build_plan(**kwargs)
        return plan, organize.apply_plan(plan)


class PlacementTests(OrganizeCase):

    def test_threshold_other_and_one_level(self):
        self.use(taxonomy(web=["SQL Injection", "XSS"]))
        self.notes("04 Web", "SQL Injection", 5)
        self.notes("04 Web", "XSS", 4)
        self.notes("04 Web", "General", 1)
        self.organize()
        files = self.md_files()
        self.assertEqual([f for f in files if "/SQL Injection/" in f], [f"04 Web/SQL Injection/sqlinjection-{i}.md" for i in range(5)])
        self.assertEqual(sum("/Other/" in f for f in files), 5)
        self.assertTrue(all(f.count("/") == 2 for f in files if f.startswith("04 Web/")))
        self.assertEqual(organize.check_vault(), [])

    def test_no_subfolders_when_no_topic_reaches_five(self):
        self.use(taxonomy(web=["SQL Injection", "XSS"]))
        self.notes("04 Web", "SQL Injection", 4)
        self.notes("04 Web", "XSS", 4)
        self.organize()
        self.assertTrue(all(f.count("/") == 1 for f in self.md_files() if f.startswith("04 Web/")))
        self.assertEqual(organize.check_vault(), [])

    def test_a_topic_growing_from_four_to_five_leaves_other(self):
        self.use(taxonomy(web=["SQL Injection", "XSS"]))
        self.notes("04 Web", "SQL Injection", 5)
        self.notes("04 Web", "XSS", 4)
        self.organize()
        self.assertEqual(sum("/Other/xss-" in f for f in self.md_files()), 4)
        self.write("04 Web/xss-new.md", note_text("XSS New"))  # what kb --split writes
        self.topic_of["xss-new"] = "XSS"
        plan, result = self.organize()
        self.assertEqual(plan["summary"]["classified"], 1)
        self.assertEqual(result["moved"], 5)
        self.assertEqual(sorted(f for f in self.md_files() if "/XSS/" in f),
                         sorted([f"04 Web/XSS/xss-{i}.md" for i in range(4)] + ["04 Web/XSS/xss-new.md"]))
        self.assertFalse((TEST_VAULT / "04 Web" / "Other").exists(), "the emptied Other folder is removed")

    def test_a_note_deeper_than_one_level_is_reported_and_moved_up(self):
        self.use(taxonomy(web=["SQL Injection"]))
        self.notes("04 Web", "SQL Injection", 5)
        self.organize()
        (TEST_VAULT / "04 Web/SQL Injection/sqlinjection-0.md").rename(TEST_VAULT / "04 Web/SQL Injection/x.md")
        self.write("04 Web/SQL Injection/Deep/sqlinjection-0.md",
                   self.read("04 Web/SQL Injection/x.md"))
        (TEST_VAULT / "04 Web/SQL Injection/x.md").unlink()
        problems = organize.check_vault()
        self.assertTrue(any("deeper than one subfolder" in p for p in problems), problems)
        self.assertTrue(any("folder is not a topic" not in p for p in problems))
        self.organize()
        self.assertIn("04 Web/SQL Injection/sqlinjection-0.md", self.md_files())
        self.assertEqual(organize.check_vault(), [])

    def test_small_category_gets_only_general_without_a_model_call(self):
        self.notes("06 Cloud", "General", 3, prefix="cloud")
        plan, _ = self.organize()
        self.assertEqual(organize.topic_names(plan["taxonomy"], "06 Cloud"), ["General"])
        self.assertEqual([c for c in self.model.calls if c[0].startswith("You organise")], [])
        self.assertEqual(self.md_files(), [f"06 Cloud/cloud-{i}.md" for i in range(3)])


# ---------------------------------------------------------------- plan and apply

class PlanApplyTests(OrganizeCase):

    def setUp(self):
        super().setUp()
        self.use(taxonomy(web=["SQL Injection", "XSS"]))
        self.notes("04 Web", "SQL Injection", 6)
        self.notes("04 Web", "XSS", 2)
        self.write("00 Inbox/unsorted.md", note_text("Unsorted"))
        self.seed_index({slug: "04 Web" for slug in self.topic_of} | {"unsorted": "00 Inbox"})
        self.journal = '{"at": null, "module": "Web Module", "created": ["xss-0"], "backfilled": true}\n'
        config.SPLIT_LOG.write_text(self.journal, encoding="utf-8")

    def snapshot(self):
        return {p.relative_to(TEST_VAULT).as_posix(): p.read_bytes()
                for p in TEST_VAULT.rglob("*") if p.is_file()}

    def test_dry_run_writes_nothing_into_the_vault(self):
        before = self.snapshot()
        out_file = self.tmp_dir() / "plan.json"
        with mock.patch.object(sys, "argv", ["kb", "--organize", "--dry-run", "--plan-out", str(out_file)]), \
             mock.patch.object(cli, "check_ollama", side_effect=AssertionError("no Ollama check")), \
             mock.patch("builtins.input", side_effect=AssertionError("must not ask")):
            cli.run()
        self.assertEqual(self.snapshot(), before)
        self.assertIn("Dry run: nothing was changed.", self.out.getvalue())
        self.assertEqual(organize.load_plan(out_file)["summary"]["moves"], 8)

    def test_plan_file_round_trips(self):
        plan = organize.build_plan(set_source="htb")
        path = self.tmp_dir() / "plan.json"
        organize.save_plan(plan, path)
        self.assertEqual(organize.load_plan(path), plan)

    def test_apply_writes_only_the_block_and_moves(self):
        before = self.snapshot()
        index_before = config.INDEX_FILE.read_bytes()
        plan, result = self.organize(set_source="htb")
        self.assertEqual(result["moved"], 8)  # 6 to SQL Injection/, 2 to Other/
        after = self.snapshot()
        self.assertEqual(config.INDEX_FILE.read_bytes(), index_before)
        for entry in plan["notes"]:
            text = after[entry["to"]].decode("utf-8")
            block, body = meta.split(text)
            self.assertEqual(body.encode("utf-8"), before[entry["from"]], "body bytes must not change")
            self.assertEqual(meta.read(block), entry["set"])
        self.assertEqual(plan["notes"][6]["set"],  # xss-0: its module comes from the journal
                         {"topic": "XSS", "type": "technique", "module": "Web Module", "source": "htb"})
        self.assertEqual(after["00 Inbox/unsorted.md"], before["00 Inbox/unsorted.md"])
        self.assertEqual(main.find_index_drift(),
                         {"missing_file": [], "wrong_category": [], "not_indexed": [], "duplicate": []})
        self.assertEqual(json.loads(config.TAXONOMY_FILE.read_text(encoding="utf-8")), plan["taxonomy"])

    def test_apply_is_idempotent(self):
        plan, _ = self.organize()
        once = self.snapshot()
        result = organize.apply_plan(plan)
        self.assertEqual(self.snapshot(), once)
        self.assertEqual((result["moved"], result["updated"], result["taxonomy_written"]), (0, 0, False))
        again = organize.build_plan()
        self.assertEqual(again["summary"]["classified"], 0)
        self.assertEqual(again["summary"]["moves"], 0)
        self.assertEqual(again["summary"]["metadata_updates"], 0)

    def test_apply_refuses_a_changed_vault(self):
        plan = organize.build_plan()
        self.write("04 Web/new-note.md", note_text("New Note"))
        before = self.snapshot()
        with self.assertRaises(organize.PlanMismatchError):
            organize.apply_plan(plan)
        self.assertEqual(self.snapshot(), before)

    def test_empty_folders_are_removed(self):
        (TEST_VAULT / "04 Web" / "Old Topic").mkdir()
        (TEST_VAULT / "04 Web" / "Old Topic" / ".DS_Store").write_bytes(b"x")
        (TEST_VAULT / "04 Web" / "Empty").mkdir()
        _, result = self.organize()
        self.assertEqual(sorted(result["removed_folders"]), ["04 Web/Empty", "04 Web/Old Topic"])
        self.assertEqual(organize.check_vault(), [])

    def test_existing_user_frontmatter_is_kept(self):
        block = "---\ntags: [lab]\ntopic: XSS\n---\n"
        self.write("04 Web/xss-0.md", block + note_text("XSS 0"))
        plan, _ = self.organize()
        entry = next(e for e in plan["notes"] if e["slug"] == "xss-0")
        text = (TEST_VAULT / entry["to"]).read_text(encoding="utf-8")
        self.assertEqual(text, "---\ntags: [lab]\ntopic: XSS\ntype: technique\n"
                               'module: "Web Module"\n---\n' + note_text("XSS 0"))

    def test_cli_apply_after_yes_and_cancel_on_no(self):
        def run(answer):
            with mock.patch.object(sys, "argv", ["kb", "--organize"]), \
                 mock.patch("builtins.input", return_value=answer):
                cli.run()
        before = self.snapshot()
        run("no")
        self.assertEqual(self.snapshot(), before)
        run("yes")
        self.assertIn("04 Web/SQL Injection/sqlinjection-0.md", self.md_files())


# ---------------------------------------------------------------- manual moves

class ManualMoveTests(OrganizeCase):

    def setUp(self):
        super().setUp()
        self.use(taxonomy(web=["SQL Injection", "XSS"]))
        self.notes("04 Web", "SQL Injection", 5)
        self.notes("04 Web", "XSS", 5)
        self.organize()
        # The user drags one SQL injection note into the XSS folder in Obsidian
        (TEST_VAULT / "04 Web/SQL Injection/sqlinjection-0.md").rename(TEST_VAULT / "04 Web/XSS/sqlinjection-0.md")

    def run_cli(self, *answers, yes=False):
        argv = ["kb", "--organize"] + (["--yes"] if yes else [])
        answers = list(answers)
        self.questions = []

        def ask(question):
            self.questions.append(question)
            return answers.pop(0)
        with mock.patch.object(sys, "argv", argv), mock.patch("builtins.input", side_effect=ask):
            cli.run()
        return self.out.getvalue()

    def test_detected_and_skipped_with_yes(self):
        plan = organize.build_plan()
        self.assertEqual([(m["path"], m["folder"], m["derived"]) for m in plan["manual_moves"]],
                         [("04 Web/XSS/sqlinjection-0.md", "XSS", "SQL Injection")])
        out = self.run_cli(yes=True)
        self.assertIn("04 Web/XSS/sqlinjection-0.md: folder 'XSS', metadata says 'SQL Injection' -> skip", out)
        self.assertIn("04 Web/XSS/sqlinjection-0.md", self.md_files())
        self.assertTrue(self.read("04 Web/XSS/sqlinjection-0.md").startswith('---\ntopic: "SQL Injection"'))

    def test_folder_wins(self):
        self.run_cli("f", "yes")
        self.assertIn("04 Web/XSS/sqlinjection-0.md", self.md_files())
        self.assertTrue(self.read("04 Web/XSS/sqlinjection-0.md").startswith('---\ntopic: "XSS"'))
        self.assertEqual(organize.check_vault(), [])

    def test_metadata_wins(self):
        self.run_cli("m", "yes")
        self.assertIn("04 Web/SQL Injection/sqlinjection-0.md", self.md_files())
        self.assertEqual(organize.check_vault(), [])

    def test_folder_wins_is_offered_only_for_a_topic_folder(self):
        (TEST_VAULT / "04 Web/Mine").mkdir()
        (TEST_VAULT / "04 Web/XSS/sqlinjection-0.md").rename(TEST_VAULT / "04 Web/Mine/sqlinjection-0.md")
        self.run_cli("f", "m", "yes")  # 'f' is not accepted, so the question repeats
        self.assertEqual(self.questions, ["  [m]etadata wins / [s]kip: "] * 2 + ["\nApply? (yes/no): "])
        self.assertIn("04 Web/SQL Injection/sqlinjection-0.md", self.md_files())
        self.assertFalse((TEST_VAULT / "04 Web/Mine").exists())


# ---------------------------------------------------------------- classification

class ClassificationTests(OrganizeCase):

    def test_a_new_topic_is_added_and_visible_to_the_next_batch(self):
        self.use(taxonomy(web=["SQL Injection"]))
        self.notes("04 Web", "SQL Injection", 30, prefix="a")

        def answer(slug, system):
            if slug == "a-0":
                return {"slug": slug, "topic": None, "type": "concept",
                        "new_topic": {"name": "Web Caching", "definition": "Caches and their attacks."}}
            if slug == "a-1":  # the same new topic again in one batch maps to the first one
                return {"slug": slug, "topic": None, "type": "concept",
                        "new_topic": {"name": "web caching", "definition": "Duplicate."}}
            return {"slug": slug, "topic": "SQL Injection", "type": "technique"}
        self.model.answer = answer
        plan = organize.build_plan()
        first, second = self.model.classify_calls()
        self.assertNotIn("Web Caching:", first[0])
        self.assertIn("Web Caching: Caches and their attacks.", second[0])
        self.assertEqual(plan["new_topics"], [{"category": "04 Web", "name": "Web Caching",
                                               "definition": "Caches and their attacks."}])
        topics = {e["slug"]: e["set"]["topic"] for e in plan["notes"]}
        self.assertEqual((topics["a-0"], topics["a-1"]), ("Web Caching", "Web Caching"))
        self.assertEqual(organize.validate_taxonomy(plan["taxonomy"]), [])

    def test_a_proposal_that_collides_maps_to_the_existing_topic(self):
        self.use(taxonomy(web=[("SQL Injection", ["SQLi"])]))
        self.notes("04 Web", "SQL Injection", 1)
        self.model.answer = lambda slug, system: {"slug": slug, "topic": None, "type": "technique",
                                                  "new_topic": {"name": "SQLi", "definition": "x"}}
        plan = organize.build_plan()
        self.assertEqual(plan["new_topics"], [])
        self.assertEqual(plan["notes"][0]["set"]["topic"], "SQL Injection")

    def test_unknown_topic_or_type_is_retried(self):
        self.use(taxonomy(web=["SQL Injection"]))
        self.notes("04 Web", "SQL Injection", 2)
        answers = iter([{"topic": "Made Up", "type": "technique"}, {"topic": "SQL Injection", "type": "howto"},
                        {"topic": "SQL Injection", "type": "technique"}])
        replies = {}

        def answer(slug, system):
            if slug not in replies or slug == "sqlinjection-0":
                replies[slug] = next(answers) if slug == "sqlinjection-0" else {"topic": "SQL Injection", "type": "tool"}
            return {"slug": slug, **replies[slug]}
        self.model.answer = answer
        plan = organize.build_plan()
        self.assertEqual(len(self.model.classify_calls()), 3)
        self.assertIn("previous response was rejected", self.model.classify_calls()[1][1])
        self.assertEqual({e["slug"]: (e["set"]["topic"], e["set"]["type"]) for e in plan["notes"]},
                         {"sqlinjection-0": ("SQL Injection", "technique"), "sqlinjection-1": ("SQL Injection", "tool")})

    def test_an_answer_that_stays_wrong_is_never_written(self):
        self.use(taxonomy(web=["SQL Injection"]))
        self.notes("04 Web", "SQL Injection", 2)
        self.model.answer = lambda slug, system: {"slug": slug, "topic": "Made Up", "type": "technique"}
        plan, _ = self.organize()
        self.assertEqual(len(self.model.classify_calls()), config.MAX_RETRIES + 1)
        self.assertTrue(any("not classified" in w for w in plan["warnings"]))
        self.assertEqual([e["set"] for e in plan["notes"]], [{}, {}])
        self.assertEqual(self.read("04 Web/sqlinjection-0.md"), note_text("SQL Injection 0"))

    def test_new_topics_disallowed(self):
        self.use(taxonomy(web=["SQL Injection"]))
        self.notes("04 Web", "SQL Injection", 1)
        organize.build_plan(allow_new_topics=False)
        system = self.model.classify_calls()[0][0]
        self.assertNotIn("new_topic", system)
        self.assertNotIn("Propose a new topic", system)

    def test_proposal_drops_bad_names_and_adds_general(self):
        self.notes("04 Web", "x", 12, prefix="w")
        self.model.proposal = {"topics": [
            {"name": "SQL Injection", "definition": "SQLi.", "aliases": ["SQLi", "sql injection"]},
            {"name": "Other", "definition": "reserved"}, {"name": "sql-injection", "definition": "dup"},
            {"name": "XSS", "definition": "Scripts.", "aliases": ["SQLi"]}, {"name": "General", "definition": "x"}]}
        plan = organize.build_plan()
        self.assertEqual(plan["taxonomy"]["categories"]["04 Web"]["topics"], [
            {"name": "SQL Injection", "definition": "SQLi.", "aliases": ["SQLi"]},
            {"name": "XSS", "definition": "Scripts.", "aliases": []},
            organize.general_topic()])
        self.assertIn("Aim for 4 to 4 topics", self.model.calls[0][0])
        self.assertIn("w-0 | x 0 | Summary of x 0.", self.model.calls[0][1])


# ---------------------------------------------------------------- CLI

class OrganizeCliTests(OrganizeCase):

    def test_organize_and_taxonomy_run_without_the_ollama_check(self):
        self.use(taxonomy(web=["SQL Injection"]))
        self.notes("04 Web", "SQL Injection", 5)
        for argv in (["kb", "--taxonomy"], ["kb", "--organize", "--yes", "--set-source", "htb"], ["kb", "--taxonomy"]):
            with self.subTest(argv=argv), \
                 mock.patch.object(sys, "argv", argv), \
                 mock.patch.object(cli, "check_ollama", side_effect=AssertionError("no Ollama check")):
                cli.run()
        out = self.out.getvalue()
        self.assertIn("PROBLEM: no valid topic: 04 Web/sqlinjection-0.md", out)
        self.assertIn("No flags, no problems.", out)
        self.assertIn("     5  SQL Injection", out)

    def test_taxonomy_flags_large_topics_and_general(self):
        self.use(taxonomy(web=["SQL Injection"]))
        self.notes("04 Web", "SQL Injection", 41)
        self.notes("04 Web", "General", 20, prefix="gen")
        self.organize()
        report = "\n".join(organize.taxonomy_report())
        self.assertIn("04 Web / SQL Injection: 41 notes, more than 40", report)
        self.assertIn("04 Web: 'General' holds 20 of 61 notes", report)

    def test_bad_source_word_is_refused(self):
        with mock.patch.object(sys, "argv", ["kb", "--organize", "--yes", "--set-source", "Two Words"]):
            with self.assertRaises(SystemExit):
                cli.run()
        self.assertIn("one lowercase word", self.out.getvalue())


if __name__ == "__main__":
    unittest.main()

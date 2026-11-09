"""Tests for scripts/coverage.py, on a synthetic vault."""
import importlib.util
import json
import re
import shutil
from pathlib import Path

from test_cke import TEST_VAULT, VaultTestCase  # noqa: F401  (sets CKE_VAULT first)

SPEC = importlib.util.spec_from_file_location("coverage_script", Path(__file__).parent.parent / "scripts" / "coverage.py")
coverage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(coverage)


def tearDownModule():
    shutil.rmtree(TEST_VAULT, ignore_errors=True)


class CoveragePageTests(VaultTestCase):

    def note(self, path, topic, note_type, links=()):
        block = f'---\ntopic: "{topic}"\ntype: {note_type}\n---\n' if topic else ""
        body = f"# {Path(path).stem.title()}\n\nSummary.\n\n## Usage\n\n" + " ".join(f"[[{l}]]" for l in links) + "\n"
        self.write(path, block + body)

    def setUp(self):
        super().setUp()
        (TEST_VAULT / ".kb_taxonomy.json").write_text(json.dumps({"version": 1, "categories": {"04 Web": {"topics": [
            {"name": "SQL Injection", "definition": "SQLi.", "aliases": []},
            {"name": "XSS", "definition": "Scripts.", "aliases": []},
            {"name": "Empty Topic", "definition": "Nothing yet.", "aliases": []},
            {"name": "General", "definition": "Rest.", "aliases": []}]}}}), encoding="utf-8")
        for i in range(6):
            self.note(f"04 Web/SQL Injection/sqli-{i}.md", "SQL Injection", "defense" if i == 0 else "technique",
                      links=[f"sqli-{i + 1}", "xss-0", f"sqli-{i}"])  # a self link does not count
        self.note("04 Web/Other/xss-0.md", "XSS", "tool")
        self.note("04 Web/Other/xss-1.md", "XSS", "concept", links=["missing-note", "[:upper:]"])
        self.note("04 Web/new-note.md", None, None)
        self.write("00 Maps/web-map.md", "# Web — Module Map\n\n- [[xss-1]]\n- [[new-note]]\n")
        self.data = coverage.build_data(TEST_VAULT)

    def topic(self, name):
        [web] = [c for c in self.data["categories"] if c["name"] == "04 Web"]
        return next(t for t in web["topics"] if t["name"] == name)

    def test_totals(self):
        # links: sqli-0..4 -> next sqli (5), every sqli -> xss-0 (6); maps and self links do not count
        self.assertEqual(self.data["totals"], {"notes": 9, "categories": 1, "topics": 4, "links": 11})
        self.assertEqual(sum(t["count"] for c in self.data["categories"] for t in c["topics"]), 9)

    def test_topics_types_and_flags(self):
        sqli, xss = self.topic("SQL Injection"), self.topic("XSS")
        self.assertEqual((sqli["count"], sqli["types"]["defense"], sqli["types"]["technique"]), (6, 1, 5))
        self.assertEqual(sqli["unlinked"], 1)  # sqli-0: only itself links to it
        self.assertEqual(sqli["flags"], ["no_tool"])
        self.assertEqual(xss["unlinked"], 1)  # xss-1: linked only from a module map
        self.assertEqual(xss["flags"], ["thin", "no_defense"])
        self.assertEqual(self.topic("Empty Topic")["flags"], ["thin", "no_defense", "no_tool"])
        no_topic = self.topic(coverage.NO_TOPIC)
        self.assertEqual([n["path"] for n in no_topic["notes"]], ["04 Web/new-note.md"])
        self.assertIn("weak", no_topic["flags"])

    def test_large_flag(self):
        for i in range(6, 41):
            self.note(f"04 Web/SQL Injection/sqli-{i}.md", "SQL Injection", "technique")
        self.assertIn("large", coverage.build_data(TEST_VAULT)["categories"][0]["topics"][0]["flags"])

    def test_page_is_self_contained_and_translated(self):
        out = TEST_VAULT / "page.html"
        coverage.main(["--vault", str(TEST_VAULT), "--out", str(out), "--lang", "az"])
        page = out.read_text(encoding="utf-8")
        self.assertIn('<html lang="az">', page)
        self.assertIn("Bilik bazasının əhatəsi", page)
        self.assertNotRegex(page, r"(src|href)=[\"']?https?:")
        self.assertNotRegex(page, r"<script[^>]+src=|<link[^>]+stylesheet|@import|url\(")
        data = json.loads(re.search(r"const DATA = (.*?);\nconst S = ", page, re.S).group(1))
        self.assertEqual(data["totals"]["notes"], 9)
        self.assertEqual(data["vault"], TEST_VAULT.name)

    def test_default_output_is_in_the_vault(self):
        out = coverage.main(["--vault", str(TEST_VAULT)])
        self.assertEqual(out, TEST_VAULT / ".kb_coverage.html")
        self.assertIn('<html lang="en">', out.read_text(encoding="utf-8"))

    def test_a_script_end_tag_in_a_title_cannot_break_the_page(self):
        self.write("04 Web/evil.md", "# </script><b>x\n\nSummary.\n")
        page = coverage.render(coverage.build_data(TEST_VAULT))
        self.assertEqual(page.count("</script>"), 1)

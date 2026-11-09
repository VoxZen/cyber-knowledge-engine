"""Coverage page: one self-contained HTML file that shows where a vault is strong and where it is thin.

    python scripts/coverage.py [--vault DIR] [--out FILE] [--lang en|az]

Reads the category folders, each note's frontmatter (topic, type), the taxonomy and the
wikilinks, and writes <vault>/.kb_coverage.html by default. The page needs no network:
plain HTML, CSS and a little JavaScript, all inline.
"""
import argparse
import html
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import config, meta, vault  # noqa: E402

# The category colours of the Obsidian graph (.obsidian/graph.json colour groups)
CATEGORY_COLORS = {
    "01 Networking": "#4E79A7", "02 Linux": "#F28E2B", "03 Windows": "#76B7B2", "04 Web": "#E15759",
    "05 Active Directory": "#B07AA1", "06 Cloud": "#9C755F", "07 Programming": "#EDC948",
    "08 Tools": "#59A14F", "09 Methodology": "#FF9DA7",
}
OTHER_COLOR = "#BAB0AC"
THIN = 5            # fewer notes than this: "thin"
LARGE = 40          # more notes than this: "large"
NO_TOPIC = "—"  # the group of notes that have no topic yet
LINK_RE = re.compile(r"\[\[([^\]]*?)\]\]")

STRINGS = {
    "en": {
        "title": "Knowledge base coverage", "notes": "notes", "categories": "categories", "topics": "topics",
        "links": "links between notes", "generated": "generated", "map": "Map of the vault",
        "map_note": "Each block is a category and each tile a topic; area is proportional to the number of notes. "
                    "Click a tile to list its notes.",
        "health": "Topic health", "health_note": "Click a column header to sort, or a row to list its notes.",
        "category": "Category", "topic": "Topic", "count": "Notes", "mix": "Type mix",
        "unlinked": "Not linked", "flags": "Flags",
        "unlinked_note": "Not linked: notes that no other note links to (links from module maps do not count).",
        "thin": "thin", "large": "large", "no_defense": "no defense notes", "no_tool": "no tool notes",
        "weak": "weakly linked",
        "thin_def": f"fewer than {THIN} notes", "large_def": f"more than {LARGE} notes",
        "weak_def": "more than half of its notes have no incoming link from another note",
        "concept": "concept", "technique": "technique", "defense": "defense", "tool": "tool",
        "process": "process", "reference": "reference", "no_topic": "no topic yet",
        "close": "Close", "no_incoming": "no incoming link",
        "panel_hint": "Select a tile or a row to list its notes here.",
    },
    "az": {
        "title": "Bilik bazasının əhatəsi", "notes": "qeyd", "categories": "kateqoriya", "topics": "mövzu",
        "links": "qeydlər arası keçid", "generated": "yaradılıb", "map": "Bazanın xəritəsi",
        "map_note": "Hər blok bir kateqoriya, hər kafel bir mövzudur; sahə qeydlərin sayına mütənasibdir. "
                    "Mövzunun qeydlərini görmək üçün kafelə klikləyin.",
        "health": "Mövzuların vəziyyəti",
        "health_note": "Sıralamaq üçün sütun başlığına, qeydləri görmək üçün sətrə klikləyin.",
        "category": "Kateqoriya", "topic": "Mövzu", "count": "Qeyd", "mix": "Tip bölgüsü",
        "unlinked": "Keçidsiz", "flags": "İşarələr",
        "unlinked_note": "Keçidsiz: başqa heç bir qeydin keçid vermədiyi qeydlər (modul xəritələrindən gələn keçidlər sayılmır).",
        "thin": "az", "large": "böyük", "no_defense": "müdafiə qeydi yoxdur", "no_tool": "alət qeydi yoxdur",
        "weak": "zəif əlaqəli",
        "thin_def": f"{THIN}-dən az qeyd", "large_def": f"{LARGE}-dan çox qeyd",
        "weak_def": "qeydlərinin yarıdan çoxuna başqa qeyddən keçid yoxdur",
        "concept": "konsepsiya", "technique": "texnika", "defense": "müdafiə", "tool": "alət",
        "process": "proses", "reference": "arayış", "no_topic": "hələ mövzusu yoxdur",
        "close": "Bağla", "no_incoming": "daxil olan keçid yoxdur",
        "panel_hint": "Qeydləri burada görmək üçün kafel və ya sətir seçin.",
    },
}


def link_targets(text):
    return {raw.split("|", 1)[0].split("#", 1)[0].strip() for raw in LINK_RE.findall(text)}


def read_vault(vault_dir):
    """Notes with category, topic, type, title, relative path and outgoing link targets."""
    notes = []
    for category in config.VAULT_CATEGORIES:
        root = vault_dir / category
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.md")):
            if any(part.startswith(".") for part in path.relative_to(root).parts):
                continue
            text = path.read_bytes().decode("utf-8")
            block, body = meta.split(text)
            values = meta.read(block)
            notes.append({"slug": path.stem, "category": category, "topic": values.get("topic"),
                          "type": values.get("type"), "title": vault.markdown_to_json(body)["title"] or path.stem,
                          "path": path.relative_to(vault_dir).as_posix(), "links": link_targets(body)})
    return notes


def load_taxonomy(vault_dir):
    path = vault_dir / ".kb_taxonomy.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"categories": {}}


def build_data(vault_dir):
    """Everything the page shows, as plain data (also used by the tests)."""
    notes = read_vault(vault_dir)
    taxonomy = load_taxonomy(vault_dir)
    slugs = {n["slug"] for n in notes}
    incoming = Counter()
    pairs = set()
    for note in notes:
        for target in note["links"]:
            if target in slugs and target != note["slug"]:
                pairs.add((note["slug"], target))
    for _, target in pairs:
        incoming[target] += 1

    categories = []
    topic_total = 0
    for category in config.VAULT_CATEGORIES:
        members = [n for n in notes if n["category"] == category]
        if not members:
            continue
        defined = taxonomy.get("categories", {}).get(category, {}).get("topics", [])
        names = [t["name"] for t in defined]
        topic_total += len(names)
        definitions = {t["name"]: t.get("definition", "") for t in defined}
        groups = {name: [] for name in names}
        for note in members:
            groups.setdefault(note["topic"] if note["topic"] in groups else NO_TOPIC, []).append(note)
        topics = []
        for name, group in groups.items():
            if name == NO_TOPIC and not group:
                continue
            types = Counter(n["type"] for n in group if n["type"] in config.NOTE_TYPES)
            unlinked = sum(1 for n in group if not incoming[n["slug"]])
            flags = []
            if len(group) < THIN:
                flags.append("thin")
            if len(group) > LARGE:
                flags.append("large")
            if not types["defense"]:
                flags.append("no_defense")
            if not types["tool"]:
                flags.append("no_tool")
            if group and unlinked > len(group) / 2:
                flags.append("weak")
            topics.append({
                "name": name, "definition": definitions.get(name, ""), "count": len(group),
                "types": {t: types[t] for t in config.NOTE_TYPES}, "unlinked": unlinked, "flags": flags,
                "notes": sorted(({"title": n["title"], "type": n["type"] or "", "path": n["path"],
                                  "incoming": incoming[n["slug"]]} for n in group), key=lambda n: n["title"].lower()),
            })
        categories.append({"name": category, "color": CATEGORY_COLORS.get(category, OTHER_COLOR),
                           "count": len(members), "topics": topics})
    return {
        "vault": vault_dir.name, "generated": date.today().isoformat(),
        "totals": {"notes": len(notes), "categories": len(categories), "topics": topic_total, "links": len(pairs)},
        "types": config.NOTE_TYPES, "categories": categories,
    }


PAGE = """<!doctype html>
<html lang="__LANG__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root {
  color-scheme: light;
  --surface: #fcfcfb; --surface-2: #f2f1ee; --line: #d9d7d0; --ink: #0b0b0b; --ink-2: #52514e; --ink-3: #75736d;
  --accent: #1f5fae; --hover: rgba(0,0,0,0.06);
  --t-concept: #2a78d6; --t-technique: #eb6834; --t-defense: #1baf7a;
  --t-tool: #eda100; --t-process: #e87ba4; --t-reference: #008300;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --surface: #1a1a19; --surface-2: #242422; --line: #3a3a37; --ink: #f0efec; --ink-2: #c3c2b7; --ink-3: #9a988f;
    --accent: #7fb0f0; --hover: rgba(255,255,255,0.08);
    --t-concept: #3987e5; --t-technique: #d95926; --t-defense: #199e70;
    --t-tool: #c98500; --t-process: #d55181; --t-reference: #008300;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --surface: #1a1a19; --surface-2: #242422; --line: #3a3a37; --ink: #f0efec; --ink-2: #c3c2b7; --ink-3: #9a988f;
  --accent: #7fb0f0; --hover: rgba(255,255,255,0.08);
  --t-concept: #3987e5; --t-technique: #d95926; --t-defense: #199e70;
  --t-tool: #c98500; --t-process: #d55181; --t-reference: #008300;
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body { margin: 0; background: var(--surface); color: var(--ink);
  font: 16px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
main { max-width: 1200px; margin: 0 auto; padding: 24px 16px 64px; }
h1 { font-size: 1.6rem; margin: 0 0 4px; font-weight: 650; }
h2 { font-size: 1.15rem; margin: 36px 0 4px; font-weight: 650; }
p.note { margin: 0 0 12px; color: var(--ink-2); font-size: 0.92rem; }
.totals { color: var(--ink-2); margin: 0; display: flex; flex-wrap: wrap; gap: 4px 18px; }
.totals b { color: var(--ink); font-variant-numeric: tabular-nums; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 14px; margin: 0 0 10px; font-size: 0.85rem; color: var(--ink-2); padding: 0; list-style: none; }
.legend li { display: flex; align-items: center; gap: 6px; }
.sw { width: 12px; height: 12px; border-radius: 3px; flex: none; }
#map { position: relative; width: 100%; border: 1px solid var(--line); background: var(--surface); }
.cat { position: absolute; overflow: hidden; }
.cat-label { position: absolute; left: 0; right: 0; top: 0; height: 20px; padding: 2px 6px; font-size: 0.78rem;
  font-weight: 650; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--ink); background: var(--surface-2); }
.tile { position: absolute; border: 2px solid var(--surface); border-radius: 4px; padding: 3px 5px; overflow: hidden;
  cursor: pointer; font-size: 0.78rem; line-height: 1.2; }
.tile:hover, .tile:focus-visible { outline: 2px solid var(--ink); outline-offset: -2px; }
.tile.sel { outline: 3px solid var(--ink); outline-offset: -3px; }
.tile span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tile .n { font-variant-numeric: tabular-nums; opacity: 0.85; }
.table-wrap { overflow-x: auto; border: 1px solid var(--line); }
table { border-collapse: collapse; width: 100%; font-size: 0.9rem; }
th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--line); vertical-align: middle; }
th { position: sticky; top: 0; background: var(--surface-2); font-weight: 650; white-space: nowrap; cursor: pointer; user-select: none; }
th[aria-sort="ascending"]::after { content: " \\25B2"; font-size: 0.7em; }
th[aria-sort="descending"]::after { content: " \\25BC"; font-size: 0.7em; }
td.cat-cell { white-space: nowrap; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
tbody tr { cursor: pointer; }
tbody tr:hover { background: var(--hover); }
tbody tr.sel { background: var(--hover); font-weight: 600; }
.cat-dot { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px; vertical-align: -1px; }
.bar { display: flex; gap: 2px; width: 140px; height: 12px; }
.bar i { display: block; height: 100%; }
.bar i:first-child { border-radius: 4px 0 0 4px; }
.bar i:last-child { border-radius: 0 4px 4px 0; }
.bar i:only-child { border-radius: 4px; }
.flag { display: inline-block; border: 1px solid var(--line); border-radius: 3px; padding: 0 5px; margin: 1px 3px 1px 0;
  font-size: 0.78rem; white-space: nowrap; color: var(--ink-2); }
.flag.strong { border-color: var(--ink-2); color: var(--ink); }
dl.flags { display: grid; grid-template-columns: max-content 1fr; gap: 2px 10px; font-size: 0.85rem; color: var(--ink-2); margin: 10px 0 0; }
dl.flags dt { margin: 0; } dl.flags dd { margin: 0; }
#panel { border: 1px solid var(--line); background: var(--surface); margin-top: 36px; }
#panel header { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; padding: 10px 14px;
  border-bottom: 1px solid var(--line); background: var(--surface-2); }
#panel h2 { margin: 0; font-size: 1.05rem; }
#panel .def { padding: 8px 14px 0; margin: 0; color: var(--ink-2); font-size: 0.9rem; }
#panel ol { margin: 8px 0 12px; padding: 0 14px 0 40px; }
#panel li { padding: 3px 0; }
#panel a { color: var(--accent); text-decoration: none; }
#panel a:hover { text-decoration: underline; }
#panel .meta { color: var(--ink-3); font-size: 0.82rem; margin-left: 6px; }
#panel button { font: inherit; font-size: 0.85rem; border: 1px solid var(--line); background: var(--surface); color: var(--ink);
  border-radius: 4px; padding: 2px 10px; cursor: pointer; }
#panel .empty { padding: 12px 14px; margin: 0; color: var(--ink-2); }
@media (min-width: 1000px) {
  .layout { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 24px; align-items: start; }
  #panel { position: sticky; top: 16px; margin-top: 0; max-height: calc(100vh - 32px); overflow: auto; }
}
@media print { #panel { display: none; } .layout { display: block; } }
</style>
</head>
<body>
<main>
<h1>__TITLE__</h1>
<p class="totals" id="totals"></p>
<div class="layout">
<div>
<h2>__MAP__</h2>
<p class="note">__MAP_NOTE__</p>
<ul class="legend" id="cat-legend"></ul>
<div id="map" role="list"></div>
<h2>__HEALTH__</h2>
<p class="note">__HEALTH_NOTE__</p>
<ul class="legend" id="type-legend"></ul>
<div class="table-wrap"><table id="health"><thead></thead><tbody></tbody></table></div>
<dl class="flags" id="flag-defs"></dl>
<p class="note" style="margin-top:8px">__UNLINKED_NOTE__</p>
</div>
<aside id="panel" aria-live="polite"></aside>
</div>
</main>
<script>
const DATA = __DATA__;
const S = __STRINGS__;
const fmt = n => n.toLocaleString(document.documentElement.lang);
const el = (tag, attrs = {}, text) => { const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); if (text !== undefined) e.textContent = text; return e; };
const typeVar = t => `var(--t-${t})`;
const rows = [];
DATA.categories.forEach(c => c.topics.forEach(t => rows.push({cat: c, topic: t})));
const keyOf = r => r.cat.name + "\\u0001" + r.topic.name;
const topicName = t => t.name === "\\u2014" ? S.no_topic : t.name;

// Totals line
const tot = DATA.totals;
document.getElementById("totals").append(...[
  [tot.notes, S.notes], [tot.categories, S.categories], [tot.topics, S.topics], [tot.links, S.links]].map(([n, label]) => {
    const s = el("span"); s.append(el("b", {}, fmt(n)), " " + label); return s; }),
  Object.assign(el("span"), {textContent: `${S.generated} ${DATA.generated}`}));

// Legends
const catLegend = document.getElementById("cat-legend");
DATA.categories.forEach(c => { const li = el("li"); li.append(Object.assign(el("span", {class: "sw"}), {style: `background:${c.color}`}), c.name); catLegend.append(li); });
const typeLegend = document.getElementById("type-legend");
DATA.types.forEach(t => { const li = el("li"); const sw = el("span", {class: "sw"}); sw.style.background = typeVar(t); li.append(sw, S[t]); typeLegend.append(li); });
const defs = document.getElementById("flag-defs");
[["thin", S.thin_def], ["large", S.large_def], ["weak", S.weak_def]].forEach(([f, d]) => defs.append(el("dt", {}, S[f]), el("dd", {}, d)));

// Squarified treemap: items [{value}] into rect {x,y,w,h}; returns rects in item order
function squarify(items, rect) {
  const out = new Array(items.length);
  const order = items.map((it, i) => i).sort((a, b) => items[b].value - items[a].value);
  const total = items.reduce((s, it) => s + it.value, 0) || 1;
  let {x, y, w, h} = rect; const scale = (w * h) / total;
  let rowIdx = [], i = 0;
  const worst = (idx, side) => { const areas = idx.map(k => items[k].value * scale); const s = areas.reduce((a, b) => a + b, 0);
    return Math.max(...areas.map(a => Math.max(side * side * a / (s * s), (s * s) / (side * side * a)))); };
  const layoutRow = idx => { const s = idx.reduce((a, k) => a + items[k].value * scale, 0);
    if (w >= h) { const rw = s / h; let yy = y; idx.forEach(k => { const rh = items[k].value * scale / rw; out[k] = {x, y: yy, w: rw, h: rh}; yy += rh; }); x += rw; w -= rw; }
    else { const rh = s / w; let xx = x; idx.forEach(k => { const rw = items[k].value * scale / rh; out[k] = {x: xx, y, w: rw, h: rh}; xx += rw; }); y += rh; h -= rh; } };
  while (i < order.length) {
    const side = Math.min(w, h); const k = order[i];
    if (!rowIdx.length || worst([...rowIdx, k], side) <= worst(rowIdx, side)) { rowIdx.push(k); i++; }
    else { layoutRow(rowIdx); rowIdx = []; }
  }
  if (rowIdx.length) layoutRow(rowIdx);
  return out;
}
function inkFor(hex) {
  const c = hex.replace("#", ""); const ch = [0, 2, 4].map(i => parseInt(c.slice(i, i + 2), 16) / 255)
    .map(v => v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4));
  const L = 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
  return L > 0.30 ? "#111111" : "#ffffff";
}
const map = document.getElementById("map");
const tiles = new Map();
function drawMap() {
  map.textContent = ""; tiles.clear();
  const W = map.clientWidth; const H = Math.round(W < 640 ? W * 1.35 : Math.min(W * 0.58, 680));
  map.style.height = H + "px";
  const cats = DATA.categories.map(c => ({value: c.count}));
  squarify(cats, {x: 0, y: 0, w: W, h: H}).forEach((r, ci) => {
    const c = DATA.categories[ci];
    const box = el("div", {class: "cat", title: `${c.name}: ${c.count} ${S.notes}`});
    Object.assign(box.style, {left: r.x + "px", top: r.y + "px", width: r.w + "px", height: r.h + "px"});
    const label = r.h > 44 && r.w > 40 ? 20 : 0;
    if (label) box.append(el("div", {class: "cat-label"}, `${c.name} \\u00b7 ${c.count}`));
    const topics = c.topics.filter(t => t.count > 0);
    squarify(topics.map(t => ({value: t.count})), {x: 0, y: label, w: r.w, h: r.h - label}).forEach((tr, ti) => {
      const t = topics[ti];
      const tile = el("div", {class: "tile", role: "listitem", tabindex: "0",
        title: `${c.name} / ${topicName(t)}: ${t.count} ${S.notes}` + (t.definition ? `\\n${t.definition}` : "")});
      Object.assign(tile.style, {left: tr.x + "px", top: tr.y + "px", width: tr.w + "px", height: tr.h + "px",
        background: c.color, color: inkFor(c.color)});
      if (tr.w >= 64 && tr.h >= 34) tile.append(el("span", {}, topicName(t)), el("span", {class: "n"}, fmt(t.count)));
      else if (tr.w >= 22 && tr.h >= 18) tile.append(el("span", {class: "n"}, fmt(t.count)));
      const row = {cat: c, topic: t};
      tile.addEventListener("click", () => select(row));
      tile.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(row); } });
      tiles.set(keyOf(row), tile); box.append(tile);
    });
    map.append(box);
  });
  if (selected) tiles.get(keyOf(selected))?.classList.add("sel");
}

// Topic health table
const COLS = [
  {key: "cat", label: S.category, val: r => r.cat.name},
  {key: "topic", label: S.topic, val: r => topicName(r.topic).toLowerCase()},
  {key: "count", label: S.count, num: true, val: r => r.topic.count},
  {key: "mix", label: S.mix, val: r => r.topic.count ? r.topic.types.defense / r.topic.count : 0},
  {key: "unlinked", label: S.unlinked, num: true, val: r => r.topic.unlinked},
  {key: "flags", label: S.flags, val: r => r.topic.flags.length},
];
const table = document.getElementById("health");
const headRow = el("tr"); table.tHead.append(headRow);
let sort = {key: "cat", dir: 1};
COLS.forEach(col => { const th = el("th", {scope: "col", class: col.num ? "num" : "", tabindex: "0"}, col.label);
  const go = () => { sort = {key: col.key, dir: sort.key === col.key ? -sort.dir : (col.num || col.key === "flags" ? -1 : 1)}; drawTable(); };
  th.addEventListener("click", go); th.addEventListener("keydown", e => { if (e.key === "Enter") go(); });
  col.th = th; headRow.append(th); });
function drawTable() {
  const col = COLS.find(c => c.key === sort.key);
  const sorted = rows.slice().sort((a, b) => { const va = col.val(a), vb = col.val(b);
    return (va < vb ? -1 : va > vb ? 1 : 0) * sort.dir || a.cat.name.localeCompare(b.cat.name) || b.topic.count - a.topic.count; });
  COLS.forEach(c => c.th.setAttribute("aria-sort", c.key === sort.key ? (sort.dir > 0 ? "ascending" : "descending") : "none"));
  const body = table.tBodies[0]; body.textContent = "";
  sorted.forEach(r => {
    const t = r.topic; const tr = el("tr", {tabindex: "0"});
    const cat = el("td", {class: "cat-cell"}); const dot = el("span", {class: "cat-dot"}); dot.style.background = r.cat.color; cat.append(dot, r.cat.name);
    const bar = el("div", {class: "bar", title: DATA.types.map(k => `${S[k]}: ${t.types[k]}`).join("\\n")});
    DATA.types.forEach(k => { if (t.types[k]) { const i = el("i"); i.style.flexGrow = t.types[k]; i.style.background = typeVar(k); bar.append(i); } });
    const mix = el("td"); mix.append(bar);
    const flags = el("td"); t.flags.forEach(f => flags.append(el("span", {class: "flag" + (f === "thin" || f === "large" || f === "weak" ? " strong" : "")}, S[f])));
    tr.append(cat, el("td", {}, topicName(t)), el("td", {class: "num"}, fmt(t.count)), mix, el("td", {class: "num"}, fmt(t.unlinked)), flags);
    tr.addEventListener("click", () => select(r));
    tr.addEventListener("keydown", e => { if (e.key === "Enter") select(r); });
    if (selected && keyOf(selected) === keyOf(r)) tr.classList.add("sel");
    tr.dataset.key = keyOf(r); body.append(tr);
  });
}

// Notes panel
let selected = null;
const panel = document.getElementById("panel");
function showPanel() {
  panel.textContent = "";
  if (!selected) { panel.append(el("p", {class: "empty"}, S.panel_hint)); return; }
  const {cat, topic} = selected;
  const head = el("header"); head.append(el("h2", {}, `${cat.name} / ${topicName(topic)} (${fmt(topic.count)})`));
  const close = el("button", {type: "button"}, S.close); close.addEventListener("click", () => select(null)); head.append(close);
  panel.append(head);
  if (topic.definition) panel.append(el("p", {class: "def"}, topic.definition));
  const list = el("ol");
  topic.notes.forEach(n => { const li = el("li");
    const a = el("a", {href: `obsidian://open?vault=${encodeURIComponent(DATA.vault)}&file=${encodeURIComponent(n.path.replace(/\\.md$/, ""))}`}, n.title);
    li.append(a, el("span", {class: "meta"}, (n.type ? S[n.type] || n.type : "") + (n.incoming ? "" : ` \\u00b7 ${S.no_incoming}`)));
    list.append(li); });
  panel.append(list);
}
function select(row) {
  selected = row;
  document.querySelectorAll(".tile.sel, tr.sel").forEach(e => e.classList.remove("sel"));
  if (row) { tiles.get(keyOf(row))?.classList.add("sel");
    table.querySelector(`tr[data-key="${CSS.escape(keyOf(row))}"]`)?.classList.add("sel"); }
  showPanel();
  if (row && window.innerWidth < 1000) panel.scrollIntoView({block: "start"});
}
drawMap(); drawTable(); showPanel();
let resizeTimer; window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(drawMap, 120); });
</script>
</body>
</html>
"""


def render(data, lang="en"):
    strings = STRINGS[lang]
    # </ inside the JSON would end the script element
    as_js = lambda value: json.dumps(value, ensure_ascii=False).replace("</", "<\\/")
    page = PAGE
    for key, value in {"__LANG__": lang, "__TITLE__": strings["title"], "__MAP__": strings["map"],
                       "__MAP_NOTE__": strings["map_note"], "__HEALTH__": strings["health"],
                       "__HEALTH_NOTE__": strings["health_note"], "__UNLINKED_NOTE__": strings["unlinked_note"]}.items():
        page = page.replace(key, html.escape(value))
    return page.replace("__STRINGS__", as_js(strings)).replace("__DATA__", as_js(data))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Write a one-page HTML coverage report of a CKE vault.")
    parser.add_argument("--vault", type=Path, default=config.VAULT, help="vault folder (default: CKE_VAULT or ~/Documents/CyberKB)")
    parser.add_argument("--out", type=Path, help="output file (default: <vault>/.kb_coverage.html)")
    parser.add_argument("--lang", choices=sorted(STRINGS), default="en", help="language of the page's interface")
    args = parser.parse_args(argv)
    vault_dir = args.vault.expanduser()
    if not vault_dir.is_dir():
        parser.error(f"no vault at {vault_dir}")
    data = build_data(vault_dir)
    out = (args.out or vault_dir / ".kb_coverage.html").expanduser()
    out.write_text(render(data, args.lang), encoding="utf-8")
    t = data["totals"]
    print(f"{out}: {t['notes']} notes, {t['categories']} categories, {t['topics']} topics, {t['links']} links")
    return out


if __name__ == "__main__":
    main()

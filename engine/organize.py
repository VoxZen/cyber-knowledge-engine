"""kb --organize and kb --taxonomy: topics, types and topic subfolders.

Rules:
- A note is identified by its file name (slug). Its top-level folder is its category.
- Frontmatter is the truth for topic, type, module and source. Subfolders are derived
  from it: Category/<Topic>/ for a topic with TOPIC_FOLDER_MIN or more notes,
  Category/Other/ for smaller topics, no subfolders in a category where no topic is that big.
- The topics of each category are data, in <vault>/.kb_taxonomy.json.

Two stages, so the model's work can be reviewed and the file moves are deterministic:
build_plan() reads the vault and calls the model but writes nothing into the vault;
apply_plan() writes frontmatter and moves files, with no model call.
"""
import copy
import hashlib
import json
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath

from pydantic import BaseModel

from engine import brain, config, meta, vault

GENERAL = "General"
OTHER = "Other"
GENERAL_DEFINITION = "Notes of this folder that fit no narrower topic."
GENERAL_WARN_SHARE = 0.25   # kb --taxonomy flags a category where General holds more than this
PROPOSE_MIN_NOTES = 10      # a smaller category gets only General, without a model call
BATCH_SIZE = 25
PLAN_VERSION = 1

NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 &+()'\-]*")
SOURCE_RE = re.compile(r"[a-z0-9][a-z0-9_-]*")


class PlanMismatchError(RuntimeError):
    """The plan was built for another state of the vault."""


# ---------------------------------------------------------------- taxonomy

def normalize(name):
    """Lower case, letters and digits only: 'SQL Injection' and 'sql-injection' are the same name."""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def empty_taxonomy():
    return {"version": 1, "categories": {}}


def load_taxonomy(path=None):
    path = Path(path or config.TAXONOMY_FILE)
    if not path.exists():
        return empty_taxonomy()
    return json.loads(path.read_text(encoding="utf-8"))


def taxonomy_text(taxonomy):
    return json.dumps(taxonomy, ensure_ascii=False, indent=2) + "\n"


def save_taxonomy(taxonomy, path=None):
    _write_atomic(Path(path or config.TAXONOMY_FILE), taxonomy_text(taxonomy))


def topics_of(taxonomy, category):
    return taxonomy.get("categories", {}).get(category, {}).get("topics", [])


def topic_names(taxonomy, category):
    return [topic["name"] for topic in topics_of(taxonomy, category)]


def canonical(taxonomy, category, value):
    """The topic name that `value` means in this category (a name or an alias), or None."""
    if not value:
        return None
    key = normalize(value)
    topics = topics_of(taxonomy, category)
    for topic in topics:
        if normalize(topic["name"]) == key:
            return topic["name"]
    for topic in topics:
        if any(normalize(alias) == key for alias in topic.get("aliases", [])):
            return topic["name"]
    return None


def name_problem(name, topics=()):
    """Why `name` cannot be a topic name next to `topics` (the other topics of its category), or None."""
    if not isinstance(name, str):
        return "the name must be text"
    if not 2 <= len(name) <= 40:
        return "the name must be 2 to 40 characters"
    if not NAME_RE.fullmatch(name) or name != name.rstrip():
        return ("the name may use only letters, digits, spaces and & + ( ) ' -, "
                "starting with a letter or digit, with no trailing space")
    key = normalize(name)
    if key == normalize(OTHER):
        return f"'{OTHER}' is reserved for the folder of small topics"
    if key in {normalize(category) for category in config.VAULT_CATEGORIES}:
        return "the name of a category folder cannot be a topic"
    for topic in topics:
        if normalize(topic["name"]) == key:
            return f"it is the same name as the topic '{topic['name']}'"
        if any(normalize(alias) == key for alias in topic.get("aliases", [])):
            return f"it is an alias of the topic '{topic['name']}'"
    return None


def validate_taxonomy(taxonomy):
    """List of problems; empty when the taxonomy is valid."""
    if not isinstance(taxonomy, dict) or not isinstance(taxonomy.get("categories"), dict):
        return ["the taxonomy must be an object with a 'categories' object"]
    problems = []
    for category, entry in taxonomy["categories"].items():
        if category not in config.ORGANIZE_CATEGORIES:
            problems.append(f"{category}: not a category that kb --organize handles")
            continue
        topics = entry.get("topics") if isinstance(entry, dict) else None
        if not isinstance(topics, list):
            problems.append(f"{category}: 'topics' must be a list")
            continue
        checked = []
        for topic in topics:
            if not (isinstance(topic, dict) and isinstance(topic.get("name"), str)
                    and isinstance(topic.get("definition", ""), str)
                    and isinstance(topic.get("aliases", []), list)
                    and all(isinstance(alias, str) for alias in topic.get("aliases", []))):
                problems.append(f"{category}: a topic needs a name, a definition and a list of aliases: {topic!r}")
                continue
            problem = name_problem(topic["name"], checked)
            if problem:
                problems.append(f"{category}: topic '{topic['name']}': {problem}")
            for alias in topic.get("aliases", []):
                key = normalize(alias)
                if not key:
                    problems.append(f"{category}: topic '{topic['name']}' has an empty alias")
                    continue
                clash = [other["name"] for other in checked
                         if key == normalize(other["name"])
                         or any(key == normalize(a) for a in other.get("aliases", []))]
                if clash:
                    problems.append(f"{category}: alias '{alias}' of '{topic['name']}' "
                                    f"is also the name or an alias of '{clash[0]}'")
            checked.append(topic)
        if topics and GENERAL not in [topic.get("name") for topic in topics if isinstance(topic, dict)]:
            problems.append(f"{category}: has topics but no '{GENERAL}' topic")
    return problems


def add_topic(taxonomy, category, name, definition="", aliases=()):
    entry = taxonomy.setdefault("categories", {}).setdefault(category, {"topics": []})
    entry.setdefault("topics", []).append({"name": name, "definition": definition, "aliases": list(aliases)})


def general_topic():
    return {"name": GENERAL, "definition": GENERAL_DEFINITION, "aliases": []}


# ---------------------------------------------------------------- notes on disk

@dataclass
class NoteInfo:
    slug: str
    category: str
    path: Path
    block: str
    body: str
    meta: dict
    title: str
    summary: str
    headings: list

    @property
    def rel(self):
        return vault.relative(self.path)

    @property
    def folder(self):
        """The subfolder under the category: '' at the top, 'A/B' if deeper than one level."""
        return "/".join(self.path.relative_to(config.VAULT / self.category).parts[:-1])


def read_text(path):
    # Bytes, not read_text(): universal newlines would turn \r\n into \n and change the body
    return path.read_bytes().decode("utf-8")


def load_note(slug, category, path):
    text = read_text(path)
    block, body = meta.split(text)
    data = vault.markdown_to_json(body)
    return NoteInfo(slug, category, path, block, body, meta.read(block), data["title"] or slug,
                    data["summary"], [section["heading"] for section in data["sections"]])


def scan(categories=None):
    """(notes, duplicates): the notes of `categories` (default: all organised categories),
    and {slug: [paths]} for slugs that exist more than once anywhere in the vault."""
    categories = set(categories or config.ORGANIZE_CATEGORIES)
    paths = vault.note_paths()
    duplicates = {slug: found for slug, found in paths.items() if len(found) > 1}
    notes = [load_note(slug, category, path) for slug, category, path in vault.iter_note_files()
             if category in categories and slug not in duplicates]
    return notes, duplicates


def fingerprint(rel_paths=None):
    """SHA-256 over the sorted relative paths of all notes."""
    if rel_paths is None:
        rel_paths = [vault.relative(path) for _, _, path in vault.iter_note_files()]
    return hashlib.sha256("\n".join(sorted(rel_paths)).encode("utf-8")).hexdigest()


def read_journal(path=None):
    """{slug: module} from the split journal; a later line wins over an earlier one."""
    path = Path(path or config.SPLIT_LOG)
    modules = {}
    if not path.exists():
        return modules
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict) or not record.get("module"):
            continue
        for slug in record.get("created") or []:
            modules[slug] = record["module"]
    return modules


# ---------------------------------------------------------------- placement

def target_folder(topic, counts):
    """Subfolder for a note with this topic, given the topic counts of its category.

    None: no topic, the note stays where it is. '': the category folder itself.
    """
    if not topic:
        return None
    if not counts or max(counts.values()) < config.TOPIC_FOLDER_MIN:
        return ""
    return topic if counts[topic] >= config.TOPIC_FOLDER_MIN else OTHER


def target_path(category, slug, folder):
    return f"{category}/{folder}/{slug}.md" if folder else f"{category}/{slug}.md"


# ---------------------------------------------------------------- model calls

PROPOSE_SYSTEM = """You organise a personal cybersecurity knowledge base. You are given every note of one folder: its file name, title and one-line summary. Propose the topics this folder should be divided into.

Rules:
- A topic is a specific subject that several notes share: a vulnerability class, a protocol, a service, a platform feature, an attack phase.
- A topic is not a kind of note. Do not create topics such as "Tools", "Techniques", "Concepts", "Basics", "Advanced", "Miscellaneous".
- Exception by folder: if the folder holds tools, group them by what they are used for (for example "Web Fuzzing", "Password Cracking"). If the folder holds methodology, group by engagement phase or activity (for example "Reconnaissance", "Reporting").
- Topics should not overlap. Each note must have exactly one obvious home.
- Aim for {low} to {high} topics. Every topic should fit at least 5 of the notes shown.
- Names: 1 to 4 words, Title Case, letters, digits, spaces and & + ( ) ' - only. Use the name practitioners use ("SQL Injection", "Kerberos", "File Transfers").
- Give each topic one sentence that says what belongs in it, and common short names as aliases ("SQLi", "XSS").
- Do not include a catch-all topic; one named "General" is added automatically.

Respond only with JSON: {"topics": [{"name": "...", "definition": "...", "aliases": ["..."]}]}"""

CLASSIFY_SYSTEM = """You file notes of a personal cybersecurity knowledge base. All notes below are in the folder "{category}". For each note choose its topic and its type.

TOPICS of this folder:
{topics}

TYPES:
concept: what something is or how it works
technique: an offensive action (enumerate, exploit, escalate, move, persist, bypass)
defense: detection, hardening, mitigation, remediation
tool: one specific program or utility and how to use it
process: methodology, workflow, checklist, reporting
reference: a lookup list or table (ports, default credentials, payload lists, cheat sheets)

Rules:
- Choose the topic of the note's primary subject, by its exact name from the list.
- Use "General" only when no listed topic fits.
{new_topic_rule}- Answer for every note, in the order given, and copy each slug exactly.

Respond only with JSON: {answer_format}"""

NEW_TOPIC_RULE = ('- Propose a new topic only when no listed topic fits and the subject is specific enough that '
                  'several notes will belong to it. Then set "topic" to null and fill "new_topic" with a name '
                  '(1 to 4 words, Title Case) and a one-sentence definition.\n')
FORMAT_WITH_NEW = ('{"notes": [{"slug": "...", "topic": "..." or null, '
                   '"new_topic": null or {"name": "...", "definition": "..."}, "type": "..."}]}')
FORMAT_WITHOUT_NEW = '{"notes": [{"slug": "...", "topic": "...", "type": "..."}]}'


class ProposedTopic(BaseModel):
    name: str
    definition: str = ""
    aliases: list[str] = []


class TopicProposal(BaseModel):
    topics: list[ProposedTopic]


class NewTopic(BaseModel):
    name: str
    definition: str = ""


class Answer(BaseModel):
    slug: str
    topic: str | None = None
    new_topic: NewTopic | None = None
    type: str


class BatchAnswer(BaseModel):
    notes: list[Answer]


def topic_range(count):
    low = max(4, min(16, round(count / 25)))
    high = max(low, min(16, math.ceil(count / 12)))
    return low, high


def propose_topics(category, notes, backend=None, log=print):
    """Topics for a category with no topics yet: one model call over all its notes, plus General.

    Names that break the naming rules or repeat another topic are dropped with a warning,
    and so are aliases that clash with another topic.
    """
    low, high = topic_range(len(notes))
    system = PROPOSE_SYSTEM.replace("{low}", str(low)).replace("{high}", str(high))
    prompt = f"FOLDER: {category}\n" + "\n".join(f"{n.slug} | {n.title} | {n.summary}" for n in notes)
    proposal = brain.generate_validated(system, prompt, backend=backend, schema=TopicProposal)
    topics = []
    for item in proposal.topics:
        name = item.name.strip()
        if normalize(name) == normalize(GENERAL):
            continue
        problem = name_problem(name, topics)
        if problem:
            log(f"  dropped proposed topic '{name}' in {category}: {problem}")
            continue
        topics.append({"name": name, "definition": item.definition.strip(), "aliases": []})
        for alias in item.aliases:
            alias = alias.strip()
            if normalize(alias) and normalize(alias) != normalize(name) and not name_problem(alias, topics[:-1]) \
                    and normalize(alias) not in {normalize(a) for t in topics for a in t["aliases"]}:
                topics[-1]["aliases"].append(alias)
    topics.append(general_topic())
    return topics


class BatchValidator:
    """Checks one classification answer against the working taxonomy.

    Used as the `schema` of brain.generate_validated, so a wrong answer (unknown slug,
    topic or type, a missing note) is sent back to the model with the reason, and an
    answer that still fails after the retries is never written.
    Returns {slug: (topic, definition or None, type)}; a definition marks a new topic.
    """

    def __init__(self, taxonomy, category, slugs, allow_new):
        self.taxonomy, self.category, self.slugs, self.allow_new = taxonomy, category, list(slugs), allow_new

    def model_validate(self, raw):
        batch = BatchAnswer.model_validate(raw)
        answers = {}
        for answer in batch.notes:
            slug = answer.slug.strip()
            if slug not in self.slugs:
                raise ValueError(f"'{slug}' is not one of the slugs given; copy each slug exactly")
            if slug in answers:
                raise ValueError(f"'{slug}' is answered twice")
            note_type = answer.type.strip().lower()
            if note_type not in config.NOTE_TYPES:
                raise ValueError(f"'{answer.type}' for '{slug}' is not a type; use one of {', '.join(config.NOTE_TYPES)}")
            if answer.topic and answer.topic.strip():
                name = canonical(self.taxonomy, self.category, answer.topic.strip())
                if name is None:
                    hint = (" or set topic to null and propose new_topic" if self.allow_new else "")
                    raise ValueError(f"topic '{answer.topic}' for '{slug}' is not in the list; "
                                     f"use a listed name exactly{hint}")
                answers[slug] = (name, None, note_type)
            elif answer.new_topic is not None and self.allow_new:
                proposed = answer.new_topic.name.strip()
                name = canonical(self.taxonomy, self.category, proposed)
                if name is not None:
                    answers[slug] = (name, None, note_type)  # an existing topic under another spelling
                else:
                    problem = name_problem(proposed, topics_of(self.taxonomy, self.category))
                    if problem:
                        raise ValueError(f"new topic '{proposed}' for '{slug}': {problem}")
                    answers[slug] = (proposed, answer.new_topic.definition.strip(), note_type)
            else:
                raise ValueError(f"'{slug}' has no topic; choose one from the list")
        missing = [slug for slug in self.slugs if slug not in answers]
        if missing:
            raise ValueError(f"no answer for: {', '.join(missing)}")
        return answers


def classify_prompts(taxonomy, category, notes, allow_new):
    topics = "\n".join(f"{t['name']}: {t.get('definition', '')}" for t in topics_of(taxonomy, category))
    system = (CLASSIFY_SYSTEM.replace("{category}", category).replace("{topics}", topics)
              .replace("{new_topic_rule}", NEW_TOPIC_RULE if allow_new else "")
              .replace("{answer_format}", FORMAT_WITH_NEW if allow_new else FORMAT_WITHOUT_NEW))
    blocks = [f"SLUG: {n.slug}\nTITLE: {n.title}\nSUMMARY: {n.summary}\nSECTIONS: {', '.join(n.headings)}"
              for n in notes]
    return system, "\n\n".join(blocks)


def classify_batch(taxonomy, category, notes, allow_new=True, backend=None):
    system, prompt = classify_prompts(taxonomy, category, notes, allow_new)
    validator = BatchValidator(taxonomy, category, [n.slug for n in notes], allow_new)
    return brain.generate_validated(system, prompt, backend=backend, schema=validator)


def classify(taxonomy, category, notes, allow_new=True, backend=None, log=print):
    """Classify notes in batches of BATCH_SIZE, one batch after the other.

    A new topic is validated and added to `taxonomy` before the next batch, so later
    batches can choose it. Returns ({slug: (topic, type)}, [new topics], [warnings]).
    A batch the model fails on after the retries is left out with a warning.
    """
    results, new_topics, warnings = {}, [], []
    for start in range(0, len(notes), BATCH_SIZE):
        batch = notes[start:start + BATCH_SIZE]
        log(f"  {category}: classifying notes {start + 1}-{start + len(batch)} of {len(notes)}")
        try:
            answers = classify_batch(taxonomy, category, batch, allow_new, backend)
        except RuntimeError as error:
            warnings.append(f"{category}: batch {start + 1}-{start + len(batch)} not classified: {error}")
            continue
        for slug, (name, definition, note_type) in answers.items():
            if definition is not None:
                existing = canonical(taxonomy, category, name)
                if existing is None:
                    add_topic(taxonomy, category, name, definition)
                    new_topics.append({"category": category, "name": name, "definition": definition})
                    log(f"  new topic in {category}: {name}")
                else:
                    name = existing  # two notes of one batch proposed the same new topic
            results[slug] = (name, note_type)
    return results, new_topics, warnings


# ---------------------------------------------------------------- stage 1: plan

def build_plan(taxonomy=None, set_source=None, backend=None, decide=None, allow_new_topics=True, log=print):
    """Read the vault, call the model where needed, and return a plan. Writes nothing.

    taxonomy: start from this instead of the vault's taxonomy file.
    decide(note, folder, derived, folder_is_topic) answers a manual move with
    'folder', 'metadata' or 'skip'; without it every manual move is skipped.
    """
    if set_source is not None and not SOURCE_RE.fullmatch(set_source):
        raise ValueError(f"--set-source must be one lowercase word, got '{set_source}'")
    tax = copy.deepcopy(taxonomy if taxonomy is not None else load_taxonomy())
    problems = validate_taxonomy(tax)
    if problems:
        raise ValueError("the taxonomy is invalid:\n  " + "\n  ".join(problems))
    tax.setdefault("version", 1)

    notes, duplicates = scan()
    warnings = [f"duplicate slug, not organised until one file is removed: {slug} in "
                + ", ".join(vault.relative(p) for p in paths) for slug, paths in sorted(duplicates.items())]
    by_category = {category: [n for n in notes if n.category == category] for category in config.ORGANIZE_CATEGORIES}

    # Topics for categories that have notes but none yet
    proposed = []
    for category, members in by_category.items():
        if members and not topics_of(tax, category):
            if len(members) < PROPOSE_MIN_NOTES:
                topics = [general_topic()]
            else:
                log(f"Proposing topics for {category} ({len(members)} notes)...")
                topics = propose_topics(category, members, backend=backend, log=log)
            tax.setdefault("categories", {})[category] = {"topics": topics}
            proposed.append(category)

    # Current values; aliases become canonical names
    state = {}
    to_classify = {category: [] for category in config.ORGANIZE_CATEGORIES}
    for note in notes:
        note_type = note.meta.get("type", "").strip().lower()
        values = {"topic": canonical(tax, note.category, note.meta.get("topic")),
                  "type": note_type if note_type in config.NOTE_TYPES else None,
                  "module": note.meta.get("module"), "source": note.meta.get("source")}
        state[note.slug] = values
        if values["topic"] is None or values["type"] is None:
            to_classify[note.category].append(note)

    new_topics, classified = [], []
    for category, members in to_classify.items():
        if not members:
            continue
        results, added, batch_warnings = classify(tax, category, members, allow_new_topics, backend, log)
        new_topics += added
        warnings += batch_warnings
        for slug, (topic, note_type) in results.items():
            values = state[slug]
            values["topic"] = values["topic"] or topic
            values["type"] = values["type"] or note_type
            classified.append(slug)

    journal = read_journal()
    for note in notes:
        values = state[note.slug]
        values["module"] = values["module"] or journal.get(note.slug)
        values["source"] = values["source"] or set_source

    def counts_by_category():
        counts = {category: Counter() for category in config.ORGANIZE_CATEGORIES}
        for note in notes:
            if state[note.slug]["topic"]:
                counts[note.category][state[note.slug]["topic"]] += 1
        return counts

    # Manual moves: a note in a subfolder that is neither its derived folder, nor Other,
    # nor the folder of the topic its frontmatter names (that one is a rename or a regroup)
    counts = counts_by_category()
    manual_moves, skipped = [], set()
    for note in notes:
        topic = state[note.slug]["topic"]
        derived = target_folder(topic, counts[note.category])
        folder = note.folder
        if derived is None or not folder or "/" in folder or folder in (derived, OTHER):
            continue
        if normalize(folder) == normalize(note.meta.get("topic", "")):
            continue
        folder_topic = canonical(tax, note.category, folder)
        decision = decide(note, folder, derived, folder_topic is not None) if decide else "skip"
        if decision == "folder" and folder_topic is None:
            decision = "skip"
        manual_moves.append({"slug": note.slug, "path": note.rel, "folder": folder,
                             "derived": derived or note.category, "decision": decision})
        if decision == "folder":
            state[note.slug]["topic"] = folder_topic
        elif decision == "skip":
            skipped.add(note.slug)

    counts = counts_by_category()
    entries, after_paths, moves, updates = [], [], 0, 0
    planned = {note.slug for note in notes if note.slug not in skipped}
    for _, _, path in vault.iter_note_files():
        if path.stem not in planned:
            after_paths.append(vault.relative(path))
    for note in notes:
        if note.slug in skipped:
            continue
        values = state[note.slug]
        folder = target_folder(values["topic"], counts[note.category])
        to = note.rel if folder is None else target_path(note.category, note.slug, folder)
        to_set = {key: values[key] for key in meta.OWNED_KEYS if values[key] is not None}
        entries.append({"slug": note.slug, "category": note.category, "from": note.rel, "to": to, "set": to_set})
        after_paths.append(to)
        moves += to != note.rel
        updates += any(note.meta.get(key) != value for key, value in to_set.items())
        if values["topic"] is None:
            warnings.append(f"no topic for {note.rel}: it stays where it is")

    return {
        "version": PLAN_VERSION,
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        "vault": str(config.VAULT),
        "fingerprint": fingerprint(),
        "fingerprint_after": fingerprint(after_paths),
        "taxonomy": tax,
        "notes": entries,
        "summary": {"notes": len(notes), "classified": len(classified), "moves": moves,
                    "metadata_updates": updates, "proposed_categories": proposed},
        "classified": sorted(classified),
        "new_topics": new_topics,
        "manual_moves": manual_moves,
        "skipped": [{"slug": m["slug"], "path": m["path"], "reason": "manual move, skipped"}
                    for m in manual_moves if m["decision"] == "skip"],
        "warnings": warnings,
    }


def save_plan(plan, path):
    Path(path).write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_plan(path):
    plan = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(plan, dict) or plan.get("version") != PLAN_VERSION or "notes" not in plan:
        raise ValueError(f"{path} is not a kb --organize plan (version {PLAN_VERSION})")
    return plan


def plan_summary(plan):
    """The lines kb --organize prints before asking to apply."""
    summary = plan["summary"]
    lines = [f"Vault: {config.VAULT}",
             f"Notes in {config.ORGANIZE_CATEGORIES[0]} .. {config.ORGANIZE_CATEGORIES[-1]}: {summary['notes']}"]
    for category in summary["proposed_categories"]:
        lines.append(f"Topics proposed for {category}: " + ", ".join(topic_names(plan["taxonomy"], category)))
    lines.append(f"New topics: {len(plan['new_topics'])}")
    for topic in plan["new_topics"]:
        lines.append(f"  {topic['category']} / {topic['name']}: {topic['definition']}")
    lines.append(f"Notes classified: {summary['classified']}")
    lines.append(f"Notes to move: {summary['moves']}")
    lines.append(f"Notes with metadata to update: {summary['metadata_updates']}")
    lines.append(f"Manual moves: {len(plan['manual_moves'])}")
    for move in plan["manual_moves"]:
        lines.append(f"  {move['path']}: folder '{move['folder']}', metadata says '{move['derived']}' "
                     f"-> {move['decision']}")
    for warning in plan["warnings"]:
        lines.append(f"WARNING: {warning}")
    return lines


# ---------------------------------------------------------------- stage 2: apply

def _write_atomic(target, text):
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.parent / f".{target.name}.kb-tmp"
    temp.write_bytes(text.encode("utf-8"))
    os.replace(temp, target)


def _check_entry(entry, taxonomy):
    slug, category, to = entry.get("slug"), entry.get("category"), entry.get("to")
    if category not in config.ORGANIZE_CATEGORIES:
        return f"{slug}: '{category}' is not an organised category"
    parts = PurePosixPath(str(to)).parts
    values = entry.get("set", {})
    stays = "topic" not in values and to == entry.get("from")  # a note without topic is not moved
    if not (parts and parts[0] == category and parts[-1] == f"{slug}.md" and ".." not in parts):
        return f"{slug}: target '{to}' is not <category>/[<topic>/]{slug}.md"
    if not stays and len(parts) > 3:
        return f"{slug}: target '{to}' is deeper than one subfolder"
    if not stays and len(parts) == 3 and parts[1] != OTHER and parts[1] not in topic_names(taxonomy, category):
        return f"{slug}: target folder '{parts[1]}' is not a topic of {category}"
    if set(values) - set(meta.OWNED_KEYS):
        return f"{slug}: sets keys CKE does not own"
    if "topic" in values and values["topic"] not in topic_names(taxonomy, category):
        return f"{slug}: topic '{values['topic']}' is not in the taxonomy of {category}"
    if "type" in values and values["type"] not in config.NOTE_TYPES:
        return f"{slug}: type '{values['type']}' is not a note type"
    if "source" in values and not SOURCE_RE.fullmatch(values["source"]):
        return f"{slug}: source '{values['source']}' is not one lowercase word"
    return None


def remove_empty_folders():
    """Remove empty subfolders of the organised categories (a lone .DS_Store counts as empty)."""
    removed = []
    for category in config.ORGANIZE_CATEGORIES:
        root = config.VAULT / category
        if not root.is_dir():
            continue
        for folder in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
            if any(part.startswith(".") for part in folder.relative_to(root).parts):
                continue
            content = [p.name for p in folder.iterdir()]
            if all(name == ".DS_Store" for name in content):
                for name in content:
                    (folder / name).unlink()
                folder.rmdir()
                removed.append(vault.relative(folder))
    return removed


def apply_plan(plan, log=print):
    """Write frontmatter and move notes as the plan says. No model call.

    Refuses a plan built for another state of the vault (the fingerprint decides).
    Applying the same plan again changes nothing. The index is not touched.
    """
    current = fingerprint()
    if current not in (plan.get("fingerprint"), plan.get("fingerprint_after")):
        raise PlanMismatchError("the vault has changed since this plan was built (notes added, removed or "
                                "moved); build a new plan with kb --organize")
    taxonomy = plan["taxonomy"]
    problems = validate_taxonomy(taxonomy)
    paths = vault.note_paths()
    targets = Counter(entry.get("to") for entry in plan["notes"])
    for entry in plan["notes"]:
        problem = _check_entry(entry, taxonomy)
        found = paths.get(entry.get("slug"), [])
        if problem is None and len(found) != 1:
            problem = f"{entry.get('slug')}: expected one file, found {len(found)}"
        if problem is None and vault.category_of(found[0]) != entry["category"]:
            problem = f"{entry['slug']}: is in {vault.category_of(found[0])}, the plan says {entry['category']}"
        if problem is None and targets[entry["to"]] > 1:
            problem = f"{entry['slug']}: two notes have the target {entry['to']}"
        if problem:
            problems.append(problem)
    if problems:
        raise ValueError("the plan is invalid, nothing was changed:\n  " + "\n  ".join(problems[:20]))

    moved = updated = 0
    for entry in plan["notes"]:
        source = paths[entry["slug"]][0]
        text = read_text(source)
        block, body = meta.split(text)
        now = meta.read(block)
        changes = {key: value for key, value in entry["set"].items() if now.get(key) != value}
        new_text = (meta.set_keys(block, changes) if changes else block) + body
        target = config.VAULT / entry["to"]
        if target == source and new_text == text:
            continue
        # On a case-insensitive disk "sql injection/x.md" and "SQL Injection/x.md" are one file:
        # removing the "old" one after the write would remove the note itself
        same_file = target.exists() and target.samefile(source)
        _write_atomic(target, new_text)
        if not same_file:
            source.unlink()
            moved += 1
        updated += bool(changes)
    removed = remove_empty_folders()
    taxonomy_written = False
    if not config.TAXONOMY_FILE.exists() or config.TAXONOMY_FILE.read_text(encoding="utf-8") != taxonomy_text(taxonomy):
        save_taxonomy(taxonomy)
        taxonomy_written = True
    return {"moved": moved, "updated": updated, "removed_folders": removed, "taxonomy_written": taxonomy_written}


# ---------------------------------------------------------------- check and report

def check_vault(taxonomy=None):
    """Problems with the organisation of the vault; an empty list when everything is in order."""
    tax = taxonomy if taxonomy is not None else load_taxonomy()
    problems = [f"taxonomy: {problem}" for problem in validate_taxonomy(tax)]
    for slug, found in sorted(vault.note_paths().items()):
        if len(found) > 1:
            problems.append(f"duplicate slug {slug}: " + ", ".join(vault.relative(p) for p in found))

    for category_dir in vault.category_dirs():
        category = category_dir.name
        for path in sorted(category_dir.rglob("*")):
            relative = path.relative_to(category_dir)
            if any(part.startswith(".") for part in relative.parts):
                continue
            if path.is_dir():
                if all(p.name == ".DS_Store" for p in path.iterdir()):
                    problems.append(f"empty folder: {vault.relative(path)}")
                if (len(relative.parts) == 1 and category in config.ORGANIZE_CATEGORIES
                        and path.name != OTHER and path.name not in topic_names(tax, category)):
                    problems.append(f"folder is not a topic of {category}: {vault.relative(path)}")
            elif path.suffix == ".md" and len(relative.parts) > 2:
                problems.append(f"note deeper than one subfolder: {vault.relative(path)}")

    notes, _ = scan()
    counts = {category: Counter() for category in config.ORGANIZE_CATEGORIES}
    for note in notes:
        topic = note.meta.get("topic")
        if topic not in topic_names(tax, note.category):
            problems.append(f"no valid topic: {note.rel}" + (f" (topic '{topic}')" if topic else ""))
        else:
            counts[note.category][topic] += 1
        if note.meta.get("type") not in config.NOTE_TYPES:
            problems.append(f"no valid type: {note.rel}")
    for note in notes:
        topic = note.meta.get("topic")
        if topic in topic_names(tax, note.category):
            expected = target_path(note.category, note.slug, target_folder(topic, counts[note.category]))
            if note.rel != expected:
                problems.append(f"not at its derived path: {note.rel} (expected {expected})")
    return problems


def taxonomy_report():
    """kb --taxonomy: topics with counts, folders and definitions, then flags and problems."""
    tax = load_taxonomy()
    notes, _ = scan()
    lines = []
    flags = []
    for category in config.ORGANIZE_CATEGORIES:
        members = [n for n in notes if n.category == category]
        names = topic_names(tax, category)
        counts = Counter(n.meta.get("topic") for n in members if n.meta.get("topic") in names)
        lines.append(f"{category}  ({len(members)} notes, {len(names)} topics)")
        for topic in topics_of(tax, category):
            folder = target_folder(topic["name"], counts) if counts else None
            shown = {None: "-", "": "-", OTHER: f"{OTHER}/"}.get(folder, f"{folder}/")
            lines.append(f"  {counts[topic['name']]:>4}  {topic['name']:<36} {shown:<38} {topic.get('definition', '')}")
            if counts[topic["name"]] > config.TOPIC_WARN_MAX:
                flags.append(f"{category} / {topic['name']}: {counts[topic['name']]} notes, more than "
                             f"{config.TOPIC_WARN_MAX}; consider splitting it")
        if members and counts[GENERAL] > GENERAL_WARN_SHARE * len(members):
            flags.append(f"{category}: '{GENERAL}' holds {counts[GENERAL]} of {len(members)} notes "
                         f"(more than {GENERAL_WARN_SHARE:.0%})")
    lines.append("")
    problems = check_vault(tax)
    for flag in flags:
        lines.append(f"FLAG: {flag}")
    for problem in problems:
        lines.append(f"PROBLEM: {problem}")
    if not flags and not problems:
        lines.append("No flags, no problems.")
    elif problems:
        lines.append("Run kb --organize to give notes a topic and type and to move them to their folders.")
    return lines

"""Frontmatter of a note: the YAML block between two '---' lines at the top of the file.

CKE owns four keys (topic, type, module, source). Everything else in the block belongs
to the user (Obsidian properties, comments, lists), so the block is treated as raw lines:
only the owned keys are read, updated or inserted, and the block is never re-serialised.
No YAML library is needed for that.
"""

OWNED_KEYS = ("topic", "type", "module", "source")
QUOTED_KEYS = ("topic", "module")  # free text, always written in double quotes


def split(text):
    """(block, body) with block + body == text.

    A block exists only if the first line is exactly '---' and a later line is exactly '---'.
    The block includes both marker lines and the newline after the closing one.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        return "", text
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            block = "".join(lines[:i + 1])
            return block, text[len(block):]
    return "", text


def _key_of(line):
    """The key of a top-level 'key: value' line, or None."""
    if not line or line[0] in " \t#-" or ":" not in line:
        return None
    return line.split(":", 1)[0].strip()


def _is_continuation(line):
    """A line that belongs to the key above it: indented, or a '- item' of a block list."""
    return line[:1] in (" ", "\t") or line.startswith("- ") or line.rstrip("\r\n") == "-"


def _unquote(raw):
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        out, i = [], 1
        while i < len(value) - 1:
            if value[i] == "\\" and i + 1 < len(value) - 1:
                out.append(value[i + 1])
                i += 2
            else:
                out.append(value[i])
                i += 1
        return "".join(out)
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def read(block):
    """{key: value} for the owned keys that are present with a non-empty value."""
    values = {}
    for line in block.splitlines()[1:-1]:
        key = _key_of(line)
        if key in OWNED_KEYS and key not in values:
            value = _unquote(line.split(":", 1)[1])
            if value:
                values[key] = value
    return values


def format_line(key, value):
    if key in QUOTED_KEYS:
        escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
        return f'{key}: "{escaped}"\n'
    return f"{key}: {value}\n"


def set_keys(block, values):
    """Return the block with each owned key in `values` set, or removed when its value is None.

    Lines of other keys, comments and lists are kept as they are, in their order. A key that
    is already there is updated in place; a new key is added before the closing '---' in
    OWNED_KEYS order. With no lines left between the markers the result is "" (no block).
    """
    unknown = set(values) - set(OWNED_KEYS)
    if unknown:
        raise ValueError(f"not a key CKE owns: {', '.join(sorted(unknown))}")
    if block:
        lines = block.splitlines(keepends=True)
        opening, inner, closing = lines[0], lines[1:-1], lines[-1]
    else:
        opening, inner, closing = "---\n", [], "---\n"
    if inner and not inner[-1].endswith("\n"):
        inner[-1] += "\n"

    result, done, skipping = [], set(), False
    for line in inner:
        if skipping and _is_continuation(line):
            continue  # the old value of a key being replaced (e.g. a list under it)
        skipping = False
        key = _key_of(line)
        if key in values:
            skipping = True
            if key not in done and values[key] is not None:
                result.append(format_line(key, values[key]))
            done.add(key)
            continue
        result.append(line)
    for key in OWNED_KEYS:
        if key in values and key not in done and values[key] is not None:
            result.append(format_line(key, values[key]))

    if not any(line.strip() for line in result):
        return ""
    if not closing.endswith("\n"):
        closing += "\n"
    return opening + "".join(result) + closing

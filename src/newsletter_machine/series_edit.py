"""Comment-preserving edits to one part of a ``series/<slug>.yaml`` file.

Varun annotates series files by hand, so a status change rewrites only the lines it must. The
edit is a best effort on block-style YAML: callers parse the result and compare it with the
series they expect, and rewrite the whole file when the lines were written some other way.
"""

import json
import re
from collections.abc import Mapping

COMMENT = r"(?P<comment>[ \t]+#.*?)?[ \t]*$"
# a quoted scalar is matched whole, so a " # " inside it is not a comment; a plain value
# ends at the first " #", as in YAML
VALUE = r"""[ \t]*(?:'(?:[^'\n]|'')*'|"(?:[^"\\\n]|\\.)*"|[^\s#'"][^\n]*?)?"""


def part_block(text: str, number: int) -> tuple[int, int, str] | None:
    """``(start, end, key indent)`` of part ``number``'s block in block-style YAML."""
    start = re.search(rf"^([ \t]*)- number:[ \t]*{number}[ \t]*(?:#.*)?$", text, re.MULTILINE)
    if start is None:
        return None
    indent = start.group(1)
    # the next part, or a top-level key; a column-0 comment stays inside the block
    after = re.compile(rf"^(?:{indent}-[ \t]|[^\s#])", re.MULTILINE)
    end = after.search(text, start.end())
    return start.end(), end.start() if end else len(text), f"{indent}  "


def _line(key: str, field: str, value: str, comment: str | None) -> str:
    # JSON strings are valid YAML and quote anything odd (colons, hashes, quotes)
    return f"{key}{field}: {json.dumps(value, ensure_ascii=False)}{comment or ''}"


def _set_field(body: str, key: str, field: str, value: str) -> tuple[str, bool]:
    """Replace ``field``'s one-line value; False when the key is missing."""
    pattern = re.compile(rf"^{key}{re.escape(field)}:{VALUE}{COMMENT}", re.MULTILINE)
    body, count = pattern.subn(lambda m: _line(key, field, value, m.group("comment")), body, 1)
    return body, bool(count)


def edit_part(
    text: str,
    number: int,
    *,
    statuses: tuple[str, ...],
    status: str,
    fields: Mapping[str, str],
) -> str | None:
    """Set part ``number``'s status (only from one of ``statuses``) and ``fields``; a missing
    field key is added after the status line, in the order given. None when the part or a
    matching status line is not found."""
    block = part_block(text, number)
    if block is None:
        return None
    start, end, key = block
    body = text[start:end]
    missing: list[str] = []
    for field, value in fields.items():
        body, found = _set_field(body, key, field, value)
        if not found:
            missing.append(_line(key, field, value, None))
    choices = "|".join(re.escape(s) for s in statuses)
    status_line = re.compile(rf"^{key}status:[ \t]*(['\"]?)(?:{choices})\1{COMMENT}", re.MULTILINE)
    added = "".join(f"\n{line}" for line in missing)
    body, flipped = status_line.subn(
        lambda m: f"{key}status: {status}{m.group('comment') or ''}{added}", body, 1
    )
    return text[:start] + body + text[end:] if flipped else None

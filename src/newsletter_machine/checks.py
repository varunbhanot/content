"""Checklist items that code checks exactly: banned patterns, word count, paragraph length."""

import re
from dataclasses import dataclass
from typing import Literal

from newsletter_machine.checklist import ChecklistItem

CheckStatus = Literal["pass", "fail", "not-checked"]
CheckedBy = Literal["code", "critic"]

SOURCES_HEADING = re.compile(r"^#{1,6}\s+Sources\s*$", re.MULTILINE | re.IGNORECASE)
LINK_TARGET = re.compile(r"\]\([^)]*\)")
WORD = re.compile(r"[^\W_]+(?:['’-][^\W_]+)*")
BARE_URL = re.compile(r"https?://\S+")
VARUN_MARKER = re.compile(r"\[VARUN:[^\]]*\]")
TITLE_LINE = re.compile(r"^# .*$", re.MULTILINE)
LIST_MARKER = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
SKIPPED_BLOCK_PREFIXES = ("#", "|", "![", "[![")
FENCE = "```"
QUOTE_CONTEXT_CHARS = 60
QUOTE_PREVIEW_CHARS = 80


@dataclass(frozen=True)
class CheckResult:
    """The verdict on one checklist item, from code or from the critic model."""

    item: ChecklistItem
    status: CheckStatus
    quotes: tuple[str, ...] = ()
    fix: str = ""
    checked_by: CheckedBy = "code"


def body_without_sources(draft: str) -> str:
    """The draft up to its ``## Sources`` heading (the list is not prose)."""
    match = SOURCES_HEADING.search(draft)
    return draft[: match.start()] if match else draft


def reader_text(text: str) -> str:
    """What a reader sees: no link targets, bare URLs or ``[VARUN: ...]`` placeholders."""
    return VARUN_MARKER.sub("", BARE_URL.sub("", LINK_TARGET.sub("]", text)))


def count_words(text: str) -> int:
    """Words a reader sees: URLs and Markdown symbols are not words; "end-to-end" is one."""
    return len(WORD.findall(reader_text(text)))


def prose_words(draft: str) -> int:
    """Word count of the draft body: no title, no Sources list, no placeholders."""
    return count_words(TITLE_LINE.sub("", body_without_sources(draft)))


def _blocks(text: str) -> list[str]:
    """Blank-line separated blocks; code fences dropped; a heading line is a block of its own."""
    blocks: list[str] = []
    current: list[str] = []
    in_fence = False
    for line in text.splitlines():
        is_fence = line.strip().startswith(FENCE)
        if is_fence or not line.strip() or line.lstrip().startswith("#"):
            if current and not in_fence:
                blocks.append("\n".join(current))
            current = []
            if is_fence:
                in_fence = not in_fence
            elif not in_fence and line.strip():
                blocks.append(line)  # heading
            continue
        if not in_fence:
            current.append(line)
    if current and not in_fence:
        blocks.append("\n".join(current))
    return blocks


def _list_items(lines: list[str]) -> list[str]:
    """One string per list item; indented continuation lines belong to the item above."""
    items: list[list[str]] = []
    for line in lines:
        if LIST_MARKER.match(line) or not items:
            items.append([LIST_MARKER.sub("", line).strip()])
        else:
            items[-1].append(line.strip())
    return [" ".join(item) for item in items]


def paragraphs(text: str) -> tuple[str, ...]:
    """Prose paragraphs; each list item counts alone; headings, code and tables are skipped."""
    result: list[str] = []
    for block in _blocks(text):
        if block.lstrip().startswith(SKIPPED_BLOCK_PREFIXES):
            continue
        lines = block.splitlines()
        first_item = next((i for i, line in enumerate(lines) if LIST_MARKER.match(line)), None)
        intro = lines if first_item is None else lines[:first_item]
        if intro:  # a list may follow its intro sentence with no blank line
            result.append(" ".join(line.strip() for line in intro))
        if first_item is not None:
            result.extend(_list_items(lines[first_item:]))
    return tuple(result)


def _context(text: str, start: int, end: int) -> str:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    line_end = len(text) if line_end == -1 else line_end
    left = max(line_start, start - QUOTE_CONTEXT_CHARS)
    right = min(line_end, end + QUOTE_CONTEXT_CHARS)
    prefix = "…" if left > line_start else ""
    suffix = "…" if right < line_end else ""
    return f"{prefix}{text[left:right].strip()}{suffix}"


def _pattern_hits(item: ChecklistItem, body: str) -> list[str]:
    return [_context(body, m.start(), m.end()) for p in item.patterns for m in p.finditer(body)]


def _paragraph_hits(item: ChecklistItem, body: str) -> list[str]:
    limit = item.max_paragraph_chars
    if not limit:
        return []
    return [
        f"{para[:QUOTE_PREVIEW_CHARS]}… ({len(para)} chars)"
        for para in paragraphs(body)
        if len(para) > limit
    ]


def _word_range_miss(item: ChecklistItem, draft: str) -> str | None:
    if item.word_range is None:
        return None
    low, high = item.word_range
    words = prose_words(draft)
    return None if low <= words <= high else f"{words} words (target {low} to {high})"


def _fix(item: ChecklistItem, pattern_hits: int, paragraph_hits: int, miss: str | None) -> str:
    steps = []
    if miss and item.word_range:
        steps.append(f"Bring the body within {item.word_range[0]} to {item.word_range[1]} words.")
    if pattern_hits:
        steps.append("Rewrite the quoted passages without the flagged wording.")
    if paragraph_hits:
        steps.append(f"Split paragraphs longer than {item.max_paragraph_chars} characters.")
    return " ".join(steps)


def run_mechanical(item: ChecklistItem, draft: str) -> CheckResult:
    """Check a mechanical item exactly; fails when hits exceed ``item.allowed``."""
    if not item.is_mechanical:
        raise ValueError(f"Checklist item {item.id!r} is not a mechanical check.")
    body = reader_text(body_without_sources(draft))
    pattern_hits, paragraph_hits = _pattern_hits(item, body), _paragraph_hits(item, body)
    miss = _word_range_miss(item, draft)
    if len(pattern_hits) + len(paragraph_hits) <= item.allowed and miss is None:
        return CheckResult(item=item, status="pass")
    quotes = ((miss,) if miss else ()) + tuple(pattern_hits + paragraph_hits)
    fix = _fix(item, len(pattern_hits), len(paragraph_hits), miss)
    return CheckResult(item=item, status="fail", quotes=quotes, fix=fix)

"""Final files for ``newsletter-machine issue``: the draft's Sources list and the editor notes."""

import html
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from newsletter_machine.checks import SOURCES_HEADING
from newsletter_machine.sources import SourceDoc, extract_urls, normalize_url
from newsletter_machine.workspace import (
    BRIEFS_DIR,
    CRITIQUES_DIR,
    ERRORS_DIR,
    PLAN_FILE,
    RESEARCH_NOTES,
    Files,
    file_text,
    versioned,
)
from newsletter_machine.writer import usable_sources

SOURCES_TITLE = "## Sources"
LINK_TEXT_SPECIALS = re.compile(r"([\[\]\\])")
HEADING_LINE = re.compile(r"^(#{1,5}) ", re.MULTILINE)
LIST_LINE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s|^\s{2,}\S")  # item or indented continuation


@dataclass(frozen=True)
class SourcesFix:
    draft: str
    dropped: tuple[str, ...]  # URLs the writer listed that are not usable ingested sources


def _link(doc: SourceDoc) -> str:
    return f"- [{LINK_TEXT_SPECIALS.sub(r'\\\1', doc.title)}]({doc.url})"


def _cited(section: str, docs: tuple[SourceDoc, ...]) -> tuple[list[SourceDoc], list[str]]:
    by_url = {normalize_url(doc.url): doc for doc in docs}
    kept: dict[str, SourceDoc] = {}
    dropped: list[str] = []
    for url in extract_urls(html.unescape(section)):  # source tags showed URLs html-escaped
        key = normalize_url(url)
        if key in by_url:
            kept.setdefault(key, by_url[key])
        elif url not in dropped:
            dropped.append(url)
    return list(kept.values()), dropped


def _split_section(section: str) -> tuple[str, str]:
    """``(list, tail)``: the Sources heading through its list, then anything after the list.

    Lines before the first list item (e.g. "What I read:") belong to the Sources section;
    with no list at all, the whole section is the writer's Sources text and there is no tail.
    """
    lines = section.splitlines()
    start = next((i for i, line in enumerate(lines[1:], 1) if LIST_LINE.match(line)), None)
    if start is None:
        return section, ""
    end = start
    while end < len(lines) and (not lines[end].strip() or LIST_LINE.match(lines[end])):
        end += 1
    return "\n".join(lines[:end]), "\n".join(lines[end:]).strip()


def _split_tail(tail: str) -> tuple[str, str]:
    """``(linked, kept)``: tail paragraphs holding a URL join the Sources list; the rest stay."""
    blocks = [block for block in re.split(r"\n\s*\n", tail) if block.strip()]
    linked = [block for block in blocks if extract_urls(html.unescape(block))]
    kept = [block for block in blocks if block not in linked]
    return "\n\n".join(linked), "\n\n".join(kept)


def normalise_sources(draft: str, docs: Iterable[SourceDoc]) -> SourcesFix:
    """Rebuild ``## Sources`` from ingested sources only, titled as ingested.

    Keeps the writer's order; drops links that are not usable sources; lists every usable
    source when the writer cited none (or wrote no Sources section). Text after the list
    (a sign-off, a ``[VARUN: ...]`` marker) stays after it, unless a paragraph holds links:
    those are Sources too, so they are rebuilt or dropped like the list.
    """
    usable = usable_sources(docs)
    match = SOURCES_HEADING.search(draft)
    body = (draft[: match.start()] if match else draft).rstrip()
    listed, tail = _split_section(draft[match.start() :]) if match else ("", "")
    linked, tail = _split_tail(tail)
    cited, dropped = _cited(f"{listed}\n{linked}", usable)
    links = "\n".join(_link(doc) for doc in (cited or usable))
    after = f"\n{tail}\n" if tail else ""
    return SourcesFix(f"{body}\n\n{SOURCES_TITLE}\n\n{links}\n{after}", tuple(dropped))


@dataclass(frozen=True)
class NotesInput:
    draft_name: str
    final_version: int
    files: Mapping[str, Any]
    docs: tuple[SourceDoc, ...]
    summary: str
    dropped: tuple[str, ...]
    final_summary: Mapping[str, Any] | None = None  # the final version's critique counts
    series: str = ""  # the series part this draft is, blank for a plain issue
    parked: tuple[str, ...] = ()  # one line per source the relevance filter set aside
    unchecked: tuple[str, ...] = ()  # sources kept because their relevance check failed


def critique_summary(files: Files, version: int) -> dict[str, Any] | None:
    """The critic's counts for one version, or None when it is missing or malformed."""
    raw = file_text(files, versioned(CRITIQUES_DIR, version, "json"))
    try:
        data = json.loads(raw or "")
    except ValueError:
        return None
    keys = ("passed", "failed", "not_checked", "failed_items")
    return data if isinstance(data, dict) and all(k in data for k in keys) else None


def _critique_line(files: Files, version: int, override: Mapping[str, Any] | None = None) -> str:
    data = override or critique_summary(files, version)
    if data is None:
        return f"- Draft v{version}: no critique summary"
    failed = ", ".join(f"`{item}`" for item in data["failed_items"])
    detail = f" ({failed})" if failed else ""
    return (
        f"- Draft v{version}: {data['passed']} passed, {data['failed']} failed{detail}, "
        f"{data['not_checked']} not checked"
    )


def error_lines(files: Files) -> list[str]:
    """One line per sub-agent failure recorded under ``/errors``."""
    prefix = f"{ERRORS_DIR}/"
    return [
        f"{path.removeprefix(prefix).removesuffix('.md')} failed: {file_text(files, path)}"
        for path in sorted(files)
        if path.startswith(prefix)
    ]


def _source_lines(docs: tuple[SourceDoc, ...], dropped: tuple[str, ...]) -> list[str]:
    lines = [f"- Skipped: {d.title} ({d.url}): {d.detail}" for d in docs if d.status == "failed"]
    lines += [f"- Fallback text only: {d.title} ({d.url})" for d in docs if d.status == "fallback"]
    lines += [f"- Dropped from Sources (not an ingested source): {url}" for url in dropped]
    return lines or ["- Every source ingested and every cited link matched."]


def _numbers(docs: tuple[SourceDoc, ...]) -> str:
    """``[n]`` as the agents use it (usable sources only), so a claim traces to its source."""
    lines = [f"- [{i}] {d.title} ({d.url})" for i, d in enumerate(usable_sources(docs), start=1)]
    return "\n".join(lines) or "(no usable sources)"


def _research(files: Files) -> str:
    notes = file_text(files, RESEARCH_NOTES)
    if not notes:
        return "(no research notes)"
    body = notes.split("\n", 1)[1] if notes.startswith("# ") else notes
    return HEADING_LINE.sub(r"#\1 ", body.strip())


def _section(title: str, body: str) -> str:
    return f"## {title}\n\n{body.strip()}"


def _listed(title: str, lines: tuple[str, ...]) -> str:
    return f"{title}:\n" + "\n".join(lines) if lines else f"{title}: none"


def _series(notes: NotesInput) -> list[str]:
    if not notes.series:
        return []
    body = [notes.series, _listed("Parked (off-topic, not used)", notes.parked)]
    if notes.unchecked:
        body.append(_listed("Unchecked (relevance check failed, kept)", notes.unchecked))
    return [_section("Series", "\n\n".join(body))]


def render_notes(notes: NotesInput) -> str:
    """Everything behind the draft: run log, source problems, plan, last brief, research."""
    files, version = notes.files, notes.final_version
    run_log = [_critique_line(files, v) for v in range(1, version)]
    run_log.append(_critique_line(files, version, notes.final_summary))
    run_log += [f"- {line}" for line in error_lines(files)]
    brief = file_text(files, versioned(BRIEFS_DIR, version, "md"))
    parts = [
        f"# Editor notes: {notes.draft_name}\n\nFinal draft: v{version}.",
        *_series(notes),
        _section("Editor's summary", notes.summary or "(no summary)"),
        _section("Run log", "\n".join(run_log)),
        _section("Sources", "\n".join(_source_lines(notes.docs, notes.dropped))),
        _section("Source numbers ([n] in the plan, briefs and notes)", _numbers(notes.docs)),
        _section("Plan", file_text(files, PLAN_FILE) or "(no plan written)"),
        _section("Final brief", brief or "(no brief)"),
        _section("Research notes", _research(files)),
    ]
    return "\n\n".join(parts) + "\n"

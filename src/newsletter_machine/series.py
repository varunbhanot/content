"""A planned multi-part series: the ``series/<slug>.yaml`` schema, validated on every load.

Varun edits these files by hand, so every field is checked and an error names the file, the
part and the field. Fields used by later phases (``draft``, ``url``, ``summary``, ``teaser``)
are optional and only type-checked here. ``revisions`` (optional) records each time the
remaining outline was revised; files written before it existed load unchanged.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal, get_args
from urllib.parse import urlsplit

from newsletter_machine.validation import is_int, non_empty_text, one_of

SeriesStatus = Literal["proposed", "approved", "complete"]
Access = Literal["free", "paid"]
PartStatus = Literal["planned", "drafted", "published"]

SERIES_FIELDS = ("topic", "status", "parts", "revisions")  # revisions is optional
PART_REQUIRED = ("number", "title", "question", "brief", "arc", "access", "status", "sources")
PART_OPTIONAL = ("thin", "needs", "draft", "url", "summary", "teaser")
SOURCE_FIELDS = frozenset({"title", "url"})
REVISION_FIELDS = frozenset({"date", "reason", "changes"})
MIN_ARC_STEPS = 2
SLUG_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)  # as ingest accepts them
ARC_SEPARATOR = " -> "
THIN_DEFAULT_NOTE = "needs more reading"


@dataclass(frozen=True)
class SourceRef:
    """A saved source that supports a part (title and URL as ingested)."""

    title: str
    url: str


@dataclass(frozen=True)
class SeriesPart:
    number: int
    title: str
    question: str  # the one reader question this part answers
    brief: str
    arc: tuple[str, ...]  # steps from basic to advanced, within this part
    access: Access
    status: PartStatus
    sources: tuple[SourceRef, ...]  # source coverage
    thin: bool = False  # True when the part needs more reading
    needs: str = ""  # what reading is missing
    draft: str | None = None  # later phases: draft path, live URL, summary, teaser promised
    url: str | None = None
    summary: str = ""
    teaser: str = ""


@dataclass(frozen=True)
class Revision:
    """One revision of the remaining outline: when, why, and what changed."""

    date: str  # ISO date, YYYY-MM-DD
    reason: str
    changes: tuple[str, ...]


@dataclass(frozen=True)
class Series:
    topic: str
    status: SeriesStatus
    parts: tuple[SeriesPart, ...]
    revisions: tuple[Revision, ...] = ()  # oldest first


def is_web_url(value: str) -> bool:
    """An absolute http(s) address with a host, and no spaces."""
    if not URL_PATTERN.fullmatch(value):
        return False
    try:
        return bool(urlsplit(value).hostname)
    except ValueError:  # e.g. an unclosed IPv6 bracket
        return False


def is_slug(value: str) -> bool:
    """Kebab-case: lowercase letters and digits joined by single hyphens."""
    return bool(SLUG_PATTERN.fullmatch(value))


def _optional_text(raw: Mapping[str, Any], name: str, where: str) -> str:
    value = raw.get(name, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{where}: '{name}' must be text")
    return value.strip()


def _optional_path(raw: Mapping[str, Any], where: str) -> str | None:
    value = raw.get("draft")
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str):
        raise ValueError(f"{where}: 'draft' must be text or empty")
    return value.strip()


def _optional_url(raw: Mapping[str, Any], where: str) -> str | None:
    value = raw.get("url")
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str) or not is_web_url(value.strip()):
        raise ValueError(f"{where}: 'url' must be an http(s) address or empty (got {value!r})")
    return value.strip()


def _arc(raw: Mapping[str, Any], where: str) -> tuple[str, ...]:
    value = raw.get("arc")
    if (
        not isinstance(value, list)
        or len(value) < MIN_ARC_STEPS
        or not all(isinstance(v, str) and v.strip() for v in value)
    ):
        raise ValueError(
            f"{where}: 'arc' must list at least {MIN_ARC_STEPS} non-empty steps, basic to advanced"
        )
    return tuple(step.strip() for step in value)


def _source(value: object, where: str, index: int) -> SourceRef:
    valid = (
        isinstance(value, dict)
        and set(value) == SOURCE_FIELDS
        and isinstance(value["title"], str)
        and value["title"].strip()
        and isinstance(value["url"], str)
        and URL_PATTERN.fullmatch(value["url"].strip())
    )
    if not valid:
        raise ValueError(f"{where}: source #{index} must have only 'title' and an http(s) 'url'")
    assert isinstance(value, dict)  # narrowed above, for mypy
    return SourceRef(title=value["title"].strip(), url=value["url"].strip())


def _sources(raw: Mapping[str, Any], where: str) -> tuple[SourceRef, ...]:
    value = raw.get("sources")
    if not isinstance(value, list):
        raise ValueError(f"{where}: 'sources' must be a list (empty when none)")
    return tuple(_source(item, where, index) for index, item in enumerate(value, start=1))


def _thin(raw: Mapping[str, Any], where: str) -> bool:
    value = raw.get("thin", False)
    if not isinstance(value, bool):
        raise ValueError(f"{where}: 'thin' must be true or false (got {value!r})")
    return value


def _check_fields(raw: Mapping[str, Any], where: str) -> None:
    unknown = set(raw) - set(PART_REQUIRED) - set(PART_OPTIONAL)
    if unknown:
        raise ValueError(f"{where}: unknown field(s) {sorted(unknown)}")
    missing = [name for name in PART_REQUIRED if name not in raw]
    if missing:
        raise ValueError(f"{where}: missing field(s) {missing}")


def _parse_part(raw: object, path: str, index: int) -> SeriesPart:
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: part #{index} is not a mapping")
    number = raw.get("number")
    if not is_int(number) or number != index:
        raise ValueError(
            f"{path}: part #{index}: 'number' must be {index} (parts are numbered 1, 2, 3 "
            f"in order; got {number!r})"
        )
    where = f"{path}: part {index}"
    _check_fields(raw, where)
    return SeriesPart(
        number=index,
        title=non_empty_text(raw, "title", where),
        question=non_empty_text(raw, "question", where),
        brief=non_empty_text(raw, "brief", where),
        arc=_arc(raw, where),
        access=one_of(where, "access", raw.get("access"), get_args(Access)),
        status=one_of(where, "status", raw.get("status"), get_args(PartStatus)),
        sources=_sources(raw, where),
        thin=_thin(raw, where),
        needs=_optional_text(raw, "needs", where),
        draft=_optional_path(raw, where),
        url=_optional_url(raw, where),
        summary=_optional_text(raw, "summary", where),
        teaser=_optional_text(raw, "teaser", where),
    )


def _revision_date(value: object, where: str) -> str:
    # YAML reads an unquoted 2026-11-11 as a date; a time of day is not a revision date
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip()).isoformat()
        except ValueError:
            pass
    raise ValueError(f"{where}: 'date' must be a date like 2026-11-11 (got {value!r})")


def _changes(value: object, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise ValueError(f"{where}: 'changes' must be a list of non-empty lines")
    return tuple(line.strip() for line in value)


def _revision(raw: object, path: str, index: int) -> Revision:
    where = f"{path}: revision #{index}"
    if not isinstance(raw, dict) or set(raw) != REVISION_FIELDS:
        raise ValueError(f"{where} must have only 'date', 'reason' and 'changes'")
    return Revision(
        date=_revision_date(raw["date"], where),
        reason=non_empty_text(raw, "reason", where),
        changes=_changes(raw["changes"], where),
    )


def _revisions(data: Mapping[str, Any], path: str) -> tuple[Revision, ...]:
    value = data.get("revisions")
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{path}: 'revisions' must be a list (or left out)")
    return tuple(_revision(raw, path, index) for index, raw in enumerate(value, start=1))


def parse_series(data: object, path: str) -> Series:
    """Validate a parsed YAML document; ``ValueError`` names ``path``, the part and the field."""
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping with 'topic', 'status' and 'parts'")
    unknown = set(data) - set(SERIES_FIELDS)
    if unknown:
        raise ValueError(f"{path}: unknown field(s) {sorted(unknown)}")
    raw_parts = data.get("parts")
    if not isinstance(raw_parts, list) or not raw_parts:
        raise ValueError(f"{path}: 'parts' must be a non-empty list")
    return Series(
        topic=non_empty_text(data, "topic", path),
        status=one_of(path, "status", data.get("status"), get_args(SeriesStatus)),
        parts=tuple(_parse_part(raw, path, index) for index, raw in enumerate(raw_parts, start=1)),
        revisions=_revisions(data, path),
    )


def _part_mapping(part: SeriesPart) -> dict[str, Any]:
    return {
        "number": part.number,
        "title": part.title,
        "question": part.question,
        "brief": part.brief,
        "arc": list(part.arc),
        "access": part.access,
        "status": part.status,
        "sources": [{"title": s.title, "url": s.url} for s in part.sources],
        "thin": part.thin,
        "needs": part.needs,
        "draft": part.draft,
        "url": part.url,
        "summary": part.summary,
        "teaser": part.teaser,
    }


def series_to_mapping(series: Series) -> dict[str, Any]:
    """The YAML-ready form; ``parse_series`` reads it back to an equal ``Series``. A series
    never revised has no ``revisions`` key, as before revisions existed."""
    mapping: dict[str, Any] = {
        "topic": series.topic,
        "status": series.status,
        "parts": [_part_mapping(part) for part in series.parts],
    }
    if series.revisions:
        mapping["revisions"] = [
            {"date": r.date, "reason": r.reason, "changes": list(r.changes)}
            for r in series.revisions
        ]
    return mapping


def _sources_line(sources: Sequence[SourceRef]) -> str:
    listed = "; ".join(f"{s.title} ({s.url})" for s in sources) or "none"
    return f"  Sources ({len(sources)}): {listed}"


def _part_lines(part: SeriesPart) -> list[str]:
    flag = f"  THIN: {part.needs or THIN_DEFAULT_NOTE}" if part.thin else ""
    lines = [
        f"Part {part.number} [{part.access}, {part.status}] {part.title}{flag}",
        f"  Question: {part.question}",
        f"  Arc: {ARC_SEPARATOR.join(part.arc)}",
        f"  Brief: {part.brief}",
        _sources_line(part.sources),
    ]
    if part.draft:
        lines.append(f"  Draft: {part.draft}")
    if part.url:
        lines.append(f"  URL: {part.url}")
    if part.summary:
        lines.append(f"  Summary: {part.summary}")
    if part.teaser:
        lines.append(f"  Teaser: {part.teaser}")
    return lines


def format_outline(series: Series, slug: str) -> str:
    """A plain-text outline for the terminal: one block per part."""
    lines = [f"Series '{slug}' ({series.status}): {series.topic}"]
    for part in series.parts:
        lines.extend(_part_lines(part))
    lines.extend(f"Revised {r.date}: {r.reason}" for r in series.revisions)
    return "\n".join(lines) + "\n"

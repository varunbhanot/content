"""Source records and pure link parsing (URLs, YouTube ids, --since, links files)."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SourceKind = Literal["article", "youtube"]
SourceStatus = Literal["ok", "fallback", "failed"]

URL_PATTERN = re.compile(r"https?://[^\s<>\"'\]]+", re.IGNORECASE)
TRAILING_PUNCTUATION = ".,;:!?"
TRACKING_PARAMS = frozenset({"fbclid", "gclid", "mc_cid", "mc_eid", "ref_src"})
YOUTUBE_HOSTS = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"})
YOUTUBE_PATH_PREFIXES = ("/shorts/", "/embed/", "/live/")
VIDEO_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{11}")
SINCE_PATTERN = re.compile(r"(\d+)([hdw])")
SINCE_UNITS = {"h": "hours", "d": "days", "w": "weeks"}
COMMENT_PREFIX = "#"


@dataclass(frozen=True)
class InboxLink:
    """A link Varun saved, with his optional one-line note."""

    url: str
    note: str
    subject: str
    received_at: datetime


@dataclass(frozen=True)
class SourceDoc:
    """Clean text for one source; ``detail`` explains a fallback or failure."""

    url: str
    title: str
    kind: SourceKind
    status: SourceStatus
    text: str
    note: str = ""
    detail: str = ""


def _trim_url(url: str) -> str:
    """Drop trailing punctuation and unbalanced closing parens (``(see https://x.com/a)``)."""
    trimmed = url.rstrip(TRAILING_PUNCTUATION)
    while trimmed.endswith(")") and trimmed.count(")") > trimmed.count("("):
        trimmed = trimmed[:-1].rstrip(TRAILING_PUNCTUATION)
    return trimmed


def failed_doc(link: InboxLink, kind: SourceKind, detail: str) -> SourceDoc:
    """The one shape of a failed source: body empty, reason in ``detail``.

    The page title is unknown, so the title falls back to Varun's note, then the email
    subject, then the URL.
    """
    return SourceDoc(
        url=link.url,
        title=link.note.strip() or link.subject.strip() or link.url,
        kind=kind,
        status="failed",
        text="",
        note=link.note,
        detail=detail,
    )


def extract_urls(text: str) -> tuple[str, ...]:
    """Return http(s) URLs in ``text`` in order, without trailing punctuation or duplicates."""
    urls = (_trim_url(match) for match in URL_PATTERN.findall(text))
    return tuple(dict.fromkeys(url for url in urls if url))


def _is_tracking_param(name: str) -> bool:
    return name.lower().startswith("utm_") or name.lower() in TRACKING_PARAMS


def normalize_url(url: str) -> str:
    """Lowercase scheme/host and drop the fragment and tracking query params."""
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)]
    kept = urlencode([(k, v) for k, v in query if not _is_tracking_param(k)])
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, kept, ""))


def dedupe_by_url(links: Iterable[InboxLink]) -> tuple[InboxLink, ...]:
    """Keep the first link for each normalised URL (the key only; URLs stay as written)."""
    seen: dict[str, InboxLink] = {}
    for link in links:
        seen.setdefault(normalize_url(link.url), link)
    return tuple(seen.values())


def _candidate_video_id(host: str, path: str, query: str) -> str | None:
    if host == "youtu.be":
        return path.lstrip("/").split("/")[0]
    if host not in YOUTUBE_HOSTS:
        return None
    if path == "/watch":
        return dict(parse_qsl(query)).get("v")
    for prefix in YOUTUBE_PATH_PREFIXES:
        if path.startswith(prefix):
            return path.removeprefix(prefix).split("/")[0]
    return None


def youtube_video_id(url: str) -> str | None:
    """Return the 11-character video id for a YouTube video URL, else None."""
    parts = urlsplit(url)
    candidate = _candidate_video_id(parts.netloc.lower(), parts.path, parts.query)
    if candidate and VIDEO_ID_PATTERN.fullmatch(candidate):
        return candidate
    return None


def parse_since(value: str, now: datetime) -> datetime:
    """Parse ``Nh``/``Nd``/``Nw`` (relative to ``now``) or ``YYYY-MM-DD`` (UTC midnight)."""
    match = SINCE_PATTERN.fullmatch(value.strip())
    if match:
        amount = int(match.group(1))
        try:
            if amount > 0:
                return now - timedelta(**{SINCE_UNITS[match.group(2)]: amount})
        except OverflowError:
            pass
    else:
        try:
            return datetime.strptime(value.strip(), "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            pass
    raise ValueError(f"since must look like 7d, 24h, 2w or YYYY-MM-DD (got {value!r})")


def _parse_links_line(path: Path, number: int, line: str, now: datetime) -> InboxLink:
    url, *rest = line.split(maxsplit=1)
    note = rest[0] if rest else ""
    if not URL_PATTERN.fullmatch(url):
        raise ValueError(f"{path.name}:{number}: expected 'URL [note]', got {line!r}")
    return InboxLink(url=url, note=note.strip(), subject="", received_at=now)


def read_links_file(path: Path, now: datetime) -> tuple[InboxLink, ...]:
    """Read ``URL [note]`` lines; blank lines and ``#`` comments are skipped."""
    lines = path.read_text(encoding="utf-8").splitlines()
    links = (
        _parse_links_line(path, number, line.strip(), now)
        for number, line in enumerate(lines, start=1)
        if line.strip() and not line.strip().startswith(COMMENT_PREFIX)
    )
    return dedupe_by_url(links)

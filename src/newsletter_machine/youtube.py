"""YouTube ingestion: transcript first, then a clearly marked description fallback."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import requests
from trafilatura.metadata import extract_metadata
from youtube_transcript_api import YouTubeTranscriptApi

from newsletter_machine.sources import InboxLink, SourceDoc
from newsletter_machine.web import HtmlFetcher

logger = logging.getLogger(__name__)

TranscriptFetcher = Callable[[str], str]

# EU IPs get redirected to consent.youtube.com; its title is not the video's.
CONSENT_TITLE_PREFIX = "Before you continue"
WATCH_URL = "https://www.youtube.com/watch?v={video_id}"
UNAVAILABLE_TEMPLATE = (
    "Transcript unavailable ({reason}). "
    "Paste a transcript manually if this video matters for the issue."
)


@dataclass(frozen=True)
class VideoMeta:
    title: str
    description: str


class TimeoutSession(requests.Session):
    """``requests`` has no default timeout; this applies one to every request."""

    def __init__(self, timeout: float) -> None:
        super().__init__()
        self._timeout = timeout

    def request(  # type: ignore[override]
        self, method: str | bytes, url: str | bytes, **kwargs: Any
    ) -> requests.Response:
        kwargs.setdefault("timeout", self._timeout)
        return super().request(method, url, **kwargs)


def make_transcript_fetcher(languages: tuple[str, ...], *, timeout: float) -> TranscriptFetcher:
    """Return ``fetch(video_id) -> text`` preferring ``languages`` in order."""

    api = YouTubeTranscriptApi(http_client=TimeoutSession(timeout))

    def fetch(video_id: str) -> str:
        snippets = api.fetch(video_id, languages=languages)
        return " ".join(s.text.strip() for s in snippets if s.text.strip())

    return fetch


def _video_meta(video_id: str, fetch_html: HtmlFetcher) -> VideoMeta:
    """Best-effort title/description from the watch page's Open Graph tags."""
    placeholder = VideoMeta(title=f"YouTube video {video_id}", description="")
    watch_url = WATCH_URL.format(video_id=video_id)
    try:
        meta = extract_metadata(fetch_html(watch_url), default_url=watch_url)
    except Exception as exc:  # metadata is best-effort; never lose the transcript over it
        logger.warning("Could not read watch page for %s: %s", video_id, exc)
        return placeholder
    if meta.title and meta.title.startswith(CONSENT_TITLE_PREFIX):
        return placeholder
    return VideoMeta(
        title=meta.title or placeholder.title, description=(meta.description or "").strip()
    )


def _fallback(link: InboxLink, meta: VideoMeta, reason: str) -> SourceDoc:
    notice = UNAVAILABLE_TEMPLATE.format(reason=reason)
    text = f"{notice}\n\nVideo description:\n{meta.description}" if meta.description else notice
    return SourceDoc(
        url=link.url,
        title=meta.title,
        kind="youtube",
        status="fallback",
        text=text,
        note=link.note,
        detail=f"transcript unavailable: {reason}",
    )


def ingest_youtube(
    link: InboxLink,
    video_id: str,
    fetch_transcript: TranscriptFetcher,
    fetch_html: HtmlFetcher,
) -> SourceDoc:
    """Transcript when available; otherwise description + an explicit 'unavailable' notice."""
    meta = _video_meta(video_id, fetch_html)
    try:
        transcript = fetch_transcript(video_id).strip()
    except Exception as exc:  # library errors, raw requests errors, bad XML: all -> fallback
        logger.warning("No transcript for %s: %s", video_id, type(exc).__name__)
        return _fallback(link, meta, type(exc).__name__)
    if not transcript:
        return _fallback(link, meta, "empty transcript")
    return SourceDoc(
        url=link.url, title=meta.title, kind="youtube", status="ok", text=transcript, note=link.note
    )

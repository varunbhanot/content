from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
import requests
from youtube_transcript_api import RequestBlocked, TranscriptsDisabled

from newsletter_machine import youtube
from newsletter_machine.sources import InboxLink
from newsletter_machine.web import FetchError
from newsletter_machine.youtube import ingest_youtube, make_transcript_fetcher

VIDEO_ID = "dQw4w9WgXcQ"
LINK = InboxLink(
    url=f"https://youtu.be/{VIDEO_ID}",
    note="watch the eval part",
    subject="",
    received_at=datetime(2026, 11, 1, tzinfo=UTC),
)
WATCH_HTML = """<html><head><title>Evals in prod - YouTube</title>
<meta property="og:title" content="Evals in prod">
<meta property="og:description" content="A talk about shipping evals.">
</head><body></body></html>"""


def _watch_page(url: str) -> str:
    assert url == f"https://www.youtube.com/watch?v={VIDEO_ID}"
    return WATCH_HTML


def test_ingest_youtube_uses_transcript_and_page_title() -> None:
    doc = ingest_youtube(LINK, VIDEO_ID, lambda vid: "hello and welcome", _watch_page)
    assert doc.status == "ok"
    assert doc.kind == "youtube"
    assert doc.title == "Evals in prod"
    assert doc.text == "hello and welcome"
    assert doc.note == "watch the eval part"


@pytest.mark.parametrize("error", [TranscriptsDisabled(VIDEO_ID), RequestBlocked(VIDEO_ID)])
def test_ingest_youtube_falls_back_to_description_when_transcript_unavailable(
    error: Exception,
) -> None:
    def no_transcript(video_id: str) -> str:
        raise error

    doc = ingest_youtube(LINK, VIDEO_ID, no_transcript, _watch_page)
    assert doc.status == "fallback"
    assert doc.title == "Evals in prod"
    assert "A talk about shipping evals." in doc.text
    assert "Transcript unavailable" in doc.text
    assert type(error).__name__ in doc.detail


def test_ingest_youtube_uses_placeholder_title_when_page_fetch_fails() -> None:
    def no_page(url: str) -> str:
        raise FetchError("HTTP 429")

    doc = ingest_youtube(LINK, VIDEO_ID, lambda vid: "transcript text", no_page)
    assert doc.status == "ok"
    assert doc.title == f"YouTube video {VIDEO_ID}"


def test_ingest_youtube_fallback_without_any_metadata_still_explains() -> None:
    def no_transcript(video_id: str) -> str:
        raise TranscriptsDisabled(video_id)

    doc = ingest_youtube(LINK, VIDEO_ID, no_transcript, lambda url: "<html></html>")
    assert doc.status == "fallback"
    assert doc.title == f"YouTube video {VIDEO_ID}"
    assert doc.text.startswith("Transcript unavailable")


def test_make_transcript_fetcher_joins_snippets(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, Any] = {}

    class _FakeApi:
        def __init__(self, http_client: Any) -> None:
            calls["client"] = http_client

        def fetch(self, video_id: str, languages: tuple[str, ...]) -> list[SimpleNamespace]:
            calls["args"] = (video_id, languages)
            return [
                SimpleNamespace(text="hello"),
                SimpleNamespace(text=" world "),
                SimpleNamespace(text=""),
            ]

    monkeypatch.setattr(youtube, "YouTubeTranscriptApi", _FakeApi)
    fetch = make_transcript_fetcher(("en", "de"), timeout=7)
    assert fetch(VIDEO_ID) == "hello world"
    assert calls["args"] == (VIDEO_ID, ("en", "de"))


def test_ingest_youtube_treats_empty_transcript_as_fallback() -> None:
    doc = ingest_youtube(LINK, VIDEO_ID, lambda vid: "  ", _watch_page)
    assert doc.status == "fallback"
    assert "empty transcript" in doc.detail


def test_ingest_youtube_falls_back_on_network_error_from_transcript_client() -> None:
    def blocked(video_id: str) -> str:
        raise requests.exceptions.ProxyError("403 Forbidden")

    doc = ingest_youtube(LINK, VIDEO_ID, blocked, _watch_page)
    assert doc.status == "fallback"
    assert "ProxyError" in doc.detail


def test_transcript_http_client_applies_default_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_request(self: Any, method: str, url: str, **kwargs: Any) -> str:
        seen.update(kwargs)
        return "response"

    monkeypatch.setattr(requests.Session, "request", fake_request)
    session = youtube.TimeoutSession(7)
    assert session.request("GET", "https://www.youtube.com/") == "response"
    assert seen["timeout"] == 7
    session.request("GET", "https://www.youtube.com/", timeout=1)
    assert seen["timeout"] == 1


def test_ingest_youtube_falls_back_on_any_transcript_error_and_page_error() -> None:
    def bad_xml(video_id: str) -> str:
        raise ValueError("malformed timedtext")

    def bad_page(url: str) -> str:
        raise RuntimeError("decoder crashed")

    doc = ingest_youtube(LINK, VIDEO_ID, bad_xml, bad_page)
    assert doc.status == "fallback"
    assert doc.title == f"YouTube video {VIDEO_ID}"
    assert "ValueError" in doc.detail


def test_make_transcript_fetcher_reuses_one_session(monkeypatch: pytest.MonkeyPatch) -> None:
    clients: list[Any] = []

    class _FakeApi:
        def __init__(self, http_client: Any) -> None:
            clients.append(http_client)

        def fetch(self, video_id: str, languages: tuple[str, ...]) -> list[SimpleNamespace]:
            return [SimpleNamespace(text="x")]

    monkeypatch.setattr(youtube, "YouTubeTranscriptApi", _FakeApi)
    fetch = make_transcript_fetcher(("en",), timeout=3)
    fetch(VIDEO_ID)
    fetch(VIDEO_ID)
    assert len({id(c) for c in clients}) == 1


def test_ingest_youtube_ignores_consent_page_title() -> None:
    consent = '<html><head><meta property="og:title" content="Before you continue to YouTube">'
    consent += "</head></html>"
    doc = ingest_youtube(LINK, VIDEO_ID, lambda vid: "words", lambda url: consent)
    assert doc.title == f"YouTube video {VIDEO_ID}"


def test_make_transcript_fetcher_builds_api_once(monkeypatch: pytest.MonkeyPatch) -> None:
    built: list[Any] = []

    class _FakeApi:
        def __init__(self, http_client: Any) -> None:
            built.append(http_client)

        def fetch(self, video_id: str, languages: tuple[str, ...]) -> list[SimpleNamespace]:
            return [SimpleNamespace(text="x")]

    monkeypatch.setattr(youtube, "YouTubeTranscriptApi", _FakeApi)
    fetch = make_transcript_fetcher(("en",), timeout=3)
    fetch(VIDEO_ID)
    fetch(VIDEO_ID)
    assert len(built) == 1

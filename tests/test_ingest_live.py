"""Live checks against real services: ``uv run pytest -m live tests/test_ingest_live.py``."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from dotenv import dotenv_values

from newsletter_machine.articles import extract_article
from newsletter_machine.browser_fetch import make_browser_fetcher
from newsletter_machine.config import IngestSettings, load_ingest_settings
from newsletter_machine.gmail import build_gmail_client, read_inbox_links
from newsletter_machine.sources import InboxLink
from newsletter_machine.web import make_html_fetcher, with_fallback
from newsletter_machine.youtube import ingest_youtube, make_transcript_fetcher

REPO_ROOT = Path(__file__).resolve().parent.parent
LIVE_ENV = {**dotenv_values(REPO_ROOT / ".env"), **os.environ}
CAPTIONED_VIDEO_ID = "zjkBMFhNj_g"  # Andrej Karpathy, "Intro to Large Language Models"
CLOUDFLARE_ARTICLE = (
    "https://commandline.microsoft.com/agentic-software-engineering"  # refuses plain httpx
)
NOW = datetime.now(UTC)


@pytest.fixture
def live_settings() -> IngestSettings:
    env = {k: v for k, v in LIVE_ENV.items() if v is not None}
    return load_ingest_settings(env, repo_root=REPO_ROOT)


def _link(url: str) -> InboxLink:
    return InboxLink(url=url, note="", subject="", received_at=NOW)


@pytest.mark.live
def test_live_article_fetch_extracts_text(live_settings: IngestSettings) -> None:
    fetch = make_html_fetcher(live_settings.fetch_timeout)
    doc = extract_article(_link("https://en.wikipedia.org/wiki/Software_agent"), fetch)
    assert doc.status == "ok", doc.detail
    assert "agent" in doc.text.lower()


@pytest.mark.live
def test_live_cloudflare_site_via_browser_fallback(live_settings: IngestSettings) -> None:
    """A site that refuses plain Python clients (Cloudflare) is read via the browser retry."""
    fetch = with_fallback(
        make_html_fetcher(live_settings.fetch_timeout),
        make_browser_fetcher(live_settings.fetch_timeout),
    )
    doc = extract_article(_link(CLOUDFLARE_ARTICLE), fetch)
    assert doc.status == "ok", doc.detail
    assert len(doc.text) > 1000


@pytest.mark.live
def test_live_youtube_transcript(live_settings: IngestSettings) -> None:
    doc = ingest_youtube(
        _link(f"https://youtu.be/{CAPTIONED_VIDEO_ID}"),
        CAPTIONED_VIDEO_ID,
        make_transcript_fetcher(
            live_settings.transcript_languages, timeout=live_settings.fetch_timeout
        ),
        make_html_fetcher(live_settings.fetch_timeout),
    )
    assert doc.status == "ok", doc.detail  # "fallback" here means YouTube blocked this IP
    assert len(doc.text) > 1000


@pytest.mark.live
def test_live_gmail_label_reads(live_settings: IngestSettings) -> None:
    if not live_settings.gmail_client_secrets.is_file():
        pytest.skip(f"needs Gmail OAuth client JSON at {live_settings.gmail_client_secrets}")
    client = build_gmail_client(live_settings)
    links = read_inbox_links(client, live_settings.gmail_label, NOW - timedelta(days=30))
    assert all(link.url.startswith("http") for link in links)

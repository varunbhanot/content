"""Article extraction: fetch a page and keep only its main text (trafilatura)."""

import logging

import trafilatura
from trafilatura.settings import Document

from newsletter_machine.sources import InboxLink, SourceDoc, failed_doc
from newsletter_machine.web import FetchError, HtmlFetcher

logger = logging.getLogger(__name__)

NO_TEXT_DETAIL = "no extractable text (paywalled, JS-only or empty page)"


def extract_article(link: InboxLink, fetch_html: HtmlFetcher) -> SourceDoc:
    """Fetch ``link`` and return its main text; failures become ``status='failed'`` records."""
    try:
        html = fetch_html(link.url)
    except FetchError as exc:
        logger.warning("Could not fetch %s: %s", link.url, exc)
        return failed_doc(link, "article", str(exc))
    extracted = trafilatura.bare_extraction(
        html, url=link.url, with_metadata=True, include_comments=False
    )
    if not isinstance(extracted, Document) or not (extracted.text or "").strip():
        logger.warning("No extractable text at %s", link.url)
        return failed_doc(link, "article", NO_TEXT_DETAIL)
    return SourceDoc(
        url=link.url,
        title=extracted.title or link.url,
        kind="article",
        status="ok",
        text=(extracted.text or "").strip(),
        note=link.note,
    )

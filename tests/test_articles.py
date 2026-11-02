from datetime import UTC, datetime

from newsletter_machine.articles import extract_article
from newsletter_machine.sources import InboxLink
from newsletter_machine.web import FetchError

PARAGRAPH = "Agents in production fail for boring reasons like retries and timeouts. " * 12
ARTICLE_HTML = f"""<html><head><title>Why agents fail | Blog</title>
<meta property="og:title" content="Why agents fail"></head>
<body><nav>menu</nav><article><h1>Why agents fail</h1><p>{PARAGRAPH}</p></article>
<footer>cookie banner</footer></body></html>"""

LINK = InboxLink(
    url="https://blog.example.com/why",
    note="good on retries",
    subject="",
    received_at=datetime(2026, 11, 1, tzinfo=UTC),
)


def test_extract_article_returns_title_and_clean_text() -> None:
    doc = extract_article(LINK, lambda url: ARTICLE_HTML)
    assert doc.status == "ok"
    assert doc.kind == "article"
    assert doc.title == "Why agents fail"
    assert "boring reasons" in doc.text
    assert "cookie banner" not in doc.text
    assert doc.url == LINK.url
    assert doc.note == "good on retries"


def test_extract_article_marks_fetch_error_as_failed() -> None:
    def fail(url: str) -> str:
        raise FetchError("HTTP 403")

    doc = extract_article(LINK, fail)
    assert doc.status == "failed"
    assert doc.detail == "HTTP 403"
    assert doc.title == LINK.url
    assert doc.text == ""


def test_extract_article_marks_empty_page_as_failed() -> None:
    doc = extract_article(LINK, lambda url: "<html><body></body></html>")
    assert doc.status == "failed"
    assert "no extractable text" in doc.detail

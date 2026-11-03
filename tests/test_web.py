from collections.abc import Callable

import httpx
import pytest

from newsletter_machine import web
from newsletter_machine.web import (
    MAX_BODY_BYTES,
    BlockedError,
    FetchError,
    guard_url,
    header_charset,
    make_html_fetcher,
    with_fallback,
)

Handler = Callable[[httpx.Request], httpx.Response]


def _mock(handler: Handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def _html(body: str = "<p>hi</p>", status: int = 200, ctype: str = "text/html") -> Handler:
    return lambda request: httpx.Response(status, headers={"content-type": ctype}, text=body)


def test_fetcher_returns_html_body() -> None:
    fetch = make_html_fetcher(5, transport=_mock(_html("<p>hello</p>")))
    assert fetch("https://example.com/a") == "<p>hello</p>"


def test_fetcher_accepts_xhtml_content_type() -> None:
    fetch = make_html_fetcher(5, transport=_mock(_html(ctype="application/xhtml+xml")))
    assert fetch("https://example.com/a") == "<p>hi</p>"


def test_fetcher_raises_on_http_error_status() -> None:
    fetch = make_html_fetcher(5, transport=_mock(_html(status=403)))
    with pytest.raises(FetchError, match="HTTP 403"):
        fetch("https://example.com/a")


def test_fetcher_rejects_non_html_content() -> None:
    fetch = make_html_fetcher(5, transport=_mock(_html(ctype="application/pdf")))
    with pytest.raises(FetchError, match="content type"):
        fetch("https://example.com/a.pdf")


def test_fetcher_rejects_oversized_body() -> None:
    fetch = make_html_fetcher(5, transport=_mock(_html("x" * (MAX_BODY_BYTES + 1))))
    with pytest.raises(FetchError, match="larger than"):
        fetch("https://example.com/big")


@pytest.mark.parametrize("url", ["ftp://example.com/a", "file:///etc/passwd", "example.com"])
def test_fetcher_rejects_non_http_schemes(url: str) -> None:
    fetch = make_html_fetcher(5, transport=_mock(_html()))
    with pytest.raises(FetchError, match="http"):
        fetch(url)


def test_fetcher_wraps_transport_errors() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    fetch = make_html_fetcher(5, transport=_mock(boom))
    with pytest.raises(FetchError, match="no route"):
        fetch("https://example.com/a")


def test_fetcher_builds_default_client_with_timeout() -> None:
    fetch = make_html_fetcher(3.5)
    assert callable(fetch)


def test_fetcher_uses_meta_charset_when_header_has_none() -> None:
    page = '<html><head><meta charset="windows-1252"></head><p>café “quoted”</p></html>'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "text/html"}, content=page.encode("windows-1252")
        )

    fetch = make_html_fetcher(5, transport=_mock(handler))
    assert "café “quoted”" in fetch("https://example.com/a")


def test_fetcher_falls_back_to_utf8_on_unknown_meta_charset() -> None:
    page = '<meta charset="not-a-codec"><p>naïve</p>'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, content=page.encode())

    fetch = make_html_fetcher(5, transport=_mock(handler))
    assert "naïve" in fetch("https://example.com/a")


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/admin",
        "http://127.0.0.1:8080/",
        "http://192.168.1.1/",
        "http://[::1]/",
        "http://169.254.169.254/latest",
    ],
)
def test_fetcher_refuses_local_and_private_hosts(url: str) -> None:
    fetch = make_html_fetcher(5, transport=_mock(_html()))
    with pytest.raises(FetchError, match="private"):
        fetch(url)


def test_fetcher_refuses_redirect_to_private_host() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "example.com":
            return httpx.Response(302, headers={"location": "http://10.0.0.5/secret"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text="secret")

    fetch = make_html_fetcher(5, transport=_mock(handler))
    with pytest.raises(FetchError, match="private"):
        fetch("https://example.com/r")


def test_fetcher_refuses_redirect_to_non_http_scheme() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "ftp://example.com/file"})

    fetch = make_html_fetcher(5, transport=_mock(handler))
    with pytest.raises(FetchError, match="http"):
        fetch("https://example.com/r")


@pytest.mark.parametrize(
    "url", ["http://2130706433/admin", "http://127.1:8080/", "http://0x7f000001/", "http://10.1/"]
)
def test_fetcher_refuses_shorthand_numeric_private_hosts(url: str) -> None:
    fetch = make_html_fetcher(5, transport=_mock(_html()))
    with pytest.raises(FetchError, match="private"):
        fetch(url)


def test_fetcher_allows_public_numeric_host() -> None:
    fetch = make_html_fetcher(5, transport=_mock(_html("<p>ok</p>")))
    assert fetch("http://93.184.215.14/") == "<p>ok</p>"


def test_fetcher_enforces_total_read_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = iter([0.0, 1.0, 100.0, 200.0])
    monkeypatch.setattr(web, "monotonic", lambda: next(clock))

    def handler(request: httpx.Request) -> httpx.Response:
        chunks = iter([b"<p>", b"slow", b"</p>"])
        return httpx.Response(200, headers={"content-type": "text/html"}, content=chunks)

    fetch = make_html_fetcher(5, transport=_mock(handler))
    with pytest.raises(FetchError, match="took longer"):
        fetch("https://example.com/slow")


@pytest.mark.parametrize("status", [403, 503])
def test_fetcher_raises_blocked_error_on_bot_protection_statuses(status: int) -> None:
    fetch = make_html_fetcher(5, transport=_mock(_html(status=status)))
    with pytest.raises(BlockedError, match=f"HTTP {status}"):
        fetch("https://example.com/a")


def test_fetcher_404_is_not_treated_as_blocked() -> None:
    fetch = make_html_fetcher(5, transport=_mock(_html(status=404)))
    with pytest.raises(FetchError) as info:
        fetch("https://example.com/a")
    assert not isinstance(info.value, BlockedError)


def _refuse(url: str) -> str:
    raise BlockedError("HTTP 403")


def test_with_fallback_retries_blocked_fetch_with_fallback() -> None:
    fetch = with_fallback(_refuse, lambda url: f"<p>{url}</p>")
    assert fetch("https://example.com/a") == "<p>https://example.com/a</p>"


def test_with_fallback_does_not_retry_other_errors() -> None:
    calls: list[str] = []

    def not_found(url: str) -> str:
        raise FetchError("HTTP 404")

    def fallback(url: str) -> str:
        calls.append(url)
        return ""

    with pytest.raises(FetchError, match="HTTP 404"):
        with_fallback(not_found, fallback)("https://example.com/a")
    assert calls == []


def test_with_fallback_reports_both_errors_when_fallback_fails() -> None:
    def also_refused(url: str) -> str:
        raise FetchError("HTTP 403")

    with pytest.raises(FetchError, match="HTTP 403; browser retry failed: HTTP 403"):
        with_fallback(_refuse, also_refused)("https://example.com/a")


@pytest.mark.parametrize(
    ("url", "message"),
    [("ftp://example.com/a", "http"), ("http://10.0.0.1/", "private"), ("https:///x", "private")],
)
def test_guard_url_refuses_bad_targets(url: str, message: str) -> None:
    with pytest.raises(FetchError, match=message):
        guard_url(url)


def test_guard_url_allows_public_https() -> None:
    guard_url("https://example.com/a")


@pytest.mark.parametrize(
    ("content_type", "expected"),
    [
        ("text/html; charset=ISO-8859-1", "ISO-8859-1"),
        ('text/html; charset="utf-8"', "utf-8"),
        ("text/html", None),
    ],
)
def test_header_charset(content_type: str, expected: str | None) -> None:
    assert header_charset(content_type) == expected


def test_rate_limit_429_is_not_treated_as_blocked() -> None:
    """429 means 'slow down': never retried with the browser fallback."""
    fetch = make_html_fetcher(5, transport=_mock(_html(status=429)))
    with pytest.raises(FetchError, match="HTTP 429") as info:
        fetch("https://example.com/a")
    assert not isinstance(info.value, BlockedError)

from collections.abc import Callable

import httpx
import pytest

from newsletter_machine import web
from newsletter_machine.web import MAX_BODY_BYTES, FetchError, make_html_fetcher

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

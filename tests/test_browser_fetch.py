import threading
from collections.abc import Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from curl_cffi.requests.exceptions import RequestException

from newsletter_machine import browser_fetch
from newsletter_machine.browser_fetch import (
    MAX_REDIRECTS,
    BrowserResponse,
    curl_opener,
    make_browser_fetcher,
)
from newsletter_machine.web import MAX_BODY_BYTES, FetchError


@dataclass(frozen=True)
class FakeResponse:
    status_code: int
    headers: Mapping[str, str] = field(default_factory=dict)
    body: tuple[bytes, ...] = ()

    def header(self, name: str) -> str:
        return self.headers.get(name.lower(), "")

    def chunks(self) -> Iterator[bytes]:
        return iter(self.body)


def _page(html: str = "<p>hi</p>", ctype: str = "text/html") -> FakeResponse:
    return FakeResponse(200, {"content-type": ctype}, (html.encode(),))


def _redirect(location: str, status: int = 301) -> FakeResponse:
    return FakeResponse(status, {"location": location})


class FakeOpener:
    def __init__(self, routes: Mapping[str, FakeResponse | Exception]) -> None:
        self.routes = routes
        self.opened: list[str] = []

    def __call__(self, url: str, timeout: float) -> AbstractContextManager[BrowserResponse]:
        self.opened.append(url)
        return self._open(url)

    @contextmanager
    def _open(self, url: str) -> Iterator[BrowserResponse]:
        route = self.routes[url]
        if isinstance(route, Exception):
            raise route
        yield route


def test_returns_html_body() -> None:
    fetch = make_browser_fetcher(5, opener=FakeOpener({"https://a.com/x": _page("<p>ok</p>")}))
    assert fetch("https://a.com/x") == "<p>ok</p>"


def test_follows_relative_redirects() -> None:
    opener = FakeOpener(
        {"https://a.com/short": _redirect("/long/"), "https://a.com/long/": _page("<p>long</p>")}
    )
    assert make_browser_fetcher(5, opener=opener)("https://a.com/short") == "<p>long</p>"
    assert opener.opened == ["https://a.com/short", "https://a.com/long/"]


def test_refuses_private_start_url_without_opening_it() -> None:
    opener = FakeOpener({})
    with pytest.raises(FetchError, match="private"):
        make_browser_fetcher(5, opener=opener)("http://127.0.0.1/admin")
    assert opener.opened == []


def test_refuses_redirect_to_private_host() -> None:
    opener = FakeOpener({"https://a.com/r": _redirect("http://169.254.169.254/latest", 302)})
    with pytest.raises(FetchError, match="private"):
        make_browser_fetcher(5, opener=opener)("https://a.com/r")
    assert opener.opened == ["https://a.com/r"]


def test_refuses_redirect_to_non_http_scheme() -> None:
    opener = FakeOpener({"https://a.com/r": _redirect("file:///etc/passwd")})
    with pytest.raises(FetchError, match="http"):
        make_browser_fetcher(5, opener=opener)("https://a.com/r")


def test_gives_up_after_too_many_redirects() -> None:
    opener = FakeOpener({"https://a.com/loop": _redirect("https://a.com/loop")})
    with pytest.raises(FetchError, match="too many redirects"):
        make_browser_fetcher(5, opener=opener)("https://a.com/loop")
    assert len(opener.opened) == MAX_REDIRECTS + 1


def test_redirect_without_location_is_an_error() -> None:
    opener = FakeOpener({"https://a.com/r": FakeResponse(302)})
    with pytest.raises(FetchError, match="without a location"):
        make_browser_fetcher(5, opener=opener)("https://a.com/r")


def test_still_blocked_status_is_an_error() -> None:
    opener = FakeOpener({"https://a.com/x": FakeResponse(403, {"content-type": "text/html"})})
    with pytest.raises(FetchError, match="HTTP 403"):
        make_browser_fetcher(5, opener=opener)("https://a.com/x")


def test_rejects_non_html() -> None:
    opener = FakeOpener({"https://a.com/x.pdf": _page(ctype="application/pdf")})
    with pytest.raises(FetchError, match="content type"):
        make_browser_fetcher(5, opener=opener)("https://a.com/x.pdf")


def test_rejects_oversized_body() -> None:
    big = FakeResponse(200, {"content-type": "text/html"}, (b"x" * (MAX_BODY_BYTES + 1),))
    with pytest.raises(FetchError, match="larger than"):
        make_browser_fetcher(5, opener=FakeOpener({"https://a.com/x": big}))("https://a.com/x")


def test_decodes_with_header_charset() -> None:
    page = FakeResponse(
        200, {"content-type": "text/html; charset=windows-1252"}, ("café".encode("cp1252"),)
    )
    fetch = make_browser_fetcher(5, opener=FakeOpener({"https://a.com/x": page}))
    assert fetch("https://a.com/x") == "café"


def test_wraps_transport_errors() -> None:
    opener = FakeOpener({"https://a.com/x": RequestException("tls handshake failed")})
    with pytest.raises(FetchError, match="tls handshake failed"):
        make_browser_fetcher(5, opener=opener)("https://a.com/x")


@pytest.mark.parametrize(
    "location", ["http://127.0.0.1\\@a.com/", "http://user@10.0.0.1/", "https://a.com/x y"]
)
def test_refuses_ambiguous_redirect_locations(location: str) -> None:
    opener = FakeOpener({"https://a.com/r": _redirect(location, 302)})
    with pytest.raises(FetchError, match="ambiguous"):
        make_browser_fetcher(5, opener=opener)("https://a.com/r")
    assert opener.opened == ["https://a.com/r"]


def test_allows_at_sign_in_redirect_path() -> None:
    opener = FakeOpener(
        {"https://m.com/p": _redirect("/@author/post"), "https://m.com/@author/post": _page()}
    )
    assert make_browser_fetcher(5, opener=opener)("https://m.com/p") == "<p>hi</p>"


def test_each_hop_gets_only_the_remaining_time(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = iter([0.0, 1.0, 4.0])  # start, hop 1, hop 2
    monkeypatch.setattr(browser_fetch, "monotonic", lambda: next(clock))
    timeouts: list[float] = []
    opener = FakeOpener({"https://a.com/1": _redirect("/2"), "https://a.com/2": _page()})

    def timed(url: str, timeout: float) -> AbstractContextManager[BrowserResponse]:
        timeouts.append(timeout)
        return opener(url, timeout)

    monkeypatch.setattr(browser_fetch, "read_capped", lambda chunks, deadline, timeout: b"ok")
    assert make_browser_fetcher(5, opener=timed)("https://a.com/1") == "ok"
    assert timeouts == [4.0, 1.0]


def test_gives_up_when_redirects_use_up_the_time(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = iter([0.0, 1.0, 6.0])
    monkeypatch.setattr(browser_fetch, "monotonic", lambda: next(clock))
    opener = FakeOpener({"https://a.com/1": _redirect("/2"), "https://a.com/2": _page()})
    with pytest.raises(FetchError, match="took longer"):
        make_browser_fetcher(5, opener=opener)("https://a.com/1")
    assert opener.opened == ["https://a.com/1"]


def test_curl_session_is_created_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[str] = []
    monkeypatch.setattr(
        browser_fetch.curl_requests, "Session", lambda impersonate: created.append(impersonate)
    )
    curl_opener()
    assert created == []


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - http.server API
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/page")
            self.end_headers()
            return
        body = b"<p>local</p>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture
def local_server() -> Iterator[str]:
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def test_curl_opener_streams_a_real_response(local_server: str) -> None:
    with curl_opener()(f"{local_server}/page", 5) as response:
        assert response.status_code == 200
        assert response.header("Content-Type") == "text/html; charset=utf-8"
        assert b"".join(response.chunks()) == b"<p>local</p>"


def test_curl_opener_does_not_follow_redirects_itself(local_server: str) -> None:
    with curl_opener()(f"{local_server}/redirect", 5) as response:
        assert response.status_code == 302
        assert response.header("location") == "/page"

"""Fallback HTML fetcher that connects like a real Chrome browser (curl_cffi).

Some sites (often behind Cloudflare) refuse Python HTTP clients by their TLS/HTTP
fingerprint, not their User-Agent. Varun chose to retry those refusals with a
browser fingerprint; ``web.with_fallback`` uses this only after a plain fetch is
refused. Redirects are followed by hand so every hop passes ``web.guard_url``.
"""

import logging
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from time import monotonic
from typing import Protocol
from urllib.parse import urljoin, urlsplit

from curl_cffi import requests as curl_requests
from curl_cffi.requests.exceptions import RequestException

from newsletter_machine.web import (
    FetchError,
    HtmlFetcher,
    check_response,
    decode_html,
    guard_url,
    header_charset,
    read_capped,
)

logger = logging.getLogger(__name__)

IMPERSONATE = "chrome"
MAX_REDIRECTS = 10
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
MIN_HOP_TIMEOUT = 0.5  # seconds; curl treats 0 as "no timeout", so never pass it
# urllib and libcurl can disagree about the host of URLs with these; refuse them outright.
AMBIGUOUS_URL_CHARS = frozenset("\\ \t\r\n")


class BrowserResponse(Protocol):
    """The slice of an HTTP response the fetcher needs (easy to fake in tests)."""

    @property
    def status_code(self) -> int: ...

    def header(self, name: str) -> str: ...

    def chunks(self) -> Iterator[bytes]: ...


Opener = Callable[[str, float], AbstractContextManager[BrowserResponse]]


@dataclass(frozen=True)
class _CurlResponse:
    response: curl_requests.Response

    @property
    def status_code(self) -> int:
        return int(self.response.status_code)

    def header(self, name: str) -> str:
        return str(self.response.headers.get(name) or "")

    def chunks(self) -> Iterator[bytes]:
        # curl_cffi leaves iter_content/close unannotated; the runtime types are bytes/None.
        return iter(self.response.iter_content())  # type: ignore[no-untyped-call]


def curl_opener() -> Opener:
    """Open one URL with a Chrome fingerprint, streaming, without following redirects.

    The curl session is created on first use, so runs that never need it pay nothing.
    """
    sessions: list[curl_requests.Session] = []

    @contextmanager
    def open_url(url: str, timeout: float) -> Iterator[BrowserResponse]:
        if not sessions:
            sessions.append(curl_requests.Session(impersonate=IMPERSONATE))
        response = sessions[0].get(url, allow_redirects=False, stream=True, timeout=timeout)
        try:
            yield _CurlResponse(response)
        finally:
            response.close()  # type: ignore[no-untyped-call]

    return open_url


def _next_url(url: str, response: BrowserResponse) -> str:
    location = response.header("location")
    if not location:
        raise FetchError(f"HTTP {response.status_code} redirect without a location")
    target = urljoin(url, location)
    if AMBIGUOUS_URL_CHARS.intersection(location) or "@" in urlsplit(target).netloc:
        raise FetchError(f"refusing ambiguous redirect location {location!r}")
    return target


def _remaining(deadline: float, timeout: float) -> float:
    left = deadline - monotonic()
    if left <= 0:
        raise FetchError(f"page took longer than {timeout:g}s to download")
    return max(left, MIN_HOP_TIMEOUT)


def _fetch(open_url: Opener, url: str, timeout: float) -> str:
    deadline = monotonic() + timeout
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        guard_url(current)
        logger.debug("Browser-fetching %s", current)
        try:
            with open_url(current, _remaining(deadline, timeout)) as response:
                if response.status_code in REDIRECT_STATUSES:
                    current = _next_url(current, response)
                    continue
                content_type = response.header("content-type")
                check_response(response.status_code, content_type)
                body = read_capped(response.chunks(), deadline, timeout)
                return decode_html(body, header_charset(content_type))
        except RequestException as exc:
            raise FetchError(str(exc) or type(exc).__name__) from exc
    raise FetchError(f"too many redirects (more than {MAX_REDIRECTS})")


def make_browser_fetcher(timeout: float, *, opener: Opener | None = None) -> HtmlFetcher:
    """Return ``fetch(url) -> html`` over a browser fingerprint; inject ``opener`` in tests."""
    open_url = opener or curl_opener()
    return lambda url: _fetch(open_url, url, timeout)

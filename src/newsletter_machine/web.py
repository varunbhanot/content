"""Small HTML fetcher over httpx: http(s) only, size-capped, errors as ``FetchError``."""

import codecs
import ipaddress
import logging
import re
import socket
from collections.abc import Callable
from time import monotonic
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger(__name__)

HtmlFetcher = Callable[[str], str]

MAX_BODY_BYTES = 5 * 1024 * 1024
ALLOWED_SCHEMES = frozenset({"http", "https"})
HTML_CONTENT_TYPES = ("text/html", "application/xhtml+xml")
USER_AGENT = "Mozilla/5.0 (compatible; newsletter-machine/0.1; personal reading tool)"
FIRST_ERROR_STATUS = 400
LOCAL_HOSTNAMES = frozenset({"localhost", "localhost.localdomain"})
DEFAULT_ENCODING = "utf-8"
CHARSET_SNIFF_BYTES = 4096
META_CHARSET = re.compile(rb"""<meta[^>]+charset=["']?([A-Za-z0-9_.:-]+)""", re.IGNORECASE)


class FetchError(Exception):
    """Raised when a page cannot be fetched as HTML."""


def _read_capped(response: httpx.Response, deadline: float, timeout: float) -> bytes:
    """Read at most MAX_BODY_BYTES, and give up once the whole fetch exceeds ``timeout``."""
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_bytes():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise FetchError(f"page larger than {MAX_BODY_BYTES} bytes")
        if monotonic() > deadline:
            raise FetchError(f"page took longer than {timeout:g}s to download")
        chunks.append(chunk)
    return b"".join(chunks)


def _check_response(response: httpx.Response) -> None:
    if response.status_code >= FIRST_ERROR_STATUS:
        raise FetchError(f"HTTP {response.status_code}")
    content_type = response.headers.get("content-type", "").lower()
    if not content_type.startswith(HTML_CONTENT_TYPES):
        raise FetchError(f"unsupported content type {content_type or 'unknown'!r}")


def _encoding(response: httpx.Response, body: bytes) -> str:
    """Header charset, else the page's ``<meta charset>``, else UTF-8 (unknown names ignored)."""
    match = META_CHARSET.search(body[:CHARSET_SNIFF_BYTES])
    candidates = (response.charset_encoding, match.group(1).decode() if match else None)
    for name in candidates:
        if name:
            try:
                return codecs.lookup(name).name
            except LookupError:
                logger.debug("Ignoring unknown charset %r", name)
    return DEFAULT_ENCODING


def _is_private_host(host: str) -> bool:
    """Literal loopback/private/link-local IPs and localhost (DNS names are not resolved)."""
    if host.lower() in LOCAL_HOSTNAMES or host.lower().endswith(".localhost"):
        return True
    try:
        address: ipaddress.IPv4Address | ipaddress.IPv6Address = ipaddress.ip_address(
            host.strip("[]")
        )
    except ValueError:
        try:  # shorthand IPv4 the OS resolver accepts: 127.1, 2130706433, 0x7f000001
            address = ipaddress.IPv4Address(socket.inet_aton(host))
        except OSError:
            return False
    return not address.is_global


def _guard_request(request: httpx.Request) -> None:
    """Runs for the first request and every redirect hop (an httpx event hook)."""
    if request.url.scheme not in ALLOWED_SCHEMES:
        raise FetchError(f"only http(s) URLs can be fetched (got {str(request.url)!r})")
    if _is_private_host(request.url.host):
        raise FetchError(f"refusing to fetch private or local address {request.url.host!r}")


def _fetch(client: httpx.Client, url: str, timeout: float) -> str:
    if urlsplit(url).scheme.lower() not in ALLOWED_SCHEMES:
        raise FetchError(f"only http(s) URLs can be fetched (got {url!r})")
    logger.debug("Fetching %s", url)
    deadline = monotonic() + timeout
    try:
        with client.stream("GET", url) as response:
            _check_response(response)
            body = _read_capped(response, deadline, timeout)
            encoding = _encoding(response, body)
    except httpx.HTTPError as exc:
        raise FetchError(str(exc) or type(exc).__name__) from exc
    return body.decode(encoding, errors="replace")


def make_html_fetcher(
    timeout: float, *, transport: httpx.BaseTransport | None = None
) -> HtmlFetcher:
    """Return ``fetch(url) -> html``; inject ``transport`` (e.g. a MockTransport) in tests."""
    client = httpx.Client(
        follow_redirects=True,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT},
        event_hooks={"request": [_guard_request]},
        transport=transport,
    )
    return lambda url: _fetch(client, url, timeout)

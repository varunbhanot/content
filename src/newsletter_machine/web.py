"""Small HTML fetcher over httpx: http(s) only, size-capped, errors as ``FetchError``."""

import codecs
import ipaddress
import logging
import re
import socket
from collections.abc import Callable, Iterable
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
# Bot-protection refusals worth one browser retry. 429 (rate limit) is deliberately excluded:
# the site asked us to slow down, so we respect it instead of retrying.
BLOCKED_STATUSES = frozenset({403, 503})
LOCAL_HOSTNAMES = frozenset({"localhost", "localhost.localdomain"})
DEFAULT_ENCODING = "utf-8"
CHARSET_SNIFF_BYTES = 4096
META_CHARSET = re.compile(rb"""<meta[^>]+charset=["']?([A-Za-z0-9_.:-]+)""", re.IGNORECASE)
HEADER_CHARSET = re.compile(r"""charset=["']?([^;"'\s]+)""", re.IGNORECASE)


class FetchError(Exception):
    """Raised when a page cannot be fetched as HTML."""


class BlockedError(FetchError):
    """The site refused the request (403/503), typically bot protection."""


def read_capped(chunks: Iterable[bytes], deadline: float, timeout: float) -> bytes:
    """Read at most MAX_BODY_BYTES, and give up once the whole fetch exceeds ``timeout``."""
    parts: list[bytes] = []
    size = 0
    for chunk in chunks:
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise FetchError(f"page larger than {MAX_BODY_BYTES} bytes")
        if monotonic() > deadline:
            raise FetchError(f"page took longer than {timeout:g}s to download")
        parts.append(chunk)
    return b"".join(parts)


def check_response(status: int, content_type: str) -> None:
    """Raise ``BlockedError``/``FetchError`` unless this is a successful HTML response."""
    if status in BLOCKED_STATUSES:
        raise BlockedError(f"HTTP {status}")
    if status >= FIRST_ERROR_STATUS:
        raise FetchError(f"HTTP {status}")
    content_type = content_type.lower()
    if not content_type.startswith(HTML_CONTENT_TYPES):
        raise FetchError(f"unsupported content type {content_type or 'unknown'!r}")


def header_charset(content_type: str) -> str | None:
    match = HEADER_CHARSET.search(content_type)
    return match.group(1) if match else None


def decode_html(body: bytes, charset: str | None) -> str:
    """Decode with the header charset, else the page's ``<meta charset>``, else UTF-8."""
    match = META_CHARSET.search(body[:CHARSET_SNIFF_BYTES])
    candidates = (charset, match.group(1).decode() if match else None)
    for name in candidates:
        if name:
            try:
                return body.decode(codecs.lookup(name).name, errors="replace")
            except LookupError:
                logger.debug("Ignoring unknown charset %r", name)
    return body.decode(DEFAULT_ENCODING, errors="replace")


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


def _guard(scheme: str, host: str, url: str) -> None:
    if scheme.lower() not in ALLOWED_SCHEMES:
        raise FetchError(f"only http(s) URLs can be fetched (got {url!r})")
    if not host or _is_private_host(host):
        raise FetchError(f"refusing to fetch private or local address {host!r}")


def guard_url(url: str) -> None:
    """Refuse non-http(s) URLs and local/private hosts; call before every request or hop."""
    parts = urlsplit(url)
    _guard(parts.scheme, parts.hostname or "", url)


def _guard_request(request: httpx.Request) -> None:
    """Runs for the first request and every redirect hop (an httpx event hook)."""
    _guard(request.url.scheme, request.url.host, str(request.url))


def _fetch(client: httpx.Client, url: str, timeout: float) -> str:
    if urlsplit(url).scheme.lower() not in ALLOWED_SCHEMES:
        raise FetchError(f"only http(s) URLs can be fetched (got {url!r})")
    logger.debug("Fetching %s", url)
    deadline = monotonic() + timeout
    try:
        with client.stream("GET", url) as response:
            check_response(response.status_code, response.headers.get("content-type", ""))
            body = read_capped(response.iter_bytes(), deadline, timeout)
            charset = response.charset_encoding
    except httpx.HTTPError as exc:
        raise FetchError(str(exc) or type(exc).__name__) from exc
    return decode_html(body, charset)


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


def with_fallback(primary: HtmlFetcher, fallback: HtmlFetcher) -> HtmlFetcher:
    """Use ``primary``; only when a site refuses it (``BlockedError``) retry with ``fallback``."""

    def fetch(url: str) -> str:
        try:
            return primary(url)
        except BlockedError as blocked:
            logger.info("%s refused a plain fetch (%s); retrying as a browser", url, blocked)
            try:
                return fallback(url)
            except FetchError as exc:
                raise FetchError(f"{blocked}; browser retry failed: {exc}") from exc

    return fetch

"""Gmail inbox reader: links (and one-line notes) from messages under a label."""

import base64
import logging
import os
import re
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from newsletter_machine.config import ConfigError, IngestSettings
from newsletter_machine.sources import InboxLink, dedupe_by_url, extract_urls

logger = logging.getLogger(__name__)

READ_SCOPES = ("https://www.googleapis.com/auth/gmail.readonly",)
# Adds messages to the mailbox (like IMAP APPEND); it cannot send mail.
INSERT_SCOPE = "https://www.googleapis.com/auth/gmail.insert"
DELIVERY_SCOPES = (*READ_SCOPES, INSERT_SCOPE)
REAUTH_HINT = "Run 'uv run newsletter-machine gmail-auth' and update NM_GMAIL_TOKEN_B64."
USER_ID = "me"
MAX_NOTE_CHARS = 280
# Lines where Varun's own words end: signature ("-- "), forwards, replies, mobile footers.
NOTE_STOP_LINE = re.compile(
    r"^(-- ?|-{5,}\s*Forwarded message.*|Begin forwarded message:?|On .+ wrote:|Sent from my .+)$",
    re.IGNORECASE,
)
QUOTE_PREFIX = ">"
TOKEN_FILE_MODE = 0o600
TOKEN_DIR_MODE = 0o700
IGNORED_HOSTS = frozenset(
    {"accounts.google.com", "myaccount.google.com", "support.google.com", "mail.google.com"}
)
INVISIBLE_TAGS = frozenset({"head", "title", "style", "script", "noscript", "template"})
WHITESPACE = re.compile(r"\s+")


class GmailError(Exception):
    """Raised when the Gmail inbox cannot be read."""


class GmailClient(Protocol):
    def label_id(self, name: str) -> str | None: ...

    def list_message_ids(self, label_id: str, query: str) -> list[str]: ...

    def get_message(self, message_id: str) -> Mapping[str, Any]: ...


def _decode(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def _walk_parts(part: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
    yield part
    for child in part.get("parts", []):
        yield from _walk_parts(child)


def _body_text(payload: Mapping[str, Any], mime_type: str) -> str:
    return "\n".join(
        _decode(part["body"]["data"])
        for part in _walk_parts(payload)
        if part.get("mimeType") == mime_type and part.get("body", {}).get("data")
    )


class _HtmlBody(HTMLParser):
    """Visible text plus ``<a href>`` targets; skips head/style/script and image/CSS URLs."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.text: list[str] = []
        self.hrefs: list[str] = []
        self._hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in INVISIBLE_TAGS:
            self._hidden_depth += 1
        elif tag == "a":
            self.hrefs.extend(value for name, value in attrs if name == "href" and value)

    def handle_endtag(self, tag: str) -> None:
        if tag in INVISIBLE_TAGS and self._hidden_depth:
            self._hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._hidden_depth:
            self.text.append(data)


def _html_text(raw_html: str) -> str:
    parser = _HtmlBody()
    parser.feed(raw_html)
    parser.close()
    hrefs = " ".join(url for href in parser.hrefs for url in extract_urls(href))
    return f"{' '.join(parser.text)}\n{hrefs}"


def _message_text(payload: Mapping[str, Any]) -> str:
    """Plain-text body, or visible HTML text + link targets when there is no plain part."""
    plain = _body_text(payload, "text/plain")
    if plain.strip():
        return plain
    return _html_text(_body_text(payload, "text/html"))


def _note(text: str) -> str:
    own_lines: list[str] = []
    for line in (raw.strip() for raw in text.splitlines()):
        if NOTE_STOP_LINE.match(line):
            break
        if not line.startswith(QUOTE_PREFIX):
            own_lines.append(line)
    words = [w for w in WHITESPACE.split(" ".join(own_lines)) if w and not extract_urls(w)]
    return " ".join(words)[:MAX_NOTE_CHARS]


def _is_wanted(url: str) -> bool:
    return urlsplit(url).netloc.lower() not in IGNORED_HOSTS and "unsubscribe" not in url.lower()


def _subject(payload: Mapping[str, Any]) -> str:
    headers = payload.get("headers", [])
    return next((h["value"] for h in headers if h.get("name", "").lower() == "subject"), "")


def _links_from_message(message: Mapping[str, Any]) -> tuple[InboxLink, ...]:
    payload = message["payload"]
    text = _message_text(payload)
    received = datetime.fromtimestamp(int(message["internalDate"]) / 1000, tz=UTC)
    note, subject = _note(text), _subject(payload)
    return tuple(
        InboxLink(url=url, note=note, subject=subject, received_at=received)
        for url in extract_urls(text)
        if _is_wanted(url)
    )


def _query(since: datetime, senders: tuple[str, ...]) -> str:
    after = f"after:{int(since.timestamp())}"
    if not senders:
        return after
    return f"{after} {{{' '.join(f'from:{sender}' for sender in senders)}}}"


def read_inbox_links(
    client: GmailClient, label: str, since: datetime, *, senders: tuple[str, ...] = ()
) -> tuple[InboxLink, ...]:
    """Links from messages under ``label`` since ``since`` (from ``senders`` if given)."""
    label_id = client.label_id(label)
    if label_id is None:
        raise GmailError(
            f"Gmail label {label!r} not found. Create it (or fix NM_GMAIL_LABEL) and make "
            "sure your inbox filter applies it."
        )
    message_ids = client.list_message_ids(label_id, _query(since, senders))
    logger.info("Found %d messages under label %r", len(message_ids), label)
    links = [link for mid in message_ids for link in _links_from_message(client.get_message(mid))]
    return dedupe_by_url(sorted(links, key=lambda link: link.received_at))


class GoogleGmailClient:
    """Thin adapter over the google-api-python-client Gmail resource."""

    def __init__(self, service: Any) -> None:
        self._service = service

    def label_id(self, name: str) -> str | None:
        labels = self._service.users().labels().list(userId=USER_ID).execute().get("labels", [])
        wanted = name.casefold()
        return next((lb["id"] for lb in labels if lb["name"].casefold() == wanted), None)

    def list_message_ids(self, label_id: str, query: str) -> list[str]:
        ids: list[str] = []
        token: str | None = None
        while True:
            page = (
                self._service.users()
                .messages()
                .list(userId=USER_ID, labelIds=[label_id], q=query, pageToken=token)
                .execute()
            )
            ids.extend(m["id"] for m in page.get("messages", []))
            token = page.get("nextPageToken")
            if not token:
                return ids

    def get_message(self, message_id: str) -> Mapping[str, Any]:
        request = self._service.users().messages().get(userId=USER_ID, id=message_id, format="full")
        result: Mapping[str, Any] = request.execute()
        return result

    def profile_address(self) -> str:
        """The account's own address (readonly scope)."""
        profile = self._service.users().getProfile(userId=USER_ID).execute()
        return str(profile["emailAddress"])

    def insert_message(self, raw: bytes, label_ids: Sequence[str]) -> str:
        """Add an RFC 822 message to the mailbox (``gmail.insert``: nothing is sent)."""
        body = {"raw": base64.urlsafe_b64encode(raw).decode("ascii"), "labelIds": list(label_ids)}
        request = (
            self._service.users()
            .messages()
            .insert(userId=USER_ID, body=body, internalDateSource="dateHeader")
        )
        return str(request.execute()["id"])


def _save_token(path: Path, creds: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=TOKEN_DIR_MODE)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, TOKEN_FILE_MODE)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(creds.to_json())
    path.chmod(TOKEN_FILE_MODE)


def _cached_credentials(settings: IngestSettings, scopes: Sequence[str]) -> Any | None:
    if not settings.gmail_token.exists():
        return None
    creds = Credentials.from_authorized_user_file(  # type: ignore[no-untyped-call]
        str(settings.gmail_token),
        None,  # None: keep the scopes the token was granted
    )
    if not creds.has_scopes(list(scopes)):
        logger.warning("Cached Gmail token lacks a needed permission; asking for consent again")
        return None
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            return creds
        except RefreshError:
            logger.warning("Cached Gmail token could not be refreshed; asking for consent again")
    return None


def _headless_credentials(info: Mapping[str, Any], scopes: Sequence[str]) -> Any:
    """Credentials from ``NM_GMAIL_TOKEN_B64``: refreshed now, never a browser."""
    creds = Credentials.from_authorized_user_info(dict(info), None)  # type: ignore[no-untyped-call]
    if not creds.has_scopes(list(scopes)):
        raise ConfigError(
            f"The Gmail token in NM_GMAIL_TOKEN_B64 does not grant {', '.join(scopes)}. "
            + REAUTH_HINT
        )
    try:
        creds.refresh(Request())
    except RefreshError as exc:
        raise ConfigError(
            f"Google rejected the Gmail token in NM_GMAIL_TOKEN_B64 ({exc}). " + REAUTH_HINT
        ) from None
    return creds


def _require_client_file(settings: IngestSettings) -> None:
    if not settings.gmail_client_secrets.is_file():
        raise ConfigError(
            f"Gmail OAuth client file not found at {settings.gmail_client_secrets}. Create a "
            "Desktop OAuth client in Google Cloud (Gmail API enabled), download the JSON there, "
            "or point NM_GMAIL_CLIENT_SECRETS at it. Scheduled runs use NM_GMAIL_TOKEN_B64 instead."
        )


def _consent(settings: IngestSettings, scopes: Sequence[str]) -> Any:
    flow = InstalledAppFlow.from_client_secrets_file(
        str(settings.gmail_client_secrets), list(scopes)
    )
    return flow.run_local_server(port=0)


def authorize(settings: IngestSettings, scopes: Sequence[str] = DELIVERY_SCOPES) -> Path:
    """Browser consent for ``scopes`` (always asks), saving the token file; returns its path."""
    _require_client_file(settings)
    _save_token(settings.gmail_token, _consent(settings, scopes))
    return settings.gmail_token


def _service(creds: Any) -> GoogleGmailClient:
    return GoogleGmailClient(build("gmail", "v1", credentials=creds, cache_discovery=False))


def build_gmail_client(
    settings: IngestSettings, scopes: Sequence[str] = READ_SCOPES
) -> GoogleGmailClient:
    """Authorise and build the client.

    With ``NM_GMAIL_TOKEN_B64`` (scheduled/hosted runs) the token is refreshed in memory and a
    problem is a ``ConfigError``. Otherwise: cached token, refresh, or first-run browser consent.
    """
    if settings.gmail_token_info is not None:
        return _service(_headless_credentials(settings.gmail_token_info, scopes))
    _require_client_file(settings)
    creds = _cached_credentials(settings, scopes)
    if creds is None:
        creds = _consent(settings, scopes)
    _save_token(settings.gmail_token, creds)
    return _service(creds)

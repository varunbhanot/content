import base64
import json
import stat
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from newsletter_machine import gmail
from newsletter_machine.config import ConfigError, IngestSettings
from newsletter_machine.gmail import (
    GmailError,
    GoogleGmailClient,
    build_gmail_client,
    read_inbox_links,
)

SINCE = datetime(2026, 10, 30, tzinfo=UTC)


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def _message(
    msg_id: str, epoch_ms: int, *, plain: str | None = None, html: str | None = None
) -> dict[str, Any]:
    parts = []
    if plain is not None:
        parts.append({"mimeType": "text/plain", "body": {"data": _b64(plain)}})
    if html is not None:
        parts.append({"mimeType": "text/html", "body": {"data": _b64(html)}})
    payload = {
        "mimeType": "multipart/alternative",
        "headers": [{"name": "Subject", "value": f"subj {msg_id}"}],
        "parts": [{"mimeType": "multipart/mixed", "parts": parts}],
    }
    return {"id": msg_id, "internalDate": str(epoch_ms), "payload": payload}


class FakeGmail:
    def __init__(self, messages: list[dict[str, Any]], labels: dict[str, str]) -> None:
        self.messages = {m["id"]: m for m in messages}
        self.labels = labels
        self.queries: list[tuple[str, str]] = []

    def label_id(self, name: str) -> str | None:
        return self.labels.get(name)

    def list_message_ids(self, label_id: str, query: str) -> list[str]:
        self.queries.append((label_id, query))
        return list(self.messages)

    def get_message(self, message_id: str) -> Mapping[str, Any]:
        return self.messages[message_id]


def test_read_inbox_links_extracts_urls_notes_and_dedupes() -> None:
    client = FakeGmail(
        [
            _message("b", 1_762_000_200_000, plain="https://a.com/x?utm_source=share"),
            _message("a", 1_762_000_100_000, plain="Great take on evals\nhttps://a.com/x\n"),
            _message(
                "c",
                1_762_000_300_000,
                html='<p>see <a href="https://youtu.be/dQw4w9WgXcQ">this</a></p>',
            ),
        ],
        {"newsletter": "Label_1"},
    )
    links = read_inbox_links(client, "newsletter", SINCE)
    assert [link.url for link in links] == ["https://a.com/x", "https://youtu.be/dQw4w9WgXcQ"]
    assert links[0].note == "Great take on evals"
    assert links[0].subject == "subj a"
    assert links[0].received_at == datetime.fromtimestamp(1_762_000_100, tz=UTC)
    assert client.queries == [("Label_1", f"after:{int(SINCE.timestamp())}")]


def test_read_inbox_links_skips_mailto_and_unsubscribe_links() -> None:
    plain = "https://good.com/a\nhttps://list.example.com/unsubscribe?u=1\nhttps://myaccount.google.com/x"
    client = FakeGmail([_message("a", 1, plain=plain)], {"newsletter": "L"})
    assert [link.url for link in read_inbox_links(client, "newsletter", SINCE)] == [
        "https://good.com/a"
    ]


def test_read_inbox_links_handles_single_part_body_and_long_note() -> None:
    message = {
        "id": "s",
        "internalDate": "1000",
        "payload": {
            "mimeType": "text/plain",
            "headers": [],
            "body": {"data": _b64("x" * 400 + "\nhttps://b.com/1")},
        },
    }
    (link,) = read_inbox_links(FakeGmail([message], {"n": "L"}), "n", SINCE)
    assert link.url == "https://b.com/1"
    assert len(link.note) == gmail.MAX_NOTE_CHARS
    assert link.subject == ""


def test_read_inbox_links_returns_empty_for_empty_label() -> None:
    assert read_inbox_links(FakeGmail([], {"n": "L"}), "n", SINCE) == ()


def test_read_inbox_links_raises_when_label_missing() -> None:
    with pytest.raises(GmailError, match="'newsletter'.*NM_GMAIL_LABEL"):
        read_inbox_links(FakeGmail([], {}), "newsletter", SINCE)


class _Call:
    def __init__(self, result: Any) -> None:
        self.result = result

    def execute(self) -> Any:
        return self.result


class _FakeMessages:
    def __init__(self) -> None:
        self.list_calls: list[dict[str, Any]] = []

    def list(self, **kwargs: Any) -> _Call:
        self.list_calls.append(kwargs)
        if kwargs.get("pageToken") is None:
            return _Call({"messages": [{"id": "1"}], "nextPageToken": "p2"})
        return _Call({"messages": [{"id": "2"}]})

    def get(self, **kwargs: Any) -> _Call:
        return _Call({"id": kwargs["id"], "format": kwargs["format"]})


class _FakeService:
    def __init__(self) -> None:
        self.messages_resource = _FakeMessages()

    def users(self) -> "_FakeService":
        return self

    def labels(self) -> "_FakeService":
        return self

    def list(self, userId: str) -> _Call:  # noqa: N803 - mirrors Google's kwarg
        return _Call({"labels": [{"id": "Label_9", "name": "Newsletter"}]})

    def messages(self) -> _FakeMessages:
        return self.messages_resource


def test_google_gmail_client_resolves_label_case_insensitively() -> None:
    client = GoogleGmailClient(_FakeService())
    assert client.label_id("newsletter") == "Label_9"
    assert client.label_id("other") is None


def test_google_gmail_client_pages_through_message_ids() -> None:
    service = _FakeService()
    client = GoogleGmailClient(service)
    assert client.list_message_ids("Label_9", "after:1") == ["1", "2"]
    assert service.messages_resource.list_calls[0]["labelIds"] == ["Label_9"]
    assert client.get_message("1") == {"id": "1", "format": "full"}


def _settings(tmp_path: Path) -> IngestSettings:
    return IngestSettings(
        gmail_label="newsletter",
        gmail_allowed_senders=("me",),
        gmail_client_secrets=tmp_path / "client.json",
        gmail_token=tmp_path / "secrets" / "token.json",
        fetch_timeout=5,
        transcript_languages=("en",),
    )


class _FakeCreds:
    def __init__(
        self,
        *,
        valid: bool,
        expired: bool = False,
        refresh_token: str = "",
        scopes: tuple[str, ...] = tuple(gmail.READ_SCOPES),
    ) -> None:
        self.valid = valid
        self.expired = expired
        self.refresh_token = refresh_token
        self.refreshed = False
        self.scopes = scopes

    def has_scopes(self, scopes: list[str]) -> bool:
        return set(scopes) <= set(self.scopes)

    def refresh(self, request: Any) -> None:
        self.refreshed = True
        self.valid = True

    def to_json(self) -> str:
        return json.dumps({"token": "t"})


def _patch_build(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    def fake_build(*args: Any, **kwargs: Any) -> _FakeService:
        seen["args"], seen["kwargs"] = args, kwargs
        return _FakeService()

    monkeypatch.setattr(gmail, "build", fake_build)
    return seen


def test_build_gmail_client_requires_client_secrets(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="NM_GMAIL_CLIENT_SECRETS"):
        build_gmail_client(_settings(tmp_path))


def test_build_gmail_client_runs_consent_flow_and_saves_private_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    settings.gmail_client_secrets.write_text("{}")
    seen = _patch_build(monkeypatch)

    class _Flow:
        def run_local_server(self, port: int) -> _FakeCreds:
            return _FakeCreds(valid=True)

    monkeypatch.setattr(
        gmail.InstalledAppFlow, "from_client_secrets_file", lambda path, scopes: _Flow()
    )
    assert isinstance(build_gmail_client(settings), GoogleGmailClient)
    assert json.loads(settings.gmail_token.read_text()) == {"token": "t"}
    assert stat.S_IMODE(settings.gmail_token.stat().st_mode) == 0o600
    assert seen["args"] == ("gmail", "v1")


def test_build_gmail_client_refreshes_expired_cached_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    settings.gmail_client_secrets.write_text("{}")
    settings.gmail_token.parent.mkdir()
    settings.gmail_token.write_text("{}")
    creds = _FakeCreds(valid=False, expired=True, refresh_token="r")
    monkeypatch.setattr(gmail.Credentials, "from_authorized_user_file", lambda path, scopes: creds)
    _patch_build(monkeypatch)
    build_gmail_client(settings)
    assert creds.refreshed


def test_build_gmail_client_reuses_valid_cached_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    settings.gmail_client_secrets.write_text("{}")
    settings.gmail_token.parent.mkdir()
    settings.gmail_token.write_text("{}")
    creds = _FakeCreds(valid=True)
    monkeypatch.setattr(gmail.Credentials, "from_authorized_user_file", lambda path, scopes: creds)
    _patch_build(monkeypatch)
    build_gmail_client(settings)
    assert not creds.refreshed


def test_build_gmail_client_reruns_consent_when_refresh_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    settings.gmail_client_secrets.write_text("{}")
    settings.gmail_token.parent.mkdir()
    settings.gmail_token.write_text("{}")

    class _Revoked(_FakeCreds):
        def refresh(self, request: Any) -> None:
            raise gmail.RefreshError("revoked")

    monkeypatch.setattr(
        gmail.Credentials,
        "from_authorized_user_file",
        lambda path, scopes: _Revoked(valid=False, expired=True, refresh_token="r"),
    )
    fresh = _FakeCreds(valid=True)

    class _Flow:
        def run_local_server(self, port: int) -> _FakeCreds:
            return fresh

    monkeypatch.setattr(
        gmail.InstalledAppFlow, "from_client_secrets_file", lambda path, scopes: _Flow()
    )
    _patch_build(monkeypatch)
    build_gmail_client(settings)
    assert json.loads(settings.gmail_token.read_text()) == {"token": "t"}


def test_read_inbox_links_html_only_uses_anchor_hrefs_and_visible_text() -> None:
    html = (
        "<html><head><title>Fwd</title><style>body{color:red}</style>"
        '<link href="https://fonts.googleapis.com/css?family=Roboto"></head>'
        '<body><p>Great read</p><a href="https://ex.com/a?x=1&amp;y=2">link</a>'
        '<img src="https://t.mailer.com/open.gif"><script>var u="https://evil.js/x"</script>'
        "</body></html>"
    )
    (link,) = read_inbox_links(FakeGmail([_message("h", 1, html=html)], {"n": "L"}), "n", SINCE)
    assert link.url == "https://ex.com/a?x=1&y=2"
    assert link.note == "Great read link"


def test_read_inbox_links_restricts_query_to_allowed_senders() -> None:
    client = FakeGmail([], {"n": "L"})
    read_inbox_links(client, "n", SINCE, senders=("me", "work@example.com"))
    assert client.queries == [
        ("L", f"after:{int(SINCE.timestamp())} {{from:me from:work@example.com}}")
    ]


def test_note_cuts_only_at_signature_delimiter() -> None:
    plain = "Great piece\n--> skip to the 2nd half\nhttps://x.com/a\n-- \nVarun"
    (link,) = read_inbox_links(FakeGmail([_message("a", 1, plain=plain)], {"n": "L"}), "n", SINCE)
    assert link.note == "Great piece --> skip to the 2nd half"


def test_note_ignores_quoted_and_forwarded_text() -> None:
    plain = (
        "Worth a read\nhttps://x.com/a\n\nSent from my iPhone\n"
        "---------- Forwarded message ---------\nFrom: someone\nlots of boilerplate"
    )
    (link,) = read_inbox_links(FakeGmail([_message("a", 1, plain=plain)], {"n": "L"}), "n", SINCE)
    assert link.note == "Worth a read"


def test_note_drops_quoted_reply_lines() -> None:
    plain = "My take\n> quoted earlier mail\nhttps://x.com/b\nOn Mon, Varun wrote:\n> more"
    (link,) = read_inbox_links(FakeGmail([_message("a", 1, plain=plain)], {"n": "L"}), "n", SINCE)
    assert link.note == "My take"

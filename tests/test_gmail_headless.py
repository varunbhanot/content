import base64
import email
import json
from pathlib import Path
from typing import Any

import pytest

from newsletter_machine import gmail
from newsletter_machine.config import ConfigError, IngestSettings
from newsletter_machine.gmail import (
    DELIVERY_SCOPES,
    INSERT_SCOPE,
    READ_SCOPES,
    GoogleGmailClient,
    authorize,
    build_gmail_client,
)

INFO = {"refresh_token": "r", "client_id": "c", "client_secret": "s", "scopes": [INSERT_SCOPE]}


def _settings(tmp_path: Path, info: dict[str, Any] | None = None) -> IngestSettings:
    return IngestSettings(
        gmail_label="newsletter",
        gmail_allowed_senders=("me",),
        gmail_client_secrets=tmp_path / "client.json",
        gmail_token=tmp_path / "secrets" / "token.json",
        fetch_timeout=5,
        transcript_languages=("en",),
        gmail_token_info=info,
    )


class _Creds:
    def __init__(self, scopes: tuple[str, ...], *, fail: Exception | None = None) -> None:
        self.scopes = scopes
        self.fail = fail
        self.refreshed = 0
        self.valid = False
        self.expired = False
        self.refresh_token = "r"

    def has_scopes(self, scopes: list[str]) -> bool:
        return set(scopes) <= set(self.scopes)

    def refresh(self, request: Any) -> None:
        if self.fail:
            raise self.fail
        self.refreshed += 1
        self.valid = True

    def to_json(self) -> str:
        return json.dumps({"token": "t", "scopes": list(self.scopes)})


def _no_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a headless run must never open a browser")

    monkeypatch.setattr(gmail.InstalledAppFlow, "from_client_secrets_file", _boom)


def _use_info_creds(monkeypatch: pytest.MonkeyPatch, creds: _Creds) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    def _from_info(info: dict[str, Any], scopes: Any) -> _Creds:
        seen["info"], seen["scopes"] = info, scopes
        return creds

    monkeypatch.setattr(gmail.Credentials, "from_authorized_user_info", _from_info)
    monkeypatch.setattr(gmail, "build", lambda *a, **k: _Service())
    return seen


def test_headless_token_refreshes_without_client_file_or_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_browser(monkeypatch)
    creds = _Creds(DELIVERY_SCOPES)
    seen = _use_info_creds(monkeypatch, creds)
    client = build_gmail_client(_settings(tmp_path, INFO), DELIVERY_SCOPES)
    assert isinstance(client, GoogleGmailClient)
    assert creds.refreshed == 1
    assert seen["info"] == INFO and seen["scopes"] is None  # granted scopes come from the token
    assert not _settings(tmp_path).gmail_token.exists()  # nothing written to disk


def test_headless_token_without_insert_scope_is_a_config_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_browser(monkeypatch)
    _use_info_creds(monkeypatch, _Creds(READ_SCOPES))
    build_gmail_client(_settings(tmp_path, INFO))  # reading is fine
    with pytest.raises(ConfigError, match="gmail-auth"):
        build_gmail_client(_settings(tmp_path, INFO), DELIVERY_SCOPES)


def test_rejected_headless_token_is_a_config_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_browser(monkeypatch)
    _use_info_creds(monkeypatch, _Creds(DELIVERY_SCOPES, fail=gmail.RefreshError("invalid_grant")))
    with pytest.raises(ConfigError, match="NM_GMAIL_TOKEN_B64.*gmail-auth"):
        build_gmail_client(_settings(tmp_path, INFO), DELIVERY_SCOPES)


def test_cached_token_without_needed_scope_asks_for_consent_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    settings.gmail_client_secrets.write_text("{}")
    settings.gmail_token.parent.mkdir()
    settings.gmail_token.write_text("{}")
    monkeypatch.setattr(
        gmail.Credentials, "from_authorized_user_file", lambda path, scopes: _Creds(READ_SCOPES)
    )
    asked: list[tuple[str, ...]] = []

    class _Flow:
        def run_local_server(self, port: int) -> _Creds:
            fresh = _Creds(DELIVERY_SCOPES)
            fresh.valid = True
            return fresh

    def _flow(path: str, scopes: list[str]) -> _Flow:
        asked.append(tuple(scopes))
        return _Flow()

    monkeypatch.setattr(gmail.InstalledAppFlow, "from_client_secrets_file", _flow)
    monkeypatch.setattr(gmail, "build", lambda *a, **k: _Service())
    build_gmail_client(settings, DELIVERY_SCOPES)
    assert asked == [DELIVERY_SCOPES]
    assert INSERT_SCOPE in json.loads(settings.gmail_token.read_text())["scopes"]


def test_authorize_always_runs_consent_and_saves_the_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    settings.gmail_client_secrets.write_text("{}")

    class _Flow:
        def run_local_server(self, port: int) -> _Creds:
            return _Creds(DELIVERY_SCOPES)

    monkeypatch.setattr(
        gmail.InstalledAppFlow, "from_client_secrets_file", lambda path, scopes: _Flow()
    )
    assert authorize(settings, DELIVERY_SCOPES) == settings.gmail_token
    assert settings.gmail_token.exists()


def test_authorize_requires_the_client_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="NM_GMAIL_CLIENT_SECRETS"):
        authorize(_settings(tmp_path), DELIVERY_SCOPES)


class _Call:
    def __init__(self, result: Any) -> None:
        self.result = result

    def execute(self) -> Any:
        return self.result


class _Service:
    def __init__(self) -> None:
        self.inserted: list[dict[str, Any]] = []

    def users(self) -> "_Service":
        return self

    def messages(self) -> "_Service":
        return self

    def getProfile(self, userId: str) -> _Call:  # noqa: N802, N803 - Google's names
        return _Call({"emailAddress": "varun@example.com"})

    def insert(self, **kwargs: Any) -> _Call:
        self.inserted.append(kwargs)
        return _Call({"id": "m-1"})


def test_client_profile_address_and_insert_message() -> None:
    service = _Service()
    client = GoogleGmailClient(service)
    assert client.profile_address() == "varun@example.com"
    raw = b"Subject: hi\r\n\r\nbody\r\n"
    assert client.insert_message(raw, ("INBOX", "UNREAD")) == "m-1"
    call = service.inserted[0]
    assert call["userId"] == "me" and call["internalDateSource"] == "dateHeader"
    assert call["body"]["labelIds"] == ["INBOX", "UNREAD"]
    decoded = email.message_from_bytes(base64.urlsafe_b64decode(call["body"]["raw"]))
    assert decoded["Subject"] == "hi"


def test_reconsent_keeps_the_insert_scope_the_cached_token_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A revoked read+insert token re-consented by `ingest` must not lose gmail.insert."""
    settings = _settings(tmp_path)
    settings.gmail_client_secrets.write_text("{}")
    settings.gmail_token.parent.mkdir()
    settings.gmail_token.write_text("{}")
    revoked = _Creds(DELIVERY_SCOPES, fail=gmail.RefreshError("revoked"))
    revoked.expired = True
    monkeypatch.setattr(gmail.Credentials, "from_authorized_user_file", lambda path, s: revoked)
    asked: list[tuple[str, ...]] = []

    class _Flow:
        def run_local_server(self, port: int) -> _Creds:
            return _Creds(DELIVERY_SCOPES)

    def _flow(path: str, scopes: list[str]) -> _Flow:
        asked.append(tuple(scopes))
        return _Flow()

    monkeypatch.setattr(gmail.InstalledAppFlow, "from_client_secrets_file", _flow)
    monkeypatch.setattr(gmail, "build", lambda *a, **k: _Service())
    build_gmail_client(settings, READ_SCOPES)
    assert asked == [DELIVERY_SCOPES]

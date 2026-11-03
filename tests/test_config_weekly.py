import base64
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from newsletter_machine import config
from newsletter_machine.config import (
    ConfigError,
    load_ingest_settings,
    load_settings,
    load_weekly_settings,
)

TOKEN = {"refresh_token": "r-secret", "client_id": "cid", "client_secret": "c-secret"}


def _b64(value: object) -> str:
    raw = value if isinstance(value, str) else json.dumps(value)
    return base64.b64encode(raw.encode()).decode()


def test_gmail_token_b64_is_decoded_and_hidden_from_repr() -> None:
    settings = load_ingest_settings({"NM_GMAIL_TOKEN_B64": _b64(TOKEN)})
    assert settings.gmail_token_info == TOKEN
    assert "r-secret" not in repr(settings)


def test_gmail_token_b64_can_be_ignored_even_when_broken() -> None:
    env = {"NM_GMAIL_TOKEN_B64": "%%%"}
    assert load_ingest_settings(env, ignore_token=True).gmail_token_info is None


def test_gmail_token_b64_is_optional() -> None:
    assert load_ingest_settings({}).gmail_token_info is None
    assert load_ingest_settings({"NM_GMAIL_TOKEN_B64": "  "}).gmail_token_info is None


@pytest.mark.parametrize(
    "value",
    [
        "%%%not-base64%%%",
        _b64("not json"),
        _b64(["a", "list"]),
        _b64({"client_id": "cid", "client_secret": "s"}),
        _b64({**TOKEN, "refresh_token": ""}),
        _b64({**TOKEN, "client_id": 3}),
    ],
)
def test_bad_gmail_token_b64_is_a_config_error_without_the_value(value: str) -> None:
    with pytest.raises(ConfigError, match="NM_GMAIL_TOKEN_B64") as info:
        load_ingest_settings({"NM_GMAIL_TOKEN_B64": value})
    assert value not in str(info.value) and "secret" not in str(info.value).replace(
        "client_secret", ""
    )


def test_weekly_defaults_to_kolkata_and_no_substack() -> None:
    weekly = load_weekly_settings({})
    assert weekly.timezone == ZoneInfo("Asia/Kolkata")
    assert weekly.substack is None


def test_weekly_timezone_is_configurable_and_validated() -> None:
    assert load_weekly_settings({"NM_TIMEZONE": "Europe/London"}).timezone == ZoneInfo(
        "Europe/London"
    )
    with pytest.raises(ConfigError, match="NM_TIMEZONE"):
        load_weekly_settings({"NM_TIMEZONE": "Mars/Base"})
    with pytest.raises(ConfigError, match="NM_TIMEZONE"):
        load_weekly_settings({"NM_TIMEZONE": "../etc/passwd"})


@pytest.mark.parametrize("flag", ["", "false", "0", "no", "OFF"])
def test_substack_is_off_unless_opted_in(flag: str) -> None:
    env = {"NM_SUBSTACK_DRAFT": flag, "SUBSTACK_COOKIES": "c"}
    assert load_weekly_settings(env).substack is None


def test_substack_flag_must_be_a_boolean() -> None:
    with pytest.raises(ConfigError, match="NM_SUBSTACK_DRAFT"):
        load_weekly_settings({"NM_SUBSTACK_DRAFT": "maybe"})


def test_substack_opt_in_with_cookies() -> None:
    env = {
        "NM_SUBSTACK_DRAFT": "true",
        "SUBSTACK_PUBLICATION_URL": "https://varunbhanot.substack.com/",
        "SUBSTACK_COOKIES": "substack.sid=s3cret",
    }
    substack = load_weekly_settings(env).substack
    assert substack is not None
    assert substack.publication_url == "https://varunbhanot.substack.com"
    assert substack.cookies == "substack.sid=s3cret"
    assert "s3cret" not in repr(substack)


def test_substack_opt_in_with_email_and_password() -> None:
    env = {
        "NM_SUBSTACK_DRAFT": "1",
        "SUBSTACK_PUBLICATION_URL": "https://x.substack.com",
        "SUBSTACK_EMAIL": "v@example.com",
        "SUBSTACK_PASSWORD": "pw-secret",
    }
    substack = load_weekly_settings(env).substack
    assert substack is not None and substack.email == "v@example.com"
    assert "pw-secret" not in repr(substack)


@pytest.mark.parametrize(
    "env",
    [
        {"SUBSTACK_COOKIES": "c"},
        {"SUBSTACK_PUBLICATION_URL": "http://x.substack.com", "SUBSTACK_COOKIES": "c"},
        {"SUBSTACK_PUBLICATION_URL": "https://x.substack.com"},
        {"SUBSTACK_PUBLICATION_URL": "https://x.substack.com", "SUBSTACK_EMAIL": "v@e.com"},
    ],
)
def test_substack_opt_in_needs_url_and_credentials(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match="SUBSTACK_"):
        load_weekly_settings({"NM_SUBSTACK_DRAFT": "yes", **env})


def test_voice_dir_falls_back_to_project_root_when_cwd_has_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = load_settings({"ANTHROPIC_API_KEY": "k"})
    assert settings.voice_dir == config.PROJECT_ROOT / "voice"
    assert (settings.voice_dir / "samples" / "hand").is_dir()


def test_voice_dir_prefers_cwd_when_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "voice" / "samples" / "hand").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    assert load_settings({"ANTHROPIC_API_KEY": "k"}).voice_dir == tmp_path / "voice"


def test_relative_voice_dir_missing_from_cwd_falls_back_to_the_project(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``.env.example`` sets NM_VOICE_DIR=voice and MDA uploads it; hosted cwd is elsewhere."""
    monkeypatch.chdir(tmp_path)
    settings = load_settings({"ANTHROPIC_API_KEY": "k", "NM_VOICE_DIR": "voice"})
    assert settings.voice_dir == config.PROJECT_ROOT / "voice"


def test_absolute_voice_dir_never_falls_back(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="Voice corpus not found"):
        load_settings({"ANTHROPIC_API_KEY": "k", "NM_VOICE_DIR": str(tmp_path / "none")})


def test_gmail_token_info_is_read_only() -> None:
    info = load_ingest_settings({"NM_GMAIL_TOKEN_B64": _b64(TOKEN)}).gmail_token_info
    assert info is not None
    with pytest.raises(TypeError):
        info["token"] = "x"  # type: ignore[index]


def test_issue_timezone_falls_back_to_utc() -> None:
    assert config.issue_timezone({"NM_TIMEZONE": "Europe/Paris"}) == ZoneInfo("Europe/Paris")
    assert config.issue_timezone({"NM_TIMEZONE": "Nowhere/Land"}) == ZoneInfo("UTC")

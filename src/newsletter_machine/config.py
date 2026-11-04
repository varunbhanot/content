"""Environment-based configuration, validated at the boundary."""

import base64
import binascii
import json
import logging
import math
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import find_dotenv, load_dotenv

logger = logging.getLogger(__name__)

DEFAULT_WRITER_MODEL = "anthropic:claude-sonnet-5-5"
DEFAULT_FAST_MODEL = "anthropic:claude-haiku-5-5"
DEFAULT_VOICE_DIR = "voice"
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # the repo (editable install, hosted image)
DEFAULT_TIMEZONE = "Asia/Kolkata"
FALLBACK_TIMEZONE = ZoneInfo("UTC")
TOKEN_INFO_KEYS = ("refresh_token", "client_id", "client_secret")
TRUE_WORDS = frozenset({"1", "true", "yes", "on"})
FALSE_WORDS = frozenset({"", "0", "false", "no", "off"})
DEFAULT_GMAIL_LABEL = "newsletter"
DEFAULT_GMAIL_CLIENT_SECRETS = ".secrets/gmail-client.json"
DEFAULT_GMAIL_TOKEN = ".secrets/gmail-token.json"
DEFAULT_FETCH_TIMEOUT = "20"
DEFAULT_TRANSCRIPT_LANGUAGES = "en"
DEFAULT_GMAIL_ALLOWED_SENDERS = "me"
DEFAULT_MAX_REVISIONS = 1
MAX_REVISIONS_LIMIT = 3  # each revision is a writer + critic call; caps cost per issue
SENDER_PATTERN = re.compile(r"[^\s{}()\"]+")


class ConfigError(Exception):
    """Raised when configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str = field(repr=False)
    writer_model: str
    fast_model: str
    voice_dir: Path
    critic_model: str


@dataclass(frozen=True)
class EditorSettings:
    """Settings only ``issue`` reads, so a bad value never breaks ``hello`` or ``draft``."""

    editor_model: str
    max_revisions: int


@dataclass(frozen=True)
class IngestSettings:
    """Settings for ``ingest``; deliberately independent of the Anthropic key."""

    gmail_label: str
    gmail_allowed_senders: tuple[str, ...]
    gmail_client_secrets: Path
    gmail_token: Path
    fetch_timeout: float
    transcript_languages: tuple[str, ...]
    # Headless OAuth token (NM_GMAIL_TOKEN_B64); when set, Gmail never opens a browser.
    gmail_token_info: Mapping[str, Any] | None = field(default=None, repr=False)


@dataclass(frozen=True)
class SubstackSettings:
    """Opt-in Substack draft step; one of ``cookies`` or ``email``+``password`` is set."""

    publication_url: str
    cookies: str = field(default="", repr=False)
    email: str = ""
    password: str = field(default="", repr=False)


@dataclass(frozen=True)
class WeeklySettings:
    """Settings only ``weekly`` (the scheduled run) reads."""

    timezone: ZoneInfo
    substack: SubstackSettings | None  # None unless NM_SUBSTACK_DRAFT opts in


def _load_env(env: Mapping[str, str] | None) -> Mapping[str, str]:
    if env is None:
        load_dotenv(find_dotenv(usecwd=True))
        return os.environ
    return env


def _resolve_path(value: str, repo_root: Path | None) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (repo_root or Path.cwd()) / path


def _voice_dir(value: str | None, repo_root: Path | None) -> Path:
    """``NM_VOICE_DIR`` (default ``voice``) from the cwd; a relative path missing there falls
    back to the project's own folder, since hosted runs start outside the repo."""
    raw = value or DEFAULT_VOICE_DIR
    path = _resolve_path(raw, repo_root)
    if path.is_dir() or repo_root is not None or Path(raw).is_absolute():
        return path
    return PROJECT_ROOT / raw


def _require_provider_prefix(name: str, value: str) -> str:
    value = value.strip()  # a stray space from .env must not reach the API as part of the id
    provider, sep, model = value.partition(":")
    if not sep or not provider or not model:
        raise ConfigError(f"{name} must look like 'provider:model' (got {value!r}).")
    return value


def _max_revisions(value: str) -> int:
    value = value.strip()
    if not value:
        return DEFAULT_MAX_REVISIONS
    if not (value.isascii() and value.isdigit()) or int(value) > MAX_REVISIONS_LIMIT:
        raise ConfigError(
            f"NM_MAX_REVISIONS must be a whole number from 0 to {MAX_REVISIONS_LIMIT} "
            f"(got {value!r})."
        )
    return int(value)


def load_settings(
    env: Mapping[str, str] | None = None, *, repo_root: Path | None = None
) -> Settings:
    """Load settings from ``env`` (or ``.env`` + process env when ``env`` is None)."""
    env = _load_env(env)
    api_key = env.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise ConfigError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key."
        )

    writer_model = _require_provider_prefix(
        "NM_WRITER_MODEL", env.get("NM_WRITER_MODEL", DEFAULT_WRITER_MODEL)
    )
    critic_model = _require_provider_prefix(
        "NM_CRITIC_MODEL", env.get("NM_CRITIC_MODEL", "").strip() or writer_model
    )
    fast_model = _require_provider_prefix(
        "NM_FAST_MODEL", env.get("NM_FAST_MODEL", DEFAULT_FAST_MODEL)
    )

    voice_dir = _voice_dir(env.get("NM_VOICE_DIR"), repo_root)
    if not (voice_dir / "samples" / "hand").is_dir():
        raise ConfigError(
            f"Voice corpus not found: {voice_dir}/samples/hand does not exist. "
            "Set NM_VOICE_DIR to the voice/ folder."
        )

    return Settings(
        anthropic_api_key=api_key,
        writer_model=writer_model,
        fast_model=fast_model,
        voice_dir=voice_dir,
        critic_model=critic_model,
    )


def load_editor_settings(
    settings: Settings, env: Mapping[str, str] | None = None
) -> EditorSettings:
    """``NM_EDITOR_MODEL`` (blank = the writer model) and ``NM_MAX_REVISIONS`` (0 to 3)."""
    env = _load_env(env)
    editor_model = _require_provider_prefix(
        "NM_EDITOR_MODEL", env.get("NM_EDITOR_MODEL", "").strip() or settings.writer_model
    )
    return EditorSettings(
        editor_model=editor_model, max_revisions=_max_revisions(env.get("NM_MAX_REVISIONS", ""))
    )


def load_planner_model(settings: Settings, env: Mapping[str, str] | None = None) -> str:
    """``NM_PLANNER_MODEL`` for ``series plan`` (blank = the writer model)."""
    env = _load_env(env)
    return _require_provider_prefix(
        "NM_PLANNER_MODEL", env.get("NM_PLANNER_MODEL", "").strip() or settings.writer_model
    )


def _model_or(name: str, fallback: str, env: Mapping[str, str] | None) -> str:
    """The ``provider:model`` in env var ``name``, or ``fallback`` when it is blank."""
    env = _load_env(env)
    return _require_provider_prefix(name, env.get(name, "").strip() or fallback)


def load_relevance_model(settings: Settings, env: Mapping[str, str] | None = None) -> str:
    """``NM_RELEVANCE_MODEL`` for the series relevance filter (blank = the fast model)."""
    return _model_or("NM_RELEVANCE_MODEL", settings.fast_model, env)


def load_summary_model(settings: Settings, env: Mapping[str, str] | None = None) -> str:
    """``NM_SUMMARY_MODEL`` for a drafted series part's one-line summary (blank = fast model)."""
    return _model_or("NM_SUMMARY_MODEL", settings.fast_model, env)


def load_runner_model(env: Mapping[str, str] | None = None) -> str:
    """The hosted runner's model: ``NM_RUNNER_MODEL``, else ``NM_FAST_MODEL`` (it only calls
    one tool)."""
    env = _load_env(env)
    runner = env.get("NM_RUNNER_MODEL", "").strip()
    if runner:
        return _require_provider_prefix("NM_RUNNER_MODEL", runner)
    fast = env.get("NM_FAST_MODEL", "").strip() or DEFAULT_FAST_MODEL
    return _require_provider_prefix("NM_FAST_MODEL", fast)


def _positive_float(name: str, value: str) -> float:
    try:
        number = float(value)
    except ValueError:
        raise ConfigError(f"{name} must be a number of seconds (got {value!r}).") from None
    if not math.isfinite(number) or number <= 0:
        raise ConfigError(f"{name} must be a positive number of seconds (got {value!r}).")
    return number


def _csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _allowed_senders(value: str) -> tuple[str, ...]:
    senders = _csv(value)
    if not senders or not all(SENDER_PATTERN.fullmatch(s) for s in senders):
        raise ConfigError(
            "NM_GMAIL_ALLOWED_SENDERS must be comma-separated addresses or 'me' "
            f"(got {value!r}); only mail from them is read."
        )
    return senders


def load_ingest_settings(
    env: Mapping[str, str] | None = None,
    *,
    repo_root: Path | None = None,
    ignore_token: bool = False,
) -> IngestSettings:
    """Load ingest settings from ``env`` (or ``.env`` + process env when ``env`` is None).

    ``ignore_token`` skips ``NM_GMAIL_TOKEN_B64`` (``gmail-auth`` replaces a broken one).
    """
    env = _load_env(env)
    label = env.get("NM_GMAIL_LABEL", DEFAULT_GMAIL_LABEL).strip()
    if not label:
        raise ConfigError("NM_GMAIL_LABEL must name the Gmail label your filter applies.")
    languages = _csv(env.get("NM_TRANSCRIPT_LANGUAGES", DEFAULT_TRANSCRIPT_LANGUAGES))
    if not languages:
        raise ConfigError("NM_TRANSCRIPT_LANGUAGES must list language codes, e.g. 'en,de'.")
    return IngestSettings(
        gmail_label=label,
        gmail_allowed_senders=_allowed_senders(
            env.get("NM_GMAIL_ALLOWED_SENDERS", DEFAULT_GMAIL_ALLOWED_SENDERS)
        ),
        gmail_client_secrets=_resolve_path(
            env.get("NM_GMAIL_CLIENT_SECRETS", DEFAULT_GMAIL_CLIENT_SECRETS), repo_root
        ),
        gmail_token=_resolve_path(env.get("NM_GMAIL_TOKEN", DEFAULT_GMAIL_TOKEN), repo_root),
        fetch_timeout=_positive_float(
            "NM_FETCH_TIMEOUT", env.get("NM_FETCH_TIMEOUT", DEFAULT_FETCH_TIMEOUT)
        ),
        transcript_languages=languages,
        gmail_token_info=None if ignore_token else _token_info(env.get("NM_GMAIL_TOKEN_B64", "")),
    )


def _token_info(value: str) -> Mapping[str, Any] | None:
    """Decode ``NM_GMAIL_TOKEN_B64``; errors name the variable, never its value."""
    value = value.strip()
    if not value:
        return None
    hint = "NM_GMAIL_TOKEN_B64 must be the base64 of the token file 'gmail-auth' writes"
    try:
        info = json.loads(base64.b64decode(value, validate=True))
    except (binascii.Error, ValueError):
        raise ConfigError(f"{hint}; it could not be decoded.") from None
    if not isinstance(info, dict):
        raise ConfigError(f"{hint}; it is not a JSON object.")
    missing = [
        key for key in TOKEN_INFO_KEYS if not isinstance(info.get(key), str) or not info[key]
    ]
    if missing:
        raise ConfigError(f"{hint}; it lacks {', '.join(missing)}.")
    return MappingProxyType(info)


def _flag(name: str, value: str) -> bool:
    word = value.strip().lower()
    if word in TRUE_WORDS:
        return True
    if word in FALSE_WORDS:
        return False
    raise ConfigError(f"{name} must be true or false (got {value!r}).")


def _timezone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value.strip())
    except (ZoneInfoNotFoundError, ValueError):
        raise ConfigError(
            f"NM_TIMEZONE must be an IANA time zone such as 'Asia/Kolkata' (got {value!r})."
        ) from None


def _substack(env: Mapping[str, str]) -> SubstackSettings | None:
    if not _flag("NM_SUBSTACK_DRAFT", env.get("NM_SUBSTACK_DRAFT", "")):
        return None
    url = env.get("SUBSTACK_PUBLICATION_URL", "").strip().rstrip("/")
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.netloc:
        raise ConfigError(
            "NM_SUBSTACK_DRAFT is on: set SUBSTACK_PUBLICATION_URL to your https:// publication "
            f"address (got {url!r})."
        )
    cookies = env.get("SUBSTACK_COOKIES", "").strip()
    email = env.get("SUBSTACK_EMAIL", "").strip()
    password = env.get("SUBSTACK_PASSWORD", "")
    if not cookies and not (email and password):
        raise ConfigError(
            "NM_SUBSTACK_DRAFT is on: set SUBSTACK_COOKIES, or SUBSTACK_EMAIL and "
            "SUBSTACK_PASSWORD."
        )
    return SubstackSettings(url, cookies=cookies, email=email, password=password)


def issue_timezone(env: Mapping[str, str] | None = None) -> ZoneInfo:
    """``NM_TIMEZONE`` for dating an issue, or UTC when it is invalid (the error itself is
    reported by ``load_weekly_settings``)."""
    try:
        return _timezone(_load_env(env).get("NM_TIMEZONE", DEFAULT_TIMEZONE))
    except ConfigError:
        return FALLBACK_TIMEZONE


def load_weekly_settings(env: Mapping[str, str] | None = None) -> WeeklySettings:
    """``NM_TIMEZONE`` (issue date) and the opt-in Substack step (``NM_SUBSTACK_DRAFT``)."""
    env = _load_env(env)
    return WeeklySettings(
        timezone=_timezone(env.get("NM_TIMEZONE", DEFAULT_TIMEZONE)),
        substack=_substack(env),
    )

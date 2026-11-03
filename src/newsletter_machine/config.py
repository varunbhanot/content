"""Environment-based configuration, validated at the boundary."""

import logging
import math
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

logger = logging.getLogger(__name__)

DEFAULT_WRITER_MODEL = "anthropic:claude-sonnet-5-5"
DEFAULT_FAST_MODEL = "anthropic:claude-haiku-5-5"
DEFAULT_VOICE_DIR = "voice"
DEFAULT_GMAIL_LABEL = "newsletter"
DEFAULT_GMAIL_CLIENT_SECRETS = ".secrets/gmail-client.json"
DEFAULT_GMAIL_TOKEN = ".secrets/gmail-token.json"
DEFAULT_FETCH_TIMEOUT = "20"
DEFAULT_TRANSCRIPT_LANGUAGES = "en"
DEFAULT_GMAIL_ALLOWED_SENDERS = "me"
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
class IngestSettings:
    """Settings for ``ingest``; deliberately independent of the Anthropic key."""

    gmail_label: str
    gmail_allowed_senders: tuple[str, ...]
    gmail_client_secrets: Path
    gmail_token: Path
    fetch_timeout: float
    transcript_languages: tuple[str, ...]


def _load_env(env: Mapping[str, str] | None) -> Mapping[str, str]:
    if env is None:
        load_dotenv(find_dotenv(usecwd=True))
        return os.environ
    return env


def _resolve_path(value: str, repo_root: Path | None) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (repo_root or Path.cwd()) / path


def _require_provider_prefix(name: str, value: str) -> str:
    value = value.strip()  # a stray space from .env must not reach the API as part of the id
    provider, sep, model = value.partition(":")
    if not sep or not provider or not model:
        raise ConfigError(f"{name} must look like 'provider:model' (got {value!r}).")
    return value


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

    voice_dir = _resolve_path(env.get("NM_VOICE_DIR", DEFAULT_VOICE_DIR), repo_root)
    if not (voice_dir / "samples" / "hand").is_dir():
        raise ConfigError(f"Voice corpus not found: {voice_dir}/samples/hand does not exist.")

    return Settings(
        anthropic_api_key=api_key,
        writer_model=writer_model,
        fast_model=fast_model,
        voice_dir=voice_dir,
        critic_model=critic_model,
    )


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
    env: Mapping[str, str] | None = None, *, repo_root: Path | None = None
) -> IngestSettings:
    """Load ingest settings from ``env`` (or ``.env`` + process env when ``env`` is None)."""
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
    )

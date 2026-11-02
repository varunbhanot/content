"""Environment-based configuration, validated at the boundary."""

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

logger = logging.getLogger(__name__)

DEFAULT_WRITER_MODEL = "anthropic:claude-sonnet-5-5"
DEFAULT_FAST_MODEL = "anthropic:claude-haiku-5-5"
DEFAULT_VOICE_DIR = "voice"


class ConfigError(Exception):
    """Raised when configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str = field(repr=False)
    writer_model: str
    fast_model: str
    voice_dir: Path


def _require_provider_prefix(name: str, value: str) -> str:
    provider, sep, model = value.partition(":")
    if not sep or not provider or not model:
        raise ConfigError(f"{name} must look like 'provider:model' (got {value!r}).")
    return value


def load_settings(
    env: Mapping[str, str] | None = None, *, repo_root: Path | None = None
) -> Settings:
    """Load settings from ``env`` (or ``.env`` + process env when ``env`` is None)."""
    if env is None:
        load_dotenv(find_dotenv(usecwd=True))
        env = os.environ

    api_key = env.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise ConfigError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key."
        )

    writer_model = _require_provider_prefix(
        "NM_WRITER_MODEL", env.get("NM_WRITER_MODEL", DEFAULT_WRITER_MODEL)
    )
    fast_model = _require_provider_prefix(
        "NM_FAST_MODEL", env.get("NM_FAST_MODEL", DEFAULT_FAST_MODEL)
    )

    voice_dir = Path(env.get("NM_VOICE_DIR", DEFAULT_VOICE_DIR))
    if not voice_dir.is_absolute():
        voice_dir = (repo_root or Path.cwd()) / voice_dir
    if not (voice_dir / "samples" / "hand").is_dir():
        raise ConfigError(f"Voice corpus not found: {voice_dir}/samples/hand does not exist.")

    return Settings(
        anthropic_api_key=api_key,
        writer_model=writer_model,
        fast_model=fast_model,
        voice_dir=voice_dir,
    )

from collections.abc import Callable
from pathlib import Path

import pytest

from newsletter_machine.config import ConfigError, load_settings


def test_load_settings_returns_settings_with_defaults(make_voice_dir: Callable[..., Path]) -> None:
    voice = make_voice_dir()
    settings = load_settings({"ANTHROPIC_API_KEY": "sk-ant-x", "NM_VOICE_DIR": str(voice)})
    assert settings.writer_model == "anthropic:claude-sonnet-5-5"
    assert settings.fast_model == "anthropic:claude-haiku-5-5"
    assert settings.voice_dir == voice


def test_load_settings_raises_when_api_key_missing(make_voice_dir: Callable[..., Path]) -> None:
    voice = make_voice_dir()
    with pytest.raises(ConfigError, match=r"\.env\.example"):
        load_settings({"NM_VOICE_DIR": str(voice)})


def test_load_settings_raises_when_api_key_blank(make_voice_dir: Callable[..., Path]) -> None:
    voice = make_voice_dir()
    with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
        load_settings({"ANTHROPIC_API_KEY": "  ", "NM_VOICE_DIR": str(voice)})


def test_load_settings_rejects_model_without_provider_prefix(
    make_voice_dir: Callable[..., Path],
) -> None:
    voice = make_voice_dir()
    env = {
        "ANTHROPIC_API_KEY": "k",
        "NM_VOICE_DIR": str(voice),
        "NM_WRITER_MODEL": "claude-sonnet-5-5",
    }
    with pytest.raises(ConfigError, match="NM_WRITER_MODEL"):
        load_settings(env)


def test_load_settings_raises_when_hand_samples_dir_missing(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="samples/hand"):
        load_settings({"ANTHROPIC_API_KEY": "k", "NM_VOICE_DIR": str(tmp_path)})


def test_load_settings_resolves_relative_voice_dir_against_repo_root(
    make_voice_dir: Callable[..., Path],
) -> None:
    voice = make_voice_dir()
    settings = load_settings(
        {"ANTHROPIC_API_KEY": "k", "NM_VOICE_DIR": "voice"}, repo_root=voice.parent
    )
    assert settings.voice_dir == voice


def test_settings_repr_hides_api_key(make_voice_dir: Callable[..., Path]) -> None:
    voice = make_voice_dir()
    settings = load_settings({"ANTHROPIC_API_KEY": "sk-ant-secret", "NM_VOICE_DIR": str(voice)})
    assert "secret" not in repr(settings)


def test_load_settings_reads_process_env_and_dotenv_when_env_is_none(
    make_voice_dir: Callable[..., Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    voice = make_voice_dir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("NM_VOICE_DIR", str(voice))
    assert load_settings().voice_dir == voice

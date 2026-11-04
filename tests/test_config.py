from collections.abc import Callable
from pathlib import Path

import pytest

from newsletter_machine import config
from newsletter_machine.config import (
    ConfigError,
    load_editor_settings,
    load_ingest_settings,
    load_planner_model,
    load_relevance_model,
    load_settings,
    load_summary_model,
)


def test_load_settings_returns_settings_with_defaults(make_voice_dir: Callable[..., Path]) -> None:
    voice = make_voice_dir()
    settings = load_settings({"ANTHROPIC_API_KEY": "sk-ant-x", "NM_VOICE_DIR": str(voice)})
    assert settings.writer_model == "anthropic:claude-sonnet-5-5"
    assert settings.fast_model == "anthropic:claude-haiku-5-5"
    assert settings.voice_dir == voice


def test_critic_model_defaults_to_writer_model(make_voice_dir: Callable[..., Path]) -> None:
    env = {"ANTHROPIC_API_KEY": "k", "NM_VOICE_DIR": str(make_voice_dir())}
    settings = load_settings({**env, "NM_WRITER_MODEL": "anthropic:w"})
    assert settings.critic_model == "anthropic:w"


def test_blank_critic_model_falls_back_to_writer_model(
    make_voice_dir: Callable[..., Path],
) -> None:
    env = {"ANTHROPIC_API_KEY": "k", "NM_VOICE_DIR": str(make_voice_dir())}
    settings = load_settings({**env, "NM_WRITER_MODEL": "anthropic:w", "NM_CRITIC_MODEL": " "})
    assert settings.critic_model == "anthropic:w"


def test_critic_model_can_be_set(make_voice_dir: Callable[..., Path]) -> None:
    env = {"ANTHROPIC_API_KEY": "k", "NM_VOICE_DIR": str(make_voice_dir())}
    assert load_settings({**env, "NM_CRITIC_MODEL": "anthropic:c"}).critic_model == "anthropic:c"


def test_critic_model_requires_provider_prefix(make_voice_dir: Callable[..., Path]) -> None:
    env = {"ANTHROPIC_API_KEY": "k", "NM_VOICE_DIR": str(make_voice_dir())}
    with pytest.raises(ConfigError, match="NM_CRITIC_MODEL"):
        load_settings({**env, "NM_CRITIC_MODEL": "c"})


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


def test_load_ingest_settings_defaults_without_anthropic_key(tmp_path: Path) -> None:
    settings = load_ingest_settings({}, repo_root=tmp_path)
    assert settings.gmail_label == "newsletter"
    assert settings.gmail_client_secrets == tmp_path / ".secrets" / "gmail-client.json"
    assert settings.gmail_token == tmp_path / ".secrets" / "gmail-token.json"
    assert settings.fetch_timeout == 20.0
    assert settings.transcript_languages == ("en",)


def test_load_ingest_settings_reads_overrides(tmp_path: Path) -> None:
    env = {
        "NM_GMAIL_LABEL": " Reading/Newsletter ",
        "NM_GMAIL_CLIENT_SECRETS": "/abs/client.json",
        "NM_GMAIL_TOKEN": "tok.json",
        "NM_FETCH_TIMEOUT": "5.5",
        "NM_TRANSCRIPT_LANGUAGES": "en, de ,",
    }
    settings = load_ingest_settings(env, repo_root=tmp_path)
    assert settings.gmail_label == "Reading/Newsletter"
    assert settings.gmail_client_secrets == Path("/abs/client.json")
    assert settings.gmail_token == tmp_path / "tok.json"
    assert settings.fetch_timeout == 5.5
    assert settings.transcript_languages == ("en", "de")


@pytest.mark.parametrize(
    ("env", "name"),
    [
        ({"NM_GMAIL_LABEL": "  "}, "NM_GMAIL_LABEL"),
        ({"NM_FETCH_TIMEOUT": "soon"}, "NM_FETCH_TIMEOUT"),
        ({"NM_FETCH_TIMEOUT": "0"}, "NM_FETCH_TIMEOUT"),
        ({"NM_FETCH_TIMEOUT": "nan"}, "NM_FETCH_TIMEOUT"),
        ({"NM_TRANSCRIPT_LANGUAGES": " , "}, "NM_TRANSCRIPT_LANGUAGES"),
    ],
)
def test_load_ingest_settings_rejects_invalid_values(
    env: dict[str, str], name: str, tmp_path: Path
) -> None:
    with pytest.raises(ConfigError, match=name):
        load_ingest_settings(env, repo_root=tmp_path)


def test_load_ingest_settings_reads_process_env_when_env_is_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NM_GMAIL_LABEL", "from-env")
    assert load_ingest_settings().gmail_label == "from-env"


def test_load_ingest_settings_parses_allowed_senders(tmp_path: Path) -> None:
    assert load_ingest_settings({}, repo_root=tmp_path).gmail_allowed_senders == ("me",)
    env = {"NM_GMAIL_ALLOWED_SENDERS": "me, work@example.com"}
    settings = load_ingest_settings(env, repo_root=tmp_path)
    assert settings.gmail_allowed_senders == ("me", "work@example.com")


@pytest.mark.parametrize("value", [" , ", "a b@example.com", "x{y}"])
def test_load_ingest_settings_rejects_bad_allowed_senders(value: str, tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="NM_GMAIL_ALLOWED_SENDERS"):
        load_ingest_settings({"NM_GMAIL_ALLOWED_SENDERS": value}, repo_root=tmp_path)


def test_model_settings_are_stripped(make_voice_dir: Callable[..., Path]) -> None:
    env = {"ANTHROPIC_API_KEY": "k", "NM_VOICE_DIR": str(make_voice_dir())}
    settings = load_settings({**env, "NM_WRITER_MODEL": " anthropic:w ", "NM_FAST_MODEL": "a:f "})
    assert (settings.writer_model, settings.critic_model, settings.fast_model) == (
        "anthropic:w",
        "anthropic:w",
        "a:f",
    )


def test_editor_model_defaults_to_writer_model(make_voice_dir: Callable[..., Path]) -> None:
    env = {"ANTHROPIC_API_KEY": "k", "NM_VOICE_DIR": str(make_voice_dir())}
    env = {**env, "NM_WRITER_MODEL": "anthropic:w", "NM_EDITOR_MODEL": " "}
    assert load_editor_settings(load_settings(env), env).editor_model == "anthropic:w"


def test_editor_model_can_be_set(make_voice_dir: Callable[..., Path]) -> None:
    env = {"ANTHROPIC_API_KEY": "k", "NM_VOICE_DIR": str(make_voice_dir())}
    env = {**env, "NM_EDITOR_MODEL": "anthropic:e"}
    assert load_editor_settings(load_settings(env), env).editor_model == "anthropic:e"


def test_editor_model_requires_provider_prefix(make_voice_dir: Callable[..., Path]) -> None:
    env = {"ANTHROPIC_API_KEY": "k", "NM_VOICE_DIR": str(make_voice_dir())}
    env = {**env, "NM_EDITOR_MODEL": "e"}
    with pytest.raises(ConfigError, match="NM_EDITOR_MODEL"):
        load_editor_settings(load_settings(env), env)


def test_max_revisions_defaults_to_one(make_voice_dir: Callable[..., Path]) -> None:
    env = {"ANTHROPIC_API_KEY": "k", "NM_VOICE_DIR": str(make_voice_dir())}
    assert load_editor_settings(load_settings(env), env).max_revisions == 1


@pytest.mark.parametrize(("value", "expected"), [("0", 0), (" 3 ", 3), ("", 1)])
def test_max_revisions_accepts_zero_to_three(
    make_voice_dir: Callable[..., Path], value: str, expected: int
) -> None:
    env = {"ANTHROPIC_API_KEY": "k", "NM_VOICE_DIR": str(make_voice_dir())}
    env = {**env, "NM_MAX_REVISIONS": value}
    assert load_editor_settings(load_settings(env), env).max_revisions == expected


@pytest.mark.parametrize("value", ["4", "-1", "x", "1.5", "true", "²"])
def test_max_revisions_rejects_out_of_range(
    make_voice_dir: Callable[..., Path], value: str
) -> None:
    env = {"ANTHROPIC_API_KEY": "k", "NM_VOICE_DIR": str(make_voice_dir())}
    env = {**env, "NM_MAX_REVISIONS": value}
    with pytest.raises(ConfigError, match="NM_MAX_REVISIONS"):
        load_editor_settings(load_settings(env), env)


def test_issue_only_settings_do_not_break_other_commands(
    make_voice_dir: Callable[..., Path],
) -> None:
    env = {"ANTHROPIC_API_KEY": "k", "NM_VOICE_DIR": str(make_voice_dir())}
    bad = {**env, "NM_MAX_REVISIONS": "9", "NM_EDITOR_MODEL": "nope"}
    settings = load_settings(bad)  # hello and draft never read them
    with pytest.raises(ConfigError, match="NM_EDITOR_MODEL"):
        load_editor_settings(settings, bad)


@pytest.mark.parametrize(
    ("value", "expected"), [("", "anthropic:w"), (" anthropic:p ", "anthropic:p")]
)
def test_planner_model_defaults_to_writer_model(
    make_voice_dir: Callable[..., Path], value: str, expected: str
) -> None:
    env = {"ANTHROPIC_API_KEY": "k", "NM_VOICE_DIR": str(make_voice_dir())}
    env = {**env, "NM_WRITER_MODEL": "anthropic:w", "NM_PLANNER_MODEL": value}
    assert load_planner_model(load_settings(env), env) == expected


def test_planner_model_requires_provider_prefix(make_voice_dir: Callable[..., Path]) -> None:
    env = {"ANTHROPIC_API_KEY": "k", "NM_VOICE_DIR": str(make_voice_dir()), "NM_PLANNER_MODEL": "p"}
    with pytest.raises(ConfigError, match="NM_PLANNER_MODEL"):
        load_planner_model(load_settings(env), env)


@pytest.mark.parametrize(
    ("value", "expected"), [("", "anthropic:f"), (" anthropic:r ", "anthropic:r")]
)
def test_relevance_model_defaults_to_fast_model(
    make_voice_dir: Callable[..., Path], value: str, expected: str
) -> None:
    env = {"ANTHROPIC_API_KEY": "k", "NM_VOICE_DIR": str(make_voice_dir())}
    env = {**env, "NM_FAST_MODEL": "anthropic:f", "NM_RELEVANCE_MODEL": value}
    assert load_relevance_model(load_settings(env), env) == expected


def test_relevance_model_requires_provider_prefix(make_voice_dir: Callable[..., Path]) -> None:
    env = {"ANTHROPIC_API_KEY": "k", "NM_VOICE_DIR": str(make_voice_dir())}
    env = {**env, "NM_RELEVANCE_MODEL": "r"}
    with pytest.raises(ConfigError, match="NM_RELEVANCE_MODEL"):
        load_relevance_model(load_settings(env), env)


@pytest.mark.parametrize(
    ("value", "expected"), [("", "anthropic:f"), (" anthropic:s ", "anthropic:s")]
)
def test_summary_model_defaults_to_fast_model(
    make_voice_dir: Callable[..., Path], value: str, expected: str
) -> None:
    env = {"ANTHROPIC_API_KEY": "k", "NM_VOICE_DIR": str(make_voice_dir())}
    env = {**env, "NM_FAST_MODEL": "anthropic:f", "NM_SUMMARY_MODEL": value}
    assert load_summary_model(load_settings(env), env) == expected


def test_summary_model_requires_provider_prefix(make_voice_dir: Callable[..., Path]) -> None:
    env = {"ANTHROPIC_API_KEY": "k", "NM_VOICE_DIR": str(make_voice_dir())}
    env = {**env, "NM_SUMMARY_MODEL": "s"}
    with pytest.raises(ConfigError, match="NM_SUMMARY_MODEL"):
        load_summary_model(load_settings(env), env)

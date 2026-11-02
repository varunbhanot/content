from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from newsletter_machine import cli
from newsletter_machine.cli import extract_text, main


def test_cli_hello_exits_2_without_api_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert main(["hello"]) == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err


def test_extract_text_returns_str_content_unchanged() -> None:
    assert extract_text("plain") == "plain"


def test_extract_text_joins_text_blocks() -> None:
    blocks = [{"type": "text", "text": "a"}, {"type": "tool_use"}, {"type": "text", "text": "b"}]
    assert extract_text(blocks) == "ab"


class _FakeAgent:
    def __init__(self) -> None:
        self.payload: dict[str, Any] = {}

    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.payload = payload
        return {"messages": [type("M", (), {"content": "answer"})()]}


def test_cli_hello_prints_agent_answer(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    make_voice_dir: Callable[..., Path],
) -> None:
    voice = make_voice_dir()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("NM_VOICE_DIR", str(voice))
    fake = _FakeAgent()
    monkeypatch.setattr(cli, "build_hello_agent", lambda settings: fake)
    assert main(["hello", "--question", "why?"]) == 0
    assert capsys.readouterr().out.strip() == "answer"
    assert fake.payload["messages"][0]["content"] == "why?"


def test_cli_hello_exits_1_when_agent_fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    make_voice_dir: Callable[..., Path],
) -> None:
    voice = make_voice_dir()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("NM_VOICE_DIR", str(voice))

    class _Boom:
        def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("network down")

    monkeypatch.setattr(cli, "build_hello_agent", lambda settings: _Boom())
    assert main(["hello"]) == 1
    assert "network down" in capsys.readouterr().err

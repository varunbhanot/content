import hashlib
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from dotenv import dotenv_values
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from newsletter_machine.agent import build_hello_agent
from newsletter_machine.config import Settings, load_settings
from newsletter_machine.voice import load_voice_corpus

REPO_ROOT = Path(__file__).resolve().parent.parent


class _ToolFriendlyFake(GenericFakeChatModel):
    def bind_tools(self, tools: Any, **kwargs: Any) -> "_ToolFriendlyFake":
        return self


def _fake() -> _ToolFriendlyFake:
    return _ToolFriendlyFake(messages=iter([AIMessage(content="hi")]))


def _settings(voice: Path) -> Settings:
    return load_settings({"ANTHROPIC_API_KEY": "k", "NM_VOICE_DIR": str(voice)})


def test_build_hello_agent_compiles_with_fake_model(make_voice_dir: Callable[..., Path]) -> None:
    agent = build_hello_agent(_settings(make_voice_dir()), model=_fake())
    assert hasattr(agent, "invoke")


def test_hello_agent_invoke_returns_model_reply(make_voice_dir: Callable[..., Path]) -> None:
    agent = build_hello_agent(_settings(make_voice_dir()), model=_fake())
    result = agent.invoke({"messages": [{"role": "user", "content": "hello"}]})
    assert result["messages"][-1].content == "hi"


def test_hello_agent_denies_write_file_tool(make_voice_dir: Callable[..., Path]) -> None:
    voice = make_voice_dir()
    call = {
        "name": "write_file",
        "args": {"file_path": "/samples/hand/new.md", "content": "x"},
        "id": "1",
    }
    model = _ToolFriendlyFake(
        messages=iter([AIMessage(content="", tool_calls=[call]), AIMessage(content="done")])
    )
    agent = build_hello_agent(_settings(voice), model=model)
    result = agent.invoke({"messages": [{"role": "user", "content": "write"}]})
    assert not (voice / "samples" / "hand" / "new.md").exists()
    assert "permission" in str(result["messages"][-2].content).lower()


def test_build_hello_agent_uses_settings_key_not_process_env(
    make_voice_dir: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    agent = build_hello_agent(_settings(make_voice_dir()))
    assert hasattr(agent, "invoke")


def _hash_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


# Read .env without mutating os.environ so the live test can find a key stored only there.
LIVE_ENV = {**dotenv_values(REPO_ROOT / ".env"), **os.environ}


@pytest.fixture
def real_settings() -> Settings:
    return load_settings(LIVE_ENV, repo_root=REPO_ROOT)


@pytest.mark.live
@pytest.mark.skipif(not LIVE_ENV.get("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY")
def test_hello_agent_live_cites_hand_post(real_settings: Settings) -> None:
    before = _hash_tree(real_settings.voice_dir)
    agent = build_hello_agent(real_settings)
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "List hand-written posts and name one title."}]}
    )
    text = str(result["messages"][-1].content).lower()
    titles = [s.title.lower() for s in load_voice_corpus(real_settings.voice_dir, era="hand")]
    assert any(t[:20] in text for t in titles)
    assert _hash_tree(real_settings.voice_dir) == before


def test_make_chat_model_passes_anthropic_key_only_to_anthropic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from newsletter_machine import agent

    calls: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(agent, "init_chat_model", lambda m, **kw: calls.append((m, kw)))
    agent.make_chat_model("anthropic:a", "secret")
    agent.make_chat_model("openai:b", "secret")
    assert calls == [("anthropic:a", {"api_key": "secret"}), ("openai:b", {})]

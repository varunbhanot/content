from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from newsletter_machine import cli, config
from newsletter_machine.cli import main
from newsletter_machine.critic import judgement_items
from newsletter_machine.grounding import load_grounding

ROOT = Path(__file__).resolve().parent.parent
VOICE = ROOT / "voice"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "sources"
DRAFT = "# Evals are the moat\n\nThe demo worked. Production did not.\n\n## Sources\n\n- [A](u)\n"


class FakeModel(GenericFakeChatModel):
    def bind_tools(self, tools: Any, **kwargs: Any) -> "FakeModel":
        return self


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("NM_VOICE_DIR", str(VOICE))
    monkeypatch.setenv("NM_WRITER_MODEL", "fake:writer")
    monkeypatch.setenv("NM_CRITIC_MODEL", "fake:critic")


def _all_pass() -> AIMessage:
    items = judgement_items(load_grounding(VOICE).checklist)
    verdicts = [{"item_id": item.id, "passed": True} for item in items]
    args = {"verdicts": verdicts, "summary": "Sounds like Varun."}
    return AIMessage(content="", tool_calls=[{"name": "CriticOutput", "args": args, "id": "1"}])


def _use_models(
    monkeypatch: pytest.MonkeyPatch, writer: list[AIMessage], critic: list[AIMessage]
) -> dict[str, str]:
    seen: dict[str, str] = {}
    models = {"fake:writer": writer, "fake:critic": critic}

    def _make(model: str, api_key: str) -> FakeModel:
        seen[model] = api_key
        return FakeModel(messages=iter(models[model]))

    monkeypatch.setattr(cli, "make_chat_model", _make)
    return seen


def _draft(tmp_path: Path, *extra: str) -> int:
    out = tmp_path / "issue.md"
    return main(["draft", "--sources", str(FIXTURES), "--out", str(out), *extra])


def test_draft_writes_draft_and_critique(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seen = _use_models(monkeypatch, [AIMessage(content=DRAFT)], [_all_pass()])
    assert _draft(tmp_path, "--angle", "evals are the moat") == 0
    assert (tmp_path / "issue.md").read_text() == DRAFT
    critique = (tmp_path / "issue.critique.md").read_text()
    assert "Sounds like Varun." in critique
    assert "`length`" in critique  # mechanical item: far too short
    out = capsys.readouterr().out
    assert "Using 1 of 2 sources (1 failed source skipped)" in out
    assert "Wrote " in out and "issue.md (6 words)"  # title not counted in out
    assert "failed" in out and "issue.critique.md" in out
    assert seen == {"fake:writer": "k", "fake:critic": "k"}


def test_draft_exits_2_without_api_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert _draft(tmp_path) == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err


def test_draft_exits_2_on_missing_sources_dir(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["draft", "--sources", str(tmp_path / "x"), "--out", str(tmp_path / "d.md")])
    assert code == 2
    assert "not a directory" in capsys.readouterr().err


def test_draft_exits_2_when_all_sources_failed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    failed = FIXTURES / "02-failed-source.md"
    (sources / failed.name).write_text(failed.read_text())
    code = main(["draft", "--sources", str(sources), "--out", str(tmp_path / "d.md")])
    assert code == 2
    assert "No usable sources" in capsys.readouterr().err


def test_draft_exits_2_when_output_exists_before_calling_models(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seen = _use_models(monkeypatch, [], [])
    (tmp_path / "issue.md").write_text("mine")
    assert _draft(tmp_path) == 2
    assert "--overwrite" in capsys.readouterr().err
    assert seen == {}
    assert (tmp_path / "issue.md").read_text() == "mine"


def test_draft_overwrite_replaces_outputs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _use_models(monkeypatch, [AIMessage(content=DRAFT)], [_all_pass()])
    (tmp_path / "issue.md").write_text("old")
    assert _draft(tmp_path, "--overwrite") == 0
    assert (tmp_path / "issue.md").read_text() == DRAFT


def test_draft_exits_2_on_broken_voice_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    make_voice_dir: Callable[..., Path],
) -> None:
    monkeypatch.setenv("NM_VOICE_DIR", str(make_voice_dir()))
    assert _draft(tmp_path) == 2
    assert "style-guide.md" in capsys.readouterr().err


def test_draft_exits_1_when_writer_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _use_models(monkeypatch, [AIMessage(content=" ")], [])
    assert _draft(tmp_path) == 1
    assert "Writer failed" in capsys.readouterr().err
    assert not (tmp_path / "issue.md").exists()


def test_draft_exits_1_but_keeps_draft_when_critic_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _use_models(monkeypatch, [AIMessage(content=DRAFT)], [])  # critic model has no reply
    assert _draft(tmp_path) == 1
    err = capsys.readouterr().err
    assert "Critic failed" in err
    assert "draft kept" in err
    assert (tmp_path / "issue.md").read_text() == DRAFT
    assert not (tmp_path / "issue.critique.md").exists()


def test_draft_exits_1_when_draft_cannot_be_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _use_models(monkeypatch, [AIMessage(content=DRAFT)], [_all_pass()])

    def _boom(self: Path, *args: Any, **kwargs: Any) -> int:
        raise PermissionError("read-only disk")

    monkeypatch.setattr(Path, "write_text", _boom)
    assert _draft(tmp_path) == 1
    assert "read-only disk" in capsys.readouterr().err


def test_draft_removes_stale_critique_when_critic_fails_on_overwrite(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _use_models(monkeypatch, [AIMessage(content=DRAFT)], [])
    (tmp_path / "issue.md").write_text("old draft")
    (tmp_path / "issue.critique.md").write_text("old critique")
    assert _draft(tmp_path, "--overwrite") == 1
    assert (tmp_path / "issue.md").read_text() == DRAFT
    assert not (tmp_path / "issue.critique.md").exists()


def test_draft_exits_2_when_model_provider_package_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def _missing(model: str, api_key: str) -> FakeModel:
        raise ImportError("install langchain-openai")

    monkeypatch.setattr(cli, "make_chat_model", _missing)
    assert _draft(tmp_path) == 2
    assert "langchain-openai" in capsys.readouterr().err


def test_draft_network_oserror_in_critic_reports_critic_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _use_models(monkeypatch, [AIMessage(content=DRAFT)], [_all_pass()])

    def _reset(*args: Any) -> None:
        raise ConnectionResetError("connection reset")

    monkeypatch.setattr(cli, "run_critic", _reset)
    assert _draft(tmp_path) == 1
    assert "Critic failed: connection reset (draft kept at" in capsys.readouterr().err


def test_draft_exits_1_when_critique_cannot_be_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _use_models(monkeypatch, [AIMessage(content=DRAFT)], [_all_pass()])
    original = Path.write_text

    def _fail_critique(self: Path, *args: Any, **kwargs: Any) -> int:
        if self.name.endswith(".critique.md"):
            raise PermissionError("no space")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", _fail_critique)
    assert _draft(tmp_path) == 1
    assert "Could not write the critique: no space" in capsys.readouterr().err
    assert (tmp_path / "issue.md").exists()

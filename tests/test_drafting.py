from pathlib import Path
from typing import Any

import pytest
from deepagents import create_deep_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from newsletter_machine.drafting import build_subagents, check_outputs, output_paths, write_atomic
from newsletter_machine.grounding import load_grounding
from newsletter_machine.prompts import load_prompt

ROOT = Path(__file__).resolve().parent.parent


class FakeModel(GenericFakeChatModel):
    def bind_tools(self, tools: Any, **kwargs: Any) -> "FakeModel":
        return self


def _fake() -> FakeModel:
    return FakeModel(messages=iter([AIMessage(content="x")]))


def test_output_paths_puts_critique_next_to_draft(tmp_path: Path) -> None:
    paths = output_paths(tmp_path / "issue.md")
    assert paths.draft == tmp_path / "issue.md"
    assert paths.critique == tmp_path / "issue.critique.md"


def test_output_paths_requires_markdown_suffix(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"\.md"):
        output_paths(tmp_path / "issue.txt")


def test_check_outputs_refuses_existing_files(tmp_path: Path) -> None:
    paths = output_paths(tmp_path / "issue.md")
    paths.critique.write_text("old")
    with pytest.raises(FileExistsError, match="--overwrite"):
        check_outputs(paths, overwrite=False)
    check_outputs(paths, overwrite=True)


def test_check_outputs_refuses_directory_target(tmp_path: Path) -> None:
    (tmp_path / "issue.md").mkdir()
    with pytest.raises(IsADirectoryError):
        check_outputs(output_paths(tmp_path / "issue.md"), overwrite=True)


def test_check_outputs_refuses_missing_parent(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="nope"):
        check_outputs(output_paths(tmp_path / "nope" / "issue.md"), overwrite=False)


def test_build_subagents_plug_into_a_deep_agent() -> None:
    """Phase 4 contract: the lead agent takes these as ``task`` sub-agents unchanged."""
    agents = build_subagents(load_grounding(ROOT / "voice"), _fake(), _fake())
    assert (agents.writer["name"], agents.critic["name"]) == ("writer", "voice-critic")
    assert agents.writer_version == load_prompt("writer").version
    assert agents.critic_version == load_prompt("critic").version
    lead = create_deep_agent(model=_fake(), subagents=[agents.writer, agents.critic])
    assert hasattr(lead, "invoke")


def test_write_atomic_replaces_file_and_leaves_no_temp(tmp_path: Path) -> None:
    target = tmp_path / "issue.md"
    target.write_text("old")
    write_atomic(target, "new")
    assert target.read_text() == "new"
    assert [p.name for p in tmp_path.iterdir()] == ["issue.md"]


def test_write_atomic_keeps_old_file_when_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "issue.md"
    target.write_text("old")

    def _boom(self: Path, *args: Any, **kwargs: Any) -> int:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", _boom)
    with pytest.raises(OSError, match="disk full"):
        write_atomic(target, "new")
    assert target.read_text() == "old"
    assert [p.name for p in tmp_path.iterdir()] == ["issue.md"]

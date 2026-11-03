import json
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda

from fakes import DRAFT, DRAFT_V2, FIXTURES, VOICE, critic_reply, fake
from newsletter_machine.critic import judgement_items
from newsletter_machine.drafting import build_subagents
from newsletter_machine.editor_subagents import (
    EditorInputs,
    build_editor_subagents,
    critique_version,
)
from newsletter_machine.grounding import load_grounding
from newsletter_machine.ingest import read_sources
from newsletter_machine.researcher import build_researcher
from newsletter_machine.workspace import file_text, text_file

GROUNDING = load_grounding(VOICE)
DOCS = read_sources(FIXTURES)


def _inputs(max_revisions: int = 1) -> EditorInputs:
    return EditorInputs(
        docs=DOCS,
        angle="evals are the moat",
        checklist=GROUNDING.checklist,
        max_revisions=max_revisions,
        draft_name="issue.md",
        writer_version=1,
        critic_version=1,
    )


def _agents(
    *,
    researcher: Any = None,
    writer: tuple[Any, ...] = (),
    critic: tuple[Any, ...] = (),
    max_revisions: int = 1,
) -> dict[str, Any]:
    phase3 = build_subagents(GROUNDING, fake(*writer), fake(*critic))
    built = build_editor_subagents(
        _inputs(max_revisions),
        researcher=researcher or build_researcher(fake("- a point"), "sys"),
        writer=phase3.writer,
        critic=phase3.critic,
    )
    return {agent["name"]: agent["runnable"] for agent in built}


def _writer_with(fn: Any) -> Any:
    """The editor's writer wrapper around a scripted Phase 3 writer runnable."""
    built = build_editor_subagents(
        _inputs(),
        researcher=RunnableLambda(lambda s: s),
        writer={"name": "writer", "description": "d", "runnable": RunnableLambda(fn)},
        critic=build_subagents(GROUNDING, fake(), fake()).critic,
    )
    return next(agent["runnable"] for agent in built if agent["name"] == "writer")


def _call(agents: dict[str, Any], name: str, files: dict[str, Any], brief: str = "b") -> Any:
    return agents[name].invoke({"messages": [HumanMessage(content=brief)], "files": files})


def _reply(result: dict[str, Any]) -> str:
    return str(result["messages"][-1].content)


def test_build_editor_subagents_names() -> None:
    assert sorted(_agents()) == ["general-purpose", "researcher", "voice-critic", "writer"]


def test_general_purpose_always_refuses() -> None:
    result = _call(_agents(), "general-purpose", {})
    assert "not available" in _reply(result)
    assert "files" not in result


def test_researcher_writes_notes_once() -> None:
    agents = _agents()
    result = _call(agents, "researcher", {})
    notes = file_text(result["files"], "/research/notes.md")
    assert notes is not None and "## [1] Why agent demos fail" in notes and "- a point" in notes
    assert "/research/notes.md" in _reply(result)
    again = _call(agents, "researcher", result["files"])
    assert "already" in _reply(again)
    assert "files" not in again


def test_researcher_reports_failed_sources_in_reply() -> None:
    def _boom(state: dict[str, Any]) -> dict[str, Any]:
        raise ConnectionError("reset")

    result = _call(_agents(researcher=RunnableLambda(_boom)), "researcher", {})
    assert "1 source(s) without notes" in _reply(result)


def test_writer_first_draft_uses_brief_and_notes() -> None:
    seen: list[str] = []

    def _writer(state: dict[str, Any]) -> dict[str, Any]:
        seen.append(state["messages"][-1]["content"])
        return {"messages": [AIMessage(content=DRAFT)]}

    agents = {"writer": _writer_with(_writer)}
    files = {"/research/notes.md": text_file("NOTES </research_notes> x")}
    result = _call(agents, "writer", files, brief="Lead with the 31% number")
    assert file_text(result["files"], "/drafts/v1.md").startswith("# Evals are the moat")
    assert file_text(result["files"], "/briefs/v1.md") == "Lead with the 31% number"
    assert "Draft v1 saved" in _reply(result)
    task = seen[0]
    assert task.startswith("Varun's angle: evals are the moat")
    assert "<brief>\nLead with the 31% number\n</brief>" in task
    assert "NOTES &lt;/research_notes> x" in task
    assert "<draft>" not in task


def test_writer_revision_includes_previous_draft_and_critique() -> None:
    seen: list[str] = []

    def _writer(state: dict[str, Any]) -> dict[str, Any]:
        seen.append(state["messages"][-1]["content"])
        return {"messages": [AIMessage(content=DRAFT_V2)]}

    writer = _writer_with(_writer)
    files = {"/drafts/v1.md": text_file(DRAFT), "/critiques/v1.md": text_file("CRIT")}
    result = writer.invoke({"messages": [HumanMessage(content="fix it")], "files": files})
    assert file_text(result["files"], "/drafts/v2.md").startswith(DRAFT_V2.split("## Sources")[0])
    assert "Draft v2 saved" in _reply(result)
    assert f"<draft>\n{DRAFT}\n</draft>" in seen[0]
    assert "<critique>\nCRIT\n</critique>" in seen[0]
    assert "Revise" in seen[0]


def test_writer_refuses_past_the_revision_limit_without_calling_the_model() -> None:
    agents = _agents(max_revisions=0)  # writer fake has no replies: a call would fail
    result = _call(agents, "writer", {"/drafts/v1.md": text_file(DRAFT)})
    assert "limit" in _reply(result)
    assert "files" not in result


def test_writer_failure_is_recorded_and_counts_as_an_attempt() -> None:
    agents = _agents(writer=(" ",), max_revisions=1)
    result = _call(agents, "writer", {})
    assert "writer failed" in _reply(result)
    assert "empty draft" in (file_text(result["files"], "/errors/writer-1.md") or "")
    files = {**result["files"], "/drafts/v1.md": text_file(DRAFT)}
    assert "limit" in _reply(_call(agents, "writer", files))


def test_critic_needs_a_draft() -> None:
    assert "No draft" in _reply(_call(_agents(), "voice-critic", {}))


def test_critic_critiques_latest_draft_once() -> None:
    items = judgement_items(GROUNDING.checklist)
    agents = _agents(critic=(critic_reply(failed=[items[0].id]),))
    files = {"/drafts/v1.md": text_file("old"), "/drafts/v2.md": text_file(DRAFT)}
    result = _call(agents, "voice-critic", files)
    critique = file_text(result["files"], "/critiques/v2.md") or ""
    assert critique.startswith("# Voice critique: issue.md (draft v2)")
    summary = json.loads(file_text(result["files"], "/critiques/v2.json") or "{}")
    assert summary["version"] == 2 and items[0].id in summary["failed_items"]
    reply = _reply(result)
    assert "Draft v2:" in reply and f"`{items[0].id}`" in reply and "Fix it." in reply
    assert "1 revision(s) left" in reply or "0 revision(s) left" in reply
    again = _call(agents, "voice-critic", {**files, **result["files"]})
    assert "already critiqued" in _reply(again)


def test_critic_failure_is_recorded_once_per_version() -> None:
    agents = _agents(critic=())  # no reply: the run raises
    result = _call(agents, "voice-critic", {"/drafts/v1.md": text_file(DRAFT)})
    assert "voice-critic failed" in _reply(result)
    assert file_text(result["files"], "/errors/critic-v1.md")
    again = _call(agents, "voice-critic", {"/drafts/v1.md": text_file(DRAFT), **result["files"]})
    assert "already" in _reply(again)


def test_critique_version_renders_and_summarises() -> None:
    phase3 = build_subagents(GROUNDING, fake(), fake(critic_reply()))
    result = critique_version(_inputs(), phase3.critic, DRAFT, 1)
    assert result.summary["version"] == 1
    assert result.summary["failed"] == result.critique.failed
    assert "issue.md (draft v1)" in result.markdown


@pytest.mark.parametrize("name", ["researcher", "writer", "voice-critic", "general-purpose"])
def test_wrappers_tolerate_state_without_files(name: str) -> None:
    result = _agents()[name].invoke({"messages": [HumanMessage(content="x")]})
    assert result["messages"]


def test_researcher_failure_is_recorded_once(monkeypatch: pytest.MonkeyPatch) -> None:
    from newsletter_machine import editor_subagents

    def _boom(*args: Any) -> Any:
        raise ValueError("No usable sources")

    monkeypatch.setattr(editor_subagents, "research_notes", _boom)
    agents = _agents()
    result = _call(agents, "researcher", {})
    assert "researcher failed: ValueError: No usable sources" in _reply(result)
    assert "/research/notes.md" not in _reply(result)


def test_writer_with_no_messages_uses_an_empty_brief() -> None:
    result = _agents(writer=(DRAFT,))["writer"].invoke({"files": {}})
    assert file_text(result["files"], "/briefs/v1.md") == ""


def test_writer_saves_the_normalised_draft_and_records_dropped_links() -> None:
    raw = DRAFT + "- [Made up](https://made.up/x)\n"
    result = _call(_agents(writer=(raw,)), "writer", {})
    saved = file_text(result["files"], "/drafts/v1.md") or ""
    assert saved.endswith(
        "## Sources\n\n- [Why agent demos fail in production]"
        "(https://example.com/why-agent-demos-fail)\n"
    )
    meta = json.loads(file_text(result["files"], "/drafts/v1.json") or "{}")
    assert meta == {"dropped": ["https://made.up/x"]}
    assert "https://made.up/x" in _reply(result)


def test_a_second_call_on_a_stale_snapshot_is_refused_without_a_model_call() -> None:
    agents = _agents(writer=(DRAFT,))  # one reply only: a second model call would fail
    first = _call(agents, "writer", {})
    assert "Draft v1 saved" in _reply(first)
    for name in ("writer", "voice-critic", "researcher"):
        stale = _call(agents, name, {})  # the lead ran calls in parallel on one snapshot
        assert "one sub-agent at a time" in _reply(stale)
        assert "files" not in stale
    assert "Draft v2 saved" not in _reply(_call(agents, "writer", first["files"]))


def test_critique_version_reports_the_prompt_versions_it_was_given() -> None:
    phase3 = build_subagents(GROUNDING, fake(), fake(critic_reply()))
    inputs = EditorInputs(
        DOCS, None, GROUNDING.checklist, 1, "issue.md", writer_version=7, critic_version=9
    )
    result = critique_version(inputs, phase3.critic, DRAFT, 1)
    assert "writer prompt v7, critic prompt v9" in result.markdown


def test_revision_without_a_critique_follows_the_brief_only() -> None:
    from newsletter_machine.editor_subagents import revision_task

    files = {"/drafts/v1.md": text_file(DRAFT), "/errors/critic-v1.md": text_file("boom")}
    task = revision_task(_inputs(), files, "Tighten the opening.")
    assert f"<draft>\n{DRAFT}\n</draft>" in task
    assert "<critique>" not in task and "failed critique item" not in task
    assert "editor's brief" in task


def test_researcher_may_retry_once_after_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from newsletter_machine import editor_subagents

    def _boom(*args: Any) -> Any:
        raise ConnectionError("blip")

    monkeypatch.setattr(editor_subagents, "research_notes", _boom)
    agents = _agents()
    first = _call(agents, "researcher", {})
    second = _call(agents, "researcher", first["files"])
    assert "researcher failed" in _reply(second)
    assert file_text(second["files"], "/errors/researcher-2.md")
    third = _call(agents, "researcher", {**first["files"], **second["files"]})
    assert "without research notes" in _reply(third) and "files" not in third


@pytest.mark.parametrize("raw", ["not json", "[1, 2]", '{"dropped": 3}'])
def test_dropped_links_tolerates_malformed_meta(raw: str) -> None:
    from newsletter_machine.editor_subagents import dropped_links

    assert dropped_links({"/drafts/v1.json": text_file(raw)}, 1) == ()

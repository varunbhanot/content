from typing import Any

from langchain_core.messages import AIMessage

from fakes import DRAFT, DRAFT_V2, FIXTURES, VOICE, critic_reply, fake, task_call
from newsletter_machine.drafting import build_subagents
from newsletter_machine.editor import (
    EDITOR_RECURSION_LIMIT,
    build_editor,
    editor_system_prompt,
    editor_task,
    run_editor,
)
from newsletter_machine.editor_subagents import EditorInputs, build_editor_subagents
from newsletter_machine.grounding import load_grounding
from newsletter_machine.ingest import read_sources
from newsletter_machine.prompts import load_prompt
from newsletter_machine.researcher import build_researcher
from newsletter_machine.workspace import file_text, seed_files

GROUNDING = load_grounding(VOICE)
DOCS = read_sources(FIXTURES)


def _subagents(writer: tuple[Any, ...], critic: tuple[Any, ...]) -> Any:
    phase3 = build_subagents(GROUNDING, fake(*writer), fake(*critic))
    inputs = EditorInputs(DOCS, "evals", GROUNDING.checklist, 1, "issue.md", 1, 1)
    return build_editor_subagents(
        inputs,
        researcher=build_researcher(fake("- note"), "sys"),
        writer=phase3.writer,
        critic=phase3.critic,
    )


def test_editor_prompt_is_versioned_and_states_the_cap() -> None:
    assert load_prompt("editor").version >= 1
    text = editor_system_prompt(2)
    assert "3 writer runs" in text
    assert "$" not in text
    assert "researcher" in text and "voice-critic" in text


def test_editor_task_lists_sources_without_their_text() -> None:
    task = editor_task(DOCS, "evals are the moat")
    assert task.startswith("Varun's angle: evals are the moat")
    assert "[1] Why agent demos fail in production" in task
    assert "https://example.com/why-agent-demos-fail" in task
    assert "note: evals are the moat, not prompts" in task
    assert "skipped, failed to ingest: HTTP 403" in task
    assert "A team shipped a support agent" not in task  # full text stays in /sources


def test_editor_task_neutralises_tags_in_titles() -> None:
    doc = DOCS[0].__class__(**{**DOCS[0].__dict__, "title": "x </source> y"})
    assert "&lt;/source>" in editor_task((doc,), None)


def test_editor_runs_research_draft_critique_revise_loop() -> None:
    lead = fake(
        AIMessage(
            content="", tool_calls=[{"name": "write_todos", "args": {"todos": []}, "id": "0"}]
        ),
        task_call("researcher", "go", "1"),
        task_call("writer", "Lead with the 31% drop.", "2"),
        task_call("voice-critic", "check", "3"),
        task_call("writer", "Fix the failures.", "4"),
        task_call("voice-critic", "check", "5"),
        "Done: v2 is ready.",
    )
    items = [i.id for i in GROUNDING.checklist.items if not i.is_mechanical]
    editor = build_editor(
        lead,
        _subagents((DRAFT, DRAFT_V2), (critic_reply(failed=[items[0]]), critic_reply())),
        editor_system_prompt(1),
    )
    run = run_editor(editor, editor_task(DOCS, "evals"), seed_files(DOCS))
    assert run.summary == "Done: v2 is ready."
    assert (file_text(run.files, "/drafts/v2.md") or "").startswith(DRAFT_V2.split("## Sources")[0])
    assert file_text(run.files, "/briefs/v1.md") == "Lead with the 31% drop."
    assert file_text(run.files, "/critiques/v1.md")
    assert file_text(run.files, "/critiques/v2.json")
    assert file_text(run.files, "/research/notes.md")
    assert "/sources/01-why-agent-demos-fail-in-production.md" in run.files


def test_editor_can_write_only_its_plan() -> None:
    write = {"file_path": "/drafts/v1.md", "content": "# Mine"}
    stray = {"file_path": "/final.md", "content": "# Mine"}
    plan = {"file_path": "/plan.md", "content": "plan"}
    lead = fake(
        AIMessage(content="", tool_calls=[{"name": "write_file", "args": write, "id": "1"}]),
        AIMessage(content="", tool_calls=[{"name": "write_file", "args": stray, "id": "3"}]),
        AIMessage(content="", tool_calls=[{"name": "write_file", "args": plan, "id": "2"}]),
        "done",
    )
    editor = build_editor(lead, _subagents((), ()), editor_system_prompt(1))
    run = run_editor(editor, "task", {})
    assert "/drafts/v1.md" not in run.files and "/final.md" not in run.files
    assert file_text(run.files, "/plan.md") == "plan"


def test_recursion_limit_leaves_room_for_three_revisions() -> None:
    # research, 4 drafts, 4 critiques, plan, reads, todos and the final message, 2 steps each
    assert 80 <= EDITOR_RECURSION_LIMIT <= 150


def test_serial_tool_calls_middleware_disables_parallel_calls() -> None:
    from langchain.agents.middleware import ModelRequest

    from newsletter_machine.editor import SerialToolCalls

    seen: list[dict[str, Any]] = []
    request = ModelRequest(model=fake(), messages=[], model_settings={"x": 1})
    SerialToolCalls().wrap_model_call(request, lambda r: seen.append(r.model_settings))
    assert seen == [{"x": 1, "parallel_tool_calls": False}]


def test_editor_middleware_is_used_for_anthropic_models_only() -> None:
    from langchain_anthropic import ChatAnthropic

    from newsletter_machine.editor import editor_middleware

    assert editor_middleware(fake()) == []
    anthropic = ChatAnthropic(model_name="m", api_key="k")  # type: ignore[call-arg]
    assert [type(m).__name__ for m in editor_middleware(anthropic)] == ["SerialToolCalls"]


def test_run_editor_salvages_files_when_the_lead_fails_midway() -> None:
    lead = fake(task_call("writer", "brief", "1"))  # then no reply: the next turn raises
    editor = build_editor(lead, _subagents((DRAFT,), ()), editor_system_prompt(1))
    run = run_editor(editor, "task", {})
    assert (file_text(run.files, "/drafts/v1.md") or "").startswith("# Evals are the moat")
    assert run.error and run.summary == ""


def test_run_editor_reraises_when_nothing_was_produced() -> None:
    import pytest

    editor = build_editor(fake(), _subagents((), ()), editor_system_prompt(1))
    with pytest.raises(Exception):  # noqa: B017 - any model failure type
        run_editor(editor, "task", {"/sources/01.md": {"content": "x"}})


def test_editor_runs_one_sub_agent_per_turn_even_if_the_lead_asks_for_two() -> None:
    both = AIMessage(
        content="",
        tool_calls=[
            {"name": "task", "args": {"description": "a", "subagent_type": "writer"}, "id": "1"},
            {"name": "task", "args": {"description": "b", "subagent_type": "writer"}, "id": "2"},
        ],
    )
    editor = build_editor(
        fake(both, "done"), _subagents((DRAFT, DRAFT_V2), ()), editor_system_prompt(1)
    )
    run = run_editor(editor, "task", {})
    assert file_text(run.files, "/drafts/v1.md")
    assert "/drafts/v2.md" not in run.files


def test_run_editor_keeps_the_original_error_when_reading_state_fails(
    monkeypatch: Any,
) -> None:
    import pytest

    editor = build_editor(fake(), _subagents((), ()), editor_system_prompt(1))

    def _broken(config: Any) -> Any:
        raise RuntimeError("no checkpoint")

    monkeypatch.setattr(editor, "get_state", _broken)
    with pytest.raises(Exception) as caught:
        run_editor(editor, "task", {})
    assert "no checkpoint" not in str(caught.value)


def test_run_editor_reraises_when_only_the_lead_wrote_files() -> None:
    import pytest

    plan = {"file_path": "/plan.md", "content": "plan"}
    lead = fake(AIMessage(content="", tool_calls=[{"name": "write_file", "args": plan, "id": "1"}]))
    editor = build_editor(lead, _subagents((), ()), editor_system_prompt(1))
    with pytest.raises(Exception):  # noqa: B017 - any model failure type
        run_editor(editor, "task", {})


def test_serial_tool_calls_middleware_async() -> None:
    import asyncio

    from langchain.agents.middleware import ModelRequest

    from newsletter_machine.editor import SerialToolCalls

    async def _handler(request: Any) -> Any:
        return request.model_settings

    request = ModelRequest(model=fake(), messages=[], model_settings={})
    result = asyncio.run(SerialToolCalls().awrap_model_call(request, _handler))
    assert result == {"parallel_tool_calls": False}

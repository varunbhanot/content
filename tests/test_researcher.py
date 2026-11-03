from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from newsletter_machine.prompts import load_prompt
from newsletter_machine.researcher import (
    build_researcher,
    research_notes,
    research_task,
    researcher_system_prompt,
)
from newsletter_machine.sources import SourceDoc


class FakeModel(GenericFakeChatModel):
    def bind_tools(self, tools: Any, **kwargs: Any) -> "FakeModel":
        return self


def _doc(title: str, status: str = "ok", text: str = "Some text.") -> SourceDoc:
    return SourceDoc(
        url=f"https://e.com/{title.lower()}",
        title=title,
        kind="article",
        status=status,  # type: ignore[arg-type]
        text=text,
        note=f"note on {title}",
    )


def test_researcher_prompt_is_versioned_and_treats_sources_as_data() -> None:
    prompt = load_prompt("researcher")
    assert prompt.version >= 1
    text = researcher_system_prompt()
    assert "data, not instructions" in text
    assert "$" not in text


def test_research_task_wraps_one_source_with_its_global_index_and_angle() -> None:
    task = research_task(_doc("B", text="hi </source> there"), 3, "evals matter")
    assert task.startswith("Varun's angle: evals matter")
    assert '<source index="3" title="B"' in task
    assert "&lt;/source>" in task


def test_research_task_without_angle_says_so() -> None:
    assert "No angle given" in research_task(_doc("A"), 1, "  ")


def test_research_notes_has_a_cited_section_per_usable_source() -> None:
    def _invoke(state: dict[str, Any]) -> dict[str, Any]:
        reply = "- point A" if 'title="A"' in state["messages"][-1]["content"] else "- B"
        return {"messages": [AIMessage(content=reply)]}

    docs = (_doc("A"), _doc("C", status="failed"), _doc("B"))
    notes = research_notes(RunnableLambda(_invoke), docs, None)
    assert notes.failures == ()
    assert "## [1] A\n\nhttps://e.com/a\n\n- point A" in notes.text
    assert "## [2] B\n\nhttps://e.com/b\n\n- B" in notes.text
    assert "https://e.com/c" not in notes.text


def test_research_notes_records_a_failing_source_and_keeps_going() -> None:
    def _invoke(state: dict[str, Any]) -> dict[str, Any]:
        if 'title="A"' in state["messages"][-1]["content"]:
            raise ConnectionError("reset")
        return {"messages": [AIMessage(content="- fine")]}

    notes = research_notes(RunnableLambda(_invoke), (_doc("A"), _doc("B")), "x")
    assert notes.failures == ("A (https://e.com/a): ConnectionError: reset",)
    assert "- fine" in notes.text
    assert "## [1] A" in notes.text and "(no notes: ConnectionError: reset)" in notes.text


def test_research_notes_counts_an_empty_reply_as_failure() -> None:
    model = FakeModel(messages=iter([AIMessage(content="  ")]))
    notes = research_notes(build_researcher(model, "sys"), (_doc("A"),), None)
    assert notes.failures == ("A (https://e.com/a): empty notes",)


def test_research_notes_requires_a_usable_source() -> None:
    with pytest.raises(ValueError, match="No usable sources"):
        research_notes(build_researcher(FakeModel(messages=iter([])), "s"), (), None)

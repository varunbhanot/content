"""Researcher sub-agent: one fast-model call per source, returning short sourced notes."""

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable

from newsletter_machine.agent import extract_text
from newsletter_machine.prompts import Prompt, load_prompt, render
from newsletter_machine.sources import SourceDoc
from newsletter_machine.writer import angle_line, format_source, usable_sources

logger = logging.getLogger(__name__)

RESEARCHER_NAME = "researcher"
NOTES_TITLE = "# Research notes"


@dataclass(frozen=True)
class ResearchNotes:
    """Notes per usable source, numbered as the writer sees them; ``failures`` explain gaps."""

    text: str
    failures: tuple[str, ...]


def researcher_system_prompt(prompt: Prompt | None = None) -> str:
    return render(prompt or load_prompt(RESEARCHER_NAME))


def build_researcher(model: BaseChatModel, system_prompt: str) -> Runnable[Any, Any]:
    """A tool-less agent that reads one source per call."""
    return create_agent(model, tools=[], system_prompt=system_prompt, name=RESEARCHER_NAME)


def research_task(doc: SourceDoc, index: int, angle: str | None) -> str:
    """One source, numbered as in the writer's task, so ``[n]`` in the notes matches."""
    return f"{angle_line(angle)}\n\n{format_source(doc, index)}"


RESEARCH_CONCURRENCY = 4  # sources are independent; a few at once keeps rate limits happy


def _notes(result: Any) -> tuple[str, str]:
    """``(notes, failure reason)`` for one source's result or exception."""
    if isinstance(result, Exception):
        return "", f"{type(result).__name__}: {result}"
    body = extract_text(result["messages"][-1].content).strip()
    return body, "" if body else "empty notes"


def _section(doc: SourceDoc, index: int, body: str) -> str:
    return f"## [{index}] {doc.title}\n\n{doc.url}\n\n{body}"


def research_notes(
    researcher: Runnable[Any, Any], docs: Iterable[SourceDoc], angle: str | None
) -> ResearchNotes:
    """Notes for each usable source, a few at a time; a failing source is recorded, not fatal."""
    usable = usable_sources(docs)
    if not usable:
        raise ValueError("No usable sources: every source failed to ingest.")
    logger.info("Researching %d sources", len(usable))
    tasks = [
        {"messages": [{"role": "user", "content": research_task(doc, index, angle)}]}
        for index, doc in enumerate(usable, start=1)
    ]
    results = researcher.batch(
        tasks, config={"max_concurrency": RESEARCH_CONCURRENCY}, return_exceptions=True
    )
    sections: list[str] = []
    failures: list[str] = []
    for index, (doc, result) in enumerate(zip(usable, results, strict=True), start=1):
        body, reason = _notes(result)
        if reason:
            logger.warning("Research on %s failed: %s", doc.url, reason)
            failures.append(f"{doc.title} ({doc.url}): {reason}")
            body = f"(no notes: {reason})"
        sections.append(_section(doc, index, body))
    return ResearchNotes(
        text="\n\n".join([NOTES_TITLE, *sections]) + "\n", failures=tuple(failures)
    )

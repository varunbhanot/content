"""Series planner: proposes a multi-part outline from the sources past ``issue`` runs saved.

Code, not the model, owns the facts: sources come from ``drafts/<YYYY-MM-DD>.sources/``, the
model cites them by number, and code maps those numbers to titles and URLs, numbers the parts,
keeps Part 1 free and flags thin coverage.
"""

import logging
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from newsletter_machine.agent import AgentOutputError
from newsletter_machine.ingest import SOURCES_SUFFIX, has_ingested_sources, read_sources
from newsletter_machine.prompts import Prompt, load_prompt, render
from newsletter_machine.series import MIN_ARC_STEPS, Series, SeriesPart, SourceRef
from newsletter_machine.sources import SourceDoc, normalize_url
from newsletter_machine.writer import format_source, usable_sources

logger = logging.getLogger(__name__)

PLANNER_NAME = "planner"
MIN_PARTS = 3  # fewer is a single issue
MAX_PARTS = 6  # more needs splitting into two series
MIN_PART_SOURCES = 2  # fewer supporting sources marks a part thin
PLANNER_SOURCE_CHARS = 4_000  # an excerpt per source: enough to cluster, cheap over 4 weeks
MAX_PLANNER_SOURCES = 80  # ~320k characters of excerpts; more means --since is too wide
SOURCES_DIR = re.compile(rf"(\d{{4}}-\d{{2}}-\d{{2}}){re.escape(SOURCES_SUFFIX)}")


class PlannedPart(BaseModel):
    """One part as the model proposes it (the structured-output schema)."""

    title: str = Field(description="Working title in plain words.")
    question: str = Field(description="The one reader question this part answers.")
    brief: str = Field(description="2 to 4 sentences for the writer.")
    arc: list[str] = Field(description="2 to 5 steps, from the basic idea to the advanced one.")
    access: Literal["free", "paid"] = Field(description="Part 1 is free; deeper parts may be paid.")
    source_indexes: list[int] = Field(description="Numbers of the sources that support it.")
    thin: bool = Field(description="True when the part needs more reading.")
    needs: str = Field(default="", description="What Varun should read next, if thin.")


class SeriesPlan(BaseModel):
    parts: list[PlannedPart] = Field(description="The parts, in reading order.")


@dataclass(frozen=True)
class PlanningInput:
    dirs: tuple[Path, ...]  # the dated source folders read, oldest first
    docs: tuple[SourceDoc, ...]  # usable sources, one per URL (the newest copy)


def _folder_date(path: Path) -> date | None:
    match = SOURCES_DIR.fullmatch(path.name)
    if match is None or not path.is_dir():
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def saved_source_dirs(drafts_dir: Path, since: date) -> tuple[Path, ...]:
    """``<YYYY-MM-DD>.sources`` folders in ``drafts_dir`` dated ``since`` or later, oldest first."""
    if not drafts_dir.is_dir():
        raise ValueError(f"--drafts-dir {drafts_dir} is not a directory.")
    dated = ((day, path) for path in drafts_dir.iterdir() if (day := _folder_date(path)))
    return tuple(path for day, path in sorted(dated) if day >= since)


def _dedupe(docs: Iterable[SourceDoc]) -> tuple[SourceDoc, ...]:
    """One doc per normalised URL: first position kept; the newest copy wins, except that a
    fallback (e.g. a video description) never replaces an earlier full text."""
    by_url: dict[str, SourceDoc] = {}
    for doc in docs:
        key = normalize_url(doc.url)
        earlier = by_url.get(key)
        if earlier is None or doc.status == "ok" or earlier.status != "ok":
            by_url[key] = doc
    return tuple(by_url.values())


def collect_sources(drafts_dir: Path, since: date) -> PlanningInput:
    """Usable saved sources in the window; none is a usage error (raised before any model call)."""
    dirs = tuple(d for d in saved_source_dirs(drafts_dir, since) if has_ingested_sources(d))
    docs = _dedupe(doc for folder in dirs for doc in usable_sources(read_sources(folder)))
    if not docs:
        raise ValueError(
            f"No usable saved sources in {drafts_dir} since {since:%Y-%m-%d} "
            "(<YYYY-MM-DD>.sources folders written by 'issue'). Run 'issue' first, "
            "or widen --since."
        )
    if len(docs) > MAX_PLANNER_SOURCES:
        raise ValueError(
            f"{len(docs)} saved sources since {since:%Y-%m-%d} is more than one plan can read "
            f"({MAX_PLANNER_SOURCES}); narrow --since."
        )
    logger.info("Planning from %d sources in %d folders", len(docs), len(dirs))
    return PlanningInput(dirs=dirs, docs=docs)


def planner_system_prompt(prompt: Prompt | None = None) -> str:
    return render(
        prompt or load_prompt(PLANNER_NAME), min_parts=str(MIN_PARTS), max_parts=str(MAX_PARTS)
    )


def planner_task(topic: str, docs: Sequence[SourceDoc]) -> str:
    """The user message: the topic, then every source excerpt, numbered from 1."""
    sources = "\n\n".join(
        format_source(doc, index, PLANNER_SOURCE_CHARS) for index, doc in enumerate(docs, start=1)
    )
    return f"Series topic: {topic}\n\nSaved sources from the last few weeks:\n\n{sources}"


def build_planner(model: BaseChatModel, system_prompt: str) -> Runnable[Any, Any]:
    """A tool-less agent with structured output (strategy picked per model, as for the critic)."""
    return create_agent(
        model, tools=[], system_prompt=system_prompt, response_format=SeriesPlan, name=PLANNER_NAME
    )


def _check_part(part: PlannedPart, number: int) -> None:
    for name in ("title", "question", "brief"):
        if not getattr(part, name).strip():
            raise AgentOutputError(f"The planner returned part {number} with an empty {name}.")
    if len([step for step in part.arc if step.strip()]) < MIN_ARC_STEPS:
        raise AgentOutputError(
            f"The planner returned part {number} with an arc of fewer than {MIN_ARC_STEPS} steps."
        )


def _coverage(indexes: Sequence[int], docs: Sequence[SourceDoc]) -> tuple[SourceRef, ...]:
    """Map cited numbers to sources; unknown numbers are dropped, repeats kept once."""
    unknown = sorted({i for i in indexes if not 1 <= i <= len(docs)})
    if unknown:
        logger.warning("Planner cited unknown source numbers, ignored: %s", unknown)
    valid = dict.fromkeys(i for i in indexes if 1 <= i <= len(docs))
    return tuple(_source_ref(docs[i - 1]) for i in valid)


def _source_ref(doc: SourceDoc) -> SourceRef:
    """Title as ingested, or the URL when the page had no usable title."""
    return SourceRef(title=doc.title.strip() or doc.url, url=doc.url)


def _to_part(planned: PlannedPart, number: int, docs: Sequence[SourceDoc]) -> SeriesPart:
    _check_part(planned, number)
    sources = _coverage(planned.source_indexes, docs)
    access = "free" if number == 1 else planned.access
    if access != planned.access:
        logger.info("Part 1 marked free (the planner proposed %s)", planned.access)
    return SeriesPart(
        number=number,
        title=planned.title.strip(),
        question=planned.question.strip(),
        brief=planned.brief.strip(),
        arc=tuple(step.strip() for step in planned.arc if step.strip()),
        access=access,
        status="planned",
        sources=sources,
        thin=planned.thin or len(sources) < MIN_PART_SOURCES,
        needs=planned.needs.strip(),
    )


def run_planner(planner: Runnable[Any, Any], topic: str, docs: Sequence[SourceDoc]) -> Series:
    """Run the planner once and turn its outline into a ``proposed`` series."""
    logger.info("Planner outlining %r from %d sources", topic, len(docs))
    task = planner_task(topic, docs)
    result = planner.invoke({"messages": [{"role": "user", "content": task}]})
    output = result.get("structured_response")
    if not isinstance(output, SeriesPlan):
        raise AgentOutputError("The planner did not return a structured outline.")
    count = len(output.parts)
    if not MIN_PARTS <= count <= MAX_PARTS:
        raise AgentOutputError(
            f"The planner proposed {count} parts; a series has {MIN_PARTS} to {MAX_PARTS}."
        )
    parts = tuple(
        _to_part(planned, number, docs) for number, planned in enumerate(output.parts, start=1)
    )
    return Series(topic=topic, status="proposed", parts=parts)

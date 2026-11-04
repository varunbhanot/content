"""Series relevance filter: one cheap structured-output call per usable source.

Off-topic sources are parked, not deleted: they stay in ``<date>.sources/`` and are listed in
``<date>.parked.md``. A source whose check fails is kept (wrongly dropping a link costs more
than keeping a weak one) and reported as unchecked.
"""

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from newsletter_machine.issue_output import LINK_TEXT_SPECIALS
from newsletter_machine.model_middleware import model_retry
from newsletter_machine.prompts import Prompt, load_prompt, render
from newsletter_machine.sources import SourceDoc
from newsletter_machine.writer import format_source, usable_sources

logger = logging.getLogger(__name__)

RELEVANCE_NAME = "relevance"
RELEVANCE_SOURCE_CHARS = 4_000  # an excerpt is enough to judge the topic, and keeps calls cheap
RELEVANCE_CONCURRENCY = 4  # as the researcher: sources are independent
PARKED_TITLE = "# Parked sources"


class RelevanceVerdict(BaseModel):
    """The model's verdict on one source (the structured-output schema)."""

    on_topic: bool = Field(description="True when the source helps any part of the series.")
    reason: str = Field(description="One short line explaining the verdict.")


@dataclass(frozen=True)
class SourceNote:
    """A source and one line on why it was parked (or why its check failed)."""

    doc: SourceDoc
    reason: str


@dataclass(frozen=True)
class Relevance:
    """``kept``: on-topic, unchecked and failed sources in their original order (failed ones
    stay so the notes still list them as skipped); ``parked``: off-topic sources."""

    kept: tuple[SourceDoc, ...]
    parked: tuple[SourceNote, ...]
    unchecked: tuple[SourceNote, ...]  # kept because their check failed; reason = the error
    on_topic: int  # usable sources judged on-topic

    @property
    def all_unchecked(self) -> bool:
        """True when every usable source's check failed: the filter did not run at all."""
        return bool(self.unchecked) and not self.on_topic and not self.parked


def relevance_system_prompt(prompt: Prompt | None = None) -> str:
    return render(prompt or load_prompt(RELEVANCE_NAME))


def build_relevance_classifier(model: BaseChatModel, system_prompt: str) -> Runnable[Any, Any]:
    """A tool-less agent with structured output (strategy picked per model, as for the critic).

    Retries only, no prompt caching: as for the researcher, the prompt is below the cacheable
    minimum and every call's source text is unique.
    """
    return create_agent(
        model,
        tools=[],
        system_prompt=system_prompt,
        response_format=RelevanceVerdict,
        middleware=[model_retry()],
        name=RELEVANCE_NAME,
    )


def relevance_task(context: str, doc: SourceDoc, index: int) -> str:
    """The series topic and outline, then one source excerpt."""
    return f"{context}\n\n{format_source(doc, index, RELEVANCE_SOURCE_CHARS)}"


def _verdict(result: Any) -> RelevanceVerdict | str:
    """The verdict, or why there is none."""
    if isinstance(result, Exception):
        return f"{type(result).__name__}: {result}"
    output = result.get("structured_response") if isinstance(result, dict) else None
    return output if isinstance(output, RelevanceVerdict) else "the model returned no verdict"


def _judge(
    classifier: Runnable[Any, Any], usable: Sequence[SourceDoc], context: str
) -> list[RelevanceVerdict | str]:
    tasks = [
        {"messages": [{"role": "user", "content": relevance_task(context, doc, index)}]}
        for index, doc in enumerate(usable, start=1)
    ]
    results = classifier.batch(
        tasks, config={"max_concurrency": RELEVANCE_CONCURRENCY}, return_exceptions=True
    )
    return [_verdict(result) for result in results]


def classify_sources(
    classifier: Runnable[Any, Any], docs: Iterable[SourceDoc], context: str
) -> Relevance:
    """Judge every usable source against ``context``; never raises for a failed check."""
    docs = tuple(docs)
    usable = usable_sources(docs)
    logger.info("Checking %d sources against the series", len(usable))
    verdicts = _judge(classifier, usable, context) if usable else []
    parked: list[SourceNote] = []
    unchecked: list[SourceNote] = []
    for doc, verdict in zip(usable, verdicts, strict=True):
        if isinstance(verdict, str):
            logger.warning("Relevance check on %s failed, kept: %s", doc.url, verdict)
            unchecked.append(SourceNote(doc, verdict))
        elif not verdict.on_topic:
            parked.append(SourceNote(doc, verdict.reason))
    parked_ids = {id(item.doc) for item in parked}  # by identity: equal duplicates stay apart
    return Relevance(
        kept=tuple(doc for doc in docs if id(doc) not in parked_ids),
        parked=tuple(parked),
        unchecked=tuple(unchecked),
        on_topic=len(usable) - len(parked) - len(unchecked),
    )


def one_line(text: str) -> str:
    return " ".join(text.split())


def _link_text(text: str) -> str:
    return LINK_TEXT_SPECIALS.sub(r"\\\1", text)


def source_lines(parked: Iterable[SourceNote]) -> tuple[str, ...]:
    """One Markdown bullet per source: link, then the reason on one line."""
    return tuple(
        f"- [{_link_text(one_line(item.doc.title) or item.doc.url)}]({item.doc.url}): "
        f"{one_line(item.reason)}"
        for item in parked
    )


def render_parked(parked: Sequence[SourceNote], label: str, sources_dir: Path) -> str:
    """``<date>.parked.md``: what was set aside this run, and where its text still is."""
    lines = source_lines(parked) or ("Nothing parked: every usable source is on the series topic.",)
    intro = (
        f"{label}. These sources were judged off the series topic and not used. Their text "
        f"stays in {sources_dir}, for a later part or a plain issue."
    )
    return f"{PARKED_TITLE}\n\n{intro}\n\n" + "\n".join(lines) + "\n"

"""What a drafted series part carries forward: its closing teaser and a one-line summary.

The teaser is the draft's italic "Next in this series: ..." line, found by a regex. The
summary is one cheap model call on the final draft; the next part's recap is built from it.
"""

import logging
import re
from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable

from newsletter_machine.agent import AgentOutputError, extract_text
from newsletter_machine.checks import body_without_sources
from newsletter_machine.model_middleware import model_retry
from newsletter_machine.prompts import Prompt, load_prompt, render
from newsletter_machine.relevance import one_line
from newsletter_machine.writer import neutralise_tags

logger = logging.getLogger(__name__)

SUMMARY_NAME = "summary"
SUMMARY_DRAFT_CHARS = 12_000  # a ~1,000-word part fits; the cap bounds a runaway draft
MAX_SUMMARY_CHARS = 300  # one sentence; the series file and the next angle stay short
# an emphasised line (italic or bold, whole or in part, maybe quoted) opening with the phrase;
# the marker touches the word, so a "* " bullet is not emphasis. series_checks.yaml's
# series-final-no-teaser pattern is the same regex (a test keeps them in step).
TEASER_LINE = re.compile(
    r"^[ \t]*(?:>[ \t]*)?[*_]+Next in this series\b.*$", re.IGNORECASE | re.MULTILINE
)
EMPHASIS = re.compile(r"(?<!\w)[*_]+|[*_]+(?!\w)")  # markers at word edges, not a*b or a_b


def extract_teaser(draft: str) -> str:
    """The last emphasised "Next in this series ..." line without its Markdown, or ""."""
    matches = list(TEASER_LINE.finditer(draft))
    if not matches:
        return ""
    line = matches[-1].group(0).strip().removeprefix(">").strip()
    return " ".join(EMPHASIS.sub("", line).split())


def summary_system_prompt(prompt: Prompt | None = None) -> str:
    return render(prompt or load_prompt(SUMMARY_NAME))


def build_summariser(model: BaseChatModel, system_prompt: str) -> Runnable[Any, Any]:
    """A tool-less agent, retries only (one short call per run: nothing worth caching)."""
    return create_agent(
        model,
        tools=[],
        system_prompt=system_prompt,
        middleware=[model_retry()],
        name=SUMMARY_NAME,
    )


def summary_task(draft: str) -> str:
    body = body_without_sources(draft).strip()[:SUMMARY_DRAFT_CHARS]
    return f"<draft>\n{neutralise_tags(body)}\n</draft>"


def _capped(text: str) -> str:
    if len(text) <= MAX_SUMMARY_CHARS:
        return text
    cut = text[:MAX_SUMMARY_CHARS]
    head = cut.rsplit(" ", 1)[0] if " " in cut else cut[: MAX_SUMMARY_CHARS - 1]
    return head.rstrip(" ,;:") + "…"


def summarise_part(summariser: Runnable[Any, Any], draft: str) -> str:
    """One line stating the part's core claim; ``AgentOutputError`` when the model gives none."""
    logger.info("Summarising a %d-character part", len(draft))
    task = {"messages": [{"role": "user", "content": summary_task(draft)}]}
    result = summariser.invoke(task)
    summary = one_line(extract_text(result["messages"][-1].content))
    if not summary:
        raise AgentOutputError("The summariser returned an empty summary.")
    return _capped(summary)

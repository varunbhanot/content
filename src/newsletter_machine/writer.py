"""Writer sub-agent: drafts an issue in Varun's voice from the week's sources."""

import html
import logging
import re
from collections.abc import Iterable

from deepagents import CompiledSubAgent
from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel

from newsletter_machine.agent import AgentOutputError, extract_text
from newsletter_machine.grounding import Grounding, format_checklist, format_samples
from newsletter_machine.model_middleware import subagent_middleware
from newsletter_machine.prompts import Prompt, load_prompt, render
from newsletter_machine.sources import SourceDoc

logger = logging.getLogger(__name__)

WRITER_NAME = "writer"
WRITER_DESCRIPTION = (
    "Writes a Beyond the AI Demo draft in Varun's voice. Give it the week's sources "
    "(inside <source> tags) and Varun's angle; it returns the Markdown draft with a Sources list."
)
MAX_SOURCE_CHARS = 24_000  # ~6k tokens per source keeps a week's run within the cost budget
WRAPPER_TAG = re.compile(
    r"<(\s*/?\s*(?:source|draft|brief|research_notes|critique|series_context)\b)", re.IGNORECASE
)
WRAPPING_FENCE = re.compile(r"(?:^|\n)(```|~~~)[\w-]*[ \t]*\n(.*)\n\1\s*\Z", re.DOTALL)
TITLE_LINE = re.compile(r"^# ", re.MULTILINE)


def writer_system_prompt(grounding: Grounding, prompt: Prompt | None = None) -> str:
    return render(
        prompt or load_prompt(WRITER_NAME),
        style_guide=grounding.style_guide,
        checklist=format_checklist(grounding.checklist.items),
        samples=format_samples(grounding.samples),
    )


def usable_sources(docs: Iterable[SourceDoc]) -> tuple[SourceDoc, ...]:
    """Failed sources have no text; fallback ones (e.g. a video description) still help."""
    return tuple(doc for doc in docs if doc.status != "failed")


def neutralise_tags(text: str) -> str:
    """Stop untrusted text from opening or closing our ``<source>``/``<draft>`` wrappers."""
    return WRAPPER_TAG.sub(r"&lt;\1", text)


def _source_text(doc: SourceDoc, max_chars: int) -> str:
    text = neutralise_tags(doc.text)
    if len(text) <= max_chars:
        return text
    extra = len(text) - max_chars
    return f"{text[:max_chars]}\n[truncated: {extra} more characters]"


def _attrs(doc: SourceDoc, index: int) -> str:
    pairs = {
        "index": str(index),
        "title": doc.title,
        "url": doc.url,
        "kind": doc.kind,
        "status": doc.status,
        "note": doc.note,
    }
    return " ".join(f'{key}="{html.escape(value)}"' for key, value in pairs.items() if value)


def format_source(doc: SourceDoc, index: int, max_chars: int = MAX_SOURCE_CHARS) -> str:
    """One source wrapped in a ``<source>`` tag, cut at ``max_chars``; its text is untrusted."""
    return f"<source {_attrs(doc, index)}>\n{_source_text(doc, max_chars)}\n</source>"


def format_sources(docs: Iterable[SourceDoc]) -> str:
    """Usable sources wrapped in ``<source>`` tags; their text is untrusted data."""
    return "\n\n".join(
        format_source(doc, index) for index, doc in enumerate(usable_sources(docs), start=1)
    )


def angle_line(angle: str | None) -> str:
    if angle and angle.strip():
        return f"Varun's angle: {angle.strip()}"
    return "No angle given: pick the single strongest topic the sources support."


def writer_task(docs: Iterable[SourceDoc], angle: str | None) -> str:
    """The user message for the writer: the angle (if any) plus the usable sources."""
    docs = tuple(docs)
    if not usable_sources(docs):
        raise ValueError("No usable sources: every source failed to ingest.")
    return f"{angle_line(angle)}\n\nThis week's sources:\n\n{format_sources(docs)}"


def build_writer(model: BaseChatModel, system_prompt: str) -> CompiledSubAgent:
    """A tool-less agent, usable directly or as a deep agent's ``task`` sub-agent (Phase 4)."""
    runnable = create_agent(
        model,
        tools=[],
        system_prompt=system_prompt,
        middleware=subagent_middleware(model),
        name=WRITER_NAME,
    )
    return CompiledSubAgent(name=WRITER_NAME, description=WRITER_DESCRIPTION, runnable=runnable)


def _unwrap_fence(text: str) -> str:
    """Drop a fence wrapping the whole draft, even after a preamble line."""
    match = WRAPPING_FENCE.search(text)
    if match is None or not match.group(2).lstrip().startswith("# "):
        return text
    title_before_fence = TITLE_LINE.search(text[: match.start()])
    return text if title_before_fence else match.group(2)


def clean_draft(text: str) -> str:
    """The draft from its ``# `` title on: no wrapping code fence, no chatty preamble."""
    text = _unwrap_fence(text.strip())
    title = TITLE_LINE.search(text)
    return (text[title.start() :] if title else text).strip()


def run_writer(writer: CompiledSubAgent, task: str) -> str:
    """Run the writer once and return the Markdown draft."""
    logger.info("Writer drafting from a %d-character task", len(task))
    result = writer["runnable"].invoke({"messages": [{"role": "user", "content": task}]})
    draft = clean_draft(extract_text(result["messages"][-1].content))
    if not draft:
        raise AgentOutputError("The writer returned an empty draft.")
    return draft

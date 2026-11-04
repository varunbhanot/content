"""Voice-critic sub-agent: checks a draft against the checklist, returns structured feedback."""

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from deepagents import CompiledSubAgent
from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

from newsletter_machine.agent import AgentOutputError
from newsletter_machine.checklist import Checklist, ChecklistItem
from newsletter_machine.checks import CheckResult, run_mechanical
from newsletter_machine.grounding import Grounding, format_checklist
from newsletter_machine.model_middleware import subagent_middleware
from newsletter_machine.prompts import Prompt, load_prompt, render
from newsletter_machine.sources import SourceDoc
from newsletter_machine.writer import format_sources, neutralise_tags

logger = logging.getLogger(__name__)

CRITIC_NAME = "voice-critic"
CRITIC_PROMPT = "critic"
CRITIC_DESCRIPTION = (
    "Checks a draft against Varun's voice checklist (derived from his style guide). Give it "
    "the draft inside <draft> tags and the sources; it returns pass/fail per item with quotes "
    "and fixes."
)


class ItemVerdict(BaseModel):
    """The model's verdict on one checklist item (the structured-output schema)."""

    item_id: str = Field(description="The checklist item's exact id.")
    passed: bool = Field(description="True only if the draft clearly meets the rule.")
    quotes: list[str] = Field(default_factory=list, description="Offending passages, verbatim.")
    fix: str = Field(default="", description="Concrete rewrite or instruction for a fail.")


class CriticOutput(BaseModel):
    verdicts: list[ItemVerdict] = Field(description="One verdict per checklist item.")
    summary: str = Field(description="Two or three sentences: does it sound like Varun?")


@dataclass(frozen=True)
class Critique:
    results: tuple[CheckResult, ...]
    summary: str

    def _count(self, status: str) -> int:
        return sum(1 for result in self.results if result.status == status)

    @property
    def passed(self) -> int:
        return self._count("pass")

    @property
    def failed(self) -> int:
        return self._count("fail")

    @property
    def not_checked(self) -> int:
        return self._count("not-checked")


def judgement_items(checklist: Checklist) -> tuple[ChecklistItem, ...]:
    """Items the model judges; mechanical ones are checked exactly in code."""
    return tuple(item for item in checklist.items if not item.is_mechanical)


def critic_system_prompt(grounding: Grounding, prompt: Prompt | None = None) -> str:
    return render(
        prompt or load_prompt(CRITIC_PROMPT),
        style_guide=grounding.style_guide,
        checklist=format_checklist(judgement_items(grounding.checklist)),
    )


def critic_task(draft: str, docs: Iterable[SourceDoc]) -> str:
    """The user message for the critic: the draft, then the sources to fact-check against."""
    return (
        f"<draft>\n{neutralise_tags(draft)}\n</draft>\n\nSources the draft was written from:\n\n"
        + (format_sources(docs))
    )


def build_critic(model: BaseChatModel, system_prompt: str) -> CompiledSubAgent:
    """A tool-less agent with structured output; a deep agent's ``task`` returns it as JSON.

    Passing the bare schema lets LangChain pick the strategy per model: native structured
    output where the model supports it (newer Claude models reject the forced ``tool_choice``
    a tool strategy needs), a structured-output tool otherwise.
    """
    runnable = create_agent(
        model,
        tools=[],
        system_prompt=system_prompt,
        response_format=CriticOutput,
        middleware=subagent_middleware(model),
        name=CRITIC_NAME,
    )
    return CompiledSubAgent(name=CRITIC_NAME, description=CRITIC_DESCRIPTION, runnable=runnable)


def _from_verdict(item: ChecklistItem, verdict: ItemVerdict | None) -> CheckResult:
    if verdict is None:
        return CheckResult(item=item, status="not-checked", checked_by="critic")
    if verdict.passed:
        return CheckResult(item=item, status="pass", checked_by="critic")
    return CheckResult(
        item=item,
        status="fail",
        quotes=tuple(q.strip() for q in verdict.quotes if q.strip()),
        fix=verdict.fix.strip(),
        checked_by="critic",
    )


def _index_verdicts(
    checklist: Checklist, verdicts: Sequence[ItemVerdict]
) -> dict[str, ItemVerdict]:
    known = {item.id for item in judgement_items(checklist)}
    unknown = sorted({v.item_id for v in verdicts} - {item.id for item in checklist.items})
    if unknown:
        logger.warning("Critic returned verdicts for unknown items, ignored: %s", unknown)
    indexed: dict[str, ItemVerdict] = {}
    for verdict in verdicts:
        if verdict.item_id in known:
            indexed.setdefault(verdict.item_id, verdict)
    return indexed


def merge_results(checklist: Checklist, draft: str, output: CriticOutput) -> Critique:
    """Code results for mechanical items, model verdicts for the rest, in checklist order."""
    verdicts = _index_verdicts(checklist, output.verdicts)
    results = tuple(
        run_mechanical(item, draft)
        if item.is_mechanical
        else _from_verdict(item, verdicts.get(item.id))
        for item in checklist.items
    )
    return Critique(results=results, summary=output.summary.strip())


def run_critic(critic: CompiledSubAgent, task: str, checklist: Checklist, draft: str) -> Critique:
    """Run the critic once on ``draft`` and merge in the exact code checks."""
    logger.info("Critic checking a %d-character draft", len(draft))
    result = critic["runnable"].invoke({"messages": [{"role": "user", "content": task}]})
    output = result.get("structured_response")
    if not isinstance(output, CriticOutput):
        raise AgentOutputError("The critic did not return structured feedback.")
    return merge_results(checklist, draft, output)

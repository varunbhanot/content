"""The editor's ``task`` sub-agents: researcher, writer and critic wrapped around the workspace.

Each wrapper is a ``CompiledSubAgent`` whose runnable takes the lead's state, reads trusted
inputs (sources, angle, checklist) from Python and earlier steps from ``state["files"]``, runs
one model step and returns new versioned files. Caps live here, in code: one research pass,
``1 + max_revisions`` writer runs, one critique per draft version.

The caps read the state snapshot, so the wrappers must see each other's results: a run-wide
``_Ledger`` runs one sub-agent at a time and refuses a call whose snapshot is missing files
an earlier call returned (the lead sent several ``task`` calls in one turn).
"""

import json
import logging
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from deepagents import CompiledSubAgent
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable, RunnableLambda

from newsletter_machine.agent import extract_text
from newsletter_machine.checklist import Checklist
from newsletter_machine.checks import prose_words
from newsletter_machine.critic import CRITIC_NAME, Critique, critic_task, run_critic
from newsletter_machine.critique_report import ReportMeta, render_critique
from newsletter_machine.issue_output import normalise_sources
from newsletter_machine.researcher import RESEARCHER_NAME, research_notes
from newsletter_machine.sources import SourceDoc
from newsletter_machine.workspace import (
    BRIEFS_DIR,
    CRITIQUES_DIR,
    DRAFTS_DIR,
    ERRORS_DIR,
    RESEARCH_NOTES,
    Files,
    count_files,
    file_text,
    latest_version,
    text_file,
    versioned,
)
from newsletter_machine.writer import WRITER_NAME, neutralise_tags, run_writer, writer_task

logger = logging.getLogger(__name__)

GENERAL_PURPOSE = "general-purpose"  # deepagents adds one unless we supply our own
RESEARCHER_DESCRIPTION = (
    "Reads every usable source and saves short, numbered, sourced notes to "
    f"{RESEARCH_NOTES}. Run it once, first. The description is ignored."
)
WRITER_DESCRIPTION = (
    "Writes the next draft version in Varun's voice to /drafts/vN.md from all sources and the "
    "research notes. Your description is the editorial brief: topic, argument, which sources "
    "carry it, structure. After a critique, it revises the latest draft against that critique."
)
CRITIC_DESCRIPTION = (
    "Checks the latest draft against Varun's voice checklist and saves /critiques/vN.md. "
    "Returns pass/fail counts and the failed items with fixes. The description is ignored."
)
GENERAL_PURPOSE_DESCRIPTION = "Not available in this pipeline."
META_EXT = "json"  # per-draft facts for the notes, e.g. links dropped from Sources
MAX_RESEARCH_ATTEMPTS = 2  # one retry for a transient failure

STALE_REPLY = (
    "Refused: another step's result is not in your files yet. Call one sub-agent at a time "
    "and wait for its result before the next."
)


StateFn = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class EditorInputs:
    """Trusted inputs the sub-agents read from code, never from the lead's messages."""

    docs: tuple[SourceDoc, ...]
    angle: str | None
    checklist: Checklist
    max_revisions: int
    draft_name: str
    writer_version: int
    critic_version: int
    series_label: str = ""  # names the series part in critique reports; blank otherwise


@dataclass(frozen=True)
class CritiqueResult:
    critique: Critique
    markdown: str
    summary: Mapping[str, Any]


def _reply(text: str, files: Mapping[str, Any] | None = None) -> dict[str, Any]:
    update: dict[str, Any] = {"messages": [AIMessage(content=text)]}
    return {**update, "files": dict(files)} if files else update


def _files(state: Mapping[str, Any]) -> Files:
    files = state.get("files")
    return files if isinstance(files, Mapping) else {}


def _brief(state: Mapping[str, Any]) -> str:
    messages = state.get("messages") or []
    if not messages:
        return ""
    last = messages[-1]
    content = last.get("content", "") if isinstance(last, Mapping) else last.content
    return extract_text(content).strip()


def _failure(agent: str, path: str, exc: Exception) -> dict[str, Any]:
    logger.warning("%s failed", agent, exc_info=True)
    reason = f"{type(exc).__name__}: {exc}"
    return _reply(f"{agent} failed: {reason}", {path: text_file(reason)})


class _Ledger:
    """Paths the wrappers have returned this run, guarded by one lock (one step at a time)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._written: set[str] = set()

    def run(self, fn: StateFn, state: dict[str, Any]) -> dict[str, Any]:
        if not self._lock.acquire(blocking=False):  # a parallel call is still running
            return _reply(STALE_REPLY)
        try:
            if not self._written <= set(_files(state)):  # ran after a parallel call finished
                return _reply(STALE_REPLY)
            result = fn(state)
            self._written |= set(result.get("files", {}))
            return result
        finally:
            self._lock.release()


def _subagent(name: str, description: str, fn: StateFn, ledger: _Ledger) -> CompiledSubAgent:
    runnable: RunnableLambda[dict[str, Any], dict[str, Any]] = RunnableLambda(
        lambda state: ledger.run(fn, state)
    )
    return CompiledSubAgent(name=name, description=description, runnable=runnable)


def dropped_links(files: Files, version: int) -> tuple[str, ...]:
    """Links the writer cited for ``version`` that were not ingested sources."""
    try:
        meta = json.loads(file_text(files, versioned(DRAFTS_DIR, version, META_EXT)) or "{}")
        return tuple(str(url) for url in meta.get("dropped", ()))
    except (ValueError, AttributeError, TypeError):
        return ()


def writer_attempts(files: Files) -> int:
    """Drafts written plus writer runs that failed: both count against the cap."""
    return latest_version(files, DRAFTS_DIR, "md") + count_files(files, ERRORS_DIR, "writer-")


def critique_version(
    inputs: EditorInputs, critic: CompiledSubAgent, draft: str, version: int
) -> CritiqueResult:
    """Critique one draft version: rendered report plus a small JSON-able summary."""
    critique = run_critic(critic, critic_task(draft, inputs.docs), inputs.checklist, draft)
    meta = ReportMeta(
        draft_name=f"{inputs.draft_name} (draft v{version})",
        words=prose_words(draft),
        writer_version=inputs.writer_version,
        critic_version=inputs.critic_version,
        checklist_version=inputs.checklist.version,
        series=inputs.series_label,
    )
    summary = {
        "version": version,
        "passed": critique.passed,
        "failed": critique.failed,
        "not_checked": critique.not_checked,
        "failed_items": [r.item.id for r in critique.results if r.status == "fail"],
    }
    return CritiqueResult(critique, render_critique(critique, meta), summary)


def _research(inputs: EditorInputs, researcher: Runnable[Any, Any]) -> StateFn:
    def run(state: dict[str, Any]) -> dict[str, Any]:
        files = _files(state)
        if RESEARCH_NOTES in files:
            return _reply(f"Research is already done: read {RESEARCH_NOTES}.")
        failures = count_files(files, ERRORS_DIR, "researcher-")
        if failures >= MAX_RESEARCH_ATTEMPTS:
            return _reply("Research failed twice: go on without research notes.")
        try:
            notes = research_notes(researcher, inputs.docs, inputs.angle)
        except Exception as exc:  # network/API failures surface as many types
            return _failure(RESEARCHER_NAME, f"{ERRORS_DIR}/researcher-{failures + 1}.md", exc)
        gaps = f" {len(notes.failures)} source(s) without notes." if notes.failures else ""
        return _reply(
            f"Research notes saved to {RESEARCH_NOTES}.{gaps}",
            {RESEARCH_NOTES: text_file(notes.text)},
        )

    return run


def _tagged(tag: str, text: str) -> str:
    return f"<{tag}>\n{neutralise_tags(text)}\n</{tag}>"


def revision_task(inputs: EditorInputs, files: Files, brief: str) -> str:
    """The writer's user message: Phase 3 task, the lead's brief, notes, and any revision ask."""
    parts = [writer_task(inputs.docs, inputs.angle)]
    if brief:
        parts.append(f"The editor's brief for this issue:\n{_tagged('brief', brief)}")
    notes = file_text(files, RESEARCH_NOTES)
    if notes:
        parts.append(
            "Research notes on the sources above ([n] is the source index):\n"
            + _tagged("research_notes", notes)
        )
    version = latest_version(files, DRAFTS_DIR, "md")
    previous = file_text(files, versioned(DRAFTS_DIR, version, "md")) if version else None
    if previous:
        parts.append(
            _revision_ask(previous, file_text(files, versioned(CRITIQUES_DIR, version, "md")))
        )
    return "\n\n".join(parts)


def _revision_ask(previous: str, critique: str | None) -> str:
    if critique is None:  # the critic failed on it: revise against the brief alone
        return (
            "Revise your previous draft below following the editor's brief, and return the "
            f"full revised draft.\n{_tagged('draft', previous)}"
        )
    return (
        "Revise your previous draft below. Fix every failed critique item, keep what "
        "passed, and return the full revised draft.\n"
        f"{_tagged('draft', previous)}\n{_tagged('critique', critique)}"
    )


def _write(inputs: EditorInputs, writer: CompiledSubAgent) -> StateFn:
    def run(state: dict[str, Any]) -> dict[str, Any]:
        files, brief = _files(state), _brief(state)
        attempts = writer_attempts(files)
        if attempts >= 1 + inputs.max_revisions:
            return _reply(f"Writer limit reached ({attempts} runs). Do not ask again; finish.")
        try:
            draft = run_writer(writer, revision_task(inputs, files, brief))
        except Exception as exc:  # network/API failures surface as many types
            return _failure(WRITER_NAME, f"{ERRORS_DIR}/writer-{attempts + 1}.md", exc)
        return _save_draft(inputs, files, draft, brief)

    return run


def _save_draft(inputs: EditorInputs, files: Files, raw: str, brief: str) -> dict[str, Any]:
    """Save the draft with its Sources list rebuilt (what the critic and Varun see) and raw."""
    version = latest_version(files, DRAFTS_DIR, "md") + 1
    fixed = normalise_sources(raw, inputs.docs)
    saved = {
        versioned(DRAFTS_DIR, version, "md"): text_file(fixed.draft),
        versioned(DRAFTS_DIR, version, META_EXT): text_file(json.dumps({"dropped": fixed.dropped})),
        versioned(BRIEFS_DIR, version, "md"): text_file(brief),
    }
    dropped = f" Dropped non-source links: {', '.join(fixed.dropped)}." if fixed.dropped else ""
    words = prose_words(fixed.draft)
    return _reply(
        f"Draft v{version} saved to /drafts/v{version}.md ({words} words).{dropped}", saved
    )


def _critic_reply(inputs: EditorInputs, files: Files, result: CritiqueResult) -> str:
    summary = result.summary
    left = max(0, 1 + inputs.max_revisions - writer_attempts(files))
    lines = [
        f"Draft v{summary['version']}: {summary['passed']} passed, {summary['failed']} failed, "
        f"{summary['not_checked']} not checked. {left} revision(s) left.",
        *(
            f"- `{r.item.id}` ({r.item.severity}): {r.fix or r.item.rule}"
            for r in result.critique.results
            if r.status == "fail"
        ),
    ]
    return "\n".join(lines)


def _critique(inputs: EditorInputs, critic: CompiledSubAgent) -> StateFn:
    def run(state: dict[str, Any]) -> dict[str, Any]:
        files = _files(state)
        version = latest_version(files, DRAFTS_DIR, "md")
        draft = file_text(files, versioned(DRAFTS_DIR, version, "md")) if version else None
        if not draft:
            return _reply("No draft to critique yet: ask the writer first.")
        error = f"{ERRORS_DIR}/critic-v{version}.md"
        if versioned(CRITIQUES_DIR, version, "md") in files or error in files:
            return _reply(f"Draft v{version} is already critiqued (or the critic failed on it).")
        try:
            result = critique_version(inputs, critic, draft, version)
        except Exception as exc:  # network/API failures surface as many types
            return _failure(CRITIC_NAME, error, exc)
        saved = {
            versioned(CRITIQUES_DIR, version, "md"): text_file(result.markdown),
            versioned(CRITIQUES_DIR, version, "json"): text_file(json.dumps(result.summary)),
        }
        return _reply(_critic_reply(inputs, files, result), saved)

    return run


def _refuse(state: dict[str, Any]) -> dict[str, Any]:
    return _reply("general-purpose is not available here: use researcher, writer, voice-critic.")


def build_editor_subagents(
    inputs: EditorInputs,
    *,
    researcher: Runnable[Any, Any],
    writer: CompiledSubAgent,
    critic: CompiledSubAgent,
) -> tuple[CompiledSubAgent, ...]:
    """The lead's sub-agents, plus a refusing ``general-purpose`` so none is auto-added."""
    ledger = _Ledger()
    return (
        _subagent(RESEARCHER_NAME, RESEARCHER_DESCRIPTION, _research(inputs, researcher), ledger),
        _subagent(WRITER_NAME, WRITER_DESCRIPTION, _write(inputs, writer), ledger),
        _subagent(CRITIC_NAME, CRITIC_DESCRIPTION, _critique(inputs, critic), ledger),
        _subagent(GENERAL_PURPOSE, GENERAL_PURPOSE_DESCRIPTION, _refuse, ledger),
    )

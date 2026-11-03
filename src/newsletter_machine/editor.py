"""Lead "editor" deep agent: plans the issue and delegates to researcher, writer and critic."""

import logging
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from deepagents import CompiledSubAgent, FilesystemPermission, create_deep_agent
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph

from newsletter_machine.agent import extract_text
from newsletter_machine.prompts import Prompt, load_prompt, render
from newsletter_machine.sources import SourceDoc
from newsletter_machine.workspace import DRAFTS_DIR, PROTECTED_DIRS, latest_version
from newsletter_machine.writer import angle_line, neutralise_tags, usable_sources

logger = logging.getLogger(__name__)

EDITOR_NAME = "editor"
EDITOR_RECURSION_LIMIT = 120  # ~55 model turns: room for 3 revisions plus reads and todos
EDITOR_THREAD = "issue"  # one in-memory thread per editor; lets a failed run be salvaged
EDITOR_PERMISSIONS = [
    FilesystemPermission(
        operations=["write"], paths=[f"{d}/**" for d in PROTECTED_DIRS], mode="deny"
    )
]


@dataclass(frozen=True)
class EditorRun:
    """The lead's final virtual filesystem and its closing message to Varun.

    ``error`` is set when the lead stopped early (model failure, recursion limit) after a
    draft was saved; ``files`` then holds what was saved so far.
    """

    files: Mapping[str, Any]
    summary: str
    error: str = ""


class SerialToolCalls(AgentMiddleware[Any, Any, Any]):
    """Ask the model for at most one tool call per turn: each step reads the last one's files."""

    def _serial(self, request: ModelRequest[Any]) -> ModelRequest[Any]:
        return request.override(
            model_settings={**request.model_settings, "parallel_tool_calls": False}
        )

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any]:
        return handler(self._serial(request))

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        return await handler(self._serial(request))


def editor_middleware(model: BaseChatModel) -> list[AgentMiddleware[Any, Any, Any]]:
    """Serial tool calls where the provider supports the switch (Anthropic); the sub-agent
    ledger still refuses stale parallel calls from any other model."""
    return [SerialToolCalls()] if isinstance(model, ChatAnthropic) else []


def editor_system_prompt(max_revisions: int, prompt: Prompt | None = None) -> str:
    return render(
        prompt or load_prompt(EDITOR_NAME),
        writer_runs=str(1 + max_revisions),
        max_revisions=str(max_revisions),
    )


def build_editor(
    model: BaseChatModel, subagents: Sequence[CompiledSubAgent], system_prompt: str
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """A deep agent on the in-state filesystem; it may write only outside the protected dirs."""
    return create_deep_agent(
        model=model,
        system_prompt=system_prompt,
        subagents=list(subagents),
        middleware=editor_middleware(model),
        permissions=EDITOR_PERMISSIONS,
        checkpointer=InMemorySaver(),
        name=EDITOR_NAME,
    )


def _source_line(doc: SourceDoc, label: str) -> str:
    note = f"; note: {doc.note}" if doc.note else ""
    if doc.status == "failed":
        state = f"skipped, failed to ingest: {doc.detail or 'unknown error'}"
    else:
        state = doc.kind if doc.status == "ok" else f"{doc.kind}, fallback text"
    return neutralise_tags(f"- {label}{doc.title} ({state}) {doc.url}{note}")


def editor_task(docs: Iterable[SourceDoc], angle: str | None) -> str:
    """The lead's user message: the angle and a source list (the text is in ``/sources``).

    Usable sources are numbered as the writer and researcher number them; failed ones
    follow, unnumbered.
    """
    docs = tuple(docs)
    lines = [_source_line(doc, f"[{i}] ") for i, doc in enumerate(usable_sources(docs), start=1)]
    lines += [_source_line(doc, "") for doc in docs if doc.status == "failed"]
    return (
        f"{angle_line(angle)}\n\nThis week's sources (full text in /sources/):\n"
        + "\n".join(lines)
        + "\n\nRun the issue."
    )


def _saved_files(editor: CompiledStateGraph[Any, Any, Any, Any], config: Any) -> dict[str, Any]:
    """Files checkpointed so far; empty if the state cannot be read (keeps the real error)."""
    try:
        return dict(editor.get_state(config).values.get("files") or {})
    except Exception:  # never mask the run's own failure
        logger.warning("Could not read the editor's saved state", exc_info=True)
        return {}


def run_editor(
    editor: CompiledStateGraph[Any, Any, Any, Any], task: str, files: Mapping[str, Any]
) -> EditorRun:
    """Run the lead once over a seeded filesystem; returns the final files and message.

    If the lead fails after the writer saved a draft, the saved files are returned with
    ``error`` set instead of being lost; a failure before any draft exists is re-raised.
    """
    logger.info("Editor planning the issue over %d seeded files", len(files))
    config: Any = {
        "recursion_limit": EDITOR_RECURSION_LIMIT,
        "configurable": {"thread_id": EDITOR_THREAD},
    }
    try:
        result = editor.invoke(
            {"messages": [{"role": "user", "content": task}], "files": dict(files)}, config
        )
    except Exception as exc:  # model/API failures and the recursion limit surface as many types
        saved = _saved_files(editor, config)
        if not latest_version(saved, DRAFTS_DIR, "md"):  # no draft to salvage
            raise
        logger.warning("Editor stopped early; keeping %d saved files", len(saved), exc_info=True)
        return EditorRun(files=saved, summary="", error=f"{type(exc).__name__}: {exc}")
    summary = extract_text(result["messages"][-1].content).strip()
    return EditorRun(files=dict(result.get("files") or {}), summary=summary)

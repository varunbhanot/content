"""Fake chat models and canned replies shared by the editor tests (offline)."""

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import anthropic
import httpx2
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from newsletter_machine.critic import judgement_items
from newsletter_machine.grounding import load_grounding

ROOT = Path(__file__).resolve().parent.parent
VOICE = ROOT / "voice"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "sources"
DRAFT = (
    "# Evals are the moat\n\nThe demo worked. Production did not.\n\n"
    "## Sources\n\n- [Why](https://example.com/why-agent-demos-fail)\n"
)
DRAFT_V2 = DRAFT.replace("Production did not.", "Production did not. Real tickets broke it.")


class FakeModel(GenericFakeChatModel):
    """A scripted chat model; tools are accepted and ignored."""

    def bind_tools(self, tools: Any, **kwargs: Any) -> "FakeModel":
        return self


def fake(*replies: AIMessage | str) -> FakeModel:
    messages = [r if isinstance(r, AIMessage) else AIMessage(content=r) for r in replies]
    return FakeModel(messages=iter(messages))


def critic_reply(failed: Sequence[str] = (), summary: str = "Sounds like Varun.") -> AIMessage:
    """A structured critic answer: every judgement item passes except ``failed``."""
    items = judgement_items(load_grounding(VOICE).checklist)
    verdicts = [
        {"item_id": item.id, "passed": item.id not in failed, "quotes": [], "fix": "Fix it."}
        for item in items
    ]
    args = {"verdicts": verdicts, "summary": summary}
    return AIMessage(content="", tool_calls=[{"name": "CriticOutput", "args": args, "id": "c"}])


def task_call(subagent: str, description: str, call_id: str) -> AIMessage:
    """A lead-agent turn that delegates to ``subagent``."""
    args = {"description": description, "subagent_type": subagent}
    return AIMessage(content="", tool_calls=[{"name": "task", "args": args, "id": call_id}])


class FlakyModel(FakeModel):
    """A scripted model that raises each of ``failures`` in turn before replying."""

    failures: list[Exception] = []
    calls: int = 0

    def _generate(self, *args: Any, **kwargs: Any) -> Any:
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return super()._generate(*args, **kwargs)


def flaky(failures: Sequence[Exception], *replies: AIMessage | str) -> FlakyModel:
    messages = [r if isinstance(r, AIMessage) else AIMessage(content=r) for r in replies]
    return FlakyModel(messages=iter(messages), failures=list(failures))


API_REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def status_error(
    cls: type[anthropic.APIStatusError], status: int, headers: dict[str, str] | None = None
) -> anthropic.APIStatusError:
    """An Anthropic SDK HTTP error, as the client raises it once its own retries give up."""
    response = httpx2.Response(status, headers=headers, request=API_REQUEST)
    return cls("boom", response=response, body=None)


def connection_error() -> anthropic.APIConnectionError:
    return anthropic.APIConnectionError(request=API_REQUEST)


class RelevanceFake(FakeModel):
    """A content-aware relevance classifier: batches run concurrently, so replies cannot be
    scripted in order. A task naming an ``off`` word is off-topic; a ``fail`` word raises; a
    ``parts`` word names the outline part the source best supports (else ``default_part``, or
    the part the outline marks "(this part)", so a plain run fits the part it drafts)."""

    off: tuple[str, ...] = ()
    fail: tuple[str, ...] = ()
    parts: dict[str, int] = {}
    default_part: int | None = None
    calls: int = 0

    def _generate(self, messages: Any, *args: Any, **kwargs: Any) -> ChatResult:
        self.calls += 1
        task = str(messages[-1].content)
        if any(word in task for word in self.fail):
            raise ConnectionResetError("classifier down")
        off = next((word for word in self.off if word in task), None)
        args_: dict[str, Any] = {
            "on_topic": off is None,
            "reason": f"about {off}" if off else "on the topic",
        }
        current = re.search(r"Part (\d+): [^\n]*\(this part\)", task)
        fallback = int(current.group(1)) if current else None
        default = self.default_part if self.default_part is not None else fallback
        part = next((n for word, n in self.parts.items() if word in task), default)
        if part is not None:
            args_["best_part"] = part
        call = {"name": "RelevanceVerdict", "args": args_, "id": f"r{self.calls}"}
        return ChatResult(generations=[ChatGeneration(message=AIMessage("", tool_calls=[call]))])


def relevance_fake(
    off: Sequence[str] = (),
    fail: Sequence[str] = (),
    parts: dict[str, int] | None = None,
    default_part: int | None = None,
) -> RelevanceFake:
    return RelevanceFake(
        messages=iter(()),
        off=tuple(off),
        fail=tuple(fail),
        parts=dict(parts or {}),
        default_part=default_part,
    )

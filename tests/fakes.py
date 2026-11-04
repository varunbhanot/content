"""Fake chat models and canned replies shared by the editor tests (offline)."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import anthropic
import httpx2
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

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

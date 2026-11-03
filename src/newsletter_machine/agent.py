"""Minimal read-only deep agent over the voice corpus."""

import logging
from typing import Any

from deepagents import FilesystemPermission, create_deep_agent
from deepagents.backends.filesystem import FilesystemBackend
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph

from newsletter_machine.config import Settings

logger = logging.getLogger(__name__)

HELLO_SYSTEM_PROMPT = (
    "You are a read-only assistant for Varun's newsletter. "
    "Files under /samples/hand are his hand-written posts (his true voice); "
    "/samples/ai-assisted are AI-assisted and NOT his voice. "
    "Never write or edit files."
)

READ_ONLY_PERMISSIONS = [FilesystemPermission(operations=["write"], paths=["/**"], mode="deny")]


class AgentOutputError(RuntimeError):
    """A model run finished but its output is unusable (empty, missing structure)."""


def extract_text(content: Any) -> str:
    """Flatten Anthropic message content (str or list of blocks) to plain text."""
    if isinstance(content, str):
        return content
    return "".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    )


ANTHROPIC_PROVIDER = "anthropic"


def make_chat_model(model: str, api_key: str) -> BaseChatModel:
    """Turn a ``provider:model`` setting into a chat model.

    ``api_key`` is the Anthropic key, so it is passed to Anthropic models only; any other
    provider reads its own key from the environment and never receives this one.
    """
    if model.partition(":")[0] == ANTHROPIC_PROVIDER:
        return init_chat_model(model, api_key=api_key)
    return init_chat_model(model)


def build_hello_agent(
    settings: Settings, *, model: str | BaseChatModel | None = None
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """Build a deep agent rooted at the voice dir, never the repo root (keeps .env unreachable)."""
    backend = FilesystemBackend(root_dir=settings.voice_dir, virtual_mode=True)
    logger.debug("Building hello agent rooted at %s", settings.voice_dir)
    chosen = model or settings.writer_model
    if isinstance(chosen, str):
        chosen = make_chat_model(chosen, settings.anthropic_api_key)
    return create_deep_agent(
        model=chosen,
        system_prompt=HELLO_SYSTEM_PROMPT,
        backend=backend,
        permissions=READ_ONLY_PERMISSIONS,
        name="hello",
    )

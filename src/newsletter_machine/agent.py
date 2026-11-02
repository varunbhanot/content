"""Minimal read-only deep agent over the voice corpus."""

import logging

from deepagents import FilesystemPermission, create_deep_agent
from deepagents.backends.filesystem import FilesystemBackend
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


def build_hello_agent(
    settings: Settings, *, model: str | BaseChatModel | None = None
) -> CompiledStateGraph:  # type: ignore[type-arg]
    """Build a deep agent rooted at the voice dir, never the repo root (keeps .env unreachable)."""
    backend = FilesystemBackend(root_dir=settings.voice_dir, virtual_mode=True)
    logger.debug("Building hello agent rooted at %s", settings.voice_dir)
    return create_deep_agent(
        model=model or settings.writer_model,
        system_prompt=HELLO_SYSTEM_PROMPT,
        backend=backend,
        permissions=READ_ONLY_PERMISSIONS,
        name="hello",
    )

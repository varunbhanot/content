"""Model-call middleware shared by the lead editor and the ``create_agent`` sub-agents."""

from typing import Any

import anthropic
from langchain.agents.middleware import AgentMiddleware, ModelRetryMiddleware
from langchain_anthropic import ChatAnthropic
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware
from langchain_core.exceptions import ModelError, ModelTimeoutError
from langchain_core.language_models import BaseChatModel

# Outer retries, on top of the Anthropic SDK's own short ones (ChatAnthropic max_retries=2):
# slower waits ride out a 429/529 burst that outlasts the SDK's backoff instead of killing a
# paid run.
MODEL_RETRIES = 3
RETRY_INITIAL_DELAY_S = 5.0
RETRY_BACKOFF_FACTOR = 3.0  # waits ~5s, 15s, 45s (with +-25% jitter)
RETRY_MAX_DELAY_S = 60.0
TRANSIENT_STATUS_CODES = frozenset({408, 409, 429})  # plus every 5xx (500, 503, 529, ...)


def _server_forbids_retry(exc: anthropic.APIStatusError) -> bool:
    return exc.response.headers.get("x-should-retry") == "false"


def is_transient_error(exc: Exception) -> bool:
    """True for rate limits, overload, dropped connections and 5xx; never for timeouts (the
    SDK already retried those, and more would multiply a ~10 min timeout), errors the
    server marks ``x-should-retry: false``, validation, auth or anything else."""
    if isinstance(exc, anthropic.APITimeoutError | ModelTimeoutError):
        return False
    if isinstance(exc, anthropic.APIConnectionError):
        return True
    if isinstance(exc, anthropic.APIStatusError):
        code = exc.status_code
        transient = code in TRANSIENT_STATUS_CODES or code >= 500
        return transient and not _server_forbids_retry(exc)
    return isinstance(exc, ModelError) and exc.is_retryable


def model_retry() -> ModelRetryMiddleware[Any, Any]:
    """Bounded exponential-backoff retries of transient model errors; re-raises when exhausted
    so callers (e.g. the editor's salvage path) still see the real failure."""
    return ModelRetryMiddleware(
        max_retries=MODEL_RETRIES,
        retry_on=is_transient_error,
        on_failure="error",
        backoff_factor=RETRY_BACKOFF_FACTOR,
        initial_delay=RETRY_INITIAL_DELAY_S,
        max_delay=RETRY_MAX_DELAY_S,
    )


def prompt_caching(model: BaseChatModel) -> list[AgentMiddleware[Any, Any, Any]]:
    """Anthropic prompt caching for Anthropic models; nothing for any other provider."""
    if isinstance(model, ChatAnthropic):
        return [AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore")]
    return []


def subagent_middleware(model: BaseChatModel) -> list[AgentMiddleware[Any, Any, Any]]:
    """Middleware for a ``create_agent`` sub-agent: retries, then caching where supported."""
    return [model_retry(), *prompt_caching(model)]

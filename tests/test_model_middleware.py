from typing import Any

import anthropic
import pytest
from langchain.agents import create_agent
from langchain.agents.middleware import ModelRetryMiddleware
from langchain_anthropic import ChatAnthropic
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware
from langchain_core.exceptions import (
    ModelAuthenticationError,
    ModelRateLimitError,
    ModelTimeoutError,
)

from fakes import API_REQUEST, connection_error, fake, flaky, status_error
from newsletter_machine.model_middleware import (
    MODEL_RETRIES,
    is_transient_error,
    model_retry,
    prompt_caching,
    subagent_middleware,
)


@pytest.fixture(autouse=True)
def _no_backoff_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("langchain.agents.middleware.model_retry.time.sleep", lambda _: None)


def _anthropic() -> ChatAnthropic:
    return ChatAnthropic(model_name="m", api_key="k")  # type: ignore[call-arg, arg-type]


@pytest.mark.parametrize(
    "exc",
    [
        status_error(anthropic.RateLimitError, 429),
        status_error(anthropic.OverloadedError, 529),
        status_error(anthropic.InternalServerError, 500),
        status_error(anthropic.ServiceUnavailableError, 503),
        status_error(anthropic.APIStatusError, 408),
        connection_error(),
        ModelRateLimitError("slow down"),
    ],
)
def test_transient_errors_are_retryable(exc: Exception) -> None:
    assert is_transient_error(exc)


@pytest.mark.parametrize(
    "exc",
    [
        status_error(anthropic.AuthenticationError, 401),
        status_error(anthropic.BadRequestError, 400),
        status_error(anthropic.PermissionDeniedError, 403),
        status_error(anthropic.NotFoundError, 404),
        status_error(anthropic.OverloadedError, 529, headers={"x-should-retry": "false"}),
        anthropic.APITimeoutError(request=API_REQUEST),
        ModelTimeoutError("hung"),
        ModelAuthenticationError("bad key"),
        ValueError("invalid"),
        StopIteration(),
    ],
)
def test_validation_and_auth_errors_are_not_retryable(exc: Exception) -> None:
    assert not is_transient_error(exc)


def test_model_retry_is_bounded_and_raises_when_exhausted() -> None:
    retry = model_retry()
    assert isinstance(retry, ModelRetryMiddleware)
    assert retry.max_retries == MODEL_RETRIES == 3
    assert retry.on_failure == "error"
    assert retry.backoff_factor > 1
    assert retry.initial_delay * retry.backoff_factor ** (MODEL_RETRIES - 1) <= retry.max_delay


def test_prompt_caching_is_for_anthropic_models_only() -> None:
    assert prompt_caching(fake()) == []
    [caching] = prompt_caching(_anthropic())
    assert isinstance(caching, AnthropicPromptCachingMiddleware)


def test_subagent_middleware_retries_always_and_caches_anthropic_only() -> None:
    assert [type(m) for m in subagent_middleware(fake())] == [ModelRetryMiddleware]
    assert [type(m) for m in subagent_middleware(_anthropic())] == [
        ModelRetryMiddleware,
        AnthropicPromptCachingMiddleware,
    ]


def _run(model: Any) -> str:
    agent = create_agent(model, tools=[], middleware=subagent_middleware(model))
    result = agent.invoke({"messages": [{"role": "user", "content": "hi"}]})
    return str(result["messages"][-1].content)


def test_transient_failure_is_retried_then_succeeds() -> None:
    model = flaky([status_error(anthropic.OverloadedError, 529)], "ok")
    assert _run(model) == "ok"
    assert model.calls == 2


def test_non_transient_failure_is_raised_without_retry() -> None:
    model = flaky([status_error(anthropic.AuthenticationError, 401)], "never")
    with pytest.raises(anthropic.AuthenticationError):
        _run(model)
    assert model.calls == 1


def test_persistent_transient_failure_gives_up_after_the_retry_budget() -> None:
    errors = [status_error(anthropic.RateLimitError, 429) for _ in range(MODEL_RETRIES + 1)]
    model = flaky(errors, "never")
    with pytest.raises(anthropic.RateLimitError):
        _run(model)
    assert model.calls == MODEL_RETRIES + 1


RETRY_AND_CACHE = [ModelRetryMiddleware, AnthropicPromptCachingMiddleware]
BUILDERS = [  # (module, builder, middleware for an Anthropic model)
    ("newsletter_machine.writer", "build_writer", RETRY_AND_CACHE),
    ("newsletter_machine.critic", "build_critic", RETRY_AND_CACHE),
    ("newsletter_machine.researcher", "build_researcher", [ModelRetryMiddleware]),
]


@pytest.mark.parametrize(("module", "builder", "anthropic_middleware"), BUILDERS)
def test_sub_agents_retry_and_cache_long_prompts_on_anthropic_only(
    monkeypatch: pytest.MonkeyPatch, module: str, builder: str, anthropic_middleware: list[Any]
) -> None:
    import importlib

    mod = importlib.import_module(module)
    seen: list[list[type[Any]]] = []

    def _capture(*args: Any, **kwargs: Any) -> Any:
        seen.append([type(m) for m in kwargs.get("middleware", ())])
        return create_agent(fake(), tools=[], name="x")

    monkeypatch.setattr(mod, "create_agent", _capture)
    getattr(mod, builder)(_anthropic(), "sys")
    getattr(mod, builder)(fake(), "sys")
    assert seen == [anthropic_middleware, [ModelRetryMiddleware]]


def test_writer_sub_agent_survives_one_transient_failure() -> None:
    from newsletter_machine.writer import build_writer

    model = flaky([connection_error()], "# Draft")
    writer = build_writer(model, "sys")["runnable"]
    result = writer.invoke({"messages": [{"role": "user", "content": "go"}]})
    assert result["messages"][-1].content == "# Draft"
    assert model.calls == 2

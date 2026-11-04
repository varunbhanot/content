"""Live relevance filter (Anthropic API): ``uv run pytest -m live tests/test_relevance_live.py``."""

import os
from pathlib import Path

import pytest
from dotenv import dotenv_values

from newsletter_machine.agent import make_chat_model
from newsletter_machine.config import load_relevance_model, load_settings
from newsletter_machine.relevance import (
    build_relevance_classifier,
    classify_sources,
    relevance_system_prompt,
)
from newsletter_machine.sources import SourceDoc

REPO_ROOT = Path(__file__).resolve().parent.parent
LIVE_ENV = {k: v for k, v in {**dotenv_values(REPO_ROOT / ".env"), **os.environ}.items() if v}
CONTEXT = (
    "Series topic: evals for LLM agents\nOutline:\n"
    "- Part 1: Why demos lie. Why do agents that pass a demo fail in production? (this part)\n"
    "- Part 2: Golden sets. How do you build a test set that reflects real traffic?"
)
ON_TOPIC = SourceDoc(
    url="https://example.com/golden-sets",
    title="Building a golden set for your agent",
    kind="article",
    status="ok",
    text="We sampled 300 real support tickets, labelled the expected tool calls, and scored "
    "every agent release against them before shipping. Regressions dropped by half.",
)
OFF_TOPIC = SourceDoc(
    url="https://example.com/sourdough",
    title="A beginner's sourdough schedule",
    kind="article",
    status="ok",
    text="Feed the starter at 8am, mix the dough at noon, and bake at 6pm the next day.",
)


@pytest.mark.live
@pytest.mark.skipif(not LIVE_ENV.get("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY")
def test_live_relevance_parks_an_off_topic_source() -> None:
    settings = load_settings(LIVE_ENV, repo_root=REPO_ROOT)
    model = make_chat_model(load_relevance_model(settings, LIVE_ENV), settings.anthropic_api_key)
    classifier = build_relevance_classifier(model, relevance_system_prompt())

    result = classify_sources(classifier, (ON_TOPIC, OFF_TOPIC), CONTEXT)

    assert result.unchecked == ()
    assert [d.url for d in result.kept] == [ON_TOPIC.url]
    assert [p.doc.url for p in result.parked] == [OFF_TOPIC.url]

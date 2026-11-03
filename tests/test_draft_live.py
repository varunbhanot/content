"""Live draft against the Anthropic API: ``uv run pytest -m live tests/test_draft_live.py``."""

import os
from pathlib import Path

import pytest
from dotenv import dotenv_values

from newsletter_machine.agent import make_chat_model
from newsletter_machine.config import Settings, load_settings
from newsletter_machine.critic import critic_task, run_critic
from newsletter_machine.drafting import build_subagents
from newsletter_machine.grounding import load_grounding
from newsletter_machine.ingest import read_sources
from newsletter_machine.writer import run_writer, writer_task

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "sources"
LIVE_ENV = {k: v for k, v in {**dotenv_values(REPO_ROOT / ".env"), **os.environ}.items() if v}


@pytest.fixture
def real_settings() -> Settings:
    return load_settings(LIVE_ENV, repo_root=REPO_ROOT)


@pytest.mark.live
@pytest.mark.skipif(not LIVE_ENV.get("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY")
def test_live_writer_then_critic(real_settings: Settings) -> None:
    grounding = load_grounding(real_settings.voice_dir)
    key = real_settings.anthropic_api_key
    agents = build_subagents(
        grounding,
        make_chat_model(real_settings.writer_model, key),
        make_chat_model(real_settings.critic_model, key),
    )
    docs = read_sources(FIXTURES)
    draft = run_writer(agents.writer, writer_task(docs, "evals are the moat, not prompts"))
    assert draft.startswith("# ")
    assert "## Sources" in draft
    critique = run_critic(agents.critic, critic_task(draft, docs), grounding.checklist, draft)
    assert len(critique.results) == len(grounding.checklist.items)
    assert critique.not_checked == 0
    assert critique.summary

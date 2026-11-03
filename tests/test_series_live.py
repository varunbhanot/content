"""Live series planning (Anthropic API): ``uv run pytest -m live tests/test_series_live.py``."""

import os
from pathlib import Path

import pytest
from dotenv import dotenv_values

from newsletter_machine.agent import make_chat_model
from newsletter_machine.config import load_planner_model, load_settings
from newsletter_machine.ingest import read_sources
from newsletter_machine.planner import (
    MAX_PARTS,
    MIN_PARTS,
    build_planner,
    planner_system_prompt,
    run_planner,
)
from newsletter_machine.writer import usable_sources

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "sources"
LIVE_ENV = {k: v for k, v in {**dotenv_values(REPO_ROOT / ".env"), **os.environ}.items() if v}


@pytest.mark.live
@pytest.mark.skipif(not LIVE_ENV.get("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY")
def test_live_planner_proposes_an_outline() -> None:
    settings = load_settings(LIVE_ENV, repo_root=REPO_ROOT)
    model = make_chat_model(load_planner_model(settings, LIVE_ENV), settings.anthropic_api_key)
    docs = usable_sources(read_sources(FIXTURES))

    series = run_planner(build_planner(model, planner_system_prompt()), "evals", docs)

    assert MIN_PARTS <= len(series.parts) <= MAX_PARTS
    assert series.parts[0].access == "free"
    assert all(len(part.arc) >= 2 and part.question for part in series.parts)

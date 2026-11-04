"""Live part summary (Anthropic API): ``uv run pytest -m live tests/test_series_summary_live.py``."""

import os
from pathlib import Path

import pytest
from dotenv import dotenv_values

from newsletter_machine.agent import make_chat_model
from newsletter_machine.config import load_settings, load_summary_model
from newsletter_machine.series_summary import (
    MAX_SUMMARY_CHARS,
    build_summariser,
    summarise_part,
    summary_system_prompt,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
LIVE_ENV = {k: v for k, v in {**dotenv_values(REPO_ROOT / ".env"), **os.environ}.items() if v}
DRAFT = """# Your demo passed. Production did not.

Every agent demo I have seen passes. The demo is twenty hand-picked prompts.

Production is ten thousand tickets nobody picked. Without evals you only learn that from users.

So measure before you ship: sample real traffic, label what good looks like, score every release.

*Next in this series: how to build a golden set from real traffic.*

## Sources

- [Why agent demos fail](https://example.com/why)
"""


@pytest.mark.live
@pytest.mark.skipif(not LIVE_ENV.get("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY")
def test_live_summary_is_one_short_line() -> None:
    settings = load_settings(LIVE_ENV, repo_root=REPO_ROOT)
    model = make_chat_model(load_summary_model(settings, LIVE_ENV), settings.anthropic_api_key)

    summary = summarise_part(build_summariser(model, summary_system_prompt()), DRAFT)

    assert summary and "\n" not in summary and len(summary) <= MAX_SUMMARY_CHARS
    assert "—" not in summary

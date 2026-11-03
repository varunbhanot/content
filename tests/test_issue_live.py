"""Live editor run against the Anthropic API: ``uv run pytest -m live tests/test_issue_live.py``."""

import os
import shutil
from pathlib import Path

import pytest
from dotenv import dotenv_values

from newsletter_machine.cli import main

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "sources"
LIVE_ENV = {k: v for k, v in {**dotenv_values(REPO_ROOT / ".env"), **os.environ}.items() if v}


@pytest.mark.live
@pytest.mark.skipif(not LIVE_ENV.get("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY")
def test_live_issue_from_fixture_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(REPO_ROOT)  # NM_VOICE_DIR is relative to the repo
    sources = tmp_path / "sources"
    shutil.copytree(FIXTURES, sources)
    out = tmp_path / "issue.md"
    code = main(
        ["issue", "--sources", str(sources), "--angle", "evals are the moat", "--out", str(out)]
    )
    assert code == 0
    draft = out.read_text()
    assert draft.startswith("# ")
    assert "## Sources\n\n- [Why agent demos fail in production](" in draft
    assert (tmp_path / "issue.critique.md").read_text().startswith("# Voice critique: issue.md")
    notes = (tmp_path / "issue.notes.md").read_text()
    assert "## Run log\n\n- Draft v1:" in notes

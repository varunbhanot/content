from pathlib import Path
from typing import Any

import pytest

from fakes import VOICE, FakeModel, fake
from newsletter_machine import cli_series, config, series_store
from newsletter_machine.cli import main
from newsletter_machine.ingest import write_sources
from newsletter_machine.series_store import load_series, save_series
from test_cli_series import DOCS
from test_series_revise import SERIES, _revised, revision_reply

REPLY = revision_reply(_revised("Judges", [3], [1, 2]), _revised("Golden sets", [2], []))


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("NM_VOICE_DIR", str(VOICE))
    monkeypatch.setenv("NM_WRITER_MODEL", "fake:writer")
    monkeypatch.setenv("NM_PLANNER_MODEL", "fake:planner")


def _use_model(monkeypatch: pytest.MonkeyPatch, *replies: Any) -> list[str]:
    calls: list[str] = []

    def _make(model: str, api_key: str) -> FakeModel:
        calls.append(model)
        return fake(*replies)

    monkeypatch.setattr(cli_series, "make_chat_model", _make)
    return calls


def _setup(tmp_path: Path) -> Path:
    write_sources(DOCS, tmp_path / "drafts" / "2026-11-10.sources")
    path = tmp_path / "series" / "evals.yaml"
    save_series(path, SERIES, "evals")
    return path


def _revise(tmp_path: Path, slug: str = "evals", since: str = "2026-11-01") -> int:
    return main(
        [
            "series", "revise", slug, "--since", since,
            "--drafts-dir", str(tmp_path / "drafts"),
            "--series-dir", str(tmp_path / "series"),
        ]
    )  # fmt: skip


def test_revise_writes_a_proposed_outline_with_a_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _setup(tmp_path)
    original = path.read_text(encoding="utf-8")
    calls = _use_model(monkeypatch, REPLY)

    assert _revise(tmp_path) == 0

    assert calls == ["fake:planner"]
    series = load_series(path)
    assert series.status == "proposed"
    assert [p.title for p in series.parts] == ["Why evals", "Judges", "Golden sets"]
    assert len(series.revisions) == 1
    assert (tmp_path / "series" / "evals.yaml.bak").read_text(encoding="utf-8") == original
    out = capsys.readouterr().out
    assert "Revising from 3 sources in 1 folder (2026-11-10.sources)" in out
    assert f"Revised {path} (proposed, 3 parts)" in out
    assert "Rewritten in full" in out and "evals.yaml.bak" in out
    assert "Reason: Judges came first." in out
    assert "  - Part 2 is old Part 3 (moved up): Judges" in out
    assert "  - Old Part 4 dropped: Evals in CI" in out
    assert "Part 2 [paid, planned] Judges" in out
    assert "newsletter-machine series approve evals" in out


@pytest.mark.parametrize(
    ("slug", "since", "message"),
    [
        ("other", "2026-11-01", "No series file"),
        ("evals", "2026-11-20", "No usable saved sources"),
        ("evals", "soon", "since"),
    ],
)
def test_revise_usage_errors_exit_2_before_any_model_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    slug: str,
    since: str,
    message: str,
) -> None:
    _setup(tmp_path)
    calls = _use_model(monkeypatch)
    assert _revise(tmp_path, slug, since) == 2
    assert message in capsys.readouterr().err and calls == []


def test_revise_refuses_a_complete_series(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _setup(tmp_path)
    save_series(path, load_series(path).__class__("evals", "complete", SERIES.parts), "evals")
    _use_model(monkeypatch)
    assert _revise(tmp_path) == 2
    assert "is complete" in capsys.readouterr().err


def test_revise_model_failure_exits_1_and_leaves_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _setup(tmp_path)
    before = path.read_text(encoding="utf-8")
    _use_model(monkeypatch, revision_reply(reason="none"))
    assert _revise(tmp_path) == 1
    assert "Planner failed: The planner proposed no remaining part." in capsys.readouterr().err
    assert path.read_text(encoding="utf-8") == before
    assert not (tmp_path / "series" / "evals.yaml.bak").exists()


def test_revise_write_failure_exits_1_and_keeps_the_outline_on_screen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _setup(tmp_path)
    _use_model(monkeypatch, REPLY)

    def _fail(*args: Any, **kwargs: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(series_store, "write_atomic", _fail)
    assert _revise(tmp_path) == 1
    captured = capsys.readouterr()
    assert "Part 2 [paid, planned] Judges" in captured.out
    assert "Could not write the series: disk full (outline not written)" in captured.err

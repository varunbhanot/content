"""``issue --series`` when this week's sources fit another part better: revise, don't draft."""

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from fakes import DRAFT, FakeModel, critic_reply, fake, relevance_fake
from newsletter_machine import cli_issue, cli_issue_series
from newsletter_machine.ingest import write_sources
from newsletter_machine.series_store import load_series
from test_cli_issue_series import (  # noqa: F401  (_env is an autouse fixture)
    DOCS,
    FULL_RUN,
    SERIES,
    _env,
    _issue,
    _series_file,
    _series_issue,
    _sources,
)
from test_series_revise import _revised, revision_reply

JUDGES_FIRST = revision_reply(
    _revised("Judges", [3], [1, 2]), _revised("Golden sets", [2], []), reason="Judges first."
)
TO_PART_3 = {"evals-a": 3, "evals-b": 3}


def _models(
    monkeypatch: pytest.MonkeyPatch, parts: dict[str, int], planner: Any = JUDGES_FIRST
) -> list[str]:
    replies = {
        "fake:editor": FULL_RUN,
        "fake:writer": (DRAFT,),
        "fake:critic": (critic_reply(),),
        "fake:fast": ("- notes",) * 3,
        "fake:summary": ("Part 2 in a sentence.",),
        "fake:planner": (planner,),
    }
    built: list[str] = []

    def _make(model: str, api_key: str) -> FakeModel:
        built.append(model)
        if model == "fake:relevance":
            return relevance_fake(off=("pricing",), parts=parts)
        return fake(*replies[model])

    monkeypatch.setattr(cli_issue, "make_chat_model", _make)
    monkeypatch.setenv("NM_PLANNER_MODEL", "fake:planner")
    return built


def _no_editor(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail(*args: Any) -> None:
        raise AssertionError("the editor must not run")

    monkeypatch.setattr(cli_issue, "run_editor", _fail)


def test_a_week_that_fits_another_part_revises_the_outline_instead_of_drafting(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _series_file(tmp_path)
    original = path.read_text(encoding="utf-8")
    _models(monkeypatch, TO_PART_3)
    _no_editor(monkeypatch)

    assert _series_issue(tmp_path) == 0

    out = capsys.readouterr().out
    assert "Fit: Part 2 has 0 of 2 on-topic sources; Part 3: 2" in out
    assert "do not fit Part 2, so it was not drafted" in out
    assert "  - Part 2 is old Part 3 (moved up, rewritten): Judges" in out
    assert "series approve evals" in out
    sources = tmp_path / "week.sources"
    assert f"--sources {sources} --out {tmp_path / 'issue.md'}" in out
    assert "--keep-outline" in out and "copy the backup above back over" in out
    series = load_series(path)
    assert series.status == "proposed"
    assert [p.title for p in series.parts] == ["Why evals", "Judges", "Golden sets"]
    assert series.revisions[0].reason == "Judges first."
    assert (tmp_path / "series" / "evals.yaml.bak").read_text(encoding="utf-8") == original
    assert not (tmp_path / "issue.md").exists()
    assert (tmp_path / "issue.parked.md").exists()  # the parked list is still written


def test_keep_outline_drafts_the_planned_part_anyway(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _series_file(tmp_path)
    built = _models(monkeypatch, TO_PART_3)

    assert _series_issue(tmp_path, "--keep-outline") == 0

    out = capsys.readouterr().out
    assert "Fit: Part 2 has 0 of 2 on-topic sources; Part 3: 2" in out
    assert "Marked Part 2 drafted" in out
    assert load_series(path).revisions == ()
    assert "fake:planner" not in built  # not needed: no revision can run


def test_a_good_fit_drafts_without_revising(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _series_file(tmp_path)
    _models(monkeypatch, {})

    assert _series_issue(tmp_path) == 0

    out = capsys.readouterr().out
    assert "Fit: Part 2 has 2 of 2 on-topic sources" in out
    assert "Marked Part 2 drafted" in out
    assert not (tmp_path / "series" / "evals.yaml.bak").exists()
    assert load_series(path).status == "approved"


def test_a_failed_revision_exits_1_and_leaves_the_series(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _series_file(tmp_path)
    before = path.read_text(encoding="utf-8")
    _models(monkeypatch, TO_PART_3, planner=revision_reply(reason="none"))
    _no_editor(monkeypatch)

    assert _series_issue(tmp_path) == 1

    err = capsys.readouterr().err
    assert "Planner failed" in err and "rerun with --keep-outline" in err
    assert path.read_text(encoding="utf-8") == before


def test_keep_outline_needs_series(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    built = _models(monkeypatch, {})
    sources = _sources(tmp_path)
    assert _issue(tmp_path, "--keep-outline", "--sources", str(sources)) == 2
    assert "--keep-outline only applies with --series" in capsys.readouterr().err
    assert built == []


def test_a_series_that_cannot_be_revised_drafts_as_planned_with_a_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    parts = (SERIES.parts[0], SERIES.parts[1], replace(SERIES.parts[2], status="drafted"))
    path = _series_file(tmp_path, replace(SERIES, parts=parts))
    _models(monkeypatch, {"evals-a": 0, "evals-b": 0})
    assert _series_issue(tmp_path) == 0
    captured = capsys.readouterr()
    assert "Part 3 is drafted after a planned part" in captured.err
    assert "drafting Part 2 as planned" in captured.err
    assert "Marked Part 2 drafted" in captured.out
    assert load_series(path).revisions == ()


def test_a_series_at_the_part_limit_is_not_revised(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    written = tuple(
        replace(SERIES.parts[0], number=n, title=f"W{n}", status="drafted") for n in range(1, 7)
    )
    planned = replace(SERIES.parts[1], number=7)
    _series_file(tmp_path, replace(SERIES, parts=(*written, planned)))
    _models(monkeypatch, {"evals-a": 0, "evals-b": 0})
    assert _series_issue(tmp_path) == 0
    assert "already has 6 written parts" in capsys.readouterr().err


def test_failed_relevance_checks_block_a_revision(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _series_file(tmp_path)
    _models(monkeypatch, TO_PART_3)
    original = cli_issue.make_chat_model

    def _make(model: str, api_key: str) -> FakeModel:
        if model == "fake:relevance":
            return relevance_fake(off=("pricing",), fail=("evals-c",), parts=TO_PART_3)
        return original(model, api_key)

    monkeypatch.setattr(cli_issue, "make_chat_model", _make)
    docs = (*DOCS, replace(DOCS[0], url="https://example.com/evals-c", text="Body evals-c."))
    folder = tmp_path / "c.sources"
    write_sources(docs, folder)
    assert _issue(tmp_path, "--series", "evals", "--sources", str(folder)) == 0
    assert "1 relevance check failed, so the outline is not revised" in capsys.readouterr().err
    assert load_series(path).revisions == ()


def test_the_rerun_hint_quotes_paths_with_spaces(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _series_file(tmp_path)
    _models(monkeypatch, TO_PART_3)
    _no_editor(monkeypatch)
    folder = tmp_path / "my week.sources"
    write_sources(DOCS, folder)
    assert _issue(tmp_path, "--series", "evals", "--sources", str(folder)) == 0
    assert f"--sources '{folder}'" in capsys.readouterr().out


def test_duplicate_sources_reach_the_reviser_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _series_file(tmp_path)
    _models(monkeypatch, TO_PART_3)
    _no_editor(monkeypatch)
    seen: list[int] = []
    original = cli_issue_series.RevisionJob

    def _job(*args: Any) -> Any:
        seen.append(len(args[3]))
        return original(*args)

    monkeypatch.setattr(cli_issue_series, "RevisionJob", _job)
    folder = tmp_path / "dup.sources"
    write_sources((*DOCS, DOCS[0]), folder)
    assert _issue(tmp_path, "--series", "evals", "--sources", str(folder)) == 0
    assert seen == [2]


def test_too_many_sources_are_cut_for_the_reviser(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _series_file(tmp_path)
    _models(monkeypatch, TO_PART_3)
    _no_editor(monkeypatch)
    monkeypatch.setattr(cli_issue_series, "MAX_PLANNER_SOURCES", 1)
    assert _series_issue(tmp_path) == 0
    assert "Only the first 1 of 2 on-topic sources go to the planner" in capsys.readouterr().out


def test_the_rerun_hint_names_a_custom_series_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "work"
    from newsletter_machine.series_store import save_series

    save_series(folder / "evals.yaml", SERIES, "evals")
    _models(monkeypatch, TO_PART_3)
    _no_editor(monkeypatch)
    sources = _sources(tmp_path)
    args = ["issue", "--out", str(tmp_path / "issue.md"), "--series-dir", str(folder)]
    from newsletter_machine.cli import main

    assert main([*args, "--series", "evals", "--sources", str(sources)]) == 0
    assert f"--series-dir {folder}" in capsys.readouterr().out


def test_a_link_saved_twice_counts_once_for_the_fit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _series_file(tmp_path)
    _models(monkeypatch, {"evals-a": 3})
    folder = tmp_path / "dup2.sources"
    write_sources((*DOCS, DOCS[0]), folder)
    assert _issue(tmp_path, "--series", "evals", "--sources", str(folder)) == 0
    assert "Fit: Part 2 has 1 of 2 on-topic sources; Part 3: 1" in capsys.readouterr().out
    assert load_series(path).revisions == ()


def test_the_rerun_hint_keeps_overwrite(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _series_file(tmp_path)
    _models(monkeypatch, TO_PART_3)
    _no_editor(monkeypatch)
    assert _series_issue(tmp_path, "--overwrite") == 0
    assert f"--out {tmp_path / 'issue.md'} --overwrite" in capsys.readouterr().out

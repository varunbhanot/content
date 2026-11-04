from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from fakes import DRAFT, VOICE, FakeModel, critic_reply, fake, relevance_fake, task_call
from newsletter_machine import cli_issue, cli_issue_series, config, drafting, editor_subagents
from newsletter_machine.cli import main
from newsletter_machine.ingest import write_sources
from newsletter_machine.series import Series, SeriesPart
from newsletter_machine.series_store import load_series, save_series
from newsletter_machine.sources import SourceDoc

FULL_RUN = (
    task_call("researcher", "go", "1"),
    task_call("writer", "Part 1 brief.", "2"),
    task_call("voice-critic", "check", "3"),
    "Done: v1 is ready.",
)
DOCS = tuple(
    SourceDoc(
        url=f"https://example.com/{slug}",
        title=f"Title {slug}",
        kind="article",
        status="ok",
        text=f"Body about {slug}.",
    )
    for slug in ("evals-a", "pricing", "evals-b")
)
LABEL = "Series 'evals', Part 2 of 3: Golden sets (paid)"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("NM_VOICE_DIR", str(VOICE))
    for name in ("writer", "critic", "editor", "fast", "relevance", "summary"):
        monkeypatch.setenv(f"NM_{name.upper()}_MODEL", f"fake:{name}")
    monkeypatch.setenv("NM_MAX_REVISIONS", "1")


def _part(number: int, title: str, status: str = "planned") -> SeriesPart:
    return SeriesPart(
        number=number,
        title=title,
        question=f"Question {number}?",
        brief=f"Brief {number}.",
        arc=("what it is", "how to scale it"),
        access="free" if number == 1 else "paid",
        status=status,  # type: ignore[arg-type]
        sources=(),
    )


SERIES = Series(
    topic="evals",
    status="approved",
    parts=(_part(1, "Why evals", "drafted"), _part(2, "Golden sets"), _part(3, "Judges")),
)


def _series_file(tmp_path: Path, series: Series = SERIES) -> Path:
    path = tmp_path / "series" / "evals.yaml"
    save_series(path, series, "evals")
    return path


def _sources(tmp_path: Path, docs: Sequence[SourceDoc] = DOCS) -> Path:
    folder = tmp_path / "week.sources"
    write_sources(docs, folder)
    return folder


def _use_models(
    monkeypatch: pytest.MonkeyPatch,
    *,
    editor: Sequence[Any] = FULL_RUN,
    off: tuple[str, ...] = ("pricing",),
    writer: str = DRAFT,
    summary: str = "Part 2 in a sentence.",
) -> list[str]:
    replies = {
        "fake:editor": editor,
        "fake:writer": (writer,),
        "fake:critic": (critic_reply(),),
        "fake:fast": ("- notes",) * 3,
        "fake:summary": (summary,),
    }
    built: list[str] = []

    def _make(model: str, api_key: str) -> FakeModel:
        built.append(model)
        return relevance_fake(off=off) if model == "fake:relevance" else fake(*replies[model])

    monkeypatch.setattr(cli_issue, "make_chat_model", _make)
    return built


def _issue(tmp_path: Path, *extra: str) -> int:
    return main(
        [
            "issue", "--out", str(tmp_path / "issue.md"),
            "--series-dir", str(tmp_path / "series"), *extra,
        ]
    )  # fmt: skip


def _series_issue(tmp_path: Path, *extra: str) -> int:
    return _issue(tmp_path, "--series", "evals", "--sources", str(_sources(tmp_path)), *extra)


def test_series_issue_drafts_the_next_part_from_on_topic_sources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _series_file(tmp_path)
    built = _use_models(monkeypatch)
    tasks: list[str] = []
    original = cli_issue.run_editor
    monkeypatch.setattr(
        cli_issue,
        "run_editor",
        lambda e, task, files: tasks.append(task) or original(e, task, files),
    )
    assert _series_issue(tmp_path) == 0
    out = capsys.readouterr().out
    assert f"Drafting {LABEL}" in out
    assert "Relevance: 2 on-topic, 1 parked" in out
    assert f"Parked list -> {tmp_path / 'issue.parked.md'}" in out
    assert "Parked: Title pricing (https://example.com/pricing): about pricing" in out
    assert "Marked Part 2 drafted in" in out
    parked = (tmp_path / "issue.parked.md").read_text()
    assert "- [Title pricing](https://example.com/pricing): about pricing" in parked
    assert str(tmp_path / "week.sources") in parked
    series = load_series(path)
    assert [p.status for p in series.parts] == ["drafted", "drafted", "planned"]
    assert series.parts[1].draft == "issue.md"  # relative to the folder holding series/
    notes = (tmp_path / "issue.notes.md").read_text()
    assert f"## Series\n\n{LABEL}" in notes and "Title pricing" in notes
    assert "- [2] Title evals-b" in notes  # pricing is not numbered: the editor never saw it
    assert f"\n{LABEL}\n" in (tmp_path / "issue.critique.md").read_text()
    assert "Varun's angle: this issue is Part 2 of 3 of a series on evals" in tasks[0]
    assert "pricing" not in tasks[0]
    assert "fake:relevance" in built


def test_series_and_angle_together_are_a_usage_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _series_file(tmp_path)
    built = _use_models(monkeypatch)
    with pytest.raises(SystemExit) as exc:
        _series_issue(tmp_path, "--angle", "evals")
    assert exc.value.code == 2
    assert "not allowed with argument" in capsys.readouterr().err
    assert built == []


@pytest.mark.parametrize(
    ("series", "message"),
    [
        (replace(SERIES, status="proposed"), "is proposed"),
        (
            replace(SERIES, parts=tuple(replace(p, status="drafted") for p in SERIES.parts)),
            "no planned part left",
        ),
        (None, "No series file at"),
    ],
)
def test_series_issue_exits_2_before_any_model_on_a_series_it_cannot_draft(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    series: Series | None,
    message: str,
) -> None:
    if series is not None:
        _series_file(tmp_path, series)
    built = _use_models(monkeypatch)
    assert _series_issue(tmp_path) == 2
    assert message in capsys.readouterr().err
    assert built == []


def test_series_issue_exits_2_on_an_invalid_series_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _series_file(tmp_path)
    path.write_text(path.read_text().replace("topic: evals", "topic: ''"))
    built = _use_models(monkeypatch)
    assert _series_issue(tmp_path) == 2
    assert "'topic' must be non-empty text" in capsys.readouterr().err
    assert built == []


def test_series_issue_exits_2_on_a_bad_series_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _use_models(monkeypatch)
    assert _issue(tmp_path, "--series", "Evals Series", "--sources", str(_sources(tmp_path))) == 2
    assert "kebab-case" in capsys.readouterr().err


def test_series_issue_rewrites_a_parked_list_left_by_a_failed_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _series_file(tmp_path)
    _use_models(monkeypatch)
    (tmp_path / "issue.parked.md").write_text("old")
    assert _series_issue(tmp_path) == 0
    assert (tmp_path / "issue.parked.md").read_text().startswith("# Parked sources")


def test_series_issue_with_no_on_topic_source_exits_0_without_a_draft(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _series_file(tmp_path)
    before = path.read_text()
    _use_models(monkeypatch, off=("Body about",))
    assert _series_issue(tmp_path) == 0
    out = capsys.readouterr().out
    assert "Relevance: 0 on-topic, 3 parked" in out
    assert "No on-topic sources for Part 2; nothing to draft." in out
    assert (tmp_path / "issue.parked.md").exists()
    assert not (tmp_path / "issue.md").exists()
    assert path.read_text() == before


def test_series_issue_leaves_the_series_file_alone_when_the_run_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _series_file(tmp_path)
    before = path.read_text()
    _use_models(monkeypatch, editor=())
    assert _series_issue(tmp_path) == 1
    assert "Part 2 stays planned" in capsys.readouterr().err
    assert path.read_text() == before
    assert (tmp_path / "issue.parked.md").exists()  # written before the editor ran


def test_series_issue_exits_1_but_keeps_the_draft_when_the_series_cannot_be_updated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _series_file(tmp_path)
    _use_models(monkeypatch)

    def _changed(*args: Any, **kwargs: Any) -> bool:
        raise ValueError("Part 2 is drafted, not planned")

    monkeypatch.setattr(cli_issue_series, "mark_drafted", _changed)
    assert _series_issue(tmp_path) == 1
    err = capsys.readouterr().err
    assert "Could not update" in err and "not planned" in err and "draft kept" in err
    assert (tmp_path / "issue.md").exists()


def test_series_issue_says_when_comments_could_not_be_kept(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _series_file(tmp_path)
    _use_models(monkeypatch)
    monkeypatch.setattr(cli_issue_series, "mark_drafted", lambda *a, **k: False)
    assert _series_issue(tmp_path) == 0
    assert "rewritten in full" in capsys.readouterr().out


def test_series_issue_exits_1_when_the_parked_file_cannot_be_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _series_file(tmp_path)
    _use_models(monkeypatch)
    original = Path.write_text

    def _write(self: Path, *args: Any, **kwargs: Any) -> int:
        if self.name.endswith(".parked.md"):
            raise PermissionError("read-only disk")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", _write)
    assert _series_issue(tmp_path) == 1
    captured = capsys.readouterr()
    assert "Could not write the parked list: read-only disk" in captured.err
    assert "Parked list ->" not in captured.out
    assert not (tmp_path / "issue.md").exists()


def test_series_issue_reports_unchecked_sources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _series_file(tmp_path)
    _use_models(monkeypatch)

    def _make(model: str, api_key: str) -> FakeModel:
        if model == "fake:relevance":
            return relevance_fake(fail=("pricing",))
        replies = {
            "fake:editor": FULL_RUN,
            "fake:writer": (DRAFT,),
            "fake:critic": (critic_reply(),),
        }
        return fake(*replies.get(model, ("- notes",) * 3))

    monkeypatch.setattr(cli_issue, "make_chat_model", _make)
    assert _series_issue(tmp_path) == 0
    out = capsys.readouterr().out
    assert "Relevance: 2 on-topic, 0 parked, 1 unchecked (kept)" in out
    assert "Unchecked (kept): Title pricing" in out
    notes = (tmp_path / "issue.notes.md").read_text()
    assert "kept):\n- [Title pricing](https://example.com/pricing): ConnectionResetError" in notes


def test_series_issue_refuses_an_out_that_is_already_a_parts_draft(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    drafted = replace(SERIES.parts[0], draft=str(tmp_path / "issue.md"))
    path = _series_file(tmp_path, replace(SERIES, parts=(drafted, *SERIES.parts[1:])))
    before = path.read_text()
    built = _use_models(monkeypatch)
    assert _series_issue(tmp_path, "--overwrite") == 2
    err = capsys.readouterr().err
    assert "is already Part 1's draft" in err and "back to planned" in err
    assert built == [] and path.read_text() == before


def test_series_issue_exits_1_without_drafting_when_no_source_could_be_checked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _series_file(tmp_path)
    before = path.read_text()

    def _make(model: str, api_key: str) -> FakeModel:
        if model == "fake:relevance":
            return relevance_fake(fail=("Body about",))
        return fake(*{"fake:editor": FULL_RUN}.get(model, ("- notes",)))

    monkeypatch.setattr(cli_issue, "make_chat_model", _make)
    assert _series_issue(tmp_path) == 1
    captured = capsys.readouterr()
    assert "relevance check failed for every source" in captured.err
    assert "NM_RELEVANCE_MODEL" in captured.err
    assert not (tmp_path / "issue.md").exists() and path.read_text() == before


TEASER_DRAFT = DRAFT.replace(
    "## Sources", "*Next in this series: judges, and when to trust them.*\n\n## Sources"
)
PUBLISHED = replace(
    SERIES,
    parts=(
        replace(
            SERIES.parts[0],
            status="published",
            url="https://example.com/p/why-evals",
            summary="Demos pass because nobody measures them.",
            teaser="Next in this series: how to build a golden set.",
        ),
        *SERIES.parts[1:],
    ),
)


def _capture_writer_and_critic(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    """Record the writer tasks and the critic system prompt the run builds."""
    seen: dict[str, list[str]] = {"writer": [], "critic_prompt": [], "critic_task": []}
    original_task = editor_subagents.revision_task
    original_critic_task = editor_subagents.critic_task

    def _critic_task(*args: Any) -> str:
        text = original_critic_task(*args)
        seen["critic_task"].append(text)
        return text

    monkeypatch.setattr(editor_subagents, "critic_task", _critic_task)
    original_prompt = drafting.critic_system_prompt

    def _task(*args: Any) -> str:
        text = original_task(*args)
        seen["writer"].append(text)
        return text

    def _prompt(*args: Any, **kwargs: Any) -> str:
        text = original_prompt(*args, **kwargs)
        seen["critic_prompt"].append(text)
        return text

    monkeypatch.setattr(editor_subagents, "revision_task", _task)
    monkeypatch.setattr(drafting, "critic_system_prompt", _prompt)
    return seen


def test_series_issue_carries_the_previous_part_forward_and_records_what_this_one_says(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _series_file(tmp_path, PUBLISHED)
    _use_models(monkeypatch, writer=TEASER_DRAFT, summary="Golden sets turn vibes into data.")
    seen = _capture_writer_and_critic(monkeypatch)
    assert _series_issue(tmp_path) == 0
    out = capsys.readouterr().out
    writer_task = seen["writer"][0]
    assert "Previous part (Part 1):" in writer_task
    assert "- URL: https://example.com/p/why-evals" in writer_task
    assert '"Next in this series: how to build a golden set."' in writer_task
    assert 'Part 3 ("Judges": Question 3?)' in writer_task
    critic_prompt = seen["critic_prompt"][0]
    for item in ("series-link-back", "series-teaser-delivered", "series-next-teaser"):
        assert f"id: {item}" in critic_prompt
    assert "how to build a golden set" not in critic_prompt  # draft-derived: user data only
    assert "<series_context>" in seen["critic_task"][0]
    assert "how to build a golden set" in seen["critic_task"][0]
    assert "Summary: Golden sets turn vibes into data." in out
    assert "Teaser: Next in this series: judges, and when to trust them." in out
    part = load_series(path).parts[1]
    assert part.status == "drafted"
    assert part.summary == "Golden sets turn vibes into data."
    assert part.teaser == "Next in this series: judges, and when to trust them."
    critique = (tmp_path / "issue.critique.md").read_text()
    assert "series-next-teaser" in critique


def test_series_issue_warns_when_the_previous_part_has_no_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _series_file(tmp_path)
    _use_models(monkeypatch)
    assert _series_issue(tmp_path) == 0
    out = capsys.readouterr().out
    assert "Part 1 has no URL yet" in out
    assert "newsletter-machine series published evals 1 <url>" in out


def test_series_issue_still_marks_the_part_drafted_when_the_summary_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _series_file(tmp_path)
    _use_models(monkeypatch, summary="")
    assert _series_issue(tmp_path) == 0
    captured = capsys.readouterr()
    assert "Could not summarise Part 2" in captured.err
    assert "No 'Next in this series' line" in captured.err
    part = load_series(path).parts[1]
    assert (part.status, part.summary, part.teaser) == ("drafted", "", "")


def test_series_issue_exits_2_before_any_model_on_broken_series_checks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from newsletter_machine import series_checks

    _series_file(tmp_path)
    broken = tmp_path / "checks.yaml"
    broken.write_text("version: 1\nitems: []\n")
    monkeypatch.setattr(series_checks, "_checks_path", lambda: broken)
    built = _use_models(monkeypatch)
    assert _series_issue(tmp_path) == 2
    assert "'items' must be a non-empty list" in capsys.readouterr().err
    assert built == []


def test_series_issue_marks_the_part_drafted_when_the_draft_cannot_be_reread(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _series_file(tmp_path)
    _use_models(monkeypatch)
    original = Path.read_text

    def _read(self: Path, *args: Any, **kwargs: Any) -> str:
        if self.name == "issue.md":
            raise PermissionError("locked")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _read)
    assert _series_issue(tmp_path) == 0
    assert "for its summary: locked" in capsys.readouterr().err
    part = load_series(path).parts[1]
    assert (part.status, part.summary) == ("drafted", "")


def test_series_issue_does_not_record_a_teaser_on_the_final_part(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    last = replace(
        SERIES, parts=(SERIES.parts[0], replace(SERIES.parts[1], status="drafted"), SERIES.parts[2])
    )
    path = _series_file(tmp_path, last)
    _use_models(monkeypatch, writer=TEASER_DRAFT)
    assert _series_issue(tmp_path) == 0
    assert "final part" in capsys.readouterr().err
    part = load_series(path).parts[2]
    assert (part.status, part.teaser) == ("drafted", "")


def test_series_issue_skips_the_summary_when_the_part_changed_during_the_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _series_file(tmp_path)
    _use_models(monkeypatch)
    original = cli_issue.run_editor
    summaries: list[str] = []

    def _run(*args: Any) -> Any:
        result = original(*args)
        drafted = replace(SERIES.parts[1], status="drafted")  # Varun edited the file meanwhile
        save_series(
            path, replace(SERIES, parts=(SERIES.parts[0], drafted, SERIES.parts[2])), "evals"
        )
        return result

    monkeypatch.setattr(cli_issue, "run_editor", _run)
    monkeypatch.setattr(cli_issue_series, "summarise_part", lambda *a: summaries.append("x") or "")
    assert _series_issue(tmp_path) == 1
    assert "Part 2 is drafted, not planned" in capsys.readouterr().err
    assert summaries == []

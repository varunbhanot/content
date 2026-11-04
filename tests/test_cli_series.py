from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from fakes import VOICE, FakeModel, fake
from newsletter_machine import cli_series, config, series_store
from newsletter_machine.cli import main
from newsletter_machine.ingest import write_sources
from newsletter_machine.series_store import load_series
from newsletter_machine.sources import SourceDoc
from test_planner import _part, plan_reply

DOCS = tuple(
    SourceDoc(
        url=f"https://example.com/{s}",
        title=f"Title {s}",
        kind="article",
        status="ok",
        text=f"Body {s}.",
    )
    for s in ("a", "b", "c")
)
THREE_PARTS = plan_reply(_part(title="One"), _part(title="Two"), _part(title="Three"))


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


def _no_model(monkeypatch: pytest.MonkeyPatch) -> None:
    def _make(model: str, api_key: str) -> FakeModel:
        raise AssertionError("no model may be built")

    monkeypatch.setattr(cli_series, "make_chat_model", _make)


def _drafts(tmp_path: Path, day: str = "2026-10-20") -> Path:
    drafts = tmp_path / "drafts"
    write_sources(DOCS, drafts / f"{day}.sources")
    return drafts


def _plan(tmp_path: Path, *extra: str, topic: str = "evals") -> int:
    return main(
        [
            "series", "plan", topic, "--since", "2026-10-01",
            "--drafts-dir", str(tmp_path / "drafts"),
            "--series-dir", str(tmp_path / "series"),
            *extra,
        ]
    )  # fmt: skip


def _cmd(tmp_path: Path, command: str, slug: str = "evals") -> int:
    return main(["series", command, slug, "--series-dir", str(tmp_path / "series")])


def test_plan_writes_proposed_series_and_prints_outline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _drafts(tmp_path)
    calls = _use_model(monkeypatch, THREE_PARTS)

    assert _plan(tmp_path) == 0

    assert calls == ["fake:planner"]
    series = load_series(tmp_path / "series" / "evals.yaml")
    assert series.status == "proposed"
    assert [p.title for p in series.parts] == ["One", "Two", "Three"]
    out = capsys.readouterr().out
    assert "Planning from 3 sources in 1 folder (2026-10-20.sources)" in out
    assert "Part 1 [free, planned] One" in out
    assert "series approve evals" in out


def test_plan_default_window_is_28_days(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    today = datetime.now(config.issue_timezone()).date()
    old = (today - timedelta(days=40)).isoformat()
    _drafts(tmp_path, old)
    _no_model(monkeypatch)
    args = ["--drafts-dir", str(tmp_path / "drafts"), "--series-dir", str(tmp_path / "s")]

    assert main(["series", "plan", "evals", *args]) == 2
    assert "No usable saved sources" in capsys.readouterr().err

    _drafts(tmp_path, (today - timedelta(days=3)).isoformat())
    _use_model(monkeypatch, THREE_PARTS)
    assert main(["series", "plan", "evals", *args]) == 0


def test_plan_slug_comes_from_topic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _drafts(tmp_path)
    _use_model(monkeypatch, THREE_PARTS)

    assert _plan(tmp_path, topic="LLM as Judge") == 0

    assert load_series(tmp_path / "series" / "llm-as-judge.yaml").topic == "LLM as Judge"


@pytest.mark.parametrize(
    ("setup", "extra", "message"),
    [
        ("none", (), "No usable saved sources"),
        ("missing-drafts", (), "is not a directory"),
        ("bad-since", ("--since", "soon"), "since must look like"),
        ("bad-topic", (), "topic must contain ASCII letters or digits"),
        ("unicode-topic", (), "topic must contain ASCII letters or digits"),
        ("no-key", (), "ANTHROPIC_API_KEY"),
        ("proposed", (), "--overwrite"),
        ("approved", ("--overwrite",), "is approved"),
        ("invalid", (), "evals.yaml"),
        ("series-dir-is-file", (), "not a directory"),
    ],
)
def test_plan_usage_errors_exit_2_before_any_model_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    setup: str,
    extra: tuple[str, ...],
    message: str,
) -> None:
    _no_model(monkeypatch)
    if setup != "missing-drafts":
        (tmp_path / "drafts").mkdir()
    if setup not in ("none", "missing-drafts"):
        _drafts(tmp_path)
    if setup == "no-key":
        monkeypatch.delenv("ANTHROPIC_API_KEY")
    if setup in ("proposed", "approved", "invalid"):
        (tmp_path / "series").mkdir()
        status = "approved" if setup == "approved" else "proposed"
        text = _valid_yaml(status) if setup != "invalid" else "topic: [\n"
        (tmp_path / "series" / "evals.yaml").write_text(text, encoding="utf-8")
    if setup == "series-dir-is-file":
        (tmp_path / "series").write_text("x", encoding="utf-8")
    topic = {"bad-topic": "!!!", "unicode-topic": "評価"}.get(setup, "evals")

    assert _plan(tmp_path, *extra, topic=topic) == 2

    assert message in capsys.readouterr().err


def _valid_yaml(status: str) -> str:
    return (
        f"topic: evals\nstatus: {status}\nparts:\n- number: 1\n  title: T\n  question: Q?\n"
        "  brief: B.\n  arc: [a, b]\n  access: free\n  status: planned\n  sources: []\n"
    )


def test_plan_overwrite_replaces_proposed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _drafts(tmp_path)
    (tmp_path / "series").mkdir()
    (tmp_path / "series" / "evals.yaml").write_text(_valid_yaml("proposed"), encoding="utf-8")
    _use_model(monkeypatch, THREE_PARTS)

    assert _plan(tmp_path, "--overwrite") == 0

    assert len(load_series(tmp_path / "series" / "evals.yaml").parts) == 3


@pytest.mark.parametrize("replies", [(plan_reply(_part(), _part()),), ()])
def test_plan_model_failure_exits_1_and_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    replies: tuple[AIMessage, ...],
) -> None:
    _drafts(tmp_path)
    _use_model(monkeypatch, *replies)  # no replies: the fake model fails when called

    assert _plan(tmp_path) == 1

    assert "Planner failed" in capsys.readouterr().err
    assert not (tmp_path / "series" / "evals.yaml").exists()


def test_plan_refuses_to_write_if_approved_meanwhile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _drafts(tmp_path)
    _use_model(monkeypatch, THREE_PARTS)
    target = tmp_path / "series" / "evals.yaml"
    real_run = cli_series.run_planner

    def _run_then_approve(*args: Any) -> Any:
        result = real_run(*args)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_valid_yaml("approved"), encoding="utf-8")
        return result

    monkeypatch.setattr(cli_series, "run_planner", _run_then_approve)

    assert _plan(tmp_path) == 1

    assert "not written" in capsys.readouterr().err
    assert load_series(target).status == "approved"


def test_plan_write_failure_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _drafts(tmp_path)
    _use_model(monkeypatch, THREE_PARTS)

    def _fail(*args: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(cli_series, "save_series", _fail)

    assert _plan(tmp_path) == 1
    captured = capsys.readouterr()
    assert "Could not write the series: disk full" in captured.err
    assert "Part 1 [free, planned] One" in captured.out  # the paid-for outline is not lost


def test_approve_and_show_need_no_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    (tmp_path / "series").mkdir()
    (tmp_path / "series" / "evals.yaml").write_text(_valid_yaml("proposed"), encoding="utf-8")

    assert _cmd(tmp_path, "approve") == 0
    assert "Approved" in capsys.readouterr().out
    assert _cmd(tmp_path, "approve") == 0
    assert "already approved" in capsys.readouterr().out
    assert _cmd(tmp_path, "show") == 0
    assert "Series 'evals' (approved): evals" in capsys.readouterr().out


@pytest.mark.parametrize("command", ["approve", "show"])
@pytest.mark.parametrize(
    ("setup", "message"),
    [
        ("missing", "series plan"),
        ("invalid", "invalid YAML"),
        ("bad-slug", "kebab-case"),
    ],
)
def test_approve_and_show_errors_exit_2(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    command: str,
    setup: str,
    message: str,
) -> None:
    (tmp_path / "series").mkdir()
    if setup == "invalid":
        (tmp_path / "series" / "evals.yaml").write_text("topic: [\n", encoding="utf-8")

    assert _cmd(tmp_path, command, "Evals" if setup == "bad-slug" else "evals") == 2

    assert message in capsys.readouterr().err


def test_approve_enforces_one_active_series(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "series").mkdir()
    (tmp_path / "series" / "harness.yaml").write_text(_valid_yaml("approved"), encoding="utf-8")
    (tmp_path / "series" / "evals.yaml").write_text(_valid_yaml("proposed"), encoding="utf-8")

    assert _cmd(tmp_path, "approve") == 2

    assert "harness is already the active series" in capsys.readouterr().err


def test_approve_write_failure_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "series").mkdir()
    (tmp_path / "series" / "evals.yaml").write_text(_valid_yaml("proposed"), encoding="utf-8")

    def _fail(*args: Any) -> None:
        raise PermissionError("read-only")

    monkeypatch.setattr(series_store, "write_atomic", _fail)

    assert _cmd(tmp_path, "approve") == 1
    assert "Could not write the series: read-only" in capsys.readouterr().err


URL = "https://varunbhanot.substack.com/p/evals-part-1"


def _drafted_series(tmp_path: Path) -> Path:
    (tmp_path / "series").mkdir()
    path = tmp_path / "series" / "evals.yaml"
    text = _valid_yaml("approved").replace("status: planned", "status: drafted", 1) + (
        "- number: 2\n  title: T2\n  question: Q2?\n  brief: B2.\n  arc: [a, b]\n"
        "  access: paid\n  status: planned\n  sources: []\n"
    )
    path.write_text("# Varun: my notes\n" + text, encoding="utf-8")
    return path


def _published(tmp_path: Path, number: str = "1", url: str = URL) -> int:
    return main(
        ["series", "published", "evals", number, url, "--series-dir", str(tmp_path / "series")]
    )


def test_published_records_the_url_and_needs_no_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    path = _drafted_series(tmp_path)

    assert _published(tmp_path) == 0
    assert f"Recorded Part 1 published at {URL} in {path}" in capsys.readouterr().out
    assert "# Varun: my notes" in path.read_text()
    part = load_series(path).parts[0]
    assert (part.status, part.url) == ("published", URL)

    assert _published(tmp_path) == 0
    assert "already recorded" in capsys.readouterr().out


def test_published_says_when_comments_could_not_be_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _drafted_series(tmp_path)
    monkeypatch.setattr(cli_series, "save_publication", lambda publication: False)

    assert _published(tmp_path) == 0
    assert "rewritten in full" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("number", "url", "message"),
    [
        ("1", "ftp://example.com/p", "http(s) address"),
        ("2", URL, "Part 2 is planned"),
        ("9", URL, "no Part 9"),
    ],
)
def test_published_usage_errors_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], number: str, url: str, message: str
) -> None:
    path = _drafted_series(tmp_path)
    before = path.read_text()

    assert _published(tmp_path, number, url) == 2

    assert message in capsys.readouterr().err
    assert path.read_text() == before


def test_published_rejects_a_non_number_part(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _drafted_series(tmp_path)
    with pytest.raises(SystemExit) as exc:
        _published(tmp_path, "one")
    assert exc.value.code == 2


def test_published_write_failure_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _drafted_series(tmp_path)

    def _fail(*args: Any) -> None:
        raise PermissionError("read-only")

    monkeypatch.setattr(series_store, "write_atomic", _fail)

    assert _published(tmp_path) == 1
    assert "Could not write the series: read-only" in capsys.readouterr().err

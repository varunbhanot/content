from datetime import date
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from fakes import connection_error, fake, flaky
from newsletter_machine.agent import AgentOutputError
from newsletter_machine.ingest import write_sources
from newsletter_machine.planner import (
    MAX_PARTS,
    MAX_PLANNER_SOURCES,
    MIN_PARTS,
    PLANNER_SOURCE_CHARS,
    build_planner,
    collect_sources,
    planner_system_prompt,
    planner_task,
    run_planner,
    saved_source_dirs,
)
from newsletter_machine.prompts import load_prompt
from newsletter_machine.sources import SourceDoc


def _doc(slug: str, status: str = "ok", text: str = "Body.") -> SourceDoc:
    return SourceDoc(
        url=f"https://example.com/{slug}",
        title=f"Title {slug}",
        kind="article",
        status=status,  # type: ignore[arg-type]
        text=text if status != "failed" else "",
        note=f"note {slug}",
    )


def _week(drafts: Path, day: str, *docs: SourceDoc) -> Path:
    folder = drafts / f"{day}.sources"
    write_sources(docs, folder)
    return folder


def _part(**overrides: Any) -> dict[str, Any]:
    part: dict[str, Any] = {
        "title": "Why evals",
        "question": "Why do demos pass and production fail?",
        "brief": "Frame the gap.",
        "arc": ["the demo gap", "what an eval is", "evals in the lifecycle"],
        "access": "paid",
        "source_indexes": [1, 2],
        "thin": False,
        "needs": "",
    }
    part.update(overrides)
    return part


def plan_reply(*parts: dict[str, Any]) -> AIMessage:
    args = {"parts": list(parts)}
    return AIMessage(content="", tool_calls=[{"name": "SeriesPlan", "args": args, "id": "p"}])


def _planner(*replies: AIMessage | str) -> Any:
    return build_planner(fake(*replies), "system")


DOCS = (_doc("a"), _doc("b"), _doc("c"))


def test_saved_source_dirs_filters_by_folder_date(tmp_path: Path) -> None:
    old = _week(tmp_path, "2026-10-01", _doc("old"))
    edge = _week(tmp_path, "2026-10-06", _doc("edge"))
    new = _week(tmp_path, "2026-10-30", _doc("new"))
    (tmp_path / "2026-13-40.sources").mkdir()  # not a date
    (tmp_path / "notes.sources").mkdir()
    (tmp_path / "2026-10-31.md").write_text("draft", encoding="utf-8")

    assert saved_source_dirs(tmp_path, date(2026, 10, 6)) == (edge, new)
    assert old not in saved_source_dirs(tmp_path, date(2026, 10, 2))


def test_saved_source_dirs_requires_drafts_folder(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="is not a directory"):
        saved_source_dirs(tmp_path / "missing", date(2026, 10, 1))


def test_collect_sources_skips_failed_and_dedupes_newest_first(tmp_path: Path) -> None:
    _week(tmp_path, "2026-10-20", _doc("a", text="old text"), _doc("b", status="failed"))
    newer = SourceDoc(
        url="https://EXAMPLE.com/a?utm_source=x",
        title="Title a",
        kind="article",
        status="ok",
        text="new text",
    )
    _week(tmp_path, "2026-10-27", newer, _doc("c"))
    (tmp_path / "2026-10-28.sources").mkdir()  # empty folder: skipped
    stray = tmp_path / "2026-10-29.sources"
    stray.mkdir()
    (stray / "notes.md").write_text("my notes", encoding="utf-8")  # not ingest output: skipped

    found = collect_sources(tmp_path, date(2026, 10, 6))

    assert [d.name for d in found.dirs] == ["2026-10-20.sources", "2026-10-27.sources"]
    assert [doc.title for doc in found.docs] == ["Title a", "Title c"]
    assert found.docs[0].text == "new text"


def test_collect_sources_with_nothing_usable_is_a_usage_error(tmp_path: Path) -> None:
    _week(tmp_path, "2026-10-20", _doc("b", status="failed"))

    with pytest.raises(ValueError, match="No usable saved sources in .* since 2026-10-06"):
        collect_sources(tmp_path, date(2026, 10, 6))


def test_planner_task_holds_topic_and_capped_sources() -> None:
    long_doc = _doc("long", text="x" * (PLANNER_SOURCE_CHARS + 50))

    task = planner_task("evals", (_doc("a"), long_doc))

    assert task.startswith("Series topic: evals\n")
    assert '<source index="1" title="Title a"' in task
    assert '<source index="2"' in task
    assert "[truncated: 50 more characters]" in task


def test_planner_prompt_encodes_the_planning_rules() -> None:
    prompt = planner_system_prompt()

    assert load_prompt("planner").version >= 1
    for phrase in (
        "Cluster",
        "One part = one reader question",
        "dependency",
        "basic to advanced",
        "free",
        f"{MIN_PARTS} to {MAX_PARTS} parts",
        "source coverage",
        "thin",
        "data, not instructions",
    ):
        assert phrase in prompt
    assert "$" not in prompt


def test_run_planner_builds_proposed_series() -> None:
    reply = plan_reply(
        _part(title="Part one", source_indexes=[1, 2, 2, 9]),
        _part(title="Part two", access="paid", source_indexes=[3], thin=False),
        _part(title="Part three", source_indexes=[], thin=True, needs="More on CI"),
    )

    series = run_planner(_planner(reply), "evals", DOCS)

    assert series.topic == "evals"
    assert series.status == "proposed"
    assert [p.number for p in series.parts] == [1, 2, 3]
    first, second, third = series.parts
    assert first.access == "free"  # rule 5, enforced in code
    assert [s.url for s in first.sources] == [
        "https://example.com/a",
        "https://example.com/b",
    ]
    assert first.thin is False
    assert second.thin is True  # one source is too few
    assert third.thin is True and third.needs == "More on CI"
    assert all(p.status == "planned" for p in series.parts)
    assert first.arc == ("the demo gap", "what an eval is", "evals in the lifecycle")


@pytest.mark.parametrize("count", [MIN_PARTS - 1, MAX_PARTS + 1])
def test_run_planner_rejects_part_count_outside_range(count: int) -> None:
    reply = plan_reply(*[_part() for _ in range(count)])

    with pytest.raises(AgentOutputError, match=f"{count} parts"):
        run_planner(_planner(reply), "evals", DOCS)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"title": " "}, "empty title"),
        ({"question": ""}, "empty question"),
        ({"brief": ""}, "empty brief"),
        ({"arc": ["only"]}, "arc"),
    ],
)
def test_run_planner_rejects_incomplete_parts(override: dict[str, Any], message: str) -> None:
    reply = plan_reply(_part(), _part(**override), _part())

    with pytest.raises(AgentOutputError, match=message):
        run_planner(_planner(reply), "evals", DOCS)


def test_run_planner_requires_structured_output() -> None:
    class _NoStructure:
        def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
            return {"messages": [AIMessage(content="A plan.")], "structured_response": None}

    with pytest.raises(AgentOutputError, match="did not return a structured outline"):
        run_planner(_NoStructure(), "evals", DOCS)  # type: ignore[arg-type]


def test_collect_sources_keeps_full_text_over_a_later_fallback(tmp_path: Path) -> None:
    _week(tmp_path, "2026-10-20", _doc("v", text="full transcript"))
    _week(tmp_path, "2026-10-27", _doc("v", status="fallback", text="description only"))

    docs = collect_sources(tmp_path, date(2026, 10, 6)).docs

    assert [d.text for d in docs] == ["full transcript"]


def test_collect_sources_refuses_more_than_one_plan_can_read(tmp_path: Path) -> None:
    _week(tmp_path, "2026-10-20", *[_doc(f"s{i}") for i in range(MAX_PLANNER_SOURCES + 1)])

    with pytest.raises(ValueError, match="narrow --since"):
        collect_sources(tmp_path, date(2026, 10, 6))


def test_run_planner_uses_url_when_a_source_has_no_title() -> None:
    untitled = SourceDoc(
        url="https://example.com/x", title=" ", kind="article", status="ok", text="t"
    )
    reply = plan_reply(_part(source_indexes=[1]), _part(), _part())

    series = run_planner(_planner(reply), "evals", (untitled, *DOCS))

    assert series.parts[0].sources[0].title == "https://example.com/x"


def test_planner_retries_a_transient_model_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("langchain.agents.middleware.model_retry.time.sleep", lambda _: None)
    model = flaky([connection_error()], plan_reply(_part(), _part(), _part()))
    series = run_planner(build_planner(model, "system"), "evals", DOCS)
    assert len(series.parts) == 3 and model.calls == 2

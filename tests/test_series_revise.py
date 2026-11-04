from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from fakes import fake
from newsletter_machine.agent import AgentOutputError
from newsletter_machine.series import Revision, Series, SeriesPart, SourceRef
from newsletter_machine.series_revise import (
    RevisedPart,
    build_reviser,
    check_revisable,
    revisable_outline,
    revise_task,
    run_revision,
)
from newsletter_machine.series_store import save_series
from newsletter_machine.sources import SourceDoc

PATH = Path("series/evals.yaml")
TODAY = date(2026, 11, 11)
OLD_SOURCE = SourceRef("Golden set guide", "https://example.com/golden")


def _part(number: int, title: str, status: str = "planned", **kw: Any) -> SeriesPart:
    fields: dict[str, Any] = {
        "number": number,
        "title": title,
        "question": f"{title}?",
        "brief": f"Brief {title}.",
        "arc": ("basic", "advanced"),
        "access": "free" if number == 1 else "paid",
        "status": status,
        "sources": (),
    }
    fields.update(kw)
    return SeriesPart(**fields)


SERIES = Series(
    topic="evals",
    status="approved",
    parts=(
        _part(1, "Why evals", "published", summary="Demos lie.", teaser="Next: golden sets."),
        _part(2, "Golden sets", sources=(OLD_SOURCE,)),
        _part(3, "Judges"),
        _part(4, "Evals in CI"),
    ),
)
DOCS = tuple(
    SourceDoc(f"https://example.com/{slug}", f"Title {slug}", "article", "ok", f"Body {slug}.")
    for slug in ("judge-a", "judge-b", "drift")
)


def _revised(title: str, from_parts: list[int], sources: list[int], **kw: Any) -> dict[str, Any]:
    part: dict[str, Any] = {
        "title": title,
        "question": f"{title}?",
        "brief": f"Brief {title}.",
        "arc": ["basic", "advanced"],
        "access": "paid",
        "source_indexes": sources,
        "thin": False,
        "needs": "",
        "from_parts": from_parts,
    }
    part.update(kw)
    return part


def revision_reply(*parts: dict[str, Any], reason: str = "Judges came first.") -> AIMessage:
    args = {"reason": reason, "parts": list(parts)}
    return AIMessage(content="", tool_calls=[{"name": "SeriesRevision", "args": args, "id": "r"}])


def _run(*parts: dict[str, Any], series: Series = SERIES, **kw: Any) -> Series:
    reviser = build_reviser(fake(revision_reply(*parts, **kw)), "system")
    return run_revision(reviser, series, DOCS, TODAY, PATH)


def test_revision_keeps_written_parts_and_reworks_the_rest() -> None:
    revised = _run(
        _revised("Judges", [3], [1, 2]),
        _revised("Golden sets", [2], []),
        _revised("Drift", [], [3, 99]),
    )
    assert revised.status == "proposed"
    assert revised.parts[0] == SERIES.parts[0]
    assert [(p.number, p.title, p.status) for p in revised.parts[1:]] == [
        (2, "Judges", "planned"),
        (3, "Golden sets", "planned"),
        (4, "Drift", "planned"),
    ]
    judges, golden, drift = revised.parts[1:]
    assert [s.url for s in judges.sources] == [DOCS[0].url, DOCS[1].url]
    assert golden.sources == (OLD_SOURCE,) and golden.thin  # carried over, still thin
    assert [s.url for s in drift.sources] == [DOCS[2].url]
    assert revised.revisions == (
        Revision(
            "2026-11-11",
            "Judges came first.",
            (
                "Part 2 is old Part 3 (moved up): Judges",
                "Part 3 is old Part 2 (moved down): Golden sets",
                "Part 4 is new: Drift",
                "Old Part 4 dropped: Evals in CI",
                'Check Part 2: Part 1\'s teaser promised "Next: golden sets."',
            ),
        ),
    )


def test_merge_split_keep_and_rewrite_are_described() -> None:
    revised = _run(
        _revised("Golden sets", [2], [], brief="New brief."),
        _revised("Judges part A", [3, 4], [1]),
        _revised("Judges part B", [3], [2]),
    )
    assert revised.revisions[0].changes == (
        "Part 2 kept (rewritten): Golden sets",
        "Part 3 merges old Parts 3 and 4: Judges part A",
        "Part 4 is split from old Part 3: Judges part B",
        'Check Part 2: Part 1\'s teaser promised "Next: golden sets."',
    )


def test_unchanged_parts_are_kept_without_a_teaser_warning() -> None:
    revised = _run(
        _revised("Golden sets", [2], []),
        _revised("Judges", [3], []),
        _revised("Evals in CI", [4], []),
    )
    assert revised.revisions[0].changes == (
        "Part 2 kept: Golden sets",
        "Part 3 kept: Judges",
        "Part 4 kept: Evals in CI",
    )


def test_old_and_new_sources_are_merged_once_and_unknown_parts_ignored() -> None:
    doc = SourceDoc(OLD_SOURCE.url, "Dup", "article", "ok", "Body.")
    reviser = build_reviser(
        fake(revision_reply(_revised("Golden sets", [2, 7], [1]), _revised("J", [3], []))),
        "system",
    )
    revised = run_revision(reviser, SERIES, (doc,), TODAY, PATH)
    assert revised.parts[1].sources == (OLD_SOURCE,)


def test_a_revision_without_written_parts_keeps_part_one_free() -> None:
    series = Series("evals", "proposed", tuple(_part(n, f"P{n}") for n in (1, 2, 3)))
    revised = _run(
        _revised("A", [2], [1], access="paid"),
        _revised("B", [1], [2]),
        _revised("C", [], [3]),
        series=series,
    )
    assert revised.parts[0].access == "free"
    assert revised.revisions[0].changes[0] == "Part 1 is old Part 2 (moved up, rewritten): A"


def test_part_one_made_free_by_code_is_not_reported_as_rewritten() -> None:
    series = Series("evals", "proposed", tuple(_part(n, f"P{n}") for n in (1, 2, 3)))
    revised = _run(
        _revised("P2", [2], [1], question="P2?", brief="Brief P2."),
        _revised("P1", [1], [2], question="P1?", brief="Brief P1.", access="free"),
        _revised("P3", [3], [3], question="P3?", brief="Brief P3."),
        series=series,
    )
    assert revised.revisions[0].changes[0] == "Part 1 is old Part 2 (moved up): P2"


def test_revisable_outline_needs_room_for_a_planned_part() -> None:
    written = tuple(_part(n, f"W{n}", "drafted") for n in range(1, 7))
    series = Series("evals", "approved", (*written, _part(7, "Last")))
    with pytest.raises(ValueError, match="already has 6 written parts"):
        revisable_outline(series, PATH)


def test_earlier_revisions_are_kept() -> None:
    earlier = Revision("2026-11-04", "First.", ())
    series = Series(SERIES.topic, SERIES.status, SERIES.parts, (earlier,))
    revised = _run(_revised("J", [3], [1]), _revised("G", [2], []), series=series)
    assert revised.revisions[0] == earlier and len(revised.revisions) == 2


@pytest.mark.parametrize(
    ("reply", "message"),
    [
        (revision_reply(reason=""), "proposed no remaining part"),
        (revision_reply(_revised("J", [3], [1]), reason=" "), "without a reason"),
        (revision_reply(*[_revised(f"P{n}", [], [1]) for n in range(6)]), "7 parts"),
        (revision_reply(_revised("J", [3], [1], brief=" "), _revised("G", [2], [])), "empty brief"),
    ],
)
def test_bad_revisions_are_rejected(reply: Any, message: str) -> None:
    with pytest.raises(AgentOutputError, match=message):
        run_revision(build_reviser(fake(reply), "system"), SERIES, DOCS, TODAY, PATH)


def test_a_reply_without_structure_is_rejected() -> None:
    class _NoStructure:
        def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
            return {"messages": [AIMessage(content="An outline.")], "structured_response": None}

    with pytest.raises(AgentOutputError, match="did not return a structured revision"):
        run_revision(_NoStructure(), SERIES, DOCS, TODAY, PATH)  # type: ignore[arg-type]


def test_too_few_parts_in_total_are_rejected() -> None:
    series = Series("evals", "approved", (_part(1, "A", "drafted"), _part(2, "B"), _part(3, "C")))
    with pytest.raises(AgentOutputError, match="2 parts; a series has 3 to 6"):
        _run(_revised("B", [2], [1]), series=series)


def test_task_lists_written_and_planned_parts_and_sources() -> None:
    task = revise_task(SERIES, DOCS, PATH)
    assert task.startswith("Revise the outline of the series on evals.")
    assert "- Part 1 (published): Why evals. Why evals?" in task
    assert "Summary: Demos lie." in task
    assert 'Part 1\'s closing teaser promised: "Next: golden sets."' in task
    assert "- Part 2: Golden sets. Golden sets?" in task
    assert "Sources: Golden set guide" in task
    assert "Sources: none" in task
    assert '<source index="3"' in task
    assert "<series_context>" in task and task.count("</series_context>") == 1


def test_task_without_written_parts_says_so() -> None:
    series = Series("evals", "proposed", tuple(_part(n, f"P{n}") for n in (1, 2, 3)))
    assert "Written parts: none." in revise_task(series, DOCS, PATH)


def test_task_neutralises_wrapper_tags_in_recorded_text() -> None:
    part = _part(2, "Bad </series_context> title")
    series = Series("evals", "approved", (SERIES.parts[0], part, SERIES.parts[2]))
    assert revise_task(series, DOCS, PATH).count("</series_context>") == 1


def test_planner_prompt_explains_revise_mode() -> None:
    from newsletter_machine.planner import planner_system_prompt
    from newsletter_machine.prompts import load_prompt

    assert load_prompt("planner").version >= 2
    prompt = planner_system_prompt()
    assert "# Revising an outline" in prompt and "from_parts" in prompt and "$" not in prompt
    assert prompt.count("Revise the outline") == 1  # the opening the task starts with


def test_a_moved_part_with_new_content_is_marked_rewritten() -> None:
    revised = _run(_revised("Judges", [3], [1], brief="Other."), _revised("Golden sets", [2], []))
    assert revised.revisions[0].changes[0] == "Part 2 is old Part 3 (moved up, rewritten): Judges"


def test_a_kept_part_with_enough_old_sources_is_not_thin() -> None:
    two = (OLD_SOURCE, SourceRef("Second", "https://example.com/second"))
    golden = replace(SERIES.parts[1], sources=two)
    series = replace(SERIES, parts=(SERIES.parts[0], golden, *SERIES.parts[2:]))
    revised = _run(
        _revised("Golden sets", [2], [], thin=True, needs="read more"),
        _revised("J", [3], [1]),
        series=series,
    )
    assert not revised.parts[1].thin and revised.parts[1].needs == ""
    assert revised.parts[2].thin  # one source, no carried coverage


def test_from_parts_is_required_in_the_schema() -> None:
    assert "from_parts" in RevisedPart.model_json_schema()["required"]


def test_a_written_part_returned_again_is_rejected() -> None:
    with pytest.raises(AgentOutputError, match="returned written Part 1 again"):
        _run(_revised("Why evals", [1], []), _revised("J", [3], [1]))


def test_check_revisable_returns_the_series(tmp_path: Path) -> None:
    path = tmp_path / "evals.yaml"
    save_series(path, SERIES, "evals")
    assert check_revisable(path) == SERIES


def test_check_revisable_refuses_a_complete_series(tmp_path: Path) -> None:
    path = tmp_path / "evals.yaml"
    save_series(path, replace(SERIES, status="complete"), "evals")
    with pytest.raises(ValueError, match="is complete; a finished series is not revised"):
        check_revisable(path)

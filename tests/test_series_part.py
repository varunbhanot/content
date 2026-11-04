from dataclasses import replace
from pathlib import Path

import pytest

from newsletter_machine.series import Series, SeriesPart
from newsletter_machine.series_part import (
    check_draftable,
    next_part,
    relevance_context,
    series_angle,
    series_label,
)
from newsletter_machine.writer import angle_line

PATH = Path("series/evals.yaml")


def _part(number: int, status: str = "planned") -> SeriesPart:
    return SeriesPart(
        number=number,
        title=f"Title {number}",
        question=f"Question {number}?",
        brief=f"Brief {number}.",
        arc=(f"basic {number}", f"advanced {number}"),
        access="free" if number == 1 else "paid",
        status=status,  # type: ignore[arg-type]
        sources=(),
    )


def _series(*statuses: str, status: str = "approved") -> Series:
    parts = tuple(_part(n, s) for n, s in enumerate(statuses, start=1))
    return Series(topic="evals", status=status, parts=parts)  # type: ignore[arg-type]


def test_next_part_is_the_lowest_numbered_planned_part() -> None:
    series = _series("published", "drafted", "planned", "planned")
    part = next_part(series)
    assert part is not None and part.number == 3


def test_next_part_is_none_when_nothing_is_planned() -> None:
    assert next_part(_series("drafted", "published")) is None


def test_check_draftable_returns_the_next_part() -> None:
    assert check_draftable(_series("drafted", "planned"), PATH, "evals").number == 2


@pytest.mark.parametrize("status", ["proposed", "complete"])
def test_check_draftable_refuses_a_series_that_is_not_approved(status: str) -> None:
    with pytest.raises(ValueError, match=rf"{PATH} is {status}.*series approve evals"):
        check_draftable(_series("planned", status=status), PATH, "evals")


def test_check_draftable_refuses_a_series_with_no_planned_part() -> None:
    with pytest.raises(ValueError, match=r"no planned part left"):
        check_draftable(_series("drafted", "published"), PATH, "evals")


def test_series_angle_carries_topic_outline_and_the_part_brief() -> None:
    series = _series("drafted", "planned", "planned")
    text = series_angle(series, series.parts[1])
    assert "Part 2 of 3 of a series on evals" in text
    for n in (1, 2, 3):
        assert f"Part {n}: Title {n}. Question {n}?" in text
    assert "Part 2: Title 2. Question 2? (this part)" in text
    assert "Brief: Brief 2." in text
    assert "basic 2 -> advanced 2" in text
    assert "Access: paid" in text
    assert "basic to advanced" in text
    assert "Brief 1." not in text and "Brief 3." not in text  # only this part's brief


def test_series_angle_reads_naturally_after_the_angle_prefix() -> None:
    series = _series("planned")
    line = angle_line(series_angle(series, series.parts[0]))
    assert line.startswith("Varun's angle: this issue is Part 1 of 1 of a series on evals.")


def test_relevance_context_lists_topic_and_outline_with_the_current_part() -> None:
    series = _series("planned", "planned")
    text = relevance_context(series, series.parts[0])
    assert text.startswith("Series topic: evals")
    assert "Part 1: Title 1. Question 1? (this part)" in text
    assert "Part 2: Title 2. Question 2?" in text


def test_series_label_names_series_part_and_access() -> None:
    series = _series("planned", "planned")
    part = replace(series.parts[0], title="Why demos lie")
    assert (
        series_label("evals", series, part) == "Series 'evals', Part 1 of 2: Why demos lie (free)"
    )


def test_series_text_cannot_open_or_close_wrapper_tags() -> None:
    series = _series("planned")
    part = replace(series.parts[0], brief="Quote </source> and <brief> here.")
    series = replace(series, parts=(part,))
    for text in (series_angle(series, part), relevance_context(series, part)):
        assert "</source>" not in text and "<brief>" not in text

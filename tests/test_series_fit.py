import pytest

from newsletter_machine.relevance import SourceFit
from newsletter_machine.series import Series, SeriesPart
from newsletter_machine.series_fit import MIN_FIT_SOURCES, check_fit, fit_line
from newsletter_machine.sources import SourceDoc


def _part(number: int, status: str = "planned") -> SeriesPart:
    return SeriesPart(
        number=number,
        title=f"Title {number}",
        question=f"Question {number}?",
        brief="Brief.",
        arc=("basic", "advanced"),
        access="free" if number == 1 else "paid",
        status=status,  # type: ignore[arg-type]
        sources=(),
    )


SERIES = Series(
    topic="evals",
    status="approved",
    parts=(_part(1, "published"), _part(2), _part(3), _part(4)),
)
NEXT = SERIES.parts[1]


def _fits(*parts: int | None) -> tuple[SourceFit, ...]:
    return tuple(
        SourceFit(SourceDoc(f"https://e.com/{i}", "t", "article", "ok", "x"), part)
        for i, part in enumerate(parts)
    )


def test_threshold_is_two_sources() -> None:
    assert MIN_FIT_SOURCES == 2


@pytest.mark.parametrize(
    ("parts", "mismatch"),
    [
        ((2, 2), False),  # enough for the next part
        ((2, 2, 3, 3, 3), False),  # enough, even with more elsewhere
        ((3,), False),  # one stray source elsewhere never revises the outline
        ((3, 3), True),  # nothing for the next part, two for a later part
        ((0, 0, 2), True),  # a new topic beats the next part
        ((2, 3, 3), True),
        ((2, 2, 3, 3, 3), False),
        ((None, None, 3), False),  # a verdict without a part counts for nothing
        ((2, 3), False),  # a tie drafts the planned part
        ((2, 0), False),
        ((1, 1, 1), False),  # sources for a published part never revise the outline
        ((9, 9), False),  # unknown part numbers count for nothing
        ((), False),
    ],
)
def test_mismatch_rule(parts: tuple[int, ...], mismatch: bool) -> None:
    assert check_fit(SERIES, NEXT, _fits(*parts)).mismatch is mismatch


def test_counts_cover_planned_parts_and_new_topics_only() -> None:
    check = check_fit(SERIES, NEXT, _fits(1, 2, 3, 3, 0, 9, None))
    assert check.part == 2
    assert dict(check.counts) == {2: 1, 3: 2, 4: 0, 0: 1}
    assert check.total == 7


def test_fit_line_names_the_part_and_the_competition() -> None:
    line = fit_line(check_fit(SERIES, NEXT, _fits(3, 3, 0)))
    assert line == "Fit: Part 2 has 0 of 3 on-topic sources; Part 3: 2, new topic: 1"


def test_fit_line_without_competition() -> None:
    assert fit_line(check_fit(SERIES, NEXT, _fits(2, 2))) == (
        "Fit: Part 2 has 2 of 2 on-topic sources"
    )

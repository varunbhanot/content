from typing import Any

import pytest

from newsletter_machine.series import (
    Series,
    SeriesPart,
    SourceRef,
    format_outline,
    is_slug,
    parse_series,
    series_to_mapping,
)


def _part(number: int, **overrides: Any) -> dict[str, Any]:
    part: dict[str, Any] = {
        "number": number,
        "title": f"Part {number} title",
        "question": f"Question {number}?",
        "brief": f"Brief {number}.",
        "arc": ["basic idea", "advanced idea"],
        "access": "free" if number == 1 else "paid",
        "status": "planned",
        "sources": [{"title": "Why demos fail", "url": "https://example.com/a"}],
        "thin": False,
    }
    part.update(overrides)
    return part


def _data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "topic": "evals",
        "status": "proposed",
        "parts": [_part(1), _part(2), _part(3)],
    }
    data.update(overrides)
    return data


def test_parse_series_builds_frozen_records() -> None:
    series = parse_series(_data(), "series/evals.yaml")

    assert series.topic == "evals"
    assert series.status == "proposed"
    assert [p.number for p in series.parts] == [1, 2, 3]
    first = series.parts[0]
    assert first.arc == ("basic idea", "advanced idea")
    assert first.sources == (SourceRef(title="Why demos fail", url="https://example.com/a"),)
    assert first.access == "free"
    assert (first.draft, first.url, first.summary, first.teaser, first.needs) == (
        None,
        None,
        "",
        "",
        "",
    )


def test_parse_series_accepts_later_phase_fields() -> None:
    part = _part(
        1,
        status="published",
        draft="drafts/2026-11-06.md",
        url="https://varun.substack.com/p/evals-1",
        summary="Evals close the demo gap.",
        teaser="Next: building a golden set.",
        needs="More on labelling cost.",
        thin=True,
    )
    series = parse_series(_data(status="approved", parts=[part]), "f")

    parsed = series.parts[0]
    assert parsed.draft == "drafts/2026-11-06.md"
    assert parsed.url == "https://varun.substack.com/p/evals-1"
    assert parsed.teaser == "Next: building a golden set."
    assert parsed.thin is True


def test_series_round_trips_through_mapping() -> None:
    series = parse_series(_data(), "f")

    assert parse_series(series_to_mapping(series), "f") == series


def test_records_are_immutable() -> None:
    series = parse_series(_data(), "f")

    with pytest.raises(AttributeError):
        series.status = "approved"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (["not", "a", "mapping"], "expected a mapping"),
        (_data(topic=""), "'topic' must be non-empty text"),
        (_data(topic=7), "'topic' must be non-empty text"),
        (_data(status="draft"), "'status' must be one of"),
        (_data(parts=[]), "'parts' must be a non-empty list"),
        (_data(parts="x"), "'parts' must be a non-empty list"),
        (_data(extra=1), r"unknown field\(s\) \['extra'\]"),
        (_data(parts=["x"]), "part #1 is not a mapping"),
        (_data(parts=[_part(1), _part(3)]), "part #2: 'number' must be 2"),
        (_data(parts=[{**_part(1), "number": True}]), "part #1: 'number' must be 1"),
        (_data(parts=[_part(1, title=" ")]), "part 1: 'title' must be non-empty text"),
        (_data(parts=[_part(1, question=None)]), "part 1: 'question' must be non-empty text"),
        (_data(parts=[_part(1, brief=3)]), "part 1: 'brief' must be non-empty text"),
        (_data(parts=[_part(1, arc=["only one"])]), "part 1: 'arc' must list at least 2"),
        (_data(parts=[_part(1, arc="basic")]), "part 1: 'arc' must list at least 2"),
        (_data(parts=[_part(1, arc=["a", ""])]), "part 1: 'arc' must list at least 2"),
        (_data(parts=[_part(1, access="premium")]), "part 1: 'access' must be one of"),
        (_data(parts=[_part(1, status="done")]), "part 1: 'status' must be one of"),
        (_data(parts=[_part(1, thin="yes")]), "part 1: 'thin' must be true or false"),
        (_data(parts=[_part(1, sources="x")]), "part 1: 'sources' must be a list"),
        (_data(parts=[_part(1, sources=["x"])]), "part 1: source #1 must have"),
        (
            _data(parts=[_part(1, sources=[{"title": "t", "url": "ftp://x"}])]),
            "part 1: source #1 must have",
        ),
        (
            _data(parts=[_part(1, sources=[{"title": "t", "url": "https://x", "n": 1}])]),
            "part 1: source #1 must have",
        ),
        (_data(parts=[_part(1, url="not-a-url")]), "part 1: 'url' must be an http"),
        (_data(parts=[_part(1, draft=5)]), "part 1: 'draft' must be text or empty"),
        (_data(parts=[_part(1, summary=5)]), "part 1: 'summary' must be text"),
        (_data(parts=[_part(1, colour="red")]), r"part 1: unknown field\(s\) \['colour'\]"),
    ],
)
def test_parse_series_rejects_invalid_files(data: Any, message: str) -> None:
    with pytest.raises(ValueError, match=message) as info:
        parse_series(data, "series/evals.yaml")
    assert str(info.value).startswith("series/evals.yaml")


def test_missing_required_part_field_is_named() -> None:
    part = _part(1)
    del part["sources"]

    with pytest.raises(ValueError, match="part 1: missing field\\(s\\) \\['sources'\\]"):
        parse_series(_data(parts=[part]), "f")


@pytest.mark.parametrize(
    ("slug", "valid"),
    [("evals", True), ("llm-as-judge", True), ("v2", True), ("Evals", False), ("", False)],
)
def test_is_slug(slug: str, valid: bool) -> None:
    assert is_slug(slug) is valid


def test_format_outline_lists_every_part() -> None:
    thin = _part(2, thin=True, needs="More on labelling cost.", sources=[])
    series = parse_series(_data(parts=[_part(1), thin, _part(3)]), "f")

    text = format_outline(series, "evals")

    assert text.startswith("Series 'evals' (proposed): evals\n")
    assert "Part 1 [free, planned] Part 1 title" in text
    assert "  Question: Question 1?" in text
    assert "  Arc: basic idea -> advanced idea" in text
    assert "  Sources (1): Why demos fail (https://example.com/a)" in text
    assert "Part 2 [paid, planned] Part 2 title  THIN: More on labelling cost." in text
    assert "  Sources (0): none" in text


def test_format_outline_shows_draft_and_url_when_set() -> None:
    part = SeriesPart(
        number=1,
        title="T",
        question="Q?",
        brief="B.",
        arc=("a", "b"),
        access="free",
        status="published",
        sources=(),
        thin=True,
        draft="drafts/x.md",
        url="https://x.example/p",
        summary="Demos lie.",
        teaser="Next in this series: golden sets.",
    )
    text = format_outline(Series(topic="evals", status="approved", parts=(part,)), "evals")

    assert "Part 1 [free, published] T  THIN: needs more reading" in text
    assert "  Draft: drafts/x.md" in text
    assert "  URL: https://x.example/p" in text
    assert "  Summary: Demos lie." in text
    assert "  Teaser: Next in this series: golden sets." in text


def test_null_optional_fields_read_as_empty() -> None:
    part = _part(1, summary=None, teaser=None, needs=None, draft="", url="")

    parsed = parse_series(_data(parts=[part]), "f").parts[0]

    assert (parsed.summary, parsed.teaser, parsed.needs) == ("", "", "")
    assert (parsed.draft, parsed.url) == (None, None)


def test_source_urls_are_case_insensitive_like_ingest() -> None:
    part = _part(1, sources=[{"title": "t", "url": "HTTPS://Example.com/a"}])

    assert parse_series(_data(parts=[part]), "f").parts[0].sources[0].url == (
        "HTTPS://Example.com/a"
    )

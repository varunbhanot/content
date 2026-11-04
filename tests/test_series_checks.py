from dataclasses import replace
from pathlib import Path

import pytest

from fakes import VOICE
from newsletter_machine import series_checks
from newsletter_machine.checklist import Checklist
from newsletter_machine.checks import run_mechanical
from newsletter_machine.grounding import load_grounding
from newsletter_machine.series import Series, SeriesPart
from newsletter_machine.series_checks import (
    SERIES_CHECK_IDS,
    load_series_checks,
    series_checklist,
)
from newsletter_machine.voice import style_guide_sections

GROUNDING = load_grounding(VOICE)
SECTIONS = style_guide_sections(GROUNDING.style_guide)
BASE = GROUNDING.checklist


def _part(number: int, status: str = "planned", **extra: str) -> SeriesPart:
    return SeriesPart(
        number=number,
        title=f"Title {number}",
        question=f"Question {number}?",
        brief=f"Brief {number}.",
        arc=("basic", "advanced"),
        access="paid",
        status=status,  # type: ignore[arg-type]
        sources=(),
        **extra,  # type: ignore[arg-type]
    )


SERIES = Series(
    topic="evals",
    status="approved",
    parts=(
        _part(
            1,
            "published",
            url="https://example.com/p/1",
            summary="Demos lie.",
            teaser="Next in this series: golden sets.",
        ),
        _part(2),
        _part(3),
    ),
)


def _ids(checklist: Checklist) -> list[str]:
    return [item.id for item in checklist.items if item.id.startswith("series-")]


def test_load_series_checks_validates_with_the_checklist_loader() -> None:
    checks = load_series_checks(SECTIONS)
    assert {item.id for item in checks.items} == SERIES_CHECK_IDS
    assert checks.version >= 1


def test_part_1_only_gets_the_closing_teaser_check() -> None:
    combined = series_checklist(BASE, SERIES, SERIES.parts[0], load_series_checks(SECTIONS))
    assert _ids(combined) == ["series-next-teaser"]
    assert combined.items[: len(BASE.items)] == BASE.items
    assert combined.version == BASE.version
    item = combined.items[-1]
    assert 'Part 2 ("Title 2": Question 2?)' in item.rule
    assert "$" not in item.rule + item.check


def test_a_middle_part_gets_link_back_teaser_and_closing_checks_filled_in() -> None:
    combined = series_checklist(BASE, SERIES, SERIES.parts[1], load_series_checks(SECTIONS))
    assert _ids(combined) == ["series-link-back", "series-teaser-delivered", "series-next-teaser"]
    link, teaser, _ = combined.items[len(BASE.items) :]
    assert '"Title 1", https://example.com/p/1' in link.rule
    assert "opening-move" in link.check  # the link-back clause may precede the opening move
    # draft-derived text stays out of the system prompt: it reaches the critic as user data
    text = " ".join(i.rule + i.check for i in combined.items)
    assert "Demos lie." not in text and "golden sets" not in text
    assert "series context" in teaser.check


def test_the_final_part_gets_the_code_checked_no_teaser_item() -> None:
    previous = replace(SERIES.parts[1], status="drafted")  # no URL, summary or teaser
    series = replace(SERIES, parts=(SERIES.parts[0], previous, SERIES.parts[2]))
    part = series.parts[2]
    combined = series_checklist(BASE, series, part, load_series_checks(SECTIONS))
    assert _ids(combined) == ["series-link-back", "series-final-no-teaser"]
    link, final = combined.items[len(BASE.items) :]
    assert "not published yet" in link.rule
    assert final.is_mechanical
    assert run_mechanical(final, "# T\n\n*Next in this series: more.*\n").status == "fail"
    assert run_mechanical(final, "# T\n\nThe end.\n").status == "pass"
    prose = "# T\n\nEach part ended with a Next in this series line.\n"
    assert run_mechanical(final, prose).status == "pass"


def _checks_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    path = tmp_path / "series_checks.yaml"
    path.write_text(text, encoding="utf-8")
    monkeypatch.setattr(series_checks, "_checks_path", lambda: path)


ITEM = "  - id: {id}\n    section: Openings\n    rule: {rule}\n    check: c\n    severity: must\n"


def _items(rule: str = "r", ids: tuple[str, ...] = tuple(sorted(SERIES_CHECK_IDS))) -> str:
    return "version: 1\nitems:\n" + "".join(ITEM.format(id=i, rule=rule) for i in ids)


def test_load_series_checks_refuses_a_missing_or_extra_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _checks_file(tmp_path, monkeypatch, _items(ids=("series-link-back", "series-extra")))
    with pytest.raises(ValueError, match="must define exactly"):
        load_series_checks(SECTIONS)


def test_load_series_checks_refuses_an_unknown_placeholder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _checks_file(tmp_path, monkeypatch, _items(rule="Part $previos_number"))
    with pytest.raises(ValueError, match="placeholder"):
        load_series_checks(SECTIONS)


def test_series_checklist_refuses_an_id_clash_with_the_voice_checklist() -> None:
    checks = load_series_checks(SECTIONS)
    clash = replace(BASE, items=(*BASE.items, replace(BASE.items[0], id="series-next-teaser")))
    with pytest.raises(ValueError, match="already in the voice checklist"):
        series_checklist(clash, SERIES, SERIES.parts[0], checks)

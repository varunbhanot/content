"""Series-only critic checks: continuity items added to the voice checklist on series runs.

The items live in ``series_checks.yaml`` beside this module, in the voice checklist's schema,
and load through the same validator (``checklist.load_checklist``). Code picks the items that
apply to the part being drafted and fills their ``$placeholders`` from the series file; the
writer then targets them and the critic judges them like any other item.
"""

from collections.abc import Mapping
from dataclasses import replace
from importlib import resources
from pathlib import Path
from string import Template

from newsletter_machine.checklist import Checklist, ChecklistItem, load_checklist
from newsletter_machine.series import Series, SeriesPart
from newsletter_machine.series_part import NO_SUMMARY, following_part, previous_part
from newsletter_machine.writer import neutralise_tags

CHECKS_FILE = "series_checks.yaml"
LINK_BACK = "series-link-back"
TEASER_DELIVERED = "series-teaser-delivered"
NEXT_TEASER = "series-next-teaser"
FINAL_NO_TEASER = "series-final-no-teaser"
SERIES_CHECK_IDS = frozenset({LINK_BACK, TEASER_DELIVERED, NEXT_TEASER, FINAL_NO_TEASER})
PLACEHOLDERS = (
    "previous_number",
    "previous_title",
    "previous_link",
    "previous_summary",
    "previous_teaser",
    "next_number",
    "next_title",
    "next_question",
)


def _checks_path() -> Path:
    return Path(str(resources.files("newsletter_machine").joinpath(CHECKS_FILE)))


def _fill(item: ChecklistItem, values: Mapping[str, str]) -> ChecklistItem:
    return replace(
        item,
        rule=Template(item.rule).substitute(values),
        check=Template(item.check).substitute(values),
    )


def load_series_checks(sections: tuple[str, ...]) -> Checklist:
    """Load and validate ``series_checks.yaml``: the voice checklist's rules, plus exactly the
    known ids and only known ``$placeholders``."""
    path = _checks_path()
    checks = load_checklist(path, sections)
    ids = {item.id for item in checks.items}
    if ids != SERIES_CHECK_IDS:
        raise ValueError(
            f"{path}: must define exactly {sorted(SERIES_CHECK_IDS)} (got {sorted(ids)})"
        )
    probe = dict.fromkeys(PLACEHOLDERS, "x")
    for item in checks.items:
        try:
            _fill(item, probe)
        except (KeyError, ValueError) as exc:
            raise ValueError(f"{path}: item {item.id!r} has a bad placeholder: {exc}") from exc
    return checks


def _values(previous: SeriesPart | None, following: SeriesPart | None) -> dict[str, str]:
    values = dict.fromkeys(PLACEHOLDERS, "")
    if previous is not None:
        values |= {
            "previous_number": str(previous.number),
            "previous_title": previous.title,
            "previous_link": previous.url or "not published yet",
            "previous_summary": previous.summary or NO_SUMMARY,
            "previous_teaser": previous.teaser,
        }
    if following is not None:
        values |= {
            "next_number": str(following.number),
            "next_title": following.title,
            "next_question": following.question,
        }
    return {key: neutralise_tags(value) for key, value in values.items()}


def _applies(item_id: str, previous: SeriesPart | None, following: SeriesPart | None) -> bool:
    return {
        LINK_BACK: previous is not None,
        TEASER_DELIVERED: previous is not None and bool(previous.teaser),
        NEXT_TEASER: following is not None,
        FINAL_NO_TEASER: following is None,
    }[item_id]


def series_checklist(
    base: Checklist, series: Series, part: SeriesPart, checks: Checklist
) -> Checklist:
    """``base`` plus the series checks that apply to ``part``, filled in (base version kept)."""
    clash = {item.id for item in base.items} & SERIES_CHECK_IDS
    if clash:
        raise ValueError(f"Series check id(s) {sorted(clash)} already in the voice checklist.")
    previous, following = previous_part(series, part), following_part(series, part)
    values = _values(previous, following)
    extra = tuple(
        _fill(item, values) for item in checks.items if _applies(item.id, previous, following)
    )
    return replace(base, items=(*base.items, *extra))

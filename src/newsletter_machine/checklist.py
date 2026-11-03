"""The voice-critic checklist: an editable YAML file derived from the style guide."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, get_args

import yaml

from newsletter_machine.validation import is_int, one_of

Severity = Literal["must", "should"]
CHECKLIST_FILE = "critic-checklist.yaml"
ID_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
REQUIRED_FIELDS = ("id", "section", "rule", "check", "severity")
OPTIONAL_FIELDS = ("patterns", "allowed", "word_range", "max_paragraph_chars")
HIT_FIELDS = ("patterns", "max_paragraph_chars")  # fields that count hits, which 'allowed' caps
WORD_RANGE_LENGTH = 2


@dataclass(frozen=True)
class ChecklistItem:
    """One rule. Items with ``patterns``/``word_range``/``max_paragraph_chars`` run in code."""

    id: str
    section: str
    rule: str
    check: str
    severity: Severity
    patterns: tuple[re.Pattern[str], ...] = ()
    allowed: int = 0
    word_range: tuple[int, int] | None = None
    max_paragraph_chars: int | None = None

    @property
    def is_mechanical(self) -> bool:
        return bool(self.patterns) or self.word_range is not None or bool(self.max_paragraph_chars)


@dataclass(frozen=True)
class Checklist:
    version: int
    items: tuple[ChecklistItem, ...]


def _text(raw: Mapping[str, Any], name: str, where: str) -> str:
    value = raw.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where}: '{name}' must be non-empty text")
    return value.strip()


def _patterns(raw: Mapping[str, Any], where: str) -> tuple[re.Pattern[str], ...]:
    values = raw.get("patterns", [])
    if not isinstance(values, list) or not all(isinstance(v, str) and v for v in values):
        raise ValueError(f"{where}: 'patterns' must be a list of regexes")
    try:
        return tuple(re.compile(value, re.IGNORECASE) for value in values)
    except re.error as exc:
        raise ValueError(f"{where}: bad pattern: {exc}") from exc


def _word_range(raw: Mapping[str, Any], where: str) -> tuple[int, int] | None:
    value = raw.get("word_range")
    if value is None:
        return None
    if (
        not isinstance(value, list)
        or len(value) != WORD_RANGE_LENGTH
        or not all(is_int(v) and v >= 0 for v in value)
        or value[0] > value[1]
    ):
        raise ValueError(f"{where}: 'word_range' must be [min, max] with 0 <= min <= max")
    return value[0], value[1]


def _positive_int(raw: Mapping[str, Any], name: str, where: str, *, minimum: int) -> int | None:
    value = raw.get(name)
    if value is None:
        return None
    if not is_int(value) or value < minimum:
        raise ValueError(f"{where}: '{name}' must be an integer >= {minimum}")
    return int(value)


def _severity(raw: Mapping[str, Any], where: str) -> Severity:
    return one_of(where, "severity", raw.get("severity"), get_args(Severity))


def _item_id(raw: Mapping[str, Any], path: Path, index: int) -> str:
    value = raw.get("id")
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise ValueError(f"{path}: item #{index}: 'id' must be kebab-case (got {value!r})")
    return value


def _parse_item(raw: object, path: Path, index: int, sections: tuple[str, ...]) -> ChecklistItem:
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: item #{index} is not a mapping")
    item_id = _item_id(raw, path, index)
    where = f"{path}: item {item_id!r}"
    unknown = set(raw) - set(REQUIRED_FIELDS) - set(OPTIONAL_FIELDS)
    if unknown:
        raise ValueError(f"{where}: unknown field(s) {sorted(unknown)}")
    if "allowed" in raw and not set(raw) & set(HIT_FIELDS):
        raise ValueError(f"{where}: 'allowed' only applies to patterns or max_paragraph_chars")
    section = _text(raw, "section", where)
    if section not in sections:
        raise ValueError(f"{where}: section {section!r} is not a '## ' heading in the style guide")
    return ChecklistItem(
        id=item_id,
        section=section,
        rule=_text(raw, "rule", where),
        check=_text(raw, "check", where),
        severity=_severity(raw, where),
        patterns=_patterns(raw, where),
        allowed=_positive_int(raw, "allowed", where, minimum=0) or 0,
        word_range=_word_range(raw, where),
        max_paragraph_chars=_positive_int(raw, "max_paragraph_chars", where, minimum=1),
    )


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"Critic checklist not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping with 'version' and 'items'")
    return data


def load_checklist(path: Path, sections: tuple[str, ...]) -> Checklist:
    """Load and validate; every item must cite one of the style guide's ``sections``."""
    data = _read_yaml(path)
    version, raw_items = data.get("version"), data.get("items")
    if not is_int(version):
        raise ValueError(f"{path}: 'version' must be an integer")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError(f"{path}: 'items' must be a non-empty list")
    items = tuple(
        _parse_item(raw, path, index, sections) for index, raw in enumerate(raw_items, start=1)
    )
    seen: set[str] = set()
    for item in items:
        if item.id in seen:
            raise ValueError(f"{path}: duplicate id {item.id!r}")
        seen.add(item.id)
    return Checklist(version=version, items=items)

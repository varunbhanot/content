from pathlib import Path

import pytest

from newsletter_machine.checklist import ChecklistItem, load_checklist
from newsletter_machine.voice import load_style_guide, style_guide_sections

REPO_VOICE = Path(__file__).resolve().parent.parent / "voice"
SECTIONS = ("Rhythm", "Avoid")


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "critic-checklist.yaml"
    path.write_text(body)
    return path


ITEM = """
  - id: {id}
    section: {section}
    rule: r
    check: c
    severity: must
"""


def _items(*entries: str) -> str:
    return "version: 2\nitems:\n" + "".join(entries)


def test_real_checklist_items_cite_real_style_guide_sections() -> None:
    sections = style_guide_sections(load_style_guide(REPO_VOICE))
    checklist = load_checklist(REPO_VOICE / "critic-checklist.yaml", sections)
    assert len(checklist.items) >= 15
    assert {item.section for item in checklist.items} == set(sections)


def test_real_checklist_has_mechanical_em_dash_check() -> None:
    sections = style_guide_sections(load_style_guide(REPO_VOICE))
    checklist = load_checklist(REPO_VOICE / "critic-checklist.yaml", sections)
    em = next(item for item in checklist.items if item.id == "no-em-dashes")
    assert em.is_mechanical
    assert any(p.search("a — b") for p in em.patterns)


def test_load_checklist_parses_item_and_version(tmp_path: Path) -> None:
    path = _write(tmp_path, _items(ITEM.format(id="a", section="Rhythm")))
    checklist = load_checklist(path, SECTIONS)
    assert checklist.version == 2
    assert checklist.items == (
        ChecklistItem(id="a", section="Rhythm", rule="r", check="c", severity="must"),
    )
    assert not checklist.items[0].is_mechanical


def test_load_checklist_parses_mechanical_fields(tmp_path: Path) -> None:
    extra = "    patterns: ['x+']\n    allowed: 2\n    word_range: [10, 20]\n"
    extra += "    max_paragraph_chars: 50\n"
    path = _write(tmp_path, _items(ITEM.format(id="a", section="Avoid") + extra))
    (item,) = load_checklist(path, SECTIONS).items
    assert item.patterns[0].search("XX")  # case-insensitive
    assert (item.allowed, item.word_range, item.max_paragraph_chars) == (2, (10, 20), 50)
    assert item.is_mechanical


def test_load_checklist_rejects_unknown_section(tmp_path: Path) -> None:
    path = _write(tmp_path, _items(ITEM.format(id="a", section="Nope")))
    with pytest.raises(ValueError, match=r"critic-checklist.yaml: item 'a'.*'Nope'"):
        load_checklist(path, SECTIONS)


def test_load_checklist_rejects_duplicate_id(tmp_path: Path) -> None:
    item = ITEM.format(id="a", section="Rhythm")
    path = _write(tmp_path, _items(item, item))
    with pytest.raises(ValueError, match="duplicate id 'a'"):
        load_checklist(path, SECTIONS)


def test_load_checklist_rejects_bad_regex(tmp_path: Path) -> None:
    path = _write(tmp_path, _items(ITEM.format(id="a", section="Avoid") + "    patterns: ['(']\n"))
    with pytest.raises(ValueError, match="item 'a'.*pattern"):
        load_checklist(path, SECTIONS)


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ("    colour: red\n", "unknown field"),
        ("    allowed: -1\n", "allowed"),
        ("    allowed: true\n", "allowed"),
        ("    word_range: [20, 10]\n", "word_range"),
        ("    word_range: [1]\n", "word_range"),
        ("    max_paragraph_chars: 0\n", "max_paragraph_chars"),
        ("    patterns: 'x'\n", "patterns"),
    ],
)
def test_load_checklist_rejects_bad_fields(tmp_path: Path, extra: str, message: str) -> None:
    path = _write(tmp_path, _items(ITEM.format(id="a", section="Avoid") + extra))
    with pytest.raises(ValueError, match=message):
        load_checklist(path, SECTIONS)


def test_load_checklist_rejects_bad_severity(tmp_path: Path) -> None:
    body = _items(ITEM.format(id="a", section="Avoid")).replace("must", "maybe")
    with pytest.raises(ValueError, match="severity"):
        load_checklist(_write(tmp_path, body), SECTIONS)


def test_load_checklist_rejects_bad_id(tmp_path: Path) -> None:
    path = _write(tmp_path, _items(ITEM.format(id="Bad Id", section="Avoid")))
    with pytest.raises(ValueError, match="id"):
        load_checklist(path, SECTIONS)


def test_load_checklist_rejects_missing_required_field(tmp_path: Path) -> None:
    body = _items(ITEM.format(id="a", section="Avoid")).replace("    rule: r\n", "")
    with pytest.raises(ValueError, match="rule"):
        load_checklist(_write(tmp_path, body), SECTIONS)


@pytest.mark.parametrize(
    "body", ["", "items: []\nversion: 1\n", "version: 1\nitems: x\n", "- a\n", "version: x\n"]
)
def test_load_checklist_rejects_bad_shape(tmp_path: Path, body: str) -> None:
    with pytest.raises(ValueError, match=r"critic-checklist.yaml"):
        load_checklist(_write(tmp_path, body), SECTIONS)


def test_load_checklist_rejects_invalid_yaml(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="critic-checklist.yaml"):
        load_checklist(_write(tmp_path, "items: [\n"), SECTIONS)


def test_load_checklist_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not found"):
        load_checklist(tmp_path / "nope.yaml", SECTIONS)


def test_load_checklist_rejects_non_mapping_item(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="item #1 is not a mapping"):
        load_checklist(_write(tmp_path, "version: 1\nitems:\n  - just text\n"), SECTIONS)


def test_load_checklist_rejects_allowed_on_judgement_item(tmp_path: Path) -> None:
    path = _write(tmp_path, _items(ITEM.format(id="a", section="Avoid") + "    allowed: 2\n"))
    with pytest.raises(ValueError, match="'allowed' only applies"):
        load_checklist(path, SECTIONS)

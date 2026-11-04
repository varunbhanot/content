import yaml

from newsletter_machine.series_edit import edit_part

TEXT = """\
topic: evals
status: approved
parts:
- number: 1  # Varun: the free one
  title: Why evals
  status: drafted  # recorded by the machine
  draft: drafts/a.md
  url: null
  summary: ''
- number: 2
  title: Golden sets
  status: planned
  draft:
"""


def _part(text: str, index: int) -> dict[str, object]:
    parts = yaml.safe_load(text)["parts"]
    assert isinstance(parts, list)
    return dict(parts[index])


def test_edit_part_replaces_status_and_fields_and_keeps_comments() -> None:
    edited = edit_part(
        TEXT,
        1,
        statuses=("drafted", "published"),
        status="published",
        fields={"url": "https://example.com/p/1", "summary": "Demos lie: a claim."},
    )
    assert edited is not None
    assert "# Varun: the free one" in edited and "# recorded by the machine" in edited
    part = _part(edited, 0)
    assert part["status"] == "published"
    assert part["url"] == "https://example.com/p/1"
    assert part["summary"] == "Demos lie: a claim."
    assert _part(edited, 1) == _part(TEXT, 1)


def test_edit_part_inserts_missing_keys_after_status_in_order() -> None:
    edited = edit_part(
        TEXT,
        2,
        statuses=("planned",),
        status="drafted",
        fields={"draft": "drafts/b.md", "summary": "S #1", "teaser": "Next: x"},
    )
    assert edited is not None
    part = _part(edited, 1)
    assert part == {
        "number": 2,
        "title": "Golden sets",
        "status": "drafted",
        "draft": "drafts/b.md",
        "summary": "S #1",
        "teaser": "Next: x",
    }
    # draft already had a key (below status); the missing ones follow status
    assert list(part) == ["number", "title", "status", "summary", "teaser", "draft"]


def test_edit_part_keeps_a_quoted_value_with_a_hash_whole() -> None:
    text = TEXT.replace("summary: ''", "summary: 'a # b'  # note")
    edited = edit_part(text, 1, statuses=("drafted",), status="drafted", fields={"summary": "new"})
    assert edited is not None
    assert _part(edited, 0)["summary"] == "new"
    assert "# note" in edited


def test_edit_part_is_none_when_the_status_is_not_one_expected() -> None:
    assert edit_part(TEXT, 2, statuses=("drafted",), status="published", fields={}) is None


def test_edit_part_is_none_for_a_missing_part() -> None:
    assert edit_part(TEXT, 7, statuses=("planned",), status="drafted", fields={}) is None


def test_edit_part_keeps_trailing_comments_with_apostrophes() -> None:
    text = TEXT.replace("status: planned", "status: planned  # Varun's next pick").replace(
        "  draft:\n", "  draft: null  # don't forget\n"
    )
    edited = edit_part(text, 2, statuses=("planned",), status="drafted", fields={"draft": "d.md"})
    assert edited is not None
    assert "# Varun's next pick" in edited and "# don't forget" in edited
    assert _part(edited, 1)["draft"] == "d.md"


def test_edit_part_keeps_a_double_quoted_value_and_its_comment() -> None:
    text = TEXT.replace("url: null", 'url: "https://a.b/#x"  # it\'s live')
    edited = edit_part(
        text, 1, statuses=("drafted",), status="published", fields={"url": "https://c.d"}
    )
    assert edited is not None
    assert _part(edited, 0)["url"] == "https://c.d" and "# it's live" in edited


def test_edit_part_gives_up_on_a_key_whose_value_spans_lines() -> None:
    text = TEXT.replace("  summary: ''\n", '  summary: "old one\n    old two"\n')
    assert (
        edit_part(text, 1, statuses=("drafted",), status="drafted", fields={"summary": "n"}) is None
    )

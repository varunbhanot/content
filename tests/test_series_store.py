from pathlib import Path

import pytest
import yaml

from newsletter_machine.series import Series, SeriesPart, SourceRef
from newsletter_machine.series_store import (
    Approval,
    approved_slugs,
    check_approval,
    check_can_plan,
    declared_status,
    draft_location,
    draft_reference,
    load_series,
    mark_drafted,
    plan_publication,
    render_series_yaml,
    save_approval,
    save_publication,
    save_series,
    series_path,
)


def _part(number: int) -> SeriesPart:
    return SeriesPart(
        number=number,
        title=f"Title {number}: a colon",
        question=f"Question {number}?",
        brief=f"Brief {number}.",
        arc=("basic", "advanced"),
        access="free" if number == 1 else "paid",
        status="planned",
        sources=(SourceRef(title="Why — demos fail", url="https://example.com/a"),),
    )


def _series(status: str = "proposed") -> Series:
    return Series(topic="evals", status=status, parts=(_part(1), _part(2), _part(3)))  # type: ignore[arg-type]


def _approve(series_dir: Path, slug: str) -> Approval:
    approval = check_approval(series_dir, slug)
    save_approval(approval)
    return approval


def _save(series_dir: Path, slug: str, status: str = "proposed") -> Path:
    path = series_path(series_dir, slug)
    save_series(path, _series(status), slug)
    return path


def test_series_path_uses_slug(tmp_path: Path) -> None:
    assert series_path(tmp_path, "evals") == tmp_path / "evals.yaml"


@pytest.mark.parametrize("slug", ["Evals", "../evals", "a b", ""])
def test_series_path_rejects_bad_slug(tmp_path: Path, slug: str) -> None:
    with pytest.raises(ValueError, match="series name must be kebab-case"):
        series_path(tmp_path, slug)


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    path = _save(tmp_path / "series", "evals")

    assert load_series(path) == _series()


def test_rendered_yaml_has_header_and_keeps_unicode() -> None:
    text = render_series_yaml(_series(), "evals")

    assert text.startswith("# Series plan: evals.")
    assert "newsletter-machine series approve evals" in text
    assert "Why — demos fail" in text


def test_load_missing_file_hints_at_plan(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="series plan"):
        load_series(tmp_path / "evals.yaml")


def test_load_invalid_yaml_names_file(tmp_path: Path) -> None:
    path = tmp_path / "evals.yaml"
    path.write_text("topic: [unclosed\n", encoding="utf-8")

    with pytest.raises(ValueError, match=f"{path}: invalid YAML"):
        load_series(path)


def test_load_invalid_schema_names_file(tmp_path: Path) -> None:
    path = tmp_path / "evals.yaml"
    path.write_text("topic: evals\nstatus: maybe\nparts: []\n", encoding="utf-8")

    with pytest.raises(ValueError, match=str(path)):
        load_series(path)


def test_check_can_plan_allows_new_file(tmp_path: Path) -> None:
    check_can_plan(tmp_path / "evals.yaml", overwrite=False)


def test_check_can_plan_refuses_existing_proposed_without_overwrite(tmp_path: Path) -> None:
    path = _save(tmp_path, "evals")

    with pytest.raises(FileExistsError, match="--overwrite"):
        check_can_plan(path, overwrite=False)
    check_can_plan(path, overwrite=True)


@pytest.mark.parametrize("status", ["approved", "complete"])
def test_check_can_plan_never_replans_approved_series(tmp_path: Path, status: str) -> None:
    path = _save(tmp_path, "evals", status)

    for overwrite in (False, True):
        with pytest.raises(ValueError, match=f"is {status}"):
            check_can_plan(path, overwrite=overwrite)


def test_check_can_plan_refuses_folder(tmp_path: Path) -> None:
    (tmp_path / "evals.yaml").mkdir()

    with pytest.raises(IsADirectoryError):
        check_can_plan(tmp_path / "evals.yaml", overwrite=True)


def test_approve_changes_only_the_status_line(tmp_path: Path) -> None:
    path = _save(tmp_path, "evals")
    edited = path.read_text(encoding="utf-8").replace(
        "topic: evals", "topic: evals  # Varun: keep it practical"
    )
    path.write_text(edited, encoding="utf-8")

    result = _approve(tmp_path, "evals")

    assert result.text is not None
    assert result.series.status == "approved"
    text = path.read_text(encoding="utf-8")
    assert "# Varun: keep it practical" in text
    assert text == edited.replace("\nstatus: proposed\n", "\nstatus: approved\n")


def test_approve_falls_back_to_rewrite_for_unusual_status_line(tmp_path: Path) -> None:
    path = tmp_path / "evals.yaml"
    path.write_text(
        '{"topic": "evals", "status": "proposed", "parts": '
        '[{"number": 1, "title": "T", "question": "Q?", "brief": "B.", "arc": ["a", "b"], '
        '"access": "free", "status": "planned", "sources": []}]}\n',
        encoding="utf-8",
    )

    result = _approve(tmp_path, "evals")

    assert result.series.status == "approved"
    assert load_series(path).status == "approved"


def test_approve_is_idempotent(tmp_path: Path) -> None:
    path = _save(tmp_path, "evals", "approved")
    before = path.read_text(encoding="utf-8")

    result = _approve(tmp_path, "evals")

    assert result.text is None
    assert path.read_text(encoding="utf-8") == before


def test_approve_refuses_complete_series(tmp_path: Path) -> None:
    _save(tmp_path, "evals", "complete")

    with pytest.raises(ValueError, match="complete"):
        _approve(tmp_path, "evals")


def test_only_one_series_may_be_approved(tmp_path: Path) -> None:
    _save(tmp_path, "harness", "approved")
    path = _save(tmp_path, "evals")

    with pytest.raises(ValueError, match="harness is already the active series"):
        _approve(tmp_path, "evals")
    assert load_series(path).status == "proposed"


def test_approve_missing_series(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="series plan"):
        _approve(tmp_path, "evals")


def test_approved_slugs_scans_folder(tmp_path: Path) -> None:
    assert approved_slugs(tmp_path / "missing") == ()
    _save(tmp_path, "harness", "approved")
    _save(tmp_path, "evals")
    _save(tmp_path, "old", "complete")

    assert approved_slugs(tmp_path) == ("harness",)


def test_approved_slugs_reads_only_the_status_of_other_files(tmp_path: Path) -> None:
    (tmp_path / "draft.yaml").write_text("status: proposed\nparts: [\n", encoding="utf-8")
    (tmp_path / "harness.yaml").write_text("status: approved\nparts: [\n", encoding="utf-8")
    (tmp_path / "other.yaml").write_text("- a list\n", encoding="utf-8")

    assert approved_slugs(tmp_path) == ("harness",)


def test_half_edited_other_series_does_not_block_approval(tmp_path: Path) -> None:
    (tmp_path / "harness.yaml").write_text("topic: h\nstatus: proposed\n", encoding="utf-8")
    _save(tmp_path, "evals")

    assert _approve(tmp_path, "evals").series.status == "approved"


def test_approve_keeps_a_trailing_comment_on_the_status_line(tmp_path: Path) -> None:
    path = _save(tmp_path, "evals")
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("\nstatus: proposed\n", "\nstatus: proposed  # flip\n"))

    assert _approve(tmp_path, "evals").series.status == "approved"

    assert "\nstatus: approved  # flip\n" in path.read_text(encoding="utf-8")
    assert load_series(path).status == "approved"


def test_approved_slugs_skips_files_that_are_not_series(tmp_path: Path) -> None:
    _save(tmp_path, "harness", "approved")
    (tmp_path / ".tmp-abc.evals.yaml").write_text("", encoding="utf-8")
    (tmp_path / "Old_Evals.yaml").write_text("status: approved\n", encoding="utf-8")

    assert approved_slugs(tmp_path) == ("harness",)


def test_check_can_plan_overwrite_replaces_a_broken_proposed_file(tmp_path: Path) -> None:
    path = tmp_path / "evals.yaml"
    path.write_text("topic: evals\nstatus: proposed\nparts: [\n", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid YAML"):
        check_can_plan(path, overwrite=False)
    check_can_plan(path, overwrite=True)


def test_check_can_plan_never_replaces_a_broken_approved_file(tmp_path: Path) -> None:
    path = tmp_path / "evals.yaml"
    path.write_text("topic: evals\nstatus: approved\nparts: []\n", encoding="utf-8")

    with pytest.raises(ValueError, match="is approved"):
        check_can_plan(path, overwrite=True)


def test_check_can_plan_refuses_series_dir_that_is_a_file(tmp_path: Path) -> None:
    (tmp_path / "series").write_text("x", encoding="utf-8")

    with pytest.raises(NotADirectoryError):
        check_can_plan(tmp_path / "series" / "evals.yaml", overwrite=False)


def test_save_series_never_writes_a_file_that_would_not_load(tmp_path: Path) -> None:
    bad = SeriesPart(
        number=1,
        title="T",
        question="Q?",
        brief="B.",
        arc=("a", "b"),
        access="free",
        status="planned",
        sources=(SourceRef(title="t", url="not a url"),),
    )
    path = tmp_path / "evals.yaml"

    with pytest.raises(ValueError, match="source #1"):
        save_series(path, Series(topic="evals", status="proposed", parts=(bad,)), "evals")
    assert not path.exists()


@pytest.mark.parametrize(
    "text",
    [
        "topic: evals\nstatus: approved\nparts: [\n",  # approved, YAML syntax error
        "topic: evals\nstatus: 'complete'\nparts:\n  - [\n",
        "topic: [\n",  # status unreadable
    ],
)
def test_check_can_plan_never_replaces_a_broken_file_unless_proposed(
    tmp_path: Path, text: str
) -> None:
    path = tmp_path / "evals.yaml"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="only a proposed outline is re-planned"):
        check_can_plan(path, overwrite=True)


def test_declared_status_of_unreadable_file_is_none(tmp_path: Path) -> None:
    (tmp_path / "binary.yaml").write_bytes(b"\xff\xfe status: approved")

    assert declared_status(tmp_path / "binary.yaml") is None
    assert approved_slugs(tmp_path) == ()


def _approved_file(series_dir: Path) -> Path:
    path = _save(series_dir, "evals", status="approved")
    text = path.read_text().replace("- number: 2\n", "- number: 2  # Varun: keep this one short\n")
    path.write_text(text)
    return path


def test_mark_drafted_flips_one_part_and_keeps_comments(tmp_path: Path) -> None:
    path = _approved_file(tmp_path)
    assert mark_drafted(path, "evals", 2, "drafts/2026-11-04.md") is True
    text = path.read_text()
    assert "# Varun: keep this one short" in text
    series = load_series(path)
    assert [p.status for p in series.parts] == ["planned", "drafted", "planned"]
    assert series.parts[1].draft == "drafts/2026-11-04.md"
    assert series.parts[0].draft is None and series.parts[2].draft is None


def test_mark_drafted_quotes_an_odd_draft_path(tmp_path: Path) -> None:
    path = _approved_file(tmp_path)
    assert mark_drafted(path, "evals", 1, "drafts/a: b #1.md") is True
    assert load_series(path).parts[0].draft == "drafts/a: b #1.md"


def test_mark_drafted_rewrites_the_file_when_the_lines_are_written_another_way(
    tmp_path: Path,
) -> None:
    path = _save(tmp_path, "evals", status="approved")
    data = yaml.safe_load(path.read_text())
    path.write_text(yaml.safe_dump(data, default_flow_style=True))  # flow style: no part lines
    assert mark_drafted(path, "evals", 3, "drafts/x.md") is False
    series = load_series(path)
    assert series.parts[2].status == "drafted" and series.parts[2].draft == "drafts/x.md"
    assert path.read_text().startswith("# Series plan: evals.")


def test_mark_drafted_refuses_a_part_that_is_no_longer_planned(tmp_path: Path) -> None:
    path = _approved_file(tmp_path)
    mark_drafted(path, "evals", 1, "drafts/x.md")
    before = path.read_text()
    with pytest.raises(ValueError, match="Part 1 is drafted, not planned"):
        mark_drafted(path, "evals", 1, "drafts/y.md")
    assert path.read_text() == before


def test_mark_drafted_refuses_a_missing_part(tmp_path: Path) -> None:
    path = _approved_file(tmp_path)
    with pytest.raises(ValueError, match="no Part 9"):
        mark_drafted(path, "evals", 9, "drafts/x.md")


def test_mark_drafted_reports_an_invalid_file(tmp_path: Path) -> None:
    path = _approved_file(tmp_path)
    path.write_text("topic: [broken\n")
    with pytest.raises(ValueError, match="invalid YAML"):
        mark_drafted(path, "evals", 1, "drafts/x.md")


def test_mark_drafted_keeps_a_column_0_comment_inside_a_part(tmp_path: Path) -> None:
    path = _save(tmp_path, "evals", status="approved")
    text = path.read_text().replace(
        "  status: planned", "# TODO tighten this brief\n  status: planned", 1
    )
    path.write_text(text)
    assert mark_drafted(path, "evals", 1, "drafts/x.md") is True
    assert "# TODO tighten this brief" in path.read_text()
    assert load_series(path).parts[0].status == "drafted"


def test_mark_drafted_adds_a_missing_draft_key(tmp_path: Path) -> None:
    path = _approved_file(tmp_path)
    path.write_text(path.read_text().replace("  draft: null\n", "", 1))  # part 1 has no draft key
    assert mark_drafted(path, "evals", 1, "drafts/x.md") is True
    assert "# Varun: keep this one short" in path.read_text()
    assert load_series(path).parts[0].draft == "drafts/x.md"


def test_mark_drafted_rewrites_when_the_line_edit_would_not_parse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from newsletter_machine import series_store

    path = _approved_file(tmp_path)
    monkeypatch.setattr(series_store, "edit_part", lambda *a, **k: "topic: [broken\n")
    assert mark_drafted(path, "evals", 1, "drafts/x.md") is False
    assert load_series(path).parts[0].status == "drafted"


def test_mark_drafted_refuses_a_series_no_longer_approved(tmp_path: Path) -> None:
    path = _save(tmp_path, "evals", status="proposed")
    with pytest.raises(ValueError, match="now proposed, no longer approved"):
        mark_drafted(path, "evals", 1, "drafts/x.md")


def test_draft_reference_is_relative_to_the_folder_holding_series(tmp_path: Path) -> None:
    path = tmp_path / "series" / "evals.yaml"
    draft = tmp_path / "drafts" / "2026-11-04.md"
    assert draft_reference(path, draft) == "drafts/2026-11-04.md"
    assert draft_location(path, "drafts/2026-11-04.md") == draft.resolve()
    assert draft_location(path, str(draft)) == draft.resolve()  # absolute stays absolute


def test_draft_reference_falls_back_to_absolute_across_drives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from newsletter_machine import series_store

    def _no_relpath(*args: object) -> str:
        raise ValueError("path is on mount 'D:'")

    monkeypatch.setattr(series_store.os.path, "relpath", _no_relpath)
    draft = tmp_path / "d.md"
    assert draft_reference(tmp_path / "series" / "evals.yaml", draft) == draft.resolve().as_posix()


def test_mark_drafted_keeps_comments_when_draft_is_written_as_capital_null(tmp_path: Path) -> None:
    path = _approved_file(tmp_path)
    path.write_text(path.read_text().replace("  draft: null\n", "  draft: Null\n", 1))
    assert mark_drafted(path, "evals", 1, "drafts/x.md") is True


def test_mark_drafted_records_summary_and_teaser_and_keeps_comments(tmp_path: Path) -> None:
    path = _approved_file(tmp_path)
    summary, teaser = "Golden sets beat vibes: a claim.", "Next in this series: judges #3."
    assert mark_drafted(path, "evals", 2, "drafts/b.md", summary=summary, teaser=teaser) is True
    assert "# Varun: keep this one short" in path.read_text()
    part = load_series(path).parts[1]
    assert (part.status, part.draft, part.summary, part.teaser) == (
        "drafted",
        "drafts/b.md",
        summary,
        teaser,
    )


def test_mark_drafted_rewrites_a_block_scalar_summary(tmp_path: Path) -> None:
    path = _approved_file(tmp_path)
    text = path.read_text().replace("  summary: ''\n", "  summary: >-\n    old\n    text\n", 1)
    path.write_text(text)
    assert mark_drafted(path, "evals", 1, "drafts/a.md", summary="new") is False
    assert load_series(path).parts[0].summary == "new"


def _drafted_file(series_dir: Path) -> Path:
    path = _approved_file(series_dir)
    mark_drafted(path, "evals", 1, "drafts/a.md")
    return path


URL = "https://varunbhanot.substack.com/p/evals-part-1"


def test_publication_marks_a_drafted_part_published_and_keeps_comments(tmp_path: Path) -> None:
    path = _drafted_file(tmp_path)
    publication = plan_publication(tmp_path, "evals", 1, URL)
    assert publication.path == path and publication.changed
    assert save_publication(publication) is True
    assert "# Varun: keep this one short" in path.read_text()
    part = load_series(path).parts[0]
    assert (part.status, part.url, part.draft) == ("published", URL, "drafts/a.md")


def test_publication_re_records_a_published_url(tmp_path: Path) -> None:
    path = _drafted_file(tmp_path)
    save_publication(plan_publication(tmp_path, "evals", 1, "https://example.com/wrong"))
    save_publication(plan_publication(tmp_path, "evals", 1, URL))
    assert load_series(path).parts[0].url == URL


def test_publication_of_the_same_url_changes_nothing(tmp_path: Path) -> None:
    path = _drafted_file(tmp_path)
    save_publication(plan_publication(tmp_path, "evals", 1, URL))
    before = path.read_text()
    again = plan_publication(tmp_path, "evals", 1, f" {URL} ")
    assert not again.changed
    assert save_publication(again) is True
    assert path.read_text() == before


@pytest.mark.parametrize(
    "url",
    ["ftp://example.com/p", "example.com/p", "https://exa mple.com", "https://", "http:///p", ""],
)
def test_publication_refuses_a_bad_url(tmp_path: Path, url: str) -> None:
    _drafted_file(tmp_path)
    with pytest.raises(ValueError, match="http"):
        plan_publication(tmp_path, "evals", 1, url)


def test_publication_refuses_a_planned_part(tmp_path: Path) -> None:
    _drafted_file(tmp_path)
    with pytest.raises(ValueError, match="Part 2 is planned"):
        plan_publication(tmp_path, "evals", 2, URL)


def test_publication_refuses_a_missing_part(tmp_path: Path) -> None:
    _drafted_file(tmp_path)
    with pytest.raises(ValueError, match="no Part 4"):
        plan_publication(tmp_path, "evals", 4, URL)


def test_publication_rewrites_a_flow_style_file(tmp_path: Path) -> None:
    path = _drafted_file(tmp_path)
    path.write_text(yaml.safe_dump(yaml.safe_load(path.read_text()), default_flow_style=True))
    assert save_publication(plan_publication(tmp_path, "evals", 1, URL)) is False
    assert load_series(path).parts[0].status == "published"


def test_publication_refuses_a_part_changed_since_it_was_checked(tmp_path: Path) -> None:
    path = _drafted_file(tmp_path)
    publication = plan_publication(tmp_path, "evals", 1, URL)
    save_series(path, _series("approved"), "evals")  # Part 1 back to planned meanwhile
    with pytest.raises(ValueError, match="Part 1 is planned"):
        save_publication(publication)

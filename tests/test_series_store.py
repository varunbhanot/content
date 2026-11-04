from pathlib import Path

import pytest

from newsletter_machine.series import Series, SeriesPart, SourceRef
from newsletter_machine.series_store import (
    Approval,
    approved_slugs,
    check_approval,
    check_can_plan,
    declared_status,
    load_series,
    render_series_yaml,
    save_approval,
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

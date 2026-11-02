from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from newsletter_machine.ingest import check_out_dir, ingest_links, slugify, write_sources
from newsletter_machine.sources import InboxLink, SourceDoc

WHEN = datetime(2026, 11, 1, tzinfo=UTC)
PREVIOUS = "---\nurl: https://old.example.com\n---\n"
ARTICLE_HTML = (
    "<html><head><title>Post A</title></head><body><article><p>"
    + "Readable article body about agent reliability. " * 15
    + "</p></article></body></html>"
)


def _link(url: str, note: str = "") -> InboxLink:
    return InboxLink(url=url, note=note, subject="", received_at=WHEN)


def test_ingest_links_routes_articles_and_youtube() -> None:
    links = (_link("https://a.com/post", "note a"), _link("https://youtu.be/dQw4w9WgXcQ"))
    docs = ingest_links(
        links,
        fetch_html=lambda url: ARTICLE_HTML,
        fetch_transcript=lambda video_id: f"transcript {video_id}",
    )
    assert [(d.kind, d.status) for d in docs] == [("article", "ok"), ("youtube", "ok")]
    assert docs[0].note == "note a"
    assert docs[1].text == "transcript dQw4w9WgXcQ"


def test_ingest_links_records_unexpected_errors_without_aborting() -> None:
    def explode(url: str) -> str:
        raise RuntimeError("parser crashed")

    links = (_link("https://a.com/1"), _link("https://b.com/2"))
    docs = ingest_links(links, fetch_html=explode, fetch_transcript=lambda v: "")
    assert [d.status for d in docs] == ["failed", "failed"]
    assert "RuntimeError: parser crashed" in docs[0].detail


def test_ingest_links_empty_input_returns_empty_tuple() -> None:
    assert ingest_links((), fetch_html=lambda u: "", fetch_transcript=lambda v: "") == ()


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Why Agents Fail: A Field Guide!", "why-agents-fail-a-field-guide"),
        ("Café — naïve résumé", "cafe-naive-resume"),
        ("???", "source"),
        ("x" * 100, "x" * 60),
    ],
)
def test_slugify(title: str, expected: str) -> None:
    assert slugify(title) == expected


def _doc(title: str, status: str = "ok") -> SourceDoc:
    return SourceDoc(
        url=f"https://a.com/{title}",
        title=title,
        kind="article",
        status=status,  # type: ignore[arg-type]
        text=f"body of {title}",
        note="my note",
        detail="" if status == "ok" else "HTTP 403",
    )


def test_write_sources_writes_one_markdown_file_per_source(tmp_path: Path) -> None:
    out = tmp_path / "week"
    paths = write_sources((_doc("First Post"), _doc("Second", "failed")), out)
    assert [p.name for p in paths] == ["01-first-post.md", "02-second.md"]
    text = paths[0].read_text(encoding="utf-8")
    front, body = text.removeprefix("---\n").split("\n---\n", 1)
    meta = yaml.safe_load(front)
    assert meta == {
        "url": "https://a.com/First Post",
        "title": "First Post",
        "kind": "article",
        "status": "ok",
        "note": "my note",
        "detail": "",
    }
    assert body.strip() == "# First Post\n\nbody of First Post"


def test_write_sources_refuses_to_overwrite_previous_ingest_output(tmp_path: Path) -> None:
    (tmp_path / "01-old.md").write_text(PREVIOUS)
    with pytest.raises(FileExistsError, match="--overwrite"):
        write_sources((_doc("A"),), tmp_path)


def test_check_out_dir_fails_fast_on_previous_output(tmp_path: Path) -> None:
    (tmp_path / "03-old.md").write_text(PREVIOUS)
    with pytest.raises(FileExistsError, match="--overwrite"):
        check_out_dir(tmp_path, overwrite=False)
    check_out_dir(tmp_path, overwrite=True)
    check_out_dir(tmp_path / "missing", overwrite=False)


def test_write_sources_ignores_unrelated_markdown(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("keep me")
    write_sources((_doc("A"),), tmp_path)
    assert (tmp_path / "README.md").read_text() == "keep me"


def test_write_sources_overwrite_replaces_only_previous_ingest_output(tmp_path: Path) -> None:
    (tmp_path / "01-a.md").write_text(PREVIOUS)
    (tmp_path / "05-stale.md").write_text(PREVIOUS)
    (tmp_path / "README.md").write_text("keep")
    (tmp_path / "keep.txt").write_text("x")
    paths = write_sources((_doc("A"),), tmp_path, overwrite=True)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["01-a.md", "README.md", "keep.txt"]
    assert paths == (tmp_path / "01-a.md",)
    assert "body of A" in paths[0].read_text()


def test_write_sources_title_with_yaml_specials_round_trips_on_one_line(tmp_path: Path) -> None:
    (path,) = write_sources((_doc('Colon: "quoted" #hash\n---'),), tmp_path)
    front = path.read_text(encoding="utf-8").removeprefix("---\n").split("\n---\n", 1)[0]
    assert yaml.safe_load(front)["title"] == 'Colon: "quoted" #hash ---'


def test_overwrite_keeps_user_files_that_only_look_like_output(tmp_path: Path) -> None:
    (tmp_path / "2026-plan.md").write_text("# my plan\n")
    write_sources((_doc("A"),), tmp_path)
    write_sources((_doc("B"),), tmp_path, overwrite=True)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["01-b.md", "2026-plan.md"]


def test_check_out_dir_rejects_existing_regular_file(tmp_path: Path) -> None:
    target = tmp_path / "notes.md"
    target.write_text("x")
    with pytest.raises(NotADirectoryError, match="notes.md"):
        check_out_dir(target, overwrite=False)


def test_write_sources_never_replaces_a_user_file_with_the_same_name(tmp_path: Path) -> None:
    (tmp_path / "01-a.md").write_text("my own notes")
    with pytest.raises(FileExistsError, match="01-a.md"):
        write_sources((_doc("A"),), tmp_path, overwrite=True)
    assert (tmp_path / "01-a.md").read_text() == "my own notes"


def test_write_sources_leaves_previous_output_intact_when_a_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "01-old.md").write_text(PREVIOUS)
    real_write = Path.write_text
    calls = {"n": 0}

    def flaky_write(self: Path, data: str, *args: object, **kwargs: object) -> int:
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("No space left on device")
        return real_write(self, data, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "write_text", flaky_write)
    with pytest.raises(OSError, match="No space"):
        write_sources((_doc("A"), _doc("B")), tmp_path, overwrite=True)
    monkeypatch.undo()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["01-old.md"]
    assert (tmp_path / "01-old.md").read_text() == PREVIOUS

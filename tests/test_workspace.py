from deepagents.backends.utils import create_file_data

from newsletter_machine.sources import SourceDoc
from newsletter_machine.workspace import (
    DRAFTS_DIR,
    count_files,
    file_text,
    latest_version,
    seed_files,
    text_file,
    versioned,
)

DOC = SourceDoc(url="https://e.com/a", title="A post", kind="article", status="ok", text="Body.")


def test_seed_files_numbers_usable_sources_as_the_agents_do() -> None:
    failed = SourceDoc(url="https://e.com/b", title="B", kind="article", status="failed", text="")
    files = seed_files((failed, DOC))
    assert list(files) == ["/sources/01-a-post.md", "/sources/failed-1-b.md"]
    assert "Body." in str(files["/sources/01-a-post.md"]["content"])
    assert "status: failed" in str(files["/sources/failed-1-b.md"]["content"])


def test_file_text_reads_str_and_line_list_content() -> None:
    files = {"/a.md": text_file("hello"), "/b.md": {"content": ["one", "two"]}}
    assert file_text(files, "/a.md") == "hello"
    assert file_text(files, "/b.md") == "one\ntwo"
    assert file_text(files, "/missing.md") is None


def test_file_text_ignores_malformed_entries() -> None:
    assert file_text({"/a.md": "raw"}, "/a.md") is None
    assert file_text({"/a.md": {"content": 3}}, "/a.md") is None


def test_versioned_and_latest_version() -> None:
    assert versioned(DRAFTS_DIR, 2, "md") == "/drafts/v2.md"
    files = {
        "/drafts/v1.md": text_file("1"),
        "/drafts/v3.md": text_file("3"),
        "/drafts/v9.json": text_file("{}"),
        "/drafts/notes.md": text_file("x"),
        "/other/v7.md": text_file("x"),
    }
    assert latest_version(files, DRAFTS_DIR, "md") == 3
    assert latest_version({}, DRAFTS_DIR, "md") == 0


def test_count_files_counts_direct_children_only() -> None:
    files = {
        "/errors/writer-1.md": create_file_data("x"),
        "/errors/writer-2.md": create_file_data("x"),
        "/errors/critic-1.md": create_file_data("x"),
        "/errors-old/writer-3.md": create_file_data("x"),
    }
    assert count_files(files, "/errors", "writer-") == 2


def test_seed_files_keeps_failed_sources_with_the_same_title_apart() -> None:
    failed = SourceDoc(
        url="https://e.com/x", title="Week", kind="article", status="failed", text=""
    )
    other = SourceDoc(url="https://e.com/y", title="Week", kind="article", status="failed", text="")
    assert list(seed_files((failed, other))) == [
        "/sources/failed-1-week.md",
        "/sources/failed-2-week.md",
    ]

import json

from newsletter_machine.issue_output import NotesInput, normalise_sources, render_notes
from newsletter_machine.sources import SourceDoc
from newsletter_machine.workspace import text_file


def _doc(slug: str, status: str = "ok", title: str = "") -> SourceDoc:
    return SourceDoc(
        url=f"https://e.com/{slug}",
        title=title or slug.upper(),
        kind="article",
        status=status,  # type: ignore[arg-type]
        text="t",
        detail="HTTP 403" if status == "failed" else "",
    )


DOCS = (_doc("a"), _doc("b"), _doc("c", status="failed"), _doc("d", title="D [beta]"))
BODY = "# Title\n\nBody text."


def test_keeps_cited_ingested_sources_in_writer_order_with_ingested_titles() -> None:
    draft = (
        f"{BODY}\n\n## Sources\n\n- [Bee](https://e.com/b?utm_source=x)\n- [A](https://E.com/a)\n"
    )
    fix = normalise_sources(draft, DOCS)
    assert fix.draft == f"{BODY}\n\n## Sources\n\n- [B](https://e.com/b)\n- [A](https://e.com/a)\n"
    assert fix.dropped == ()


def test_drops_unknown_failed_and_duplicate_links() -> None:
    draft = (
        f"{BODY}\n\n## Sources\n\n- [A](https://e.com/a)\n- [Made up](https://x.com/fake)\n"
        "- [C](https://e.com/c)\n- [A again](https://e.com/a#frag)\n"
    )
    fix = normalise_sources(draft, DOCS)
    assert fix.draft.endswith("## Sources\n\n- [A](https://e.com/a)\n")
    assert fix.dropped == ("https://x.com/fake", "https://e.com/c")


def test_lists_every_usable_source_when_none_is_cited_or_section_missing() -> None:
    expected = "- [A](https://e.com/a)\n- [B](https://e.com/b)\n- [D \\[beta\\]](https://e.com/d)\n"
    assert normalise_sources(BODY, DOCS).draft == f"{BODY}\n\n## Sources\n\n{expected}"
    no_links = normalise_sources(f"{BODY}\n\n### Sources\n\nnone\n", DOCS)
    assert no_links.draft == f"{BODY}\n\n## Sources\n\n{expected}"


def _notes_files() -> dict[str, dict[str, str]]:
    summary = {"version": 1, "passed": 17, "failed": 2, "not_checked": 0}
    return {
        "/critiques/v1.json": text_file(json.dumps({**summary, "failed_items": ["x", "y"]})),
        "/critiques/v2.json": text_file("not json"),
        "/drafts/v1.md": text_file("d1"),
        "/drafts/v2.md": text_file("d2"),
        "/briefs/v2.md": text_file("Fix x first."),
        "/plan.md": text_file("Topic: evals"),
        "/research/notes.md": text_file("# Research notes\n\n## [1] A\n\nhttps://e.com/a\n\n- p"),
        "/errors/writer-3.md": text_file("RateLimitError: slow down"),
    }


def test_render_notes_has_run_log_sources_plan_brief_and_notes() -> None:
    notes = render_notes(
        NotesInput(
            draft_name="issue.md",
            final_version=2,
            files=_notes_files(),
            docs=DOCS,
            summary="Ready.",
            dropped=("https://x.com/fake",),
        )
    )
    assert notes.startswith("# Editor notes: issue.md\n\nFinal draft: v2.")
    assert "## Editor's summary\n\nReady." in notes
    assert "- Draft v1: 17 passed, 2 failed (`x`, `y`), 0 not checked" in notes
    assert "- Draft v2: no critique summary" in notes
    assert "- writer-3 failed: RateLimitError: slow down" in notes
    assert "- Skipped: C (https://e.com/c): HTTP 403" in notes
    assert "- Dropped from Sources (not an ingested source): https://x.com/fake" in notes
    assert "## Plan\n\nTopic: evals" in notes
    assert "## Final brief\n\nFix x first." in notes
    assert "### [1] A" in notes and "\n# Research notes" not in notes


def test_render_notes_marks_missing_parts() -> None:
    notes = render_notes(NotesInput("i.md", 1, {}, DOCS[:1], "", ()))
    assert "(no summary)" in notes and "(no plan written)" in notes
    assert "(no research notes)" in notes and "(no brief)" in notes


def test_matches_html_escaped_query_urls_the_writer_copied_from_source_tags() -> None:
    video = SourceDoc(
        url="https://www.youtube.com/watch?v=abcdefghijk&t=10s",
        title="Talk",
        kind="youtube",
        status="ok",
        text="t",
    )
    draft = (
        f"{BODY}\n\n## Sources\n\n- [Talk](https://www.youtube.com/watch?v=abcdefghijk&amp;t=10s)\n"
    )
    fix = normalise_sources(draft, (*DOCS, video))
    assert fix.draft.endswith(f"- [Talk]({video.url})\n")
    assert fix.dropped == ()


def test_keeps_text_the_writer_put_after_the_sources_list() -> None:
    draft = (
        f"{BODY}\n\n## Sources\n\n- [A](https://e.com/a)\n\n"
        "*See you next week.*\n\n[VARUN: sign off]\n"
    )
    fix = normalise_sources(draft, DOCS)
    tail = "*See you next week.*\n\n[VARUN: sign off]\n"
    assert fix.draft == f"{BODY}\n\n## Sources\n\n- [A](https://e.com/a)\n\n{tail}"


def test_keeps_the_tail_when_a_line_precedes_the_list() -> None:
    draft = (
        f"{BODY}\n\n## Sources\nWhat I read:\n- [A](https://e.com/a)\n\n"
        "Thanks for reading.\n\n[VARUN: add story]\n"
    )
    fix = normalise_sources(draft, DOCS)
    tail = "Thanks for reading.\n\n[VARUN: add story]\n"
    assert fix.draft == f"{BODY}\n\n## Sources\n\n- [A](https://e.com/a)\n\n{tail}"

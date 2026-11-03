import re

import pytest

from newsletter_machine.checklist import ChecklistItem
from newsletter_machine.checks import (
    body_without_sources,
    count_words,
    paragraphs,
    prose_words,
    run_mechanical,
)


def _item(**fields: object) -> ChecklistItem:
    base: dict[str, object] = {
        "id": "x",
        "section": "Avoid",
        "rule": "the rule",
        "check": "c",
        "severity": "must",
    }
    return ChecklistItem(**{**base, **fields})  # type: ignore[arg-type]


DRAFT = """# Title

Intro line with a [link](https://example.com/a-very-long-url).

## Sources

- [One](https://example.com/one)
"""


def test_body_without_sources_drops_sources_section() -> None:
    body = body_without_sources(DRAFT)
    assert "Intro line" in body
    assert "example.com/one" not in body


def test_body_without_sources_keeps_text_without_sources_heading() -> None:
    assert body_without_sources("just text") == "just text"


def test_count_words_ignores_markdown_and_urls() -> None:
    assert count_words("# Title\n\nIt's a [good link](https://x.com/a/b) — **bold**.") == 6


def test_paragraphs_skips_headings_code_tables_and_splits_lists() -> None:
    text = "# H\n\nPara one\ncontinues.\n\n- item a\n- item b\n\n```\ncode\n```\n\n| a | b |\n"
    assert paragraphs(text) == ("Para one continues.", "item a", "item b")


def test_paragraphs_keeps_blank_lines_inside_code_fences_out() -> None:
    text = "```\nx\n\ny\n```\n\nReal."
    assert paragraphs(text) == ("Real.",)


def test_pattern_hit_fails_with_quote_in_context() -> None:
    item = _item(patterns=(re.compile("—"),))
    result = run_mechanical(item, "# T\n\nThis works — mostly.\n")
    assert result.status == "fail"
    assert result.quotes == ("This works — mostly.",)
    assert result.checked_by == "code"
    assert result.fix


def test_pattern_hits_within_allowed_pass() -> None:
    item = _item(patterns=(re.compile(r"\bquietly\b", re.IGNORECASE),), allowed=1)
    assert run_mechanical(item, "It Quietly broke.").status == "pass"
    assert run_mechanical(item, "Quietly. Quietly.").status == "fail"


def test_pattern_in_sources_section_is_ignored() -> None:
    item = _item(patterns=(re.compile("game-chang"),))
    assert run_mechanical(item, "Body.\n\n## Sources\n\n- [game-changing](u)").status == "pass"


def test_long_quote_context_is_trimmed() -> None:
    item = _item(patterns=(re.compile("needle"),))
    text = "a " * 100 + "needle" + " b" * 100
    (quote,) = run_mechanical(item, text).quotes
    assert "needle" in quote
    assert len(quote) < 160


@pytest.mark.parametrize(("words", "status"), [(5, "fail"), (10, "pass"), (21, "fail")])
def test_word_range(words: int, status: str) -> None:
    item = _item(word_range=(10, 20))
    result = run_mechanical(item, " ".join(["word"] * words))
    assert result.status == status
    if status == "fail":
        assert f"{words} words" in result.quotes[0]


def test_long_paragraphs_are_hits_beyond_allowed() -> None:
    item = _item(max_paragraph_chars=20, allowed=1)
    long_para = "x" * 30
    assert run_mechanical(item, long_para).status == "pass"
    result = run_mechanical(item, f"{long_para}\n\n{long_para}")
    assert result.status == "fail"
    assert len(result.quotes) == 2
    assert "30 chars" in result.quotes[0]


def test_run_mechanical_rejects_judgement_item() -> None:
    with pytest.raises(ValueError, match="not a mechanical"):
        run_mechanical(_item(), "text")


def test_paragraph_directly_before_code_fence_is_kept() -> None:
    text = "Setup paragraph:\n```\ncode\n```\n\nAfter."
    assert paragraphs(text) == ("Setup paragraph:", "After.")


def test_paragraph_directly_under_heading_is_measured() -> None:
    text = "## Why it breaks\n" + "x" * 50 + "\n\nNext."
    assert paragraphs(text) == ("x" * 50, "Next.")


def test_wrapped_list_item_counts_as_one_paragraph() -> None:
    text = "- item one\n  continues here\n- item two"
    assert paragraphs(text) == ("item one continues here", "item two")


def test_count_words_treats_hyphenated_words_as_one_and_skips_bare_urls() -> None:
    assert count_words("demo-vs-production, end-to-end, see https://x.com/a-b") == 3


def test_failed_mechanical_fix_is_actionable_not_the_rule() -> None:
    item = _item(patterns=(re.compile("buried"),), max_paragraph_chars=10, word_range=(50, 60))
    result = run_mechanical(item, "It was buried deep in the text.")
    assert result.fix != item.rule
    assert "50 to 60 words" in result.fix
    assert "flagged wording" in result.fix
    assert "longer than 10 characters" in result.fix


def test_list_following_intro_line_is_split_from_it() -> None:
    text = "Three things break:\n- a\n- b"
    assert paragraphs(text) == ("Three things break:", "a", "b")


def test_patterns_ignore_link_targets_and_bare_urls() -> None:
    item = _item(patterns=(re.compile(r"\bburied\b"),))
    text = "See [this post](https://e.com/why-evals-get-buried) and https://x.com/buried."
    assert run_mechanical(item, text).status == "pass"


def test_paragraph_length_ignores_link_targets() -> None:
    item = _item(max_paragraph_chars=30)
    text = "A short [linked](https://example.com/" + "x" * 100 + ") line."
    assert run_mechanical(item, text).status == "pass"


def test_prose_words_excludes_title_markers_and_sources() -> None:
    draft = (
        "# Five word title here now\n\nOne two three.\n\n[VARUN: add a story]\n\n## Sources\n\n- x"
    )
    assert prose_words(draft) == 3


def test_word_range_uses_prose_words() -> None:
    item = _item(word_range=(3, 3))
    assert run_mechanical(item, "# Long title words\n\nOne two three.").status == "pass"

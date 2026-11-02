from datetime import UTC, datetime
from pathlib import Path

import pytest

from newsletter_machine.sources import (
    InboxLink,
    extract_urls,
    failed_doc,
    normalize_url,
    parse_since,
    read_links_file,
    youtube_video_id,
)

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


def test_extract_urls_strips_trailing_punctuation_and_dedupes() -> None:
    text = "See https://a.com/x. Also (https://b.com/y) and https://a.com/x again!"
    assert extract_urls(text) == ("https://a.com/x", "https://b.com/y")


def test_extract_urls_returns_empty_tuple_for_plain_text() -> None:
    assert extract_urls("no links here") == ()


def test_normalize_url_drops_tracking_params_and_fragment() -> None:
    url = "HTTPS://Example.COM/post?utm_source=x&id=3&fbclid=abc#section"
    assert normalize_url(url) == "https://example.com/post?id=3"


def test_normalize_url_keeps_plain_url_unchanged() -> None:
    assert normalize_url("https://example.com/a?b=1") == "https://example.com/a?b=1"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com/watch?v=dQw4w9WgXcQ&t=42s",
        "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ?si=abc",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
        "https://www.youtube.com/live/dQw4w9WgXcQ",
    ],
)
def test_youtube_video_id_recognises_url_forms(url: str) -> None:
    assert youtube_video_id(url) == "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=short",
        "https://www.youtube.com/channel/UCabc",
        "https://notyoutube.com/watch?v=dQw4w9WgXcQ",
    ],
)
def test_youtube_video_id_returns_none_for_non_video_urls(url: str) -> None:
    assert youtube_video_id(url) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("7d", datetime(2026, 10, 30, 12, 0, tzinfo=UTC)),
        ("24h", datetime(2026, 11, 5, 12, 0, tzinfo=UTC)),
        ("2w", datetime(2026, 10, 23, 12, 0, tzinfo=UTC)),
        ("2026-10-30", datetime(2026, 10, 30, tzinfo=UTC)),
    ],
)
def test_parse_since_accepts_durations_and_dates(value: str, expected: datetime) -> None:
    assert parse_since(value, NOW) == expected


@pytest.mark.parametrize("value", ["0d", "abc", "7m", "", "2026-13-01"])
def test_parse_since_rejects_bad_values(value: str) -> None:
    with pytest.raises(ValueError, match="since"):
        parse_since(value, NOW)


def test_read_links_file_parses_urls_notes_and_skips_comments(tmp_path: Path) -> None:
    path = tmp_path / "links.txt"
    path.write_text(
        "# this week\n"
        "https://a.com/x  great point on evals\n"
        "\n"
        "https://youtu.be/dQw4w9WgXcQ\n"
        "https://a.com/x?utm_source=dup\n"
    )
    links = read_links_file(path, NOW)
    assert [link.url for link in links] == ["https://a.com/x", "https://youtu.be/dQw4w9WgXcQ"]
    assert links[0].note == "great point on evals"
    assert links[1].note == ""
    assert links[0].received_at == NOW


def test_read_links_file_rejects_line_without_url(tmp_path: Path) -> None:
    path = tmp_path / "links.txt"
    path.write_text("not a url\n")
    with pytest.raises(ValueError, match="links.txt:1"):
        read_links_file(path, NOW)


def test_extract_urls_keeps_balanced_parentheses() -> None:
    text = (
        "see https://en.wikipedia.org/wiki/Python_(programming_language). and [x](https://a.com/y)"
    )
    assert extract_urls(text) == (
        "https://en.wikipedia.org/wiki/Python_(programming_language)",
        "https://a.com/y",
    )


def test_read_links_file_accepts_parentheses_and_keeps_url_as_written(tmp_path: Path) -> None:
    path = tmp_path / "links.txt"
    path.write_text(
        "https://en.wikipedia.org/wiki/Python_(programming_language)\n"
        "https://ex.com/p?ids=a,b&flag#frag\n"
    )
    assert [link.url for link in read_links_file(path, NOW)] == [
        "https://en.wikipedia.org/wiki/Python_(programming_language)",
        "https://ex.com/p?ids=a,b&flag#frag",
    ]


def test_parse_since_rejects_overflowing_duration() -> None:
    with pytest.raises(ValueError, match="since"):
        parse_since("999999999d", NOW)


def test_read_links_file_accepts_tab_separated_note(tmp_path: Path) -> None:
    path = tmp_path / "links.txt"
    path.write_text("https://a.com/x\tgreat read\n")
    (link,) = read_links_file(path, NOW)
    assert (link.url, link.note) == ("https://a.com/x", "great read")


def test_failed_doc_builds_consistent_failure_record() -> None:
    link = InboxLink(url="https://a.com", note="n", subject="", received_at=NOW)
    doc = failed_doc(link, "youtube", "boom")
    assert (doc.title, doc.kind, doc.status, doc.text, doc.note, doc.detail) == (
        "https://a.com",
        "youtube",
        "failed",
        "",
        "n",
        "boom",
    )

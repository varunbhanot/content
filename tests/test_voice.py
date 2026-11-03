from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest

from newsletter_machine.voice import load_style_guide, load_voice_corpus, style_guide_sections

REPO_VOICE = Path(__file__).resolve().parent.parent / "voice"


def test_load_voice_corpus_parses_front_matter(make_voice_dir: Callable[..., Path]) -> None:
    voice = make_voice_dir((("hand", "hand", "a", "2025-01-02"),))
    (sample,) = load_voice_corpus(voice)
    assert sample.title == "Title a"
    assert sample.date == date(2025, 1, 2)
    assert sample.words == 100
    assert sample.era == "hand"
    assert sample.url == "https://example.com/a"
    assert "Body text" in sample.body


def test_load_voice_corpus_filters_by_era(make_voice_dir: Callable[..., Path]) -> None:
    voice = make_voice_dir(
        (("hand", "hand", "a", "2025-01-02"), ("ai-assisted", "ai-assisted", "b", "2026-06-01"))
    )
    samples = load_voice_corpus(voice, era="hand")
    assert [s.era for s in samples] == ["hand"]


def test_load_voice_corpus_sorted_by_date(make_voice_dir: Callable[..., Path]) -> None:
    voice = make_voice_dir(
        (("hand", "hand", "late", "2025-09-01"), ("hand", "hand", "early", "2024-01-01"))
    )
    dates = [s.date for s in load_voice_corpus(voice)]
    assert dates == sorted(dates)


def test_load_voice_corpus_raises_on_missing_front_matter(
    make_voice_dir: Callable[..., Path],
) -> None:
    voice = make_voice_dir()
    (voice / "samples" / "hand" / "broken.md").write_text("no front matter")
    with pytest.raises(ValueError, match="broken.md"):
        load_voice_corpus(voice)


def test_load_voice_corpus_raises_on_era_folder_mismatch(
    make_voice_dir: Callable[..., Path],
) -> None:
    voice = make_voice_dir((("ai-assisted", "hand", "x", "2026-06-01"),))
    with pytest.raises(ValueError, match="era"):
        load_voice_corpus(voice)


def test_load_voice_corpus_returns_tuple(make_voice_dir: Callable[..., Path]) -> None:
    assert isinstance(load_voice_corpus(make_voice_dir()), tuple)


def test_real_corpus_has_13_hand_and_10_ai_assisted() -> None:
    assert len(load_voice_corpus(REPO_VOICE, era="hand")) == 13
    assert len(load_voice_corpus(REPO_VOICE, era="ai-assisted")) == 10


def _write_sample(voice: Path, name: str, front: str) -> None:
    text = f"---\n{front}\n---\n\nbody\n"
    (voice / "samples" / "hand" / name).write_text(text)


def test_load_voice_corpus_raises_on_malformed_yaml_naming_file(
    make_voice_dir: Callable[..., Path],
) -> None:
    voice = make_voice_dir()
    _write_sample(voice, "bad-yaml.md", 'title: "unclosed\nera: hand')
    with pytest.raises(ValueError, match="bad-yaml.md"):
        load_voice_corpus(voice)


def test_load_voice_corpus_raises_on_non_date_date(make_voice_dir: Callable[..., Path]) -> None:
    voice = make_voice_dir()
    front = 'title: t\ndate: "not a date"\nurl: u\nera: hand'
    _write_sample(voice, "bad-date.md", front)
    with pytest.raises(ValueError, match="bad-date.md.*date"):
        load_voice_corpus(voice)


def test_load_voice_corpus_raises_on_non_integer_words(
    make_voice_dir: Callable[..., Path],
) -> None:
    voice = make_voice_dir()
    front = "title: t\ndate: 2025-01-01\nurl: u\nwords: abc\nera: hand"
    _write_sample(voice, "bad-words.md", front)
    with pytest.raises(ValueError, match="bad-words.md.*words"):
        load_voice_corpus(voice)


def test_load_voice_corpus_raises_when_era_folder_missing(
    make_voice_dir: Callable[..., Path],
) -> None:
    voice = make_voice_dir()
    (voice / "samples" / "ai-assisted").rmdir()
    with pytest.raises(ValueError, match="ai-assisted"):
        load_voice_corpus(voice)


def test_load_style_guide_returns_body_without_front_matter(
    make_voice_dir: Callable[..., Path],
) -> None:
    voice = make_voice_dir()
    (voice / "style-guide.md").write_text("---\ntitle: g\n---\n\n# Guide\n\n## Rhythm\n\nShort.\n")
    assert load_style_guide(voice).startswith("# Guide")


def test_load_style_guide_raises_when_missing(make_voice_dir: Callable[..., Path]) -> None:
    with pytest.raises(ValueError, match="style-guide.md"):
        load_style_guide(make_voice_dir())


def test_style_guide_sections_lists_h2_titles() -> None:
    text = "# Top\n\n## Who's talking\n\ntext\n\n### Sub\n\n## Avoid  \n"
    assert style_guide_sections(text) == ("Who's talking", "Avoid")


def test_real_style_guide_has_seven_sections() -> None:
    sections = style_guide_sections(load_style_guide(REPO_VOICE))
    assert sections == (
        "Who's talking",
        "Openings",
        "Rhythm",
        "Devices",
        "Structure and length",
        "Closings",
        "Avoid",
    )

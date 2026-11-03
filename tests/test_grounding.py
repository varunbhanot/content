from collections.abc import Callable
from pathlib import Path

import pytest

from newsletter_machine.grounding import format_checklist, format_samples, load_grounding

REPO_VOICE = Path(__file__).resolve().parent.parent / "voice"


def test_load_grounding_uses_only_hand_written_samples() -> None:
    grounding = load_grounding(REPO_VOICE)
    assert len(grounding.samples) == 13
    assert {s.era for s in grounding.samples} == {"hand"}
    assert "## Avoid" in grounding.style_guide
    assert any(item.id == "no-em-dashes" for item in grounding.checklist.items)


def test_load_grounding_fails_without_checklist(make_voice_dir: Callable[..., Path]) -> None:
    voice = make_voice_dir((("hand", "hand", "a", "2025-01-02"),))
    (voice / "style-guide.md").write_text("---\nt: 1\n---\n## Avoid\n")
    with pytest.raises(ValueError, match="critic-checklist.yaml"):
        load_grounding(voice)


def test_load_grounding_fails_without_hand_samples(make_voice_dir: Callable[..., Path]) -> None:
    voice = make_voice_dir()
    (voice / "style-guide.md").write_text("---\nt: 1\n---\n## Avoid\n")
    with pytest.raises(ValueError, match="no hand-written samples"):
        load_grounding(voice)


def test_format_samples_wraps_posts_and_drops_image_lines() -> None:
    grounding = load_grounding(REPO_VOICE)
    text = format_samples(grounding.samples[:1])
    assert text.startswith('<post title="')
    assert "substackcdn.com/image" not in text
    assert text.rstrip().endswith("</post>")


def test_format_checklist_lists_id_section_and_rule() -> None:
    grounding = load_grounding(REPO_VOICE)
    text = format_checklist(grounding.checklist.items)
    assert "- id: no-em-dashes (section: Avoid; must)" in text
    assert "  Rule: " in text
    assert "  Check: " in text

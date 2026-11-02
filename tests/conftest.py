from collections.abc import Callable
from pathlib import Path

import pytest

SAMPLE_TEMPLATE = """---
title: "{title}"
subtitle: "sub"
date: {date}
url: https://example.com/{slug}
words: {words}
era: {era}
---

# {title}

Body text for {title}.
"""


@pytest.fixture
def make_voice_dir(tmp_path: Path) -> Callable[..., Path]:
    """Build a throwaway voice dir; returns its path."""

    def _make(samples: tuple[tuple[str, str, str, str], ...] = ()) -> Path:
        voice = tmp_path / "voice"
        (voice / "samples" / "hand").mkdir(parents=True)
        (voice / "samples" / "ai-assisted").mkdir(parents=True)
        for folder, era, slug, date in samples:
            text = SAMPLE_TEMPLATE.format(
                title=f"Title {slug}", date=date, slug=slug, words=100, era=era
            )
            (voice / "samples" / folder / f"{date}-{slug}.md").write_text(text)
        return voice

    return _make

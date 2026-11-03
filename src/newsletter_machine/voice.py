"""Loader for the voice corpus (hand-written vs AI-assisted posts)."""

import logging
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal, get_args

from newsletter_machine.frontmatter import split_front_matter
from newsletter_machine.validation import is_int

logger = logging.getLogger(__name__)

Era = Literal["hand", "ai-assisted"]
STYLE_GUIDE_FILE = "style-guide.md"
H2_PATTERN = re.compile(r"^## (.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class VoiceSample:
    title: str
    date: date
    url: str
    words: int | None
    era: Era
    path: Path
    body: str


def _parse_sample(path: Path, folder_era: Era) -> VoiceSample:
    meta, body = split_front_matter(path, path.read_text(encoding="utf-8"))
    if meta.get("era") != folder_era:
        raise ValueError(f"{path}: era {meta.get('era')!r} disagrees with folder {folder_era!r}")
    try:
        sample_date = meta["date"]
        words = meta.get("words")
        if not isinstance(sample_date, date):
            raise ValueError(f"{path}: 'date' must be a YYYY-MM-DD date, got {sample_date!r}")
        if words is not None and not is_int(words):
            raise ValueError(f"{path}: 'words' must be an integer, got {words!r}")
        return VoiceSample(
            title=str(meta["title"]),
            date=sample_date,
            url=str(meta["url"]),
            words=words,
            era=folder_era,
            path=path,
            body=body,
        )
    except KeyError as exc:
        raise ValueError(f"{path}: front-matter missing {exc.args[0]!r}") from exc


def load_voice_corpus(voice_dir: Path, era: Era | None = None) -> tuple[VoiceSample, ...]:
    """Load samples sorted by date, optionally restricted to one era."""
    eras = (era,) if era else get_args(Era)
    for folder_era in eras:
        if not (voice_dir / "samples" / folder_era).is_dir():
            raise ValueError(f"Voice corpus folder missing: {voice_dir}/samples/{folder_era}")
    samples = [
        _parse_sample(path, folder_era)
        for folder_era in eras
        for path in sorted((voice_dir / "samples" / folder_era).glob("*.md"))
    ]
    return tuple(sorted(samples, key=lambda s: s.date))


def load_style_guide(voice_dir: Path) -> str:
    """The approved style guide's body (front-matter dropped)."""
    path = voice_dir / STYLE_GUIDE_FILE
    if not path.is_file():
        raise ValueError(f"Style guide not found: {path}")
    _, body = split_front_matter(path, path.read_text(encoding="utf-8"))
    return body


def style_guide_sections(text: str) -> tuple[str, ...]:
    """H2 section titles, in order; checklist items cite these."""
    return tuple(match.group(1) for match in H2_PATTERN.finditer(text))

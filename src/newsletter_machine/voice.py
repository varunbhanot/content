"""Loader for the voice corpus (hand-written vs AI-assisted posts)."""

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal, get_args

import yaml

logger = logging.getLogger(__name__)

Era = Literal["hand", "ai-assisted"]
FRONT_MATTER_DELIMITER = "---"


@dataclass(frozen=True)
class VoiceSample:
    title: str
    date: date
    url: str
    words: int | None
    era: Era
    path: Path
    body: str


def _split_front_matter(path: Path, text: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONT_MATTER_DELIMITER:
        raise ValueError(f"{path}: missing front-matter")
    try:
        end = next(
            i for i, line in enumerate(lines[1:], start=1) if line.strip() == FRONT_MATTER_DELIMITER
        )
    except StopIteration:
        raise ValueError(f"{path}: unterminated front-matter") from None
    meta = yaml.safe_load("\n".join(lines[1:end]))
    if not isinstance(meta, dict):
        raise ValueError(f"{path}: front-matter is not a mapping")
    return meta, "\n".join(lines[end + 1 :]).lstrip("\n")


def _parse_sample(path: Path, folder_era: Era) -> VoiceSample:
    meta, body = _split_front_matter(path, path.read_text(encoding="utf-8"))
    if meta.get("era") != folder_era:
        raise ValueError(f"{path}: era {meta.get('era')!r} disagrees with folder {folder_era!r}")
    try:
        return VoiceSample(
            title=str(meta["title"]),
            date=meta["date"],
            url=str(meta["url"]),
            words=meta.get("words"),
            era=folder_era,
            path=path,
            body=body,
        )
    except KeyError as exc:
        raise ValueError(f"{path}: front-matter missing {exc.args[0]!r}") from exc


def load_voice_corpus(voice_dir: Path, era: Era | None = None) -> tuple[VoiceSample, ...]:
    """Load samples sorted by date, optionally restricted to one era."""
    eras = (era,) if era else get_args(Era)
    samples = [
        _parse_sample(path, folder_era)
        for folder_era in eras
        for path in sorted((voice_dir / "samples" / folder_era).glob("*.md"))
    ]
    return tuple(sorted(samples, key=lambda s: s.date))

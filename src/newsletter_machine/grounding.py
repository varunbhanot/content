"""Voice grounding shared by writer and critic: style guide, hand-written posts, checklist."""

import html
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from newsletter_machine.checklist import CHECKLIST_FILE, Checklist, ChecklistItem, load_checklist
from newsletter_machine.voice import (
    VoiceSample,
    load_style_guide,
    load_voice_corpus,
    style_guide_sections,
)

IMAGE_LINE = re.compile(r"^\s*\[?!\[")


@dataclass(frozen=True)
class Grounding:
    style_guide: str
    samples: tuple[VoiceSample, ...]
    checklist: Checklist


def load_grounding(voice_dir: Path) -> Grounding:
    """Hand-written posts only: AI-assisted posts are not Varun's voice (voice/README.md)."""
    style_guide = load_style_guide(voice_dir)
    samples = load_voice_corpus(voice_dir, era="hand")
    if not samples:
        raise ValueError(f"{voice_dir}/samples/hand has no hand-written samples to ground on.")
    checklist = load_checklist(voice_dir / CHECKLIST_FILE, style_guide_sections(style_guide))
    return Grounding(style_guide=style_guide, samples=samples, checklist=checklist)


def _without_images(body: str) -> str:
    """Image links are long CDN URLs that cost tokens and carry no voice."""
    return "\n".join(line for line in body.splitlines() if not IMAGE_LINE.match(line))


def format_samples(samples: Iterable[VoiceSample]) -> str:
    return "\n\n".join(
        f'<post title="{html.escape(s.title)}" date="{s.date.isoformat()}">\n'
        f"{_without_images(s.body).strip()}\n</post>"
        for s in samples
    )


def format_checklist(items: Iterable[ChecklistItem]) -> str:
    return "\n".join(
        f"- id: {item.id} (section: {item.section}; {item.severity})\n"
        f"  Rule: {item.rule}\n  Check: {item.check}"
        for item in items
    )

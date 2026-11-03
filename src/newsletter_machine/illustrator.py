"""Illustrator sub-agent: picks the visuals an issue needs, draws them, places them.

One model call returns structured specs (kind, format, animation, anchor, code); code then
checks every visual (``visuals.py``), drops what fails, names files by index (never by model
text) and inserts each one after its anchor paragraph. Nothing here writes to disk except
``write_visuals``, which the CLI calls with the draft's ``<stem>.images/`` folder.
"""

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from deepagents import CompiledSubAgent
from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

from newsletter_machine.agent import AgentOutputError
from newsletter_machine.prompts import Prompt, load_prompt, render
from newsletter_machine.sources import SourceDoc
from newsletter_machine.visuals import (
    VisualError,
    check_chart_numbers,
    check_mermaid,
    place_visuals,
    plain_text,
    sanitise_svg,
)
from newsletter_machine.writer import format_sources, neutralise_tags, usable_sources

logger = logging.getLogger(__name__)

ILLUSTRATOR_NAME = "illustrator"
ILLUSTRATOR_DESCRIPTION = "Picks, draws and places the visuals for a finished draft."
FILE_PREFIX = "visual"
CAPTION_LIMIT = 200
NOTE_LIMIT = 400
PROMPT_LIMIT = 1_500


class VisualSpec(BaseModel):
    """One visual the model proposes (the structured-output schema)."""

    purpose: str = Field(description="Why this visual earns its place, in one line.")
    anchor: str = Field(description="Exact 5-12 word quote from the paragraph it follows.")
    kind: Literal["diagram", "chart", "illustration"]
    format: Literal["svg", "mermaid", "prompt-only"]
    animated: bool = Field(description="True only when the point is motion or order.")
    animation_reason: str = Field(description="One line: why it is or is not animated.")
    alt: str = Field(description="One sentence for screen readers.")
    caption: str = Field(description="One short line saying what to notice.")
    code: str = Field(description="SVG or Mermaid source, or an image prompt (prompt-only).")


class IllustratorOutput(BaseModel):
    visuals: list[VisualSpec] = Field(default_factory=list)
    skipped: str = Field(default="", description="Why there are no (or few) visuals.")


@dataclass(frozen=True)
class Visual:
    number: int  # final number: files are visual-1, visual-2... with no gaps
    proposal: int  # its position in the model's list (what rejections refer to)
    spec: VisualSpec
    path: str | None  # file name inside the images folder; None for prompt-only
    content: str  # cleaned SVG, Mermaid source, or the image prompt
    animated: bool  # what the file actually does, not what the model claimed
    removed: tuple[str, ...] = ()


@dataclass(frozen=True)
class Illustration:
    draft: str
    visuals: tuple[Visual, ...]
    rejected: tuple[tuple[int, str], ...]  # (proposal number, reason)
    skipped: str = ""


def illustrator_system_prompt(max_visuals: int, prompt: Prompt | None = None) -> str:
    return render(prompt or load_prompt(ILLUSTRATOR_NAME), max_visuals=str(max_visuals))


def build_illustrator(model: BaseChatModel, system_prompt: str) -> CompiledSubAgent:
    """A tool-less agent with structured output, built like the voice critic."""
    runnable = create_agent(
        model,
        tools=[],
        system_prompt=system_prompt,
        response_format=IllustratorOutput,
        name=ILLUSTRATOR_NAME,
    )
    return CompiledSubAgent(
        name=ILLUSTRATOR_NAME, description=ILLUSTRATOR_DESCRIPTION, runnable=runnable
    )


def illustrator_task(draft: str, docs: Iterable[SourceDoc]) -> str:
    return (
        f"<draft>\n{neutralise_tags(draft)}\n</draft>\n\nSources the draft was written from:\n\n"
        + format_sources(docs)
    )


def _one_line(text: str, limit: int = NOTE_LIMIT) -> str:
    return plain_text(text, limit)


def _file_name(number: int, spec: VisualSpec) -> str | None:
    ext = {"svg": "svg", "mermaid": "mmd"}.get(spec.format)
    return f"{FILE_PREFIX}-{number}.{ext}" if ext else None


def _build(proposal: int, spec: VisualSpec, sources: str) -> Visual:
    """Check one spec and turn it into a file; raises ``VisualError`` when it fails."""
    if spec.format == "prompt-only":
        if not spec.code.strip():
            raise VisualError("Empty image prompt.")
        return Visual(0, proposal, spec, None, spec.code.strip(), animated=False)
    if spec.format == "mermaid":
        return Visual(0, proposal, spec, None, check_mermaid(spec.code), animated=False)
    clean = sanitise_svg(spec.code)
    if spec.kind == "chart":
        check_chart_numbers(clean.svg, sources)
    return Visual(0, proposal, spec, None, clean.svg, clean.animated, clean.removed)


def _numbered(visuals: Sequence[Visual]) -> list[Visual]:
    return [
        replace(v, number=n, path=_file_name(n, v.spec)) for n, v in enumerate(visuals, start=1)
    ]


def _block(visual: Visual, image_dir: str) -> str:
    caption = plain_text(visual.spec.caption, CAPTION_LIMIT)
    if visual.path is None:
        return f"[VARUN: add image: {caption}]"
    if visual.path.endswith(".mmd"):  # check_mermaid refused fences, so this cannot break out
        return f"```mermaid\n{visual.content}\n```\n\n*{caption}*"
    alt = plain_text(visual.spec.alt, CAPTION_LIMIT)
    return f"![{alt}]({quote(image_dir)}/{visual.path})\n\n*{caption}*"


def _checked(
    specs: Sequence[VisualSpec], sources: str, max_visuals: int
) -> tuple[list[Visual], list[tuple[int, str]]]:
    built: list[Visual] = []
    rejected: list[tuple[int, str]] = []
    for proposal, spec in enumerate(specs, start=1):
        if len(built) >= max_visuals:
            rejected.append((proposal, f"over the cap of {max_visuals} visuals"))
            continue
        try:
            built.append(_build(proposal, spec, sources))
        except VisualError as exc:
            rejected.append((proposal, str(exc)))
    return built, rejected


def _placed(draft: str, visuals: Sequence[Visual], image_dir: str) -> tuple[str, set[str]]:
    items = [(str(v.proposal), v.spec.anchor, _block(v, image_dir)) for v in visuals]
    placement = place_visuals(draft, items)
    return placement.draft, set(placement.unplaced)


def illustrate(
    illustrator: CompiledSubAgent,
    draft: str,
    docs: Sequence[SourceDoc],
    *,
    max_visuals: int,
    image_dir: str,
) -> Illustration:
    """Run the illustrator once on ``draft``; returns the draft with visuals placed."""
    logger.info("Illustrator reading a %d-character draft", len(draft))
    task = illustrator_task(draft, docs)
    result = illustrator["runnable"].invoke({"messages": [{"role": "user", "content": task}]})
    output = result.get("structured_response")
    if not isinstance(output, IllustratorOutput):
        raise AgentOutputError("The illustrator did not return structured visuals.")
    sources = "\n".join(doc.text for doc in usable_sources(docs))
    built, rejected = _checked(output.visuals, sources, max_visuals)
    _, unplaced = _placed(draft, _numbered(built), image_dir)  # find anchors first...
    rejected += [
        (v.proposal, "anchor not found in the draft body")
        for v in built
        if str(v.proposal) in unplaced
    ]
    kept = _numbered([v for v in built if str(v.proposal) not in unplaced])
    placed, _ = _placed(draft, kept, image_dir)  # ...then place with gap-free numbers
    rejected.sort()
    return Illustration(placed, tuple(kept), tuple(rejected), output.skipped.strip())


def write_visuals(illustration: Illustration, folder: Path) -> tuple[Path, ...]:
    """Write every visual that has a file into ``folder`` (created if needed)."""
    files = [v for v in illustration.visuals if v.path is not None]
    if not files:
        return ()
    folder.mkdir(exist_ok=True)
    written = []
    for visual in files:
        assert visual.path is not None
        target = folder / visual.path
        target.write_text(visual.content + "\n", encoding="utf-8")
        written.append(target)
    return tuple(written)


def _visual_line(visual: Visual) -> str:
    spec = visual.spec
    motion = "animated" if visual.animated else "static"
    where = visual.path or "prompt-only (no file)"
    lines = [
        f"- **{FILE_PREFIX}-{visual.number}** ({spec.kind}, {spec.format}, {motion}): {where}",
        f"  - Why: {_one_line(spec.purpose)}",
        f"  - Animation: {_one_line(spec.animation_reason)}",
        f'  - After: "{_one_line(spec.anchor)}"',
    ]
    if visual.animated:
        lines.append("  - Substack shows SVG animation as a still: export a GIF to keep motion.")
    if visual.removed:
        lines.append(f"  - Sanitising removed: {', '.join(visual.removed)}")
    if visual.path is None:
        lines.append(f"  - Image prompt: {_one_line(visual.content, PROMPT_LIMIT)}")
    return "\n".join(lines)


def render_visual_notes(illustration: Illustration) -> str:
    """The notes' Visuals section body."""
    lines = [_visual_line(v) for v in illustration.visuals] or ["- No visuals placed."]
    lines += [f"- Dropped proposal {n}: {_one_line(r)}" for n, r in illustration.rejected]
    if illustration.skipped:
        lines.append(f"- Illustrator: {_one_line(illustration.skipped)}")
    return "\n".join(lines)

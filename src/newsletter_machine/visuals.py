"""Checks and placement for the illustrator's visuals: pure functions, no model calls.

Model-written SVG is untrusted: it is parsed (no DTDs or entities), cut down to an allowlist
of drawing and SMIL animation elements, and stripped of event handlers, external links and
``url(...)`` styles. Mermaid is checked for a known diagram type and no ``click`` callbacks.
"""

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from newsletter_machine.checks import SOURCES_HEADING

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
MAX_SVG_BYTES = 200_000

DRAWING_TAGS = frozenset(
    {
        "svg", "g", "defs", "title", "desc", "symbol", "use", "a", "rect", "circle", "ellipse",
        "line", "polyline", "polygon", "path", "text", "tspan", "textPath", "marker",
        "linearGradient", "radialGradient", "stop", "clipPath", "mask", "pattern",
    }
)  # fmt: skip
ANIMATION_TAGS = frozenset({"animate", "animateTransform", "animateMotion", "set", "mpath"})
ALLOWED_TAGS = DRAWING_TAGS | ANIMATION_TAGS
LINK_ATTRS = frozenset({"href", f"{{{XLINK_NS}}}href"})
EXTERNAL_URL = re.compile(r"url\(\s*['\"]?\s*[^#'\"\s)]", re.IGNORECASE)
DROPPED_ATTRS = frozenset({"style", "base"})  # CSS can fetch via escapes; xml:base re-roots links
MAX_ELEMENTS = 2_000
MAX_DEPTH = 40
MAX_USES = 100  # <use> fan-out can exhaust a renderer well under the byte cap
FENCE = re.compile(r"^\s*```[\w-]*\s*\n(.*?)\n\s*```\s*$", re.DOTALL)
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")

MERMAID_TYPES = (
    "flowchart", "graph", "sequenceDiagram", "classDiagram", "stateDiagram", "stateDiagram-v2",
    "erDiagram", "journey", "gantt", "pie", "quadrantChart", "timeline", "mindmap",
    "xychart-beta", "block-beta",
)  # fmt: skip
MERMAID_CLICK = re.compile(r"\bclick\b", re.IGNORECASE)
MERMAID_FENCE = re.compile(r"^\s*(```|~~~)", re.MULTILINE)
URL_TEXT = re.compile(r"(?:https?://|www\.)\S*", re.IGNORECASE)
MARKDOWN_SPECIALS = re.compile(r"([\\`*_\[\]<>!&#|~{}()])")


class VisualError(ValueError):
    """A visual failed a check; the message says why (it goes into the notes)."""


@dataclass(frozen=True)
class CleanSvg:
    svg: str
    animated: bool
    removed: tuple[str, ...]  # what sanitising took out, e.g. "<script>", "onclick="


def unfence(raw: str) -> str:
    """Drop one Markdown code fence around ``raw`` if the model added it."""
    text = raw.strip()
    match = FENCE.match(text)
    return match.group(1).strip() if match else text


def _local(name: str) -> str:
    return name.rsplit("}", 1)[-1]


def _bad_attr(element: ET.Element, name: str, value: str) -> bool:
    local, lowered = _local(name).lower(), value.lower()
    if local.startswith("on") or local in DROPPED_ATTRS or "\\" in value:
        return True
    if name in LINK_ATTRS:
        return not value.strip().startswith("#")
    if _local(element.tag) in ANIMATION_TAGS and local in {"attributename", "values", "to"}:
        # SMIL may animate geometry and colour, never a link target or a style
        if "href" in lowered or "style" in lowered or "base" in lowered:
            return True
    return bool(EXTERNAL_URL.search(value)) or "javascript:" in lowered or "image-set" in lowered


def _allowed(child: ET.Element) -> bool:
    tag = child.tag
    return isinstance(tag, str) and tag.startswith(f"{{{SVG_NS}}}") and _local(tag) in ALLOWED_TAGS


def _check_size(root: ET.Element) -> None:
    elements = list(root.iter())
    if len(elements) > MAX_ELEMENTS:
        raise VisualError(f"SVG has over {MAX_ELEMENTS} elements.")
    if sum(1 for el in elements if _local(str(el.tag)) == "use") > MAX_USES:
        raise VisualError(f"SVG has over {MAX_USES} <use> elements.")

    def depth(el: ET.Element, level: int) -> None:
        if level > MAX_DEPTH:
            raise VisualError(f"SVG nests deeper than {MAX_DEPTH} levels.")
        for child in el:
            depth(child, level + 1)

    depth(root, 1)


def _clean(element: ET.Element, removed: list[str]) -> None:
    for child in list(element):
        if not _allowed(child):
            removed.append(f"<{_local(child.tag) if isinstance(child.tag, str) else 'node'}>")
            element.remove(child)
            continue
        _clean(child, removed)
    for name, value in list(element.attrib.items()):
        if _bad_attr(element, name, value):
            removed.append(f"{_local(name)}=")
            del element.attrib[name]


def _parse(text: str) -> ET.Element:
    if len(text.encode("utf-8")) > MAX_SVG_BYTES:
        raise VisualError(f"SVG is over {MAX_SVG_BYTES // 1000} KB.")
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise VisualError("SVG must not declare a DOCTYPE or entities.")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise VisualError(f"SVG is not well-formed XML: {exc}") from None
    if root.tag != f"{{{SVG_NS}}}svg":
        raise VisualError(f'The root element must be <svg xmlns="{SVG_NS}">.')
    return root


def sanitise_svg(raw: str) -> CleanSvg:
    """Parse and clean model-written SVG; raises ``VisualError`` when it is unusable."""
    root = _parse(unfence(raw))
    _check_size(root)
    removed: list[str] = []
    _clean(root, removed)
    animated = any(_local(el.tag) in ANIMATION_TAGS for el in root.iter())
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)
    svg = ET.tostring(root, encoding="unicode")
    return CleanSvg(svg=svg, animated=animated, removed=tuple(dict.fromkeys(removed)))


def check_mermaid(raw: str) -> str:
    """The Mermaid source without fences; raises when the type is unknown or it has clicks."""
    text = unfence(raw)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    first = next((ln for ln in lines if not ln.startswith("%%")), "")
    words = first.split()
    if not words or words[0] not in MERMAID_TYPES or len(lines) < 2:
        raise VisualError(f"Not a Mermaid diagram (first line {first[:40]!r}).")
    if MERMAID_CLICK.search(text):
        raise VisualError("Mermaid 'click' callbacks are not allowed.")
    if MERMAID_FENCE.search(text) or "%%{" in text:
        raise VisualError("Mermaid must not contain code fences or %%{ directives.")
    return text


def plain_text(text: str, limit: int) -> str:
    """Model text made safe for one line of Markdown: no links, HTML or markup, capped."""
    flat = URL_TEXT.sub("", " ".join(text.split())).strip()
    if len(flat) > limit:
        flat = flat[:limit].rsplit(" ", 1)[0] + "…"
    return MARKDOWN_SPECIALS.sub(r"\\\1", flat)


def _svg_text(svg: str) -> str:
    root = ET.fromstring(svg)
    return " ".join(
        "".join(el.itertext()) for el in root.iter() if _local(el.tag) in {"text", "title"}
    )


def check_chart_numbers(svg: str, sources: str) -> None:
    """Every number written in a chart's text must appear in the sources (no invented data)."""
    known = set(NUMBER.findall(sources))
    invented = [n for n in dict.fromkeys(NUMBER.findall(_svg_text(svg))) if n not in known]
    if invented:
        raise VisualError(f"Chart numbers not found in the sources: {', '.join(invented)}.")


# --- placement ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Placement:
    draft: str
    placed: tuple[str, ...]
    unplaced: tuple[str, ...]


INLINE_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
EMPHASIS = re.compile(r"[*_`]+")
QUOTES = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"})


def _squash(text: str) -> str:
    """Text as a reader sees it: links to their words, no emphasis, straight quotes, casefold."""
    rendered = EMPHASIS.sub("", INLINE_LINK.sub(r"\1", text)).translate(QUOTES)
    return " ".join(rendered.split()).casefold()


def _paragraphs(lines: Sequence[str]) -> list[tuple[int, str]]:
    """``(last line index, text)`` per prose paragraph, skipping fenced code."""
    found: list[tuple[int, str]] = []
    current: list[str] = []
    fenced = False
    for index, line in enumerate(lines):
        if line.lstrip().startswith(("```", "~~~")):
            if current and not fenced:  # prose right above a fence is still a paragraph
                found.append((index - 1, _squash(" ".join(current))))
            fenced, current = not fenced, []
            continue
        if fenced or not line.strip():
            continue
        current.append(line)
        if index + 1 == len(lines) or not lines[index + 1].strip():
            found.append((index, _squash(" ".join(current))))
            current = []
    return found


def place_visuals(draft: str, items: Iterable[tuple[str, str, str]]) -> Placement:
    """Insert each ``(id, anchor, block)`` after the first body paragraph holding ``anchor``.

    The Sources section and fenced code are never anchors; blocks for one paragraph keep
    their given order. Items whose anchor is not found are returned in ``unplaced``.
    """
    match = SOURCES_HEADING.search(draft)
    body, tail = (draft[: match.start()], draft[match.start() :]) if match else (draft, "")
    lines = body.rstrip("\n").split("\n")
    paragraphs = _paragraphs(lines)
    after: dict[int, list[str]] = {}
    placed: list[str] = []
    unplaced: list[str] = []
    for visual_id, anchor, block in items:
        needle = _squash(anchor)
        hit = next((end for end, text in paragraphs if needle and needle in text), None)
        if hit is None:
            unplaced.append(visual_id)
            continue
        after.setdefault(hit, []).append(block.strip())
        placed.append(visual_id)
    if not placed:
        return Placement(draft, (), tuple(unplaced))
    out: list[str] = []
    for index, line in enumerate(lines):
        out.append(line)
        for block in after.get(index, []):
            out += ["", block]
    rebuilt = "\n".join(out)
    rebuilt = f"{rebuilt}\n\n{tail}" if tail else f"{rebuilt}\n"
    return Placement(rebuilt, tuple(placed), tuple(unplaced))

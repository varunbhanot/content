"""The part of an approved series that ``issue --series`` drafts, and the context it carries.

Series context travels through the existing angle seam (``writer.angle_line``), so the editor,
researcher and writer all see the topic, the outline and this part's brief; from Part 2 on,
also what earlier parts said, linked and promised, and how to open and close.
"""

from pathlib import Path

from newsletter_machine.series import ARC_SEPARATOR, Series, SeriesPart
from newsletter_machine.writer import neutralise_tags

NO_SUMMARY = "(no summary recorded)"


def next_part(series: Series) -> SeriesPart | None:
    """The lowest-numbered ``planned`` part, or None when every part is drafted or published."""
    return next((part for part in series.parts if part.status == "planned"), None)


def check_draftable(series: Series, path: Path, slug: str) -> SeriesPart:
    """The part to draft; ``ValueError`` (a usage error) unless the series is approved and a
    planned part is left."""
    if series.status != "approved":
        raise ValueError(
            f"{path} is {series.status}; only an approved series is drafted. Check the outline, "
            f"then run: newsletter-machine series approve {slug}"
        )
    part = next_part(series)
    if part is None:
        raise ValueError(f"{path} has no planned part left: every part is drafted or published.")
    return part


def _outline_lines(series: Series, current: SeriesPart) -> list[str]:
    return [
        f"- Part {part.number}: {part.title}. {part.question}"
        + (" (this part)" if part.number == current.number else "")
        for part in series.parts
    ]


def previous_part(series: Series, part: SeriesPart) -> SeriesPart | None:
    return next((p for p in series.parts if p.number == part.number - 1), None)


def following_part(series: Series, part: SeriesPart) -> SeriesPart | None:
    return next((p for p in series.parts if p.number == part.number + 1), None)


def _earlier_lines(series: Series, part: SeriesPart) -> list[str]:
    """Parts before the previous one (which gets its own block)."""
    earlier = [p for p in series.parts if p.number < part.number - 1]
    if not earlier:
        return []
    return [
        "Earlier parts:",
        *(f"- Part {p.number}: {p.title}. {p.summary or NO_SUMMARY}" for p in earlier),
        "",
    ]


def _previous_lines(previous: SeriesPart) -> list[str]:
    n = previous.number
    lines = [
        f"Previous part (Part {n}):",
        f"- Title: {previous.title}",
        f"- URL: {previous.url or 'not published yet'}",
        f"- Summary: {previous.summary or NO_SUMMARY}",
    ]
    if previous.teaser:
        lines.append(f'- Its closing teaser promised: "{previous.teaser}"')
    link = (
        f"link its title to {previous.url}"
        if previous.url
        else f"it has no URL yet, so put `[VARUN: link Part {n} here once it is published]` "
        "on its own line after the opening paragraph"
    )
    opening = (
        f'Opening: start with a one-clause link back to Part {n} ("Last time we talked '
        f'about ..."); {link}. Keep the recap to one clause, then move on to this part.'
    )
    if previous.teaser:
        opening += " Deliver what that teaser promised."
    callbacks = "You may make brief callbacks to earlier parts by name where they help."
    return [*lines, "", opening, callbacks, ""]


def _closing_line(following: SeriesPart | None) -> str:
    if following is None:
        return (
            'Closing: this is the final part of the series, so do not add a "Next in this '
            'series" line.'
        )
    return (
        "Closing: end the article, just before the Sources list, with one line in italics "
        f'pointing to Part {following.number} ("{following.title}": {following.question}), '
        'starting "*Next in this series:".'
    )


def series_angle(series: Series, part: SeriesPart) -> str:
    """The angle text for one part; it reads after "Varun's angle: "."""
    previous = previous_part(series, part)
    continuity = [*_earlier_lines(series, part), *_previous_lines(previous)] if previous else []
    lines = [
        f"this issue is Part {part.number} of {len(series.parts)} of a series on "
        f"{series.topic}. Write this part only; other parts cover the rest of the outline.",
        "",
        "Series outline:",
        *_outline_lines(series, part),
        "",
        f"This part (Part {part.number}):",
        f"- Title: {part.title}",
        f"- Question: {part.question}",
        f"- Brief: {part.brief}",
        f"- Arc, basic to advanced: {ARC_SEPARATOR.join(part.arc)}",
        f"- Access: {part.access}",
        "",
        *continuity,
        "Answer this part's question and run the article from basic to advanced along its arc, "
        "so a reader can join the series at this part.",
        _closing_line(following_part(series, part)),
    ]
    return neutralise_tags("\n".join(lines))  # planner-written text sits beside <source> tags


def relevance_context(series: Series, part: SeriesPart) -> str:
    """What the relevance filter judges each source against: topic and outline."""
    lines = [f"Series topic: {series.topic}", "Outline:", *_outline_lines(series, part)]
    return neutralise_tags("\n".join(lines))


def series_label(slug: str, series: Series, part: SeriesPart) -> str:
    """One line naming the series and part, for the terminal, notes and critique."""
    return (
        f"Series '{slug}', Part {part.number} of {len(series.parts)}: {part.title} ({part.access})"
    )

"""Does this week's reading fit the next planned part? A deterministic rule over the part each
on-topic source best supports (reported by the relevance check, no extra model call).

Only planned parts and "fits no listed part" compete: a source that best supports a drafted
or published part is no reason to change what comes next.
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from newsletter_machine.relevance import NO_LISTED_PART, SourceFit
from newsletter_machine.series import Series, SeriesPart
from newsletter_machine.sources import normalize_url

logger = logging.getLogger(__name__)

# The next part is drafted when at least this many on-topic sources best support it; below
# that, the outline is revised only if another planned part (or a new topic) has at least this
# many and more than the next part, so one stray verdict never rewrites the outline.
MIN_FIT_SOURCES = 2


@dataclass(frozen=True)
class FitCheck:
    part: int  # the next planned part
    counts: Mapping[int, int]  # planned part number (or NO_LISTED_PART) -> sources
    total: int  # on-topic sources judged

    @property
    def others(self) -> dict[int, int]:
        return {n: c for n, c in self.counts.items() if n != self.part}

    @property
    def mismatch(self) -> bool:
        """True when the next part is thinly supported and something else is well supported."""
        mine = self.counts.get(self.part, 0)
        return mine < MIN_FIT_SOURCES <= max(self.others.values(), default=0)


def check_fit(series: Series, part: SeriesPart, fits: Sequence[SourceFit]) -> FitCheck:
    planned = [p.number for p in series.parts if p.status == "planned"]
    counts = dict.fromkeys([*planned, NO_LISTED_PART], 0)
    seen: set[str] = set()
    for fit in fits:
        url = normalize_url(fit.doc.url)
        if url in seen:  # a link saved twice is one source, one vote
            continue
        seen.add(url)
        if fit.part is None:
            logger.info("No part named for %s: not counted", fit.doc.url)
        elif fit.part in counts:
            counts[fit.part] += 1
        else:
            logger.info("%s fits Part %d (not planned): not counted", fit.doc.url, fit.part)
    return FitCheck(part=part.number, counts=counts, total=len(seen))


def _name(number: int) -> str:
    return "new topic" if number == NO_LISTED_PART else f"Part {number}"


def fit_line(check: FitCheck) -> str:
    """One terminal line: the next part's support, then any other part with sources."""
    mine = check.counts.get(check.part, 0)
    line = f"Fit: Part {check.part} has {mine} of {check.total} on-topic sources"
    others = [f"{_name(n)}: {c}" for n, c in check.others.items() if c]
    return f"{line}; {', '.join(others)}" if others else line

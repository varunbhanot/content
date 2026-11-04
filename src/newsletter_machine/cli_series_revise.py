"""Run a revision of a series outline and report it: shared by ``series revise`` and by
``issue --series`` when the week's sources do not fit the next planned part.

The revised outline is written in full (the planner reworks several parts at once, so a line
edit cannot keep comments); the previous file is kept as ``<slug>.yaml.bak`` first.
"""

import logging
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from langchain_core.runnables import Runnable

from newsletter_machine.cli_common import EXIT_ERROR
from newsletter_machine.config import ConfigError
from newsletter_machine.series import Series, format_outline
from newsletter_machine.series_revise import run_revision
from newsletter_machine.series_store import save_revision
from newsletter_machine.sources import SourceDoc

logger = logging.getLogger(__name__)

WRITE_ERRORS = (ConfigError, ValueError, KeyError, OSError)


@dataclass(frozen=True)
class RevisionJob:
    """A checked series and everything one revision needs (no model call made yet)."""

    slug: str
    path: Path
    series: Series  # as read before the run; the write refuses if the file changed
    docs: tuple[SourceDoc, ...]
    reviser: Runnable[Any, Any]
    today: date


def _report(job: RevisionJob, revised: Series, backup: Path) -> None:
    revision = revised.revisions[-1]
    print(
        f"Revised {job.path} (proposed, {len(revised.parts)} parts). Rewritten in full; the "
        f"previous file, with your comments, is at {backup}"
    )
    print(f"Reason: {revision.reason}")
    print("Changes:")
    for line in revision.changes:
        print(f"  - {line}")
    print()
    print(format_outline(revised, job.slug))


def _next_steps(job: RevisionJob, extra: Sequence[str]) -> None:
    print(
        f"Next: review {job.path} (edit it if you want), then run: newsletter-machine series "
        f"approve {job.slug}"
    )
    for line in extra:
        print(line)


def apply_revision(job: RevisionJob, next_steps: Sequence[str] = ()) -> int:
    """Run the reviser, write the revised outline (``proposed``) and print what changed.
    0 when written; 1 when the model failed or the file could not be written (left as was)."""
    try:
        revised = run_revision(job.reviser, job.series, job.docs, job.today, job.path)
    except Exception as exc:  # network/API failures surface as many types
        logger.debug("Revision failed", exc_info=True)
        print(f"Planner failed: {exc} ({job.path} not changed)", file=sys.stderr)
        return EXIT_ERROR
    try:
        backup = save_revision(job.path, job.slug, job.series, revised)
    except WRITE_ERRORS as exc:
        print(format_outline(revised, job.slug))  # keep the paid-for outline on screen
        print(f"Could not write the series: {exc} (outline not written)", file=sys.stderr)
        return EXIT_ERROR
    _report(job, revised, backup)
    _next_steps(job, next_steps)
    return 0

"""Series mode for ``newsletter-machine issue --series <slug>``.

Before any model call: load and check the series file and pick the next planned part. After
ingest: drop off-topic sources (listed in ``<stem>.parked.md``). After a fully successful run:
mark the part drafted. A failed run leaves the series file untouched.
"""

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable

from newsletter_machine.cli_common import EXIT_ERROR, write_reported
from newsletter_machine.drafting import check_target
from newsletter_machine.relevance import (
    Relevance,
    build_relevance_classifier,
    classify_sources,
    one_line,
    relevance_system_prompt,
    render_parked,
)
from newsletter_machine.series import Series, SeriesPart
from newsletter_machine.series_part import (
    check_draftable,
    relevance_context,
    series_angle,
    series_label,
)
from newsletter_machine.series_store import (
    DEFAULT_SERIES_DIR,
    draft_location,
    draft_reference,
    load_series,
    mark_drafted,
    series_path,
)
from newsletter_machine.sources import SourceDoc

logger = logging.getLogger(__name__)


def add_series_options(issue: Any, steer: Any) -> None:
    """``--series`` joins ``--angle`` in one mutually exclusive group (argparse exits 2)."""
    steer.add_argument("--series", metavar="SLUG", help="Draft the next planned part of a series")
    issue.add_argument(
        "--series-dir",
        type=Path,
        default=DEFAULT_SERIES_DIR,
        help=f"Folder of series files (default: {DEFAULT_SERIES_DIR})",
    )


@dataclass(frozen=True)
class SeriesTarget:
    """A checked series file and the part to draft (no model built yet)."""

    slug: str
    path: Path
    series: Series
    part: SeriesPart
    parked: Path  # where this run lists the sources it set aside


@dataclass(frozen=True)
class SeriesJob:
    target: SeriesTarget
    classifier: Runnable[Any, Any]

    @property
    def label(self) -> str:
        t = self.target
        return series_label(t.slug, t.series, t.part)

    @property
    def angle(self) -> str:
        return series_angle(self.target.series, self.target.part)


def _check_new_draft(series: Series, path: Path, out: Path) -> None:
    """A rerun on an earlier part's ``--out`` would draft the next part over that draft."""
    for part in series.parts:
        if part.draft and draft_location(path, part.draft) == out.resolve():
            raise ValueError(
                f"{out} is already Part {part.number}'s draft in {path} ({part.status}). Pick "
                f"another --out, or to redraft Part {part.number} set its status back to "
                "planned and empty its draft field."
            )


def series_target(args: argparse.Namespace, parked: Path) -> SeriesTarget | None:
    """The series to draft, checked before any model is built; None without ``--series``."""
    if args.series is None:
        return None
    path = series_path(args.series_dir, args.series)
    series = load_series(path)
    part = check_draftable(series, path, args.series)
    _check_new_draft(series, path, args.out)
    check_target(parked, overwrite=True)  # derived from the sources: a rerun rewrites it
    return SeriesTarget(args.series, path, series, part, parked)


def series_job(target: SeriesTarget, model: BaseChatModel) -> SeriesJob:
    return SeriesJob(target, build_relevance_classifier(model, relevance_system_prompt()))


def _print_relevance(relevance: Relevance) -> None:
    unchecked = f", {len(relevance.unchecked)} unchecked (kept)" if relevance.unchecked else ""
    print(f"Relevance: {relevance.on_topic} on-topic, {len(relevance.parked)} parked{unchecked}")
    for item in relevance.parked:
        print(f"  Parked: {item.doc.title} ({item.doc.url}): {one_line(item.reason)}")
    for item in relevance.unchecked:
        print(f"  Unchecked (kept): {item.doc.title} ({item.doc.url}): {one_line(item.reason)}")


def filter_sources(
    job: SeriesJob, docs: tuple[SourceDoc, ...], sources_dir: Path
) -> Relevance | None:
    """Classify, print and write the parked list; None (exit 1) when the list cannot be
    written or no source could be checked."""
    t = job.target
    relevance = classify_sources(job.classifier, docs, relevance_context(t.series, t.part))
    _print_relevance(relevance)
    if not write_reported(
        t.parked, render_parked(relevance.parked, job.label, sources_dir), "parked list"
    ):
        return None
    print(f"Parked list -> {t.parked}")
    if relevance.all_unchecked:  # e.g. a wrong NM_RELEVANCE_MODEL: never draft unfiltered
        print(
            "The relevance check failed for every source, so nothing was filtered or drafted. "
            "Check NM_RELEVANCE_MODEL and rerun.",
            file=sys.stderr,
        )
        return None
    return relevance


def finish_series(job: SeriesJob, code: int, draft: Path) -> int:
    """Mark the part drafted after a fully successful run; leave the file alone otherwise."""
    t = job.target
    if code:
        print(
            f"Series file not updated: Part {t.part.number} stays planned in {t.path}.",
            file=sys.stderr,
        )
        return code
    try:
        kept = mark_drafted(t.path, t.slug, t.part.number, draft_reference(t.path, draft))
    except (ValueError, OSError) as exc:
        logger.debug("Series update failed", exc_info=True)
        print(
            f"Could not update {t.path}: {exc} (draft kept at {draft}; mark Part "
            f"{t.part.number} drafted by hand)",
            file=sys.stderr,
        )
        return EXIT_ERROR
    rewritten = "" if kept else " (file rewritten in full: comments were not kept)"
    print(f"Marked Part {t.part.number} drafted in {t.path}{rewritten}")
    return 0

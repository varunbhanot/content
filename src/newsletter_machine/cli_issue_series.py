"""Series mode for ``newsletter-machine issue --series <slug>``.

Before any model call: load and check the series file, pick the next planned part and add the
series checks to the critic checklist. After ingest: drop off-topic sources (listed in
``<stem>.parked.md``). When the on-topic sources fit another planned part (or a new topic)
better than the next one, revise the outline instead of drafting (unless ``--keep-outline``):
the file goes back to ``proposed`` for Varun to approve again. After a fully successful run:
mark the part drafted with its one-line summary and closing teaser. A failed run leaves the
series file untouched.
"""

import argparse
import logging
import shlex
import sys
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable

from newsletter_machine.cli_common import EXIT_ERROR, write_reported
from newsletter_machine.cli_series_revise import RevisionJob, apply_revision
from newsletter_machine.config import issue_timezone
from newsletter_machine.drafting import check_target
from newsletter_machine.grounding import Grounding
from newsletter_machine.planner import MAX_PLANNER_SOURCES, dedupe_sources, planner_system_prompt
from newsletter_machine.relevance import (
    Relevance,
    build_relevance_classifier,
    classify_sources,
    one_line,
    relevance_system_prompt,
    render_parked,
)
from newsletter_machine.series import Series, SeriesPart
from newsletter_machine.series_checks import load_series_checks, series_checklist
from newsletter_machine.series_fit import check_fit, fit_line
from newsletter_machine.series_part import (
    check_draftable,
    continuity_facts,
    following_part,
    previous_part,
    relevance_context,
    series_angle,
    series_label,
)
from newsletter_machine.series_revise import build_reviser, revisable_outline
from newsletter_machine.series_store import (
    DEFAULT_SERIES_DIR,
    check_markable,
    draft_location,
    draft_reference,
    load_series,
    mark_drafted,
    series_path,
)
from newsletter_machine.series_summary import (
    build_summariser,
    extract_teaser,
    summarise_part,
    summary_system_prompt,
)
from newsletter_machine.sources import SourceDoc
from newsletter_machine.voice import style_guide_sections
from newsletter_machine.writer import usable_sources

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
    issue.add_argument(
        "--keep-outline",
        action="store_true",
        help="With --series: draft the next planned part even if the week fits another better",
    )


@dataclass(frozen=True)
class SeriesTarget:
    """A checked series file and the part to draft (no model built yet)."""

    slug: str
    path: Path
    series: Series
    part: SeriesPart
    parked: Path  # where this run lists the sources it set aside
    keep_outline: bool = False  # draft the planned part even when the week fits another


@dataclass(frozen=True)
class SeriesJob:
    target: SeriesTarget
    classifier: Runnable[Any, Any]
    summariser: Runnable[Any, Any]
    reviser: Runnable[Any, Any] | None  # runs only on a poor fit; None with --keep-outline

    @property
    def label(self) -> str:
        t = self.target
        return series_label(t.slug, t.series, t.part)

    @property
    def angle(self) -> str:
        return series_angle(self.target.series, self.target.part)

    @property
    def context(self) -> str:
        """The previous part's summary and teaser, for the critic's continuity checks."""
        return continuity_facts(self.target.series, self.target.part)


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
        if args.keep_outline:
            raise ValueError("--keep-outline only applies with --series.")
        return None
    path = series_path(args.series_dir, args.series)
    series = load_series(path)
    part = check_draftable(series, path, args.series)
    _check_new_draft(series, path, args.out)
    check_target(parked, overwrite=True)  # derived from the sources: a rerun rewrites it
    return SeriesTarget(args.series, path, series, part, parked, args.keep_outline)


def series_grounding(grounding: Grounding, target: SeriesTarget) -> Grounding:
    """The voice grounding with this part's series checks added to the checklist, so the
    writer targets them and the critic judges them (a broken checks file is a usage error)."""
    checks = load_series_checks(style_guide_sections(grounding.style_guide))
    checklist = series_checklist(grounding.checklist, target.series, target.part, checks)
    return replace(grounding, checklist=checklist)


@dataclass(frozen=True)
class SeriesModels:
    relevance: BaseChatModel
    summary: BaseChatModel
    planner: BaseChatModel | None  # None with --keep-outline: no revision can run


def series_job(target: SeriesTarget, models: SeriesModels) -> SeriesJob:
    planner = models.planner
    return SeriesJob(
        target,
        build_relevance_classifier(models.relevance, relevance_system_prompt()),
        build_summariser(models.summary, summary_system_prompt()),
        build_reviser(planner, planner_system_prompt()) if planner is not None else None,
    )


def continuity_note(target: SeriesTarget) -> str | None:
    """A note when the previous part has no URL yet, so the draft cannot link to it."""
    previous = previous_part(target.series, target.part)
    if previous is None or previous.url:
        return None
    return (
        f"Part {previous.number} has no URL yet: the draft gets a [VARUN: ...] marker for the "
        f"link. Record it with: newsletter-machine series published {target.slug} "
        f"{previous.number} <url>"
    )


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


def _rerun_lines(t: SeriesTarget, sources_dir: Path, out: Path, overwrite: bool) -> tuple[str, ...]:
    sources, draft = shlex.quote(str(sources_dir)), shlex.quote(str(out))
    folder = t.path.parent
    custom = "" if folder == DEFAULT_SERIES_DIR else f" --series-dir {shlex.quote(str(folder))}"
    return (
        f"Then rerun: newsletter-machine issue --series {t.slug}{custom} --sources {sources} "
        f"--out {draft}{' --overwrite' if overwrite else ''}",
        f"To draft Part {t.part.number} as planned instead, copy the backup above back over "
        f"{t.path} and rerun with --keep-outline.",
    )


def _revision_sources(relevance: Relevance) -> tuple[SourceDoc, ...]:
    """On-topic sources once each, as many as one plan can read."""
    docs = dedupe_sources(usable_sources(relevance.kept))
    if len(docs) > MAX_PLANNER_SOURCES:
        print(
            f"Only the first {MAX_PLANNER_SOURCES} of {len(docs)} on-topic sources go to the "
            "planner."
        )
    return docs[:MAX_PLANNER_SOURCES]


def adjust_outline(
    job: SeriesJob, relevance: Relevance, sources_dir: Path, out: Path, *, overwrite: bool
) -> int | None:
    """None when the next part should be drafted; otherwise the exit code of a revision run
    instead (0: revised outline written for Varun to approve, 1: revision failed)."""
    t = job.target
    check = check_fit(t.series, t.part, relevance.fits)
    print(fit_line(check))
    if job.reviser is None or not check.mismatch:  # no reviser: --keep-outline
        return None
    reason = _no_revision(t, relevance)
    if reason:
        print(f"{reason}; drafting Part {t.part.number} as planned.", file=sys.stderr)
        return None
    print(
        f"This week's sources do not fit Part {t.part.number}, so it was not drafted. "
        "Revising the outline ..."
    )
    today = datetime.now(issue_timezone()).date()
    docs = _revision_sources(relevance)
    revision = RevisionJob(t.slug, t.path, t.series, docs, job.reviser, today)
    code = apply_revision(revision, _rerun_lines(t, sources_dir, out, overwrite))
    if code:
        print(
            f"To draft Part {t.part.number} as planned anyway, rerun with --keep-outline.",
            file=sys.stderr,
        )
    return code


def _no_revision(t: SeriesTarget, relevance: Relevance) -> str:
    """Why a poor fit still drafts the planned part ("" when a revision can run): verdicts
    missing for some sources, or a series a revision cannot change (both before any paid
    planner call)."""
    failed = len(relevance.unchecked)
    if failed:
        checks = "check" if failed == 1 else "checks"
        return f"{failed} relevance {checks} failed, so the outline is not revised"
    try:
        revisable_outline(t.series, t.path)
    except ValueError as exc:
        return f"{exc} Not revising"
    return ""


def _summary(job: SeriesJob, text: str) -> str:
    number = job.target.part.number
    try:
        summary = summarise_part(job.summariser, text)
    except Exception as exc:  # network/API failures surface as many types
        logger.debug("Summary failed", exc_info=True)
        print(
            f"Could not summarise Part {number}: {exc} (add a one-line summary to "
            f"{job.target.path} by hand)",
            file=sys.stderr,
        )
        return ""
    print(f"Summary: {summary}")
    return summary


def _teaser(job: SeriesJob, text: str) -> str:
    teaser = extract_teaser(text)
    final = following_part(job.target.series, job.target.part) is None
    if teaser and final:
        print(
            "The final part's draft ends with a 'Next in this series' line; remove it (not "
            "recorded).",
            file=sys.stderr,
        )
        return ""
    if teaser:
        print(f"Teaser: {teaser}")
    elif not final:
        print(
            "No 'Next in this series' line found in the draft; add one, and the teaser to "
            f"{job.target.path}, by hand.",
            file=sys.stderr,
        )
    return teaser


def _carried_forward(job: SeriesJob, draft: Path) -> tuple[str, str]:
    """``(summary, teaser)`` of the final draft; blank (with a warning) when unavailable."""
    try:
        text = draft.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Could not read {draft} for its summary: {exc}", file=sys.stderr)
        return "", ""
    return _summary(job, text), _teaser(job, text)


def finish_series(job: SeriesJob, code: int, draft: Path) -> int:
    """Mark the part drafted (with its summary and teaser) after a fully successful run;
    leave the file alone otherwise."""
    t = job.target
    if code:
        print(
            f"Series file not updated: Part {t.part.number} stays planned in {t.path}.",
            file=sys.stderr,
        )
        return code
    try:
        check_markable(t.path, t.part.number)  # before the paid summary call
        summary, teaser = _carried_forward(job, draft)
        reference = draft_reference(t.path, draft)
        kept = mark_drafted(
            t.path, t.slug, t.part.number, reference, summary=summary, teaser=teaser
        )
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

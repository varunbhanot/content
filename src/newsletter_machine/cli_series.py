"""``newsletter-machine series plan | approve | show``: propose, lock and read a series outline.

Exit codes as elsewhere: 0 done, 1 model or write failure, 2 configuration or usage error
(always before any model call). ``approve`` and ``show`` need no API key.
"""

import argparse
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.runnables import Runnable

from newsletter_machine.agent import make_chat_model
from newsletter_machine.cli_common import EXIT_CONFIG, EXIT_ERROR, configure_logging
from newsletter_machine.config import (
    ConfigError,
    issue_timezone,
    load_planner_model,
    load_settings,
)
from newsletter_machine.ingest import slugify
from newsletter_machine.planner import (
    PlanningInput,
    build_planner,
    collect_sources,
    planner_system_prompt,
    run_planner,
)
from newsletter_machine.series import format_outline
from newsletter_machine.series_store import (
    DEFAULT_SERIES_DIR,
    check_approval,
    check_can_plan,
    load_series,
    save_approval,
    save_series,
    series_path,
)
from newsletter_machine.sources import parse_since

logger = logging.getLogger(__name__)

DEFAULT_PLAN_SINCE = "28d"
DEFAULT_DRAFTS_DIR = Path("drafts")
# settings, --since, sources, series file, prompt, model provider package missing
USAGE_ERRORS = (ConfigError, ValueError, KeyError, OSError, ImportError)


def _series_dir_option(parser: Any) -> None:
    parser.add_argument(
        "--series-dir",
        type=Path,
        default=DEFAULT_SERIES_DIR,
        help=f"Folder of series files (default: {DEFAULT_SERIES_DIR})",
    )


def add_series_parser(sub: Any) -> None:
    series = sub.add_parser("series", help="Plan, approve and show a multi-part series")
    actions = series.add_subparsers(dest="series_command", required=True)
    plan = actions.add_parser("plan", help="Propose an outline from the sources saved in drafts/")
    plan.add_argument("topic", help="The series topic, e.g. evals (its slug names the file)")
    plan.add_argument(
        "--since",
        default=DEFAULT_PLAN_SINCE,
        help=f"Lookback: 28d, 4w or YYYY-MM-DD ({DEFAULT_PLAN_SINCE})",
    )
    plan.add_argument(
        "--drafts-dir",
        type=Path,
        default=DEFAULT_DRAFTS_DIR,
        help="Folder holding <date>.sources/ from earlier runs (default: drafts)",
    )
    plan.add_argument("--overwrite", action="store_true", help="Replace a proposed outline")
    _series_dir_option(plan)
    for name, text in (("approve", "Approve a proposed outline"), ("show", "Print an outline")):
        action = actions.add_parser(name, help=text)
        action.add_argument("slug", help="Series name, e.g. evals")
        _series_dir_option(action)


@dataclass(frozen=True)
class _PlanJob:
    topic: str
    slug: str
    path: Path
    sources: PlanningInput
    planner: Runnable[Any, Any]


def _slug(topic: str) -> str:
    if not any(char.isascii() and char.isalnum() for char in topic):
        raise ValueError(f"topic must contain ASCII letters or digits (got {topic!r}).")
    return slugify(topic)


def _prepare_plan(args: argparse.Namespace) -> _PlanJob:
    """Everything that can fail before the model call (exit 2)."""
    settings = load_settings()
    configure_logging()
    topic = args.topic.strip()
    slug = _slug(topic)
    path = series_path(args.series_dir, slug)
    check_can_plan(path, overwrite=args.overwrite)
    since = parse_since(args.since, datetime.now(issue_timezone())).date()
    sources = collect_sources(args.drafts_dir, since)
    model = make_chat_model(load_planner_model(settings), settings.anthropic_api_key)
    return _PlanJob(topic, slug, path, sources, build_planner(model, planner_system_prompt()))


def _planning_line(sources: PlanningInput) -> str:
    dirs = sources.dirs
    names = dirs[0].name if len(dirs) == 1 else f"{dirs[0].name} ... {dirs[-1].name}"
    folders = "folder" if len(dirs) == 1 else "folders"
    return f"Planning from {len(sources.docs)} sources in {len(dirs)} {folders} ({names})"


def _run_plan(args: argparse.Namespace) -> int:
    try:
        job = _prepare_plan(args)
    except USAGE_ERRORS as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    print(_planning_line(job.sources))
    try:
        series = run_planner(job.planner, job.topic, job.sources.docs)
    except Exception as exc:  # network/API failures surface as many types
        logger.debug("Planner run failed", exc_info=True)
        print(f"Planner failed: {exc}", file=sys.stderr)
        return EXIT_ERROR
    try:
        check_can_plan(job.path, overwrite=args.overwrite)  # it may have changed meanwhile
        save_series(job.path, series, job.slug)
    except USAGE_ERRORS as exc:
        print(format_outline(series, job.slug))  # keep the paid-for outline on screen
        print(f"Could not write the series: {exc} (outline not written)", file=sys.stderr)
        return EXIT_ERROR
    print(f"Wrote {job.path} (proposed, {len(series.parts)} parts)\n")
    print(format_outline(series, job.slug))
    print(f"Next: edit {job.path} if you want, then run: newsletter-machine series approve "
          f"{job.slug}")  # fmt: skip
    return 0


def _run_approve(args: argparse.Namespace) -> int:
    try:
        approval = check_approval(args.series_dir, args.slug)
    except USAGE_ERRORS as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    if approval.text is None:
        print(f"{approval.path} is already approved.")
        return 0
    try:
        save_approval(approval)
    except OSError as exc:
        print(f"Could not write the series: {exc}", file=sys.stderr)
        return EXIT_ERROR
    parts = len(approval.series.parts)
    print(f"Approved {approval.path} ({parts} parts). It is now the active series.")
    return 0


def _run_show(args: argparse.Namespace) -> int:
    try:
        series = load_series(series_path(args.series_dir, args.slug))
    except USAGE_ERRORS as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    print(format_outline(series, args.slug), end="")
    return 0


RUNNERS: dict[str, Callable[[argparse.Namespace], int]] = {
    "plan": _run_plan,
    "approve": _run_approve,
    "show": _run_show,
}


def run_series(args: argparse.Namespace) -> int:
    return RUNNERS[args.series_command](args)

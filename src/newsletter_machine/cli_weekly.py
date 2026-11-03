"""``newsletter-machine weekly`` (the scheduled run) and ``gmail-auth`` (one-time consent).

``weekly`` exit codes: the issue run's own non-zero code; else 1 if delivery failed; else 0.
Configuration problems (bad token, time zone, Substack settings) exit 2 before any model call.
"""

import argparse
import logging
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from newsletter_machine.cli_common import EXIT_CONFIG, EXIT_ERROR, configure_logging
from newsletter_machine.cli_issue import run_issue
from newsletter_machine.config import (
    ConfigError,
    WeeklySettings,
    load_ingest_settings,
    load_weekly_settings,
)
from newsletter_machine.gmail import DELIVERY_SCOPES, authorize, build_gmail_client
from newsletter_machine.weekly import (
    WeeklyDeps,
    WeeklyReport,
    config_failure,
    run_weekly,
    weekly_exit_code,
)

logger = logging.getLogger(__name__)

TEMP_PREFIX = "newsletter-weekly-"
UTC_ZONE = ZoneInfo("UTC")


def add_weekly_parsers(sub: Any) -> None:
    weekly = sub.add_parser(
        "weekly", help="Scheduled run: this week's issue, delivered to your Gmail inbox"
    )
    weekly.add_argument(
        "--out-dir", type=Path, help="Keep the files here (default: a temporary folder)"
    )
    weekly.add_argument(
        "--overwrite", action="store_true", help="Replace today's files already in --out-dir"
    )
    sub.add_parser("gmail-auth", help="One-time browser consent: Gmail read + insert (no send)")


@dataclass(frozen=True)
class ScheduledOutcome:
    exit_code: int
    summary: str  # one line
    started: bool = False  # the issue run began (models may have been paid for)


def _summary(report: WeeklyReport) -> str:
    if report.delivery_error:
        line = f"Could not deliver {report.subject!r}: {report.delivery_error}"
        if report.draft_path is not None:
            line += f" The draft is kept at {report.draft_path}."
    else:
        line = f"Delivered {report.subject!r} to your inbox (message {report.message_id})."
    return f"{line} {report.substack_line}" if report.substack_line else line


def _outcome(report: WeeklyReport, *, started: bool = True) -> ScheduledOutcome:
    return ScheduledOutcome(weekly_exit_code(report), _summary(report), started)


def _run_in(
    out_dir: Path | None, now: datetime, weekly: WeeklySettings, deps: WeeklyDeps, overwrite: bool
) -> WeeklyReport:
    """Run in ``out_dir``, or in a temporary folder that is removed unless delivery failed
    (then the paid-for draft stays where the summary says)."""
    if out_dir is not None:  # created by run_scheduled's checks
        return run_weekly(out_dir, now, weekly, deps, overwrite=overwrite)
    where = Path(tempfile.mkdtemp(prefix=TEMP_PREFIX))
    report: WeeklyReport | None = None
    try:
        report = run_weekly(where, now, weekly, deps)
        return report
    finally:
        if report is None or not (report.delivery_error and report.draft_path):
            shutil.rmtree(where, ignore_errors=True)


def run_scheduled(
    out_dir: Path | None, now: datetime | None = None, *, overwrite: bool = False
) -> ScheduledOutcome:
    """The whole scheduled run; shared by the CLI and the hosted agent's tool."""
    now = now or datetime.now(UTC)
    try:
        ingest = load_ingest_settings()
        configure_logging()
        if out_dir is not None:
            out_dir.mkdir(parents=True, exist_ok=True)
    except (ConfigError, ValueError, OSError) as exc:
        return ScheduledOutcome(EXIT_CONFIG, f"Config error: {exc}")
    try:
        mailbox = build_gmail_client(ingest, DELIVERY_SCOPES)  # fail fast: before any model call
    except ConfigError as exc:
        return ScheduledOutcome(EXIT_CONFIG, f"Config error: {exc}")
    except Exception as exc:  # Gmail API / network failures (OSError too) surface as many types
        logger.debug("Gmail setup failed", exc_info=True)
        return ScheduledOutcome(EXIT_ERROR, f"Gmail failed: {exc}")
    try:
        weekly = load_weekly_settings()
    except ConfigError as exc:  # Gmail works, so say so in the inbox too
        report = config_failure(mailbox, now, UTC_ZONE, f"Config error: {exc}")
        return _outcome(report, started=False)
    deps = WeeklyDeps(run_issue=run_issue, mailbox=mailbox)
    return _outcome(_run_in(out_dir, now, weekly, deps, overwrite))


def run_weekly_command(args: argparse.Namespace) -> int:
    outcome = run_scheduled(args.out_dir, overwrite=args.overwrite)
    print(outcome.summary, file=sys.stderr if outcome.exit_code else sys.stdout)
    return outcome.exit_code


def run_gmail_auth(args: argparse.Namespace) -> int:
    try:
        settings = load_ingest_settings(ignore_token=True)
        configure_logging()
        path = authorize(settings, DELIVERY_SCOPES)
    except (ConfigError, ValueError, OSError) as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    except Exception as exc:  # OAuth flow failures surface as many types
        logger.debug("Gmail consent failed", exc_info=True)
        print(f"Gmail consent failed: {exc}", file=sys.stderr)
        return EXIT_ERROR
    print(f"Saved a Gmail token (read + insert; it cannot send mail) to {path}.")
    print("For scheduled runs, store it base64-encoded as NM_GMAIL_TOKEN_B64 in .env (README).")
    return 0

"""``newsletter-machine weekly`` (the scheduled run) and ``gmail-auth`` (one-time consent).

``weekly`` exit codes: the issue run's own non-zero code; else 1 if delivery failed; else 0.
Configuration problems (bad token, time zone, Substack settings) exit 2 before any model call.
"""

import argparse
import logging
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from newsletter_machine.cli_common import EXIT_CONFIG, EXIT_ERROR, configure_logging
from newsletter_machine.cli_issue import run_issue
from newsletter_machine.config import ConfigError, load_ingest_settings, load_weekly_settings
from newsletter_machine.gmail import DELIVERY_SCOPES, authorize, build_gmail_client
from newsletter_machine.weekly import WeeklyDeps, WeeklyReport, run_weekly, weekly_exit_code

logger = logging.getLogger(__name__)

TEMP_PREFIX = "newsletter-weekly-"


def add_weekly_parsers(sub: Any) -> None:
    weekly = sub.add_parser(
        "weekly", help="Scheduled run: this week's issue, delivered to your Gmail inbox"
    )
    weekly.add_argument(
        "--out-dir", type=Path, help="Keep the files here (default: a temporary folder)"
    )
    sub.add_parser("gmail-auth", help="One-time browser consent: Gmail read + insert (no send)")


@dataclass(frozen=True)
class ScheduledOutcome:
    exit_code: int
    summary: str


@contextmanager
def _workdir(out_dir: Path | None) -> Iterator[Path]:
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        yield out_dir
        return
    with tempfile.TemporaryDirectory(prefix=TEMP_PREFIX) as tmp:
        yield Path(tmp)


def _summary(report: WeeklyReport) -> str:
    if report.delivery_error:
        line = f"Could not deliver {report.subject!r}: {report.delivery_error}"
    else:
        line = f"Delivered {report.subject!r} to your inbox (message {report.message_id})."
    return f"{line}\n{report.substack_line}" if report.substack_line else line


def run_scheduled(out_dir: Path | None, now: datetime | None = None) -> ScheduledOutcome:
    """The whole scheduled run; shared by the CLI and the hosted agent's tool."""
    try:
        ingest = load_ingest_settings()
        weekly = load_weekly_settings()
        configure_logging()
    except (ConfigError, ValueError, OSError) as exc:
        return ScheduledOutcome(EXIT_CONFIG, f"Config error: {exc}")
    try:
        mailbox = build_gmail_client(ingest, DELIVERY_SCOPES)  # fail fast: before any model call
    except ConfigError as exc:
        return ScheduledOutcome(EXIT_CONFIG, f"Config error: {exc}")
    except Exception as exc:  # Gmail API / network failures (OSError too) surface as many types
        logger.debug("Gmail setup failed", exc_info=True)
        return ScheduledOutcome(EXIT_ERROR, f"Gmail failed: {exc}")
    deps = WeeklyDeps(run_issue=run_issue, mailbox=mailbox)
    with _workdir(out_dir) as where:
        report = run_weekly(where, now or datetime.now(UTC), weekly, deps)
    return ScheduledOutcome(weekly_exit_code(report), _summary(report))


def run_weekly_command(args: argparse.Namespace) -> int:
    outcome = run_scheduled(args.out_dir)
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

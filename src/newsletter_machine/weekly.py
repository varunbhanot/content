"""The scheduled weekly run: ``issue`` headless, an optional Substack draft, inbox delivery.

Runs the Phase 4 ``issue`` command unchanged for today's date (in ``NM_TIMEZONE``), keeps a
copy of everything it prints, and always leaves Varun a message: the draft, a "no links"
notice or the failure log. Nothing is sent or published.
"""

import argparse
import contextlib
import io
import logging
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from typing import Literal, TextIO
from zoneinfo import ZoneInfo

from newsletter_machine.cli_common import EXIT_CONFIG, EXIT_ERROR
from newsletter_machine.cli_issue import IssuePaths, issue_paths
from newsletter_machine.config import SubstackSettings, WeeklySettings
from newsletter_machine.delivery import Delivery, Mailbox, deliver
from newsletter_machine.substack_draft import (
    SubstackClient,
    create_substack_draft,
    make_substack_client,
    split_title,
)

logger = logging.getLogger(__name__)

MAX_LOG_CHARS = 20_000  # keeps the message small; the tail holds the outcome
RULE = "-" * 60
NOTHING_SENT = "Nothing has been sent or published."
LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"

Status = Literal["drafted", "no_links", "failed"]
IssueRunner = Callable[[argparse.Namespace], int]


@dataclass(frozen=True)
class WeeklyDeps:
    run_issue: IssueRunner
    mailbox: Mailbox
    make_substack: Callable[[SubstackSettings], SubstackClient] = make_substack_client


@dataclass(frozen=True)
class WeeklyReport:
    status: Status
    exit_code: int  # the issue run's own exit code
    subject: str
    message_id: str  # "" when delivery failed
    delivery_error: str = ""
    substack_line: str = ""
    draft_path: Path | None = None  # set when this run wrote a draft


def config_failure(mailbox: Mailbox, now: datetime, timezone: ZoneInfo, error: str) -> WeeklyReport:
    """Tell Varun's inbox that the run could not start (e.g. a bad NM_TIMEZONE)."""
    subject = f"Newsletter run failed ({issue_date(now, timezone)})"
    body = f"{NOTHING_SENT}\n\nThe weekly run could not start:\n\n{error}\n"
    report = WeeklyReport("failed", EXIT_CONFIG, subject, "")
    try:
        return replace(report, message_id=deliver(mailbox, Delivery(subject, body, ())))
    except Exception as exc:  # Gmail API / network failures surface as many types
        logger.warning("Delivery failed", exc_info=True)
        return replace(report, delivery_error=f"{type(exc).__name__}: {exc}")


@dataclass(frozen=True)
class _IssueRun:
    code: int
    log: str
    draft: str | None  # only a draft written by this run
    written: tuple[Path, ...] = ()  # draft, critique and notes files this run wrote


def issue_date(now: datetime, timezone: ZoneInfo) -> date:
    return now.astimezone(timezone).date()


def issue_args(out: Path, *, overwrite: bool = False) -> argparse.Namespace:
    """The arguments ``issue --out OUT`` parses to: Gmail links, default window, no angle."""
    return argparse.Namespace(
        out=out, angle=None, sources=None, links_file=None, since=None, overwrite=overwrite
    )


class _Tee(io.TextIOBase):
    """Writes to the real stream (server logs) and to the captured log."""

    def __init__(self, real: TextIO, copy: io.StringIO) -> None:
        self._real, self._copy = real, copy

    def write(self, text: str) -> int:
        self._real.write(text)
        self._copy.write(text)
        return len(text)

    def flush(self) -> None:
        self._real.flush()


@contextlib.contextmanager
def _logging_to(log: io.StringIO) -> Iterator[None]:
    """Copy log records (warnings, tracebacks) into the captured log for the run."""
    handler = logging.StreamHandler(log)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        yield
    finally:
        root.removeHandler(handler)


def _captured(run: IssueRunner, args: argparse.Namespace) -> tuple[int, str]:
    """Run ``issue`` with its prints and log records copied into a buffer.

    The stdout/stderr swap is process-wide; the hosted tool allows one run at a time.
    """
    log = io.StringIO()
    out, err = _Tee(sys.stdout, log), _Tee(sys.stderr, log)
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), _logging_to(log):
        try:
            code = run(args)
        except Exception as exc:  # a bug must still reach Varun's inbox
            logger.exception("The issue run crashed")
            print(f"The issue run crashed: {type(exc).__name__}: {exc}", file=sys.stderr)
            code = EXIT_ERROR
    return code, log.getvalue()


def _read(path: Path) -> str | None:
    """A file's text, or None when it is missing or unreadable (delivery must go on)."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        logger.warning("Could not read %s", path, exc_info=True)
        return None


def _snapshot(path: Path) -> tuple[int, int, int] | None:
    """Identity of a file as it is now (atomic writes replace it), None when missing."""
    try:
        info = path.stat()
    except OSError:
        return None
    return info.st_ino, info.st_mtime_ns, info.st_size


def _fresh(path: Path, before: tuple[int, int, int] | None) -> bool:
    """True when this run wrote ``path`` (an earlier run's file under --overwrite is not)."""
    now = _snapshot(path)
    return now is not None and now != before


def _run_issue(run: IssueRunner, paths: IssuePaths, overwrite: bool) -> _IssueRun:
    files = (paths.draft, paths.critique, paths.notes)
    before = {path: _snapshot(path) for path in files}
    code, log = _captured(run, issue_args(paths.draft, overwrite=overwrite))
    written = tuple(path for path in files if _fresh(path, before[path]))
    draft = _read(paths.draft) if paths.draft in written else None
    return _IssueRun(code, log, draft, written)


def _status(run: _IssueRun) -> Status:
    if run.draft is not None:
        return "drafted"
    return "no_links" if run.code == 0 else "failed"


def _subject(status: Status, run: _IssueRun, day: date) -> str:
    if status == "no_links":
        return f"Newsletter: no links this week ({day})"
    if status == "failed" or run.draft is None:
        return f"Newsletter run failed ({day})"
    problems = " (with problems)" if run.code else ""
    return f"Newsletter draft{problems}: {split_title(run.draft)[0]} ({day})"


def _substack_line(deps: WeeklyDeps, settings: WeeklySettings, run: _IssueRun) -> str:
    """Only a clean run (exit 0 with a fresh draft) goes to Substack."""
    draft = run.draft
    if settings.substack is None or draft is None or run.code != 0:
        return ""
    try:
        client = deps.make_substack(settings.substack)
        result = create_substack_draft(client, draft, settings.substack.publication_url)
    except Exception as exc:  # unofficial API: login, captcha and HTTP errors vary
        logger.warning("Substack draft failed", exc_info=True)
        return f"Substack draft failed: {type(exc).__name__}: {exc}"
    return f"Substack draft (unpublished): {result.edit_url}"


def _trimmed(log: str) -> str:
    return log if len(log) <= MAX_LOG_CHARS else "[...]\n" + log[-MAX_LOG_CHARS:]


def _body(run: _IssueRun, substack_line: str) -> str:
    parts = [NOTHING_SENT]
    if substack_line:
        parts.append(substack_line)
    if run.draft is not None:
        parts.append(f"{RULE}\nDraft (Markdown, also attached)\n{RULE}\n\n{run.draft}")
    parts.append(f"{RULE}\nRun log\n{RULE}\n\n{_trimmed(run.log).strip() or '(no output)'}")
    return "\n\n".join(parts) + "\n"


def _attachments(run: _IssueRun) -> tuple[tuple[str, str], ...]:
    if run.draft is None:
        return ()
    texts = ((path.name, _read(path)) for path in run.written)
    return tuple((name, text) for name, text in texts if text is not None)


def run_weekly(
    out_dir: Path,
    now: datetime,
    settings: WeeklySettings,
    deps: WeeklyDeps,
    *,
    overwrite: bool = False,
) -> WeeklyReport:
    """Run this week's issue into ``out_dir`` and deliver the outcome to the inbox."""
    day = issue_date(now, settings.timezone)
    paths = issue_paths(out_dir / f"{day.isoformat()}.md")
    run = _run_issue(deps.run_issue, paths, overwrite)
    status = _status(run)
    substack_line = _substack_line(deps, settings, run)
    subject = _subject(status, run, day)
    delivery = Delivery(subject, _body(run, substack_line), _attachments(run))
    draft_path = paths.draft if run.draft is not None else None
    report = WeeklyReport(status, run.code, subject, "", "", substack_line, draft_path)
    try:
        return replace(report, message_id=deliver(deps.mailbox, delivery))
    except Exception as exc:  # Gmail API / auth / network failures surface as many types
        logger.warning("Delivery failed", exc_info=True)
        return replace(report, delivery_error=f"{type(exc).__name__}: {exc}")


def weekly_exit_code(report: WeeklyReport) -> int:
    """The issue's own failure first; then 1 if delivery failed; else 0."""
    return report.exit_code or (EXIT_ERROR if report.delivery_error else 0)

"""Hosted entry for Managed Deep Agents: the one tool the scheduled runner agent calls.

The root ``agent.py`` gives a small runner model this tool; the schedule's prompt asks it to
call the tool once. The tool runs ``newsletter-machine weekly`` in-process (temporary folder,
inbox delivery). Once a run has reached the inbox, a second call for the same issue date
returns the first answer instead of paying for another issue; a call while a run is in
progress is refused.
"""

import logging
import threading
from collections.abc import Callable
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from langchain_core.tools import tool

from newsletter_machine.cli_weekly import ScheduledOutcome, run_scheduled
from newsletter_machine.config import ConfigError, load_runner_model, load_weekly_settings
from newsletter_machine.weekly import issue_date

logger = logging.getLogger(__name__)

RUNNER_TOOL_NAME = "run_weekly_issue"


class OncePerDay:
    """Run a job at most once per day per process; concurrent calls are refused."""

    def __init__(self, run: Callable[[], ScheduledOutcome], today: Callable[[], date]) -> None:
        self._run = run
        self._today = today
        self._lock = threading.Lock()
        self._done: dict[date, str] = {}

    def __call__(self) -> str:
        if not self._lock.acquire(blocking=False):
            return "A weekly run is already in progress; not starting another."
        try:
            day = self._today()
            if day in self._done:
                return f"Already ran for {day}: {self._done[day]}"
            outcome = self._run()
            answer = _answer(outcome)
            if outcome.delivered:  # undelivered (config error, Gmail down): allow a retry
                self._done = {**self._done, day: answer}
            return answer
        finally:
            self._lock.release()


def _answer(outcome: ScheduledOutcome) -> str:
    status = "OK" if outcome.exit_code == 0 else f"Exit {outcome.exit_code}"
    return f"{status}: {outcome.summary}"


def scheduled_once() -> ScheduledOutcome:
    return run_scheduled(None)


def _issue_today() -> date:
    """Today as the issue date sees it (``NM_TIMEZONE``; UTC when that is invalid)."""
    try:
        zone = load_weekly_settings().timezone
    except ConfigError:
        zone = ZoneInfo("UTC")
    return issue_date(datetime.now(UTC), zone)


_RUNNER = OncePerDay(scheduled_once, _issue_today)


def runner_model() -> str:
    return load_runner_model()


@tool(RUNNER_TOOL_NAME)
def run_weekly_issue() -> str:
    """Run this week's newsletter issue end to end and deliver the result to Varun's Gmail
    inbox. Takes no arguments. Call it exactly once; it returns a one-line outcome."""
    logger.info("Scheduled weekly run requested")
    return _RUNNER()

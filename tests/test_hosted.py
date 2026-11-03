import threading
from datetime import date
from zoneinfo import ZoneInfo

import pytest

from newsletter_machine import config, hosted
from newsletter_machine.cli_weekly import ScheduledOutcome
from newsletter_machine.config import ConfigError, load_runner_model
from newsletter_machine.hosted import OncePerDay, run_weekly_issue

DAY = date(2026, 11, 6)


def test_runner_model_defaults_to_the_fast_model_and_is_configurable() -> None:
    assert load_runner_model({}) == config.DEFAULT_FAST_MODEL
    assert load_runner_model({"NM_FAST_MODEL": "anthropic:fast"}) == "anthropic:fast"
    assert load_runner_model({"NM_RUNNER_MODEL": " anthropic:r ", "NM_FAST_MODEL": "x:y"}) == (
        "anthropic:r"
    )
    with pytest.raises(ConfigError, match="NM_RUNNER_MODEL"):
        load_runner_model({"NM_RUNNER_MODEL": "no-provider"})


def test_runner_model_reads_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: False)
    monkeypatch.setenv("NM_RUNNER_MODEL", "anthropic:runner")
    assert hosted.runner_model() == "anthropic:runner"


def test_once_per_day_runs_once_and_repeats_the_first_answer() -> None:
    calls: list[int] = []

    def _run() -> ScheduledOutcome:
        calls.append(1)
        return ScheduledOutcome(0, "Delivered 'x'.", delivered=True)

    once = OncePerDay(_run, lambda: DAY)
    assert once() == "OK: Delivered 'x'."
    assert once() == "Already ran for 2026-11-06: OK: Delivered 'x'."
    assert len(calls) == 1


def test_once_per_day_runs_again_on_a_new_day() -> None:
    days = iter([DAY, date(2026, 11, 13)])
    once = OncePerDay(lambda: ScheduledOutcome(1, "failed", delivered=True), lambda: next(days))
    assert once() == "Exit 1: failed"
    assert once() == "Exit 1: failed"


def test_undelivered_results_are_not_cached_so_a_fix_can_retry() -> None:
    outcomes = iter(
        [
            ScheduledOutcome(2, "Config error: x"),
            ScheduledOutcome(1, "Could not deliver"),
            ScheduledOutcome(0, "Delivered.", delivered=True),
        ]
    )
    once = OncePerDay(lambda: next(outcomes), lambda: DAY)
    assert once() == "Exit 2: Config error: x"
    assert once() == "Exit 1: Could not deliver"
    assert once() == "OK: Delivered."
    assert once() == "Already ran for 2026-11-06: OK: Delivered."


def test_concurrent_call_is_refused() -> None:
    started, release = threading.Event(), threading.Event()

    def _slow() -> ScheduledOutcome:
        started.set()
        release.wait(5)
        return ScheduledOutcome(0, "done", delivered=True)

    once = OncePerDay(_slow, lambda: DAY)
    results: list[str] = []
    worker = threading.Thread(target=lambda: results.append(once()))
    worker.start()
    started.wait(5)
    assert "already in progress" in once()
    release.set()
    worker.join(5)
    assert results == ["OK: done"]


def test_tool_takes_no_arguments_and_runs_the_scheduled_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[object] = []

    def _scheduled(out_dir: object) -> ScheduledOutcome:
        seen.append(out_dir)
        return ScheduledOutcome(0, "Delivered.")

    monkeypatch.setattr(hosted, "run_scheduled", _scheduled)
    monkeypatch.setattr(hosted, "_RUNNER", OncePerDay(hosted.scheduled_once, lambda: DAY))
    assert run_weekly_issue.name == "run_weekly_issue"
    assert run_weekly_issue.args == {}
    assert run_weekly_issue.invoke({}) == "OK: Delivered."
    assert seen == [None]


def test_runner_counts_days_in_the_issue_time_zone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: False)
    monkeypatch.setenv("NM_TIMEZONE", "Pacific/Kiritimati")  # UTC+14: often "tomorrow"
    now = hosted.datetime.now(hosted.UTC)
    assert hosted._issue_today() == now.astimezone(ZoneInfo("Pacific/Kiritimati")).date()


def test_runner_falls_back_to_utc_on_a_bad_zone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: False)
    monkeypatch.setenv("NM_TIMEZONE", "Nowhere/Land")
    assert hosted._issue_today() == hosted.datetime.now(hosted.UTC).date()

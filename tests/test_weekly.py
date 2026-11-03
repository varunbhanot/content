import argparse
import logging
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from email import message_from_bytes
from email.message import Message
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from newsletter_machine.config import SubstackSettings, WeeklySettings
from newsletter_machine.weekly import (
    MAX_LOG_CHARS,
    WeeklyDeps,
    config_failure,
    issue_date,
    run_weekly,
    weekly_exit_code,
)

KOLKATA = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 11, 5, 20, 0, tzinfo=UTC)  # Friday 01:30 in Kolkata
DRAFT = "# Evals are the moat\n\nBody.\n\n## Sources\n\n- [A](https://a.example)\n"
PUB = "https://x.substack.com"


class FakeMailbox:
    def __init__(self, fail: Exception | None = None) -> None:
        self.fail = fail
        self.raw: list[bytes] = []

    def profile_address(self) -> str:
        return "varun@example.com"

    def insert_message(self, raw: bytes, label_ids: Sequence[str]) -> str:
        if self.fail:
            raise self.fail
        self.raw.append(raw)
        return "m-1"

    def message(self) -> Message:
        return message_from_bytes(self.raw[-1])


def _issue(code: int, *, draft: bool = True, extras: bool = True, output: str = "ran") -> Any:
    seen: list[argparse.Namespace] = []

    def _run(args: argparse.Namespace) -> int:
        seen.append(args)
        print(output)
        print("a warning", file=sys.stderr)
        out: Path = args.out
        if draft:
            out.write_text(DRAFT)
        if extras:
            out.with_name(f"{out.stem}.critique.md").write_text("critique")
            out.with_name(f"{out.stem}.notes.md").write_text("notes")
        return code

    _run.seen = seen  # type: ignore[attr-defined]
    return _run


def _settings(substack: SubstackSettings | None = None) -> WeeklySettings:
    return WeeklySettings(timezone=KOLKATA, substack=substack)


def _body(message: Message) -> str:
    part = next(p for p in message.walk() if p.get_content_type() == "text/plain")
    payload = part.get_payload(decode=True)
    assert isinstance(payload, bytes)
    return payload.decode("utf-8")


def _files(message: Message) -> dict[str, str]:
    return {
        str(p.get_filename()): p.get_payload(decode=True).decode()  # type: ignore[union-attr]
        for p in message.walk()
        if p.get_filename()
    }


def test_issue_date_uses_the_configured_zone() -> None:
    assert issue_date(NOW, KOLKATA) == date(2026, 11, 6)
    assert issue_date(NOW, ZoneInfo("UTC")) == date(2026, 11, 5)


def test_drafted_run_delivers_draft_and_attachments(tmp_path: Path) -> None:
    mailbox, issue = FakeMailbox(), _issue(0)
    report = run_weekly(tmp_path, NOW, _settings(), WeeklyDeps(issue, mailbox))
    assert report.status == "drafted" and report.message_id == "m-1"
    assert weekly_exit_code(report) == 0
    args = issue.seen[0]
    assert args.out == tmp_path / "2026-11-06.md"
    assert (args.sources, args.links_file, args.since, args.angle) == (None, None, None, None)
    assert args.overwrite is False
    message = mailbox.message()
    assert message["Subject"] == "Newsletter draft: Evals are the moat (2026-11-06)"
    body = _body(message)
    assert "Nothing has been sent or published." in body
    assert DRAFT in body and "ran" in body and "a warning" in body
    assert _files(message) == {
        "2026-11-06.md": DRAFT,
        "2026-11-06.critique.md": "critique",
        "2026-11-06.notes.md": "notes",
    }


def test_output_still_reaches_the_real_streams(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_weekly(tmp_path, NOW, _settings(), WeeklyDeps(_issue(0), FakeMailbox()))
    captured = capsys.readouterr()
    assert "ran" in captured.out and "a warning" in captured.err


def test_no_links_sends_a_short_notice(tmp_path: Path) -> None:
    mailbox = FakeMailbox()
    issue = _issue(0, draft=False, extras=False, output="No links found; nothing to draft.")
    report = run_weekly(tmp_path, NOW, _settings(), WeeklyDeps(issue, mailbox))
    assert report.status == "no_links" and weekly_exit_code(report) == 0
    message = mailbox.message()
    assert message["Subject"] == "Newsletter: no links this week (2026-11-06)"
    assert "No links found" in _body(message) and not _files(message)


@pytest.mark.parametrize("code", [1, 2])
def test_failed_run_delivers_the_log_and_keeps_the_exit_code(tmp_path: Path, code: int) -> None:
    mailbox = FakeMailbox()
    issue = _issue(code, draft=False, extras=False, output="Editor failed: 529 overloaded")
    report = run_weekly(tmp_path, NOW, _settings(), WeeklyDeps(issue, mailbox))
    assert report.status == "failed" and weekly_exit_code(report) == code
    message = mailbox.message()
    assert message["Subject"] == "Newsletter run failed (2026-11-06)"
    assert "Editor failed: 529 overloaded" in _body(message)


def test_kept_draft_after_a_late_failure_is_still_delivered(tmp_path: Path) -> None:
    mailbox = FakeMailbox()
    report = run_weekly(tmp_path, NOW, _settings(), WeeklyDeps(_issue(1), mailbox))
    assert report.status == "drafted" and weekly_exit_code(report) == 1
    assert mailbox.message()["Subject"] == (
        "Newsletter draft (with problems): Evals are the moat (2026-11-06)"
    )


def test_exit_2_never_delivers_an_older_draft_as_this_weeks(tmp_path: Path) -> None:
    (tmp_path / "2026-11-06.md").write_text("old draft")
    mailbox = FakeMailbox()
    issue = _issue(2, draft=False, extras=False, output="Config error: exists")
    report = run_weekly(tmp_path, NOW, _settings(), WeeklyDeps(issue, mailbox))
    assert report.status == "failed"
    assert "old draft" not in _body(mailbox.message())


def test_crash_in_the_issue_run_is_reported_not_raised(tmp_path: Path) -> None:
    def _boom(args: argparse.Namespace) -> int:
        raise RuntimeError("bug")

    mailbox = FakeMailbox()
    report = run_weekly(tmp_path, NOW, _settings(), WeeklyDeps(_boom, mailbox))
    assert report.status == "failed" and weekly_exit_code(report) == 1
    assert "RuntimeError: bug" in _body(mailbox.message())


def test_long_log_is_trimmed_to_its_tail(tmp_path: Path) -> None:
    mailbox = FakeMailbox()
    output = "x" * (MAX_LOG_CHARS * 2) + "THE END"
    issue = _issue(1, draft=False, extras=False, output=output)
    run_weekly(tmp_path, NOW, _settings(), WeeklyDeps(issue, mailbox))
    body = _body(mailbox.message())
    assert "THE END" in body and len(body) < MAX_LOG_CHARS + 2000


def test_delivery_failure_is_reported_with_exit_1(tmp_path: Path) -> None:
    mailbox = FakeMailbox(fail=OSError("403 insufficient permissions"))
    report = run_weekly(tmp_path, NOW, _settings(), WeeklyDeps(_issue(0), mailbox))
    assert report.message_id == "" and "403" in report.delivery_error
    assert weekly_exit_code(report) == 1


class FakeSubstack:
    def __init__(self, fail: Exception | None = None) -> None:
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    def create_draft(self, title: str, markdown: str) -> Mapping[str, Any]:
        if self.fail:
            raise self.fail
        self.calls.append((title, markdown))
        return {"draft": {"id": 42}}


def test_substack_draft_is_created_only_when_opted_in(tmp_path: Path) -> None:
    client, made = FakeSubstack(), []

    def _make(settings: SubstackSettings) -> FakeSubstack:
        made.append(settings)
        return client

    (tmp_path / "off").mkdir()
    run_weekly(tmp_path / "off", NOW, _settings(), WeeklyDeps(_issue(0), FakeMailbox(), _make))
    assert made == []
    mailbox = FakeMailbox()
    settings = _settings(SubstackSettings(PUB, cookies="c"))
    report = run_weekly(tmp_path, NOW, settings, WeeklyDeps(_issue(0), mailbox, _make))
    assert client.calls[0][0] == "Evals are the moat"
    assert report.substack_line == f"Substack draft (unpublished): {PUB}/publish/post/42"
    assert report.substack_line in _body(mailbox.message())


def test_substack_is_skipped_without_a_draft(tmp_path: Path) -> None:
    client = FakeSubstack()
    deps = WeeklyDeps(_issue(1, draft=False, extras=False), FakeMailbox(), lambda s: client)
    run_weekly(tmp_path, NOW, _settings(SubstackSettings(PUB, cookies="c")), deps)
    assert client.calls == []


def test_substack_failure_is_reported_and_delivery_still_happens(tmp_path: Path) -> None:
    mailbox = FakeMailbox()
    client = FakeSubstack(fail=RuntimeError("captcha"))
    deps = WeeklyDeps(_issue(0), mailbox, lambda s: client)
    report = run_weekly(tmp_path, NOW, _settings(SubstackSettings(PUB, cookies="c")), deps)
    assert report.substack_line == "Substack draft failed: RuntimeError: captcha"
    assert weekly_exit_code(report) == 0 and report.message_id == "m-1"


def test_log_records_reach_the_message(tmp_path: Path) -> None:
    def _run(args: argparse.Namespace) -> int:
        logging.getLogger("newsletter_machine.web").warning("fetch blocked for %s", "x.com")
        return 1

    mailbox = FakeMailbox()
    before = list(logging.getLogger().handlers)
    run_weekly(tmp_path, NOW, _settings(), WeeklyDeps(_run, mailbox))
    assert "WARNING newsletter_machine.web: fetch blocked for x.com" in _body(mailbox.message())
    assert logging.getLogger().handlers == before  # the capture handler is removed again


def test_overwrite_is_passed_to_the_issue_run(tmp_path: Path) -> None:
    issue = _issue(0)
    run_weekly(tmp_path, NOW, _settings(), WeeklyDeps(issue, FakeMailbox()), overwrite=True)
    assert issue.seen[0].overwrite is True


def test_undecodable_and_unreadable_files_do_not_stop_delivery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _run(args: argparse.Namespace) -> int:
        args.out.write_bytes(b"# Title\n\n\xff broken\n")
        args.out.with_name(f"{args.out.stem}.notes.md").write_text("notes")
        return 0

    real_read = Path.read_text

    def _read(self: Path, *args: Any, **kwargs: Any) -> str:
        if self.name.endswith(".notes.md"):
            raise PermissionError("denied")
        return real_read(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _read)
    mailbox = FakeMailbox()
    report = run_weekly(tmp_path, NOW, _settings(), WeeklyDeps(_run, mailbox))
    assert report.status == "drafted" and report.draft_path == tmp_path / "2026-11-06.md"
    assert set(_files(mailbox.message())) == {"2026-11-06.md"}
    assert "� broken" in _body(mailbox.message())


def test_config_failure_is_delivered() -> None:
    mailbox = FakeMailbox()
    report = config_failure(mailbox, NOW, ZoneInfo("UTC"), "Config error: NM_TIMEZONE")
    assert report.exit_code == 2 and report.message_id == "m-1"
    message = mailbox.message()
    assert message["Subject"] == "Newsletter run failed (2026-11-05)"
    assert "Config error: NM_TIMEZONE" in _body(message)
    failed = config_failure(FakeMailbox(fail=OSError("down")), NOW, ZoneInfo("UTC"), "x")
    assert failed.delivery_error == "OSError: down"

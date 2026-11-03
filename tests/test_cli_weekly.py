import argparse
import shutil
from collections.abc import Sequence
from datetime import UTC, datetime
from email import message_from_bytes
from pathlib import Path
from typing import Any

import pytest

from newsletter_machine import cli_weekly, config
from newsletter_machine.cli import main
from newsletter_machine.config import ConfigError
from newsletter_machine.gmail import DELIVERY_SCOPES

DRAFT = "# Evals are the moat\n\nBody.\n"


class FakeMailbox:
    def __init__(self) -> None:
        self.raw: list[bytes] = []

    def profile_address(self) -> str:
        return "varun@example.com"

    def insert_message(self, raw: bytes, label_ids: Sequence[str]) -> str:
        self.raw.append(raw)
        return "m-9"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: False)
    for name in ("NM_GMAIL_TOKEN_B64", "NM_SUBSTACK_DRAFT", "NM_TIMEZONE"):
        monkeypatch.delenv(name, raising=False)


def _wire(monkeypatch: pytest.MonkeyPatch, code: int = 0) -> dict[str, Any]:
    seen: dict[str, Any] = {"mailbox": FakeMailbox()}

    def _build(settings: Any, scopes: Sequence[str]) -> FakeMailbox:
        seen["scopes"] = tuple(scopes)
        mailbox: FakeMailbox = seen["mailbox"]
        return mailbox

    def _issue(args: argparse.Namespace) -> int:
        seen["out"] = args.out
        args.out.write_text(DRAFT)
        return code

    monkeypatch.setattr(cli_weekly, "build_gmail_client", _build)
    monkeypatch.setattr(cli_weekly, "run_issue", _issue)
    return seen


def test_weekly_delivers_and_cleans_up_its_temporary_folder(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen = _wire(monkeypatch)
    assert main(["weekly"]) == 0
    assert seen["scopes"] == DELIVERY_SCOPES
    assert not seen["out"].parent.exists()
    raw = seen["mailbox"].raw[0]
    assert message_from_bytes(raw)["Subject"].startswith("Newsletter draft: Evals are the moat")
    assert "Delivered 'Newsletter draft: Evals are the moat" in capsys.readouterr().out


def test_weekly_keeps_files_in_out_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen = _wire(monkeypatch)
    out_dir = tmp_path / "drafts"
    assert main(["weekly", "--out-dir", str(out_dir)]) == 0
    assert seen["out"].parent == out_dir and seen["out"].read_text() == DRAFT


def test_weekly_passes_on_the_issue_exit_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _wire(monkeypatch, code=1)
    assert main(["weekly"]) == 1
    assert "with problems" in capsys.readouterr().err


def test_weekly_config_error_exits_2_before_any_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen = _wire(monkeypatch)

    def _bad(settings: Any, scopes: Sequence[str]) -> FakeMailbox:
        raise ConfigError("token lacks gmail.insert")

    monkeypatch.setattr(cli_weekly, "build_gmail_client", _bad)
    assert main(["weekly"]) == 2
    assert "out" not in seen
    assert "Config error: token lacks gmail.insert" in capsys.readouterr().err


def test_weekly_bad_timezone_exits_2_and_tells_the_inbox(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _wire(monkeypatch)
    monkeypatch.setenv("NM_TIMEZONE", "Nowhere/Land")
    assert main(["weekly"]) == 2
    assert "out" not in seen  # no issue run
    message = message_from_bytes(seen["mailbox"].raw[0])
    assert message["Subject"].startswith("Newsletter run failed")


def test_weekly_overwrite_flag_reaches_the_issue_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen = _wire(monkeypatch)

    def _issue(args: argparse.Namespace) -> int:
        seen["overwrite"] = args.overwrite
        return 0

    monkeypatch.setattr(cli_weekly, "run_issue", _issue)
    assert main(["weekly", "--out-dir", str(tmp_path), "--overwrite"]) == 0
    assert seen["overwrite"] is True


def test_temp_folder_is_removed_even_when_the_run_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    made: list[Path] = []
    real = cli_weekly.tempfile.mkdtemp

    def _mkdtemp(**kwargs: Any) -> str:
        made.append(Path(real(**kwargs)))
        return str(made[-1])

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("bug")

    _wire(monkeypatch)
    monkeypatch.setattr(cli_weekly.tempfile, "mkdtemp", _mkdtemp)
    monkeypatch.setattr(cli_weekly, "run_weekly", _boom)
    with pytest.raises(RuntimeError):
        cli_weekly.run_scheduled(None)
    assert made and not made[0].exists()


def test_weekly_gmail_outage_exits_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _wire(monkeypatch)

    def _down(settings: Any, scopes: Sequence[str]) -> FakeMailbox:
        raise TimeoutError("oauth2.googleapis.com timed out")

    monkeypatch.setattr(cli_weekly, "build_gmail_client", _down)
    assert main(["weekly"]) == 1
    assert "Gmail failed: oauth2.googleapis.com timed out" in capsys.readouterr().err


def test_run_scheduled_reports_delivery_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _wire(monkeypatch)

    def _refuse(raw: bytes, label_ids: Sequence[str]) -> str:
        raise OSError("403")

    monkeypatch.setattr(seen["mailbox"], "insert_message", _refuse)
    outcome = cli_weekly.run_scheduled(None, datetime(2026, 11, 6, 2, tzinfo=UTC))
    assert outcome.exit_code == 1 and not outcome.delivered
    assert "Could not deliver" in outcome.summary and "OSError: 403" in outcome.summary
    kept = seen["out"]  # the paid-for draft survives a failed delivery
    assert f"The draft is kept at {kept}." in outcome.summary
    assert kept.read_text() == DRAFT
    shutil.rmtree(kept.parent)


def test_gmail_auth_saves_token_and_ignores_a_broken_b64(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setenv("NM_GMAIL_TOKEN_B64", "%%%")
    seen: dict[str, Any] = {}

    def _authorize(settings: Any, scopes: Sequence[str]) -> Path:
        seen["scopes"] = tuple(scopes)
        return tmp_path / "token.json"

    monkeypatch.setattr(cli_weekly, "authorize", _authorize)
    assert main(["gmail-auth"]) == 0
    assert seen["scopes"] == DELIVERY_SCOPES
    out = capsys.readouterr().out
    assert str(tmp_path / "token.json") in out and "NM_GMAIL_TOKEN_B64" in out


@pytest.mark.parametrize(
    ("error", "code"), [(ConfigError("no client file"), 2), (RuntimeError("denied"), 1)]
)
def test_gmail_auth_failures(monkeypatch: pytest.MonkeyPatch, error: Exception, code: int) -> None:
    def _authorize(settings: Any, scopes: Sequence[str]) -> Path:
        raise error

    monkeypatch.setattr(cli_weekly, "authorize", _authorize)
    assert main(["gmail-auth"]) == code


def test_weekly_bad_token_setting_exits_2_before_gmail(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen = _wire(monkeypatch)
    monkeypatch.setenv("NM_GMAIL_TOKEN_B64", "%%%")
    assert main(["weekly"]) == 2
    assert "scopes" not in seen
    assert "NM_GMAIL_TOKEN_B64" in capsys.readouterr().err

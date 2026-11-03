from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from youtube_transcript_api import TranscriptsDisabled

from newsletter_machine import cli, config
from newsletter_machine.cli import main
from newsletter_machine.gmail import GmailError
from newsletter_machine.sources import InboxLink
from newsletter_machine.web import BlockedError, FetchError

PREVIOUS = "---\nurl: https://old.example.com\n---\n"
ARTICLE_HTML = (
    "<html><head><title>Post A</title></head><body><article><p>"
    + "Readable article body about agent reliability. " * 15
    + "</p></article></body></html>"
)


BROWSER_CALLS: list[str] = []


def _record_browser_use(url: str) -> str:
    BROWSER_CALLS.append(url)
    return ARTICLE_HTML


@pytest.fixture(autouse=True)
def _no_unexpected_browser_fallback() -> Iterator[None]:
    """Tests that do not stub a refusal must never reach the browser fallback."""
    BROWSER_CALLS.clear()
    yield
    assert BROWSER_CALLS == []


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """No real .env, no network: fake fetchers, cwd in a temp dir."""
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(cli, "make_html_fetcher", lambda timeout: lambda url: ARTICLE_HTML)
    monkeypatch.setattr(cli, "make_browser_fetcher", lambda timeout: _record_browser_use)
    monkeypatch.setattr(
        cli, "make_transcript_fetcher", lambda languages, timeout: lambda video_id: "spoken words"
    )


def test_ingest_from_links_file_writes_one_file_per_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    links = tmp_path / "links.txt"
    links.write_text("https://a.com/post my take\nhttps://youtu.be/dQw4w9WgXcQ\n")
    out = tmp_path / "out"
    assert main(["ingest", "--links-file", str(links), "--out", str(out)]) == 0
    assert sorted(p.name for p in out.iterdir()) == ["01-post-a.md", "02-post-a.md"]
    stdout = capsys.readouterr().out
    assert "Wrote 2 files" in stdout
    assert "2 ok, 0 fallback, 0 failed" in stdout


def test_ingest_retries_refused_pages_with_browser_fetcher(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def refused(url: str) -> str:
        raise BlockedError("HTTP 403")

    monkeypatch.setattr(cli, "make_html_fetcher", lambda timeout: refused)
    monkeypatch.setattr(cli, "make_browser_fetcher", lambda timeout: lambda url: ARTICLE_HTML)
    links = tmp_path / "links.txt"
    links.write_text("https://cf.example.com/post\n")
    assert main(["ingest", "--links-file", str(links), "--out", str(tmp_path / "out")]) == 0
    assert "1 ok, 0 fallback, 0 failed" in capsys.readouterr().out


class _FakeGmail:
    def __init__(self) -> None:
        self.query = ""

    def label_id(self, name: str) -> str | None:
        return "L" if name == "newsletter" else None

    def list_message_ids(self, label_id: str, query: str) -> list[str]:
        self.query = query
        return []

    def get_message(self, message_id: str) -> dict[str, Any]:
        raise AssertionError("no messages")


def test_ingest_from_gmail_with_no_links_reports_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _FakeGmail()
    monkeypatch.setattr(cli, "build_gmail_client", lambda settings: fake)
    assert main(["ingest", "--since", "2026-10-30", "--out", str(tmp_path / "o")]) == 0
    assert fake.query == f"after:{int(datetime(2026, 10, 30, tzinfo=UTC).timestamp())} {{from:me}}"
    assert "No links found" in capsys.readouterr().out
    assert not (tmp_path / "o").exists()


def test_ingest_from_gmail_reports_fallback_and_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    when = datetime(2026, 11, 1, tzinfo=UTC)
    links = (
        InboxLink("https://a.com/1", "", "", when),
        InboxLink("https://b.com/broken", "", "", when),
        InboxLink("https://youtu.be/dQw4w9WgXcQ", "", "", when),
    )

    def fetch(url: str) -> str:
        if "broken" in url:
            raise FetchError("HTTP 404")
        return ARTICLE_HTML

    def no_transcript(video_id: str) -> str:
        raise TranscriptsDisabled(video_id)

    monkeypatch.setattr(cli, "make_html_fetcher", lambda timeout: fetch)
    monkeypatch.setattr(cli, "make_transcript_fetcher", lambda languages, timeout: no_transcript)
    monkeypatch.setattr(cli, "build_gmail_client", lambda settings: _FakeGmail())
    monkeypatch.setattr(cli, "read_inbox_links", lambda client, label, since, senders: links)
    assert main(["ingest", "--out", str(tmp_path / "o")]) == 0
    out = capsys.readouterr().out
    assert "1 ok, 1 fallback, 1 failed" in out
    assert "(HTTP 404)" in out


def test_ingest_exits_1_on_gmail_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(settings: Any) -> Any:
        raise GmailError("label 'newsletter' not found")

    monkeypatch.setattr(cli, "build_gmail_client", boom)
    assert main(["ingest", "--out", str(tmp_path / "o")]) == 1
    assert "label 'newsletter' not found" in capsys.readouterr().err


def test_ingest_exits_2_when_gmail_client_secrets_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["ingest", "--out", str(tmp_path / "o")]) == 2
    assert "NM_GMAIL_CLIENT_SECRETS" in capsys.readouterr().err


def test_ingest_exits_2_on_bad_since(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["ingest", "--since", "lots", "--out", str(tmp_path / "o")]) == 2
    assert "since" in capsys.readouterr().err


def test_ingest_exits_2_on_invalid_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NM_FETCH_TIMEOUT", "-1")
    assert main(["ingest", "--out", str(tmp_path / "o")]) == 2
    assert "NM_FETCH_TIMEOUT" in capsys.readouterr().err


def test_ingest_exits_2_on_missing_links_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "nope.txt"
    assert main(["ingest", "--links-file", str(missing), "--out", str(tmp_path / "o")]) == 2
    assert "nope.txt" in capsys.readouterr().err


def test_ingest_exits_2_before_fetching_when_out_dir_has_previous_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    links = tmp_path / "links.txt"
    links.write_text("https://a.com/post\n")
    out = tmp_path / "out"
    out.mkdir()
    (out / "01-old.md").write_text(PREVIOUS)

    def must_not_fetch(timeout: float) -> Any:
        raise AssertionError("fetched before checking --out")

    monkeypatch.setattr(cli, "make_html_fetcher", must_not_fetch)
    assert main(["ingest", "--links-file", str(links), "--out", str(out)]) == 2
    assert "--overwrite" in capsys.readouterr().err


def test_ingest_overwrite_replaces_previous_output(tmp_path: Path) -> None:
    links = tmp_path / "links.txt"
    links.write_text("https://a.com/post\n")
    out = tmp_path / "out"
    out.mkdir()
    (out / "01-old.md").write_text(PREVIOUS)
    assert main(["ingest", "--links-file", str(links), "--out", str(out), "--overwrite"]) == 0
    assert sorted(p.name for p in out.iterdir()) == ["01-post-a.md"]


def test_ingest_exits_1_when_writing_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    links = tmp_path / "links.txt"
    links.write_text("https://a.com/post\n")

    def disk_full(*args: Any, **kwargs: Any) -> Any:
        raise OSError("No space left on device")

    monkeypatch.setattr(cli, "write_sources", disk_full)
    assert main(["ingest", "--links-file", str(links), "--out", str(tmp_path / "o")]) == 1
    assert "No space left" in capsys.readouterr().err


def test_ingest_network_error_reading_inbox_exits_1_not_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def reset(settings: Any) -> Any:
        raise ConnectionResetError(104, "Connection reset by peer")

    monkeypatch.setattr(cli, "build_gmail_client", reset)
    assert main(["ingest", "--out", str(tmp_path / "o")]) == 1
    err = capsys.readouterr().err
    assert "Connection reset" in err
    assert "Config error" not in err

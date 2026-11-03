from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from fakes import (
    DRAFT,
    FIXTURES,
    VOICE,
    FakeModel,
    critic_reply,
    fake,
    illustrator_reply,
    task_call,
)
from newsletter_machine import cli_common, cli_issue, config
from newsletter_machine.cli import main
from newsletter_machine.ingest import read_sources

CITED = "https://example.com/why-agent-demos-fail"
DRAFT_WITH_FAKE_LINK = DRAFT + "- [Made up](https://made.up/x)\n"
FULL_RUN = (
    task_call("researcher", "go", "1"),
    task_call("writer", "Lead with the 31% drop.", "2"),
    task_call("voice-critic", "check", "3"),
    "Done: v1 is ready.",
)


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("NM_VOICE_DIR", str(VOICE))
    for name in ("writer", "critic", "editor", "fast"):
        monkeypatch.setenv(f"NM_{name.upper()}_MODEL", f"fake:{name}")
    monkeypatch.setenv("NM_MAX_REVISIONS", "1")
    monkeypatch.setenv("NM_ILLUSTRATOR_MODEL", "fake:illustrator")


def _use_models(
    monkeypatch: pytest.MonkeyPatch,
    *,
    editor: Sequence[Any] = FULL_RUN,
    writer: Sequence[Any] = (DRAFT_WITH_FAKE_LINK,),
    critic: Sequence[Any] = (),
    fast: Sequence[Any] = ("- the 31% number",),
    illustrator: Sequence[Any] = (),
) -> dict[str, str]:
    critic = critic or (critic_reply(),)
    replies = {
        "fake:editor": editor,
        "fake:writer": writer,
        "fake:critic": critic,
        "fake:fast": fast,
        "fake:illustrator": illustrator or (illustrator_reply(),),
    }
    seen: dict[str, str] = {}

    def _make(model: str, api_key: str) -> FakeModel:
        seen[model] = api_key
        return fake(*replies[model])

    monkeypatch.setattr(cli_issue, "make_chat_model", _make)
    return seen


def _issue(tmp_path: Path, *extra: str) -> int:
    return main(["issue", "--out", str(tmp_path / "issue.md"), *extra])


def _from_fixtures(tmp_path: Path, *extra: str) -> int:
    return _issue(tmp_path, "--sources", str(FIXTURES), *extra)


def test_issue_from_sources_writes_draft_critique_and_notes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seen = _use_models(monkeypatch)
    assert _from_fixtures(tmp_path, "--angle", "evals") == 0
    draft = (tmp_path / "issue.md").read_text()
    assert draft.startswith("# Evals are the moat")
    assert draft.endswith(f"## Sources\n\n- [Why agent demos fail in production]({CITED})\n")
    critique = (tmp_path / "issue.critique.md").read_text()
    assert critique.startswith("# Voice critique: issue.md (draft v1)")
    notes = (tmp_path / "issue.notes.md").read_text()
    assert "Done: v1 is ready." in notes and "https://made.up/x" in notes
    assert "- the 31% number" in notes
    out = capsys.readouterr().out
    assert "Using 1 of 2 sources (1 failed source skipped)" in out
    assert "Editor: v1 (" in out
    assert "issue.md" in out and "final draft v1" in out
    assert "Critique:" in out and "issue.critique.md" in out and "issue.notes.md" in out
    assert seen == {f"fake:{n}": "k" for n in ("editor", "writer", "critic", "fast", "illustrator")}
    assert not (tmp_path / "issue.sources").exists()


def test_issue_ingests_links_file_into_sources_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _use_models(monkeypatch)
    links = tmp_path / "links.txt"
    links.write_text(f"{CITED} evals are the moat\nhttps://example.com/paywalled\n")
    monkeypatch.setattr(cli_common, "ingest_links", lambda links, **kw: read_sources(FIXTURES))
    assert _issue(tmp_path, "--links-file", str(links)) == 0
    written = sorted(p.name for p in (tmp_path / "issue.sources").iterdir())
    assert written == ["01-why-agent-demos-fail-in-production.md", "02-a-paywalled-post.md"]
    assert (tmp_path / "issue.md").exists()
    assert "Wrote 2 files to" in capsys.readouterr().out


def test_issue_with_no_links_exits_0_without_model_calls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seen = _use_models(monkeypatch)
    links = tmp_path / "links.txt"
    links.write_text("# nothing this week\n")
    assert _issue(tmp_path, "--links-file", str(links)) == 0
    assert "nothing to draft" in capsys.readouterr().out
    assert not (tmp_path / "issue.md").exists()
    assert set(seen) <= {f"fake:{n}" for n in ("editor", "writer", "critic", "fast", "illustrator")}


def test_issue_gmail_failure_exits_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _use_models(monkeypatch)

    def _boom(settings: Any) -> Any:
        raise ConnectionResetError("reset by peer")

    monkeypatch.setattr(cli_common, "build_gmail_client", _boom)
    assert _issue(tmp_path) == 1
    assert "Reading the inbox failed: reset by peer" in capsys.readouterr().err


def test_issue_runs_the_critic_itself_when_the_editor_skipped_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    lead = (task_call("researcher", "go", "1"), task_call("writer", "brief", "2"), "Done.")
    _use_models(monkeypatch, editor=lead)
    assert _from_fixtures(tmp_path) == 0
    assert (tmp_path / "issue.critique.md").read_text().startswith("# Voice critique: issue.md")
    assert "- Draft v1: " in (tmp_path / "issue.notes.md").read_text()


def test_issue_without_any_draft_exits_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _use_models(monkeypatch, editor=(task_call("writer", "b", "1"), "gave up"), writer=(" ",))
    assert _from_fixtures(tmp_path) == 1
    err = capsys.readouterr().err
    assert "without a draft" in err and "writer-1 failed" in err
    assert not (tmp_path / "issue.md").exists()


def test_issue_keeps_draft_and_notes_when_the_final_critique_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lead = (task_call("writer", "brief", "1"), "Done.")
    _use_models(monkeypatch, editor=lead, critic=(AIMessage(content="no tool call"),) * 30)

    def _broken(*args: Any) -> Any:
        raise ConnectionResetError("critic down")

    monkeypatch.setattr(cli_issue, "critique_version", _broken)
    assert _from_fixtures(tmp_path) == 1
    assert "Critic failed: critic down (draft kept at" in capsys.readouterr().err
    assert (tmp_path / "issue.md").exists() and (tmp_path / "issue.notes.md").exists()
    assert not (tmp_path / "issue.critique.md").exists()


def test_issue_exits_1_when_the_editor_run_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _use_models(monkeypatch, editor=())  # the lead model has no reply
    assert _from_fixtures(tmp_path) == 1
    assert "Editor failed" in capsys.readouterr().err
    assert not (tmp_path / "issue.md").exists()


def test_issue_exits_2_when_outputs_exist_before_any_model_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seen = _use_models(monkeypatch)
    (tmp_path / "issue.notes.md").write_text("mine")
    assert _from_fixtures(tmp_path) == 2
    assert "--overwrite" in capsys.readouterr().err
    assert seen == {}


def test_issue_overwrite_replaces_all_outputs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _use_models(monkeypatch)
    for name in ("issue.md", "issue.critique.md", "issue.notes.md"):
        (tmp_path / name).write_text("old")
    assert _from_fixtures(tmp_path, "--overwrite") == 0
    assert (tmp_path / "issue.notes.md").read_text() != "old"
    assert (tmp_path / "issue.critique.md").read_text() != "old"


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (("--sources", str(FIXTURES), "--since", "7d"), "--since"),
        (("--links-file", str(FIXTURES / "links.txt"), "--since", "7d"), "--since"),
        (("--sources", "/no/such/dir"), "not a directory"),
        (("--since", "yesterday"), "since must look like"),
    ],
)
def test_issue_exits_2_on_bad_inputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    extra: tuple[str, ...],
    message: str,
) -> None:
    _use_models(monkeypatch)
    assert _issue(tmp_path, *extra) == 2
    assert message in capsys.readouterr().err


def test_issue_exits_2_without_api_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert _from_fixtures(tmp_path) == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err


def test_issue_exits_1_when_every_source_failed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _use_models(monkeypatch)
    sources = tmp_path / "src"
    sources.mkdir()
    failed = FIXTURES / "02-failed-source.md"
    (sources / failed.name).write_text(failed.read_text())
    assert _issue(tmp_path, "--sources", str(sources)) == 1
    assert "No usable sources" in capsys.readouterr().err


def test_issue_exits_2_when_sources_folder_already_holds_ingest_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _use_models(monkeypatch)
    folder = tmp_path / "issue.sources"
    folder.mkdir()
    fixture = FIXTURES / "01-why-agent-demos-fail-in-production.md"
    (folder / fixture.name).write_text(fixture.read_text())
    links = tmp_path / "links.txt"
    links.write_text(f"{CITED}\n")
    assert _issue(tmp_path, "--links-file", str(links)) == 2
    assert "--overwrite" in capsys.readouterr().err


def _fail_writes_to(monkeypatch: pytest.MonkeyPatch, suffix: str) -> None:
    original = Path.write_text

    def _write(self: Path, *args: Any, **kwargs: Any) -> int:
        if self.name.endswith(suffix):
            raise PermissionError("read-only disk")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", _write)


def test_issue_exits_1_when_the_draft_cannot_be_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _use_models(monkeypatch)
    _fail_writes_to(monkeypatch, ".issue.md")  # write_atomic's temp file
    assert _from_fixtures(tmp_path) == 1
    assert "Could not write the draft: read-only disk" in capsys.readouterr().err


def test_issue_exits_1_when_the_critique_cannot_be_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _use_models(monkeypatch)
    _fail_writes_to(monkeypatch, ".critique.md")
    assert _from_fixtures(tmp_path) == 1
    assert "Could not write the critique: read-only disk" in capsys.readouterr().err
    assert (tmp_path / "issue.md").exists()


def test_issue_exits_1_when_sources_cannot_be_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seen = _use_models(monkeypatch, editor=())
    links = tmp_path / "links.txt"
    links.write_text(f"{CITED}\n")
    monkeypatch.setattr(cli_common, "ingest_links", lambda links, **kw: read_sources(FIXTURES))
    _fail_writes_to(monkeypatch, "-in-production.md")
    assert _issue(tmp_path, "--links-file", str(links)) == 1
    assert "Could not write sources: read-only disk" in capsys.readouterr().err
    assert "fake:editor" in seen  # built, but never invoked


def test_issue_gmail_config_problem_exits_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _use_models(monkeypatch)

    def _no_secrets(settings: Any) -> Any:
        raise config.ConfigError("Gmail client secrets not found")

    monkeypatch.setattr(cli_common, "build_gmail_client", _no_secrets)
    assert _issue(tmp_path) == 2
    assert "Gmail client secrets not found" in capsys.readouterr().err


def test_issue_salvages_the_latest_draft_when_the_editor_stops_early(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _use_models(monkeypatch, editor=(task_call("writer", "brief", "1"),))
    assert _from_fixtures(tmp_path) == 1
    err = capsys.readouterr().err
    assert "Editor stopped early" in err and "kept the latest draft" in err
    assert (tmp_path / "issue.md").exists() and (tmp_path / "issue.critique.md").exists()
    assert "Editor stopped early" in (tmp_path / "issue.notes.md").read_text()


def test_issue_exits_1_when_every_ingested_source_failed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _use_models(monkeypatch)
    links = tmp_path / "links.txt"
    links.write_text("https://example.com/paywalled\n")
    failed = tuple(d for d in read_sources(FIXTURES) if d.status == "failed")
    monkeypatch.setattr(cli_common, "ingest_links", lambda links, **kw: failed)
    assert _issue(tmp_path, "--links-file", str(links)) == 1
    err = capsys.readouterr().err
    assert "No usable sources" in err and "issue.sources" in err and "Config error" not in err


def test_issue_names_the_notes_file_when_only_the_notes_cannot_be_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _use_models(monkeypatch)
    _fail_writes_to(monkeypatch, ".notes.md")
    assert _from_fixtures(tmp_path) == 1
    err = capsys.readouterr().err
    assert "Could not write the notes: read-only disk" in err
    assert (tmp_path / "issue.md").exists()
    assert (tmp_path / "issue.critique.md").exists()  # written before the notes


def test_issue_notes_include_the_critique_the_command_ran_itself(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    lead = (task_call("writer", "brief", "1"), "Done.")
    _use_models(monkeypatch, editor=lead)
    assert _from_fixtures(tmp_path) == 0
    notes = (tmp_path / "issue.notes.md").read_text()
    assert "- Draft v1: no critique summary" not in notes
    assert "- Draft v1: " in notes and " passed, " in notes


def test_issue_checks_prompts_before_fetching_any_link(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _use_models(monkeypatch)
    from newsletter_machine import prompts

    def _broken(name: str) -> Any:
        raise ValueError(f"prompts/{name}.md: 'version' must be an integer")

    monkeypatch.setattr(prompts, "load_prompt", _broken)
    for module in ("drafting", "editor", "researcher"):
        monkeypatch.setattr(f"newsletter_machine.{module}.load_prompt", _broken)
    fetched: list[Any] = []
    monkeypatch.setattr(cli_common, "ingest_links", lambda links, **kw: fetched.append(links))
    links = tmp_path / "links.txt"
    links.write_text(f"{CITED}\n")
    assert _issue(tmp_path, "--links-file", str(links)) == 2
    assert "'version' must be an integer" in capsys.readouterr().err
    assert fetched == [] and not (tmp_path / "issue.sources").exists()


def test_issue_exits_1_when_an_old_critique_cannot_be_removed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _use_models(monkeypatch)
    original = Path.unlink

    def _unlink(self: Path, missing_ok: bool = False) -> None:
        if self.name == "issue.critique.md":
            raise PermissionError("locked")
        original(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", _unlink)
    assert _from_fixtures(tmp_path) == 1
    assert "Could not remove the old critique: locked" in capsys.readouterr().err


def test_issue_rerun_hints_at_reusing_the_ingested_sources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _use_models(monkeypatch)
    folder = tmp_path / "issue.sources"
    folder.mkdir()
    fixture = FIXTURES / "01-why-agent-demos-fail-in-production.md"
    (folder / fixture.name).write_text(fixture.read_text())
    assert _issue(tmp_path, "--links-file", str(tmp_path / "links.txt")) == 2
    err = capsys.readouterr().err
    assert f"--sources {folder}" in err and "--overwrite" in err and "--out directory" not in err


SVG = '<svg xmlns="http://www.w3.org/2000/svg"><rect width="4" height="4"/></svg>'
VISUAL = {
    "purpose": "Shows the gap.",
    "anchor": "Production did not.",
    "kind": "diagram",
    "format": "svg",
    "animated": False,
    "animation_reason": "Static structure.",
    "alt": "Demo box and production box.",
    "caption": "The gap is the point.",
    "code": SVG,
}


def test_issue_places_visuals_and_writes_images(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _use_models(monkeypatch, illustrator=(illustrator_reply(VISUAL),))
    assert _from_fixtures(tmp_path) == 0
    draft = (tmp_path / "issue.md").read_text()
    image = "![Demo box and production box.](issue.images/visual-1.svg)"
    assert f"Production did not.\n\n{image}" in draft
    assert draft.rstrip().endswith(f"({CITED})")
    assert (tmp_path / "issue.images" / "visual-1.svg").read_text().startswith("<svg")
    notes = (tmp_path / "issue.notes.md").read_text()
    assert "## Visuals" in notes and "visual-1" in notes
    assert "Visuals: 1 placed" in capsys.readouterr().out


def test_issue_no_visuals_skips_the_illustrator(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _use_models(monkeypatch, illustrator=(illustrator_reply(VISUAL),))
    assert _from_fixtures(tmp_path, "--no-visuals") == 0
    assert "![" not in (tmp_path / "issue.md").read_text()
    assert not (tmp_path / "issue.images").exists()
    assert "turned off" in (tmp_path / "issue.notes.md").read_text()


def test_issue_illustrator_failure_keeps_the_draft(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _use_models(monkeypatch, illustrator=(AIMessage(content="no structure"),))
    monkeypatch.setattr(
        cli_issue, "illustrate", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    assert _from_fixtures(tmp_path) == 0
    assert (tmp_path / "issue.md").read_text().startswith("# Evals are the moat")
    assert "Illustrator failed: boom" in capsys.readouterr().err
    assert "Illustrator failed: boom" in (tmp_path / "issue.notes.md").read_text()


def test_issue_refuses_existing_images_without_overwrite(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _use_models(monkeypatch)
    (tmp_path / "issue.images").mkdir()
    (tmp_path / "issue.images" / "visual-1.svg").write_text("old")
    assert _from_fixtures(tmp_path) == 2


def test_issue_overwrite_clears_old_visuals_even_when_illustrator_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _use_models(monkeypatch)
    old = tmp_path / "issue.images" / "visual-9.svg"
    old.parent.mkdir()
    old.write_text("old")
    monkeypatch.setattr(
        cli_issue, "illustrate", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    assert _from_fixtures(tmp_path, "--overwrite") == 0
    assert not old.exists()


def test_issue_word_count_ignores_visuals(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _use_models(monkeypatch)
    assert _from_fixtures(tmp_path) == 0
    plain = capsys.readouterr().out
    _use_models(monkeypatch, illustrator=(illustrator_reply(VISUAL),))
    assert _from_fixtures(tmp_path, "--overwrite") == 0
    words = [line for line in plain.splitlines() if line.startswith("Wrote ") and "words" in line]
    assert words[0].split("(")[1] in capsys.readouterr().out

"""``newsletter-machine issue``: ingest the week's links, run the editor, write the draft.

Exit codes as elsewhere: 0 done (or nothing to draft), 1 runtime/model/write failure,
2 configuration or usage error, always before any model call.
"""

import argparse
import logging
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deepagents import CompiledSubAgent
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable

from newsletter_machine.agent import make_chat_model
from newsletter_machine.checklist import Checklist
from newsletter_machine.checks import prose_words
from newsletter_machine.cli_common import (
    DEFAULT_SINCE,
    EXIT_CONFIG,
    EXIT_ERROR,
    InboxError,
    configure_logging,
    ingest_to,
    print_critique_line,
    read_links,
    sources_line,
    write_reported,
)
from newsletter_machine.config import (
    ConfigError,
    IngestSettings,
    Settings,
    load_editor_settings,
    load_ingest_settings,
    load_settings,
)
from newsletter_machine.drafting import (
    OutputPaths,
    SubAgents,
    build_subagents,
    check_outputs,
    check_target,
    output_paths,
)
from newsletter_machine.editor import (
    EditorRun,
    build_editor,
    editor_system_prompt,
    editor_task,
    run_editor,
)
from newsletter_machine.editor_subagents import (
    EditorInputs,
    build_editor_subagents,
    critique_version,
    dropped_links,
)
from newsletter_machine.grounding import load_grounding
from newsletter_machine.illustrator import (
    Illustration,
    build_illustrator,
    illustrate,
    illustrator_system_prompt,
    render_visual_notes,
    write_visuals,
)
from newsletter_machine.ingest import check_out_dir, read_sources
from newsletter_machine.issue_output import (
    NotesInput,
    critique_summary,
    error_lines,
    render_notes,
)
from newsletter_machine.render import BrowserRenderer
from newsletter_machine.researcher import build_researcher, researcher_system_prompt
from newsletter_machine.sources import SourceDoc, parse_since
from newsletter_machine.workspace import (
    CRITIQUES_DIR,
    DRAFTS_DIR,
    file_text,
    latest_version,
    seed_files,
    versioned,
)
from newsletter_machine.writer import usable_sources

logger = logging.getLogger(__name__)

NOTES_SUFFIX = ".notes.md"
SOURCES_SUFFIX = ".sources"
IMAGES_SUFFIX = ".images"
OWN_VISUAL = re.compile(r"visual-\d+\.(?:svg|mmd|png|gif)")  # only files the illustrator names
VISUALS_OFF = "- Visuals turned off (--no-visuals or NM_MAX_VISUALS=0)."


def add_issue_parser(sub: Any) -> None:
    issue = sub.add_parser(
        "issue", help="One command: ingest links, plan, research, draft, critique, revise"
    )
    issue.add_argument("--out", required=True, type=Path, help="Draft file (.md); extras beside it")
    issue.add_argument("--angle", help="Your topic or argument in a line (optional)")
    inputs = issue.add_mutually_exclusive_group()
    inputs.add_argument("--sources", type=Path, help="Reuse a folder written by 'ingest'")
    inputs.add_argument("--links-file", type=Path, help="Read 'URL [note]' lines, not Gmail")
    issue.add_argument("--since", help=f"Gmail window: 7d, 24h, 2w or YYYY-MM-DD ({DEFAULT_SINCE})")
    issue.add_argument("--overwrite", action="store_true", help="Replace earlier outputs")
    issue.add_argument(
        "--no-visuals", action="store_true", help="Skip the illustrator (no diagrams or images)"
    )


@dataclass(frozen=True)
class IssuePaths:
    draft: Path
    critique: Path
    notes: Path
    sources: Path  # where ingest writes this week's source files
    images: Path  # the illustrator's SVG/Mermaid files, linked from the draft


def issue_paths(out: Path) -> IssuePaths:
    """``issue.md`` -> ``issue.critique.md``, ``issue.notes.md``, ``issue.sources/`` beside it."""
    base = output_paths(out)
    return IssuePaths(
        draft=base.draft,
        critique=base.critique,
        notes=out.with_name(f"{out.stem}{NOTES_SUFFIX}"),
        sources=out.with_name(f"{out.stem}{SOURCES_SUFFIX}"),
        images=out.with_name(f"{out.stem}{IMAGES_SUFFIX}"),
    )


def _check_images(images: Path, *, overwrite: bool) -> None:
    if images.exists() and not images.is_dir():
        raise NotADirectoryError(f"{images} exists and is not a directory.")
    if images.is_dir() and any(images.iterdir()) and not overwrite:
        raise FileExistsError(f"{images} holds visuals from an earlier run; pass --overwrite.")


def _check_paths(paths: IssuePaths, *, overwrite: bool, ingesting: bool) -> None:
    check_outputs(OutputPaths(paths.draft, paths.critique), overwrite=overwrite)
    check_target(paths.notes, overwrite=overwrite)
    _check_images(paths.images, overwrite=overwrite)
    if not ingesting:
        return
    try:
        check_out_dir(paths.sources, overwrite=overwrite)
    except FileExistsError:
        raise FileExistsError(
            f"{paths.sources} already holds sources from an earlier run: reuse them with "
            f"--sources {paths.sources}, or pass --overwrite to fetch the links again."
        ) from None


@dataclass(frozen=True)
class _Agents:
    """Models and rendered prompts, built before any fetch so a broken prompt exits 2 early."""

    phase3: SubAgents
    researcher: Runnable[Any, Any]
    editor_model: BaseChatModel
    editor_prompt: str
    checklist: Checklist
    max_revisions: int
    illustrator: CompiledSubAgent | None  # None when visuals are off
    max_visuals: int
    render_visuals: bool = False
    chromium_path: str = ""


@dataclass(frozen=True)
class _Job:
    paths: IssuePaths
    agents: _Agents
    ingest: IngestSettings | None  # None when reusing --sources
    since: datetime


def _build_agents(settings: Settings, *, visuals: bool = True) -> _Agents:
    editor = load_editor_settings(settings)
    grounding = load_grounding(settings.voice_dir)
    key = settings.anthropic_api_key
    phase3 = build_subagents(
        grounding,
        make_chat_model(settings.writer_model, key),
        make_chat_model(settings.critic_model, key),
    )
    fast = make_chat_model(settings.fast_model, key)
    illustrator = None
    if visuals and editor.max_visuals:
        illustrator = build_illustrator(
            make_chat_model(editor.illustrator_model, key),
            illustrator_system_prompt(editor.max_visuals),
        )
    return _Agents(
        phase3=phase3,
        researcher=build_researcher(fast, researcher_system_prompt()),
        editor_model=make_chat_model(editor.editor_model, key),
        editor_prompt=editor_system_prompt(editor.max_revisions),
        checklist=grounding.checklist,
        max_revisions=editor.max_revisions,
        illustrator=illustrator,
        max_visuals=editor.max_visuals,
        render_visuals=editor.render_visuals,
        chromium_path=editor.chromium_path,
    )


def _prepare(args: argparse.Namespace) -> _Job:
    """Everything that can fail before a model call or a fetch (exit 2)."""
    settings = load_settings()
    configure_logging()
    if args.since is not None and (args.sources is not None or args.links_file is not None):
        raise ValueError(
            "--since reads Gmail; it cannot be combined with --sources or --links-file."
        )
    paths = issue_paths(args.out)
    ingesting = args.sources is None
    _check_paths(paths, overwrite=args.overwrite, ingesting=ingesting)
    ingest = load_ingest_settings() if ingesting else None
    since = parse_since(args.since or DEFAULT_SINCE, datetime.now(UTC))
    agents = _build_agents(settings, visuals=not getattr(args, "no_visuals", False))
    return _Job(paths, agents, ingest, since)


class IngestRunError(Exception):
    """Ingesting this week's links failed at runtime (exit 1): a write, or nothing usable."""


def _gather(job: _Job, args: argparse.Namespace) -> tuple[SourceDoc, ...]:
    """Sources from ``--sources`` or freshly ingested links; () when there are no links."""
    if job.ingest is None:
        docs, where = read_sources(args.sources), args.sources
    else:
        links = read_links(job.ingest, job.since, args.links_file, datetime.now(UTC))
        if not links:
            return ()
        try:
            docs = ingest_to(job.ingest, links, job.paths.sources, overwrite=args.overwrite)
        except OSError as exc:
            raise IngestRunError(f"Could not write sources: {exc}") from exc
        where = job.paths.sources
    if not usable_sources(docs):
        raise IngestRunError(f"No usable sources: every link failed to ingest (see {where}).")
    return docs


@dataclass(frozen=True)
class _Pipeline:
    editor: Any
    inputs: EditorInputs
    critic: CompiledSubAgent


def _pipeline(job: _Job, docs: tuple[SourceDoc, ...], angle: str | None) -> _Pipeline:
    agents = job.agents
    inputs = EditorInputs(
        docs=docs,
        angle=angle,
        checklist=agents.checklist,
        max_revisions=agents.max_revisions,
        draft_name=job.paths.draft.name,
        writer_version=agents.phase3.writer_version,
        critic_version=agents.phase3.critic_version,
    )
    subagents = build_editor_subagents(
        inputs,
        researcher=agents.researcher,
        writer=agents.phase3.writer,
        critic=agents.phase3.critic,
    )
    editor = build_editor(agents.editor_model, subagents, agents.editor_prompt)
    return _Pipeline(editor, inputs, agents.phase3.critic)


def _progress(files: Any, version: int, final: Mapping[str, Any] | None) -> str:
    parts = []
    for v in range(1, version + 1):
        summary = final if v == version and final else critique_summary(files, v)
        parts.append(f"v{v} ({summary['failed']} failed)" if summary else f"v{v} (not critiqued)")
    return "Editor: " + ", ".join(parts)


@dataclass(frozen=True)
class _FinalCritique:
    markdown: str
    summary: Mapping[str, Any]


def _final_critique(pipe: _Pipeline, run: EditorRun, draft: str, version: int) -> _FinalCritique:
    """The editor's critique of the final version, or a fresh one when it has none."""
    existing = file_text(run.files, versioned(CRITIQUES_DIR, version, "md"))
    summary = critique_summary(run.files, version)
    if existing and summary:
        return _FinalCritique(existing, summary)
    logger.info("No critique for draft v%d; running the critic once more", version)
    result = critique_version(pipe.inputs, pipe.critic, draft, version)
    return _FinalCritique(result.markdown, result.summary)


def _try_critique(
    pipe: _Pipeline, run: EditorRun, draft: str, version: int
) -> _FinalCritique | Exception:
    """The final critique, or the exception that stopped it (reported after the notes)."""
    try:
        return _final_critique(pipe, run, draft, version)
    except Exception as exc:  # network/API failures surface as many types
        logger.debug("Critic run failed", exc_info=True)
        return exc


def _final_summary(final: _FinalCritique | Exception) -> Mapping[str, Any] | None:
    return final.summary if isinstance(final, _FinalCritique) else None


def _notes_text(
    pipe: _Pipeline,
    run: EditorRun,
    version: int,
    final: _FinalCritique | Exception,
    name: str,
    visuals: str,
) -> str:
    summary = run.summary or (f"Editor stopped early: {run.error}" if run.error else "")
    notes = NotesInput(
        draft_name=name,
        final_version=version,
        files=run.files,
        docs=pipe.inputs.docs,
        summary=summary,
        dropped=dropped_links(run.files, version),
        final_summary=_final_summary(final),
        visuals=visuals,
    )
    return render_notes(notes)


def _illustrate(job: _Job, pipe: _Pipeline, draft: str) -> tuple[str, str]:
    """``(draft to write, Visuals notes)``; a failure keeps the plain draft and is reported."""
    agents = job.agents
    try:
        _clear_images(job.paths.images)  # old visuals never match the new draft
    except OSError as exc:
        print(f"Could not clear old visuals: {exc}", file=sys.stderr)
        return draft, f"- Could not clear old visuals: {exc}"
    if agents.illustrator is None:
        return draft, VISUALS_OFF
    renderer = BrowserRenderer(agents.chromium_path or None) if agents.render_visuals else None
    try:
        result: Illustration = illustrate(
            agents.illustrator,
            draft,
            pipe.inputs.docs,
            max_visuals=agents.max_visuals,
            image_dir=job.paths.images.name,
            renderer=renderer,
        )
        write_visuals(result, job.paths.images)
    except Exception as exc:  # network/API/model-output/write failures: visuals are optional
        logger.debug("Illustrator failed", exc_info=True)
        print(f"Illustrator failed: {exc} (draft kept without visuals)", file=sys.stderr)
        return draft, f"- Illustrator failed: {exc}"
    finally:
        if renderer is not None:
            renderer.close()
    animated = sum(1 for v in result.visuals if v.animated)
    rendered = sum(1 for v in result.visuals if v.raster is not None)
    print(
        f"Visuals: {len(result.visuals)} placed ({animated} animated, {rendered} rendered), "
        f"{len(result.rejected)} dropped -> {job.paths.images}"
    )
    failed = [v for v in result.visuals if v.render_error]
    if failed:
        print(f"Rendering failed: {failed[0].render_error} (SVG linked instead)", file=sys.stderr)
    return result.draft, render_visual_notes(result)


def _clear_images(images: Path) -> None:
    """Remove an earlier run's visuals (only reached under --overwrite or an empty folder).

    Only ``visual-N.svg/.mmd/.png/.gif`` go: anything else Varun put there stays."""
    if images.is_dir():
        for old in images.iterdir():
            if OWN_VISUAL.fullmatch(old.name) and (old.is_file() or old.is_symlink()):
                old.unlink()


def _write_draft(job: _Job, draft: str, version: int, prose: str | None = None) -> bool:
    """Write ``draft``; the word count is of ``prose`` (the draft without visuals)."""
    if not write_reported(job.paths.draft, draft, "draft"):
        return False
    try:
        job.paths.critique.unlink(missing_ok=True)  # an earlier run's critique no longer matches
    except OSError as exc:
        print(f"Could not remove the old critique: {exc}", file=sys.stderr)
        return False
    words = prose_words(draft if prose is None else prose)
    print(f"Wrote {job.paths.draft} ({words} words, final draft v{version})")
    return True


def _write_critique(job: _Job, final: _FinalCritique | Exception) -> int:
    if isinstance(final, Exception):
        print(f"Critic failed: {final} (draft kept at {job.paths.draft})", file=sys.stderr)
        return EXIT_ERROR
    if not write_reported(job.paths.critique, final.markdown, "critique"):
        return EXIT_ERROR
    print_critique_line(final.summary, job.paths.critique)
    return 0


def _finalise(job: _Job, pipe: _Pipeline, run: EditorRun) -> int:
    """Write the latest draft as saved (Sources already rebuilt), the notes, the critique."""
    version = latest_version(run.files, DRAFTS_DIR, "md")
    draft = file_text(run.files, versioned(DRAFTS_DIR, version, "md")) if version else None
    if not draft:
        errors = "; ".join(error_lines(run.files))
        print(f"Editor finished without a draft. {errors}".rstrip(), file=sys.stderr)
        return EXIT_ERROR
    placed, visuals = _illustrate(job, pipe, draft)
    if not _write_draft(job, placed, version, prose=draft):
        return EXIT_ERROR
    final = _try_critique(pipe, run, draft, version)  # the critique judges the prose only
    print(_progress(run.files, version, _final_summary(final)))
    code = _write_critique(job, final)  # before the notes: a notes failure must not lose it
    notes = _notes_text(pipe, run, version, final, job.paths.draft.name, visuals)
    if not write_reported(job.paths.notes, notes, "notes"):
        return EXIT_ERROR
    print(f"Notes -> {job.paths.notes}")
    return code


def run_issue(args: argparse.Namespace) -> int:
    try:
        job = _prepare(args)  # settings, prompts (KeyError), paths, model packages
        docs = _gather(job, args)
    except (InboxError, IngestRunError) as exc:
        logger.debug("Ingest failed", exc_info=True)
        prefix = "Reading the inbox failed: " if isinstance(exc, InboxError) else ""
        print(f"{prefix}{exc}", file=sys.stderr)
        return EXIT_ERROR
    except (ConfigError, ValueError, KeyError, OSError, ImportError) as exc:
        # usage problems only: _gather's runtime failures are IngestRunError/InboxError above
        print(f"Config error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    if not docs:
        print("No links found; nothing to draft.")
        return 0
    pipe = _pipeline(job, docs, args.angle)
    print(sources_line(docs))
    try:
        run = run_editor(pipe.editor, editor_task(docs, args.angle), seed_files(docs))
    except Exception as exc:  # network/API failures surface as many types
        logger.debug("Editor run failed", exc_info=True)
        print(f"Editor failed: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if run.error:
        print(f"Editor stopped early: {run.error}; kept the latest draft.", file=sys.stderr)
    code = _finalise(job, pipe, run)
    return code or (EXIT_ERROR if run.error else 0)

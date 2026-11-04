"""``newsletter-machine issue``: ingest the week's links, run the editor, write the draft.

Exit codes as elsewhere: 0 done (or nothing to draft), 1 runtime/model/write failure,
2 configuration or usage error, always before any model call.
"""

import argparse
import logging
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
from newsletter_machine.cli_issue_series import (
    SeriesJob,
    SeriesModels,
    SeriesTarget,
    add_series_options,
    adjust_outline,
    continuity_note,
    filter_sources,
    finish_series,
    series_grounding,
    series_job,
    series_target,
)
from newsletter_machine.config import (
    ConfigError,
    IngestSettings,
    Settings,
    load_editor_settings,
    load_ingest_settings,
    load_planner_model,
    load_relevance_model,
    load_settings,
    load_summary_model,
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
from newsletter_machine.ingest import SOURCES_SUFFIX, check_out_dir, read_sources
from newsletter_machine.issue_output import (
    NotesInput,
    critique_summary,
    error_lines,
    render_notes,
)
from newsletter_machine.relevance import source_lines
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
PARKED_SUFFIX = ".parked.md"


def add_issue_parser(sub: Any) -> None:
    issue = sub.add_parser(
        "issue", help="One command: ingest links, plan, research, draft, critique, revise"
    )
    issue.add_argument("--out", required=True, type=Path, help="Draft file (.md); extras beside it")
    steer = issue.add_mutually_exclusive_group()
    steer.add_argument("--angle", help="Your topic or argument in a line (optional)")
    add_series_options(issue, steer)
    inputs = issue.add_mutually_exclusive_group()
    inputs.add_argument("--sources", type=Path, help="Reuse a folder written by 'ingest'")
    inputs.add_argument("--links-file", type=Path, help="Read 'URL [note]' lines, not Gmail")
    issue.add_argument("--since", help=f"Gmail window: 7d, 24h, 2w or YYYY-MM-DD ({DEFAULT_SINCE})")
    issue.add_argument("--overwrite", action="store_true", help="Replace earlier outputs")


@dataclass(frozen=True)
class IssuePaths:
    draft: Path
    critique: Path
    notes: Path
    sources: Path  # where ingest writes this week's source files
    parked: Path  # series mode: the sources the relevance filter set aside


def issue_paths(out: Path) -> IssuePaths:
    """``issue.md`` -> ``issue.critique.md``, ``issue.notes.md``, ``issue.sources/`` beside it."""
    base = output_paths(out)
    return IssuePaths(
        draft=base.draft,
        critique=base.critique,
        notes=out.with_name(f"{out.stem}{NOTES_SUFFIX}"),
        sources=out.with_name(f"{out.stem}{SOURCES_SUFFIX}"),
        parked=out.with_name(f"{out.stem}{PARKED_SUFFIX}"),
    )


def _check_paths(paths: IssuePaths, *, overwrite: bool, ingesting: bool) -> None:
    check_outputs(OutputPaths(paths.draft, paths.critique), overwrite=overwrite)
    check_target(paths.notes, overwrite=overwrite)
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


@dataclass(frozen=True)
class _Job:
    paths: IssuePaths
    agents: _Agents
    ingest: IngestSettings | None  # None when reusing --sources
    since: datetime
    series: SeriesJob | None = None  # set by --series


def _build_agents(settings: Settings, target: SeriesTarget | None = None) -> _Agents:
    editor = load_editor_settings(settings)
    grounding = load_grounding(settings.voice_dir)
    if target is not None:  # series checks join the checklist the writer and critic see
        grounding = series_grounding(grounding, target)
    key = settings.anthropic_api_key
    phase3 = build_subagents(
        grounding,
        make_chat_model(settings.writer_model, key),
        make_chat_model(settings.critic_model, key),
    )
    fast = make_chat_model(settings.fast_model, key)
    return _Agents(
        phase3=phase3,
        researcher=build_researcher(fast, researcher_system_prompt()),
        editor_model=make_chat_model(editor.editor_model, key),
        editor_prompt=editor_system_prompt(editor.max_revisions),
        checklist=grounding.checklist,
        max_revisions=editor.max_revisions,
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
    target = series_target(args, paths.parked)  # before any model is built
    ingest = load_ingest_settings() if ingesting else None
    since = parse_since(args.since or DEFAULT_SINCE, datetime.now(UTC))
    agents = _build_agents(settings, target)
    series = None
    if target is not None:
        key = settings.anthropic_api_key
        models = SeriesModels(
            relevance=make_chat_model(load_relevance_model(settings), key),
            summary=make_chat_model(load_summary_model(settings), key),
            planner=None
            if target.keep_outline
            else make_chat_model(load_planner_model(settings), key),
        )
        series = series_job(target, models)
        print(f"Drafting {series.label}")
        note = continuity_note(target)
        if note:
            print(note)
    return _Job(paths, agents, ingest, since, series)


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
class _Steer:
    """What steers the run: Varun's ``--angle``, or a series part (angle text plus notes)."""

    angle: str | None
    series: str = ""  # the series label; blank for a plain issue
    parked: tuple[str, ...] = ()
    unchecked: tuple[str, ...] = ()
    context: str = ""  # series continuity facts for the critic; blank for a plain issue


@dataclass(frozen=True)
class _Pipeline:
    editor: Any
    inputs: EditorInputs
    critic: CompiledSubAgent
    steer: _Steer


def _pipeline(job: _Job, docs: tuple[SourceDoc, ...], steer: _Steer) -> _Pipeline:
    agents = job.agents
    inputs = EditorInputs(
        docs=docs,
        angle=steer.angle,
        checklist=agents.checklist,
        max_revisions=agents.max_revisions,
        draft_name=job.paths.draft.name,
        writer_version=agents.phase3.writer_version,
        critic_version=agents.phase3.critic_version,
        series_label=steer.series,
        series_context=steer.context,
    )
    subagents = build_editor_subagents(
        inputs,
        researcher=agents.researcher,
        writer=agents.phase3.writer,
        critic=agents.phase3.critic,
    )
    editor = build_editor(agents.editor_model, subagents, agents.editor_prompt)
    return _Pipeline(editor, inputs, agents.phase3.critic, steer)


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
    pipe: _Pipeline, run: EditorRun, version: int, final: _FinalCritique | Exception, name: str
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
        series=pipe.steer.series,
        parked=pipe.steer.parked,
        unchecked=pipe.steer.unchecked,
    )
    return render_notes(notes)


def _write_draft(job: _Job, draft: str, version: int) -> bool:
    if not write_reported(job.paths.draft, draft, "draft"):
        return False
    try:
        job.paths.critique.unlink(missing_ok=True)  # an earlier run's critique no longer matches
    except OSError as exc:
        print(f"Could not remove the old critique: {exc}", file=sys.stderr)
        return False
    print(f"Wrote {job.paths.draft} ({prose_words(draft)} words, final draft v{version})")
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
    if not _write_draft(job, draft, version):
        return EXIT_ERROR
    final = _try_critique(pipe, run, draft, version)
    print(_progress(run.files, version, _final_summary(final)))
    code = _write_critique(job, final)  # before the notes: a notes failure must not lose it
    notes = _notes_text(pipe, run, version, final, job.paths.draft.name)
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
    if job.series is None:
        return _draft(job, docs, _Steer(args.angle))
    return _draft_series(job, job.series, docs, args)


def _draft_series(
    job: _Job, series: SeriesJob, docs: tuple[SourceDoc, ...], args: argparse.Namespace
) -> int:
    """Filter to on-topic sources; revise the outline when they fit another part better;
    otherwise draft the part, then mark it drafted (exit 0 only)."""
    sources_dir = args.sources or job.paths.sources
    relevance = filter_sources(series, docs, sources_dir)
    if relevance is None:
        return EXIT_ERROR
    if not usable_sources(relevance.kept):
        part = series.target.part.number
        print(f"No on-topic sources for Part {part}; nothing to draft.")
        return 0
    revised = adjust_outline(
        series, relevance, sources_dir, job.paths.draft, overwrite=args.overwrite
    )
    if revised is not None:
        return revised
    lines = source_lines(relevance.parked), source_lines(relevance.unchecked)
    steer = _Steer(series.angle, series.label, *lines, context=series.context)
    code = _draft(job, relevance.kept, steer)
    return finish_series(series, code, job.paths.draft)


def _draft(job: _Job, docs: tuple[SourceDoc, ...], steer: _Steer) -> int:
    pipe = _pipeline(job, docs, steer)
    print(sources_line(docs))
    try:
        run = run_editor(pipe.editor, editor_task(docs, steer.angle), seed_files(docs))
    except Exception as exc:  # network/API failures surface as many types
        logger.debug("Editor run failed", exc_info=True)
        print(f"Editor failed: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if run.error:
        print(f"Editor stopped early: {run.error}; kept the latest draft.", file=sys.stderr)
    code = _finalise(job, pipe, run)
    return code or (EXIT_ERROR if run.error else 0)

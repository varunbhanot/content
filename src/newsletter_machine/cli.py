"""Command-line entry point: hello, ingest, draft, issue, series, weekly and gmail-auth."""

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from newsletter_machine.agent import build_hello_agent, extract_text, make_chat_model
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
from newsletter_machine.cli_issue import add_issue_parser, run_issue
from newsletter_machine.cli_series import add_series_parser, run_series
from newsletter_machine.cli_weekly import add_weekly_parsers, run_gmail_auth, run_weekly_command
from newsletter_machine.config import (
    ConfigError,
    IngestSettings,
    load_ingest_settings,
    load_settings,
)
from newsletter_machine.critic import critic_task, run_critic
from newsletter_machine.critique_report import ReportMeta, render_critique
from newsletter_machine.drafting import (
    OutputPaths,
    SubAgents,
    build_subagents,
    check_outputs,
    output_paths,
    write_atomic,
)
from newsletter_machine.grounding import load_grounding
from newsletter_machine.ingest import check_out_dir, read_sources
from newsletter_machine.sources import InboxLink, SourceDoc, parse_since
from newsletter_machine.writer import run_writer, writer_task

logger = logging.getLogger(__name__)

DEFAULT_QUESTION = (
    "List the hand-written posts, read two of them, and name three concrete traits of "
    "Varun's voice with a short quote for each."
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="newsletter-machine")
    sub = parser.add_subparsers(dest="command", required=True)
    hello = sub.add_parser("hello", help="Smoke-test the agent against the voice corpus")
    hello.add_argument("--question", default=DEFAULT_QUESTION)
    ingest = sub.add_parser("ingest", help="Turn this week's inbox links into source text files")
    ingest.add_argument("--since", default=DEFAULT_SINCE, help="7d, 24h, 2w or YYYY-MM-DD")
    ingest.add_argument("--out", required=True, type=Path, help="Directory for the source files")
    ingest.add_argument(
        "--links-file", type=Path, help="Read 'URL [note]' lines from a file instead of Gmail"
    )
    ingest.add_argument(
        "--overwrite", action="store_true", help="Replace Markdown files already in --out"
    )
    draft = sub.add_parser("draft", help="Write a draft in Varun's voice, then critique it once")
    draft.add_argument("--sources", required=True, type=Path, help="Folder written by 'ingest'")
    draft.add_argument("--angle", help="Your topic or argument in a line (optional)")
    draft.add_argument(
        "--out", required=True, type=Path, help="Draft file (.md); critique beside it"
    )
    draft.add_argument("--overwrite", action="store_true", help="Replace existing draft/critique")
    add_issue_parser(sub)
    add_series_parser(sub)
    add_weekly_parsers(sub)
    return parser


def _run_hello(question: str) -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    configure_logging()
    try:
        agent = build_hello_agent(settings)
        result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    except Exception as exc:  # network/API failures surface as many types
        logger.debug("Agent run failed", exc_info=True)  # traceback with LOG_LEVEL=DEBUG
        print(f"Agent run failed: {exc}", file=sys.stderr)
        return EXIT_ERROR
    print(extract_text(result["messages"][-1].content))
    return 0


def _collect_links(args: argparse.Namespace) -> tuple[IngestSettings, tuple[InboxLink, ...]]:
    """Validate inputs (exit 2 on failure), then read links from the file or Gmail (exit 1)."""
    now = datetime.now(UTC)
    settings = load_ingest_settings()
    configure_logging()
    since = parse_since(args.since, now)
    check_out_dir(args.out, overwrite=args.overwrite)
    return settings, read_links(settings, since, args.links_file, now)


def _run_ingest(args: argparse.Namespace) -> int:
    try:
        settings, links = _collect_links(args)
    except InboxError as exc:
        logger.debug("Reading the inbox failed", exc_info=True)
        print(f"Reading the inbox failed: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except (ConfigError, ValueError, OSError) as exc:  # settings, --since, --out, links file
        print(f"Config error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    if not links:
        print("No links found; nothing to ingest.")
        return 0
    try:
        ingest_to(settings, links, args.out, overwrite=args.overwrite)
    except OSError as exc:
        print(f"Could not write sources: {exc}", file=sys.stderr)
        return EXIT_ERROR
    return 0


@dataclass(frozen=True)
class _DraftJob:
    docs: tuple[SourceDoc, ...]
    checklist: Checklist
    paths: OutputPaths
    task: str
    agents: SubAgents


def _prepare_draft(args: argparse.Namespace) -> _DraftJob:
    """Everything that can fail before a model call (exit 2): settings, sources, voice, out."""
    settings = load_settings()
    configure_logging()
    paths = output_paths(args.out)
    check_outputs(paths, overwrite=args.overwrite)
    docs = read_sources(args.sources)
    task = writer_task(docs, args.angle)
    grounding = load_grounding(settings.voice_dir)
    key = settings.anthropic_api_key
    agents = build_subagents(
        grounding,
        make_chat_model(settings.writer_model, key),
        make_chat_model(settings.critic_model, key),
    )
    return _DraftJob(docs, grounding.checklist, paths, task, agents)


def _report_meta(job: _DraftJob, words: int) -> ReportMeta:
    return ReportMeta(
        draft_name=job.paths.draft.name,
        words=words,
        writer_version=job.agents.writer_version,
        critic_version=job.agents.critic_version,
        checklist_version=job.checklist.version,
    )


def _save_draft(job: _DraftJob, draft: str, words: int) -> int:
    """Write the draft, then drop any critique left from an earlier run (it no longer matches)."""
    try:
        write_atomic(job.paths.draft, f"{draft.rstrip()}\n")
        job.paths.critique.unlink(missing_ok=True)
    except OSError as exc:
        print(f"Could not write the draft: {exc}", file=sys.stderr)
        return EXIT_ERROR
    print(f"Wrote {job.paths.draft} ({words} words)")
    return 0


def _critique_draft(job: _DraftJob, draft: str, words: int) -> int:
    """Run the critic on a saved draft; any failure keeps the draft."""
    try:
        critique = run_critic(job.agents.critic, critic_task(draft, job.docs), job.checklist, draft)
    except Exception as exc:  # network/API failures surface as many types
        logger.debug("Critic run failed", exc_info=True)
        print(f"Critic failed: {exc} (draft kept at {job.paths.draft})", file=sys.stderr)
        return EXIT_ERROR
    markdown = render_critique(critique, _report_meta(job, words))
    if not write_reported(job.paths.critique, markdown, "critique"):
        return EXIT_ERROR
    counts = {
        "passed": critique.passed,
        "failed": critique.failed,
        "not_checked": critique.not_checked,
    }
    print_critique_line(counts, job.paths.critique)
    return 0


def _run_draft(args: argparse.Namespace) -> int:
    try:
        job = _prepare_draft(args)
    except (ConfigError, ValueError, KeyError, OSError, ImportError) as exc:
        # settings, sources, voice files, prompts, --out, model provider package missing
        print(f"Config error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    print(sources_line(job.docs))
    try:
        draft = run_writer(job.agents.writer, job.task)
    except Exception as exc:  # network/API failures surface as many types
        logger.debug("Writer run failed", exc_info=True)
        print(f"Writer failed: {exc}", file=sys.stderr)
        return EXIT_ERROR
    words = prose_words(draft)
    return _save_draft(job, draft, words) or _critique_draft(job, draft, words)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "ingest":
        return _run_ingest(args)
    if args.command == "draft":
        return _run_draft(args)
    if args.command == "issue":
        return run_issue(args)
    if args.command == "series":
        return run_series(args)
    if args.command == "weekly":
        return run_weekly_command(args)
    if args.command == "gmail-auth":
        return run_gmail_auth(args)
    return _run_hello(args.question)

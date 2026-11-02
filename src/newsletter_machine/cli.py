"""Command-line entry point: ``newsletter-machine hello`` and ``newsletter-machine ingest``."""

import argparse
import logging
import os
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from newsletter_machine.agent import build_hello_agent
from newsletter_machine.config import (
    ConfigError,
    IngestSettings,
    load_ingest_settings,
    load_settings,
)
from newsletter_machine.gmail import build_gmail_client, read_inbox_links
from newsletter_machine.ingest import check_out_dir, ingest_links, write_sources
from newsletter_machine.sources import InboxLink, SourceDoc, parse_since, read_links_file
from newsletter_machine.web import make_html_fetcher
from newsletter_machine.youtube import make_transcript_fetcher

logger = logging.getLogger(__name__)

DEFAULT_QUESTION = (
    "List the hand-written posts, read two of them, and name three concrete traits of "
    "Varun's voice with a short quote for each."
)
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_SINCE = "7d"
EXIT_ERROR = 1
EXIT_CONFIG = 2


def extract_text(content: Any) -> str:
    """Flatten Anthropic message content (str or list of blocks) to plain text."""
    if isinstance(content, str):
        return content
    return "".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
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
    return parser


def _configure_logging() -> None:
    """Configure logging after .env is loaded; fall back to INFO on an unknown LOG_LEVEL."""
    requested = os.environ.get("LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()
    level = requested if requested in logging.getLevelNamesMapping() else DEFAULT_LOG_LEVEL
    logging.basicConfig(level=level)
    if level != requested:
        logger.warning("Unknown LOG_LEVEL %r, using %s", requested, DEFAULT_LOG_LEVEL)


def _run_hello(question: str) -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    _configure_logging()
    try:
        agent = build_hello_agent(settings)
        result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    except Exception as exc:  # network/API failures surface as many types
        logger.debug("Agent run failed", exc_info=True)  # traceback with LOG_LEVEL=DEBUG
        print(f"Agent run failed: {exc}", file=sys.stderr)
        return EXIT_ERROR
    print(extract_text(result["messages"][-1].content))
    return 0


class _InboxError(Exception):
    """Reading Gmail failed for a runtime (not configuration) reason."""


def _gmail_links(settings: IngestSettings, since: datetime) -> tuple[InboxLink, ...]:
    client = build_gmail_client(settings)
    links = read_inbox_links(
        client, settings.gmail_label, since, senders=settings.gmail_allowed_senders
    )
    senders = ", ".join(settings.gmail_allowed_senders)
    print(
        f"Found {len(links)} links in label {settings.gmail_label!r} "
        f"from {senders} since {since:%Y-%m-%d}"
    )
    return links


def _collect_links(args: argparse.Namespace) -> tuple[IngestSettings, tuple[InboxLink, ...]]:
    """Validate inputs (exit 2 on failure), then read links from the file or Gmail (exit 1)."""
    now = datetime.now(UTC)
    settings = load_ingest_settings()
    _configure_logging()
    since = parse_since(args.since, now)
    check_out_dir(args.out, overwrite=args.overwrite)
    if args.links_file is not None:
        return settings, read_links_file(args.links_file, now)
    try:
        return settings, _gmail_links(settings, since)
    except ConfigError:
        raise
    except Exception as exc:  # Gmail API / auth / network failures surface as many types
        raise _InboxError(str(exc)) from exc


def _print_summary(docs: tuple[SourceDoc, ...], paths: tuple[Path, ...], out: Path) -> None:
    for doc, path in zip(docs, paths, strict=True):
        suffix = f"  ({doc.detail})" if doc.detail else ""
        print(f"  {doc.status:<8} {path.name}{suffix}")
    counts = Counter(doc.status for doc in docs)
    print(
        f"Wrote {len(paths)} files to {out} "
        f"({counts['ok']} ok, {counts['fallback']} fallback, {counts['failed']} failed)"
    )


def _run_ingest(args: argparse.Namespace) -> int:
    try:
        settings, links = _collect_links(args)
    except _InboxError as exc:
        logger.debug("Reading the inbox failed", exc_info=True)
        print(f"Reading the inbox failed: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except (ConfigError, ValueError, OSError) as exc:  # settings, --since, --out, links file
        print(f"Config error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    if not links:
        print("No links found; nothing to ingest.")
        return 0
    docs = ingest_links(
        links,
        fetch_html=make_html_fetcher(settings.fetch_timeout),
        fetch_transcript=make_transcript_fetcher(
            settings.transcript_languages, timeout=settings.fetch_timeout
        ),
    )
    try:
        paths = write_sources(docs, args.out, overwrite=args.overwrite)
    except OSError as exc:
        print(f"Could not write sources: {exc}", file=sys.stderr)
        return EXIT_ERROR
    _print_summary(docs, paths, args.out)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "ingest":
        return _run_ingest(args)
    return _run_hello(args.question)

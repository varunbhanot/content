"""Helpers shared by the CLI commands: logging, exit codes, the Gmail inbox and summaries."""

import logging
import os
import sys
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from newsletter_machine.browser_fetch import make_browser_fetcher
from newsletter_machine.config import ConfigError, IngestSettings
from newsletter_machine.drafting import write_atomic
from newsletter_machine.gmail import build_gmail_client, read_inbox_links
from newsletter_machine.ingest import ingest_links, write_sources
from newsletter_machine.sources import InboxLink, SourceDoc, read_links_file
from newsletter_machine.web import make_html_fetcher, with_fallback
from newsletter_machine.writer import usable_sources
from newsletter_machine.youtube import make_transcript_fetcher

logger = logging.getLogger(__name__)

DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_SINCE = "7d"
EXIT_ERROR = 1
EXIT_CONFIG = 2


class InboxError(Exception):
    """Reading Gmail failed for a runtime (not configuration) reason."""


def configure_logging() -> None:
    """Configure logging after .env is loaded; fall back to INFO on an unknown LOG_LEVEL."""
    requested = os.environ.get("LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()
    level = requested if requested in logging.getLevelNamesMapping() else DEFAULT_LOG_LEVEL
    logging.basicConfig(level=level)
    if level != requested:
        logger.warning("Unknown LOG_LEVEL %r, using %s", requested, DEFAULT_LOG_LEVEL)


def gmail_links(settings: IngestSettings, since: datetime) -> tuple[InboxLink, ...]:
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


def read_links(
    settings: IngestSettings, since: datetime, links_file: Path | None, now: datetime
) -> tuple[InboxLink, ...]:
    """Links from ``links_file`` (its problems are usage errors) or from Gmail.

    Gmail runtime failures (API, auth, network) become ``InboxError``; ``ConfigError``
    (e.g. missing client secrets) passes through as a configuration problem.
    """
    if links_file is not None:
        return read_links_file(links_file, now)
    try:
        return gmail_links(settings, since)
    except ConfigError:
        raise
    except Exception as exc:  # Gmail API / auth / network failures surface as many types
        raise InboxError(str(exc)) from exc


def fetch_sources(settings: IngestSettings, links: tuple[InboxLink, ...]) -> tuple[SourceDoc, ...]:
    """Ingest each link with the real fetchers (article, browser retry, YouTube transcript)."""
    timeout = settings.fetch_timeout
    return ingest_links(
        links,
        fetch_html=with_fallback(make_html_fetcher(timeout), make_browser_fetcher(timeout)),
        fetch_transcript=make_transcript_fetcher(settings.transcript_languages, timeout=timeout),
    )


def ingest_to(
    settings: IngestSettings, links: tuple[InboxLink, ...], out: Path, *, overwrite: bool
) -> tuple[SourceDoc, ...]:
    """Fetch every link, write ``NN-<slug>.md`` files to ``out`` and print the summary.

    A write failure raises ``OSError`` (a runtime failure, exit 1 for the caller).
    """
    docs = fetch_sources(settings, links)
    paths = write_sources(docs, out, overwrite=overwrite)
    print_ingest_summary(docs, paths, out)
    return docs


def print_ingest_summary(docs: tuple[SourceDoc, ...], paths: tuple[Path, ...], out: Path) -> None:
    for doc, path in zip(docs, paths, strict=True):
        suffix = f"  ({doc.detail})" if doc.detail else ""
        print(f"  {doc.status:<8} {path.name}{suffix}")
    counts = Counter(doc.status for doc in docs)
    print(
        f"Wrote {len(paths)} files to {out} "
        f"({counts['ok']} ok, {counts['fallback']} fallback, {counts['failed']} failed)"
    )


def sources_line(docs: tuple[SourceDoc, ...]) -> str:
    usable = len(usable_sources(docs))
    skipped = len(docs) - usable
    plural = "source" if skipped == 1 else "sources"
    suffix = f" ({skipped} failed {plural} skipped)" if skipped else ""
    return f"Using {usable} of {len(docs)} sources{suffix}"


def write_reported(path: Path, text: str, what: str) -> bool:
    """Write atomically; on failure print "Could not write the <what>" and return False."""
    try:
        write_atomic(path, text)
    except OSError as exc:
        print(f"Could not write the {what}: {exc}", file=sys.stderr)
        return False
    return True


def print_critique_line(counts: Mapping[str, int], path: Path) -> None:
    print(
        f"Critique: {counts['passed']} passed, {counts['failed']} failed, "
        f"{counts['not_checked']} not checked -> {path}"
    )

"""Turn inbox links into source docs and write one Markdown file per source."""

import logging
import os
import re
import shutil
import tempfile
import unicodedata
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path

import yaml

from newsletter_machine.articles import extract_article
from newsletter_machine.sources import (
    InboxLink,
    SourceDoc,
    SourceKind,
    failed_doc,
    youtube_video_id,
)
from newsletter_machine.web import HtmlFetcher
from newsletter_machine.youtube import TranscriptFetcher, ingest_youtube

logger = logging.getLogger(__name__)

MAX_SLUG_CHARS = 60
DEFAULT_SLUG = "source"
FRONT_MATTER_FIELDS = ("url", "title", "kind", "status", "note", "detail")
NON_SLUG_CHARS = re.compile(r"[^a-z0-9]+")
YAML_LINE_WIDTH = 1000
OUTPUT_NAME = re.compile(r"\d{2,}-[a-z0-9-]+\.md")
OUTPUT_SIGNATURE = "---\nurl: "  # every file render_source writes starts with this


def _ingest_one(
    link: InboxLink, fetch_html: HtmlFetcher, fetch_transcript: TranscriptFetcher
) -> SourceDoc:
    video_id = youtube_video_id(link.url)
    kind: SourceKind = "youtube" if video_id else "article"
    try:
        if video_id:
            return ingest_youtube(link, video_id, fetch_transcript, fetch_html)
        return extract_article(link, fetch_html)
    except Exception as exc:  # one bad source must never abort the week's run
        logger.warning("Ingesting %s failed", link.url, exc_info=True)
        return failed_doc(link, kind, f"{type(exc).__name__}: {exc}")


def ingest_links(
    links: Iterable[InboxLink],
    *,
    fetch_html: HtmlFetcher,
    fetch_transcript: TranscriptFetcher,
) -> tuple[SourceDoc, ...]:
    """Ingest each link in order; failures become ``status='failed'`` docs."""
    return tuple(_ingest_one(link, fetch_html, fetch_transcript) for link in links)


def slugify(title: str) -> str:
    """ASCII, lowercase, hyphenated, at most ``MAX_SLUG_CHARS`` characters."""
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    slug = NON_SLUG_CHARS.sub("-", ascii_title.lower()).strip("-")
    return slug[:MAX_SLUG_CHARS].rstrip("-") or DEFAULT_SLUG


def _one_line(value: str) -> str:
    return " ".join(value.split())


def render_source(doc: SourceDoc) -> str:
    """Markdown with YAML front-matter (url, title, kind, status, note, detail)."""
    fields = asdict(doc)
    meta = {name: _one_line(str(fields[name])) for name in FRONT_MATTER_FIELDS}
    front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=YAML_LINE_WIDTH)
    return f"---\n{front}---\n\n# {meta['title']}\n\n{doc.text}\n"


def _is_previous_output(path: Path) -> bool:
    if not (path.is_file() and OUTPUT_NAME.fullmatch(path.name)):
        return False
    with path.open(encoding="utf-8", errors="replace") as handle:
        return handle.read(len(OUTPUT_SIGNATURE)) == OUTPUT_SIGNATURE


def _previous_output(out_dir: Path) -> tuple[Path, ...]:
    """Files an earlier ingest wrote (name AND front-matter match); others are never touched."""
    if not out_dir.is_dir():
        return ()
    return tuple(sorted(p for p in out_dir.iterdir() if _is_previous_output(p)))


def check_out_dir(out_dir: Path, *, overwrite: bool) -> tuple[Path, ...]:
    """Fail fast (before any fetching) on a bad ``--out``; returns earlier ingest output."""
    if out_dir.exists() and not out_dir.is_dir():
        raise NotADirectoryError(f"--out {out_dir} exists and is not a directory.")
    previous = _previous_output(out_dir)
    if previous and not overwrite:
        raise FileExistsError(
            f"{out_dir} already has {len(previous)} ingested source file(s); "
            "pick a new --out directory or pass --overwrite."
        )
    return previous


def _targets(docs: Iterable[SourceDoc], out_dir: Path) -> tuple[tuple[Path, SourceDoc], ...]:
    return tuple(
        (out_dir / f"{index:02d}-{slugify(doc.title)}.md", doc)
        for index, doc in enumerate(docs, start=1)
    )


def _write_staged(targets: tuple[tuple[Path, SourceDoc], ...], out_dir: Path) -> None:
    """Render everything into a staging dir first, so a failed write leaves --out untouched."""
    staging = Path(tempfile.mkdtemp(prefix=".ingest-", dir=out_dir))
    try:
        for path, doc in targets:
            (staging / path.name).write_text(render_source(doc), encoding="utf-8")
        for path, _ in targets:
            os.replace(staging / path.name, path)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def write_sources(
    docs: Iterable[SourceDoc], out_dir: Path, *, overwrite: bool = False
) -> tuple[Path, ...]:
    """Write ``NN-<slug>.md`` per doc, then drop stale earlier output; returns written paths."""
    previous = check_out_dir(out_dir, overwrite=overwrite)
    targets = _targets(docs, out_dir)
    clash = next((p for p, _ in targets if p.exists() and p not in previous), None)
    if clash is not None:
        raise FileExistsError(f"{clash} exists and was not written by ingest; move it first.")
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_staged(targets, out_dir)
    paths = tuple(path for path, _ in targets)
    for stale in set(previous) - set(paths):
        stale.unlink()
    logger.info("Wrote %d source files to %s", len(paths), out_dir)
    return paths

"""``series/<slug>.yaml`` on disk: load and validate, write atomically, plan and approve rules.

Only one series may be ``approved`` (active) at a time, so the weekly run is unambiguous.
"""

import logging
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from newsletter_machine.drafting import write_atomic
from newsletter_machine.ingest import YAML_LINE_WIDTH
from newsletter_machine.series import (
    URL_PATTERN,
    PartStatus,
    Series,
    SeriesPart,
    is_slug,
    parse_series,
    series_to_mapping,
)
from newsletter_machine.series_edit import edit_part

logger = logging.getLogger(__name__)

DEFAULT_SERIES_DIR = Path("series")
SERIES_SUFFIX = ".yaml"
STATUS_LINE = re.compile(r"^status:[ \t]*(['\"]?)proposed\1([ \t]+#.*)?[ \t]*$", re.MULTILINE)
ANY_STATUS_LINE = re.compile(r"^status:[ \t]*['\"]?([A-Za-z]+)", re.MULTILINE)
HEADER = (
    "# Series plan: {slug}. Edit any field by hand; `newsletter-machine series show {slug}`\n"
    "# checks it. When the outline is right: newsletter-machine series approve {slug}\n"
)


@dataclass(frozen=True)
class Approval:
    """A checked approval: ``text`` is the new file content, or None when nothing changes."""

    path: Path
    series: Series  # as approved
    text: str | None


def series_path(series_dir: Path, slug: str) -> Path:
    if not is_slug(slug):
        raise ValueError(
            f"series name must be kebab-case, like 'evals' or 'llm-as-judge' (got {slug!r})."
        )
    return series_dir / f"{slug}{SERIES_SUFFIX}"


def _parse_text(path: Path, text: str) -> Series:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"{path}: invalid YAML: {exc}") from exc
    return parse_series(data, str(path))


def _read(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(
            f"No series file at {path}; create one with: newsletter-machine series plan <topic>"
        )
    return path.read_text(encoding="utf-8")


def load_series(path: Path) -> Series:
    """Read and validate; any problem raises with ``path`` in the message."""
    return _parse_text(path, _read(path))


def render_series_yaml(series: Series, slug: str) -> str:
    body = yaml.safe_dump(
        series_to_mapping(series), sort_keys=False, allow_unicode=True, width=YAML_LINE_WIDTH
    )
    return HEADER.format(slug=slug) + body


def save_series(path: Path, series: Series, slug: str) -> None:
    """Write atomically, after checking the file will load again (never write a broken one)."""
    text = render_series_yaml(series, slug)
    _parse_text(path, text)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, text)
    logger.info("Wrote %s (%s, %d parts)", path, series.status, len(series.parts))


def declared_status(path: Path) -> str | None:
    """The top-level ``status`` a file declares, read leniently (the file may be invalid
    otherwise); None when it cannot be read at all."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        match = ANY_STATUS_LINE.search(text)  # broken YAML: the status line may still be fine
        return match.group(1) if match else None
    status = data.get("status") if isinstance(data, dict) else None
    return status if isinstance(status, str) else None


def check_can_plan(path: Path, *, overwrite: bool) -> None:
    """Fail fast before a model call: an approved series is never re-planned, and a proposed
    one is only replaced with ``--overwrite`` (even when hand edits broke it)."""
    if path.parent.exists() and not path.parent.is_dir():
        raise NotADirectoryError(f"--series-dir {path.parent} is not a directory.")
    if path.is_dir():
        raise IsADirectoryError(f"{path} is a directory.")
    if not path.exists():
        return
    # without --overwrite an invalid file reports its own error; with it, a broken file is
    # replaced only when it still declares itself proposed
    status = declared_status(path) if overwrite else load_series(path).status
    if status != "proposed":
        raise ValueError(
            f"{path} is {status or 'unreadable'}; only a proposed outline is re-planned. "
            "Plan under another topic name, or fix or delete the file by hand."
        )
    if not overwrite:
        raise FileExistsError(f"{path} exists; pass --overwrite to replace the proposed outline.")


def approved_slugs(series_dir: Path) -> tuple[str, ...]:
    """Slugs of series files in ``series_dir`` that declare ``status: approved``. Only the
    status is read, so a half-edited outline of another topic never blocks an approval; files
    not named ``<slug>.yaml`` (temp files, other YAML) are skipped."""
    if not series_dir.is_dir():
        return ()
    paths = sorted(p for p in series_dir.glob(f"*{SERIES_SUFFIX}") if is_slug(p.stem))
    return tuple(path.stem for path in paths if declared_status(path) == "approved")


def _approved_text(path: Path, text: str, series: Series, slug: str) -> str:
    """Flip only the top-level status line, so Varun's comments and layout survive; fall back
    to a full rewrite when that line is written some other way."""
    approved = replace(series, status="approved")
    new_text, count = STATUS_LINE.subn(r"status: approved\2", text, count=1)
    if count and _parse_text(path, new_text) == approved:
        return new_text
    return render_series_yaml(approved, slug)


def check_approval(series_dir: Path, slug: str) -> Approval:
    """Validate ``proposed`` -> ``approved`` without writing; refuses a second active series."""
    path = series_path(series_dir, slug)
    text = _read(path)
    series = _parse_text(path, text)
    if series.status == "approved":
        return Approval(path, series, text=None)
    if series.status == "complete":
        raise ValueError(f"{path} is complete; a finished series cannot be approved again.")
    others = [other for other in approved_slugs(series_dir) if other != slug]
    if others:
        raise ValueError(
            f"{others[0]} is already the active series ({series_path(series_dir, others[0])}); "
            "only one series can be approved at a time. Mark it complete first."
        )
    approved = replace(series, status="approved")
    return Approval(path, approved, text=_approved_text(path, text, series, slug))


def save_approval(approval: Approval) -> None:
    """Write a checked approval atomically (no-op when it was already approved)."""
    if approval.text is None:
        return
    write_atomic(approval.path, approval.text)
    logger.info("Approved %s", approval.path)


def _parses_to(path: Path, text: str | None, expected: Series) -> bool:
    if text is None:
        return False
    try:
        return _parse_text(path, text) == expected
    except ValueError:  # the line edit broke the YAML: fall back to a full rewrite
        return False


def _find_part(path: Path, series: Series, number: int) -> SeriesPart:
    part = next((p for p in series.parts if p.number == number), None)
    if part is None:
        raise ValueError(f"{path} has no Part {number}.")
    return part


def _with_part(series: Series, part: SeriesPart) -> Series:
    return replace(
        series, parts=tuple(part if p.number == part.number else p for p in series.parts)
    )


@dataclass(frozen=True)
class _PartEdit:
    """One part's new status (allowed only from ``statuses``) and field values."""

    number: int
    statuses: tuple[PartStatus, ...]
    status: PartStatus
    fields: Mapping[str, str]


def _write_part_edit(path: Path, slug: str, text: str, expected: Series, edit: _PartEdit) -> bool:
    """Write ``expected`` by editing only the part's lines, so comments survive; a full
    (checked) rewrite when the lines are written some other way. True when comments were kept."""
    edited = edit_part(
        text, edit.number, statuses=edit.statuses, status=edit.status, fields=edit.fields
    )
    kept = _parses_to(path, edited, expected)
    if kept and edited is not None:
        write_atomic(path, edited)
    else:
        save_series(path, expected, slug)  # checks the rewrite loads before writing
    return kept


def _drafted_series(path: Path, series: Series, edit: _PartEdit) -> Series:
    part = _find_part(path, series, edit.number)
    if part.status != "planned":
        raise ValueError(f"{path}: Part {edit.number} is {part.status}, not planned.")
    if series.status != "approved":
        raise ValueError(f"{path} is now {series.status}, no longer approved.")
    fields = edit.fields
    drafted = replace(
        part,
        status="drafted",
        draft=fields["draft"],
        summary=fields["summary"],
        teaser=fields["teaser"],
    )
    return _with_part(series, drafted)


def mark_drafted(
    path: Path, slug: str, number: int, draft: str, *, summary: str = "", teaser: str = ""
) -> bool:
    """Mark part ``number`` drafted with its draft path, one-line summary and closing teaser,
    re-reading the file first (Varun may have edited it during the run). Only those lines
    change, so comments survive; returns False when the file had to be rewritten in full."""
    text = _read(path)
    fields = {"draft": draft, "summary": summary.strip(), "teaser": teaser.strip()}
    edit = _PartEdit(number, ("planned",), "drafted", fields)
    expected = _drafted_series(path, _parse_text(path, text), edit)
    kept = _write_part_edit(path, slug, text, expected, edit)
    logger.info("Marked part %d of %s drafted (%s)", number, path, draft)
    return kept


PUBLISHABLE: tuple[PartStatus, ...] = ("drafted", "published")


@dataclass(frozen=True)
class Publication:
    """A checked ``series published``: ``changed`` is False when the URL is already recorded."""

    path: Path
    slug: str
    number: int
    url: str
    changed: bool


def check_url(url: str) -> str:
    """The stripped URL when it is an absolute http(s) address with a host."""
    url = url.strip()
    if not URL_PATTERN.fullmatch(url) or not urlsplit(url).hostname:
        raise ValueError(f"the URL must be an http(s) address like https://... (got {url!r}).")
    return url


def _published_series(path: Path, series: Series, number: int, url: str) -> Series:
    part = _find_part(path, series, number)
    if part.status not in PUBLISHABLE:
        raise ValueError(
            f"{path}: Part {number} is {part.status}; only a drafted (or published) part can "
            "be recorded as published."
        )
    return _with_part(series, replace(part, status="published", url=url))


def plan_publication(series_dir: Path, slug: str, number: int, url: str) -> Publication:
    """Validate ``series published`` without writing."""
    url = check_url(url)
    path = series_path(series_dir, slug)
    series = load_series(path)
    expected = _published_series(path, series, number, url)
    return Publication(path, slug, number, url, changed=expected != series)


def save_publication(publication: Publication) -> bool:
    """Record the URL (re-checking the file first); True when comments were kept."""
    if not publication.changed:
        return True
    p = publication
    text = _read(p.path)
    expected = _published_series(p.path, _parse_text(p.path, text), p.number, p.url)
    edit = _PartEdit(p.number, PUBLISHABLE, "published", {"url": p.url})
    kept = _write_part_edit(p.path, p.slug, text, expected, edit)
    logger.info("Marked part %d of %s published (%s)", p.number, p.path, p.url)
    return kept


def _project_root(path: Path) -> Path:
    """The folder holding the series folder (the repo, for ``series/<slug>.yaml``)."""
    return path.resolve().parent.parent


def draft_reference(path: Path, draft: Path) -> str:
    """How the series file at ``path`` records ``draft``: relative to the folder holding the
    series folder (``drafts/2026-11-04.md``), so it reads the same from any working directory;
    absolute when the draft lives on another drive."""
    try:
        return Path(os.path.relpath(draft.resolve(), _project_root(path))).as_posix()
    except ValueError:  # Windows: a different drive has no relative path
        return draft.resolve().as_posix()


def draft_location(path: Path, reference: str) -> Path:
    """The absolute draft path a series file's ``draft`` field names (see ``draft_reference``)."""
    return (_project_root(path) / reference).resolve()

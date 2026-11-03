"""The editor's virtual filesystem: where sources, notes, drafts and critiques live.

Sub-agents write these files through state updates (not tools), versioned ``v1``, ``v2``...
so the lead agent can read every step but never overwrite one.
"""

import re
from collections.abc import Iterable, Mapping
from typing import Any

from deepagents.backends.utils import create_file_data

from newsletter_machine.ingest import render_source, slugify
from newsletter_machine.sources import SourceDoc
from newsletter_machine.writer import usable_sources

SOURCES_DIR = "/sources"
RESEARCH_NOTES = "/research/notes.md"
PLAN_FILE = "/plan.md"
DRAFTS_DIR = "/drafts"
BRIEFS_DIR = "/briefs"
CRITIQUES_DIR = "/critiques"
ERRORS_DIR = "/errors"
PROTECTED_DIRS = (SOURCES_DIR, "/research", DRAFTS_DIR, BRIEFS_DIR, CRITIQUES_DIR, ERRORS_DIR)

Files = Mapping[str, Any]


def text_file(text: str) -> dict[str, Any]:
    """A file value in the shape deepagents' state backend stores."""
    return dict(create_file_data(text))


def seed_files(docs: Iterable[SourceDoc]) -> dict[str, dict[str, Any]]:
    """Usable sources as ``/sources/NN-x.md``, numbered ``[NN]`` as every agent numbers them;
    failed ones (empty, kept so the lead sees what is missing) as ``/sources/failed-N-x.md``."""
    docs = tuple(docs)
    failed = [doc for doc in docs if doc.status == "failed"]
    files = {
        f"{SOURCES_DIR}/{index:02d}-{slugify(doc.title)}.md": text_file(render_source(doc))
        for index, doc in enumerate(usable_sources(docs), start=1)
    }
    gaps = {
        f"{SOURCES_DIR}/failed-{index}-{slugify(doc.title)}.md": text_file(render_source(doc))
        for index, doc in enumerate(failed, start=1)
    }
    return {**files, **gaps}


def file_text(files: Files, path: str) -> str | None:
    """The text of ``path``, or None when it is missing or not a text file."""
    value = files.get(path)
    content = value.get("content") if isinstance(value, Mapping) else None
    if isinstance(content, str):
        return content
    if isinstance(content, list) and all(isinstance(line, str) for line in content):
        return "\n".join(content)  # older deepagents stored a list of lines
    return None


def versioned(directory: str, version: int, ext: str) -> str:
    return f"{directory}/v{version}.{ext}"


def latest_version(files: Files, directory: str, ext: str) -> int:
    """Highest ``N`` among ``<directory>/vN.<ext>``; 0 when there is none."""
    pattern = re.compile(rf"{re.escape(directory)}/v(\d+)\.{re.escape(ext)}")
    found = (pattern.fullmatch(path) for path in files)
    return max((int(match.group(1)) for match in found if match), default=0)


def count_files(files: Files, directory: str, prefix: str) -> int:
    """Files directly in ``directory`` whose name starts with ``prefix``."""
    start = f"{directory}/{prefix}"
    return sum(1 for path in files if path.startswith(start) and "/" not in path[len(start) :])

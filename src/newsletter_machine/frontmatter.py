"""YAML front-matter splitting shared by voice samples, prompts and source files."""

from pathlib import Path
from typing import Any

import yaml

FRONT_MATTER_DELIMITER = "---"


def split_front_matter(path: Path, text: str) -> tuple[dict[str, Any], str]:
    """Return ``(meta, body)``; ``ValueError`` names ``path`` on any malformed header."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONT_MATTER_DELIMITER:
        raise ValueError(f"{path}: missing front-matter")
    try:
        end = next(
            i for i, line in enumerate(lines[1:], start=1) if line.strip() == FRONT_MATTER_DELIMITER
        )
    except StopIteration:
        raise ValueError(f"{path}: unterminated front-matter") from None
    try:
        meta = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError as exc:
        raise ValueError(f"{path}: invalid front-matter YAML: {exc}") from exc
    if not isinstance(meta, dict):
        raise ValueError(f"{path}: front-matter is not a mapping")
    return meta, "\n".join(lines[end + 1 :]).strip("\n")

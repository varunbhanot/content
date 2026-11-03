"""Writer then critic, once: sub-agent wiring and output files for ``newsletter-machine draft``.

The lead "editor" agent (``editor.py``, ``newsletter-machine issue``) wraps the
``build_subagents`` output in ``editor_subagents.py`` and loops draft and critique.
"""

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from deepagents import CompiledSubAgent
from langchain_core.language_models import BaseChatModel

from newsletter_machine.critic import CRITIC_PROMPT, build_critic, critic_system_prompt
from newsletter_machine.grounding import Grounding
from newsletter_machine.prompts import load_prompt
from newsletter_machine.writer import WRITER_NAME, build_writer, writer_system_prompt

DRAFT_SUFFIX = ".md"
CRITIQUE_SUFFIX = ".critique.md"


@dataclass(frozen=True)
class OutputPaths:
    draft: Path
    critique: Path


def output_paths(out: Path) -> OutputPaths:
    """``issue.md`` -> draft ``issue.md`` and critique ``issue.critique.md`` beside it."""
    if out.suffix != DRAFT_SUFFIX:
        raise ValueError(f"--out must be a Markdown file ending in {DRAFT_SUFFIX} (got {out}).")
    return OutputPaths(draft=out, critique=out.with_name(f"{out.stem}{CRITIQUE_SUFFIX}"))


def check_outputs(paths: OutputPaths, *, overwrite: bool) -> None:
    """Fail fast, before any model call, on a target we cannot or should not write."""
    for path in (paths.draft, paths.critique):
        check_target(path, overwrite=overwrite)


def check_target(path: Path, *, overwrite: bool) -> None:
    """One output file: its folder exists, it is not a folder, it is new or may be replaced."""
    if not path.parent.is_dir():
        raise FileNotFoundError(f"Output folder {path.parent} does not exist.")
    if path.is_dir():
        raise IsADirectoryError(f"{path} is a directory.")
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} exists; pick another --out or pass --overwrite.")


@dataclass(frozen=True)
class SubAgents:
    """The two sub-agents plus the prompt versions they were built from (for the report)."""

    writer: CompiledSubAgent
    critic: CompiledSubAgent
    writer_version: int
    critic_version: int


def write_atomic(path: Path, text: str) -> None:
    """Write via a temp file and ``os.replace``, so a failed write never truncates ``path``."""
    handle, name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=f".{path.name}")
    os.close(handle)
    tmp = Path(name)
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def build_subagents(
    grounding: Grounding, writer_model: BaseChatModel, critic_model: BaseChatModel
) -> SubAgents:
    """The writer and voice-critic sub-agents, both grounded in the same voice assets."""
    writer_prompt, critic_prompt = load_prompt(WRITER_NAME), load_prompt(CRITIC_PROMPT)
    return SubAgents(
        writer=build_writer(writer_model, writer_system_prompt(grounding, writer_prompt)),
        critic=build_critic(critic_model, critic_system_prompt(grounding, critic_prompt)),
        writer_version=writer_prompt.version,
        critic_version=critic_prompt.version,
    )

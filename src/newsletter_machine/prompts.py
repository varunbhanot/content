"""Versioned prompt templates in ``prompts/*.md`` (front-matter + ``string.Template`` body)."""

from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from string import Template

from newsletter_machine.frontmatter import split_front_matter
from newsletter_machine.validation import is_int

PROMPTS_PACKAGE = "newsletter_machine"
PROMPTS_DIR = "prompts"


@dataclass(frozen=True)
class Prompt:
    name: str
    version: int
    template: str


def _read(name: str) -> str:
    resource = resources.files(PROMPTS_PACKAGE).joinpath(PROMPTS_DIR, f"{name}.md")
    if not resource.is_file():
        raise ValueError(f"Prompt not found: {PROMPTS_DIR}/{name}.md")
    return resource.read_text(encoding="utf-8")


def load_prompt(name: str) -> Prompt:
    """Load ``prompts/<name>.md``; its front-matter must carry an integer ``version``."""
    path = Path(PROMPTS_DIR) / f"{name}.md"
    meta, body = split_front_matter(path, _read(name))
    version = meta.get("version")
    if not is_int(version):
        raise ValueError(f"{path}: 'version' must be an integer (got {version!r})")
    return Prompt(name=name, version=version, template=body)


def render(prompt: Prompt, **values: str) -> str:
    """Fill ``$placeholders``; a missing value raises ``KeyError`` instead of leaking ``$x``."""
    return Template(prompt.template).substitute(values)

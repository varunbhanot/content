"""Small validators for values read from YAML (front-matter, checklist)."""

from collections.abc import Mapping, Sequence
from typing import Any, TypeGuard


def is_int(value: object) -> TypeGuard[int]:
    """True for real integers; YAML ``true`` is a bool, which Python counts as an int."""
    return isinstance(value, int) and not isinstance(value, bool)


def one_of[T: str](where: str, name: str, value: object, options: Sequence[T]) -> T:
    """Return ``value`` typed as one of ``options`` (a Literal's args), else ``ValueError``."""
    for option in options:
        if value == option:
            return option
    raise ValueError(f"{where}: '{name}' must be one of {tuple(options)} (got {value!r})")


def non_empty_text(raw: Mapping[str, Any], name: str, where: str) -> str:
    """``raw[name]`` stripped; ``ValueError`` unless it is non-empty text."""
    value = raw.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where}: '{name}' must be non-empty text")
    return value.strip()

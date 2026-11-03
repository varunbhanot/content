from pathlib import Path

import pytest

from newsletter_machine.frontmatter import split_front_matter

PATH = Path("x.md")


def test_split_front_matter_returns_meta_and_body() -> None:
    meta, body = split_front_matter(PATH, "---\na: 1\n---\n\nbody\n")
    assert meta == {"a": 1}
    assert body == "body"


def test_split_front_matter_rejects_missing_delimiter() -> None:
    with pytest.raises(ValueError, match="x.md: missing front-matter"):
        split_front_matter(PATH, "body")


def test_split_front_matter_rejects_unterminated() -> None:
    with pytest.raises(ValueError, match="unterminated"):
        split_front_matter(PATH, "---\na: 1\n")


def test_split_front_matter_rejects_non_mapping() -> None:
    with pytest.raises(ValueError, match="not a mapping"):
        split_front_matter(PATH, "---\n- a\n---\nbody")


def test_split_front_matter_rejects_bad_yaml() -> None:
    with pytest.raises(ValueError, match="invalid front-matter YAML"):
        split_front_matter(PATH, '---\na: "unclosed\n---\nbody')

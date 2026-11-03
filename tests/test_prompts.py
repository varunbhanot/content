import pytest

from newsletter_machine.prompts import Prompt, load_prompt, render

NAMES = ("writer", "critic")


@pytest.mark.parametrize("name", NAMES)
def test_load_prompt_reads_versioned_file(name: str) -> None:
    prompt = load_prompt(name)
    assert prompt.version >= 1
    assert "$style_guide" in prompt.template
    assert "$checklist" in prompt.template


def test_writer_prompt_grounds_in_samples() -> None:
    assert "$samples" in load_prompt("writer").template


@pytest.mark.parametrize("name", NAMES)
def test_real_prompts_render_with_all_placeholders(name: str) -> None:
    text = render(load_prompt(name), style_guide="G", checklist="C", samples="S")
    assert "$" not in text.replace("$$", "")
    assert "<style_guide>\nG\n</style_guide>" in text


def test_render_fails_fast_on_missing_value() -> None:
    with pytest.raises(KeyError, match="samples"):
        render(Prompt(name="p", version=1, template="$samples"))


def test_render_does_not_reinterpret_dollar_in_values() -> None:
    assert render(Prompt(name="p", version=1, template="$a"), a="$b") == "$b"


def test_load_prompt_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="nope"):
        load_prompt("nope")


def test_load_prompt_rejects_bad_version(monkeypatch: pytest.MonkeyPatch) -> None:
    from newsletter_machine import prompts

    monkeypatch.setattr(prompts, "_read", lambda name: "---\nversion: one\n---\nbody")
    with pytest.raises(ValueError, match="version"):
        load_prompt("writer")

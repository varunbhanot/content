from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from fakes import DRAFT, FIXTURES, fake
from fakes import illustrator_reply as _reply
from newsletter_machine.agent import AgentOutputError
from newsletter_machine.illustrator import (
    build_illustrator,
    illustrate,
    illustrator_system_prompt,
    render_visual_notes,
    write_visuals,
)
from newsletter_machine.ingest import read_sources

DOCS = read_sources(FIXTURES)
SVG = '<svg xmlns="http://www.w3.org/2000/svg"><rect width="4" height="4"/></svg>'
ANIMATED = (
    '<svg xmlns="http://www.w3.org/2000/svg"><circle r="1">'
    '<animate attributeName="r" from="1" to="3" dur="2s"/></circle></svg>'
)


def _visual(**overrides: Any) -> dict[str, Any]:
    base = {
        "purpose": "Show the gap between demo and production.",
        "anchor": "Production did not.",
        "kind": "diagram",
        "format": "svg",
        "animated": False,
        "animation_reason": "A static picture says it.",
        "alt": "Two boxes: demo and production.",
        "caption": "Demo versus production.",
        "code": SVG,
    }
    return {**base, **overrides}


def _run(reply: AIMessage, max_visuals: int = 3) -> Any:
    agent = build_illustrator(fake(reply), "sys")
    return illustrate(agent, DRAFT, DOCS, max_visuals=max_visuals, image_dir="issue.images")


def test_system_prompt_renders_cap() -> None:
    prompt = illustrator_system_prompt(max_visuals=2)
    assert "2" in prompt and "$" not in prompt


def test_illustrate_places_svg_and_records_file() -> None:
    result = _run(_reply(_visual()))
    assert [v.path for v in result.visuals] == ["visual-1.svg"]
    assert "![Two boxes: demo and production.](issue.images/visual-1.svg)" in result.draft
    assert "*Demo versus production.*" in result.draft
    assert result.rejected == ()


def test_illustrate_names_files_by_index_not_model_text() -> None:
    result = _run(_reply(_visual(caption="../../etc/passwd")))
    assert result.visuals[0].path == "visual-1.svg"


def test_illustrate_records_actual_animation() -> None:
    result = _run(_reply(_visual(code=ANIMATED, animated=True)))
    assert result.visuals[0].animated is True


def test_illustrate_mermaid_goes_inline_and_to_file() -> None:
    result = _run(_reply(_visual(format="mermaid", code="flowchart LR\n  A --> B")))
    assert result.visuals[0].path == "visual-1.mmd"
    assert "```mermaid\nflowchart LR\n  A --> B\n```" in result.draft


def test_illustrate_prompt_only_leaves_marker_and_no_file() -> None:
    result = _run(_reply(_visual(kind="illustration", format="prompt-only", code="A robot.")))
    assert result.visuals[0].path is None
    assert "[VARUN: add image: Demo versus production.]" in result.draft
    assert "A robot." in render_visual_notes(result)


def test_illustrate_rejects_bad_svg_invented_chart_numbers_and_over_cap() -> None:
    chart = SVG.replace("</svg>", "<text>987654</text></svg>")
    result = _run(
        _reply(
            _visual(code="<not svg"),
            _visual(kind="chart", code=chart),
            _visual(),
            _visual(),
        ),
        max_visuals=1,  # failed visuals do not use up the cap
    )
    reasons = [reason for _, reason in result.rejected]
    assert len(result.visuals) == 1
    assert any("987654" in r for r in reasons)
    assert any("cap" in r for r in reasons)
    assert len(reasons) == 3


def test_illustrate_unplaced_anchor_is_reported_not_written() -> None:
    result = _run(_reply(_visual(anchor="nowhere in the draft")))
    assert result.visuals == ()
    assert "anchor" in result.rejected[0][1]
    assert result.draft == DRAFT


def test_illustrate_zero_visuals_returns_draft_unchanged() -> None:
    result = _run(_reply(skipped="Nothing needs a picture."))
    assert result.draft == DRAFT
    assert "Nothing needs a picture." in render_visual_notes(result)


def test_illustrate_without_structured_output_raises() -> None:
    class _NoStructure:
        def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
            return {"messages": [AIMessage(content="fine")], "structured_response": None}

    agent = {"name": "illustrator", "description": "d", "runnable": _NoStructure()}
    with pytest.raises(AgentOutputError, match="structured"):
        illustrate(agent, DRAFT, DOCS, max_visuals=3, image_dir="x")  # type: ignore[arg-type]


def test_write_visuals_writes_files(tmp_path: Path) -> None:
    result = _run(_reply(_visual(), _visual(format="mermaid", code="flowchart LR\n A-->B")))
    out = tmp_path / "issue.images"
    written = write_visuals(result, out)
    assert sorted(p.name for p in written) == ["visual-1.svg", "visual-2.mmd"]
    assert (out / "visual-1.svg").read_text().startswith("<svg")


def test_files_are_numbered_without_gaps_and_rejections_name_the_proposal() -> None:
    result = _run(
        _reply(
            _visual(code="<not svg"),
            _visual(anchor="nowhere in the draft"),
            _visual(),
        )
    )
    assert [v.path for v in result.visuals] == ["visual-1.svg"]
    assert "issue.images/visual-1.svg" in result.draft
    assert [n for n, _ in result.rejected] == [1, 2]
    notes = render_visual_notes(result)
    assert "Dropped proposal 1" in notes and "Dropped proposal 2" in notes


def test_image_path_is_url_encoded() -> None:
    agent = build_illustrator(fake(_reply(_visual())), "sys")
    result = illustrate(agent, DRAFT, DOCS, max_visuals=3, image_dir="my issue.images")
    assert "(my%20issue.images/visual-1.svg)" in result.draft

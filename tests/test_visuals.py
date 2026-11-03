import pytest

from newsletter_machine.visuals import (
    VisualError,
    check_chart_numbers,
    check_mermaid,
    place_visuals,
    sanitise_svg,
)

SVG_NS = 'xmlns="http://www.w3.org/2000/svg"'


def _svg(body: str) -> str:
    return f'<svg {SVG_NS} viewBox="0 0 10 10">{body}</svg>'


# --- sanitise_svg -----------------------------------------------------------------------


def test_sanitise_keeps_plain_shapes_and_text() -> None:
    clean = sanitise_svg(_svg('<rect x="1" y="1" width="5" height="5"/><text>Agent</text>'))
    assert clean.svg.startswith("<svg")
    assert "<rect" in clean.svg and "Agent" in clean.svg
    assert clean.animated is False
    assert clean.removed == ()


def test_sanitise_strips_script_foreign_object_and_handlers() -> None:
    raw = _svg(
        "<script>alert(1)</script><foreignObject><div/></foreignObject>"
        '<rect onclick="alert(1)" width="1" height="1"/>'
    )
    clean = sanitise_svg(raw)
    assert "script" not in clean.svg and "alert" not in clean.svg
    assert "foreignObject" not in clean.svg and "onclick" not in clean.svg
    assert set(clean.removed) >= {"<script>", "<foreignObject>", "onclick="}


def test_sanitise_drops_external_links_but_keeps_internal_ones() -> None:
    raw = (
        f'<svg {SVG_NS} xmlns:xlink="http://www.w3.org/1999/xlink">'
        '<defs><path id="p" d="M0 0"/></defs>'
        '<use href="#p"/><use xlink:href="https://evil.example/x.svg#a"/>'
        '<a href="javascript:alert(1)"><text>x</text></a></svg>'
    )
    clean = sanitise_svg(raw)
    assert 'href="#p"' in clean.svg
    assert "evil.example" not in clean.svg and "javascript" not in clean.svg


def test_sanitise_drops_style_with_external_url() -> None:
    clean = sanitise_svg(_svg('<rect style="fill:url(https://x.example/a)" width="1"/>'))
    assert "x.example" not in clean.svg


def test_sanitise_marks_smil_animation() -> None:
    raw = _svg('<circle r="1"><animate attributeName="r" from="1" to="3" dur="2s"/></circle>')
    clean = sanitise_svg(raw)
    assert clean.animated is True
    assert "<animate" in clean.svg


def test_sanitise_drops_animation_that_rewrites_links() -> None:
    raw = _svg('<a><set attributeName="href" to="javascript:alert(1)"/><text>x</text></a>')
    clean = sanitise_svg(raw)
    assert "javascript" not in clean.svg


@pytest.mark.parametrize(
    "raw",
    [
        "not xml at all",
        '<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY x "y">]><svg/>',
        f"<html {SVG_NS}/>",
        _svg("x" * 300_000),
    ],
)
def test_sanitise_rejects_bad_input(raw: str) -> None:
    with pytest.raises(VisualError):
        sanitise_svg(raw)


def test_sanitise_strips_markdown_fence_around_svg() -> None:
    clean = sanitise_svg(f"```svg\n{_svg('<rect width="1"/>')}\n```")
    assert clean.svg.startswith("<svg")


# --- check_mermaid ----------------------------------------------------------------------


def test_check_mermaid_accepts_known_diagram_types() -> None:
    assert check_mermaid("```mermaid\nflowchart LR\n  A --> B\n```") == "flowchart LR\n  A --> B"
    assert check_mermaid("%% comment\nsequenceDiagram\n  A->>B: hi").startswith("%%")


@pytest.mark.parametrize("raw", ["", "A --> B", "<script>x</script>", "graph"])
def test_check_mermaid_rejects_unknown_or_empty(raw: str) -> None:
    with pytest.raises(VisualError):
        check_mermaid(raw)


def test_check_mermaid_rejects_click_callbacks() -> None:
    with pytest.raises(VisualError):
        check_mermaid('flowchart LR\n  A --> B\n  click A "https://x.example"')


# --- check_chart_numbers ----------------------------------------------------------------


def test_chart_numbers_must_come_from_sources() -> None:
    svg = _svg("<text>73%</text><text>12.5</text>")
    check_chart_numbers(svg, "Success fell to 73% and latency was 12.5 seconds.")
    with pytest.raises(VisualError, match="12.5"):
        check_chart_numbers(svg, "Success fell to 73%.")


# --- place_visuals ----------------------------------------------------------------------

DRAFT = (
    "# Title\n\nThe demo worked. Production did not.\n\n"
    "Evals caught the regression\nbefore users did.\n\n"
    "## Sources\n\n- [Why](https://example.com/why)\n"
)


def test_place_inserts_block_after_anchor_paragraph() -> None:
    placed = place_visuals(DRAFT, [("v1", "Production did not.", "![a](x.svg)")])
    assert placed.placed == ("v1",)
    assert "Production did not.\n\n![a](x.svg)\n\nEvals caught" in placed.draft


def test_place_matches_anchor_across_line_breaks_and_keeps_order() -> None:
    placed = place_visuals(
        DRAFT,
        [
            ("v1", "regression before users", "BLOCK1"),
            ("v2", "regression before users", "BLOCK2"),
        ],
    )
    assert placed.placed == ("v1", "v2")
    assert "before users did.\n\nBLOCK1\n\nBLOCK2\n\n## Sources" in placed.draft


def test_place_reports_unfound_anchor_and_never_uses_sources_section() -> None:
    placed = place_visuals(DRAFT, [("v1", "not in the draft", "B"), ("v2", "[Why]", "C")])
    assert placed.placed == ()
    assert placed.unplaced == ("v1", "v2")
    assert placed.draft == DRAFT


def test_place_ignores_anchor_inside_code_fence() -> None:
    draft = "# T\n\n```\nsecret anchor\n```\n\nText here.\n"
    placed = place_visuals(draft, [("v1", "secret anchor", "B")])
    assert placed.unplaced == ("v1",)


def test_sanitise_keeps_quoted_internal_url_references() -> None:
    clean = sanitise_svg(_svg('<rect fill="url(\'#g\')" stroke=\'url("#g")\' width="1"/>'))
    assert clean.removed == ()
    assert "url('#g')" in clean.svg


def test_place_finds_paragraph_directly_before_a_fence() -> None:
    draft = "# T\n\nIntro line\n```py\ncode\n```\n\nNext.\n"
    assert place_visuals(draft, [("v1", "Intro line", "B")]).placed == ("v1",)


def test_place_matches_rendered_text_through_markdown_and_smart_quotes() -> None:
    draft = "# T\n\nThe **demo** worked, as [Kim](https://x.example) said: “ship it”.\n"
    placed = place_visuals(draft, [("v1", 'the demo worked, as Kim said: "ship it"', "B")])
    assert placed.placed == ("v1",)


# --- security review regressions ---------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        '<rect style="fill:u\\72l(http://evil.example/x)"/>',
        "<rect style=\"background-image:image-set('http://evil.example/x.png' 1x)\"/>",
        '<rect><set attributeName="style" to="fill:red"/></rect>',
        '<rect fill="u\\72l(http://evil.example/x)"/>',
        '<use href="#a" xml:base="http://evil.example/"/>',
    ],
)
def test_sanitise_blocks_css_fetch_tricks(body: str) -> None:
    clean = sanitise_svg(_svg(body))
    assert "evil.example" not in clean.svg
    assert "style" not in clean.svg


def test_sanitise_rejects_element_bombs() -> None:
    with pytest.raises(VisualError):
        sanitise_svg(_svg('<g id="a"/>' + '<use href="#a"/>' * 200))
    with pytest.raises(VisualError):
        sanitise_svg(_svg("<g>" * 60 + "</g>" * 60))


@pytest.mark.parametrize(
    "raw",
    [
        "graph TD\nA-->B\n```\n<script>alert(1)</script>\n```mermaid\nA-->B",
        "graph TD\nA-->B\n~~~\nx",
        'graph TD\nA-->B; click A "javascript:alert(1)"',
        '%%{init: {"securityLevel": "loose"}}%%\ngraph TD\nA-->B',
    ],
)
def test_check_mermaid_rejects_fence_breakout_clicks_and_directives(raw: str) -> None:
    with pytest.raises(VisualError):
        check_mermaid(raw)


def test_plain_text_escapes_markdown_html_and_drops_links() -> None:
    from newsletter_machine.visuals import plain_text

    text = plain_text("<img src=x onerror=a()> see <https://evil.example/l> *x* end\\", 200)
    assert "<" not in text.replace("\\<", "")
    assert "evil.example" not in text
    assert not text.endswith("\\") or text.endswith("\\\\")
    assert len(plain_text("word " * 200, 50)) <= 51

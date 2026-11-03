import io
import os
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from fakes import DRAFT, FIXTURES, fake, illustrator_reply
from newsletter_machine.illustrator import (
    build_illustrator,
    illustrate,
    render_visual_notes,
    write_visuals,
)
from newsletter_machine.ingest import read_sources
from newsletter_machine.render import (
    MAX_FRAMES,
    Raster,
    RenderError,
    animation_cycle,
    encode_gif,
    frame_times,
)

DOCS = read_sources(FIXTURES)
NS = 'xmlns="http://www.w3.org/2000/svg"'
STATIC = f'<svg {NS} viewBox="0 0 40 20"><rect width="40" height="20" fill="#2563eb"/></svg>'
ANIMATED = (
    f'<svg {NS} viewBox="0 0 40 20"><rect width="40" height="20" fill="white"/>'
    '<circle cx="5" cy="10" r="4" fill="#2563eb">'
    '<animate attributeName="cx" from="5" to="35" dur="2s" repeatCount="indefinite"/>'
    "</circle></svg>"
)


def _png(colour: str) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (8, 4), colour).save(out, format="PNG")
    return out.getvalue()


# --- pure helpers -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("svg", "expected"),
    [
        (ANIMATED, 2.0),
        (ANIMATED.replace('dur="2s"', 'dur="500ms"'), 1.0),  # floor: a GIF under 1s flickers
        (ANIMATED.replace('dur="2s"', 'dur="30s"'), 6.0),  # cap: keeps the GIF small
        (ANIMATED.replace('dur="2s"', 'dur="indefinite"'), 3.0),  # unknown: default
        (STATIC, 0.0),
    ],
)
def test_animation_cycle(svg: str, expected: float) -> None:
    assert animation_cycle(svg) == expected


def test_animation_cycle_includes_begin_offsets() -> None:
    svg = ANIMATED.replace('dur="2s"', 'dur="2s" begin="1.5s"')
    assert animation_cycle(svg) == 3.5


def test_frame_times_are_even_and_capped() -> None:
    times = frame_times(2.0, fps=10)
    assert times[0] == 0.0 and len(times) == 20
    assert times[1] == pytest.approx(0.1)
    assert len(frame_times(6.0, fps=60)) == MAX_FRAMES


def test_encode_gif_loops_with_one_frame_per_png() -> None:
    gif = encode_gif([_png("white"), _png("blue"), _png("red")], frame_ms=100)
    image = Image.open(io.BytesIO(gif))
    assert image.format == "GIF"
    assert getattr(image, "n_frames", 1) == 3
    assert image.info.get("loop") == 0


def test_encode_gif_rejects_no_frames() -> None:
    with pytest.raises(RenderError):
        encode_gif([], frame_ms=100)


# --- illustrate with a renderer -------------------------------------------------------


class FakeRenderer:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[bool] = []

    def render(self, svg: str, *, animated: bool) -> Raster:
        self.calls.append(animated)
        if self.fail:
            raise RenderError("no browser")
        return Raster("gif" if animated else "png", b"GIF89a" if animated else b"\x89PNG")


def _visual(code: str, **extra: Any) -> dict[str, Any]:
    return {
        "purpose": "p",
        "anchor": "Production did not.",
        "kind": "diagram",
        "format": "svg",
        "animated": "animate" in code,
        "animation_reason": "r",
        "alt": "Alt text.",
        "caption": "Caption.",
        "code": code,
        **extra,
    }


def _illustrate(renderer: Any, *visuals: dict[str, Any]) -> Any:
    agent = build_illustrator(fake(illustrator_reply(*visuals)), "sys")
    return illustrate(
        agent, DRAFT, DOCS, max_visuals=3, image_dir="issue.images", renderer=renderer
    )


def test_draft_links_png_for_static_and_gif_for_animated(tmp_path: Path) -> None:
    renderer = FakeRenderer()
    result = _illustrate(renderer, _visual(STATIC), _visual(ANIMATED))
    assert renderer.calls == [False, True]
    assert "(issue.images/visual-1.png)" in result.draft
    assert "(issue.images/visual-2.gif)" in result.draft
    assert ".svg)" not in result.draft
    written = sorted(p.name for p in write_visuals(result, tmp_path / "issue.images"))
    assert written == ["visual-1.png", "visual-1.svg", "visual-2.gif", "visual-2.svg"]
    assert (tmp_path / "issue.images" / "visual-2.gif").read_bytes() == b"GIF89a"
    assert "Rendered: visual-2.gif" in render_visual_notes(result)
    assert "export a GIF" not in render_visual_notes(result)


def test_render_failure_keeps_the_svg_link_and_says_why() -> None:
    result = _illustrate(FakeRenderer(fail=True), _visual(STATIC))
    assert "(issue.images/visual-1.svg)" in result.draft
    assert "Not rendered: no browser" in render_visual_notes(result)


def test_mermaid_and_prompt_only_are_not_rendered() -> None:
    renderer = FakeRenderer()
    _illustrate(
        renderer,
        _visual("flowchart LR\n  A --> B", format="mermaid"),
        _visual("A robot.", format="prompt-only", kind="illustration"),
    )
    assert renderer.calls == []


# --- the real browser -------------------------------------------------------------------

CHROMIUM = os.environ.get("NM_CHROMIUM_PATH") or "/opt/pw-browsers/chromium"


@pytest.fixture(scope="module")
def browser_renderer() -> Any:
    pytest.importorskip("playwright.sync_api")
    from newsletter_machine.render import BrowserRenderer

    if not Path(CHROMIUM).exists():
        pytest.skip("no Chromium for the real-browser render test")
    renderer = BrowserRenderer(executable_path=CHROMIUM)
    yield renderer
    renderer.close()


def test_browser_renders_static_svg_to_png(browser_renderer: Any) -> None:
    raster = browser_renderer.render(STATIC, animated=False)
    image = Image.open(io.BytesIO(raster.data))
    assert raster.ext == "png" and image.format == "PNG"
    assert image.size == (80, 40)  # viewBox at 2x for sharp text on retina screens
    assert image.convert("RGB").getpixel((40, 20)) == (37, 99, 235)


def test_browser_renders_animated_svg_to_moving_gif(browser_renderer: Any) -> None:
    raster = browser_renderer.render(ANIMATED, animated=True)
    image = Image.open(io.BytesIO(raster.data))
    assert raster.ext == "gif" and getattr(image, "n_frames", 1) > 5
    first = image.convert("RGB").tobytes()
    image.seek(getattr(image, "n_frames", 1) // 2)
    assert image.convert("RGB").tobytes() != first  # the circle moved


# --- failure paths (review regressions) --------------------------------------------------


def test_failed_launch_is_tried_once_then_remembered(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("playwright.sync_api")
    import playwright.sync_api as sync_api

    from newsletter_machine.render import BrowserRenderer

    starts: list[int] = []

    class _Driver:
        def start(self) -> Any:
            starts.append(1)
            raise RuntimeError("driver will not start")

    monkeypatch.setattr(sync_api, "sync_playwright", lambda: _Driver())
    renderer = BrowserRenderer()
    for _ in range(3):
        with pytest.raises(RenderError, match="driver will not start"):
            renderer.render(STATIC, animated=False)
    assert len(starts) == 1


def test_browser_crash_becomes_render_error_and_resets_the_browser() -> None:
    from newsletter_machine.render import BrowserRenderer

    class _DeadBrowser:
        def new_context(self, **kwargs: Any) -> Any:
            raise RuntimeError("Target closed")

        def close(self) -> None:
            pass

    renderer = BrowserRenderer()
    renderer._browser = _DeadBrowser()
    with pytest.raises(RenderError, match="Target closed"):
        renderer.render(STATIC, animated=False)
    assert renderer._browser is None


def test_context_close_failure_does_not_lose_the_image() -> None:
    from newsletter_machine.render import BrowserRenderer

    class _Target:
        def screenshot(self, **kwargs: Any) -> bytes:
            return b"png"

    class _Page:
        def set_content(self, *a: Any, **k: Any) -> None: ...
        def evaluate(self, *a: Any, **k: Any) -> None: ...
        def locator(self, selector: str) -> Any:
            return type("L", (), {"first": _Target()})()

    class _Context:
        def route(self, *a: Any) -> None: ...
        def new_page(self) -> _Page:
            return _Page()

        def close(self) -> None:
            raise RuntimeError("Target closed")

    class _Browser:
        def new_context(self, **kwargs: Any) -> _Context:
            return _Context()

    renderer = BrowserRenderer()
    renderer._browser = _Browser()
    assert renderer.render(STATIC, animated=False).data == b"png"


def test_browser_sizes_percent_width_svg_by_default(browser_renderer: Any) -> None:
    svg = f'<svg {NS} width="100%"><rect width="10" height="10" fill="#2563eb"/></svg>'
    image = Image.open(io.BytesIO(browser_renderer.render(svg, animated=False).data))
    assert image.size == (1600, 900)  # DEFAULT_SIZE at 2x, not 100 px wide

"""Render the illustrator's SVGs to PNG (static) or looping GIF (SMIL-animated) for Substack.

Substack does not take SVG and would show SMIL animation as a still, so each SVG is opened
in headless Chromium (Playwright, the optional ``render`` extra) and screenshotted: once at
2x for a PNG, or frame by frame with the animation clock paused and stepped for a GIF
(assembled with Pillow). The page has no network: every request is refused.

The SVG reaching here is already sanitised (``visuals.sanitise_svg``).
"""

import io
import logging
import re
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)

PNG_SCALE = 2  # sharp text on retina screens
GIF_SCALE = 1  # GIFs grow fast; 1x keeps them small enough for an email
MAX_WIDTH = 800  # CSS pixels; wider SVGs are scaled down
DEFAULT_SIZE = (800, 450)
FPS = 12
MAX_FRAMES = 60
MIN_CYCLE, MAX_CYCLE, DEFAULT_CYCLE = 1.0, 6.0, 3.0  # seconds
ANIMATION_TAGS = frozenset({"animate", "animateTransform", "animateMotion", "set"})
CLOCK = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(ms|s|min|h)?\s*$")
UNIT_SECONDS = {"ms": 0.001, "s": 1.0, "min": 60.0, "h": 3600.0, None: 1.0}
PAGE = (
    "<!doctype html><html><head><meta charset='utf-8'><style>"
    "html,body{margin:0;padding:0;background:#fff}svg{display:block}"
    "</style></head><body>$svg</body></html>"
)
SIZE_SCRIPT = """([maxWidth, dw, dh]) => {
  const svg = document.querySelector('svg');
  const box = svg.viewBox && svg.viewBox.baseVal;
  const px = (name, fallback) => {  // "100%" or "auto" is no size: use the default
    const raw = svg.getAttribute(name) || '';
    return /^\s*[\d.]+(px)?\s*$/.test(raw) ? parseFloat(raw) : fallback;
  };
  let w = box && box.width ? box.width : px('width', dw);
  let h = box && box.height ? box.height : px('height', dh);
  if (w > maxWidth) { h = h * maxWidth / w; w = maxWidth; }
  svg.setAttribute('width', w); svg.setAttribute('height', h);
  return [w, h];
}"""
SEEK_SCRIPT = (
    "(t) => { const s = document.querySelector('svg'); s.pauseAnimations(); s.setCurrentTime(t); }"
)


class RenderError(RuntimeError):
    """A visual could not be rendered; the SVG is kept and linked instead."""


@dataclass(frozen=True)
class Raster:
    ext: str  # "png" or "gif"
    data: bytes


class Renderer(Protocol):
    def render(self, svg: str, *, animated: bool) -> Raster: ...


def _seconds(value: str | None) -> float | None:
    match = CLOCK.match(value or "")
    if not match:
        return None
    return float(match.group(1)) * UNIT_SECONDS[match.group(2)]


def animation_cycle(svg: str) -> float:
    """Seconds one loop of the SVG's SMIL animation takes (0 when it has none).

    The longest ``begin + dur`` among animation elements, clamped to 1 to 6 seconds; 3 when
    no duration is a plain clock value (e.g. ``indefinite`` or an event-based begin).
    """
    root = ET.fromstring(svg)
    animations = [el for el in root.iter() if el.tag.rsplit("}", 1)[-1] in ANIMATION_TAGS]
    if not animations:
        return 0.0
    ends = []
    for element in animations:
        dur = _seconds(element.get("dur"))
        if dur is not None:
            ends.append((_seconds(element.get("begin")) or 0.0) + dur)
    cycle = max(ends) if ends else DEFAULT_CYCLE
    return min(MAX_CYCLE, max(MIN_CYCLE, cycle))


def frame_times(cycle: float, fps: int = FPS) -> list[float]:
    """Evenly spaced capture times over one cycle, at most ``MAX_FRAMES``."""
    count = max(1, min(MAX_FRAMES, round(cycle * fps)))
    step = cycle / count
    return [round(i * step, 4) for i in range(count)]


def encode_gif(frames: Sequence[bytes], frame_ms: int) -> bytes:
    """PNG frames -> one looping GIF (adaptive palette per frame)."""
    from PIL import Image

    if not frames:
        raise RenderError("No frames to encode.")
    images = [
        Image.open(io.BytesIO(data)).convert("RGB").convert("P", palette=Image.Palette.ADAPTIVE)
        for data in frames
    ]
    out = io.BytesIO()
    images[0].save(
        out,
        format="GIF",
        save_all=True,
        append_images=images[1:],
        duration=frame_ms,
        loop=0,
        disposal=2,
    )
    return out.getvalue()


class BrowserRenderer:
    """Headless Chromium via Playwright, started on first use; call ``close`` when done."""

    def __init__(self, executable_path: str | None = None) -> None:
        self._executable = executable_path or None
        self._playwright: Any = None
        self._browser: Any = None
        self._failure: RenderError | None = None  # a failed start is not retried per visual

    def _start(self) -> Any:
        if self._failure is not None:
            raise self._failure
        if self._browser is not None:
            return self._browser
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self._failure = RenderError("Playwright is not installed: uv sync --extra render")
            raise self._failure from None
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(executable_path=self._executable)
        except Exception as exc:  # missing browser build, sandbox errors...
            self.close()
            self._failure = RenderError(f"Could not start Chromium: {exc}")
            raise self._failure from exc
        return self._browser

    def _lost_browser(self) -> None:
        """After a crash, drop the browser so the next visual starts a fresh one."""
        self.close()

    def render(self, svg: str, *, animated: bool) -> Raster:
        browser = self._start()
        try:
            context = browser.new_context(device_scale_factor=GIF_SCALE if animated else PNG_SCALE)
        except Exception as exc:  # the browser died since the last visual
            self._lost_browser()
            raise RenderError(f"Chromium is not responding: {exc}") from exc
        try:
            context.route("**/*", lambda route: route.abort())  # no network from the SVG
            page = context.new_page()
            page.set_content(PAGE.replace("$svg", svg), wait_until="load")
            page.evaluate(SIZE_SCRIPT, [MAX_WIDTH, *DEFAULT_SIZE])
            target = page.locator("svg").first
            if not animated:
                page.evaluate(SEEK_SCRIPT, 0)
                return Raster("png", target.screenshot(type="png"))
            return Raster("gif", _gif(page, target, animation_cycle(svg) or DEFAULT_CYCLE))
        except RenderError:
            raise
        except Exception as exc:  # Playwright surfaces many error types
            raise RenderError(f"Chromium could not render the SVG: {exc}") from exc
        finally:
            try:
                context.close()
            except Exception:  # a crash while closing must not lose a finished image
                logger.debug("Closing a render context failed", exc_info=True)
                self._lost_browser()

    def close(self) -> None:
        try:
            if self._browser is not None:
                self._browser.close()
            if self._playwright is not None:
                self._playwright.stop()
        except Exception:  # closing must never mask the run's own result
            logger.debug("Closing Chromium failed", exc_info=True)
        finally:
            self._browser = self._playwright = None


def _gif(page: Any, target: Any, cycle: float) -> bytes:
    times = frame_times(cycle)
    frames = []
    for moment in times:
        page.evaluate(SEEK_SCRIPT, moment)
        frames.append(target.screenshot(type="png"))
    return encode_gif(frames, frame_ms=round(1000 * cycle / len(times)))

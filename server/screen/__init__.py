"""server.screen (E6): the whole-screen reader.

    from server.screen import get_reader
    reader = get_reader().start()            # capture loop, ~every 2s, OCR only on change
    reader.set_overlay_bounds(rects)         # from the app's `overlay.bounds`
    obs = reader.latest()                    # ScreenObservation(t, app, windows, blocks)
    reader.subscribe(cb)                     # cb(obs) on every new observation
    rect = reader.locate("def pde_residual", app="Code")   # -> Rect(x,y,w,h) in screen points
    reader.watch_metrics("pinn", {"loss": r"epoch\\s+(?P<step>\\d+).*?loss\\s+(?P<value>[0-9.eE+-]+)"}, cb)
    text = await reader.describe("Is the loss curve converging?")   # Claude only
    res = await reader.where("the Run button")
    loc = locate_line("pinn_demo/pinn_convection.py", 47)     # LineLocation: .rect / .visible_lines
    loc = locate_anchor("def pde_residual(", file="pinn_demo/pinn_convection.py")
    marks = candidates("the line that defines add")   # set-of-marks targets for a model to pick by id
    rect = locate_region("terminal")    # / "editor" / "explorer" / "run_button": stable spotlight rects

Pure helpers (no pyobjc, usable on Linux): `server.screen.match.screen_contains/locate_match`,
`server.screen.metrics.TerminalMetricReader`, the types in `server.screen.types`.
"""
from .describe import DescribeError
from .lines import LineLocation
from .match import LocateResult, locate, locate_match, screen_contains
from .regions import REGIONS, Region, RegionStabilizer, find_region
from .types import (
    PERMISSION_HELP,
    Block,
    Rect,
    ScreenObservation,
    ScreenPermissionError,
    Window,
)


def get_reader():
    from .reader import get_reader as _g
    return _g()


def locate_line(file: str | None, line: int, app: str | None = None, obs: ScreenObservation | None = None):
    """-> LineLocation (truthy when the line is on screen; `.rect` full-width row, `.visible_lines`,
    `.direction`, `.reason`). With `obs`, pure OCR of that observation; else the live reader."""
    if obs is not None:
        from .lines import locate_line as _l
        return _l(obs, file, line, app)
    return get_reader().locate_line(file, line, app)


def locate_anchor(text: str, app: str | None = None, file: str | None = None,
                  obs: ScreenObservation | None = None, file_text: str | None = None):
    """-> LineLocation of the editor line containing `text` (+ `.match_rect`, `.line`)."""
    if obs is not None:
        from .lines import locate_anchor as _a
        return _a(obs, text, app, file, file_text)
    return get_reader().locate_anchor(text, app, file)


def locate_region(name: str, app: str | None = None, obs: ScreenObservation | None = None):
    """-> Rect | None of "terminal" | "editor" | "explorer" | "run_button". Live (no `obs`): stabilized
    by the reader (4-pt grid, holds while it moves < 12 pt). With `obs`: one raw frame."""
    if obs is not None:
        reg = find_region(obs, name, app)
        return reg.rect if reg else None
    return get_reader().locate_region(name, app)


def candidates(intent: str | None = None, app: str | None = None, obs: ScreenObservation | None = None,
               max_lines: int = 120):
    """Set-of-marks targets (server.screen.marks): regions 1-4 + OCR lines from id 10, each with a
    rect in screen points. Live (stabilized regions) without `obs`; pure on a given observation."""
    if obs is not None:
        from .marks import candidates as _c
        return _c(obs, intent, app, max_lines=max_lines)
    return get_reader().candidates(intent, app, max_lines)


def observe_image(path: str, overlay=None):
    from .reader import observe_image as _o
    return _o(path, overlay)


__all__ = [
    "PERMISSION_HELP",
    "REGIONS",
    "Block",
    "DescribeError",
    "LineLocation",
    "LocateResult",
    "Rect",
    "Region",
    "RegionStabilizer",
    "ScreenObservation",
    "ScreenPermissionError",
    "Window",
    "candidates",
    "find_region",
    "get_reader",
    "locate",
    "locate_anchor",
    "locate_line",
    "locate_match",
    "locate_region",
    "observe_image",
    "screen_contains",
]

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

Pure helpers (no pyobjc, usable on Linux): `server.screen.match.screen_contains/locate_match`,
`server.screen.metrics.TerminalMetricReader`, the types in `server.screen.types`.
"""
from .describe import DescribeError
from .lines import LineLocation
from .match import LocateResult, locate, locate_match, screen_contains
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


def observe_image(path: str, overlay=None):
    from .reader import observe_image as _o
    return _o(path, overlay)


__all__ = [
    "PERMISSION_HELP",
    "Block",
    "DescribeError",
    "LineLocation",
    "LocateResult",
    "Rect",
    "ScreenObservation",
    "ScreenPermissionError",
    "Window",
    "get_reader",
    "locate",
    "locate_anchor",
    "locate_line",
    "locate_match",
    "observe_image",
    "screen_contains",
]

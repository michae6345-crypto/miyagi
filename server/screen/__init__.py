"""server.screen (E6): the whole-screen reader.

    from server.screen import get_reader
    reader = get_reader().start()            # capture loop, ~every 2s, OCR only on change
    reader.set_overlay_bounds(rects)         # from the app's `overlay.bounds`
    obs = reader.latest()                    # ScreenObservation(t, app, windows, blocks)
    reader.subscribe(cb)                     # cb(obs) on every new observation
    rect = reader.locate("def pde_residual", app="Code")   # -> Rect(x,y,w,h) in screen points
    reader.watch_metrics("pinn", {"loss": r"epoch\\s+(?P<step>\\d+).*?loss\\s+(?P<value>[0-9.eE+-]+)"}, cb)
    text = await reader.describe("Is the loss curve converging?")

Pure helpers (no pyobjc, usable on Linux): `server.screen.match.screen_contains/locate_match`,
`server.screen.metrics.TerminalMetricReader`, the types in `server.screen.types`.
"""
from .match import LocateResult, locate, locate_match, screen_contains
from .types import Block, Rect, ScreenObservation, Window


def get_reader():
    from .reader import get_reader as _g
    return _g()


def observe_image(path: str, overlay=None):
    from .reader import observe_image as _o
    return _o(path, overlay)


__all__ = [
    "Block",
    "LocateResult",
    "Rect",
    "ScreenObservation",
    "Window",
    "get_reader",
    "locate",
    "locate_match",
    "observe_image",
    "screen_contains",
]

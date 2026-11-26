"""Load the recorded frames (fixtures/<name>.ocr.json, made by make_error_fixtures.py) like a live frame."""

from __future__ import annotations

import json
from pathlib import Path

from server.ambient_errors.detect import Row
from server.ambient_errors.tests.make_error_fixtures import FIXTURES
from server.screen.match import group_lines, postprocess
from server.screen.types import Rect, ScreenObservation

FIX = Path(__file__).resolve().parent / "fixtures"
SCREEN_FIX = Path(__file__).resolve().parents[2] / "screen" / "fixtures"


def frame(name: str, *, t: float = 0.0, ax: dict | None = None) -> ScreenObservation:
    path = FIX / f"{name}.ocr.json" if (FIX / f"{name}.ocr.json").exists() else SCREEN_FIX / f"{name}.ocr.json"
    obs = ScreenObservation.from_dict(json.loads(path.read_text(encoding="utf-8")))
    obs.blocks = postprocess(obs.blocks)  # what the live reader does to every frame
    obs.t = t
    if ax is not None:
        obs.ax = ax
    return obs


def ocr_rows(name: str) -> list[Row]:
    return [Row(ln.text, ln.rect) for ln in group_lines(frame(name).blocks)]


def text_rows(name: str) -> list[Row]:
    """The exact text (what the Accessibility tree reads)."""
    return [Row(x) for x in FIXTURES[name].text.splitlines()]


def empty_frame(app: str = "Terminal", title: str = "weather-app — -zsh — 120×34", text: str = "sam@mac ~ %") -> ScreenObservation:
    """A frame of `app` showing one row of text (an error gone from it)."""
    from server.screen.types import Block, Window

    win = Window(app, title, Rect(160, 110, 1180, 640))
    return ScreenObservation(t=0.0, app=app, windows=[win],
                             blocks=[Block(text, Rect(175, 150, 200, 15), 1.0, app, title)],
                             screen=Rect(0, 0, 1728, 1117))

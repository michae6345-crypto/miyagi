"""Plain data types for the screen reader. Pure Python: importable on any OS.

All rects are in macOS screen POINTS, top-left origin of the primary display
(the same space Electron's `screen` module and the `spotlight` event use).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

PERMISSION_HELP = (
    "Screen capture is blocked. Grant Screen Recording permission:\n"
    "  System Settings > Privacy & Security > Screen & System Audio Recording >\n"
    "  enable the app that runs the engine (Terminal / iTerm2 / Visual Studio Code / Claude),\n"
    "  then quit and reopen that app."
)


class ScreenPermissionError(RuntimeError):
    """The process may not capture the screen (macOS Screen Recording permission missing)."""

    def __init__(self, msg: str = PERMISSION_HELP):
        super().__init__(msg)


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def x2(self) -> float:
        return self.x + self.w

    @property
    def y2(self) -> float:
        return self.y + self.h

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    def contains_point(self, px: float, py: float) -> bool:
        return self.x <= px <= self.x2 and self.y <= py <= self.y2

    def contains(self, other: Rect) -> bool:
        """True if `other`'s centre lies inside this rect (good enough for OCR boxes)."""
        return self.contains_point(other.cx, other.cy)

    def union(self, other: Rect) -> Rect:
        x, y = min(self.x, other.x), min(self.y, other.y)
        return Rect(x, y, max(self.x2, other.x2) - x, max(self.y2, other.y2) - y)

    def pad(self, p: float) -> Rect:
        return Rect(self.x - p, self.y - p, self.w + 2 * p, self.h + 2 * p)

    def clamp(self, bounds: Rect) -> Rect:
        x, y = max(self.x, bounds.x), max(self.y, bounds.y)
        x2, y2 = min(self.x2, bounds.x2), min(self.y2, bounds.y2)
        return Rect(x, y, max(0.0, x2 - x), max(0.0, y2 - y))

    def rounded(self) -> Rect:
        return Rect(round(self.x, 1), round(self.y, 1), round(self.w, 1), round(self.h, 1))

    def to_dict(self) -> dict:
        return {"x": round(self.x, 1), "y": round(self.y, 1), "w": round(self.w, 1), "h": round(self.h, 1)}

    @staticmethod
    def from_any(r) -> Rect:
        if isinstance(r, Rect):
            return r
        if isinstance(r, dict):
            return Rect(float(r["x"]), float(r["y"]), float(r.get("w", r.get("width"))), float(r.get("h", r.get("height"))))
        x, y, w, h = r
        return Rect(float(x), float(y), float(w), float(h))


@dataclass(frozen=True)
class Window:
    app: str
    title: str
    rect: Rect
    window_id: int = 0
    pid: int = 0

    def to_dict(self) -> dict:
        return {"app": self.app, "title": self.title, "rect": self.rect.to_dict()}


@dataclass(frozen=True)
class Block:
    """One OCR'd line of text (Vision returns roughly one observation per visual line)."""
    text: str
    rect: Rect
    confidence: float
    app: str | None = None       # owning window's app, None if outside every known window
    window: str | None = None    # owning window's title

    def to_dict(self) -> dict:
        return {"text": self.text, "rect": self.rect.to_dict(), "confidence": round(self.confidence, 3),
                "app": self.app, "window": self.window}


@dataclass
class ScreenObservation:
    t: float                      # unix seconds when the frame was captured
    app: str                      # frontmost app name, e.g. "Code", "Terminal"
    windows: list[Window] = field(default_factory=list)   # front-to-back
    blocks: list[Block] = field(default_factory=list)     # reading order (top-to-bottom, left-to-right)
    screen: Rect = field(default_factory=lambda: Rect(0, 0, 0, 0))  # primary display bounds in points
    scale: float = 1.0            # backing scale factor of the frame (pixels per point)
    ocr_ms: float = 0.0           # how long OCR took for this frame
    frame: int = 0                # monotonically increasing frame counter
    source: str = "live"          # "live", or "fixture:<file>" (explicit/DEMO replay; never silent)

    def text(self, app: str | None = None) -> str:
        """All OCR text, one block per line; optionally only the blocks inside `app`'s windows."""
        from .match import app_matches
        return "\n".join(b.text for b in self.blocks if app is None or app_matches(app, b.app))

    def blocks_in(self, app: str | None) -> list[Block]:
        from .match import app_matches
        return [b for b in self.blocks if app is None or app_matches(app, b.app)]

    def lines_by_app(self) -> dict[str, list[str]]:
        """`{app: [line, ...]}` with Vision's split blocks re-joined into visual rows, in reading
        order. Pass this as `screen=` to `server.checks.evaluate_step` so regexes see whole lines
        (`epoch 2500 | loss 2.5e-01` arrives from Vision as 3 blocks). Text outside every known
        window is under the key ""."""
        from .match import group_lines
        out: dict[str, list[str]] = {}
        for ln in group_lines(self.blocks):
            out.setdefault(ln.app or "", []).append(ln.text)
        return out

    def to_dict(self, with_blocks: bool = True) -> dict:
        d = {"t": self.t, "app": self.app, "windows": [w.to_dict() for w in self.windows],
             "screen": self.screen.to_dict(), "scale": self.scale, "ocr_ms": round(self.ocr_ms, 1),
             "frame": self.frame, "source": self.source}
        if with_blocks:
            d["blocks"] = [b.to_dict() for b in self.blocks]
        return d


__all__ = ["Block", "Rect", "ScreenObservation", "Window", "asdict"]

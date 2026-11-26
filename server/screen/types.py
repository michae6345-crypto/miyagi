"""Plain data types for the screen reader. Pure Python: importable on any OS.

All rects are in macOS screen POINTS, top-left origin of the primary display
(the same space Electron's `screen` module and the `spotlight` event use).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .health import bundled_app


def permission_help() -> str:
    """What to grant when capture is blocked. Inside miyagi.app (MIYAGI_BUNDLED_PYTHON) the grant is miyagi's; a dev
    engine started from a shell needs it on the app that runs it."""
    if bundled_app():
        return ("Screen capture is blocked. Turn on miyagi in System Settings > Privacy & Security >\n"
                "  Screen & System Audio Recording, then quit and reopen miyagi.")
    return ("Screen capture is blocked. Grant Screen Recording permission:\n"
            "  System Settings > Privacy & Security > Screen & System Audio Recording >\n"
            "  enable the app that runs the engine (Terminal / iTerm2 / Visual Studio Code / Claude),\n"
            "  then quit and reopen that app.")


PERMISSION_HELP = permission_help()  # the app sets MIYAGI_BUNDLED_PYTHON before the engine starts: fixed per process


class ScreenPermissionError(RuntimeError):
    """The process may not capture the screen (macOS Screen Recording permission missing)."""

    def __init__(self, msg: str | None = None):
        super().__init__(msg or permission_help())


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


OVERLAY_ROLES = frozenset({"hover", "widget"})   # drawn over the code: left out of text / lines / locate


@dataclass(frozen=True)
class Block:
    """One OCR'd line of text (Vision returns roughly one observation per visual line)."""
    text: str
    rect: Rect
    confidence: float
    app: str | None = None       # owning window's app, None if outside every known window
    window: str | None = None    # owning window's title
    role: str = ""               # "" (content) | "hover" (editor tooltip) | "widget" (inline chat / suggestion
    #                              widget): both are OVERLAY_ROLES, not part of the code

    def to_dict(self) -> dict:
        d = {"text": self.text, "rect": self.rect.to_dict(), "confidence": round(self.confidence, 3),
             "app": self.app, "window": self.window}
        if self.role:
            d["role"] = self.role
        return d


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
    cursor: tuple[float, float] | None = None   # mouse x,y (points, top-left) at capture time
    under_cursor: dict | None = None    # what's under the mouse: see ScreenReader.cursor_context()
    ax: dict | None = None              # AX snapshot (focused editor / terminal / file / dirty)
    ax_lines: dict[str, list[str]] = field(default_factory=dict)  # {app: lines} read via AX (exact, incl. off-screen)
    trigger: str = "tick"               # why this frame was captured: tick|click|typing_pause|app_switch|...
    overlay_excluded: bool = False      # overlay left out at capture time (ScreenCaptureKit)
    capture: str = ""                   # backend that produced the frame: sck | cli | cg | fixture
    editor: dict | None = None          # frontmost VS Code window: {folder, file, path, symbol, dirty, sources}
    #                                     (server.screen.vscode; the one answer to "which file is open")
    foreign: list[Window] = field(default_factory=list)       # VS Code windows of OTHER folders than the lesson's
    #                                     (reader.set_lesson_folder): left out of windows/blocks/AX, front to back
    foreign_rects: list[Rect] = field(default_factory=list)   # the screen areas they show (blacked out for models)

    def text(self, app: str | None = None) -> str:
        """All OCR text, one block per line, plus exact AX text (editor buffer page / terminal rows)
        for matching apps; optionally only `app`'s windows."""
        from .match import app_matches
        lines = [b.text for b in self.blocks if (app is None or app_matches(app, b.app)) and b.role not in OVERLAY_ROLES]
        for a, ax_lines in self.ax_lines.items():
            if app is None or app_matches(app, a):
                lines.extend(ax_lines)
        return "\n".join(lines)

    def blocks_in(self, app: str | None, include_hover: bool = False) -> list[Block]:
        """Blocks of `app`'s windows (all if None). Hover tooltips are left out unless asked for."""
        from .match import app_matches
        return [b for b in self.blocks if (app is None or app_matches(app, b.app))
                and (include_hover or b.role not in OVERLAY_ROLES)]

    def hovers(self) -> list[str]:
        """Text of editor hover tooltips on screen (left out of text()/lines_by_app()/locate())."""
        return [b.text for b in self.blocks if b.role == "hover"]

    def widgets(self) -> list[str]:
        """Text of VS Code inline chat / suggestion widgets on screen (left out like hovers)."""
        return [b.text for b in self.blocks if b.role == "widget"]

    def lines_by_app(self) -> dict[str, list[str]]:
        """`{app: [line, ...]}` with Vision's split blocks re-joined into visual rows, in reading
        order. Pass this as `screen=` to `server.checks.evaluate_step` so regexes see whole lines
        (`epoch 2500 | loss 2.5e-01` arrives from Vision as 3 blocks). Text outside every known
        window is under the key ""."""
        from .match import group_lines
        out: dict[str, list[str]] = {}
        for ln in group_lines(self.blocks):
            out.setdefault(ln.app or "", []).append(ln.text)
        for a, ax_lines in self.ax_lines.items():  # AX text: exact, unsaved, includes scrolled-off lines
            have = set(out.get(a, []))
            out.setdefault(a, []).extend(x for x in ax_lines if x not in have)
        return out

    def to_dict(self, with_blocks: bool = True) -> dict:
        d = {"t": self.t, "app": self.app, "windows": [w.to_dict() for w in self.windows],
             "screen": self.screen.to_dict(), "scale": self.scale, "ocr_ms": round(self.ocr_ms, 1),
             "frame": self.frame, "source": self.source, "trigger": self.trigger,
             "cursor": {"x": self.cursor[0], "y": self.cursor[1]} if self.cursor else None,
             "under_cursor": self.under_cursor, "ax": self.ax, "overlay_excluded": self.overlay_excluded,
             "capture": self.capture, "editor": self.editor, "postprocessed": True}
        if with_blocks:
            d["blocks"] = [b.to_dict() for b in self.blocks]
        if self.foreign:
            d["foreign"] = [w.to_dict() for w in self.foreign]
        return d

    @staticmethod
    def from_dict(d: dict) -> ScreenObservation:
        """Inverse of `to_dict()` (recorded observations: offline tests, replays)."""
        cur = d.get("cursor")
        return ScreenObservation(
            t=float(d.get("t", 0.0)), app=d.get("app", ""),
            windows=[Window(w["app"], w.get("title", ""), Rect.from_any(w["rect"])) for w in d.get("windows", [])],
            blocks=_load_blocks(d),
            screen=Rect.from_any(d["screen"]) if d.get("screen") else Rect(0, 0, 0, 0),
            scale=float(d.get("scale", 1.0)), ocr_ms=float(d.get("ocr_ms", 0.0)), frame=int(d.get("frame", 0)),
            source=d.get("source", "recorded"), cursor=(cur["x"], cur["y"]) if cur else None,
            under_cursor=d.get("under_cursor"), ax=d.get("ax"), trigger=d.get("trigger", "tick"),
            overlay_excluded=bool(d.get("overlay_excluded", False)), capture=d.get("capture", ""),
            editor=d.get("editor"))


def _load_blocks(d: dict) -> list[Block]:
    blocks = [Block(b["text"], Rect.from_any(b["rect"]), float(b.get("confidence", 1.0)), b.get("app"),
                    b.get("window"), b.get("role", "")) for b in d.get("blocks", [])]
    if not d.get("postprocessed"):     # raw recordings: same clean-up a live frame gets
        from .match import postprocess
        blocks = postprocess(blocks)
    return blocks


__all__ = ["Block", "Rect", "ScreenObservation", "Window", "asdict"]

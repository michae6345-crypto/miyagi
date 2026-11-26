"""Where the lesson's VS Code window goes, beside miyagi's lesson panel: one pure policy, no AX, no AppKit.

    from server.workspace import layout as L
    scr = L.Screen(frame=L.Rect(0, 0, 1440, 900), visible=L.Rect(0, 25, 1440, 802))
    p = L.plan(scr, mode="lesson", panel=None, editor=L.EditorState(frame=None))
    p.action        # "set" | "leave"
    p.bounds        # the editor's frame (AX points, top-left origin) when action == "set"
    p.panel, p.side # where the lesson panel docks on that screen (mirror of app core/dock.ts panelRect), "right"

Every rect is in AX / Electron screen points: top-left origin at the primary display's top-left, y grows down.

Inputs
  screen   the display the overlay lives on (v1: the primary display; the engine watches only that one): its full
           frame, its visible frame (NSScreen.visibleFrame: without the menu bar and the Dock, wherever the Dock is, and
           nothing taken when they auto-hide) and safe_top (NSScreen.safeAreaInsets.top: the notch's height, 0 without).
  panel    the panel rect the app reported (panel.state) or None: then the policy's own panel_rect(screen).
  editor   the lesson window now: its frame, whether it is in macOS full screen, and `owned`: None = miyagi never laid
           it out, True = it is still where miyagi put it, False = the learner moved or resized it since.

Rules (Michael, Nov 25, after the MacBook Neo test)
  - macOS full screen is the learner's: leave it (the overlay floats over full-screen Spaces).
  - A window the learner moved or resized is theirs: leave it (lay out once, then only follow).
  - Otherwise: the editor fills the visible frame of the overlay's display left of the panel (PANEL_GAP of air), from
    under the menu bar / notch (plus the island's row on a Mac without a notch, where the pill sits below the menu bar)
    down to the Dock. Video lessons: the left VIDEO_FRACTION (the right column, at least VIDEO_MIN_COLUMN, holds the
    player and the steps drawer: app common/screenLayout.ts).
  - A panel the learner dragged off the right edge isn't followed: the editor keeps the docked panel's room.
  - Already there (within SLACK on every edge): nothing to do. That and the ownership rule are what keep two callers
    from moving the window back and forth.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Literal

# The v2 lesson panel (app core/theme.ts `dock`): 360 wide, 16 in from the work area's right edge, top 52 from the
# display's top (never above the work area's top + 10), ending 16 above the work area's bottom.
PANEL_W, PANEL_INSET, PANEL_TOP, PANEL_TOP_GAP = 360.0, 16.0, 52.0, 10.0
PANEL_GAP = 16.0  # air between the editor's right edge and the panel
PANEL_MIN_H = 120.0
# The v1 drawer (420 + 8 + 8) when the app hasn't said it draws the v2 panel.
PANEL_RESERVE_V1 = 436.0
# Video lessons (app common/screenLayout.ts videoLayout, the same numbers): VS Code takes the left VIDEO_FRACTION of
# the work area, the right column (never under VIDEO_MIN_COLUMN) holds the player and the steps drawer.
VIDEO_FRACTION = float(os.environ.get("MIYAGI_EDITOR_FRACTION", "0.6"))
VIDEO_MIN_COLUMN = 400.0
# A panel the learner dragged away from the right edge (#281: the panel is movable) is no longer "docked": the editor
# doesn't chase it across the screen; it keeps the room of the docked panel.
DOCKED_SLACK = 40.0
# A Mac without a notch shows the island below the menu bar (y ~ menu bar .. +36): the editor's title bar starts under
# it (t10). With a notch the island lives in the notch band, over the menu bar: no room needed.
PILL_CLEARANCE = float(os.environ.get("MIYAGI_PILL_CLEARANCE", "44"))
# The bottom shortcut bar was retired (Michael, Nov 21: no bottom bar in any lesson): nothing kept free at the bottom
# but the Dock (already outside the visible frame). MIYAGI_BAR_CLEARANCE brings back a margin.
BAR_CLEARANCE = float(os.environ.get("MIYAGI_BAR_CLEARANCE", "0"))
# Never narrower / shorter than this, even on the smallest screens (a 1280x800 Mac keeps 880 pt beside the panel).
MIN_W, MIN_H = 560.0, 400.0
SLACK = 4.0  # pt: frames this close are the same frame (AX rounds, VS Code snaps to whole points)

Mode = Literal["lesson", "video"]


def half_up(v: float) -> float:
    """JavaScript's Math.round (Python's round() goes to even: 0.5 -> 0), so the app and the engine agree."""
    return float(math.floor(v + 0.5))


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    def tuple(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.w, self.h)

    def rounded(self) -> Rect:
        return Rect(*(half_up(v) for v in self.tuple()))

    def center_in(self, other: Rect) -> bool:
        cx, cy = self.x + self.w / 2, self.y + self.h / 2
        return other.x <= cx < other.right and other.y <= cy < other.bottom

    @staticmethod
    def of(v) -> Rect | None:
        """Rect from (x, y, w, h), {x, y, w, h} or a Rect; None for anything else or an empty rect."""
        try:
            if isinstance(v, Rect):
                r = v
            elif isinstance(v, dict):
                r = Rect(float(v["x"]), float(v["y"]), float(v["w"]), float(v["h"]))
            elif isinstance(v, (tuple, list)) and len(v) == 4:
                r = Rect(*(float(n) for n in v))
            else:
                return None
        except (KeyError, TypeError, ValueError):
            return None
        return r if r.w > 0 and r.h > 0 else None


def same(a: Rect | None, b: Rect | None, slack: float = SLACK) -> bool:
    return a is not None and b is not None and all(abs(p - q) <= slack for p, q in zip(a.tuple(), b.tuple()))


@dataclass(frozen=True)
class Screen:
    frame: Rect
    visible: Rect
    safe_top: float = 0.0  # the notch's height (NSScreen.safeAreaInsets.top); 0 = no notch
    id: int | None = None

    @property
    def has_notch(self) -> bool:
        return self.safe_top > 0


@dataclass(frozen=True)
class EditorState:
    frame: Rect | None = None
    fullscreen: bool = False
    owned: bool | None = None  # None: never laid out by miyagi; True: still where miyagi put it; False: the learner's


@dataclass(frozen=True)
class Plan:
    action: Literal["set", "leave"]
    bounds: Rect | None
    reason: str
    panel: Rect
    side: Literal["right"] = "right"


def panel_rect(screen: Screen, w: float = PANEL_W) -> Rect:
    """Where the app docks the v2 lesson panel on `screen` (core/dock.ts panelRect, in screen points)."""
    vis, fr = screen.visible, screen.frame
    y = max(fr.y + PANEL_TOP, vis.y + PANEL_TOP_GAP)
    bottom = vis.bottom - PANEL_INSET
    return Rect(vis.right - PANEL_INSET - w, y, w, max(PANEL_MIN_H, bottom - y))


def work_area(screen: Screen, *, pill_clearance: float | None = None, bar_clearance: float | None = None) -> Rect:
    """The room an editor window may take on `screen`: the visible frame, below the notch (a menu bar set to auto-hide
    leaves the notch where it is), below the island's row on a Mac without a notch, above BAR_CLEARANCE."""
    vis, fr = screen.visible, screen.frame
    top = max(vis.y, fr.y + screen.safe_top)
    clear = (PILL_CLEARANCE if pill_clearance is None else pill_clearance) if not screen.has_notch else 0.0
    bottom = vis.bottom - max(0.0, BAR_CLEARANCE if bar_clearance is None else bar_clearance)
    h = bottom - top
    clear = max(0.0, min(clear, h - MIN_H, h * 0.5))  # never under MIN_H (or half the room) for the pill's sake
    top += clear
    return Rect(vis.x, top, vis.w, bottom - top)


def video_editor_w(width: float, fraction: float | None = None) -> float:
    """VS Code's width in a video lesson: the left VIDEO_FRACTION, leaving the right column at least VIDEO_MIN_COLUMN
    (app common/screenLayout.ts videoLayout's editor width, rounded the same way)."""
    f = VIDEO_FRACTION if fraction is None else fraction
    return half_up(max(0.0, min(width * f, width - VIDEO_MIN_COLUMN)))


def docked(screen: Screen, panel: Rect | None) -> bool:
    """The reported panel is the docked one: on this screen, its right edge where the dock puts it."""
    if panel is None or not panel.center_in(screen.frame):
        return False
    want = screen.visible.right - PANEL_INSET
    return abs(panel.right - want) <= DOCKED_SLACK and screen.visible.x < panel.x < screen.visible.right


def target(screen: Screen, mode: Mode = "lesson", panel: Rect | None = None, *, reserve: float | None = None,
           pill_clearance: float | None = None, bar_clearance: float | None = None,
           fraction: float | None = None) -> Rect:
    """The editor's frame on `screen` (whole points). lesson: left of the panel (the reported one when it is on this
    screen, else panel_rect / `reserve` pt short of the right edge); video: the left VIDEO_FRACTION."""
    area = work_area(screen, pill_clearance=pill_clearance, bar_clearance=bar_clearance)
    vis = screen.visible
    if mode == "video":
        right = vis.x + video_editor_w(vis.w, fraction)
    elif docked(screen, panel):
        right = panel.x - PANEL_GAP  # the panel the app really drew
    elif reserve is not None:
        right = vis.right - reserve
    else:
        right = panel_rect(screen).x - PANEL_GAP
    w = max(min(MIN_W, area.w), right - area.x)
    return Rect(area.x, area.y, min(area.w, w), area.h).rounded()


def plan(screen: Screen, *, mode: Mode = "lesson", panel: Rect | None = None, editor: EditorState | None = None,
         reserve: float | None = None, pill_clearance: float | None = None,
         bar_clearance: float | None = None, fraction: float | None = None) -> Plan:
    """Decide once: set the editor's frame, or leave it (and why). Pure."""
    pr = panel if docked(screen, panel) else panel_rect(screen)
    ed = editor or EditorState()
    if ed.fullscreen:
        return Plan("leave", None, "full screen (the learner's; the overlay floats over it)", pr)
    if ed.owned is False:
        return Plan("leave", None, "moved or resized by the learner (theirs now)", pr)
    want = target(screen, mode, panel, reserve=reserve, pill_clearance=pill_clearance, bar_clearance=bar_clearance,
                  fraction=fraction)
    if same(ed.frame, want):
        return Plan("leave", None, "already there", pr)
    return Plan("set", want, "first layout" if ed.owned is None else "follow the panel / display", pr)

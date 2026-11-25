"""App targets (Nov 24, the on-screen coach): the ONE thing on screen a desktop-app lesson's step acts on, found for free.

In a no-code lesson (Blender, AutoCAD, Photoshop...: server.lesson.app_lesson sets graph.lesson.app) the coach circles
the control or area the step names and writes the step beside it (server/orchestrator/onscreen_coach.py). Placing the
circle never calls a model. The phrase comes from the step's own words; the rect from, in order:

  1. bridge  the app's own bridge (Blender: server.workspace.blender_ext.ui_rects, imported lazily inside the function;
             absent, None, a raise or an unknown shape = skip). Area words ("viewport", "Properties", "Outliner",
             "timeline", "shader editor") map to Blender area types; object names in the step match ui.objects.
  2. AX      a bounded walk (<= 2500 nodes) of the named app's Accessibility tree: a rect only when exactly ONE element's
             label equals the phrase (case and whitespace aside). server.screen.ax primitives, read-only.
  3. OCR     the latest frame's text in that app's window: equal to the phrase, or a fuzzy ratio >= 92 for phrases of
             4+ chars, confidence >= 0.5; exactly one candidate, or a best that beats the second by >= 8.

Confidence gate (a wrong circle is worse than none): a rect outside the app's window, under miyagi's overlay, smaller
than 6 pt on a side, larger than 40% of the window (a bridge area aside), on a frame older than 2 s, or with another
app in front is dropped. All rects are screen points, top-left origin of the primary display (types.Rect).
"""
from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from .types import OVERLAY_ROLES, Rect

log = logging.getLogger("server.screen.app_target")

MIN_SIDE_PT = 6.0
MAX_WINDOW_SHARE = 0.40
MAX_FRAME_AGE_S = 2.0
MAX_AX_NODES = 2500
OCR_MIN_CONF = 0.5
OCR_FUZZY = 92.0
OCR_MARGIN = 8.0
MAX_PHRASE_CHARS = 40
OVERLAY_APPS = frozenset({"miyagi", "electron", "miyagi-overlay"})  # our own overlay in front is not "another app"

# Blender area words -> area types (the bridge's area["type"]; a shader editor is a NODE_EDITOR)
AREA_WORDS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"\b(?:3d\s*view(?:port)?|viewport)\b", re.I), "VIEW_3D"),
    (re.compile(r"\b(?:properties(?:\s+(?:editor|panel))?|modifiers?(?:\s+(?:tab|panel|properties))?)\b", re.I),
     "PROPERTIES"),
    (re.compile(r"\boutliner\b", re.I), "OUTLINER"),
    (re.compile(r"\btimeline\b", re.I), "TIMELINE"),
    (re.compile(r"\b(?:shader|node)\s+editor\b", re.I), "NODE_EDITOR"),
)
_REGEXY = re.compile(r"[\\^$|\[\]{}()*+?]|\.\*")
_QUOTED = re.compile(r"\"([^\"\n]{1,40})\"|“([^”\n]{1,40})”|‘([^’\n]{1,40})’|(?<![\w])'([^'\n]{1,40})'(?![\w])")
_MENU_PATH = re.compile(r"(?<![\w>])([A-Z][\w&-]*(?:[ \t]+[A-Z][\w&-]*){0,2})[ \t]*(?:>|→|›|»)[ \t]*[A-Za-z]")
_CLICK = re.compile(r"\b(?i:click|choose|select|open|pick|tap)\s+(?i:on\s+)?(?i:the\s+)?"
                    r"([A-Z][\w&-]*(?:[ \t]+[A-Z][\w&-]*){0,3})")
_KEYISH = re.compile(r"^(?:[A-Z]|F\d{1,2}|Tab|Esc|Escape|Return|Enter|Space|Delete|Backspace|Shift|Ctrl|Control|"
                     r"Alt|Option|Cmd|Command)$")
_ADD_NEW = re.compile(r"\b(?:add|insert|create)\s+(?:a|an|new|another)\s+$", re.I)


@dataclass(frozen=True)
class Target:
    rect: Rect
    via: str      # "bridge" | "ax" | "ocr"
    label: str    # the phrase that was found (<= 4 words on the mark)


@dataclass(frozen=True)
class Phrase:
    text: str
    kind: str     # "ui" (a control's words) | "area" (a Blender area type)


def norm(s: str | None) -> str:
    return " ".join(str(s or "").replace("…", "").replace("...", "").split()).strip(" .:;,!?").lower()


# ------------------------------------------------------------------ phrases (free, from the step's own words)

def phrases(step: dict) -> list[Phrase]:
    """What to look for, in order: step.targets[].match (not regex-like, <= 40 chars), quoted UI names in the
    instructions, the first segment of a menu path ("Add > Mesh > Torus" -> "Add"), "Click <Name>", then Blender area
    words. Object names are matched by the bridge itself (bridge_target)."""
    out: list[Phrase] = []
    seen: set[str] = set()

    def add(text: str, kind: str = "ui") -> None:
        t = " ".join(str(text or "").split()).strip(" .:;,!?")
        if not t or len(t) > MAX_PHRASE_CHARS or len(t.split()) > 5 or (kind == "ui" and _KEYISH.match(t)):
            return
        key = f"{kind}:{t.lower()}"
        if key not in seen:
            seen.add(key)
            out.append(Phrase(t, kind))

    for tg in step.get("targets") or []:
        m = tg.get("match") if isinstance(tg, dict) else None
        if isinstance(m, str) and m.strip() and not _REGEXY.search(m):
            add(m)
    text = "\n".join(str(step.get(k) or "") for k in ("instructions", "title"))
    for m in _QUOTED.finditer(text):
        add(next(g for g in m.groups() if g))
    for m in _MENU_PATH.finditer(text):
        add(m.group(1))
    for m in _CLICK.finditer(text):
        add(m.group(1))
    for rx, area in AREA_WORDS:
        if rx.search(text):
            add(area, "area")
    return out


# ------------------------------------------------------------------ rect helpers

def _rect(d) -> Rect | None:
    """{x, y, w, h} / {x, y, width, height} / a dict with a "rect" / [x, y, w, h] -> Rect; None for anything else."""
    try:
        if isinstance(d, Rect):
            return d
        if isinstance(d, dict) and isinstance(d.get("rect"), (dict, list, tuple)):
            d = d["rect"]
        if isinstance(d, dict):
            w, h = d.get("w", d.get("width")), d.get("h", d.get("height"))
            r = Rect(float(d["x"]), float(d["y"]), float(w), float(h))
        elif isinstance(d, (list, tuple)) and len(d) == 4:
            r = Rect(*(float(v) for v in d))
        else:
            return None
    except (KeyError, TypeError, ValueError):
        return None
    return r if r.w > 0 and r.h > 0 else None


def _overlap(a: Rect, b: Rect) -> float:
    w = min(a.x2, b.x2) - max(a.x, b.x)
    h = min(a.y2, b.y2) - max(a.y, b.y)
    return max(0.0, w) * max(0.0, h)


def gate(rect: Rect | None, window: Rect | None, overlay: Iterable = (), *, area: bool = False) -> Rect | None:
    """The confidence gate: the rect, or None when it is too small, outside the app's window, under miyagi's overlay,
    or larger than 40% of the window (a bridge area may be). No window known: None (nothing to check it against)."""
    if rect is None or window is None or window.w <= 0 or window.h <= 0:
        return None
    if rect.w < MIN_SIDE_PT or rect.h < MIN_SIDE_PT:
        return None
    if not window.contains(rect) or _overlap(rect, window) < 0.5 * rect.w * rect.h:
        return None
    if not area and rect.w * rect.h > MAX_WINDOW_SHARE * window.w * window.h:
        return None
    for o in overlay or ():
        o = _rect(o.to_dict() if hasattr(o, "to_dict") else o)
        if o is not None and (o.contains(rect) or _overlap(rect, o) > 0.25 * rect.w * rect.h):
            return None
    return rect


def _names(app: dict) -> list[str]:
    """The window names of the app the learner works in: `using` first (FreeCAD for AutoCAD), then the lesson's."""
    out: list[str] = []
    try:
        from server.workspace import apps
    except Exception:  # noqa: BLE001
        apps = None
    using = str(app.get("using") or "").strip()
    if using:
        tool = apps.canonical(using) if apps is not None else None
        out += ([*apps.process_names(tool)] if tool and apps is not None else []) + [using]
    tool = str(app.get("tool") or "")
    if apps is not None and tool and not using:
        out += apps.process_names(tool)
    if not using:
        out.append(str(app.get("label") or tool))
    seen: list[str] = []
    for n in out:
        if n and n.lower() not in (s.lower() for s in seen):
            seen.append(n)
    return seen


def _matches(names: list[str], actual: str | None) -> bool:
    from .match import app_matches

    return any(app_matches(n, actual) for n in names)


def app_window(obs, names: list[str]) -> Rect | None:
    """The front-most window of the app in the frame (windows are front-to-back), else None."""
    for w in getattr(obs, "windows", None) or []:
        if _matches(names, getattr(w, "app", None)):
            return _rect(getattr(w, "rect", None))
    return None


# ------------------------------------------------------------------ 1. the app's own bridge

def _bridge_ui() -> dict | None:
    """blender_ext.ui_rects(), imported here (never at module level: the bridge lane owns that module). Absent, missing
    ui_rects, None, a raise or not a dict: None."""
    try:
        from server.workspace import blender_ext
    except ImportError:
        return None
    fn = getattr(blender_ext, "ui_rects", None)
    if not callable(fn):
        return None
    try:
        ui = fn()
    except Exception as e:  # noqa: BLE001 - the bridge is a refinement: never a crash
        log.info("bridge ui_rects failed (%s): AX / OCR instead", e)
        return None
    if hasattr(ui, "close") and not isinstance(ui, dict):  # a coroutine / generator: not the shape we know
        try:
            ui.close()
        except Exception:  # noqa: BLE001
            pass
        return None
    return ui if isinstance(ui, dict) else None


def bridge_shape(ui: dict | None, window: Rect | None = None) -> dict | None:
    """The bridge's reply as {"window": Rect | None, "areas": [(type, ui_type, Rect)], "objects": [(name, Rect)]} in
    screen points. Two shapes:
      - points: {"window": rect, "areas": [{"type", "rect"}], "objects": [{"name", "rect"}]}
      - Blender's raw /ui: {"origin": "bottom-left", "windows": [{x, y, width, height, areas: [{type, ui_type, x, y,
        width, height}]}]} in Blender pixels, area x / y relative to its window: placed on the app's window on screen
        (`window`, from the frame), bottom-aligned (the screen rect includes the title bar, Blender's doesn't).
    None for anything else."""
    if not isinstance(ui, dict):
        return None
    try:
        if isinstance(ui.get("windows"), list):
            wins = [w for w in ui["windows"] if isinstance(w, dict) and _rect(w) is not None]
            if not wins or window is None:
                return None
            bw = max(wins, key=lambda w: _rect(w).w * _rect(w).h)
            braw = _rect(bw)
            k = window.w / braw.w
            bottom = window.y + window.h
            areas = []
            for a in bw.get("areas") or []:
                r = _rect(a) if isinstance(a, dict) else None
                if r is None:
                    continue
                if str(ui.get("origin") or "bottom-left") == "bottom-left":
                    y = bottom - (r.y + r.h) * k
                else:
                    y = bottom - braw.h * k + r.y * k
                areas.append((str(a.get("type") or ""), str(a.get("ui_type") or ""),
                              Rect(window.x + r.x * k, y, r.w * k, r.h * k)))
            return {"window": window, "areas": areas, "objects": []}
        if "areas" in ui or "objects" in ui or "window" in ui:
            win = _rect(ui.get("window")) or window
            areas = [(str(a.get("type") or ""), str(a.get("ui_type") or ""), r) for a in ui.get("areas") or []
                     if isinstance(a, dict) and (r := _rect(a)) is not None]
            objs = [(str(o.get("name") or ""), r) for o in ui.get("objects") or []
                    if isinstance(o, dict) and o.get("name") and (r := _rect(o)) is not None]
            return {"window": win, "areas": areas, "objects": objs}
    except (TypeError, ValueError, ZeroDivisionError, AttributeError):
        return None
    return None


def _area_type(phrase: str) -> str | None:
    p = phrase.strip()
    if p in _AREA_LABEL:
        return p
    for rx, t in AREA_WORDS:
        if rx.fullmatch(p) or (rx.search(p) and len(p.split()) <= 3):
            return t
    return None


def bridge_rect(phrase: str, ui: dict | None) -> tuple[Rect, bool] | None:
    """(rect, is_area) for a phrase in a bridge_shape(): an area word -> the largest area of that type; an object name
    (case aside) -> that object. None when it names neither."""
    if not ui:
        return None
    want = _area_type(phrase)
    if want:
        hits = [r for t, ut, r in ui.get("areas") or []
                if t == want or (want == "NODE_EDITOR" and "shader" in ut.lower())]
        if hits:
            return max(hits, key=lambda r: r.w * r.h), True
    n = norm(phrase)
    objs = [r for name, r in ui.get("objects") or [] if norm(name) == n]
    if len(objs) == 1:
        return objs[0], False
    return None


def _object_in(step: dict, ui: dict) -> tuple[str, Rect] | None:
    """An object the step names as written ("Select the Cube"), never one it adds ("add a Cube")."""
    text = " ".join(str(step.get(k) or "") for k in ("instructions", "title"))
    for name, r in sorted(ui.get("objects") or [], key=lambda o: -len(o[0])):
        m = re.search(rf"(?<![\w.]){re.escape(name)}(?![\w])", text)
        if m and not _ADD_NEW.search(text[:m.start()]):
            return name, r
    return None


def bridge_target(step: dict, app: dict, *, window: Rect | None = None, ui: dict | None = None,
                  phrase_list: list[Phrase] | None = None) -> tuple[Target, Rect | None, bool] | None:
    """(Target, the bridge's window, is_area) from the app's bridge (Blender only today), else None."""
    if str(app.get("tool") or "").lower() != "blender" and norm(app.get("using")) != "blender":
        return None
    raw = ui if ui is not None else _bridge_ui()
    shape = bridge_shape(raw, window)
    if not shape:
        return None
    if (hit := _object_in(step, shape)) is not None:
        return Target(hit[1], "bridge", hit[0]), shape.get("window"), False
    for ph in phrase_list if phrase_list is not None else phrases(step):
        got = bridge_rect(ph.text, shape)
        if got is not None:
            label = ph.text if ph.kind == "ui" else _AREA_LABEL.get(ph.text, ph.text)
            return Target(got[0], "bridge", label), shape.get("window"), got[1]
    return None


_AREA_LABEL = {"VIEW_3D": "3D Viewport", "PROPERTIES": "Properties", "OUTLINER": "Outliner", "TIMELINE": "Timeline",
               "NODE_EDITOR": "Shader Editor"}


# ------------------------------------------------------------------ 2. Accessibility

class AxTree:
    """The real AX tree of the named app's focused window (server.screen.ax primitives, read-only). Tests pass a fake
    with the same four methods."""

    def __init__(self, names: list[str]):
        self.names = names

    def root(self):
        from . import ax
        from AppKit import NSWorkspace

        if not ax.trusted():
            return None, None
        for a in NSWorkspace.sharedWorkspace().runningApplications() or []:
            if _matches(self.names, str(a.localizedName() or "")):
                app_el = ax.AX.AXUIElementCreateApplication(int(a.processIdentifier()))
                ax.AX.AXUIElementSetMessagingTimeout(app_el, ax.MESSAGING_TIMEOUT)
                win = ax.attr(app_el, "AXFocusedWindow") or ax.attr(app_el, "AXMainWindow")
                return win, ax.rect_of(win) if win is not None else None
        return None, None

    def children(self, el) -> list:
        from . import ax

        return list(ax.attr(el, "AXChildren") or [])

    def labels(self, el) -> list[str]:
        from . import ax

        return ax._labels(el)

    def rect(self, el) -> Rect | None:
        from . import ax

        return ax.rect_of(el)


def ax_target(window_app: str | list[str], phrase: str, *, tree=None, max_nodes: int = MAX_AX_NODES
              ) -> tuple[Rect, Rect | None] | None:
    """(rect, window rect) of the ONE element of the app's window whose label equals the phrase (case and whitespace
    aside); None for 0 or 2+ such elements (elements with the same rect count once), no window, or any AX error."""
    names = [window_app] if isinstance(window_app, str) else list(window_app)
    want = norm(phrase)
    if not want:
        return None
    try:
        tree = tree or AxTree(names)
        root, win = tree.root()
        if root is None:
            return None
        hits: list[Rect] = []
        queue, seen = [root], 0
        while queue and seen < max_nodes:
            el = queue.pop(0)
            seen += 1
            if any(norm(lb) == want for lb in tree.labels(el) or []):
                r = tree.rect(el)
                if r is not None and not any(r.rounded() == h.rounded() for h in hits):
                    hits.append(r)
                    if len(hits) > 1:
                        return None
            queue.extend(tree.children(el) or [])
        return (hits[0], win) if len(hits) == 1 else None
    except Exception as e:  # noqa: BLE001 - no AX (permission, binding, a dead app): OCR next
        log.info("AX target for %r failed: %s", phrase, e)
        return None


# ------------------------------------------------------------------ 3. OCR

def _spans(text: str, rect: Rect, want: str) -> list[Rect]:
    """Sub-rects of a block whose words equal `want` (a header row "View Select Add Object" -> "Add"), placed by
    character share of the block's width."""
    words = list(re.finditer(r"\S+", text))
    n = len(want.split())
    out = []
    if not words or len(words) <= n:
        return out
    total = max(1, len(text))
    for i in range(len(words) - n + 1):
        seg = text[words[i].start():words[i + n - 1].end()]
        if norm(seg) == want:
            x0, x1 = words[i].start() / total, words[i + n - 1].end() / total
            out.append(Rect(rect.x + rect.w * x0, rect.y, max(1.0, rect.w * (x1 - x0)), rect.h))
    return out


def ocr_target(obs, phrase: str, window_app: str | list[str], *, window: Rect | None = None) -> Rect | None:
    """The rect of the phrase in the app's window on this frame: blocks equal to it (or a word run inside a block equal
    to it), or with a fuzzy ratio >= 92 for 4+ char phrases; confidence >= 0.5. Exactly one candidate, or a best that
    beats the second by >= 8; else None."""
    from rapidfuzz import fuzz

    names = [window_app] if isinstance(window_app, str) else list(window_app)
    want = norm(phrase)
    if not want or obs is None:
        return None
    cands: list[tuple[float, Rect]] = []
    for b in getattr(obs, "blocks", None) or []:
        if getattr(b, "role", "") in OVERLAY_ROLES or float(getattr(b, "confidence", 0.0)) < OCR_MIN_CONF:
            continue
        if not _matches(names, getattr(b, "app", None)):
            continue
        r = _rect(getattr(b, "rect", None))
        if r is None or (window is not None and not window.contains(r)):
            continue
        got = norm(getattr(b, "text", ""))
        if got == want:
            cands.append((100.0, r))
            continue
        spans = _spans(" ".join(str(getattr(b, "text", "")).split()), r, want)
        if spans:
            cands.extend((100.0, s) for s in spans)
            continue
        if len(want) >= 4:
            score = float(fuzz.ratio(got, want))
            if score >= OCR_FUZZY:
                cands.append((score, r))
    if not cands:
        return None
    cands.sort(key=lambda c: -c[0])
    if len(cands) == 1 or cands[0][0] - cands[1][0] >= OCR_MARGIN:
        return cands[0][1]
    return None


# ------------------------------------------------------------------ the chain

def resolve(step: dict, app: dict, obs, overlay_rects: Iterable = (), *, front: str | None = None,
            now: float | None = None, bridge: Callable | None = None, ax_fn: Callable | None = None,
            ocr_fn: Callable | None = None, phrase_list: list[Phrase] | None = None) -> Target | None:
    """Bridge, then AX, then OCR, then None; each hit through gate(). front: the app in front now ('' / None: unknown,
    then the frame's). bridge / ax_fn / ocr_fn: test seams (default: bridge_target / ax_target / ocr_target)."""
    if not isinstance(step, dict) or not isinstance(app, dict):
        return None
    names = _names(app)
    if not names:
        return None
    now = time.time() if now is None else now
    front = (front or getattr(obs, "app", None) or "").strip()
    if front and front.lower() not in OVERLAY_APPS and not _matches(names, front):
        log.info("on-screen coach: %s is in front, not %s: no circle", front, names[0])
        return None
    overlay = list(overlay_rects or [])
    fresh = obs is not None and now - float(getattr(obs, "t", 0.0) or 0.0) <= MAX_FRAME_AGE_S
    win = app_window(obs, names) if fresh else None
    plist = phrase_list if phrase_list is not None else phrases(step)

    got = (bridge or bridge_target)(step, app, window=win, phrase_list=plist)
    if got is not None:
        t, bwin, area = got
        if (r := gate(t.rect, bwin or win, overlay, area=area)) is not None:
            return Target(r, "bridge", t.label)
    ui = [p for p in plist if p.kind == "ui"]
    for ph in ui:
        hit = (ax_fn or ax_target)(names, ph.text)
        if hit is not None:
            r, awin = hit
            if (r := gate(r, awin or win, overlay)) is not None:
                return Target(r, "ax", ph.text)
    if not fresh or win is None:
        return None
    for ph in ui:
        r = (ocr_fn or ocr_target)(obs, ph.text, names, window=win)
        if (r := gate(r, win, overlay)) is not None:
            return Target(r, "ocr", ph.text)
    return None

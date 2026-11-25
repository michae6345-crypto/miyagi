"""App targets (Nov 24, the on-screen coach): the ONE thing on screen a desktop-app lesson's step acts on, found for free.

In a no-code lesson (Blender, AutoCAD, Photoshop...: server.lesson.app_lesson sets graph.lesson.app) the coach circles
the control or area the step names and writes the step beside it (server/orchestrator/onscreen_coach.py). Placing the
circle never calls a model. The phrases come from the step's own words (phrases(): kind "ui" a control's words, "tab"
a Properties tab, "area" an editor, "region" a sidebar / toolbar / header); the rect from, in order:

  1. object  the app's own bridge (Blender: server.workspace.blender_ext.ui_rects, imported lazily inside the function,
             asked once per resolve; absent, None, a raise or an unknown shape = skip): an object the step acts on by
             name ("Select the Donut", case aside; never "add a Donut" / "Add a second Donut", never a name heading a
             place: "the Light properties", "Camera view"), or names at all when the step has no ui / tab phrase. "the
             Donut in the Outliner": OCR of the name inside the Outliner's rect, else the viewport box. A where ask
             (phrase_list) circles only an object the ask names ("where is the Cube?"), never the step's.
  2. AX      a bounded walk (<= 2500 nodes) of the named app's Accessibility tree: a rect only when exactly ONE element's
             label equals the phrase (case and whitespace aside). server.screen.ax primitives, read-only.
  3. OCR     the latest frame's text in that app's window: equal to the phrase, or a fuzzy ratio >= 92 for phrases of
             4+ chars, confidence >= 0.5; exactly one candidate, or a best that beats the second by >= 8.
  4. tab     a Properties tab the step names ("the Modifier tab", "Material properties", the wrench): the bridge's tab
             column (NAVIGATION_BAR). One tab's own rect only once TAB_LAYOUT_CONFIDENT (tab positions are an estimate
             nothing has verified yet), so today the column.
  5. area    last, the bridge's region ("the sidebar" / "N panel", "the toolbar", "the viewport header") or area for an
             area word the step uses as an area ("in the viewport", "the Outliner"; never "the Levels Viewport field",
             "Viewport Display" or a bare "modifier"): a precise control (AX / OCR) always beats a whole editor.

Bridge geometry is trusted only on a calibrated window: the frame's Blender window, scale k = screen width / Blender
width within 3% of 0.5 or 1.0 (a macOS backing scale of 2 or 1), its height a title bar (~28 pt, or ~0 full screen)
taller than Blender's; none fits, or two fit alike: no bridge rects at all.

Confidence gate (a wrong circle is worse than none): a rect outside the app's window, under miyagi's overlay, smaller
than 6 pt on a side, larger than 40% of the window (a bridge area / region aside), off the primary display (marks carry
no displayId), on a frame older than 2 s, or with another app in front is dropped. All rects are screen points,
top-left origin of the primary display (types.Rect). The caller hands in a fresh frame (ScreenBridge.fresh: a still
screen's latest frame can be minutes old, since the reader keeps it until something changes).
"""
from __future__ import annotations

import contextlib
import importlib
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
TITLE_BAR_PT = 28.0          # a macOS window's title bar: the screen window counts it, Blender's own size doesn't
TITLE_BAR_SLACK_PT = 24.0    # a Blender window fits the screen window when its implied title bar is within this of 28
FULLSCREEN_SLACK_PT = 4.0    # ... or within this of 0 (a full-screen window has no title bar)
WINDOW_MATCH_MARGIN_PT = 12.0  # ... and the next best fit is at least this much worse (else ambiguous: no rects)
BACKING_SCALES = (0.5, 1.0)  # k = screen pt / Blender px: Retina (2 px per pt) or not; anything else is a miscalibration
SCALE_TOLERANCE = 0.03       # k within 3% of one of them
MIN_OBJECT_NAME = 3          # object names shorter than this are never matched in a step's words
OVERLAY_APPS = frozenset({"miyagi", "electron", "miyagi-overlay"})  # our own overlay in front is not "another app"

# A Properties tab's own rect (estimate_tab) only once its layout is verified against a real Blender window; tab
# positions cannot be checked headless, so until then a tab phrase circles the whole tab column.
TAB_LAYOUT_CONFIDENT = False

# Blender area words -> area types (the bridge's area["type"]; a shader editor is a NODE_EDITOR). "modifier" names the
# Properties editor only as "modifier(s) tab / panel / properties": a bare "modifier" is the thing added, not a place.
# Use area_types() on a sentence: it also skips an area word inside a capitalized UI name ("Levels Viewport").
AREA_WORDS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"\b(?:3d\s*view(?:port)?|viewport)\b", re.IGNORECASE), "VIEW_3D"),
    (re.compile(r"\b(?:modifiers?\s+(?:tab|panel|properties)|properties(?:\s+(?:editor|panel|tab))?)\b", re.IGNORECASE),
     "PROPERTIES"),
    (re.compile(r"\boutliner\b", re.IGNORECASE), "OUTLINER"),
    (re.compile(r"\btimeline\b", re.IGNORECASE), "TIMELINE"),
    (re.compile(r"\b(?:shader|node)\s+editor\b", re.IGNORECASE), "NODE_EDITOR"),
)
_REGEXY = re.compile(r"[\\^$|\[\]{}()*+?]|\.\*")
_QUOTED = re.compile(r"\"([^\"\n]{1,40})\"|“([^”\n]{1,40})”|‘([^’\n]{1,40})’|(?<![\w])'([^'\n]{1,40})'(?![\w])")
_MENU_PATH = re.compile(r"(?<![\w>])([A-Z][\w&-]*(?:[ \t]+[A-Z][\w&-]*){0,2})[ \t]*(?:>|→|›|»)[ \t]*[A-Za-z]")
_CLICK = re.compile(r"\b(?i:click|choose|select|open|pick|tap)\s+(?i:on\s+)?(?i:the\s+)?"
                    r"([A-Z][\w&-]*(?:[ \t]+[A-Z][\w&-]*){0,3})")
_KEYISH = re.compile(r"^(?:[A-Z]|F\d{1,2}|Tab|Esc|Escape|Return|Enter|Space|Delete|Backspace|Shift|Ctrl|Control|"
                     r"Alt|Option|Cmd|Command)$")
_FIELD_NOUN = re.compile(r"^\s+(?:field|value|setting|checkbox|check\s*box|slider)e?s?\b", re.IGNORECASE)
_AREA_NOUN = re.compile(r"^\s+(?:tab|panel|editor|area|window|header)s?\b", re.IGNORECASE)
_NEXT_CAP = re.compile(r"^[ \t]+[A-Z]")
_PREV_WORD = re.compile(r"([A-Za-z][\w'’-]*)[ \t]+$")
_SENTENCE_START = re.compile(r"(?:^|[.!?:;\n\"“(]\s*)$")
_NOT_A_NAME = frozenset({"blender", "blender's", "blender’s"})  # "the Blender viewport" is the viewport
# "add a Donut", "Add a second Cube", "Add another mesh Cube", "Add a UV Sphere": up to two words between the article
# and the name (the new object's kind / ordinal), never the existing object of that name; "Add the Donut from the Add
# menu": the one being added too
_ADD_NEW = re.compile(r"\b(?:add|insert|create)\s+(?:(?:a|an|new|another)(?:[ \t]+[\w.-]+){0,2}|the)[ \t]+$",
                      re.IGNORECASE)
# a name the step only names (no verb acts on it) is an object only right after an article / determiner, exactly as
# spelled: "the Empty is", never "the field is empty" or "the viewport area"
_DETERMINER = re.compile(r"\b(?:the|your|this|that)[ \t]+$", re.IGNORECASE)
# an object's name used as the head of a UI place or another name ("the Light properties", "Camera view", "the Light
# settings", "Cube Mesh"): not the object itself
_NAME_AS_HEAD = re.compile(r"^(?:['’]s)?[ \t]+(?:(?:properties|property|tabs?|panels?|editors?|views?|settings?|data|"
                           r"menus?)\b|[A-Z])")
# words that may follow an object the step only names (not acts on): "the Donut is", "the Donut from the side"; any
# other word makes the name an attribute's head ("the Light power", "the Cube scale"), not the object
_AFTER_NAMED = frozenset({
    "in", "on", "at", "to", "into", "onto", "from", "with", "without", "within", "near", "behind", "below", "above",
    "under", "over", "and", "or", "but", "nor", "is", "are", "was", "were", "be", "should", "will", "would", "can",
    "could", "must", "may", "might", "has", "have", "had", "now", "so", "then", "until", "while", "when", "by",
    "for", "of", "as", "up", "down", "back", "again", "too", "that", "which", "you", "it", "its", "looks", "look",
    "appears", "appear", "seems", "seem", "sits", "stays"
})

# Properties tabs (SpaceProperties.context) by the words a step uses for them: "the Modifier tab", "Material
# properties", "Object Data properties", the wrench.
TAB_NAMES: dict[str, str] = {
    "modifier": "MODIFIER", "modifiers": "MODIFIER", "wrench": "MODIFIER",
    "material": "MATERIAL", "materials": "MATERIAL",
    "object": "OBJECT",
    "object data": "DATA", "mesh data": "DATA", "data": "DATA",
    "render": "RENDER", "output": "OUTPUT", "world": "WORLD", "physics": "PHYSICS",
    "constraint": "CONSTRAINT", "constraints": "CONSTRAINT", "object constraint": "CONSTRAINT",
    "object constraints": "CONSTRAINT",
    "particle": "PARTICLES", "particles": "PARTICLES", "particle system": "PARTICLES",
    "particle systems": "PARTICLES",
    "scene": "SCENE", "view layer": "VIEW_LAYER", "texture": "TEXTURE", "textures": "TEXTURE",
    "collection": "COLLECTION", "collections": "COLLECTION",
    # a light's / camera's Object Data tab is called its Light / Camera properties
    "light": "DATA", "camera": "DATA",
}
TAB_LABEL: dict[str, str] = {"MODIFIER": "Modifier tab", "MATERIAL": "Material tab", "OBJECT": "Object tab",
                             "DATA": "Object Data tab", "RENDER": "Render tab", "OUTPUT": "Output tab",
                             "WORLD": "World tab", "PHYSICS": "Physics tab", "CONSTRAINT": "Constraints tab",
                             "PARTICLES": "Particles tab", "SCENE": "Scene tab", "VIEW_LAYER": "View Layer tab",
                             "TEXTURE": "Texture tab", "COLLECTION": "Collection tab"}
_TAB_KEYS = "|".join(sorted((re.escape(k).replace(r"\ ", r"\s+") for k in TAB_NAMES if k != "wrench"),
                            key=lambda k: -len(k)))
_TAB_RX = re.compile(rf"\b({_TAB_KEYS})\s+(?:properties|property\s+tab|tab)\b|\b(modifiers?)\s+panel\b|\b(wrench)\b",
                     re.IGNORECASE)
_PLACE_NOUN = re.compile(r"^[ \t]+(tab|panel|properties|property|editor|area)s?\b", re.IGNORECASE)
_PLACE = re.compile(r"^(.*?)[ \t]+(tab|panel|properties|property|editor|area)s?$", re.IGNORECASE)
_MENU_BEFORE = re.compile(r"(?:>|→|›|»)\s*$")

# Blender regions by the words a step uses for them -> (area type, region type); "header" only with its editor named
REGION_WORDS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"\b(?:side\s?bar|n[ \t-]panel)\b", re.IGNORECASE), "VIEW_3D:UI"),
    (re.compile(r"\b(?:tool\s?bar|t[ \t-]panel)\b", re.IGNORECASE), "VIEW_3D:TOOLS"),
)
_HEADER = re.compile(r"\b(3d\s*view(?:port)?|viewport|outliner|timeline|properties(?:\s+editor)?|(?:shader|node)\s+"
                     r"editor)(?:['’]s)?\s+header\b|\bheader\s+of\s+the\s+(3d\s*view(?:port)?|viewport|outliner|"
                     r"timeline|properties(?:\s+editor)?|(?:shader|node)\s+editor)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Target:
    rect: Rect
    via: str      # "bridge" | "ax" | "ocr"
    label: str    # the phrase that was found (<= 4 words on the mark)


@dataclass(frozen=True)
class Phrase:
    text: str
    kind: str     # "ui" (a control's words) | "ui_exact" (a control's whole label only: an exact AX label or a whole
    #               OCR block, never a word run inside a longer block) | "tab" (a Properties context: "MODIFIER") |
    #               "area" (a Blender area type: "VIEW_3D") | "region" ("VIEW_3D:UI": an area type and a region type)


UI_KINDS = ("ui", "ui_exact")


def norm(s: str | None) -> str:
    return " ".join(str(s or "").replace("…", "").replace("...", "").split()).strip(" .:;,!?").lower()


# ------------------------------------------------------------------ phrases (free, from the step's own words)

def phrases(step: dict) -> list[Phrase]:
    """What to look for, in order: step.targets[].match (not regex-like, <= 40 chars), quoted UI names in the
    instructions, the first segment of a menu path ("Add > Mesh > Torus" -> "Add"), "Click <Name>", then Properties
    tabs, regions and Blender area words. A quoted or clicked name followed by tab / panel / properties / editor /
    area ("Open the Modifier tab") names a place, never a control: it becomes a tab or area phrase (place_phrases), so
    "Modifier" is never looked for inside the "Add Modifier" button; a place miyagi doesn't know ("the Shading tab",
    "the Transform panel") keeps its name as a whole-label control (ui_exact: the "Shading" workspace tab, the
    "Transform" panel header), never a word inside a longer label (named_place). A bare Properties tab word as a
    control ("Modifier", "Material", "Object", from a target's match, quotes or "Click ...") is that tab when the text
    names the tab, else whole-label only (ui_phrase). A name (also a target's match) that IS an area or region ("Click
    the Viewport", "Open the Sidebar") is only that area / region phrase, never a control's words found inside "Levels
    Viewport" / "Toggle Sidebar". Object names are matched by the bridge itself (_object_in)."""
    out: list[Phrase] = []
    seen: set[str] = set()
    text = "\n".join(str(step.get(k) or "") for k in ("instructions", "title"))

    def add(name: str, kind: str = "ui") -> None:
        t = " ".join(str(name or "").split()).strip(" .:;,!?")
        if not t or len(t) > MAX_PHRASE_CHARS or len(t.split()) > 5 or (kind in UI_KINDS and _KEYISH.match(t)):
            return
        key = f"{kind}:{t.lower()}"
        if key not in seen:
            seen.add(key)
            out.append(Phrase(t, kind))

    def add_ui(name: str) -> None:
        p = ui_phrase(name, text)
        add(p.text, p.kind)

    def add_name(name: str, after: str) -> None:
        noun = _PLACE_NOUN.match(after)
        placed = named_place(f"{name} {noun.group(1)}" if noun else name)
        if placed is None:
            add_ui(name)
            return
        for p in placed:
            add(p.text, p.kind)

    for tg in step.get("targets") or []:
        m = tg.get("match") if isinstance(tg, dict) else None
        if isinstance(m, str) and m.strip() and not _REGEXY.search(m):
            whole = " ".join(m.split()).strip(" .:;,!?")
            if (region := region_type(whole)) is not None:
                add(region, "region")
            elif not _PLACE.match(whole) and (area := _area_type(whole)) is not None:
                add(area, "area")
            else:
                add_ui(m)
    for m in _QUOTED.finditer(text):
        add_name(next(g for g in m.groups() if g), text[m.end():])
    # a menu path's head is a menu ("Object > Apply"), never a Properties tab: a word run inside a header row block
    # ("View Select Add Object") is still that menu
    for m in _MENU_PATH.finditer(text):
        add(m.group(1))
    for m in _CLICK.finditer(text):
        add_name(m.group(1), text[m.end():])
    for tab in tab_contexts(text):
        add(tab, "tab")
    for region in region_types(text):
        add(region, "region")
    for area in area_types(text):
        add(area, "area")
    return out


def place_phrases(name: str) -> list[Phrase] | None:
    """A name that IS a region or area ("Sidebar", "N panel", "Toolbar", "viewport header", "Viewport", "3D Viewport",
    "Outliner") is that place alone, never a control's words ("Viewport" would be found inside "Levels Viewport",
    "Sidebar" inside "Toggle Sidebar"). A name that ends in tab / panel / properties / editor / area is a place: its
    Properties tab ("Modifier tab", "Material properties" -> tab MODIFIER / MATERIAL) and / or area ("Properties
    editor", "Outliner area"); [] when it names no place miyagi knows ("Transform panel"). None: not a place name (no
    such ending), a control's words."""
    whole = " ".join(str(name or "").split()).strip(" .:;,!?")
    if (region := region_type(whole)) is not None:
        return [Phrase(region, "region")]
    m = _PLACE.match(whole)
    if m is None:
        area = _area_type(whole)
        return [Phrase(area, "area")] if area else None
    base, noun = m.group(1).strip(), m.group(2).lower()
    out: list[Phrase] = []
    tab = TAB_NAMES.get(norm(base))
    if tab and noun in ("tab", "properties", "property") or (tab == "MODIFIER" and noun == "panel"):
        out.append(Phrase(tab, "tab"))
    area = _area_type(f"{base} {noun}") or _area_type(base)
    if area:
        out.append(Phrase(area, "area"))
    return out


def named_place(name: str) -> list[Phrase] | None:
    """place_phrases(name), except that a place miyagi doesn't know ("Shading tab", "Layout tab", "UV Editing tab",
    "Transform panel") keeps its name as a whole-label control: [ui_exact "Shading"], found only as an exact AX label
    or a whole OCR block (the workspace tab, the panel header), never inside a longer label ("Shading Nodes"). A bare
    Properties tab word there ("Data panel", "Object panel"): nothing. None: not a place name."""
    placed = place_phrases(name)
    if placed != []:
        return placed
    m = _PLACE.match(" ".join(str(name or "").split()).strip(" .:;,!?"))
    base = m.group(1).strip() if m else ""
    if not base or norm(base) in TAB_NAMES or norm(base) in _NOT_A_NAME:
        return []
    return [Phrase(base, "ui_exact")]


def ui_phrase(name: str, text: str = "") -> Phrase:
    """A control's words as a phrase. A bare Properties tab word ("Modifier", "Material", "Object", "World": a
    TAB_NAMES key) is never matched inside a longer label (the "Modifier" in "Add Modifier"): it is that tab when
    `text` names it ("Open the Modifier tab."), else a whole-label control (ui_exact)."""
    tab = TAB_NAMES.get(norm(name))
    if tab is None:
        return Phrase(name, "ui")
    if tab in tab_contexts(text):
        return Phrase(tab, "tab")
    return Phrase(name, "ui_exact")


def _named_as_ui(text: str, start: int) -> bool:
    """The word before `start` makes it part of a capitalized UI name ("Levels Viewport", "Toggle Sidebar"), or a menu
    path leads to it ("View > Sidebar"): not the place itself."""
    before = text[:start]
    if _MENU_BEFORE.search(before):
        return True
    pw = _PREV_WORD.search(before)
    return bool(pw and pw.group(1)[0].isupper() and pw.group(1).lower() not in _NOT_A_NAME
                and not _SENTENCE_START.search(before[:pw.start()]))


def tab_contexts(text: str) -> list[str]:
    """The Properties tabs the text names: "<tab name> properties / tab" ("Go to the Material properties", "the
    Object Data tab"), "modifier panel", "the wrench". Skipped inside a capitalized UI name."""
    text = str(text or "")
    out: list[str] = []
    for m in _TAB_RX.finditer(text):
        if _named_as_ui(text, m.start()):
            continue
        word = next(g for g in m.groups() if g)
        tab = TAB_NAMES.get(norm(word))
        if tab and tab not in out:
            out.append(tab)
    return out


def region_types(text: str) -> list[str]:
    """The Blender regions the text names, as "AREA:REGION": the sidebar / N panel (VIEW_3D:UI), the toolbar /
    T panel (VIEW_3D:TOOLS), "<editor> header" / "header of the <editor>" (that editor's HEADER). A bare "header" is
    never one (a modifier panel has a header too); a menu item ("View > Sidebar") neither."""
    text = str(text or "")
    out: list[str] = []
    for rx, region in REGION_WORDS:
        for m in rx.finditer(text):
            if _named_as_ui(text, m.start()) or _NEXT_CAP.match(text[m.end():]):
                continue
            if region not in out:
                out.append(region)
            break
    for m in _HEADER.finditer(text):
        area = _area_type(next(g for g in m.groups() if g))
        if area and f"{area}:HEADER" not in out:
            out.append(f"{area}:HEADER")
    return out


def region_type(name: str) -> str | None:
    """The region a name IS, as a whole ("Sidebar", "N panel", "toolbar", "T-panel", "the 3D Viewport header" minus
    the article): "VIEW_3D:UI" / "VIEW_3D:TOOLS" / "<AREA>:HEADER"; None for a name that only contains one ("Toggle
    Sidebar", "Sidebar Tab")."""
    p = " ".join(str(name or "").split()).strip(" .:;,!?")
    for rx, region in REGION_WORDS:
        if rx.fullmatch(p):
            return region
    m = _HEADER.fullmatch(p)
    if m is not None and (area := _area_type(next(g for g in m.groups() if g))):
        return f"{area}:HEADER"
    return None


def area_types(text: str) -> list[str]:
    """The Blender area types the text names AS AN AREA. An area word is skipped when it is part of a capitalized UI
    name (a capitalized word before it that doesn't start the sentence, "the Levels Viewport field"; or a capitalized
    word after it, "Viewport Display") or names a control's value ("viewport field / value / setting / checkbox /
    slider"). A wrong whole-editor circle is worse than none."""
    text = str(text or "")
    out: list[str] = []
    for rx, area in AREA_WORDS:
        for m in rx.finditer(text):
            after = text[m.end():]
            if _FIELD_NOUN.match(after):
                continue
            if _NEXT_CAP.match(after) and not _AREA_NOUN.match(after):
                continue
            before = text[:m.start()]
            pw = _PREV_WORD.search(before)
            if (pw and pw.group(1)[0].isupper() and pw.group(1).lower() not in _NOT_A_NAME
                    and not _SENTENCE_START.search(before[:pw.start()])):
                continue
            if area not in out:
                out.append(area)
            break
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


def on_primary(rect: Rect | None, screen: Rect | None) -> bool:
    """The rect's centre is on the primary display. Marks carry no displayId, so a rect on another display (x past
    the primary's width, a negative y above it) would be drawn on the primary one. Unknown display: False."""
    if rect is None or screen is None or screen.w <= 0 or screen.h <= 0:
        return False
    return screen.x <= rect.cx <= screen.x2 and screen.y <= rect.cy <= screen.y2


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
    try:  # import_module reads sys.modules first (a test's fake), not the package attribute an earlier import set
        blender_ext = importlib.import_module("server.workspace.blender_ext")
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
        with contextlib.suppress(Exception):
            ui.close()
        return None
    return ui if isinstance(ui, dict) else None


def _sane_scale(k: float) -> bool:
    """k (screen points per Blender pixel) is a macOS backing scale: within 3% of 0.5 (Retina) or 1.0."""
    return any(abs(k - s) <= SCALE_TOLERANCE * s for s in BACKING_SCALES)


def bridge_shape(ui: dict | None, window: Rect | None = None) -> dict | None:
    """The bridge's reply in screen points:
        {"window": Rect | None, "areas": [(type, ui_type, Rect)], "regions": [(area type, region type, Rect)],
         "objects": [(name, Rect)], "tabs": Rect | None, "context": str | None, "contexts": [str],
         "mode": str | None, "active": str | None}
    Two shapes:
      - points: {"window": rect, "areas": [{"type", "rect"}], "objects": [{"name", "rect"}], "tabs"?: rect, ...}
      - Blender's raw /ui: {"origin": "bottom-left", "mode", "active", "windows": [{x, y, width, height, areas: [{type,
        ui_type, x, y, width, height, regions: [...], objects?: [...], properties?: {context, tabs, contexts?}}]}]}
        in Blender pixels, area / region / object x / y relative to its window: placed on the app's window on screen
        (`window`, from the frame: the front-most one; None: no rects, never a guess from Blender's own x / y),
        bottom-aligned (the screen rect includes the title bar, Blender's doesn't). The Blender window is the one whose
        shape fits the screen window (_fit_window, also for a single window): k = screen width / Blender width must
        be a backing scale (within 3% of 0.5 or 1.0) and the implied title bar ~28 pt (or ~0, full screen); none
        fits or two fit alike: None (never rects on the wrong window). Regions under MIN_SIDE_PT (hidden sidebars)
        are dropped; objects come from the largest 3D Viewport, the tab column from the largest Properties editor.
    None for anything else."""
    if not isinstance(ui, dict):
        return None
    try:
        if isinstance(ui.get("windows"), list):
            return _raw_shape(ui, window)
        if "areas" in ui or "objects" in ui or "window" in ui:
            win = _rect(ui.get("window")) or window
            areas = [(str(a.get("type") or ""), str(a.get("ui_type") or ""), r) for a in ui.get("areas") or []
                     if isinstance(a, dict) and (r := _rect(a)) is not None]
            objs = [(str(o.get("name") or ""), r) for o in ui.get("objects") or []
                    if isinstance(o, dict) and o.get("name") and (r := _rect(o)) is not None]
            regions = [(str(g.get("area") or ""), str(g.get("type") or ""), r) for g in ui.get("regions") or []
                       if isinstance(g, dict) and (r := _rect(g)) is not None]
            return {"window": win, "areas": areas, "regions": regions, "objects": objs, "tabs": _rect(ui.get("tabs")),
                    "context": _str(ui.get("context")), "contexts": _strs(ui.get("contexts")),
                    "mode": _str(ui.get("mode")), "active": _str(ui.get("active"))}
    except (TypeError, ValueError, ZeroDivisionError, AttributeError):
        return None
    return None


def _str(v) -> str | None:
    return v if isinstance(v, str) and v else None


def _strs(v) -> list[str]:
    return [x for x in v if isinstance(x, str) and x] if isinstance(v, list) else []


def _raw_shape(ui: dict, window: Rect | None) -> dict | None:
    wins = [w for w in ui["windows"] if isinstance(w, dict) and _rect(w) is not None]
    if not wins or window is None:
        return None
    bw = _fit_window(wins, window)
    if bw is None:
        return None
    braw = _rect(bw)
    k = window.w / braw.w
    bottom = window.y + window.h
    bottom_left = str(ui.get("origin") or "bottom-left") == "bottom-left"

    def place(r: Rect) -> Rect:
        y = bottom - (r.y + r.h) * k if bottom_left else bottom - braw.h * k + r.y * k
        return Rect(window.x + r.x * k, y, r.w * k, r.h * k)

    areas, regions = [], []
    view3d: tuple[float, dict] | None = None
    props: tuple[float, dict, list] | None = None
    for a in bw.get("areas") or []:
        r = _rect(a) if isinstance(a, dict) else None
        if r is None:
            continue
        atype = str(a.get("type") or "")
        areas.append((atype, str(a.get("ui_type") or ""), place(r)))
        mine = []
        for g in a.get("regions") or []:
            gr = _rect(g) if isinstance(g, dict) else None
            if gr is None:
                continue
            sr = place(gr)
            if sr.w >= MIN_SIDE_PT and sr.h >= MIN_SIDE_PT:  # a hidden sidebar / toolbar is 1 px wide
                regions.append((atype, str(g.get("type") or ""), sr))
                mine.append((str(g.get("type") or ""), sr))
        size = r.w * r.h
        if atype == "VIEW_3D" and isinstance(a.get("objects"), list) and (view3d is None or size > view3d[0]):
            view3d = (size, a)
        if atype == "PROPERTIES" and (props is None or size > props[0]):
            props = (size, a, mine)
    objects = []
    for o in (view3d[1]["objects"] if view3d else []):
        r = _rect(o) if isinstance(o, dict) else None
        if r is not None and isinstance(o.get("name"), str) and o["name"]:
            objects.append((o["name"], place(r)))
    tabs, context, contexts = None, None, []
    if props is not None:
        p = props[1].get("properties") if isinstance(props[1].get("properties"), dict) else {}
        tr = _rect(p.get("tabs"))
        tabs = place(tr) if tr is not None else next((r for t, r in props[2] if t == "NAVIGATION_BAR"), None)
        if tabs is not None and (tabs.w < MIN_SIDE_PT or tabs.h < MIN_SIDE_PT):
            tabs = None
        context, contexts = _str(p.get("context")), _strs(p.get("contexts"))
    return {"window": window, "areas": areas, "regions": regions, "objects": objects, "tabs": tabs,
            "context": context, "contexts": contexts, "mode": _str(ui.get("mode")), "active": _str(ui.get("active"))}


def _fit_window(wins: list[dict], window: Rect) -> dict | None:
    """The Blender window (/ui pixels) that is the screen window: k = screen width / its width is a backing scale
    (_sane_scale), and scaled by k its height plus a title bar of ~28 pt (or ~0: full screen) is the screen window's
    height. None: none fits, or the best fits no better than the next by WINDOW_MATCH_MARGIN_PT (two windows of one
    shape: ambiguous)."""
    scored: list[tuple[float, dict]] = []
    for w in wins:
        r = _rect(w)
        if r is None:
            continue
        k = window.w / r.w
        if not _sane_scale(k):
            continue
        title = window.h - r.h * k  # the title bar this window would imply
        if abs(title - TITLE_BAR_PT) <= TITLE_BAR_SLACK_PT:
            scored.append((abs(title - TITLE_BAR_PT), w))
        elif abs(title) <= FULLSCREEN_SLACK_PT:
            scored.append((abs(title), w))
    if not scored:
        log.info("on-screen coach: no Blender window fits the one in front (scale / title bar): no bridge rects")
        return None
    scored.sort(key=lambda e: e[0])
    if len(scored) > 1 and scored[1][0] - scored[0][0] < WINDOW_MATCH_MARGIN_PT:
        log.info("on-screen coach: %d Blender windows fit the one in front: no bridge rects", len(scored))
        return None
    return scored[0][1]


def _area_type(phrase: str) -> str | None:
    """The area type a phrase IS (an area phrase "VIEW_3D", or the whole phrase an area name: "Outliner", "3D
    Viewport", "Modifier tab"); never one it merely contains ("Add Modifier", "Viewport Display")."""
    p = phrase.strip()
    if p in _AREA_LABEL:
        return p
    for rx, t in AREA_WORDS:
        if rx.fullmatch(p):
            return t
    return None


def _bridge_area(want: str, ui: dict) -> Rect | None:
    hits = [r for t, ut, r in ui.get("areas") or [] if t == want or (want == "NODE_EDITOR" and "shader" in ut.lower())]
    return max(hits, key=lambda r: r.w * r.h) if hits else None


def _bridge_region(want: str, ui: dict) -> Rect | None:
    """The region "AREA:REGION" of the largest area of that type that has one (regions are already >= 6 pt)."""
    area, _, region = want.partition(":")
    hits = [r for a, t, r in ui.get("regions") or [] if a == area and t == region]
    return max(hits, key=lambda r: r.w * r.h) if hits else None


def _bridge_object(phrase: str, ui: dict) -> Rect | None:
    n = norm(phrase)
    objs = [r for name, r in ui.get("objects") or [] if norm(name) == n]
    return objs[0] if len(objs) == 1 else None


def bridge_rect(phrase: str, ui: dict | None) -> tuple[Rect, bool] | None:
    """(rect, is_area) for a phrase in a bridge_shape(): a phrase that IS an area name -> the largest area of that
    type; an object name (case aside, unique) -> that object. None when it names neither."""
    if not ui:
        return None
    want = _area_type(phrase)
    if want and (r := _bridge_area(want, ui)) is not None:
        return r, True
    r = _bridge_object(phrase, ui)
    return (r, False) if r is not None else None


# a verb that acts on the object named right after it ("Select the Donut", "click on the cube", "Scale the Torus")
_ACTS = re.compile(r"\b(?:select|click|pick|choose|tap|move|grab|drag|scale|resize|rotate|spin|delete|remove|"
                   r"duplicate|copy|hide|unhide|rename|join|parent|frame|focus|isolate|shade|smooth|extrude|"
                   r"subdivide|edit|snap|place|position|apply\s+\w+\s+to)"
                   r"(?:[ \t]+(?:on|at|to|the|your|this|that|both|whole|it))*[ \t]+$", re.IGNORECASE)


@dataclass(frozen=True)
class ObjectHit:
    name: str
    rect: Rect
    outliner: bool   # "the Donut in the Outliner": look for its row there first


def _object_in(step: dict, ui: dict, *, acting: bool) -> ObjectHit | None:
    """The bridge object the step names: whole word, names of MIN_OBJECT_NAME+ chars unique among the objects (two
    that differ only in case: neither); never one it adds ("add a Donut", "Add a second Cube", "Add the Donut") and
    never a name that heads a UI place or another name ("the Light properties", "Camera view", "Cube Mesh"). acting:
    only one the step acts on ("Select the Donut", case aside: "select the donut"); else one a verb acts on, or one it
    names exactly as spelled right after the / your / this / that, followed by nothing or a function word ("the Donut is"; never "the
    Light power", "the viewport area" or "the field is empty" for objects Area / Empty). The longest name first
    ("Cube.001" before "Cube")."""
    text = "\n".join(str(step.get(k) or "") for k in ("instructions", "title"))  # a line apart: no name runs on
    counts: dict[str, int] = {}
    for name, _ in ui.get("objects") or []:
        counts[name.casefold()] = counts.get(name.casefold(), 0) + 1
    for name, r in sorted(ui.get("objects") or [], key=lambda o: -len(o[0])):
        if len(name) < MIN_OBJECT_NAME or counts[name.casefold()] != 1:
            continue
        for m in re.finditer(rf"(?<![\w.]){re.escape(name)}(?![\w]|\.\w)", text, re.IGNORECASE):
            before = text[:m.start()]
            if _ADD_NEW.search(before) or (acting and not _ACTS.search(before)):
                continue
            if not acting and not _ACTS.search(before) and (m.group(0) != name or not _DETERMINER.search(before)):
                continue
            after = text[m.end():]
            if _NAME_AS_HEAD.match(after):
                continue
            nxt = re.match(r"(?:['’]s)?[ \t]+([A-Za-z]+)", after)  # "the Donut's icing": an attribute too
            if not acting and nxt and nxt.group(1).lower() not in _AFTER_NAMED:
                continue
            outliner = bool(re.match(r"\s+(?:in|from)\s+the\s+outliner\b", after, re.IGNORECASE))
            return ObjectHit(name, r, outliner)
    return None


def _object_asked(plist: list[Phrase], ui: dict) -> ObjectHit | None:
    """A where ask's own object ("where is the Cube?" -> ui phrase "Cube"): a ui phrase that IS one object's name
    (case aside, MIN_OBJECT_NAME+ chars, unique among the objects). Never an object the step itself names."""
    for ph in plist:
        if ph.kind not in UI_KINDS or len(ph.text) < MIN_OBJECT_NAME:
            continue
        want = ph.text.casefold()
        hits = [(name, r) for name, r in ui.get("objects") or [] if name.casefold() == want]
        if len(hits) == 1:
            return ObjectHit(hits[0][0], hits[0][1], False)
    return None


def _has_bridge(app: dict) -> bool:
    return str(app.get("tool") or "").lower() == "blender" or norm(app.get("using")) == "blender"


_AREA_LABEL = {"VIEW_3D": "3D Viewport", "PROPERTIES": "Properties", "OUTLINER": "Outliner", "TIMELINE": "Timeline",
               "NODE_EDITOR": "Shader Editor"}
_REGION_LABEL = {"VIEW_3D:UI": "Sidebar", "VIEW_3D:TOOLS": "Toolbar"}


# ------------------------------------------------------------------ Properties tabs (estimate, not yet trusted)

# Blender's tab column, top-down, with a gap between groups (ED_buttons_tabs_list); the bridge's `contexts` gives the
# real order of the tabs shown now, this only says where the gaps go.
TAB_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"TOOL"}),
    frozenset({"RENDER", "OUTPUT", "VIEW_LAYER", "SCENE", "COMPOSITOR", "WORLD", "COLLECTION"}),
    frozenset({"OBJECT", "MODIFIER", "SHADERFX", "PARTICLES", "PHYSICS", "CONSTRAINT", "DATA", "BONE",
               "BONE_CONSTRAINT", "MATERIAL"}),
    frozenset({"TEXTURE"}),
    frozenset({"STRIP", "STRIP_MODIFIER"}),
)
TAB_CELL = 1.0       # a tab button's height, in column widths (the buttons are square)
TAB_GAP = 0.5        # the gap between two groups, in column widths
TAB_TOP_PAD = 0.25   # the column's top padding, in column widths


def _group(ctx: str) -> int:
    return next((i for i, g in enumerate(TAB_GROUPS) if ctx in g), len(TAB_GROUPS))


def estimate_tab(tabs: Rect | None, contexts: list[str], want: str, *, cell: float = TAB_CELL, gap: float = TAB_GAP,
                 pad: float = TAB_TOP_PAD) -> Rect | None:
    """The rect of one tab in the tab column (screen points, top-left origin): the column `tabs`, the tabs shown now
    top-down (`contexts`), square buttons cell * width tall from pad * width below the top, gap * width between groups.
    None: no column, `want` not shown, or the estimate falls outside the column. Used only when TAB_LAYOUT_CONFIDENT."""
    if tabs is None or tabs.w <= 0 or want not in contexts:
        return None
    unit = tabs.w
    y = tabs.y + pad * unit
    prev = None
    for ctx in contexts:
        g = _group(ctx)
        if prev is not None and g != prev:
            y += gap * unit
        prev = g
        if ctx == want:
            r = Rect(tabs.x, y, tabs.w, cell * unit)
            return r if r.y2 <= tabs.y2 + 0.5 else None
        y += cell * unit
    return None


# ------------------------------------------------------------------ 2. Accessibility

class AxTree:
    """The real AX tree of the named app's focused window (server.screen.ax primitives, read-only). Tests pass a fake
    with the same four methods."""

    def __init__(self, names: list[str]):
        self.names = names

    def root(self):
        from AppKit import NSWorkspace

        from . import ax

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


def ocr_target(obs, phrase: str, window_app: str | list[str], *, window: Rect | None = None,
               whole: bool = False) -> Rect | None:
    """The rect of the phrase in the app's window on this frame: blocks equal to it (or a word run inside a block equal
    to it), or with a fuzzy ratio >= 92 for 4+ char phrases; confidence >= 0.5. Exactly one candidate, or a best that
    beats the second by >= 8; else None. whole (a ui_exact phrase): only a block equal to it, no word run, no fuzzy."""
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
        if whole:
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
    """1. a bridge object the step acts on, 2. AX, 3. OCR (ui phrases), 4. a Properties tab (the bridge's tab column),
    5. a bridge region or area, else None; every hit through gate() and on_primary(). A precise control always beats a
    whole editor: "click Add Modifier" circles the button (AX / OCR), never the Properties area. front: the app in
    front now ('' / None: unknown, then the frame's). bridge / ax_fn / ocr_fn: test seams (default: _bridge_ui, a
    zero-argument call for the raw /ui reply / ax_target / ocr_target). The bridge is asked once per call."""
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
    screen = _rect(getattr(obs, "screen", None)) if obs is not None else None
    plist = phrase_list if phrase_list is not None else phrases(step)
    ui = [p for p in plist if p.kind in UI_KINDS]
    tabs = [p for p in plist if p.kind == "tab"]

    def ok(r: Rect | None) -> Rect | None:  # no displayId on a mark: only a rect on the primary display
        if r is not None and not on_primary(r, screen):
            log.info("on-screen coach: %s is off the primary display (%s): no circle", r.rounded(), screen)
            return None
        return r

    def ocr(phrase: str, where: Rect, *, whole: bool = False) -> Rect | None:
        kw = {"whole": True} if whole else {}  # a ui_exact phrase: a whole block only, never a word inside one
        return ok(gate((ocr_fn or ocr_target)(obs, phrase, names, window=where, **kw), win, overlay))

    # one bridge round trip; none without the app's window on a fresh frame (nothing to place its rects on)
    shape = bridge_shape((bridge or _bridge_ui)(), win) if _has_bridge(app) and win is not None else None
    bwin = (shape or {}).get("window") or win

    def from_bridge(r: Rect | None, label: str, *, area: bool = False) -> Target | None:
        r = ok(gate(r, bwin, overlay, area=area))
        return Target(r, "bridge", label) if r is not None else None

    # 1. an object the step acts on (or names, when it names no control or tab); for a where ask (phrase_list), only
    # an object the ask itself names, never the step's ("Select the Cube" + "where is the Modifier tab?": the tab)
    hit = None
    if shape:
        hit = (_object_asked(plist, shape) if phrase_list is not None
               else _object_in(step, shape, acting=bool(ui or tabs)))
    if hit is not None:
        outliner = _bridge_area("OUTLINER", shape) if hit.outliner else None
        if outliner is not None and fresh and win is not None and (r := ocr(hit.name, outliner)) is not None:
            return Target(r, "ocr", hit.name)
        if (t := from_bridge(hit.rect, hit.name)) is not None:
            return t
    # 2. / 3. a control's words: AX, then OCR
    for ph in ui:
        got = (ax_fn or ax_target)(names, ph.text)
        if got is not None:
            r, awin = got
            if (r := ok(gate(r, awin or win, overlay))) is not None:
                return Target(r, "ax", ph.text)
    if fresh and win is not None:
        for ph in ui:
            if (r := ocr(ph.text, win, whole=ph.kind == "ui_exact")) is not None:
                return Target(r, "ocr", ph.text)
    if not shape:
        return None
    # 4. a Properties tab: one tab only once its layout is trusted, else the whole tab column
    for ph in tabs:
        label = TAB_LABEL.get(ph.text, "Properties tabs")
        if TAB_LAYOUT_CONFIDENT:
            one = estimate_tab(shape.get("tabs"), shape.get("contexts") or [], ph.text)
            if one is not None and (t := from_bridge(one, label)) is not None:
                return t
        if (t := from_bridge(shape.get("tabs"), label)) is not None:
            return t
    # 5. a region, then an area (the chain's last resort)
    for ph in plist:
        if ph.kind == "region" and (r := _bridge_region(ph.text, shape)) is not None:
            area, _, region = ph.text.partition(":")
            label = _REGION_LABEL.get(ph.text) or f"{_AREA_LABEL.get(area, area)} {region.lower()}"
            if (t := from_bridge(r, label, area=True)) is not None:
                return t
    for ph in plist:
        if ph.kind not in ("area", "ui"):
            continue
        want = _area_type(ph.text)
        r = _bridge_area(want, shape) if want else None
        if r is not None and (t := from_bridge(r, _AREA_LABEL.get(want, ph.text), area=True)) is not None:
            return t
    return None

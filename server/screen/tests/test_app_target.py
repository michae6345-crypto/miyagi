"""server.screen.app_target: the on-screen coach's free resolver chain (bridge -> AX -> OCR -> None) and its confidence
gate. Offline: a fake blender_ext module in sys.modules (or none), a fake AX tree, fake ScreenObservations."""
from __future__ import annotations

import sys
import time
import types
from pathlib import Path

import pytest

from server.screen import app_target as T
from server.screen.types import Block, Rect, ScreenObservation, Window

BLENDER = {"tool": "blender", "label": "Blender"}
WIN = Rect(100, 50, 1000, 700)
MOD = "server.workspace.blender_ext"


def step(instr: str = "Click Add, then choose Mesh > Torus.", **kw) -> dict:
    return {"id": "s1", "title": "Add a torus", "instructions": instr, **kw}


PRIMARY = Rect(0, 0, 1440, 900)  # the primary display, in points


def obs(blocks=(), *, app: str = "Blender", t: float | None = None, windows=None,
        screen: Rect = PRIMARY) -> ScreenObservation:
    return ScreenObservation(t=time.time() if t is None else t, app=app,
                             windows=windows if windows is not None else [Window("Blender", "donut.blend", WIN)],
                             blocks=list(blocks), screen=screen)


def blk(text: str, x: float, y: float, w: float = 40, h: float = 16, conf: float = 0.9, app: str = "Blender") -> Block:
    return Block(text, Rect(x, y, w, h), conf, app=app, window="donut.blend")


@pytest.fixture
def no_bridge(monkeypatch):
    monkeypatch.setitem(sys.modules, MOD, None)  # import -> ImportError


def fake_bridge(monkeypatch, ui_rects) -> None:
    mod = types.ModuleType(MOD)
    if ui_rects is not None:
        mod.ui_rects = ui_rects
    monkeypatch.setitem(sys.modules, MOD, mod)


class Recorder:
    def __init__(self, result=None):
        self.calls: list = []
        self.result = result

    def __call__(self, *a, **kw):
        self.calls.append((a, kw))
        return self.result


# ------------------------------------------------------------------ phrases

def test_phrases_from_targets_quotes_menu_paths_and_area_words():
    st = step('In the Properties editor, click "Add Modifier" then Generate > Subdivision Surface.',
              targets=[{"match": "Modifier Properties"}, {"match": r"Add\s+Modifier"}, {"match": "x" * 41}])
    got = [(p.text, p.kind) for p in T.phrases(st)]
    assert got[0] == ("Modifier Properties", "ui")  # targets first; the regex-like and the too-long one are left out
    assert ("Add Modifier", "ui") in got and ("Generate", "ui") in got
    assert ("PROPERTIES", "area") in got
    assert not any(t == r"Add\s+Modifier" or t.startswith("xxx") for t, _ in got)


def test_phrases_never_take_a_key_for_a_control():
    assert [p.text for p in T.phrases(step("Press G then Z to move it up."))] == []
    assert [p.text for p in T.phrases(step("Add > Mesh > Torus"))][:1] == ["Add"]


# ------------------------------------------------------------------ 1. bridge

def test_bridge_hit_is_via_bridge_and_ax_ocr_are_not_called(monkeypatch):
    fake_bridge(monkeypatch, lambda: {"window": {"x": 100, "y": 50, "w": 1000, "h": 700},
                                      "areas": [{"type": "PROPERTIES", "rect": {"x": 850, "y": 300, "w": 240, "h": 400}}],
                                      "objects": [{"name": "Torus", "x": 500, "y": 400, "w": 80, "h": 60}]})
    ax, ocr = Recorder(), Recorder()
    t = T.resolve(step("Select the Torus in the viewport."), BLENDER, obs(), [], ax_fn=ax, ocr_fn=ocr)
    assert t.via == "bridge" and t.label == "Torus" and t.rect == Rect(500, 400, 80, 60)
    assert ax.calls == [] and ocr.calls == []  # a bridge object: AX / OCR never asked
    # an area is the last resort: reached only after AX and OCR found no control
    t = T.resolve(step("In the Properties editor, click Add Modifier."), BLENDER, obs(), [], ax_fn=ax, ocr_fn=ocr)
    assert t is not None and t.via == "bridge" and t.rect == Rect(850, 300, 240, 400) and t.label == "Properties"
    assert ax.calls and ocr.calls
    # "the Modifier tab" is a place, not a control: no AX / OCR for it; no tab column known -> the Properties area
    ax2, ocr2 = Recorder(), Recorder()
    t = T.resolve(step("In the Properties editor, open the Modifier tab."), BLENDER, obs(), [], ax_fn=ax2, ocr_fn=ocr2)
    assert t is not None and t.via == "bridge" and t.label == "Properties" and ax2.calls == [] == ocr2.calls
    t = T.resolve(step("Add a Torus with Shift+A."), BLENDER, obs(), [], ax_fn=ax, ocr_fn=Recorder())
    assert t is None or t.label != "Torus"  # an object the step ADDS is never the one circled


def test_bridge_raw_blender_pixels_are_placed_on_the_window_bottom_aligned(monkeypatch):
    # Blender's /ui: retina pixels (2 px per pt), origin bottom-left, area x / y relative to its window. The screen
    # window (1000 x 700 pt) has a 50 pt title bar Blender's 2000 x 1300 px window doesn't count.
    fake_bridge(monkeypatch, lambda: {"ok": True, "origin": "bottom-left", "pixel_size": 2.0, "windows": [
        {"x": 0, "y": 0, "width": 2000, "height": 1300, "areas": [
            {"type": "VIEW_3D", "ui_type": "VIEW_3D", "x": 0, "y": 200, "width": 1500, "height": 1100},
            {"type": "OUTLINER", "ui_type": "OUTLINER", "x": 1500, "y": 900, "width": 500, "height": 400},
            {"type": "NODE_EDITOR", "ui_type": "ShaderNodeTree", "x": 0, "y": 0, "width": 1500, "height": 200}]}]})
    t = T.resolve(step("Rename it in the Outliner."), BLENDER, obs(), [], ax_fn=Recorder(), ocr_fn=Recorder())
    assert t.via == "bridge" and t.rect == Rect(850, 100, 250, 200)
    t = T.resolve(step("Look around the 3D viewport."), BLENDER, obs(), [], ax_fn=Recorder(), ocr_fn=Recorder())
    assert t.rect == Rect(100, 100, 750, 550)  # a bridge area may be larger than 40% of the window
    t = T.resolve(step("Open the shader editor."), BLENDER, obs(), [], ax_fn=Recorder(), ocr_fn=Recorder())
    assert t.rect == Rect(100, 650, 750, 100)


@pytest.mark.parametrize("ui_rects", [None, "missing", "raises", "bad"])
def test_bridge_absent_or_broken_falls_through_to_ax(monkeypatch, ui_rects):
    if ui_rects is None:
        monkeypatch.setitem(sys.modules, MOD, None)
    elif ui_rects == "missing":
        fake_bridge(monkeypatch, None)
    elif ui_rects == "raises":
        fake_bridge(monkeypatch, lambda: (_ for _ in ()).throw(OSError("bridge down")))
    else:
        fake_bridge(monkeypatch, lambda: ["not", "a", "dict"])
    ax = Recorder(((Rect(300, 60, 40, 20)), WIN))
    t = T.resolve(step("In the Properties editor, click Add."), BLENDER, obs(), [], ax_fn=ax, ocr_fn=Recorder())
    assert ax.calls and t is not None and t.via == "ax" and t.label == "Add"


def test_bridge_returning_none_falls_through(monkeypatch):
    fake_bridge(monkeypatch, lambda: None)
    ax = Recorder((Rect(300, 60, 40, 20), WIN))
    assert T.resolve(step(), BLENDER, obs(), [], ax_fn=ax).via == "ax"


def test_the_bridge_is_imported_only_inside_a_function():
    src = Path(T.__file__).read_text(encoding="utf-8").splitlines()
    lines = [ln for ln in src if "blender_ext" in ln
             and (ln.lstrip().startswith(("from ", "import ")) or "import_module(" in ln)]
    assert lines and all(ln.startswith("        ") for ln in lines)  # inside a function body, never at module level


# ------------------------------------------------------------------ 2. AX

class Node:
    def __init__(self, label: str = "", rect: Rect | None = None, kids=()):
        self.label, self.r, self.kids = label, rect, list(kids)


class FakeTree:
    def __init__(self, root: Node, win: Rect = WIN):
        self._root, self._win = root, win

    def root(self):
        return self._root, self._win

    def children(self, el):
        return el.kids

    def labels(self, el):
        return [el.label] if el.label else []

    def rect(self, el):
        return el.r


def test_ax_needs_exactly_one_equal_label():
    one = FakeTree(Node(kids=[Node("  add ", Rect(300, 60, 40, 20)), Node("Add Modifier", Rect(900, 300, 120, 20))]))
    assert T.ax_target("Blender", "Add", tree=one) == (Rect(300, 60, 40, 20), WIN)
    two = FakeTree(Node(kids=[Node("Add", Rect(300, 60, 40, 20)), Node("Add", Rect(600, 60, 40, 20))]))
    assert T.ax_target("Blender", "Add", tree=two) is None
    nested = FakeTree(Node(kids=[Node("Add", Rect(300, 60, 40, 20), kids=[Node("Add", Rect(300, 60, 40, 20))])]))
    assert T.ax_target("Blender", "Add", tree=nested) is not None  # the same element twice (button + its text)
    assert T.ax_target("Blender", "Add", tree=FakeTree(Node(kids=[Node("Object")]))) is None


def test_ax_walk_is_bounded():
    chain = Node()
    cur = chain
    for _ in range(3000):
        nxt = Node()
        cur.kids = [nxt]
        cur = nxt
    cur.label, cur.r = "Add", Rect(300, 60, 40, 20)
    assert T.ax_target("Blender", "Add", tree=FakeTree(chain)) is None


@pytest.mark.parametrize("labels", [[], ["Add", "Add"]])
def test_ax_zero_or_two_hits_fall_through_to_ocr(no_bridge, labels):
    kids = [Node(lb, Rect(300 + 100 * i, 60, 40, 20)) for i, lb in enumerate(labels)]
    tree = FakeTree(Node(kids=kids))
    o = obs([blk("Add", 400, 70)])
    t = T.resolve(step(), BLENDER, o, [], ax_fn=lambda names, p: T.ax_target(names, p, tree=tree))
    assert t is not None and t.via == "ocr" and t.rect == Rect(400, 70, 40, 16)


def test_ax_error_is_no_hit():
    class Broken(FakeTree):
        def root(self):
            raise RuntimeError("AX gone")

    assert T.ax_target("Blender", "Add", tree=Broken(Node())) is None


# ------------------------------------------------------------------ 3. OCR

def test_ocr_exact_fuzzy_and_word_runs():
    o = obs([blk("Add Modifier", 900, 300, 120), blk("View Select Add Object", 200, 60, 220)])
    assert T.ocr_target(o, "Add Modifer", "Blender") == Rect(900, 300, 120, 16)  # ratio >= 92
    r = T.ocr_target(o, "Object", "Blender")
    assert r is not None and 200 + 220 * 0.7 < r.cx < 420 and r.y == 60  # placed inside its header row


@pytest.mark.parametrize("case", ["ambiguous", "low_conf", "outside", "overlay", "stale", "front", "tiny", "huge"])
def test_ocr_refusals_give_none(no_bridge, case):
    blocks = [blk("Torus", 400, 300)]
    overlay, front, t = [], None, None
    if case == "ambiguous":
        blocks.append(blk("Torus", 600, 300))
    elif case == "low_conf":
        blocks = [blk("Torus", 400, 300, conf=0.3)]
    elif case == "outside":
        blocks = [blk("Torus", 1200, 300)]
    elif case == "overlay":
        overlay = [Rect(380, 280, 300, 100)]
    elif case == "stale":
        t = time.time() - 5
    elif case == "front":
        front = "Safari"
    elif case == "tiny":
        blocks = [blk("Torus", 400, 300, w=4, h=4)]
    elif case == "huge":
        blocks = [blk("Torus", 120, 60, w=900, h=600)]
    st = step("Click Torus.")
    got = T.resolve(st, BLENDER, obs(blocks, t=t), overlay, front=front, ax_fn=Recorder())
    assert got is None
    assert T.resolve(st, BLENDER, obs([blk("Torus", 400, 300)]), [], ax_fn=Recorder()).via == "ocr"  # control


def test_ocr_best_beats_second_by_eight():
    o = obs([blk("Subdivision Surface", 400, 300, 160), blk("Subdivision Surf", 400, 400, 160)])
    assert T.ocr_target(o, "Subdivision Surface", "Blender") == Rect(400, 300, 160, 16)  # the other is under 92
    o = obs([blk("Subdivision Surface", 400, 300, 160), blk("Subdivision Surfaces", 400, 400, 160)])
    assert T.ocr_target(o, "Subdivision Surface", "Blender") is None  # 100 vs ~97: too close to call


def test_other_apps_text_and_our_overlay_in_front():
    o = obs([blk("Torus", 400, 300, app="Safari")])
    assert T.ocr_target(o, "Torus", "Blender") is None
    got = T.resolve(step("Click Torus."), BLENDER, obs([blk("Torus", 400, 300)]), [], front="miyagi", ax_fn=Recorder())
    assert got is not None  # miyagi's own overlay in front is not "another app"


def test_using_app_windows_are_matched():
    o = obs([Block("Pad", Rect(400, 300, 40, 16), 0.9, app="FreeCAD")], app="FreeCAD",
            windows=[Window("FreeCAD", "car.FCStd", WIN)])
    t = T.resolve(step("Click Pad."), {"tool": "autocad", "label": "AutoCAD", "using": "FreeCAD"}, o, [],
                  ax_fn=Recorder())
    assert t is not None and t.via == "ocr"


def test_gate():
    assert T.gate(Rect(400, 300, 40, 20), None) is None
    assert T.gate(Rect(400, 300, 40, 20), WIN) == Rect(400, 300, 40, 20)
    assert T.gate(Rect(400, 300, 5, 20), WIN) is None
    assert T.gate(Rect(100, 50, 900, 600), WIN) is None
    assert T.gate(Rect(100, 50, 900, 600), WIN, area=True) is not None
    assert T.gate(Rect(400, 300, 40, 20), WIN, [{"x": 390, "y": 290, "w": 100, "h": 100}]) is None


# ------------------------------------------------------------------ review round 1

@pytest.mark.parametrize("win,hit", [
    (Rect(1500, 100, 1000, 700), Rect(2000, 300, 40, 20)),   # a display to the right of a 1440-wide primary
    (Rect(100, -800, 1000, 700), Rect(400, -500, 40, 20)),   # a display above it
])
def test_a_window_on_another_display_is_never_circled(no_bridge, win, hit):
    # marks carry no displayId: a rect off the primary display would be drawn on the primary one
    o = obs([blk("Add", hit.x, hit.y)], windows=[Window("Blender", "donut.blend", win)])
    ax = Recorder((hit, win))
    assert T.resolve(step("Click Add."), BLENDER, o, [], ax_fn=ax) is None
    assert ax.calls  # AX found it; the display check refused it
    assert T.resolve(step("Click Add."), BLENDER, obs(), [], ax_fn=Recorder((Rect(300, 60, 40, 20), WIN))).via == "ax"


def test_an_unknown_primary_display_is_no_circle(no_bridge):
    o = obs([blk("Add", 400, 70)], screen=Rect(0, 0, 0, 0))
    assert T.resolve(step("Click Add."), BLENDER, o, [], ax_fn=Recorder((Rect(300, 60, 40, 20), WIN))) is None


RAW_MAIN = {"x": 0, "y": 0, "width": 2000, "height": 1300, "areas": [
    {"type": "VIEW_3D", "ui_type": "VIEW_3D", "x": 0, "y": 200, "width": 1500, "height": 1100},
    {"type": "OUTLINER", "ui_type": "OUTLINER", "x": 1500, "y": 900, "width": 500, "height": 400}]}
RAW_PREFS = {"x": 0, "y": 0, "width": 1400, "height": 1100, "areas": [
    {"type": "PREFERENCES", "ui_type": "PREFERENCES", "x": 0, "y": 0, "width": 1400, "height": 1100}]}


def test_raw_bridge_with_several_windows_places_areas_on_the_one_that_fits(monkeypatch):
    fake_bridge(monkeypatch, lambda: {"origin": "bottom-left", "windows": [RAW_MAIN, RAW_PREFS]})
    main = Rect(100, 50, 1000, 678)   # 2000 x 1300 px at 2 px / pt + a 28 pt title bar
    prefs = Rect(200, 100, 700, 578)  # 1400 x 1100 px at 2 px / pt + a 28 pt title bar
    st = step("Rename it in the Outliner.")
    # the main window in front: its Outliner, on it
    o = obs(windows=[Window("Blender", "donut.blend", main), Window("Blender", "Preferences", prefs)])
    t = T.resolve(st, BLENDER, o, [], ax_fn=Recorder(), ocr_fn=Recorder())
    assert t is not None and t.via == "bridge" and t.rect == Rect(850, 78, 250, 200)
    # Preferences in front: the main window's Outliner is never placed on it
    o = obs(windows=[Window("Blender", "Preferences", prefs), Window("Blender", "donut.blend", main)])
    assert T.resolve(st, BLENDER, o, [], ax_fn=Recorder(), ocr_fn=Recorder()) is None


def test_raw_bridge_with_two_windows_of_one_shape_is_ambiguous(monkeypatch):
    fake_bridge(monkeypatch, lambda: {"origin": "bottom-left", "windows": [RAW_MAIN, {**RAW_MAIN, "x": 40}]})
    o = obs(windows=[Window("Blender", "donut.blend", Rect(100, 50, 1000, 678))])
    assert T.resolve(step("Rename it in the Outliner."), BLENDER, o, [], ax_fn=Recorder(), ocr_fn=Recorder()) is None


# ------------------------------------------------------------------ review round 3: area words, area last

# the bridge's real /ui shape (blender_ext.ui_rects): retina pixels, bottom-left origin, areas relative to the window
RAW_UI = {"ok": True, "origin": "bottom-left", "pixel_size": 2.0, "windows": [
    {"x": 0, "y": 0, "width": 2000, "height": 1300, "areas": [
        {"type": "VIEW_3D", "ui_type": "VIEW_3D", "x": 0, "y": 0, "width": 1400, "height": 1300},
        {"type": "OUTLINER", "ui_type": "OUTLINER", "x": 1400, "y": 900, "width": 600, "height": 400},
        {"type": "PROPERTIES", "ui_type": "PROPERTIES", "x": 1400, "y": 0, "width": 600, "height": 900}]}]}
MAIN = Rect(100, 50, 1000, 678)  # 2000 x 1300 px at 2 px / pt + a 28 pt title bar


@pytest.mark.parametrize("instr,not_area", [
    ("Type 2 in the Levels Viewport field.", "3D Viewport"),          # a field in the modifier panel
    ("Press Ctrl+2 to add a Subdivision modifier", "Properties"),     # a key press in the viewport
    ("Turn on Viewport Display > In Front.", "3D Viewport"),
    ("Set the viewport value to 3.", "3D Viewport"),
])
def test_area_words_inside_a_ui_name_or_a_bare_modifier_never_circle_that_area(monkeypatch, instr, not_area):
    fake_bridge(monkeypatch, lambda: RAW_UI)
    t = T.resolve(step(instr), BLENDER, obs(windows=[Window("Blender", "donut.blend", MAIN)]), [],
                  ax_fn=Recorder(), ocr_fn=Recorder())
    assert t is None or t.label != not_area


def test_area_types():
    assert T.area_types("Type 2 in the Levels Viewport field.") == []
    assert T.area_types("Press Ctrl+2 to add a Subdivision modifier") == []
    assert T.area_types("Viewport Display settings") == []
    assert T.area_types("Hover over the viewport and press G.") == ["VIEW_3D"]
    assert T.area_types("Viewport: hover over it.") == ["VIEW_3D"]                  # starts the sentence
    assert T.area_types("Look around the Blender viewport.") == ["VIEW_3D"]
    assert T.area_types("Open the Modifier tab in the Properties editor.") == ["PROPERTIES"]
    assert T.area_types("Open the modifiers panel.") == ["PROPERTIES"]
    assert T.area_types("Rename it in the Outliner Tab, then in the 3D Viewport.") == ["VIEW_3D", "OUTLINER"]


def test_a_ui_name_beats_a_bridge_area(monkeypatch):
    fake_bridge(monkeypatch, lambda: RAW_UI)
    o = obs([blk("Add Modifier", 900, 300, 120)], windows=[Window("Blender", "donut.blend", MAIN)])
    t = T.resolve(step("click Add Modifier"), BLENDER, o, [], ax_fn=Recorder())
    assert t is not None and t.via == "ocr" and t.rect == Rect(900, 300, 120, 16) and t.label == "Add Modifier"
    # with the Properties editor named too: the button still wins; the area only when no control is found
    st = step("In the Properties editor, click Add Modifier.")
    t = T.resolve(st, BLENDER, o, [], ax_fn=Recorder())
    assert t.via == "ocr" and t.label == "Add Modifier"
    o = obs(windows=[Window("Blender", "donut.blend", MAIN)])
    t = T.resolve(st, BLENDER, o, [], ax_fn=Recorder(), ocr_fn=Recorder())
    assert t.via == "bridge" and t.label == "Properties" and t.rect == Rect(800, 278, 300, 450)


def test_a_ui_phrase_is_never_mapped_to_the_area_it_contains(monkeypatch):
    fake_bridge(monkeypatch, lambda: RAW_UI)
    o = obs(windows=[Window("Blender", "donut.blend", MAIN)])
    assert T.resolve(step("click Add Modifier"), BLENDER, o, [], ax_fn=Recorder(), ocr_fn=Recorder()) is None
    assert T.bridge_rect("Add Modifier", T.bridge_shape(RAW_UI, MAIN)) is None
    assert T.bridge_rect("Outliner", T.bridge_shape(RAW_UI, MAIN))[1] is True  # a phrase that IS an area name


def test_the_bridge_is_asked_once_per_resolve(monkeypatch):
    calls = []
    fake_bridge(monkeypatch, lambda: calls.append(1) or RAW_UI)
    o = obs(windows=[Window("Blender", "donut.blend", MAIN)])
    T.resolve(step("In the Properties editor, click Add Modifier."), BLENDER, o, [], ax_fn=Recorder(),
              ocr_fn=Recorder())
    assert calls == [1]


# ------------------------------------------------------------------ round 4: the round-3 regressions, by name

def ui_phrases(instr: str) -> list[str]:
    return [p.text for p in T.phrases(step(instr)) if p.kind == "ui"]


def test_r3_levels_viewport_field_is_no_view3d():
    ps = T.phrases(step("Type 2 in the Levels Viewport field."))
    assert ("VIEW_3D", "area") not in [(p.text, p.kind) for p in ps]
    assert T.area_types("Type 2 in the Levels Viewport field.") == []


def test_r3_ctrl_2_subdivision_modifier_is_no_properties():
    ps = T.phrases(step("Press Ctrl+2 to add a Subdivision modifier"))
    assert not any(p.text in ("PROPERTIES", "MODIFIER") for p in ps)
    assert T.area_types("Press Ctrl+2 to add a Subdivision modifier") == []


def test_r3_click_add_modifier_circles_the_button_never_the_properties_area(monkeypatch):
    fake_bridge(monkeypatch, lambda: RAW_UI)  # the bridge has the PROPERTIES area
    o = obs([blk("Add Modifier", 900, 300, 120)], windows=[Window("Blender", "donut.blend", MAIN)])
    t = T.resolve(step("click Add Modifier"), BLENDER, o, [], ax_fn=Recorder())
    assert t == T.Target(Rect(900, 300, 120, 16), "ocr", "Add Modifier")
    t = T.resolve(step("click Add Modifier"), BLENDER, o, [], ax_fn=Recorder((Rect(890, 296, 130, 22), MAIN)))
    assert t.via == "ax" and t.label == "Add Modifier"


# ------------------------------------------------------------------ round 4: the reproduced wrong circle

MODIFIER_TAB = "Open the Modifier tab in the Properties editor."


def test_must_not_circle_modifier_inside_the_add_modifier_button(no_bridge):
    # round 3: _CLICK took "Modifier" as a control and OCR found it inside the "Add Modifier" button
    assert "Modifier" not in ui_phrases(MODIFIER_TAB)
    assert [(p.text, p.kind) for p in T.phrases(step(MODIFIER_TAB))] == [("MODIFIER", "tab"), ("PROPERTIES", "area")]
    o = obs([blk("Add Modifier", 900, 300, 120)])
    assert T.resolve(step(MODIFIER_TAB), BLENDER, o, [], ax_fn=Recorder()) is None


def test_must_not_circle_modifier_for_a_where_ask(no_bridge):
    from server.orchestrator import onscreen_coach as OC

    plist = OC.where_phrases("where is the Modifier tab?")
    assert plist and not any(p.kind == "ui" for p in plist)
    o = obs([blk("Add Modifier", 900, 300, 120)])
    assert T.resolve(step(MODIFIER_TAB), BLENDER, o, [], ax_fn=Recorder(), phrase_list=plist) is None


@pytest.mark.parametrize("instr,want", [
    ('Click the "Modifier" tab.', [("MODIFIER", "tab"), ("PROPERTIES", "area")]),
    ("Open the Modifier Properties", [("MODIFIER", "tab"), ("PROPERTIES", "area")]),
    ("Open the Properties panel", [("PROPERTIES", "area")]),
    ("Expand the Transform panel.", []),                     # a place miyagi doesn't know: nothing, never "Transform"
    ("Go to the Material properties", [("MATERIAL", "tab")]),
    ("Click the wrench icon.", [("MODIFIER", "tab")]),
    ("Open the Object Data properties and add a UV map.", [("DATA", "tab")]),
])
def test_a_named_place_is_a_tab_or_area_never_a_control(instr, want):
    assert [(p.text, p.kind) for p in T.phrases(step(instr))] == want


def test_place_phrases():
    assert T.place_phrases("Add Modifier") is None
    assert T.place_phrases("Modifier tab") == [T.Phrase("MODIFIER", "tab"), T.Phrase("PROPERTIES", "area")]
    assert T.place_phrases("material properties") == [T.Phrase("MATERIAL", "tab")]
    assert T.place_phrases("Outliner area") == [T.Phrase("OUTLINER", "area")]
    assert T.place_phrases("Transform panel") == []
    # a name that IS an area or region: that place only (review round 2 of the targets lane)
    assert T.place_phrases("Viewport") == [T.Phrase("VIEW_3D", "area")]
    assert T.place_phrases("3D Viewport") == [T.Phrase("VIEW_3D", "area")]
    assert T.place_phrases("Outliner") == [T.Phrase("OUTLINER", "area")]
    assert T.place_phrases("Sidebar") == [T.Phrase("VIEW_3D:UI", "region")]
    assert T.place_phrases("N panel") == [T.Phrase("VIEW_3D:UI", "region")]
    assert T.place_phrases("Toolbar") == [T.Phrase("VIEW_3D:TOOLS", "region")]
    assert T.place_phrases("viewport header") == [T.Phrase("VIEW_3D:HEADER", "region")]
    for name in ("Levels Viewport", "Toggle Sidebar", "Outliner Filter", "Viewport Display"):
        assert T.place_phrases(name) is None, name


# ------------------------------------------------------------------ round 4: the bridge's /ui v2 (fakes)

def raw_v2(*, objects=None, sidebar_px: int = 1, nav: bool = True, props: dict | None = None, extra_windows=()):
    """The bridge's /ui with mode, active, regions, 3D Viewport objects and the Properties tab column (2000 x 1300 px:
    a Retina window of 1000 x 650 pt)."""
    view3d = {"type": "VIEW_3D", "ui_type": "VIEW_3D", "x": 0, "y": 0, "width": 1400, "height": 1300,
              "regions": [{"type": "HEADER", "x": 0, "y": 1252, "width": 1400, "height": 48},
                          {"type": "TOOLS", "x": 0, "y": 0, "width": 80, "height": 1252},
                          {"type": "UI", "x": 1400 - sidebar_px, "y": 0, "width": sidebar_px, "height": 1252},
                          {"type": "WINDOW", "x": 0, "y": 0, "width": 1400, "height": 1300}],
              "objects": objects if objects is not None else [
                  {"name": "Donut", "type": "MESH", "x": 600, "y": 500, "width": 200, "height": 100},
                  {"name": "Plate", "type": "MESH", "x": 400, "y": 300, "width": 600, "height": 120},
                  {"name": "Light", "type": "LIGHT", "x": 900, "y": 1000, "width": 24, "height": 24}]}
    regions = [{"type": "HEADER", "x": 1400, "y": 852, "width": 600, "height": 48},
               {"type": "WINDOW", "x": 1458, "y": 0, "width": 542, "height": 852}]
    if nav:
        regions.append({"type": "NAVIGATION_BAR", "x": 1400, "y": 0, "width": 58, "height": 852})
    properties = {"type": "PROPERTIES", "ui_type": "PROPERTIES", "x": 1400, "y": 0, "width": 600, "height": 900,
                  "regions": regions,
                  "properties": props if props is not None else {
                      "context": "OBJECT", "contexts": ["TOOL", "RENDER", "OUTPUT", "OBJECT", "MODIFIER", "MATERIAL"]}}
    outliner = {"type": "OUTLINER", "ui_type": "OUTLINER", "x": 1400, "y": 900, "width": 600, "height": 400,
                "regions": [{"type": "WINDOW", "x": 1400, "y": 900, "width": 600, "height": 400}]}
    main = {"x": 0, "y": 0, "width": 2000, "height": 1300, "areas": [view3d, outliner, properties]}
    return {"ok": True, "origin": "bottom-left", "pixel_size": 2.0, "mode": "OBJECT", "active": "Donut",
            "windows": [main, *extra_windows]}


RETINA = Rect(100, 50, 1000, 678)   # k = 0.5, 28 pt title bar: bottom at 728
PLAIN = Rect(100, 50, 2000, 1328)   # k = 1.0, 28 pt title bar: bottom at 1378
WIDE = Rect(0, 0, 2400, 1500)       # a primary display that holds PLAIN


def bobs(blocks=(), win: Rect = RETINA, screen: Rect = PRIMARY, windows=None):
    return obs(blocks, windows=windows if windows is not None else [Window("Blender", "donut.blend", win)],
               screen=screen)


def run(instr: str, ui, o=None, **kw):
    return T.resolve(step(instr), BLENDER, o if o is not None else bobs(), [], bridge=lambda: ui,
                     ax_fn=kw.pop("ax_fn", Recorder()), ocr_fn=kw.pop("ocr_fn", None), **kw)


def test_bridge_shape_v2_maps_regions_objects_tabs_and_state():
    shape = T.bridge_shape(raw_v2(sidebar_px=1), RETINA)
    assert shape["mode"] == "OBJECT" and shape["active"] == "Donut" and shape["context"] == "OBJECT"
    assert shape["contexts"][-1] == "MATERIAL"
    assert dict(shape["objects"])["Donut"] == Rect(400, 428, 100, 50)      # (100 + 600/2, 728 - 600/2, 200/2, 100/2)
    assert shape["tabs"] == Rect(800, 302, 29, 426)                        # the NAVIGATION_BAR region
    kinds = {(a, t) for a, t, _ in shape["regions"]}
    assert ("VIEW_3D", "TOOLS") in kinds and ("VIEW_3D", "UI") not in kinds  # a 1 px (hidden) sidebar is dropped
    assert ("PROPERTIES", "NAVIGATION_BAR") in kinds
    # the Properties editor's own tabs rect wins over the region
    shape = T.bridge_shape(raw_v2(props={"context": "MODIFIER", "tabs": {"x": 1400, "y": 0, "width": 60,
                                                                           "height": 800}}), RETINA)
    assert shape["tabs"] == Rect(800, 328, 30, 400) and shape["context"] == "MODIFIER" and shape["contexts"] == []


def test_modifier_tab_with_the_bridge_circles_the_tab_column(monkeypatch):
    t = run(MODIFIER_TAB, raw_v2(), bobs([blk("Add Modifier", 900, 300, 120)]))
    assert t == T.Target(Rect(800, 302, 29, 426), "bridge", "Modifier tab")
    # through the default seam too (a fake blender_ext module)
    fake_bridge(monkeypatch, lambda: raw_v2())
    t = T.resolve(step(MODIFIER_TAB), BLENDER, bobs(), [], ax_fn=Recorder(), ocr_fn=Recorder())
    assert t.via == "bridge" and t.rect == Rect(800, 302, 29, 426)
    # no tab column: the Properties editor (the area), never the button's word
    t = run(MODIFIER_TAB, raw_v2(nav=False), bobs([blk("Add Modifier", 900, 300, 120)]))
    assert t.via == "bridge" and t.label == "Properties"


def test_material_properties_circles_the_tab_column_never_one_tab():
    assert T.TAB_LAYOUT_CONFIDENT is False
    t = run("Go to the Material properties", raw_v2())
    assert t == T.Target(Rect(800, 302, 29, 426), "bridge", "Material tab")
    one = T.estimate_tab(Rect(800, 302, 29, 426), raw_v2()["windows"][0]["areas"][2]["properties"]["contexts"],
                         "MATERIAL")
    assert one is not None and t.rect != one  # the estimate exists, and is not used


def test_material_properties_without_the_bridge_is_none(no_bridge):
    assert T.resolve(step("Go to the Material properties"), BLENDER, bobs([blk("Material", 820, 400, 60)]), [],
                     ax_fn=Recorder()) is None


def test_one_tab_only_once_the_layout_is_trusted(monkeypatch):
    monkeypatch.setattr(T, "TAB_LAYOUT_CONFIDENT", True)
    t = run("Go to the Material properties", raw_v2())
    # contexts TOOL | RENDER OUTPUT | OBJECT MODIFIER MATERIAL, unit 29: 0.25 pad, 5 cells and 2 gaps above MATERIAL
    assert t.rect == Rect(800, 302 + 29 * (0.25 + 5 + 2 * 0.5), 29, 29) and t.label == "Material tab"
    t = run("Open the Texture tab", raw_v2())  # not shown now: the column, never a guessed slot
    assert t.rect == Rect(800, 302, 29, 426)


def test_estimate_tab_hand_math():
    col = Rect(10, 100, 20, 400)
    ctxs = ["TOOL", "RENDER", "OUTPUT", "OBJECT", "MODIFIER"]
    assert T.estimate_tab(col, ctxs, "TOOL") == Rect(10, 105, 20, 20)                  # 0.25 * 20 pad
    assert T.estimate_tab(col, ctxs, "RENDER") == Rect(10, 135, 20, 20)                # + 1 cell + 1 gap (10)
    assert T.estimate_tab(col, ctxs, "OUTPUT") == Rect(10, 155, 20, 20)
    assert T.estimate_tab(col, ctxs, "MODIFIER") == Rect(10, 205, 20, 20)              # 4 cells + 2 gaps
    assert T.estimate_tab(col, ctxs, "MATERIAL") is None                               # not shown
    assert T.estimate_tab(None, ctxs, "TOOL") is None
    assert T.estimate_tab(Rect(10, 100, 20, 60), ctxs, "MODIFIER") is None             # past the column's end
    assert T.estimate_tab(col, ctxs, "OUTPUT", cell=1.5, gap=0.0, pad=0.0) == Rect(10, 160, 20, 30)


# ------------------------------------------------------------------ round 4: objects

@pytest.mark.parametrize("instr", ["Select the Donut", "select the donut", "Click on the Donut to select it."])
def test_select_the_donut_circles_the_object(instr):
    t = run(instr, raw_v2())
    assert t == T.Target(Rect(400, 428, 100, 50), "bridge", "Donut")


def test_object_mapping_at_k_1():
    t = run("Select the Donut", raw_v2(), bobs(win=PLAIN, screen=WIDE))
    assert t == T.Target(Rect(700, 778, 200, 100), "bridge", "Donut")  # (100 + 600, 1378 - 600, 200, 100)


@pytest.mark.parametrize("instr", ["Add a Donut", "add a torus", "Add another Donut with Shift+A.",
                                   "Add a second Cube", "Add another mesh Cube", "Add a UV Sphere",
                                   "Add a new UV Sphere next to the Cube.", "Add the Donut from the Add menu.",
                                   "add the torus"])
def test_an_added_object_is_never_circled(instr):
    objs = [{"name": "Donut", "x": 600, "y": 500, "width": 200, "height": 100},
            {"name": "Torus", "x": 900, "y": 500, "width": 200, "height": 100},
            {"name": "Sphere", "x": 200, "y": 200, "width": 200, "height": 100},
            {"name": "Cube", "x": 200, "y": 800, "width": 200, "height": 100}]
    t = run(instr, raw_v2(objects=objs))
    if instr == "Add a new UV Sphere next to the Cube.":  # never the Sphere; the Cube it only names may be circled
        assert t is not None and t.label == "Cube"
    else:
        assert t is None or t.label not in ("Donut", "Torus", "Sphere", "Cube")


LCC = [{"name": "Light", "type": "LIGHT", "x": 900, "y": 1000, "width": 48, "height": 48},
       {"name": "Camera", "type": "CAMERA", "x": 300, "y": 900, "width": 48, "height": 48},
       {"name": "Cube", "type": "MESH", "x": 600, "y": 500, "width": 200, "height": 100}]


@pytest.mark.parametrize("instr", ["Open the Light properties", "Open the Camera properties",
                                   "Press Numpad 0 for Camera view.",
                                   "Set the Light power to 1000 W in the Light settings",
                                   "Check the Cube scale.", "Look at the Cube's modifiers.",
                                   "Rename the Cube Mesh data."])
def test_must_not_circle_an_object_whose_name_heads_a_place(instr):
    t = run(instr, raw_v2(objects=LCC))
    assert t is None or t.label not in ("Light", "Camera", "Cube"), (instr, t)


def test_light_and_camera_properties_are_the_object_data_tab():
    assert T.place_phrases("Light properties") == [T.Phrase("DATA", "tab")]
    assert T.tab_contexts("Open the Camera properties") == ["DATA"]
    t = run("Open the Light properties", raw_v2(objects=LCC))
    assert t == T.Target(Rect(800, 302, 29, 426), "bridge", "Object Data tab")
    # the object itself, when the step acts on it or only names it
    assert run("Select the Light", raw_v2(objects=LCC)).label == "Light"
    assert run("Look at the Camera from above.", raw_v2(objects=LCC)).label == "Camera"


def test_two_objects_with_one_casefolded_name_is_none():
    objs = [{"name": "Donut", "x": 600, "y": 500, "width": 200, "height": 100},
            {"name": "donut", "x": 900, "y": 500, "width": 200, "height": 100}]
    assert run("Select the Donut", raw_v2(objects=objs)) is None


def test_a_tiny_object_box_is_none():
    objs = [{"name": "Donut", "x": 600, "y": 500, "width": 10, "height": 10}]  # 5 x 5 pt
    assert run("Select the Donut", raw_v2(objects=objs)) is None


def test_short_names_and_partial_words_never_match():
    objs = [{"name": "Ob", "x": 600, "y": 500, "width": 200, "height": 100},
            {"name": "Cube", "x": 900, "y": 500, "width": 200, "height": 100}]
    assert run("Select the Ob", raw_v2(objects=objs)) is None
    assert run("Select the Cubes", raw_v2(objects=objs)) is None
    objs.append({"name": "Cube.001", "x": 200, "y": 500, "width": 200, "height": 100})
    assert run("Select Cube.001", raw_v2(objects=objs)).rect == Rect(200, 428, 100, 50)


def test_an_object_only_when_acted_on_while_a_control_is_named():
    # "the Donut" is not acted on, "Shade Smooth" is the control: never the Donut box
    o = bobs([blk("Shade Smooth", 300, 100, 90)])
    t = run("With the Donut selected, click Shade Smooth.", raw_v2(), o)
    assert t.via == "ocr" and t.label == "Shade Smooth"
    assert run("With the Donut selected, click Shade Smooth.", raw_v2()) is None
    # no control or tab named: an object the step names is circled
    assert run("Look at the Donut from the side.", raw_v2()).label == "Donut"


CUBE = [{"name": "Cube", "type": "MESH", "x": 600, "y": 500, "width": 200, "height": 100}]


@pytest.mark.parametrize("plist,label", [
    ([T.Phrase("MODIFIER", "tab"), T.Phrase("PROPERTIES", "area")], "Modifier tab"),   # where is the Modifier tab?
    ([T.Phrase("Add menu", "ui"), T.Phrase("Add", "ui")], None),                       # where is the Add menu?
    ([T.Phrase("OUTLINER", "area")], "Outliner"),                                      # where is the outliner?
])
def test_must_not_circle_the_steps_object_for_a_where_ask(plist, label):
    for instr in ("Select the Cube, then open the Modifier tab.", "Select the Cube"):
        t = run(instr, raw_v2(objects=CUBE), phrase_list=plist)
        assert (t.label if t else None) == label, (instr, plist, t)


def test_a_where_ask_for_an_object_circles_that_object():
    t = run("Open the Modifier tab.", raw_v2(objects=CUBE), phrase_list=[T.Phrase("Cube", "ui")])
    assert t == T.Target(Rect(400, 428, 100, 50), "bridge", "Cube")
    assert run("Open the Modifier tab.", raw_v2(objects=CUBE), phrase_list=[T.Phrase("cube", "ui")]).label == "Cube"


def test_select_in_the_outliner_reads_the_outliner_text():
    # the Outliner: (1400, 900, 600, 400) px -> (800, 78, 300, 200) pt
    o = bobs([blk("Donut", 830, 120, 40), blk("Donut", 420, 440, 40)])
    t = run("Select the Donut in the Outliner", raw_v2(), o)
    assert t == T.Target(Rect(830, 120, 40, 16), "ocr", "Donut")
    # the Outliner has no such text: the viewport object, never the other text block
    o = bobs([blk("Donut", 420, 440, 40)])
    t = run("Select the Donut in the Outliner", raw_v2(), o)
    assert t == T.Target(Rect(400, 428, 100, 50), "bridge", "Donut")


# ------------------------------------------------------------------ round 4: regions

def test_sidebar_region_only_when_shown():
    assert run("Press N to open the sidebar.", raw_v2(sidebar_px=1)) is None       # hidden: dropped, no circle
    t = run("Press N to open the sidebar.", raw_v2(sidebar_px=400))
    assert t.via == "bridge" and t.label == "Sidebar" and t.rect == Rect(600, 102, 200, 626)  # (100 + 1000/2, ...)
    t = run("Pick the Move tool in the toolbar.", raw_v2(), bobs())
    assert t.label == "Toolbar" and t.rect == Rect(100, 102, 40, 626)
    t = run("In the viewport header, open Shading.", raw_v2())
    assert t.label == "3D Viewport header" and t.rect == Rect(100, 78, 700, 24)


def test_region_words_that_are_not_regions():
    assert T.region_types("Choose View > Sidebar.") == []
    assert T.region_types("Click the header of the Subdivision panel.") == []
    assert T.region_types("Open the Toggle Sidebar menu.") == []
    assert T.region_types("Press N to open the N panel, then the toolbar.") == ["VIEW_3D:UI", "VIEW_3D:TOOLS"]


# ------------------------------------------------------------------ round 4: calibration

def test_a_miscalibrated_window_gives_no_bridge_rects():
    win = Rect(100, 50, 1460, 1300 * 0.73 + 28)   # k = 0.73: neither Retina nor not
    assert T.bridge_shape(raw_v2(), win) is None
    o = bobs(win=win, screen=WIDE)
    for instr in ("Select the Donut", MODIFIER_TAB, "Look around the 3D viewport."):
        assert run(instr, raw_v2(), o) is None, instr


@pytest.mark.parametrize("k,ok", [(0.5 * 1.029, True), (0.5 * 0.971, True), (1.0 * 1.029, True),
                                  (0.5 * 1.04, False), (1.0 * 0.95, False), (0.75, False)])
def test_scale_within_three_percent_of_a_backing_scale(k, ok):
    win = Rect(0, 0, 2000 * k, 1300 * k + 28)
    assert (T.bridge_shape(raw_v2(), win) is not None) is ok


def test_fullscreen_blender_is_accepted():
    full = Rect(0, 0, 1000, 650)                   # 2000 x 1300 px at 2 px / pt, no title bar
    t = run("Select the Donut", raw_v2(), bobs(win=full))
    assert t == T.Target(Rect(300, 350, 100, 50), "bridge", "Donut")   # (600/2, 650 - (500 + 100)/2, ...)
    # a second window of another shape at a sane scale (1000 x 500 px, k = 1.0: an implied 150 pt title bar): the
    # title-bar / full-screen scoring picks the full-screen main window
    other = {"x": 0, "y": 0, "width": 1000, "height": 500, "areas": []}
    assert T._sane_scale(full.w / other["width"])
    t = run("Select the Donut", raw_v2(extra_windows=[other]), bobs(win=full))
    assert t == T.Target(Rect(300, 350, 100, 50), "bridge", "Donut")
    # ... and beside a windowed one (RETINA: 28 pt title bar, k = 0.5) the other shape is rejected by the scoring
    other = {"x": 0, "y": 0, "width": 1000, "height": 560, "areas": []}   # k = 1.0, implied title 118 pt
    t = run("Select the Donut", raw_v2(extra_windows=[other]), bobs(win=RETINA))
    assert t == T.Target(Rect(400, 428, 100, 50), "bridge", "Donut")
    # a second window that fits exactly as well (full screen at k = 1.0 vs windowed at 0.5): ambiguous, no rects
    other = {"x": 0, "y": 0, "width": 1000, "height": 678, "areas": []}
    assert run("Select the Donut", raw_v2(extra_windows=[other]), bobs(win=RETINA)) is None


def test_two_same_shaped_blender_windows_give_none():
    twin = {**raw_v2()["windows"][0], "x": 40}
    assert run("Select the Donut", raw_v2(extra_windows=[twin])) is None
    assert run("Select the Donut", raw_v2(extra_windows=[twin]), bobs(win=Rect(0, 0, 1000, 650))) is None


def test_no_screen_window_gives_no_bridge_rects():
    assert T.bridge_shape(raw_v2(), None) is None
    assert run("Select the Donut", raw_v2(), bobs(windows=[])) is None


# ------------------------------------------------------------------ round 4: every source is gated, the bridge once

def test_every_bridge_source_passes_the_gate_and_the_primary_display():
    # under miyagi's overlay: refused
    assert T.resolve(step("Select the Donut"), BLENDER, bobs(), [Rect(380, 410, 200, 100)],
                     bridge=lambda: raw_v2(), ax_fn=Recorder()) is None
    t = T.resolve(step(MODIFIER_TAB), BLENDER, bobs(), [Rect(780, 280, 60, 460)], bridge=lambda: raw_v2(),
                  ax_fn=Recorder())
    assert t is not None and t.via == "bridge" and t.label == "Properties"  # the editor, never the covered column
    # a Blender window on another display: refused (marks carry no displayId)
    off = Rect(1500, 50, 1000, 678)
    for instr in ("Select the Donut", MODIFIER_TAB, "Press N to open the sidebar."):
        assert run(instr, raw_v2(sidebar_px=400), bobs(win=off)) is None, instr
    # a tab column larger than 40% of the window is not one: never circled as the tab column
    huge = raw_v2(props={"context": "OBJECT", "tabs": {"x": 0, "y": 0, "width": 1600, "height": 1100}})
    t = run(MODIFIER_TAB, huge, bobs())
    assert t is not None and t.label == "Properties"


def test_the_bridge_is_asked_once_with_every_source():
    calls = []

    def ui():
        calls.append(1)
        return raw_v2()

    for instr in ("Select the Donut", MODIFIER_TAB, "Press N to open the sidebar.", "click Add Modifier",
                  "Select the Donut in the Outliner"):
        calls.clear()
        T.resolve(step(instr), BLENDER, bobs(), [], bridge=ui, ax_fn=Recorder(), ocr_fn=Recorder())
        assert calls == [1], instr


# ------------------------------------------------------------------ review round 2: area / region names, common words

LEVELS = blk("Levels Viewport", 300, 200, 120)
TOGGLE = blk("Toggle Sidebar", 300, 260, 110)
FILTER = blk("Outliner Filter", 300, 320, 110)
VIEW3D_PT = Rect(100, 78, 700, 650)     # the 3D Viewport: (0, 0, 1400, 1300) px at k 0.5, bottom at 728
SIDEBAR_PT = Rect(600, 102, 200, 626)   # a shown 400 px sidebar


@pytest.mark.parametrize("instr", ["Click the Viewport and press G.", "Click the 3D Viewport, then press G.",
                                   "Open the Sidebar.", "Open the N panel.", "Click the Outliner.",
                                   "Select the Toolbar."])
def test_an_area_or_region_name_is_never_a_ui_phrase(instr):
    got = T.phrases(step(instr))
    assert got and not any(p.kind == "ui" for p in got), got


def test_must_not_circle_viewport_inside_levels_viewport():
    o = bobs([LEVELS, TOGGLE, FILTER])
    for instr in ("Click the Viewport and press G.", "Click the 3D Viewport, then press G."):
        assert run(instr, None, o) is None, instr                       # no bridge: nothing, never the OCR word
        t = run(instr, raw_v2(), o)
        assert t == T.Target(VIEW3D_PT, "bridge", "3D Viewport"), (instr, t)


def test_must_not_circle_sidebar_inside_toggle_sidebar():
    o = bobs([LEVELS, TOGGLE, FILTER])
    assert run("Open the Sidebar.", None, o) is None
    assert run("Open the Sidebar.", raw_v2(sidebar_px=1), o) is None    # hidden: no region, never "Toggle Sidebar"
    assert run("Open the Sidebar.", raw_v2(sidebar_px=400), o) == T.Target(SIDEBAR_PT, "bridge", "Sidebar")


@pytest.mark.parametrize("ask,label", [("where is the viewport?", "3D Viewport"),
                                       ("where is the sidebar?", "Sidebar"),
                                       ("where is the outliner?", "Outliner")])
def test_must_not_circle_a_where_asked_place_inside_a_longer_control(ask, label):
    from server.orchestrator import onscreen_coach as OC

    plist = OC.where_phrases(ask)
    assert plist and not any(p.kind == "ui" for p in plist), plist
    o = bobs([LEVELS, TOGGLE, FILTER])
    assert run("Press G to move it.", None, o, phrase_list=plist) is None
    t = run("Press G to move it.", raw_v2(sidebar_px=400), o, phrase_list=plist)
    assert t is not None and t.via == "bridge" and t.label == label, (ask, t)


AREA_EMPTY = [{"name": "Area", "type": "LIGHT", "x": 600, "y": 500, "width": 48, "height": 48},
              {"name": "Empty", "type": "EMPTY", "x": 900, "y": 500, "width": 48, "height": 48}]


@pytest.mark.parametrize("instr", ["Move the mouse over the viewport area and press G.",
                                   "Hover over the 3D Viewport area, then press Shift+A.",
                                   "If the field is empty, type 2.",
                                   "Leave the name field empty and press Enter."])
def test_must_not_circle_an_object_named_like_a_common_word(instr):
    t = run(instr, raw_v2(objects=AREA_EMPTY))
    assert t is None or t.label not in ("Area", "Empty"), (instr, t)


def test_a_named_object_needs_its_exact_spelling_after_a_determiner():
    assert run("Look at the Empty from above.", raw_v2(objects=AREA_EMPTY)).label == "Empty"
    assert run("Look at the empty from above.", raw_v2(objects=AREA_EMPTY)) is None
    assert run("Look at Empty from above.", raw_v2(objects=AREA_EMPTY)) is None
    # a verb acting on it: case aside, as before
    assert run("select the empty", raw_v2(objects=AREA_EMPTY)).label == "Empty"

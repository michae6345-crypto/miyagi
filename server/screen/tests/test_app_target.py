"""server.screen.app_target: the on-screen coach's free resolver chain (bridge -> AX -> OCR -> None) and its confidence
gate. Offline: a fake blender_ext module in sys.modules (or none), a fake AX tree, fake ScreenObservations."""
from __future__ import annotations

import sys
import time
import types

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
    t = T.resolve(step("In the Properties editor, open the Modifier tab."), BLENDER, obs(), [], ax_fn=ax, ocr_fn=ocr)
    assert t is not None and t.via == "bridge" and t.rect == Rect(850, 300, 240, 400) and t.label in ("Modifier", "Properties")
    assert ax.calls == [] and ocr.calls == []
    t = T.resolve(step("Select the Torus in the viewport."), BLENDER, obs(), [], ax_fn=ax, ocr_fn=ocr)
    assert t.via == "bridge" and t.label == "Torus" and t.rect == Rect(500, 400, 80, 60)
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
    src = open(T.__file__, encoding="utf-8").read().splitlines()
    lines = [ln for ln in src if "blender_ext" in ln and ln.lstrip().startswith(("from ", "import "))]
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

"""On-screen coach (Nov 24) in a real LessonSession: an app lesson's step circled on screen with its words beside it.
Offline: the strict contract-validating hub, a fake resolver (app_target.resolve) or fake resolver parts, no model."""
from __future__ import annotations

import asyncio
import json
import threading
import time
import types

import pytest

from server.lesson import app_lesson
from server.orchestrator import curated, onscreen_coach as OC
from server.orchestrator import session as session_mod
from server.orchestrator.screen_bridge import FakeScreen
from server.orchestrator.tests.test_session import Rig, run
from server.screen import app_target
from server.screen.types import Block, Rect, ScreenObservation, Window
from shared.contracts.events import engine_message

HIT = app_target.Target(Rect(400.0, 300.0, 60.0, 24.0), "ocr", "Add")


def blender_graph() -> dict:
    return {
        "lesson": {"id": "lesson-blender-donut", "title": "Blender Beginner Tutorial - Make a Donut", "goal": "a donut"},
        "sources": [{"id": "src1", "kind": "blog", "title": "Blender donut", "url": "https://example.com/donut"}],
        "steps": [
            {"id": "s1", "index": 1, "title": "Add a torus",
             "instructions": "Press Shift+A and choose Mesh > Torus to add the donut.",
             "checks": [{"id": "c1", "type": "screen_contains", "label": "torus added", "pattern": "Torus"}],
             "targets": [{"match": "Add", "label": "Add menu"}], "explanations": [], "hints": [], "common_mistakes": []},
            {"id": "s2", "index": 2, "title": "Smooth it",
             "instructions": "In the Properties editor, open the Modifier tab and add a Subdivision Surface modifier.",
             "checks": [{"id": "c2", "type": "screen_contains", "label": "modifier added", "pattern": "Subdivision"}],
             "targets": [], "explanations": [], "hints": [], "common_mistakes": []},
        ],
    }


def code_graph() -> dict:
    return {
        "lesson": {"id": "lesson-pandas-excel", "title": "Read Excel files with pandas"},
        "sources": [{"id": "src1", "kind": "blog", "title": "pandas read_excel", "url": "https://example.com/pandas"}],
        "steps": [{"id": "s1", "index": 1, "title": "Read the sheet", "file": "read.py",
                   "instructions": "In read.py, call pd.read_excel('data.xlsx') and print the head.",
                   "checks": [{"id": "c1", "type": "file_contains", "label": "read_excel", "pattern": "read_excel",
                               "file": "read.py"}],
                   "targets": [{"match": "Add"}], "explanations": [], "hints": [], "common_mistakes": []}],
    }


class Resolver:
    """Stands in for app_target.resolve: returns `result` (a Target or None), counts calls; `gate` blocks a call."""

    def __init__(self, result=HIT):
        self.result = result
        self.calls: list = []
        self.gate: threading.Event | None = None

    def __call__(self, step, app, obs, overlay, **kw):
        self.calls.append({"step": step.get("id"), "app": app, **kw})
        if self.gate is not None:
            self.gate.wait(5)
        return self.result


@pytest.fixture
def fast(monkeypatch):
    monkeypatch.setattr(OC, "STEP_DELAYS_S", (0.0, 0.0, 0.0, 0.0))
    monkeypatch.setattr(OC, "HOLD_POLL_S", 0.0)


@pytest.fixture
def resolver(monkeypatch, fast):
    r = Resolver()
    monkeypatch.setattr(app_target, "resolve", r)
    return r


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.setenv("MIYAGI_LESSONS_DIR", str(tmp_path / "lessons"))
    monkeypatch.delenv("DEMO", raising=False)
    return Rig(tmp_path)


async def settle(rig) -> None:
    for _ in range(4):
        await asyncio.sleep(0.05)
        await rig.settle()


def marks(rig) -> list[dict]:
    return [p for p in rig.of("annotate") if p.get("marks")]


def clears(rig) -> list[dict]:
    return [p for p in rig.of("annotate") if p.get("clear")]


async def start(rig, graph=None) -> None:
    await rig.s.load_graph(graph or blender_graph())
    await settle(rig)


async def press_card(rig, card: dict) -> None:
    tok = session_mod._ANSWERED.set(set())  # the learner's press (action context)
    try:
        await rig.s._emit_card(card, window_s=0.0)
    finally:
        session_mod._ANSWERED.reset(tok)
    await settle(rig)


# ------------------------------------------------------------------ lesson.ready lesson.app

def test_lesson_ready_carries_the_app_of_an_adapted_blender_lesson(rig, resolver):
    g = app_lesson.adapt(blender_graph())
    assert g["lesson"]["app"] == {"tool": "blender", "label": "Blender"}
    run(start(rig, blender_graph()))
    ready = rig.of("lesson.ready")[-1]
    assert ready["lesson"]["app"] == {"tool": "blender", "label": "Blender"}
    engine_message("lesson.ready", ready)  # the contract takes it


def test_lesson_ready_carries_using(rig):
    g = app_lesson.adapt(blender_graph())
    g["lesson"]["app"]["using"] = "Blender 4"
    rig.s.graph = g
    assert rig.s._lesson_ready_payload()["lesson"]["app"] == {"tool": "blender", "label": "Blender", "using": "Blender 4"}


def test_a_code_lesson_has_no_app_and_no_point_mark(rig, resolver):
    run(start(rig, code_graph()))
    assert "app" not in rig.of("lesson.ready")[-1]["lesson"]
    assert not OC.is_app_lesson(rig.s)
    run(rig.s.action("show_me"))
    assert marks(rig) == [] and resolver.calls == []


def test_the_curated_vscode_demo_lesson_has_no_app():
    g = curated.lesson_for("build a neural network", force=True)
    if g is None:
        pytest.skip("curated lesson file not in this checkout")
    app_lesson.adapt(g)
    assert "app" not in g["lesson"]
    s = types.SimpleNamespace(graph=g)
    assert not OC.is_app_lesson(s)


def test_a_vscode_app_is_never_an_app_lesson():
    g = blender_graph()
    g["lesson"]["app"] = {"tool": "vscode", "label": "VS Code"}
    assert not OC.is_app_lesson(types.SimpleNamespace(graph=g))
    g["lesson"]["app"] = {"tool": "blender", "label": "Blender"}
    assert OC.is_app_lesson(types.SimpleNamespace(graph=g))


# ------------------------------------------------------------------ step start

def test_step_start_sends_one_mark_with_text_and_keys(rig, resolver):
    run(start(rig))
    ms = marks(rig)
    assert len(ms) == 1 and len(ms[0]["marks"]) == 1
    m = ms[0]["marks"][0]
    assert m["why"] == "point" and m["stepId"] == "s1" and m["id"] == "os-s1-1"
    assert (m["x"], m["y"], m["w"], m["h"]) == (400.0, 300.0, 60.0, 24.0)
    assert m["label"] == "Add" and len(m["label"].split()) <= 4
    assert m["text"] == "Press Shift+A and choose Mesh > Torus to add the donut." and len(m["text"].split()) <= 12
    assert m["keys"] == ["⇧A"]
    assert "holdMs" not in ms[0]
    engine_message("annotate", ms[0])


def test_step_start_retries_until_found_then_stops(rig, monkeypatch, fast):
    r = Resolver(None)
    seq = iter([None, None, HIT, HIT])
    monkeypatch.setattr(app_target, "resolve", lambda *a, **kw: r(*a, **kw) and None or next(seq))
    run(start(rig))
    assert len(r.calls) == 3 and len(marks(rig)) == 1


def test_step_start_gives_up_after_three_retries(rig, monkeypatch, fast):
    r = Resolver(None)
    monkeypatch.setattr(app_target, "resolve", r)
    run(start(rig))
    assert len(r.calls) == 4 and marks(rig) == []


def test_replays_restores_and_the_hold_send_nothing(rig, resolver):
    run(start(rig))
    n = len(marks(rig))
    rig.s.restoring = True
    try:
        run(rig.s.start_step(0))
        run(settle(rig))
    finally:
        rig.s.restoring = False
    assert len(marks(rig)) == n
    run(OC.on_step(rig.s, rig.s.step_gen, {**rig.s.step, "replay": True}))
    assert len(marks(rig)) == n


def test_held_step_waits_for_the_learner(rig, resolver, monkeypatch):
    held = {"on": True}
    monkeypatch.setattr(type(rig.s), "awaiting_start", property(lambda self: held["on"]))

    async def go():
        await start(rig)
        assert marks(rig) == []  # "Before you start" is up: nothing yet
        held["on"] = False
        await settle(rig)

    run(go())
    assert len(marks(rig)) == 1


def test_a_step_change_during_a_resolve_sends_nothing(rig, monkeypatch, fast):
    r = Resolver()
    r.gate = threading.Event()
    monkeypatch.setattr(app_target, "resolve", r)

    async def go():
        await rig.s.load_graph(blender_graph())
        for _ in range(50):
            if r.calls:
                break
            await asyncio.sleep(0.01)
        assert r.calls and r.calls[0]["step"] == "s1"
        rig.s.step_gen += 1  # the learner moved on while the resolver ran
        r.gate.set()
        await settle(rig)

    run(go())
    assert [m for p in marks(rig) for m in p["marks"] if m["stepId"] == "s1"] == []


# ------------------------------------------------------------------ Not yet / where?

def test_a_pressed_not_yet_recircles_but_not_twice_within_eight_seconds(rig, resolver):
    run(start(rig))
    assert len(marks(rig)) == 1
    resolver.result = app_target.Target(Rect(420.0, 300.0, 60.0, 24.0), "ocr", "Add")  # moved 20 pt: a new mark
    run(press_card(rig, {"stepId": "s1", "kind": "hint", "title": "Not yet", "body": "Add the torus first."}))
    assert len(marks(rig)) == 2
    run(press_card(rig, {"stepId": "s1", "kind": "hint", "title": "Not yet", "body": "Still no torus."}))
    assert len(marks(rig)) == 2  # the identical mark went out moments ago
    rig.clock.t += 9
    run(press_card(rig, {"stepId": "s1", "kind": "hint", "title": "Not yet", "body": "Try the Add menu."}))
    assert len(marks(rig)) == 3


def test_a_not_yet_off_the_press_path_never_marks(rig, resolver):
    run(start(rig))
    n = len(resolver.calls)
    run(rig.s._emit_card({"stepId": "s1", "kind": "hint", "title": "Not yet", "body": "auto"}, window_s=0.0))
    run(settle(rig))
    assert len(resolver.calls) == n and len(marks(rig)) == 1


def test_show_me_always_resends_with_a_new_id(rig, resolver):
    run(start(rig))

    async def go():
        await rig.s.action("show_me")
        await settle(rig)
        await rig.s.action("show_me")
        await settle(rig)

    run(go())
    ids = [p["marks"][0]["id"] for p in marks(rig)]
    assert len(ids) == 3 and len(set(ids)) == 3
    assert not [c for c in rig.of("card") if c.get("title") in ("Nothing to point at", "Where to work")]


def test_show_me_with_nothing_found_sends_the_where_words(tmp_path, monkeypatch, fast):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    r = Resolver(None)
    monkeypatch.setattr(app_target, "resolve", r)
    rg = Rig(tmp_path, screen=FakeScreen())
    run(start(rg))
    rg.s.last_obs = object()  # the reader has a frame: "not found" really means not on screen
    mark = rg.mark()
    run(rg.s.action("show_me"))
    run(settle(rg))
    after = rg.since(mark)
    assert r.calls and not [e for e in after if e["type"] == "annotate"]
    assert [e for e in after if e["type"] == "card" and e["payload"].get("kind") == "where"]  # the existing words


def test_a_typed_where_ask_circles_what_it_names(rig, resolver):
    run(start(rig))
    run(rig.s.action("ask", "where is the Add menu?"))
    run(settle(rig))
    assert len(marks(rig)) == 2
    pl = resolver.calls[-1]["phrase_list"]
    assert [p.text for p in pl][:2] == ["Add menu", "Add"]


def test_the_idle_and_evaluate_loops_never_mark(rig, resolver):
    run(start(rig))
    n, calls = len(rig.of("annotate")), len(resolver.calls)

    async def go():
        for _ in range(3):
            rig.clock.t += 30
            await rig.s.tick()
            await rig.s.evaluate("tick")
        await settle(rig)

    run(go())
    assert len(rig.of("annotate")) == n and len(resolver.calls) == calls


# ------------------------------------------------------------------ clear / one pointer

def test_pass_clears_once_and_nothing_when_no_mark_is_up(rig, resolver):
    run(start(rig))
    run(rig.s._pass_step())
    run(settle(rig))
    assert len(clears(rig)) == 1
    run(OC.clear(rig.s))
    assert len(clears(rig)) == 1


def test_skip_clears(rig, resolver):
    run(start(rig))
    run(rig.s.action("skip_step"))
    run(settle(rig))
    assert len(clears(rig)) == 1


def test_lesson_end_clears_once(rig, resolver):
    run(start(rig))
    run(rig.s.end_lesson("stopped"))
    assert len(clears(rig)) == 1
    run(rig.s.end_lesson("stopped"))
    assert len(clears(rig)) == 1


def test_no_clear_when_nothing_was_drawn(rig, monkeypatch, fast):
    monkeypatch.setattr(app_target, "resolve", Resolver(None))
    run(start(rig))
    run(rig.s._pass_step())
    run(rig.s.end_lesson("stopped"))
    assert clears(rig) == []


def test_a_new_lesson_clears_the_old_mark(rig, resolver):
    run(start(rig))
    run(rig.s.load_graph(code_graph()))
    assert len(clears(rig)) == 1


def test_no_spotlight_rect_while_the_steps_mark_is_up(rig, resolver):
    run(start(rig))
    assert OC.holds_spot(rig.s)
    mark = rig.mark()
    run(rig.s._show_spot({"rect": {"x": 10.0, "y": 10.0, "w": 100.0, "h": 20.0}, "caption": "here", "app": "Blender"}))
    assert not [e for e in rig.since(mark) if e["type"] == "spotlight" and e["payload"].get("rect")]
    run(OC.clear(rig.s))
    assert not OC.holds_spot(rig.s)


# ------------------------------------------------------------------ free only

def test_the_onscreen_path_never_calls_a_model(rig, monkeypatch, fast):
    def boom(*a, **kw):
        raise AssertionError("a model was called on the on-screen path")

    for name in ("show_me", "point", "where", "explain", "describe"):
        monkeypatch.setattr(rig.s.m, name, boom, raising=False)
    reader = types.SimpleNamespace(where=boom, describe=boom, overlay_rects=lambda: [],
                                   latest=lambda: ScreenObservation(
                                       t=time.time(), app="Blender", windows=[Window("Blender", "d", Rect(0, 0, 1200, 800))],
                                       blocks=[Block("Add", Rect(400, 300, 40, 16), 0.9, app="Blender")]))
    monkeypatch.setattr(OC, "_observe", lambda s: (reader.latest(), reader.overlay_rects(), "Blender"))
    monkeypatch.setitem(__import__("sys").modules, "server.workspace.blender_ext", None)
    monkeypatch.setattr(app_target, "ax_target", lambda *a, **kw: None)

    async def go():
        await start(rig)
        await rig.s.action("show_me")
        await settle(rig)

    run(go())
    ms = marks(rig)
    assert len(ms) == 2 and all(p["marks"][0]["label"] == "Add" for p in ms)
    assert not rig.of("error")


# ------------------------------------------------------------------ copy

@pytest.mark.parametrize("text,want", [
    ("Press Shift+A and add a Torus.", ["⇧A"]),
    ("Save the file with ⌘S.", ["⌘S"]),
    ("press G then Z to move it up", ["G", "Z"]),
    ("Press Ctrl+Shift+Z to redo.", ["⌃⇧Z"]),
    ("Press Tab, then press Numpad 1.", ["Tab", "Numpad 1"]),
    ("Render with F12.", ["F12"]),
    ("Press Esc, then Delete, then Return, then Space.", ["Esc", "Delete", "Return"]),
    ("Select a face in the viewport.", []),
])
def test_keys(text, want):
    assert OC.keys(text) == want


def test_text_is_cut_at_a_clause():
    t = OC.short_text("In the Properties editor, open the Modifier tab, click Add Modifier and choose Subdivision "
                      "Surface, then set Levels to 2.")
    assert t == "In the Properties editor, open the Modifier tab" and len(t.split()) <= 12
    assert OC.short_text("Add a torus. Then scale it.") == "Add a torus."


def test_where_phrases():
    assert OC.where_phrases("where do I click?") == []
    assert OC.where_phrases("how do I add a torus?") is None
    assert [p.text for p in OC.where_phrases("where's the outliner?")] == ["outliner", "OUTLINER"]
    assert OC.where_phrases("where is the thing I need to press to make the donut smooth?") is None  # > 8 words


def test_contract_marks_validate():
    m = {"marks": [{"id": "os-s1-1", "why": "point", "stepId": "s1", "label": "Add", "text": "Add a torus",
                    "keys": ["⇧A"], "x": 1.0, "y": 2.0, "w": 30.0, "h": 20.0}]}
    assert engine_message("annotate", m)["payload"] == json.loads(json.dumps(m))
    assert engine_message("annotate", {"marks": [{"why": "answer", "askId": "a1", "x": 1, "y": 2, "w": 3, "h": 4}]})
    assert engine_message("annotate", {"clear": True})

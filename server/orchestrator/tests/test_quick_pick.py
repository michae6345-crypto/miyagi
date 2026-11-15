"""t9 screen.avoid (quick_pick.py + ax.quickpick_in), offline: a FAKE AX tree of a VS Code window (never the real AX API)
and a fake session. Run from the repo root:  python -m pytest server/orchestrator/tests/test_quick_pick.py -q"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace as NS

import pytest

from server.orchestrator import quick_pick
from server.screen.types import Rect
from shared.contracts.events import validate_engine_payload

ax = pytest.importorskip("server.screen.ax")  # pure helpers only: quickpick_in takes the fake tree's get / rect


def node(role: str, rect: tuple, parent: dict | None = None, **attrs) -> dict:
    el = {"AXRole": role, "rect": Rect(*rect), "AXParent": parent, "AXChildren": [], **attrs}
    if parent is not None:
        parent["AXChildren"].append(el)
    return el


def get(el, name):
    return el.get(name) if el is not None else None


def rect(el):
    return el.get("rect") if el is not None else None


def vscode_tree() -> dict:
    """A 1440x900 VS Code window: the workbench, an editor (focused AXTextArea), the find widget (top right) and the
    quick-pick widget (input = AXComboBox, list = AXList "Quick Input") at the top centre."""
    win = node("AXWindow", (0, 0, 1440, 900))
    bench = node("AXGroup", (0, 0, 1440, 900), win)
    editor = node("AXTextArea", (348, 80, 1092, 600), bench, AXRoleDescription="editor")
    find = node("AXTextField", (1100, 84, 300, 26), bench, AXDescription="Find")
    widget = node("AXGroup", (420, 38, 600, 360), bench, AXDOMClassList=["quick-input-widget", "show-file-icons"])
    header = node("AXGroup", (426, 44, 588, 30), widget)
    combo = node("AXComboBox", (430, 46, 580, 26), header, AXDescription="Type to narrow down results.")
    node("AXList", (420, 78, 600, 320), widget, AXDescription="Quick Input")
    return {"win": win, "editor": editor, "find": find, "widget": widget, "combo": combo, "bench": bench}


# ---------------------------------------------------------------------- the AX match (fake tree)

def test_quickpick_found_from_its_focused_input():
    t = vscode_tree()
    assert ax.quickpick_in(t["win"], t["combo"], get, rect) == Rect(420, 38, 600, 360)  # the whole widget


def test_quickpick_found_by_hint_without_combobox_role_or_class():
    t = vscode_tree()
    t["combo"]["AXRole"] = "AXTextField"  # an older Chromium: a plain text field; the "Quick Input" list says it
    t["widget"].pop("AXDOMClassList")
    assert ax.quickpick_in(t["win"], t["combo"], get, rect) == Rect(420, 38, 600, 360)


@pytest.mark.parametrize("focus", ["editor", "find"])
def test_no_quickpick_when_focus_is_elsewhere(focus):
    t = vscode_tree()
    assert ax.quickpick_in(t["win"], t[focus], get, rect) is None


def test_centred_text_field_without_any_hint_is_not_the_quickpick():
    win = node("AXWindow", (0, 0, 1440, 900))
    box = node("AXGroup", (420, 60, 600, 40), win)
    field = node("AXTextField", (430, 66, 580, 26), box, AXDescription="Search settings")
    assert ax.quickpick_in(win, field, get, rect) is None


def test_quickpick_low_in_the_window_is_not_matched():
    t = vscode_tree()
    t["combo"]["rect"] = Rect(430, 600, 580, 26)  # bottom half: not where VS Code puts its picker
    assert ax.quickpick_in(t["win"], t["combo"], get, rect) is None


# ---------------------------------------------------------------------- screen.avoid (fake session, fake AX tree)

class AXScreen:
    """The reader's "ui:quickpick" region, from the fake tree's focused element (ax.quickpick_in)."""

    def __init__(self) -> None:
        self.tree = vscode_tree()
        self.focused = self.tree["editor"]
        self.looks = 0

    def region(self, name: str, app: str | None = None) -> dict | None:
        assert name == "ui:quickpick"
        self.looks += 1
        r = ax.quickpick_in(self.tree["win"], self.focused, get, rect)
        return r.to_dict() if r is not None else None


def session(screen, lesson: bool = True):
    sent: list[tuple[str, dict]] = []

    async def emit(type_: str, payload: dict | None = None) -> None:
        validate_engine_payload(type_, payload)  # the contract (events.py) accepts it
        sent.append((type_, payload))

    return NS(graph={"lesson": {"id": "l1"}} if lesson else None, lesson_epoch=1, screen=screen, emit=emit), sent


def avoids(sent) -> list[list[dict]]:
    return [p["rects"] for t, p in sent if t == "screen.avoid"]


def test_open_stay_open_close_sends_one_rect_then_nothing_then_empty():
    scr = AXScreen()
    s, sent = session(scr)

    async def go():
        await quick_pick.poll(s)  # closed from the start: nothing to say
        assert avoids(sent) == []
        scr.focused = scr.tree["combo"]  # the learner opens the kernel picker
        await quick_pick.poll(s)
        assert avoids(sent) == [[{"kind": "quickpick", "x": 420.0, "y": 38.0, "w": 600.0, "h": 360.0}]]
        await quick_pick.poll(s)  # still open: nothing re-sent
        await quick_pick.poll(s)
        assert len(avoids(sent)) == 1
        scr.focused = scr.tree["editor"]  # picked: it closed
        await quick_pick.poll(s)
        assert avoids(sent)[-1] == [] and len(avoids(sent)) == 2
        await quick_pick.poll(s)  # still closed: nothing
        assert len(avoids(sent)) == 2

    asyncio.run(go())
    assert all(t == "screen.avoid" for t, _ in sent)


def test_a_resized_picker_is_sent_again():
    scr = AXScreen()
    s, sent = session(scr)
    scr.focused = scr.tree["combo"]

    async def go():
        await quick_pick.poll(s)
        scr.tree["widget"]["rect"] = Rect(420, 38, 600, 120)  # typing filtered the list down
        await quick_pick.poll(s)

    asyncio.run(go())
    assert [r[0]["h"] for r in avoids(sent)] == [360.0, 120.0]


def test_no_lesson_sends_nothing():
    scr = AXScreen()
    scr.focused = scr.tree["combo"]  # the picker is open, but no lesson runs
    s, sent = session(scr, lesson=False)
    asyncio.run(quick_pick.poll(s))
    assert sent == [] and scr.looks == 0  # not even an AX look


def test_lesson_end_then_new_lesson_starts_from_nothing():
    scr = AXScreen()
    scr.focused = scr.tree["combo"]
    s, sent = session(scr)

    async def go():
        await quick_pick.poll(s)
        s.graph = None  # lesson ended (the app drops the avoid rects on lesson.ended): nothing sent
        await quick_pick.poll(s)
        assert len(avoids(sent)) == 1
        s.graph, s.lesson_epoch = {"lesson": {"id": "l2"}}, 2  # the next lesson, picker still open: sent again
        await quick_pick.poll(s)

    asyncio.run(go())
    assert len(avoids(sent)) == 2 and avoids(sent)[1][0]["kind"] == "quickpick"


def test_a_failed_look_changes_nothing():
    class Broken(AXScreen):
        def region(self, name, app=None):
            raise RuntimeError("AX timeout")

    s, sent = session(Broken())
    asyncio.run(quick_pick.poll(s))
    assert sent == []


def test_contract_rejects_an_unknown_kind():
    with pytest.raises(Exception):
        validate_engine_payload("screen.avoid", {"rects": [{"kind": "toast", "x": 0, "y": 0, "w": 1, "h": 1}]})
    assert validate_engine_payload("screen.avoid", {"rects": []}) == {"rects": []}

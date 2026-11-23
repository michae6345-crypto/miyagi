"""Circle to ask through the session (server/orchestrator/circle_ask.py): offline, a fake screen and a fake model.

The hub is strict, so every card and annotate here is checked against shared/contracts/events.py.
"""

from __future__ import annotations

import asyncio

import pytest

from server.coach import llm
from server.orchestrator.modules import Modules
from server.orchestrator.screen_bridge import FakeScreen
from server.orchestrator.tests.test_session import Rig
from server.screen.types import ScreenPermissionError
from shared.contracts.events import parse_app_message

REGION = {"x": 100.0, "y": 200.0, "w": 300.0, "h": 80.0, "displayId": 69733378, "scale": 2.0}
OBS = {"blocks": [{"text": "Run", "rect": {"x": 120, "y": 220, "w": 40, "h": 18}, "app": "Code"},
                  {"text": "import numpy as np", "rect": {"x": 180, "y": 220, "w": 160, "h": 18}, "app": "Code"},
                  {"text": "elsewhere", "rect": {"x": 900, "y": 700, "w": 100, "h": 18}, "app": "Code"}],
       "screen": {"x": 0, "y": 0, "w": 1512, "h": 982}, "scale": 2.0, "app": "Code", "windows": []}


def _image():
    from PIL import Image

    return Image.new("RGB", (3024, 1964), (240, 240, 235))


class FakeModel:
    def __init__(self, data):
        self.data, self.calls = data, []

    async def __call__(self, **kw):
        self.calls.append(kw)
        return llm.CallResult(data=self.data, model="claude-haiku-5-5", latency_s=0.1)


@pytest.fixture
def screen():
    s = FakeScreen()
    s.ask = (OBS, _image())
    return s


@pytest.fixture
def rig(tmp_path, monkeypatch, screen):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.delenv("DEMO", raising=False)
    return Rig(tmp_path, modules=Modules(demo=False, force_stubs="lesson,finder,diagrams"), screen=screen)


@pytest.fixture
def model(monkeypatch):
    m = FakeModel({"title": "The Run button", "body": "Run starts your script. It runs the open file.",
                   "box_id": 1, "label": "Run button"})
    monkeypatch.setattr(llm, "structured_call_retrying", m)
    return m


def run(coro):
    return asyncio.run(coro)


def test_circle_ask_without_a_lesson_answers_next_to_the_circle_and_circles_the_thing(rig, model):
    async def go():
        await rig.s.action("ask", "", region=REGION, ask_id="ask-1", source="circle")
        await rig.settle()

    run(go())
    [card] = rig.of("card")
    assert card["kind"] == "answer" and card["title"] == "The Run button"
    assert card["askId"] == "ask-1" and card["region"] == REGION and "stepId" not in card
    [ann] = rig.of("annotate")
    [mark] = ann["marks"]
    assert mark["why"] == "answer" and mark["askId"] == "ask-1" and mark["displayId"] == REGION["displayId"]
    assert ann["holdMs"] > 0
    assert "error" not in rig.types()  # never "No lesson is running yet." for a circle
    assert "LEARNER ASKS: What is this?" in model.calls[0]["user_text"]


def test_circle_ask_in_a_lesson_carries_the_step_and_its_context(rig, model):
    async def go():
        await rig.start_lesson()
        mark = rig.mark()
        await rig.s.action("ask", "why is this here?", region=REGION, ask_id="ask-2", source="circle")
        await rig.settle()
        return mark

    since = run(go())
    cards = [e["payload"] for e in rig.since(since) if e["type"] == "card"]
    [card] = [c for c in cards if c.get("askId") == "ask-2"]
    assert card["stepId"] == rig.s.step["id"]
    assert rig.s.step["title"] in model.calls[0]["user_text"]
    assert "LEARNER ASKS: why is this here?" in model.calls[0]["user_text"]


def test_no_permission_says_plainly_it_cannot_see(rig, model, screen):
    screen.ask_error = ScreenPermissionError("no Screen Recording")

    async def go():
        await rig.s.action("ask", "", region=REGION, ask_id="ask-3")
        await rig.settle()

    run(go())
    [card] = rig.of("card")
    assert card["title"] == "I can't see your screen" and "Screen Recording" in card["body"]
    assert card["askId"] == "ask-3" and model.calls == [] and rig.of("annotate") == []


def test_screen_reported_down_skips_the_capture(rig, model, screen):
    screen.down = "no_permission"
    screen.ask_error = AssertionError("must not capture")

    async def go():
        await rig.s.action("ask", "", region=REGION, ask_id="ask-4")
        await rig.settle()

    run(go())
    [card] = rig.of("card")
    assert card["title"] == "I can't see your screen" and model.calls == []


def test_no_screen_reader_at_all(rig, model):
    rig.s.screen = None

    async def go():
        await rig.s.action("ask", "", region=REGION, ask_id="ask-5")
        await rig.settle()

    run(go())
    [card] = rig.of("card")
    assert card["title"] == "I can't see your screen" and "can't see your screen" in card["body"]


def test_no_model_answers_from_the_text_read(rig, monkeypatch):
    """No key: the real structured call refuses before the network; the card quotes the circled text."""
    async def go():
        await rig.s.action("ask", "", region=REGION, ask_id="ask-6")
        await rig.settle()

    run(go())
    [card] = rig.of("card")
    assert card["title"] == "Here's what I read" and "import numpy as np" in card["body"]
    assert "elsewhere" not in card["body"] and rig.of("annotate") == []


def test_stubbed_coach_answers_from_the_text_read(tmp_path, monkeypatch, screen):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    rig = Rig(tmp_path, modules=Modules(demo=False, force_stubs="all"), screen=screen)

    async def go():
        await rig.s.action("ask", "What is this?", region=REGION, ask_id="ask-7")
        await rig.settle()

    run(go())
    [card] = rig.of("card")
    assert card["title"] == "Here's what I read" and card["askId"] == "ask-7"


def test_a_failing_capture_falls_back_to_a_fresh_last_frame_without_a_picture(rig, model, screen):
    import time

    screen.ask_error = TimeoutError("capture stalled")
    rig.s.last_obs = type("Obs", (), {**OBS, "t": time.time()})()

    async def go():
        await rig.s.action("ask", "", region=REGION, ask_id="ask-8")
        await rig.settle()

    run(go())
    [card] = rig.of("card")
    assert card["title"] == "The Run button"
    assert len(model.calls[0]["user_content"]) == 1  # text only: no picture from an old frame


def test_plain_typed_ask_is_unchanged_and_echoes_its_ask_id(rig, monkeypatch):
    async def explain(step, question, context):
        return {"stepId": step["id"], "kind": "answer", "title": "Answer", "body": f"About {question}"}

    async def go():
        await rig.start_lesson()
        monkeypatch.setattr(rig.s.m, "explain", explain)
        mark = rig.mark()
        await rig.s.action("ask", "why tanh?", ask_id="ask-9", source="typed")
        await rig.settle()
        return mark

    since = run(go())
    cards = [e["payload"] for e in rig.since(since) if e["type"] == "card"]
    assert any(c["body"] == "About why tanh?" and c.get("askId") == "ask-9" and "region" not in c for c in cards)


def test_engine_dispatch_passes_the_region_through(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    from server.orchestrator.main import Engine

    e = Engine()
    seen: list = []

    async def action(kind, text=None, **kw):
        seen.append((kind, text, kw))

    e.session.action = action
    raw = {"type": "action", "payload": {"kind": "ask", "text": "What is this?", "region": REGION,
                                         "source": "circle", "askId": "ask-10"}}
    assert parse_app_message(raw).payload.region is not None
    run(e.dispatch(raw))
    run(e.dispatch({"type": "action", "payload": {"kind": "hint"}}))
    assert seen[0] == ("ask", "What is this?", {"region": REGION, "ask_id": "ask-10", "source": "circle"})
    assert seen[1] == ("hint", None, {})  # an older app's action: called exactly as before


# ---------------------------------------------------------------------------------------------- fix round 1

class FakeReader:
    """A ScreenReader stand-in behind the REAL ScreenBridge: capture_once records the display it was asked for."""

    status, thread_alive, fixture, last_error = "ok", True, None, None

    def __init__(self, obs=OBS):
        self.obs, self.pil, self.asked = obs, _image(), []

    def capture_once(self, display_id=None, trigger="ask"):
        self.asked.append((display_id, trigger))
        return self.obs, self.pil

    def latest_frame(self, region=None):
        raise AssertionError("an ask never reads the reader's last frame")


def _bridge(reader, paused=True):
    from server.orchestrator.screen_bridge import ScreenBridge

    b = ScreenBridge(enabled=True)
    b.reader, b.paused, b.started = reader, paused, not paused
    return b


def test_bridge_captures_the_display_the_learner_circled_on(tmp_path, monkeypatch, model):
    """Display B circled while the focused window is on A: the one-off capture is of B (region.displayId), through
    the real ScreenBridge.ask_frame -> reader.capture_once, paused or not."""
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.delenv("DEMO", raising=False)
    reader = FakeReader()
    bridge = _bridge(reader)
    rig = Rig(tmp_path, modules=Modules(demo=False, force_stubs="lesson,finder,diagrams"), screen=bridge)

    async def go():
        await rig.s.action("ask", "", region={**REGION, "displayId": 424242}, ask_id="d1", source="circle")
        await rig.settle()

    run(go())
    assert reader.asked == [(424242, "ask")]
    [card] = rig.of("card")
    assert card["askId"] == "d1" and card["title"] == "The Run button"
    bridge.paused = False  # a running reader: still a one-off capture of that display, never its last frame
    assert bridge.ask_frame(9) == (OBS, reader.pil)
    assert reader.asked[-1] == (9, "ask")


def test_bridge_without_a_one_off_capture_reads_nothing():
    """A reader with no capture_once (an old one): no frame, never its stale last picture."""
    class Old:
        def latest_frame(self, region=None):
            raise AssertionError("must not read the last frame")

    assert _bridge(Old()).ask_frame(1) == (None, None)


def test_the_session_passes_the_region_display_to_the_capture(rig, model, screen):
    async def go():
        await rig.s.action("ask", "", region=REGION, ask_id="d2", source="circle")
        await rig.settle()

    run(go())
    assert screen.ask_displays == [REGION["displayId"]]


def test_a_demo_fixture_frame_is_not_explained_as_the_real_screen(rig, model, screen, monkeypatch):
    """DEMO=1 without Screen Recording swaps in a fixture PNG: the learner gets "I can't see your screen"."""
    monkeypatch.delenv("TUT_SCREEN_FIXTURE", raising=False)
    screen.ask = ({**OBS, "source": "fixture:vscode_fullscreen_top.png"}, _image())

    async def go():
        await rig.s.action("ask", "", region=REGION, ask_id="f1", source="circle")
        await rig.settle()

    run(go())
    [card] = rig.of("card")
    assert card["title"] == "I can't see your screen" and "Screen Recording" in card["body"]
    assert card["askId"] == "f1" and model.calls == [] and rig.of("annotate") == []


def test_an_explicit_dev_fixture_is_read_as_the_screen(rig, model, screen, monkeypatch):
    monkeypatch.setenv("TUT_SCREEN_FIXTURE", "/nonexistent/fixture.png")
    screen.ask = ({**OBS, "source": "fixture:fixture.png"}, _image())

    async def go():
        await rig.s.action("ask", "", region=REGION, ask_id="f2", source="circle")
        await rig.settle()

    run(go())
    [card] = rig.of("card")
    assert card["title"] == "The Run button" and len(model.calls) == 1


def test_a_fixture_last_frame_is_not_used_either(rig, model, screen, monkeypatch):
    import time

    monkeypatch.delenv("TUT_SCREEN_FIXTURE", raising=False)
    screen.ask_error = TimeoutError("capture stalled")
    rig.s.last_obs = type("Obs", (), {**OBS, "t": time.time(), "source": "fixture:x.png"})()

    async def go():
        await rig.s.action("ask", "", region=REGION, ask_id="f3")
        await rig.settle()

    run(go())
    [card] = rig.of("card")
    assert card["title"] == "I can't see your screen" and model.calls == []


def test_a_failing_circle_ask_without_a_lesson_still_answers_its_ink(rig, model, monkeypatch):
    from server.orchestrator import circle_ask

    async def boom(*a, **k):
        raise RuntimeError("emit failed")

    monkeypatch.setattr(circle_ask, "answer", boom)

    async def go():
        await rig.s.action("ask", "", region=REGION, ask_id="x1", source="circle")
        await rig.settle()

    run(go())
    [card] = rig.of("card")
    assert card["askId"] == "x1" and card["region"] == REGION and card["kind"] == "answer"
    assert "error" not in rig.types()  # never the bare error event the app can't tie to the circle


def test_a_failing_circle_ask_in_a_lesson_keeps_try_again_and_its_ink(rig, model, monkeypatch):
    from server.orchestrator import circle_ask

    async def boom(*a, **k):
        raise RuntimeError("emit failed")

    async def go():
        await rig.start_lesson()
        monkeypatch.setattr(circle_ask, "answer", boom)
        mark = rig.mark()
        await rig.s.action("ask", "", region=REGION, ask_id="x2", source="circle")
        await rig.settle()
        return mark

    since = run(go())
    [card] = [e["payload"] for e in rig.since(since) if e["type"] == "card"]
    assert card["askId"] == "x2" and card["region"] == REGION and card["stepId"] == rig.s.step["id"]
    assert "retry" in (card.get("actions") or [])
    assert rig.s._last_ask_region == (REGION, "x2")  # Try again asks about the same circle


def test_a_step_change_mid_answer_sends_a_short_card_with_the_ask_id(rig, monkeypatch):
    """The learner moved on while Haiku answered: no answer about the old step, but the ink gets its askId back."""
    async def slow(**kw):
        rig.s.step_gen += 1  # the learner changed step meanwhile
        return llm.CallResult(data={"title": "The Run button", "body": "Run starts your script.", "box_id": 1,
                                    "label": "Run"}, model="claude-haiku-5-5", latency_s=0.1)

    monkeypatch.setattr(llm, "structured_call_retrying", slow)

    async def go():
        await rig.start_lesson()
        mark = rig.mark()
        await rig.s.action("ask", "", region=REGION, ask_id="m1", source="circle")
        await rig.settle()
        return mark

    since = run(go())
    cards = [e["payload"] for e in rig.since(since) if e["type"] == "card"]
    [card] = [c for c in cards if c.get("askId") == "m1"]
    assert card["title"] == "We moved on" and "stepId" not in card and card["region"] == REGION
    assert not any(c.get("title") == "The Run button" for c in cards)
    assert not [e for e in rig.since(since) if e["type"] == "annotate"]


def test_a_circle_does_not_begin_a_lesson_held_by_before_you_start(rig, model, monkeypatch):
    begun: list = []

    async def go():
        await rig.start_lesson()
        rig.s._start_hold = rig.s.lesson_epoch  # "Before you start" is up
        assert rig.s.awaiting_start

        async def begin(why):
            begun.append(why)

        monkeypatch.setattr(rig.s, "_begin", begin)
        await rig.s.action("ask", "", region=REGION, ask_id="b1", source="circle")
        await rig.settle()
        await rig.s.action("hint")  # a real step control still begins it
        await rig.settle()

    run(go())
    assert begun == ["hint"]
    assert any(c.get("askId") == "b1" for c in rig.of("card"))


def test_a_circle_while_the_lesson_is_paused_still_answers(rig, model, screen):
    """VS Code closed (lesson.paused): the circle is still answered next to the ink, with the step as context, and
    the paused surface is not sent again."""
    async def go():
        await rig.start_lesson()
        rig.s.app_v2 = True
        await rig.s._pause("editor_closed")
        screen.pause("lesson paused")
        mark = rig.mark()
        await rig.s.action("ask", "what is this?", region=REGION, ask_id="p1", source="circle")
        await rig.settle()
        return mark

    since = run(go())
    assert rig.s.paused is not None
    evs = rig.since(since)
    [card] = [e["payload"] for e in evs if e["type"] == "card" and e["payload"].get("askId") == "p1"]
    assert card["title"] == "The Run button" and card["stepId"] == rig.s.step["id"]
    assert not [e for e in evs if e["type"] == "lesson.paused"]
    assert [e for e in evs if e["type"] == "annotate"]
    assert rig.s.step["title"] in model.calls[0]["user_text"]

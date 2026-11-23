"""Fast circle to ask through circle_ask.answer (Nov 22): the streamed path first, the one-shot card as the fallback.

Offline: Anthropic is an httpx2 MockTransport (server/coach/tests/test_fast_ask.py's fake), the screen is a FakeScreen
and the non-streaming coach is a fake model. The hub is strict, so every event is checked against the contract.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import uuid

import httpx2
import pytest

from server.coach import fast_ask as fa
from server.coach import llm
from server.coach.tests.test_fast_ask import Api, message, stream_reply
from server.orchestrator.modules import Modules
from server.orchestrator.screen_bridge import FakeScreen
from server.orchestrator.tests.test_circle_ask import OBS, REGION, FakeModel, _image
from server.orchestrator.tests.test_session import Rig

KEY = "sk-ant-test-fake-key"


@pytest.fixture
def screen():
    s = FakeScreen()
    s.ask = (OBS, _image())
    return s


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    fake = Api()
    monkeypatch.setattr(fa, "_transport", httpx2.MockTransport(fake))
    fa.reset()
    yield fake
    fa.reset()


@pytest.fixture
def rig(tmp_path, monkeypatch, screen, api):
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


def asked(rig, since: int = 0) -> list[tuple[str, dict]]:
    return [(e["type"], e["payload"]) for e in rig.since(since)
            if e["type"] in ("answer.delta", "answer.done", "card", "annotate")]


def test_words_stream_then_done_then_one_card(rig, api, model, screen):
    api.replies.append(stream_reply(["[DRAW:800,100,40:Run button]\n", "The Run button ", "starts your script."]))

    async def go():
        await rig.s.action("ask", "what is this", region=REGION, ask_id="f1", source="circle", release_t=None)
        await rig.settle()

    run(go())
    seq = asked(rig)
    assert [t for t, _ in seq] == ["annotate", "answer.delta", "answer.delta", "answer.done", "card"]
    done = seq[3][1]
    assert done == {"askId": "f1", "text": "The Run button starts your script.", "complete": True}
    card = seq[4][1]
    assert card["kind"] == "answer" and card["askId"] == "f1" and card["region"] == REGION
    assert card["title"] == "Run button" and card["body"] == done["text"]
    assert len(rig.of("annotate")) == 1  # the streamed mark only, no second one with the card
    assert model.calls == []  # the one-shot coach never ran
    assert screen.ask_displays == [REGION["displayId"]]  # no app capture: one capture at release (fast_region)
    body = api.bodies()[0]
    assert body["stream"] is True and body["model"] == "claude-haiku-5-5"
    assert body["messages"][-1]["content"][0]["type"] == "image"


def _capture_file(folder, data: bytes) -> str:
    os.makedirs(folder, mode=0o700, exist_ok=True)
    os.chmod(folder, 0o700)
    path = os.path.join(folder, f"cap-{os.getpid()}-{uuid.uuid4()}.jpg")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return path


def _jpeg(w: int, h: int) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), (230, 230, 225)).save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def test_the_apps_capture_is_used_and_nothing_is_captured_at_release(rig, api, model, screen, tmp_path, monkeypatch):
    from shared import capture_file

    folder = os.path.realpath(str(tmp_path / "miyagi-capture"))
    monkeypatch.setattr(capture_file, "capture_dirs", lambda: [folder])
    data = _jpeg(616, 176)
    path = _capture_file(folder, data)
    rect = {"x": 96.0, "y": 196.0, "w": 308.0, "h": 88.0}  # the box the helper really captured (margin added)
    cap = {"path": path, "w": 616, "h": 176, "rect": rect, "displayId": REGION["displayId"]}
    api.replies.append(stream_reply(["[DRAW:308,88,20:Run]\n", "That is the Run button."]))

    async def go():
        await rig.s.action("ask", "", region=REGION, ask_id="f2", source="circle", capture=cap, release_t=1.0)
        await rig.settle()

    run(go())
    assert getattr(screen, "ask_displays", []) == [] and not os.path.exists(path)  # read, deleted, no capture at release
    sent = api.bodies()[0]["messages"][-1]["content"][0]["source"]["data"]
    import base64

    assert base64.b64decode(sent) == data  # the helper's crop, as is
    assert "616 x 176 pixels" in api.bodies()[0]["messages"][-1]["content"][1]["text"]
    [ann] = rig.of("annotate")
    [mark] = ann["marks"]
    sx, sy, _r = capture_file.crop_to_screen(capture_file.Capture(data, 616, 176, tuple(rect.values()), 1), 308, 88, 20)
    assert mark["x"] + mark["w"] / 2 == pytest.approx(sx, abs=0.1) and mark["y"] + mark["h"] / 2 == pytest.approx(sy, abs=0.1)
    [card] = rig.of("card")
    assert card["askId"] == "f2" and card["body"] == "That is the Run button." and model.calls == []


def test_a_capture_that_fails_its_checks_falls_back_to_a_capture_at_release(rig, api, model, screen, tmp_path):
    outside = tmp_path / "elsewhere.jpg"
    outside.write_bytes(_jpeg(10, 10))
    cap = {"path": str(outside), "w": 10, "h": 10, "rect": {"x": 0, "y": 0, "w": 5, "h": 5}, "displayId": 1}
    api.replies.append(stream_reply(["[DRAW:none]\n", "A toolbar."]))

    async def go():
        await rig.s.action("ask", "", region=REGION, ask_id="f3", source="circle", capture=cap)
        await rig.settle()

    run(go())
    assert outside.exists()  # never read or deleted: not the helper's file
    assert screen.ask_displays == [REGION["displayId"]] and rig.of("card")[0]["body"] == "A toolbar."


def test_a_cloud_refusal_falls_back_to_the_one_shot_card(rig, api, model, monkeypatch):
    import server.config as cfg

    monkeypatch.setattr(cfg, "_app_cloud_url", "https://miyagi-cloud.onrender.com/v1")
    monkeypatch.setattr(cfg, "_app_keys", {"miyagiToken": "install-token-test"})
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    api.replies.append(httpx2.Response(429, json={"type": "error", "error": {
        "type": "rate_limit_error", "status": "RATE_LIMIT_ERROR", "code": 429, "message": "miyagi_quota"}}))

    async def go():
        await rig.s.action("ask", "", region=REGION, ask_id="f4", source="circle")
        await rig.settle()

    try:
        run(go())
    finally:
        cfg._clear_verdict()
    assert len(api.requests) == 1  # the streamed try, never retried
    assert [t for t, _ in asked(rig)] == ["card", "annotate"]  # nothing streamed: the one-shot card and its mark
    [card] = rig.of("card")
    assert card["title"] == "The Run button" and card["askId"] == "f4" and len(model.calls) == 1


def test_a_step_change_mid_stream_sends_moved_on(rig, api, model, monkeypatch):
    real = fa._emit

    async def emit(fn, type_, payload):
        ok = await real(fn, type_, payload)
        if type_ == "answer.delta":
            rig.s.step_gen += 1  # the learner changed step once the first words showed
        return ok

    monkeypatch.setattr(fa, "_emit", emit)
    api.replies.append(stream_reply(["[DRAW:none]\n", "The Run ", "button starts it."]))

    async def go():
        await rig.start_lesson()
        mark = rig.mark()
        await rig.s.action("ask", "", region=REGION, ask_id="f5", source="circle")
        await rig.settle()
        return mark

    since = run(go())
    seq = asked(rig, since)
    done = [p for t, p in seq if t == "answer.done"]
    assert done and done[0]["reason"] == "moved_on" and done[0]["complete"] is False
    cards = [p for t, p in seq if t == "card" and p.get("askId") == "f5"]
    assert [c["title"] for c in cards] == ["We moved on"] and model.calls == []
    assert [p["text"] for t, p in seq if t == "answer.delta"] == ["The Run "]  # the stream stopped there


def test_a_refusal_after_words_ends_in_a_failed_card(rig, api, model):
    api.replies.append(stream_reply(["[DRAW:none]\n", "This panel shows "], stop="refusal",
                                    model="claude-haiku-5-5"))

    async def go():
        await rig.s.action("ask", "", region=REGION, ask_id="f6", source="circle")
        await rig.settle()

    run(go())
    seq = asked(rig)
    assert [t for t, _ in seq] == ["answer.delta", "answer.done", "card"]
    assert seq[1][1] == {"askId": "f6", "text": "", "complete": False, "reason": "refusal"}
    card = seq[2][1]
    assert card["askId"] == "f6" and card["title"] == "I couldn't read that" and model.calls == []


def test_offline_still_deletes_the_apps_capture(rig, api, model, screen, tmp_path, monkeypatch):
    from shared import capture_file

    folder = os.path.realpath(str(tmp_path / "miyagi-capture"))
    monkeypatch.setattr(capture_file, "capture_dirs", lambda: [folder])
    path = _capture_file(folder, _jpeg(20, 10))
    monkeypatch.setenv("DEMO", "1")
    cap = {"path": path, "w": 20, "h": 10, "rect": {"x": 100, "y": 200, "w": 10, "h": 5}, "displayId": 1}

    async def go():
        await rig.s.action("ask", "", region=REGION, ask_id="f7", source="circle", capture=cap)
        await rig.settle()

    run(go())
    assert not os.path.exists(path) and api.requests == [] and len(rig.of("card")) == 1


def test_the_retry_path_still_answers_after_a_failed_stream(rig, api, model):
    """A stream that breaks before any word: one non-streaming retry answers (answer.done fallback: true)."""
    api.replies.append(httpx2.Response(529, json={"type": "error", "error": {"type": "overloaded_error",
                                                                             "message": "Overloaded"}}))
    api.replies.append(httpx2.Response(200, json=message("[DRAW:none]\nThe Run button.", model="claude-haiku-5-5")))

    async def go():
        await rig.s.action("ask", "", region=REGION, ask_id="f8", source="circle")
        await rig.settle()

    run(go())
    done = rig.of("answer.done")
    assert done == [{"askId": "f8", "text": "The Run button.", "complete": True, "fallback": True}]
    assert json.dumps(rig.of("card")[0]).count("The Run button.") == 1 and model.calls == []

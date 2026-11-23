"""Fast circle to ask through circle_ask.answer (Nov 22): the streamed path first, the one-shot card as the fallback.

Offline: Anthropic is an httpx2 MockTransport (server/coach/tests/test_fast_ask.py's fake), the screen is a FakeScreen
and the non-streaming coach is a fake model. The hub is strict, so every event is checked against the contract.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import time
import uuid

import httpx2
import pytest

from server.coach import fast_ask as fa
from server.coach import llm
from server.coach.tests.test_fast_ask import Api, message, stream_reply
from server.orchestrator import fast_region
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


class Vision:
    """The fake OCR and window list for the app's crop (fast_region._ocr / _windows): never Vision, never the real
    windows on this Mac. blocks / windows as the real ones' shape (text + rect, app + title + rect)."""

    def __init__(self) -> None:
        self.blocks: list = []
        self.windows: list = []
        self.calls: list = []
        self.fail: Exception | None = None

    def ocr(self, jpeg: bytes, rect: tuple, scale: float) -> list:
        self.calls.append((len(jpeg), rect, scale))
        if self.fail is not None:
            raise self.fail
        return list(self.blocks)

    def wins(self, rect: tuple) -> list:
        return list(self.windows)


@pytest.fixture(autouse=True)
def vision(monkeypatch):
    v = Vision()
    monkeypatch.setattr(fast_region, "_ocr", v.ocr)
    monkeypatch.setattr(fast_region, "_windows", v.wins)
    return v


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
        await rig.s.action("ask", "", region=REGION, ask_id="f2", source="circle", capture=cap,
                           release_t=time.monotonic())
        await rig.settle()

    run(go())
    assert getattr(screen, "ask_displays", []) == [] and not os.path.exists(path)  # read, deleted, no capture at release
    sent = api.bodies()[0]["messages"][-1]["content"][0]["source"]["data"]
    assert base64.b64decode(sent) == data  # read by OCR, nothing on it to hide: the helper's bytes
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


def test_a_cloud_refusal_sends_the_cloud_card_and_never_calls_again(rig, api, model, monkeypatch):
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
    assert [t for t, _ in asked(rig)] == ["card"]  # the cloud's own words, no one-shot call to be refused again
    [card] = rig.of("card")
    assert card["askId"] == "f4" and card["region"] == REGION and model.calls == []
    assert card["body"] == cfg.CLOUD_ERRORS["miyagi_quota"]


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


# ---------------------------------------------------------------------------------------------------- fix round 2

FAKE_KEY = "sk-ant-api03-" + "Zq7xW2vR9kLmP4tYb8NcD3fHj6gS1aE5uI0oQwXzVbN"
CAP_RECT = {"x": 96.0, "y": 196.0, "w": 300.0, "h": 80.0}  # 600 x 160 px: 2 px per point


def _app_capture(tmp_path, monkeypatch, w: int = 600, h: int = 160) -> tuple[dict, bytes]:
    from shared import capture_file

    folder = os.path.realpath(str(tmp_path / "miyagi-capture"))
    monkeypatch.setattr(capture_file, "capture_dirs", lambda: [folder])
    data = _jpeg(w, h)
    path = _capture_file(folder, data)
    return {"path": path, "w": w, "h": h, "rect": dict(CAP_RECT), "displayId": REGION["displayId"]}, data


def _sent(api) -> tuple[bytes, str]:
    content = api.bodies()[0]["messages"][-1]["content"]
    return base64.b64decode(content[0]["source"]["data"]), content[1]["text"]


def _px(jpeg: bytes, x: float, y: float) -> tuple[int, int, int]:
    """The sent picture's pixel at screen point (x, y) of the crop (2 px per point)."""
    from PIL import Image

    with Image.open(io.BytesIO(jpeg)) as im:
        return im.convert("RGB").getpixel((int((x - CAP_RECT["x"]) * 2), int((y - CAP_RECT["y"]) * 2)))


def test_a_secret_on_the_apps_crop_is_blacked_out_and_redacted(rig, api, model, screen, vision, tmp_path,
                                                                monkeypatch):
    """The helper's crop is the raw screen: an API key in it never reaches the request, in pixels or in text."""
    cap, data = _app_capture(tmp_path, monkeypatch)
    vision.blocks = [{"text": f"export ANTHROPIC_API_KEY={FAKE_KEY}", "rect": {"x": 110, "y": 210, "w": 220, "h": 12}},
                     {"text": "Run", "rect": {"x": 120, "y": 240, "w": 30, "h": 12}}]
    vision.windows = [{"app": "Code", "title": "main.py - lesson", "rect": {"x": 0, "y": 0, "w": 1512, "h": 982}}]
    api.replies.append(stream_reply(["[DRAW:none]\n", "That line sets a key."]))

    async def go():
        await rig.s.action("ask", "", region=REGION, ask_id="r1", source="circle", capture=cap,
                           release_t=time.monotonic())
        await rig.settle()

    run(go())
    assert vision.calls == [(len(data), (96.0, 196.0, 300.0, 80.0), 2.0)]  # OCR on the crop, its rect and scale
    assert getattr(screen, "ask_displays", []) == []  # the app's crop was used, no capture at release
    jpeg, text = _sent(api)
    assert jpeg != data  # encoded again, with the secret row blacked out
    assert all(c < 40 for c in _px(jpeg, 200, 216))  # inside the key's row: black
    assert all(c < 40 for c in _px(jpeg, 109, 209))  # just past its box (the 2 pt pad): black too
    assert all(c > 180 for c in _px(jpeg, 200, 262))  # below it, nothing hidden: the screen as it was
    assert FAKE_KEY not in text and "sk-ant-api03" not in text  # the OCR text is redacted
    assert "[secret]" in text and "Run" in text and "<untrusted" in text
    assert rig.of("card")[0]["body"] == "That line sets a key." and model.calls == []


def test_another_projects_window_on_the_apps_crop_is_greyed(rig, api, model, vision, tmp_path, monkeypatch):
    cap, _data = _app_capture(tmp_path, monkeypatch)
    folder = tmp_path / "calculator"
    folder.mkdir()
    monkeypatch.setattr(fast_region, "_lesson_folder", lambda _s: str(folder))
    vision.blocks = [{"text": "PRIVATE_NOTE", "rect": {"x": 110, "y": 210, "w": 80, "h": 12}}]
    vision.windows = [{"app": "Code", "title": "notes.py — other-project",
                       "rect": {"x": 96, "y": 196, "w": 150, "h": 80}},
                      {"app": "Code", "title": "calc.py — calculator",
                       "rect": {"x": 0, "y": 0, "w": 1512, "h": 982}}]
    api.replies.append(stream_reply(["[DRAW:none]\n", "Your editor."]))

    async def go():
        await rig.s.action("ask", "", region=REGION, ask_id="r2", source="circle", capture=cap,
                           release_t=time.monotonic())
        await rig.settle()

    run(go())
    jpeg, text = _sent(api)
    assert "PRIVATE_NOTE" not in text
    r, g, b = _px(jpeg, 120, 250)  # the other project's window: grey, not its pixels
    assert all(110 <= c <= 146 for c in (r, g, b))
    assert all(c > 180 for c in _px(jpeg, 350, 250))  # the lesson's own window: as it was


@pytest.mark.parametrize("why", ["no_ocr", "private_app"])
def test_no_ocr_or_a_private_app_falls_back_to_a_capture_at_release(rig, api, model, screen, vision, tmp_path,
                                                                     monkeypatch, why):
    cap, data = _app_capture(tmp_path, monkeypatch)
    if why == "no_ocr":
        vision.fail = RuntimeError("Vision OCR failed")
    else:
        vision.windows = [{"app": "1Password", "title": "Vault", "rect": {"x": 300, "y": 200, "w": 400, "h": 300}},
                          {"app": "Code", "title": "main.py", "rect": {"x": 0, "y": 0, "w": 1512, "h": 982}}]
    api.replies.append(stream_reply(["[DRAW:none]\n", "A toolbar."]))

    async def go():
        await rig.s.action("ask", "", region=REGION, ask_id="r3", source="circle", capture=cap,
                           release_t=time.monotonic())
        await rig.settle()

    run(go())
    assert not os.path.exists(cap["path"])  # still read and deleted
    assert screen.ask_displays == [REGION["displayId"]]  # the reader's frame (secrets, private apps left out)
    jpeg, _text = _sent(api)
    assert jpeg != data and rig.of("card")[0]["body"] == "A toolbar."


def test_a_refusal_with_no_words_never_makes_a_second_call(rig, api, model, screen):
    api.replies.append(stream_reply([], stop="refusal", model="claude-haiku-5-5"))

    async def go():
        await rig.s.action("ask", "", region=REGION, ask_id="r4", source="circle", release_t=time.monotonic())
        await rig.settle()

    run(go())
    assert len(api.requests) == 1 and model.calls == []  # no one-shot Haiku call to be refused again
    assert screen.ask_displays == [REGION["displayId"]]  # the one capture (frame_for), none more at release
    assert [t for t, _ in asked(rig)] == ["card"]
    card = rig.of("card")[0]
    assert card["askId"] == "r4" and card["title"] == "I couldn't read that"


def test_no_time_left_sends_the_failed_card_without_a_call(rig, api, model):
    """The action waited long (a queue, a slow capture): too little of the deadline is left to start anything."""
    from server.orchestrator import circle_ask

    async def go():
        await rig.s.action("ask", "", region=REGION, ask_id="r5", source="circle",
                           release_t=time.monotonic() - circle_ask.ASK_DEADLINE_S + 1.0)
        await rig.settle()

    run(go())
    assert api.requests == [] and model.calls == []
    [card] = rig.of("card")
    assert card["askId"] == "r5" and card["title"] == "I couldn't read that"


def test_the_one_shot_answer_is_cut_at_the_deadline(rig, api, model, monkeypatch):
    from server.orchestrator import circle_ask

    monkeypatch.setattr(circle_ask, "ASK_DEADLINE_S", 1.0)
    monkeypatch.setattr(circle_ask, "MIN_ONESHOT_S", 0.2)
    calls: list = []

    async def slow(**kw):
        calls.append(kw)
        await asyncio.sleep(30)

    monkeypatch.setattr(llm, "structured_call_retrying", slow)

    async def go():
        t0 = time.monotonic()
        await rig.s.action("ask", "", region=REGION, ask_id="r6", source="circle", release_t=t0)
        await rig.settle()
        return time.monotonic() - t0

    took = run(go())
    assert len(calls) == 1 and took < 3.0  # the one-shot started, and was cut at the deadline
    assert api.requests == []  # under MIN_STREAM_S left: the stream never started
    [card] = rig.of("card")
    assert card["askId"] == "r6" and card["title"] == "I couldn't read that"

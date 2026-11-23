"""Circle to ask, fast path, through the session: the app's capture, the streamed answer (answer.delta), the mark
from the [DRAW] line, the fallback to the non-streaming answer, the ask metrics and ask.warm. Offline: the SDK talks
to an httpx2 MockTransport (server/coach/tests/test_fast_ask.FakeAPI). The hub is strict, so every event here is
checked against shared/contracts/events.py."""

from __future__ import annotations

import asyncio
import io
import json
import os
import uuid

import pytest

from server.coach import fast_ask, llm
from server.coach.tests.test_fast_ask import FakeAPI, failing, streaming, text_events
from server.orchestrator import circle_ask
from server.orchestrator.modules import Modules
from server.orchestrator.screen_bridge import FakeScreen
from server.orchestrator.tests.test_circle_ask import OBS, REGION, FakeModel, _image
from server.orchestrator.tests.test_launch_contract import quiet_env  # noqa: F401 - a fixture
from server.orchestrator.tests.test_session import Rig


def jpeg(w: int, h: int) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), (250, 250, 250)).save(buf, format="JPEG", quality=80)
    return buf.getvalue()


@pytest.fixture
def screen():
    s = FakeScreen()
    s.ask = (OBS, _image())
    return s


@pytest.fixture
def rig(tmp_path, monkeypatch, screen):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    monkeypatch.delenv("DEMO", raising=False)
    monkeypatch.delenv("MIYAGI_FAST_ASK", raising=False)
    return Rig(tmp_path, modules=Modules(demo=False, force_stubs="lesson,finder,diagrams"), screen=screen)


@pytest.fixture
def api(monkeypatch):
    fake = FakeAPI(streaming(text_events(["[DRAW:none]\nHello."])))
    monkeypatch.setattr(llm, "get_client", lambda: fake.client)
    monkeypatch.setattr(llm, "has_credentials", lambda: True)
    monkeypatch.setattr(llm, "offline_mode", lambda: False)
    monkeypatch.setattr(llm, "record_cost", lambda *a, **k: 0.0)
    fast_ask.reset_warm()
    yield fake
    fast_ask.reset_warm()


@pytest.fixture
def model(monkeypatch):
    m = FakeModel({"title": "The Run button", "body": "Run starts your script. It runs the open file.",
                   "box_id": 1, "label": "Run button"})
    monkeypatch.setattr(llm, "structured_call_retrying", m)
    return m


@pytest.fixture
def capdir(tmp_path, monkeypatch):
    """The helper's folder: $TMPDIR/miyagi-capture (0700), as shared/capture_file.capture_dirs() finds it."""
    root = tmp_path / "tmp"
    d = root / "miyagi-capture"
    d.mkdir(parents=True)
    os.chmod(d, 0o700)
    monkeypatch.setenv("TMPDIR", str(root))
    monkeypatch.setattr("shared.capture_file.capture_dirs", lambda: [os.path.realpath(d)])
    return d


def write_capture(d, w: int = 600, h: int = 160) -> tuple[dict, bytes]:
    data = jpeg(w, h)
    p = d / f"cap-{uuid.uuid4()}.jpg"
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.chmod(p, 0o600)
    return {"path": str(p), "w": w, "h": h, "rect": {"x": 94.0, "y": 194.0, "w": 312.0, "h": 92.0},
            "displayId": REGION["displayId"]}, data


def run(coro):
    return asyncio.run(coro)


def circle(rig, text: str = "", ask_id: str = "q1", capture: dict | None = None):
    async def go():
        await rig.s.action("ask", text, region=dict(REGION), ask_id=ask_id, source="circle", capture=capture)
        await rig.settle()

    run(go())


def test_the_answer_streams_after_the_mark_and_the_card_carries_the_full_text(rig, api, model, screen):
    api.respond = streaming(text_events(["[DRAW:110,30,20:Run button]\n", "The Run button ", "starts your script.",
                                         " It runs the open file."], model="claude-sonnet-5-5"))
    circle(rig, "why is this button greyed out right now")
    types = [t for t in rig.types() if t in ("annotate", "answer.delta", "card")]
    assert types[0] == "annotate" and types[-1] == "card" and "answer.delta" in types
    deltas = rig.of("answer.delta")
    assert all(d["askId"] == "q1" for d in deltas) and deltas[-1]["done"] is True
    text = "".join(d["text"] for d in deltas)
    [card] = rig.of("card")
    assert card["body"] == text == "The Run button starts your script. It runs the open file."
    assert card["askId"] == "q1" and card["region"] == REGION and card["title"] == "Run button"
    [ann] = rig.of("annotate")  # one mark only: the card does not draw it again
    assert ann["marks"][0]["askId"] == "q1" and ann["marks"][0]["why"] == "answer"
    assert model.calls == []  # no non-streaming call
    assert screen.ask_displays == [REGION["displayId"]]  # no capture from the app: the engine took a frame


def test_the_apps_capture_is_used_and_no_frame_is_taken(rig, api, model, screen, capdir):
    cap, data = write_capture(capdir)
    api.respond = streaming(text_events(["[DRAW:none]\nThat is the import line."]))
    circle(rig, capture=cap)
    assert getattr(screen, "ask_displays", []) == []  # the engine's own capture is skipped
    import base64

    sent = api.requests[0]["messages"][0]["content"][0]
    assert sent["type"] == "image" and base64.b64decode(sent["source"]["data"]) == data
    assert not os.path.exists(cap["path"])  # read once, then deleted
    [card] = rig.of("card")
    assert card["body"] == "That is the import line." and rig.of("annotate") == []


def test_a_bad_capture_path_is_refused_and_the_engine_captures_as_before(rig, api, model, screen, capdir, tmp_path):
    outside = tmp_path / f"cap-{uuid.uuid4()}.jpg"  # the right name, the wrong folder
    outside.write_bytes(jpeg(600, 160))
    os.chmod(outside, 0o600)
    cap = {"path": str(outside), "w": 600, "h": 160, "rect": {"x": 94, "y": 194, "w": 312, "h": 92},
           "displayId": REGION["displayId"]}
    circle(rig, capture=cap)
    assert outside.exists()  # never touched: it is not the helper's file
    assert screen.ask_displays == [REGION["displayId"]]
    assert len(rig.of("card")) == 1


def test_a_stream_error_falls_back_to_the_non_streaming_answer(rig, api, model):
    api.respond = failing(500)
    circle(rig)
    [card] = rig.of("card")
    assert card["title"] == "The Run button" and card["askId"] == "q1" and len(model.calls) == 1
    assert rig.of("answer.delta") == []
    [ann] = rig.of("annotate")  # the fallback's own mark (its box id)
    assert ann["marks"][0]["askId"] == "q1"


def test_a_stream_that_breaks_after_the_mark_never_draws_a_second_one(rig, api, model):
    api.respond = streaming(text_events(["[DRAW:110,30,20:Run]\nThe Run", " button"], error=True))
    circle(rig)
    assert len(rig.of("annotate")) == 1  # the streamed one; the fallback card's mark is dropped
    [card] = rig.of("card")
    assert card["title"] == "The Run button" and len(model.calls) == 1  # its text replaces the streamed words


def test_the_capture_rides_into_the_fallback(rig, api, model, capdir):
    cap, data = write_capture(capdir)
    api.respond = failing(500)
    circle(rig, capture=cap)
    import base64

    content = model.calls[0]["user_content"]
    [img] = [b for b in content if b.get("type") == "image"]
    assert base64.b64decode(img["source"]["data"]) == data
    assert len(rig.of("card")) == 1


def test_a_slow_failure_answers_from_the_text_read_without_a_second_call(rig, api, model, monkeypatch):
    clock = iter([0.0, *[100.0] * 50])
    monkeypatch.setattr(circle_ask.AskTimer, "elapsed", lambda self: next(clock))
    api.respond = failing(500)
    circle(rig)
    [card] = rig.of("card")
    assert model.calls == [] and card["askId"] == "q1" and card["title"] == "Here's what I read"


def test_the_stream_is_skipped_when_turned_off(rig, api, model, monkeypatch):
    monkeypatch.setenv("MIYAGI_FAST_ASK", "0")
    circle(rig)
    assert api.requests == [] and len(model.calls) == 1


def test_ask_metrics_hold_timings_and_no_content(rig, api, model, caplog):
    api.respond = streaming(text_events(["[DRAW:none]\n", "Secret words here."]))
    with caplog.at_level("INFO", logger="orchestrator.circle_ask"):
        circle(rig, "what does this private thing say exactly")
    [line] = [r.getMessage() for r in caplog.records if r.getMessage().startswith("ask.metrics ")]
    rec = json.loads(line.split(" ", 1)[1])
    assert rec["outcome"] == "ok" and rec["route"] == "stream" and rec["model"]
    assert {"received", "picture", "first_byte", "first_text", "first_delta", "done", "card"} <= set(rec["marks"])
    assert "Secret" not in line and "private" not in line  # no words, no answer text
    from server.sessions import store

    path = store.state_dir() / circle_ask.METRICS_FILE
    assert json.loads(path.read_text().splitlines()[-1])["marks"]["card"] >= 0


def test_moved_on_while_streaming_sends_no_more_deltas(rig, api, model):
    async def go():
        await rig.start_lesson()
        gen = rig.s.step_gen

        async def bump(*a, **k):
            rig.s.step_gen = gen + 1  # the learner moved to another step while the answer streamed
            return await orig(*a, **k)

        orig = fast_ask.circle_stream
        rig.s.m.circle_stream_fn = lambda: bump
        mark = rig.mark()
        await rig.s.action("ask", "", region=dict(REGION), ask_id="q9", source="circle")
        await rig.settle()
        return mark

    api.respond = streaming(text_events(["[DRAW:110,30,20:Run]\nThe Run button."]))
    since = run(go())
    events = rig.since(since)
    assert not [e for e in events if e["type"] == "answer.delta"]
    assert not [e for e in events if e["type"] == "annotate"]
    [card] = [e["payload"] for e in events if e["type"] == "card" and e["payload"].get("askId") == "q9"]
    assert card["title"] == "We moved on"


# ---------------------------------------------------------------------------------------------------- ask.warm

def test_ask_warm_is_listed_instant_and_schedules_the_warmup(quiet_env, monkeypatch):  # noqa: F811
    from server.coach import fast_ask as fa
    from server.orchestrator import main

    eng = main.Engine()
    eng.recorder.enabled = False
    eng.session.m = eng.modules = Modules(demo=False, force_stubs="lesson,finder,diagrams")
    seen: list = []
    from server import coach

    monkeypatch.setattr(coach, "warm_ask", lambda: seen.append(1) or True)
    assert "ask.warm" in main.INSTANT and "ask.warm" in eng.capabilities()

    async def go():
        await eng.dispatch({"type": "ask.warm", "payload": {"pttId": "p1"}})
        await eng.dispatch({"type": "ask.warm"})

    run(go())
    assert seen == [1, 1]
    eng.session.m = Modules(demo=False, force_stubs="all")  # the coach stubbed: not offered, nothing sent
    assert "ask.warm" not in eng.capabilities() and eng.ask_warm() is False
    assert fa.WARM_EVERY_S == 240.0

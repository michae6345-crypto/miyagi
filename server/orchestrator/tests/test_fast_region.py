"""ask.region (fast circle to ask, Nov 22): the circled region is captured, cropped and encoded before release, into
an in-memory slot keyed by askId (server/orchestrator/fast_region.py). Offline: the capture is a fake frame."""

from __future__ import annotations

import asyncio
import io

import pytest

from server.coach import fast_ask
from server.orchestrator import fast_region as fr
from server.orchestrator.tests.test_launch_contract import _engine, quiet_env  # noqa: F401 - quiet_env: a fixture

ORIGIN = (-1440.0, 200.0)  # a second display left of the primary one
SCALE = 2.0
DOT = (-1300.0, 280.0)  # a red dot on screen (points)
SECRET = {"x": -1420.0, "y": 300.0, "w": 200.0, "h": 12.0}  # an OCR row that held a key


def picture():
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (900, 600), (235, 235, 230))  # 450 x 300 pt
    cx, cy = (DOT[0] - ORIGIN[0]) * SCALE, (DOT[1] - ORIGIN[1]) * SCALE
    ImageDraw.Draw(img).ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=(220, 0, 0))
    return img


def observation() -> dict:
    return {"blocks": [{"text": "Run", "rect": {"x": -1310.0, "y": 270.0, "w": 30.0, "h": 16.0}, "app": "Code"},
                       {"text": "OPENAI_KEY=[secret]", "rect": SECRET, "app": "Code"}],
            "windows": [], "scale": SCALE, "app": "Code",
            "screen": {"x": ORIGIN[0], "y": ORIGIN[1], "w": 450.0, "h": 300.0}}


REGION = {"x": -1430.0, "y": 240.0, "w": 200.0, "h": 90.0, "displayId": 7, "scale": 2.0}


class Session:
    step = None
    workdir = ""
    graph = None


@pytest.fixture
def cap(monkeypatch):
    calls: list = []

    async def capture(session, display_id, region=None):
        calls.append(display_id)
        return observation(), picture(), None

    monkeypatch.setattr(fr, "_capture", capture)
    fr.clear()
    yield calls
    fr.clear()


def red_centre(data: bytes) -> tuple[float, float]:
    from PIL import Image

    im = Image.open(io.BytesIO(data)).convert("RGB")
    pts = [(x, y) for y in range(im.height) for x in range(im.width)
           if (lambda p: p[0] > 150 and p[1] < 90 and p[2] < 90)(im.getpixel((x, y)))]
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def test_region_is_captured_before_release_and_taken_once(cap):
    async def flow():
        task = fr.remember_soon(Session(), "c1", REGION)
        assert task is not None
        await task  # the capture ran while the keys were still held
        first = await fr.take("c1", dict(REGION))
        second = await fr.take("c1", dict(REGION))  # dropped on use
        return first, second

    pre, again = asyncio.run(flow())
    assert cap == [7] and again is None and pre.reason is None
    jpeg, rect, w, h = pre.crop
    assert jpeg.startswith(b"\xff\xd8") and max(w, h) <= fast_ask.MAX_EDGE_PX
    # the rect is exactly what the JPEG shows: the dot found in the crop maps back to where it is on screen
    px, py = red_centre(jpeg)
    mark, _ = fast_ask.to_mark({"x": px, "y": py, "r": 10, "label": ""}, rect, w, h)
    assert (mark["x"] + mark["w"] / 2, mark["y"] + mark["h"] / 2) == pytest.approx(DOT, abs=1.0)
    assert pre.app == "Code"


def test_secret_rows_stay_black_in_the_slot_crop(cap):
    from PIL import Image

    async def flow():
        await fr.remember_soon(Session(), "c1", REGION)
        return await fr.take("c1", REGION)

    pre = asyncio.run(flow())
    jpeg, rect, _w, _h = pre.crop
    im = Image.open(io.BytesIO(jpeg)).convert("RGB")
    x, y = round((SECRET["x"] + 40 - rect["x"]) * SCALE), round((SECRET["y"] + 6 - rect["y"]) * SCALE)
    assert max(im.getpixel((x, y))) < 40


def test_a_moved_region_is_cropped_again_from_the_same_frame(cap):
    moved = {**REGION, "x": REGION["x"] + 20, "w": REGION["w"] - 20}

    async def flow():
        await fr.remember_soon(Session(), "c1", REGION)
        return await fr.take("c1", moved)

    pre = asyncio.run(flow())
    assert cap == [7] and pre.region["x"] == moved["x"]  # one capture only
    assert pre.crop[1]["x"] == pytest.approx(moved["x"] - fast_ask.CROP_MARGIN_PT, abs=0.5)


def test_another_display_an_unknown_ask_or_an_old_slot_gives_nothing(cap):
    t = [100.0]

    async def flow():
        await fr.remember_soon(Session(), "c1", REGION, clock=lambda: t[0])
        other = await fr.take("c1", {**REGION, "displayId": 8})
        await fr.remember_soon(Session(), "c2", REGION, clock=lambda: t[0])
        t[0] += fr.SLOT_TTL_S + 1
        old = await fr.take("c2", REGION, clock=lambda: t[0])
        unknown = await fr.take("nope", REGION)
        return other, old, unknown

    assert asyncio.run(flow()) == (None, None, None)


def test_a_slot_expires_by_itself_and_a_newer_region_replaces_it(cap, monkeypatch):
    monkeypatch.setattr(fr, "SLOT_TTL_S", 0.05)

    async def flow():
        fr.remember_soon(Session(), "c1", REGION)
        fr.remember_soon(Session(), "c1", {**REGION, "w": 150.0})  # the ink grew: one slot, the newest region
        assert list(fr._slots) == ["c1"]
        await asyncio.sleep(0.15)
        return dict(fr._slots)

    assert asyncio.run(flow()) == {}


def test_capture_reasons_and_no_capture(cap, monkeypatch):
    async def no_permission(session, display_id, region=None):
        return None, None, "no_permission"

    monkeypatch.setattr(fr, "_capture", no_permission)

    async def flow():
        await fr.remember_soon(Session(), "c1", REGION)
        return await fr.take("c1", REGION)

    pre = asyncio.run(flow())
    assert pre.reason == "no_permission" and pre.crop is None
    monkeypatch.setattr(fr, "_capture_fn", lambda: None)  # lane eng-circle-ask not merged: nothing to do

    async def none():
        return fr.remember_soon(Session(), "c1", REGION)

    assert asyncio.run(none()) is None
    assert fr.remember_soon(Session(), "c1", REGION) is None  # no running loop
    assert asyncio.run(fr.capture_and_crop(Session(), {"x": 0, "y": 0, "w": -5, "h": 1})) is None


def test_frame_for_takes_the_slot_else_captures_now(cap, monkeypatch):
    async def flow():
        await fr.remember_soon(Session(), "c1", REGION)
        slot = await fr.frame_for(Session(), "c1", REGION)  # from the slot: no second capture
        now = await fr.frame_for(Session(), "c2", REGION)  # no ask.region came: captured on release
        bad = await fr.frame_for(Session(), "c3", {"x": 1})
        return slot, now, bad

    slot, now, bad = asyncio.run(flow())
    assert cap == [7, 7] and slot.crop is not None and now.crop is not None and bad.reason == "no_frame"

    def broken(*a, **k):
        raise RuntimeError("PIL")

    monkeypatch.setattr(fr, "prepare", broken)  # no crop, but the frame still answers the non-streaming way
    pre = asyncio.run(fr.frame_for(Session(), "c4", REGION))
    assert pre.reason is None and pre.crop is None and pre.obs is not None
    monkeypatch.setattr(fr, "_capture_fn", lambda: None)
    assert asyncio.run(fr.frame_for(Session(), "c5", REGION)).reason == "no_screen"


def test_lesson_context_is_plain_strings():
    class S(Session):
        graph = {"lesson": {"title": "Train a PINN", "goal": "fit Burgers"}}

        def _memory_kw(self, step, purpose):
            return {"memory": "lr was 0.3"}

    ctx = fr.lesson_context(S(), {"id": "s1", "title": "Set lr", "instructions": "Use 1e-3"}, "lr = 0.3", "Code")
    assert ctx == {"screen_text": "lr = 0.3", "app": "Code", "lesson": "Train a PINN fit Burgers",
                   "step": "Set lr\nUse 1e-3", "memory": "lr was 0.3"}
    assert fr.lesson_context(Session(), None) == {"screen_text": "", "app": ""}


def test_ask_region_is_instant_and_starts_the_capture(quiet_env, monkeypatch):  # noqa: F811
    main, eng, _ws, _calls = _engine(monkeypatch)
    seen: list = []
    monkeypatch.setattr(fr, "remember_soon", lambda session, ask_id, region: seen.append((ask_id, region)))
    assert "ask.region" in main.INSTANT  # never queued behind a build or an answer

    async def go():
        await eng.dispatch({"type": "ask.region", "payload": {"askId": "c1", "region": REGION}})

    asyncio.run(go())
    assert seen == [("c1", REGION)]

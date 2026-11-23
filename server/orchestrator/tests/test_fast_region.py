"""Fast circle to ask, the fallback capture (server/orchestrator/fast_region.py): with no app capture on the ask, the
circled region is captured, cropped and encoded at release. Offline: the capture is a fake frame."""

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
    yield calls


def red_centre(data: bytes) -> tuple[float, float]:
    from PIL import Image

    im = Image.open(io.BytesIO(data)).convert("RGB")
    pts = [(x, y) for y in range(im.height) for x in range(im.width)
           if (lambda p: p[0] > 150 and p[1] < 90 and p[2] < 90)(im.getpixel((x, y)))]
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def test_frame_for_captures_crops_and_maps_back_to_the_screen(cap):
    pre = asyncio.run(fr.frame_for(Session(), "c1", REGION))
    assert cap == [7] and pre.reason is None
    jpeg, rect, w, h = pre.crop
    assert jpeg.startswith(b"\xff\xd8") and max(w, h) <= fast_ask.MAX_EDGE_PX
    # the rect is exactly what the JPEG shows: the dot found in the crop maps back to where it is on screen
    px, py = red_centre(jpeg)
    mark, _ = fast_ask.to_mark({"x": px, "y": py, "r": 10, "label": ""}, rect, w, h)
    assert (mark["x"] + mark["w"] / 2, mark["y"] + mark["h"] / 2) == pytest.approx(DOT, abs=1.0)
    assert pre.app == "Code"


def test_secret_rows_stay_black_in_the_crop(cap):
    from PIL import Image

    pre = asyncio.run(fr.frame_for(Session(), "c1", REGION))
    jpeg, rect, _w, _h = pre.crop
    im = Image.open(io.BytesIO(jpeg)).convert("RGB")
    x, y = round((SECRET["x"] + 40 - rect["x"]) * SCALE), round((SECRET["y"] + 6 - rect["y"]) * SCALE)
    assert max(im.getpixel((x, y))) < 40


def test_capture_reasons_and_no_capture(cap, monkeypatch):
    async def no_permission(session, display_id, region=None):
        return None, None, "no_permission"

    monkeypatch.setattr(fr, "_capture", no_permission)
    pre = asyncio.run(fr.frame_for(Session(), "c1", REGION))
    assert pre.reason == "no_permission" and pre.crop is None
    assert asyncio.run(fr.capture_and_crop(Session(), {"x": 0, "y": 0, "w": -5, "h": 1})) is None
    assert asyncio.run(fr.frame_for(Session(), "c3", {"x": 1})).reason == "no_frame"


def test_frame_for_without_a_crop_still_has_the_frame(cap, monkeypatch):
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


def test_ask_region_is_not_a_command(quiet_env, monkeypatch):  # noqa: F811
    """Dropped for the native capture (action ask capture): one capture path while the keys are held."""
    main, _eng, _ws, _calls = _engine(monkeypatch)
    from shared.contracts import events

    assert "ask.region" not in main.INSTANT and "ask.region" not in events.APP_COMMANDS
    assert not hasattr(fr, "remember_soon")

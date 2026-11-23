"""ScreenReader.capture_once (circle to ask, Nov 22): one frame for one ask, on the display the learner circled on.

It must publish nothing (no subscriber, no metric reader), keep the reader's own frame / display key / blank streak /
error state, and never hand back an older picture. Offline: a fake ScreenCaptureKit returns a fixture PNG, OCR is
faked, nothing touches the real screen.
"""
import os
import sys
import time

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="pyobjc capture is macOS-only")

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "vscode_fullscreen_top.png")
MAIN, SIDE = 1, 2  # SIDE sits left of and above the main display


class FakeSCK:
    excluded_apps = ()
    overlay_apps = ("miyagi",)

    def __init__(self, fail_for=()):
        self.calls, self.fail_for = [], set(fail_for)

    def capture(self, display_id=None):
        from server.screen import macos
        from server.screen.types import Rect

        self.calls.append(display_id)
        if display_id in self.fail_for:
            raise RuntimeError("display gone")
        img = macos.load_cgimage(FIXTURE, cache=True)
        screen = Rect(-1728, -300, 1728, 1117) if display_id == SIDE else Rect(0, 0, 1728, 1117)
        return img, screen, 2.0


@pytest.fixture
def reader(monkeypatch):
    from server.screen import macos
    from server.screen.reader import ScreenReader
    from server.screen.types import Block, Rect

    monkeypatch.setattr(macos, "has_permission", lambda: True)
    monkeypatch.setattr(macos, "list_windows", lambda *a, **k: [])
    monkeypatch.setattr(macos, "active_displays", lambda: [(MAIN, Rect(0, 0, 1728, 1117)),
                                                           (SIDE, Rect(-1728, -300, 1728, 1117))])
    monkeypatch.setattr(macos, "target_display_id", lambda: MAIN)  # the focused window is on the main display
    monkeypatch.setattr(macos, "ocr_image", lambda img, screen, scale: (
        [Block("def pde_residual(x):", Rect(screen.x + 100, screen.y + 100, 300, 20), 1.0)], 5.0))
    monkeypatch.delenv("TUT_SCREEN_FIXTURE", raising=False)
    monkeypatch.delenv("DEMO", raising=False)
    r = ScreenReader(use_ax=False, use_events=False)
    r._sck = FakeSCK()
    monkeypatch.setattr(r, "_attach_cursor_and_ax", lambda obs: None)
    return r


def test_the_circled_display_is_captured_and_nothing_is_published(reader):
    from server.screen.types import Rect

    seen, fed = [], []

    class Metric:
        def feed(self, obs):
            fed.append(obs)

    reader.subscribe(lambda obs: seen.append(obs))
    reader._metric_readers.append(Metric())
    before = object()
    reader._latest, reader._latest_image, reader._screen_key = None, before, (0, 0, 1728, 1117)
    frame, streak = reader._frame, reader._blank_streak

    obs, pil = reader.capture_once(SIDE, "ask")

    assert reader._sck.calls == [SIDE]  # display B, although the focused window is on A
    assert obs.screen == Rect(-1728, -300, 1728, 1117) and obs.source == "live" and obs.trigger == "ask"
    assert [b.text for b in obs.blocks] == ["def pde_residual(x):"]
    assert pil is not None and pil.size == (3456, 2234)
    assert seen == [] and fed == []  # no on_screen (screen.seen / checks / spotlight), no metric reader
    assert reader._latest is None and reader._latest_image is before  # the reader's own frame is untouched
    assert reader._screen_key == (0, 0, 1728, 1117)  # no display_changed reset for the lesson's reader
    assert reader._frame == frame and reader._blank_streak == streak and reader.last_error is None


def test_a_display_that_is_not_active_falls_back_to_the_usual_one(reader):
    obs, _ = reader.capture_once(424242)
    assert reader._sck.calls == [MAIN] and obs.screen.x == 0


def test_a_display_that_cannot_be_captured_falls_back_to_the_usual_one(reader, monkeypatch):
    real = reader._grab

    def grab(display_id=None):
        if display_id == SIDE:
            raise RuntimeError("that display can't be captured")
        return real(display_id)

    monkeypatch.setattr(reader, "_grab", grab)
    obs, pil = reader.capture_once(SIDE)
    assert reader._sck.calls == [MAIN] and obs.screen.x == 0 and pil is not None


def test_no_display_id_reads_the_usual_display(reader):
    reader.capture_once(None)
    assert reader._sck.calls == [MAIN]


def test_a_blank_frame_returns_nothing_not_an_older_picture(reader, monkeypatch):
    from server.screen import health

    monkeypatch.setattr(health, "blank_kind", lambda thumb: "black")
    old_obs, old_img = object(), object()
    reader._latest, reader._latest_image = old_obs, old_img  # a frame left over from a lesson that has ended
    assert reader.capture_once(SIDE) == (None, None)
    assert reader._latest is old_obs and reader._latest_image is old_img and reader._blank_streak == 0


def test_no_screen_recording_raises_and_leaves_the_error_state_alone(reader, monkeypatch):
    from server.screen import macos
    from server.screen.types import ScreenPermissionError

    monkeypatch.setattr(macos, "has_permission", lambda: False)
    monkeypatch.setattr(reader, "_permission_warned", True)  # no help text on stderr
    with pytest.raises(ScreenPermissionError):
        reader.capture_once(SIDE)
    assert reader.last_error is None


def test_the_overlay_is_blacked_out_in_the_picture(reader):
    reader.set_overlay_bounds([{"x": -1728, "y": -300, "w": 100, "h": 50}])
    _, pil = reader.capture_once(SIDE)
    assert sum(pil.getpixel((20, 20))[:3]) == 0  # the overlay's corner on display B (its pixel 0, 0)


def test_observe_now_still_publishes_after_the_refactor(reader):
    seen = []
    reader.subscribe(lambda obs: seen.append(obs))
    obs = reader.observe_now(force=True)
    assert seen == [obs] and reader._latest is obs and reader._frame == 1
    assert [b.text for b in obs.blocks] == ["def pde_residual(x):"] and time.time() - obs.t < 5

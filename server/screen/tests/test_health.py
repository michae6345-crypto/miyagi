"""Black / blank / stale frame detection, display change and wake recovery, resume honesty (fake frames, offline)."""
import sys
import types

import pytest

from server.screen import health
from server.screen.types import Rect

mac = pytest.mark.skipif(sys.platform != "darwin", reason="macOS capture")
N = 64 * 64


def test_blank_thumb_detection():
    assert health.is_blank_thumb(bytes(N))                      # all black
    assert health.is_blank_thumb(bytes([200]) * N)              # one flat colour
    assert not health.is_blank_thumb(bytes([10, 200] * (N // 2)))
    assert not health.is_blank_thumb(None)


def test_display_changed():
    a = (0.0, 0.0, 1440.0, 900.0)
    assert not health.display_changed(None, a)
    assert not health.display_changed(a, a)
    assert health.display_changed(a, (0.0, 0.0, 1920.0, 1080.0))


def test_permission_hint_names_the_python_binary():
    assert sys.executable.split("/")[-1][:6] in health.permission_hint() or "python" in health.permission_hint()


def _reader(monkeypatch, thumbs, screens=None):
    from server.screen import macos
    from server.screen.reader import ScreenReader
    r = ScreenReader(use_ax=False, use_events=False)
    r.fixture = None
    seq, scr = iter(thumbs), iter(screens or [])
    default = Rect(0, 0, 1440, 900)
    monkeypatch.setattr(r, "_grab", lambda: (object(), next(scr, default), 2.0, [], None, "live", True))
    monkeypatch.setattr(macos, "thumbnail", lambda img: next(seq))
    monkeypatch.setattr(macos, "ocr_image", lambda img, screen, scale: ([], 1.0))
    monkeypatch.setattr(macos, "frontmost_app", lambda w: "Code")
    return r


GOOD = bytes([10, 200] * (N // 2))


@mac
def test_blank_frames_are_reported_after_a_streak_then_recover(monkeypatch):
    r = _reader(monkeypatch, [bytes(N)] * 3 + [GOOD])
    assert r.observe_now() is None and r.last_error is None     # one black frame: a transition, no error yet
    assert r.observe_now() is None
    with pytest.raises(Exception, match="blank frame"):
        r.observe_now()
    assert r.status == "error" and "blank" in r.last_error and r.latest() is None
    obs = r.observe_now()                                        # pixels are back
    assert obs is not None and r.last_error is None and r.status == "ok"


@mac
def test_display_change_resets_capture_state_and_forces_ocr(monkeypatch):
    r = _reader(monkeypatch, [GOOD, GOOD, GOOD], [Rect(0, 0, 1440, 900), Rect(0, 0, 1440, 900), Rect(0, 0, 1920, 1080)])
    assert r.observe_now(force=True) is not None
    assert r.observe_now(force=False) is None                    # unchanged screen: no OCR
    r._sck = types.SimpleNamespace(_filter="stale")
    assert r.observe_now(force=False) is not None                # resolution switched: forced
    assert r._sck._filter is None


@mac
def test_reset_capture_clears_sck_backoff(monkeypatch):
    r = _reader(monkeypatch, [GOOD])
    r._sck = types.SimpleNamespace(_filter="x")
    r._sck_retry_at, r._sck_streak, r._prev_thumb = 1e12, 4, b"old"
    r.reset_capture("wake")
    assert r._sck_retry_at == 0.0 and r._sck_streak == 0 and r._prev_thumb is None and r._sck._filter is None


@mac
def test_bridge_stays_paused_when_resume_cannot_start_the_reader(monkeypatch):
    from server.orchestrator.screen_bridge import ScreenBridge
    b = ScreenBridge.__new__(ScreenBridge)
    import threading
    b._pause_lock, b._fresh_after, b._on_front, b._loop = threading.Lock(), 0.0, None, None
    b.paused = True

    class Dead:
        events = None
        ax_reader = None
        _thread = None
        _stop = threading.Event()
        thread_alive = False
        status = "ok"
        def start(self):
            raise RuntimeError("boom")
    b.reader = Dead()
    b.resume("test")
    assert b.paused is True
    b.paused = False
    assert b.down_reason() == "capture thread stopped"

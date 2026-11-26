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


def test_permission_hint_names_the_python_binary(monkeypatch):
    monkeypatch.delenv(health.BUNDLED_ENV, raising=False)  # a dev engine started from a shell
    assert health.engine_binary() in health.permission_hint()


BUNDLED = "/Applications/miyagi.app/Contents/Resources/python/bin/python3.12"


def _hints() -> dict[str, str]:
    from server.orchestrator.session import LessonSession as Session
    from server.screen import types as screen_types

    return {"permission_hint": health.permission_hint(), "accessibility_hint": health.accessibility_hint(),
            "permission_help": screen_types.permission_help(), "error": str(screen_types.ScreenPermissionError()),
            **{f"toast {r}": Session.screen_down_message(r) for r in ("no_permission", "no_accessibility", "other")}}


def test_inside_miyagi_app_the_hints_name_miyagi_not_python_or_terminal(monkeypatch):
    """MIYAGI_BUNDLED_PYTHON (the app's localEngine.ts): macOS lists the grant under miyagi, so that is what to turn on."""
    monkeypatch.setenv(health.BUNDLED_ENV, BUNDLED)
    for name, text in _hints().items():
        assert "miyagi" in text and "System Settings" in text, name
        assert "python3" not in text.lower() and "Terminal" not in text and "iTerm" not in text, (name, text)
        assert "Miyagi" not in text and "—" not in text, name  # lowercase miyagi, no em dash


def test_a_dev_engine_still_says_which_program_needs_the_grant(monkeypatch):
    monkeypatch.delenv(health.BUNDLED_ENV, raising=False)
    hints = _hints()
    assert health.engine_binary() in hints["permission_hint"] and "Terminal" in hints["permission_help"]
    assert all("Miyagi" not in t for t in hints.values())


@mac
def test_inside_miyagi_app_the_accessibility_help_names_miyagi(monkeypatch):
    from server.screen import ax

    monkeypatch.setenv(health.BUNDLED_ENV, BUNDLED)
    text = ax.ax_help()
    assert "turn on miyagi" in text and "Terminal" not in text and "python3" not in text
    monkeypatch.delenv(health.BUNDLED_ENV)
    assert "Terminal" in ax.ax_help()


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
    b.paused, b.started = True, False

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


# ---- multi-display, AX revocation, flat frames, wake gap (all offline: fake displays / fake clocks)

@pytest.mark.skipif(sys.platform != "darwin", reason="imports server.screen.macos (pyobjc): macOS only")
def test_pick_display_prefers_the_window_then_the_cursor_then_main():
    from server.screen import macos
    left, right = (1, Rect(0, 0, 1440, 900)), (2, Rect(1440, 0, 1920, 1080))
    both = [left, right]
    assert macos.pick_display(both, Rect(1600, 100, 800, 600)) == 2                      # window on the second monitor
    assert macos.pick_display(both, Rect(1300, 100, 400, 400)) == 2                      # straddles: 140 px left, 260 right
    assert macos.pick_display(both, Rect(1000, 100, 800, 400)) == 1                      # 440 px on left, 360 on right
    assert macos.pick_display(both, None, (1500.0, 50.0)) == 2                           # no window: the cursor
    assert macos.pick_display(both, Rect(9000, 9000, 100, 100), None, main_id=1) == 1    # off every display: main
    assert macos.pick_display([], Rect(0, 0, 1, 1)) is None


@mac
def test_overlay_mask_lands_on_the_second_displays_pixels(monkeypatch):
    from server.screen import macos
    from server.screen.reader import _mask_thumb
    screen = Rect(1440, 0, 1920, 1080)                      # second display, global origin (1440, 0)
    flat = bytes([200]) * (macos.THUMB_W * macos.THUMB_H)
    out = _mask_thumb(flat, [Rect(1440 + 960, 540, 192, 108)], screen)   # a box at the display's centre (global coords)
    sx, sy = macos.THUMB_W / 1920, macos.THUMB_H / 1080
    x0, y0 = int(960 * sx), int(540 * sy)
    assert out[(y0 + 2) * macos.THUMB_W + x0 + 2] == 0     # masked at display-local pixels
    assert out[2 * macos.THUMB_W + 2] == 200               # untouched elsewhere
    assert _mask_thumb(flat, [Rect(0, 0, 400, 400)], screen) == flat  # a box on the OTHER display masks nothing


@mac
def test_grab_captures_the_display_holding_the_window(monkeypatch):
    from server.screen import macos
    from server.screen.reader import ScreenReader
    displays = [(1, Rect(0, 0, 1440, 900)), (2, Rect(1440, 0, 1920, 1080))]
    monkeypatch.setattr(macos, "has_permission", lambda: True)
    monkeypatch.setattr(macos, "active_displays", lambda: displays)
    monkeypatch.setattr(macos, "frontmost_window", lambda: {"rect": {"x": 1600.0, "y": 100.0, "w": 900.0, "h": 700.0}})
    monkeypatch.setattr(macos.Quartz, "CGMainDisplayID", lambda: 1)
    monkeypatch.setattr(macos.Quartz, "CGEventCreate", lambda x: None)
    monkeypatch.setattr(macos.Quartz, "CGEventGetLocation", lambda e: types.SimpleNamespace(x=10.0, y=10.0))
    assert macos.target_display_id() == 2                   # the cursor is on display 1, the VS Code window on 2
    seen = {}
    r = ScreenReader(use_ax=False, use_events=False)
    r.fixture, r.use_sck = None, True
    img, scr = object(), displays[1][1]

    def fake_sck(display_id=None):
        seen["id"] = display_id
        return img, scr, 2.0, set()

    monkeypatch.setattr(r, "_sck_capture", fake_sck)
    monkeypatch.setattr(macos, "list_windows", lambda screen: [])
    out = r._grab()
    assert seen["id"] == 2 and out[1] == scr


def test_accessibility_revocation_is_reported_apart_from_screen_recording():
    from server.orchestrator.screen_bridge import ScreenBridge
    from server.orchestrator.session import LessonSession as Session
    from server.screen.reader import ScreenReader
    trusted = {"v": True}
    r = ScreenReader(use_ax=False, use_events=False)
    r._ax_check = lambda: trusted["v"]
    r._thread = types.SimpleNamespace(is_alive=lambda: True)
    assert r.check_accessibility() is True and r.ax_trusted is True
    b = ScreenBridge.__new__(ScreenBridge)
    b.reader, b.paused = r, False
    assert b.down_reason() is None
    trusted["v"] = False
    assert r.check_accessibility() is False
    assert b.down_reason() == "no_accessibility"            # reported ...
    assert b.down_reason(include_ax=False) is None          # ... but the OCR path is not paused
    assert r.status in ("idle", "ok") and r.last_error is None
    r.last_error = "no_permission: x"
    assert b.down_reason() == "no_permission"               # Screen Recording stays its own reason
    r.last_error = None
    trusted["v"] = True
    r.check_accessibility()
    assert b.down_reason() is None
    msg = Session.screen_down_message("no_accessibility")
    assert "Accessibility" in msg and "Screen Recording" not in msg


@mac
def test_missing_ax_binding_is_unavailable_not_revoked(monkeypatch, caplog):
    """A venv without pyobjc-framework-ApplicationServices: AX is off (warned once), never reported as a revoked
    Accessibility grant, and frames still get their cursor context (OCR keeps working)."""
    import logging

    from server.screen import ax
    monkeypatch.setattr(ax, "AX", None)
    with pytest.raises(ax.AXUnavailable):
        ax.trusted()
    r = _reader(monkeypatch, [GOOD])
    r.use_ax = True
    with caplog.at_level(logging.WARNING, logger="server.screen"):
        r._start_sensors()
    assert r.ax_reader is None and any("AX reader unavailable" in m for m in caplog.messages)
    assert r.check_accessibility() is None and r.ax_trusted is None        # unknown, not "REVOKED"
    obs = r.observe_now(force=True)
    assert obs is not None and r.status == "ok" and obs.cursor is not None and obs.ax is None


def test_session_words_a_blank_frame_as_blank_not_as_a_permission_problem():
    from server.orchestrator.session import LessonSession as Session
    msg = Session.screen_down_message("ScreenUnavailableError: blank frame (one flat colour): the screen shows no content")
    assert "blank" in msg and "Screen Recording" not in msg


@mac
def test_a_flat_non_black_screen_needs_a_much_longer_streak_than_a_black_one(monkeypatch):
    flat = bytes([128]) * N
    r = _reader(monkeypatch, [flat] * (health.FLAT_STREAK + 1))
    for _ in range(health.FLAT_STREAK - 1):                 # a solid-colour slide: no error for many frames
        assert r.observe_now() is None and r.last_error is None
    with pytest.raises(Exception, match="blank frame"):
        r.observe_now()
    assert "Screen Recording" not in r.last_error


@mac
def test_run_loop_resets_capture_after_a_sleep_gap(monkeypatch):
    from server.screen.reader import ScreenReader
    import server.screen.reader as rd
    r = ScreenReader(use_ax=False, use_events=False)
    r.fixture, r.debounce = None, 0.0
    calls = []
    monkeypatch.setattr(r, "reset_capture", lambda why="": calls.append(why))
    monkeypatch.setattr(r, "observe_now", lambda force=True, trigger="": r._stop.set())
    monkeypatch.setattr(r, "check_accessibility", lambda: None)
    r.interval = 0.01
    r._last_tick = 1000.0
    monkeypatch.setattr(rd.time, "time", lambda: 1000.0 + 3600)   # the Mac slept for an hour
    r._run()
    assert calls == ["wake"]
    calls.clear()
    r._stop.clear()
    r._last_tick = 1000.0 + 3600 - 1.0                            # a normal 1 s gap: no reset
    r._run()
    assert calls == []


@mac
def test_reset_capture_waits_for_an_in_flight_capture(monkeypatch):
    import threading
    r = _reader(monkeypatch, [GOOD])
    r._sck = types.SimpleNamespace(_filter="x")
    done = threading.Event()
    with r._capture_lock:                                         # observe_now is mid-capture
        t = threading.Thread(target=lambda: (r.reset_capture("wake"), done.set()))
        t.start()
        assert not done.wait(0.2) and r._sck._filter == "x"       # blocked: the filter isn't pulled from under it
    assert done.wait(2) and r._sck._filter is None

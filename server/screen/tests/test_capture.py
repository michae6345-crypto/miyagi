"""Capture backends: ScreenCaptureKit -> screencapture -> CG, and recovering from SCK stalls.

On macOS 26, replayd (the daemon behind ScreenCaptureKit) can drop our connection in a loop: no
SCK completion handler fires, and CGDisplayCreateImage (built on SCK) blocks 5 s and returns nil,
while Apple's `screencapture` keeps working. The reader must keep producing frames through that.
Offline and hermetic (fake frames; neither the ScreenCaptureKit binding nor Screen Recording is needed) unless marked
`live_display`: those capture the real screen and run only with SCREEN_ALLOW_LIVE=1 (local only, no network, no models).
"""
import logging
import os
import sys
import tempfile
import time

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="pyobjc capture is macOS-only")


def _reader():
    from server.screen.reader import ScreenReader
    return ScreenReader(use_ax=False, use_events=False)


class StalledSCK:
    excluded_apps = ()
    calls = 0

    def capture(self, display_id=None):
        from server.screen.sck import SCKStalled
        StalledSCK.calls += 1
        raise SCKStalled("SCShareableContent gave no answer in 1.5 s")


def _fake_frame(*_a, **_k):
    from server.screen import macos
    from server.screen.types import Rect
    img = macos.load_cgimage(os.path.join(os.path.dirname(__file__), "..", "fixtures", "vscode_fullscreen_top.png"),
                             cache=True)
    return macos.Frame(img, Rect(0, 0, 1728, 1117), 2.0, time.time())


@pytest.fixture
def no_windows(monkeypatch):
    from server.screen import macos
    monkeypatch.setattr(macos, "list_windows", lambda *a, **k: [])
    monkeypatch.setattr(macos, "has_permission", lambda: True)
    monkeypatch.setattr(macos, "target_display_id", lambda: None)   # not this Mac's window layout


def test_sck_stall_falls_back_to_screencapture_in_the_same_frame(monkeypatch, no_windows):
    from server.screen import macos
    monkeypatch.setattr(macos, "capture_main_display_cli", _fake_frame)
    monkeypatch.setattr(macos, "capture_main_display", lambda *a, **k: pytest.fail("CG must not be needed"))
    r = _reader()
    r._sck = StalledSCK()
    img, _screen, _scale, _windows, _app, source, excluded = r._grab()
    assert img is not None and source == "live" and r.backend == "cli"
    assert excluded is False            # overlay is in the pixels: observe_now masks its text


def test_observation_records_backend_and_masks_overlay(monkeypatch, no_windows):
    from server.screen import macos
    monkeypatch.setattr(macos, "capture_main_display_cli", _fake_frame)
    r = _reader()
    r._sck = StalledSCK()
    r.set_overlay_bounds([{"x": 0, "y": 0, "w": 1728, "h": 300}])
    obs = r.observe_now(force=True)
    assert obs.capture == "cli" and not obs.overlay_excluded and r.status == "ok"
    assert all(b.rect.cy > 300 for b in obs.blocks)     # overlay region dropped
    assert any("pde" in b.text or "def" in b.text for b in obs.blocks)


def test_sck_backoff_doubles_and_logs_once_per_streak(monkeypatch, caplog):
    r = _reader()
    r._sck = StalledSCK()
    StalledSCK.calls = 0
    delays = []
    with caplog.at_level(logging.WARNING, logger="server.screen"):
        for _ in range(4):
            r._sck_retry_at = 0.0          # pretend the wait elapsed
            assert r._sck_capture() is None
            delays.append(round(r._sck_retry_at - time.time()))
    assert delays == [10, 20, 40, 80]
    assert StalledSCK.calls == 4
    assert r._sck_capture() is None and StalledSCK.calls == 4   # inside the window: SCK not touched
    assert sum("ScreenCaptureKit failed" in m for m in caplog.messages) == 1
    r._sck_streak = 20
    r._sck_retry_at = 0.0
    r._sck_capture()
    assert r._sck_retry_at - time.time() <= 300.5               # capped at 5 min


def test_sck_recovery_resets_backoff(monkeypatch):
    r = _reader()
    r._sck_streak, r._sck_retry_at = 3, 0.0

    class OK:
        excluded_apps = ("Electron",)

        def capture(self, display_id=None):
            return object(), None, 2.0

    r._sck = OK()
    assert r._sck_capture() is not None and r._sck_streak == 0 and r._sck_retry_at == 0.0


def test_no_screencapture_binary_uses_cg(monkeypatch, no_windows):
    from server.screen import macos

    def missing(*a, **k):
        raise FileNotFoundError(macos.SCREENCAPTURE)
    monkeypatch.setattr(macos, "capture_main_display_cli", missing)
    monkeypatch.setattr(macos, "capture_main_display", _fake_frame)
    r = _reader()
    r.use_sck = False
    r._grab()
    assert r.backend == "cg"


def test_tut_capture_cg_forces_the_old_path(monkeypatch, no_windows):
    from server.screen import macos
    monkeypatch.setenv("TUT_CAPTURE", "cg")
    monkeypatch.setattr(macos, "capture_main_display_cli", lambda *a, **k: pytest.fail("cli must be skipped"))
    monkeypatch.setattr(macos, "capture_main_display", _fake_frame)
    r = _reader()
    assert not r.use_sck
    r._grab()
    assert r.backend == "cg"


def test_both_paths_failing_is_unavailable_not_permission(monkeypatch, no_windows):
    from server.screen import macos

    def down(*a, **k):
        raise macos.ScreenUnavailableError("screencapture failed (exit 1): no image")
    monkeypatch.setattr(macos, "capture_main_display_cli", down)
    r = _reader()
    r._sck = StalledSCK()
    with pytest.raises(macos.ScreenUnavailableError):
        r.observe_now(force=True)
    assert r.status == "error" and "ScreenUnavailableError" in r.last_error


def test_sck_retries_once_on_a_stale_filter_but_not_on_a_stall():
    from server.screen.sck import SCKCapturer, SCKStalled
    c = SCKCapturer.__new__(SCKCapturer)
    c._filter = "stale"
    seen = []

    def once_bad(*_a):
        seen.append(c._filter)
        if len(seen) == 1:
            raise RuntimeError("ScreenCaptureKit capture failed: window list changed")
        return "img", None, 2.0
    c._capture_once = once_bad
    assert c.capture() == ("img", None, 2.0) and seen == ["stale", None]   # refreshed, then OK

    def stalled(*_a):
        seen.append("stall")
        raise SCKStalled("no answer")
    c._capture_once = stalled
    seen.clear()
    with pytest.raises(SCKStalled):
        c.capture()
    assert seen == ["stall"]


def test_interrupted_shareable_content_is_not_a_permission_error(monkeypatch):
    """replayd interrupting our connection makes SCShareableContent call back with no content;
    that used to be reported as `no_permission`."""
    from types import SimpleNamespace

    from server.screen import sck
    from server.screen.types import ScreenPermissionError

    class FakeContent:
        @staticmethod
        def getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_(_d, _o, handler):
            handler(None, None)
    monkeypatch.setattr(sck, "SCK", SimpleNamespace(SCShareableContent=FakeContent))
    monkeypatch.setattr(sck.Quartz, "CGPreflightScreenCaptureAccess", lambda: True)
    c = sck.SCKCapturer()
    with pytest.raises(RuntimeError) as ei:
        c._refresh()
    assert not isinstance(ei.value, ScreenPermissionError)


# ---------------------------------------------------------------------- local capture check

def test_screencapture_backend_live(live_display):
    from server.screen import macos
    before = set(os.listdir(tempfile.gettempdir()))
    f = macos.capture_main_display_cli()
    assert f.scale >= 1 and f.screen.w > 0
    import Quartz
    assert Quartz.CGImageGetWidth(f.image) == round(f.screen.w * f.scale)
    leftovers = {n for n in set(os.listdir(tempfile.gettempdir())) - before if n.startswith("miyagi-screen-")}
    assert not leftovers                 # the screenshot temp file never outlives the call


class _SCKOutcome:
    """A stand-in SCKCapturer that does one of the things the real one does."""
    excluded_apps = ("Electron",)
    overlay_apps = ("Electron",)

    def __init__(self, outcome):
        self.outcome = outcome

    def capture(self, display_id=None):
        from server.screen import sck
        if self.outcome == "works":
            f = _fake_frame()
            return f.image, f.screen, f.scale
        raise {"stalled": sck.SCKStalled("SCShareableContent gave no answer in 1.5 s"),
               "declined": sck.SCKDeclined("The user declined TCCs (-3801)"),
               "failed": RuntimeError("ScreenCaptureKit capture failed: window list changed")}[self.outcome]


@pytest.mark.parametrize("outcome", ["works", "stalled", "declined", "failed", "no_binding"])
def test_reader_produces_live_frames_whatever_sck_does(monkeypatch, no_windows, outcome):
    from server.screen import macos, sck
    monkeypatch.setattr(macos, "capture_main_display_cli", _fake_frame)
    monkeypatch.setattr(macos, "capture_main_display", lambda *a, **k: pytest.fail("screencapture works: no CG"))
    if outcome == "no_binding":                      # a venv without pyobjc-framework-ScreenCaptureKit
        monkeypatch.setattr(sck, "SCK", None)
    r = _reader()
    if outcome != "no_binding":
        r._sck = _SCKOutcome(outcome)
    obs = r.observe_now(force=True)
    assert obs is not None and obs.source == "live" and r.status == "ok"
    assert obs.capture == ("sck" if outcome == "works" else "cli")
    assert any("def" in b.text for b in obs.blocks)
    assert r.use_sck is (outcome != "no_binding")  # a stall, decline or failure is temporary; only no binding is final


def test_missing_sck_binding_falls_back_for_good_and_says_so_once(monkeypatch, no_windows, caplog):
    """No ScreenCaptureKit binding is permanent: no 10 s / 20 s ... retries, one clear warning, frames keep coming."""
    from server.screen import macos, sck
    monkeypatch.setattr(sck, "SCK", None)
    with pytest.raises(sck.SCKUnavailable):
        sck.SCKCapturer()
    monkeypatch.setattr(macos, "capture_main_display_cli", _fake_frame)
    r = _reader()
    with caplog.at_level(logging.WARNING, logger="server.screen"):
        for _ in range(3):
            img, *_rest, source, _excluded = r._grab()
            assert img is not None and source == "live" and r.backend == "cli"
    assert r.use_sck is False and r._sck is None and r._sck_streak == 0 and r._sck_retry_at == 0.0
    assert sum("ScreenCaptureKit unavailable" in m for m in caplog.messages) == 1
    assert not any("ScreenCaptureKit failed" in m for m in caplog.messages)


def test_reader_produces_live_frames_live(live_display):
    r = _reader()
    obs = r.observe_now(force=True)
    assert obs is not None and obs.source == "live" and obs.capture in ("sck", "cli")
    assert r.status == "ok"

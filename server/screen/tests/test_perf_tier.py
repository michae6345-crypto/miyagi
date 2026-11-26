"""Low-end Mac perf (MacBook Neo, 8 GB): tier detection, adaptive AX rate, idle capture backoff, the thumbnail diff.
Offline and hermetic: no capture, no AX, no model."""
import os
import random
import sys
import threading
import time

import pytest

from server.screen import perf_tier as P

GB = 1024 ** 3


@pytest.fixture(autouse=True)
def _no_power_probe(monkeypatch):
    monkeypatch.setenv("MIYAGI_PERF_SAVING", "0")   # never spawn pmset in tests


def test_tier_low_for_8gb_or_two_perf_cores():
    assert P.profile_for(8 * GB, 4).tier == "low"          # 8 GB M1 / M2 Air
    assert P.profile_for(16 * GB, 2).tier == "low"         # A-series (2 P cores)
    assert P.profile_for(16 * GB, 4).tier == "normal"
    assert P.profile_for(None, None).tier == "normal"      # unknown: as before
    low = P.profile_for(8 * GB, 2)
    assert low.ax_hz == 5 and low.ax_idle_hz == 1 and "8 GB RAM" in low.reason and "2 performance cores" in low.reason


def test_tier_override():
    assert P.profile_for(64 * GB, 12, "low").tier == "low"
    assert P.profile_for(8 * GB, 2, "normal").tier == "normal"
    assert P.profile_for(8 * GB, 2, "auto").tier == "low"


def test_idle_heartbeat_backs_off_and_caps():
    assert P.idle_heartbeat(5.0, 0, False, 8.0) == 5.0
    assert P.idle_heartbeat(5.0, 2, False, 8.0) == 5.0
    assert P.idle_heartbeat(5.0, 3, False, 8.0) == 7.5
    assert P.idle_heartbeat(5.0, 50, False, 8.0) == 8.0
    assert P.idle_heartbeat(5.0, 0, True, 10.0) == 7.5        # power saving
    assert P.idle_heartbeat(5.0, 50, True, 3.0) == 5.0        # a cap under base: never faster than base


def test_ax_period_active_idle_and_saving():
    normal, low = P.profile_for(16 * GB, 4), P.profile_for(8 * GB, 2)
    assert P.ax_period(normal, 0.0) == pytest.approx(0.1)
    assert P.ax_period(normal, P.AX_IDLE_AFTER_S) == pytest.approx(0.5)
    assert P.ax_period(low, 0.0) == pytest.approx(0.2)
    assert P.ax_period(low, 10.0) == pytest.approx(1.0)
    assert P.ax_period(normal, 0.0, saving=True) == pytest.approx(0.2)


def test_changed_matches_the_python_loop():
    from server.screen.reader import _changed, _changed_py
    rnd = random.Random(7)
    base = bytes(rnd.randrange(256) for _ in range(432 * 280))
    assert _changed(None, base, 3) and not _changed(base, base, 3)
    for moved in (1, 2, 3, 4, 40):
        for delta in (5, 12, 13, 200):
            b = bytearray(base)
            for i in rnd.sample(range(len(b)), moved):
                b[i] = (b[i] + delta) % 256 if b[i] + delta < 256 else max(0, b[i] - delta)
            b = bytes(b)
            assert _changed(base, b, 3) == _changed_py(base, b, 3), (moved, delta)


@pytest.mark.skipif(sys.platform != "darwin", reason="ax.py imports AppKit")
def test_ax_reader_slows_down_when_nothing_changes_and_snaps_back():
    from server.screen.ax import AXReader, AXSnapshot
    r = AXReader(profile=P.profile_for(16 * GB, 4))
    snap = AXSnapshot(t=0, app="Code", bundle_id="com.microsoft.VSCode", pid=1, document="/a.py", mouse=(10, 10))
    t = 1000.0
    r._step(lambda: snap, t)
    assert r.next_period(t) == pytest.approx(0.1)                       # just changed: 10 Hz
    r._step(lambda: snap, t + 1)
    assert r.next_period(t + P.AX_IDLE_AFTER_S + 0.1) == pytest.approx(0.5)  # nothing for 3 s: 2 Hz
    moved = AXSnapshot(t=0, app="Code", bundle_id="com.microsoft.VSCode", pid=1, document="/a.py", mouse=(11, 10))
    r._step(lambda: moved, t + 5)
    assert r.next_period(t + 5) == pytest.approx(0.1)                   # the pointer moved: back to 10 Hz


@pytest.mark.skipif(sys.platform != "darwin", reason="ax.py imports AppKit")
def test_ax_reader_keeps_full_rate_while_a_typing_pause_is_pending():
    from server.screen.ax import AXReader, AXSnapshot, EditorState
    r = AXReader(profile=P.profile_for(8 * GB, 2))
    ed = lambda text: EditorState(text, 1, 0, 0, 1, None, None)
    a = AXSnapshot(t=0, app="Code", bundle_id=None, pid=1, editor=ed("x"))
    b = AXSnapshot(t=0, app="Code", bundle_id=None, pid=1, editor=ed("xy"))
    r._step(lambda: a, 0.0)
    r._step(lambda: b, 0.1)                                              # typed: a pause is pending
    assert r.next_period(100.0) == pytest.approx(r.period)              # even long after: fire it on time
    assert r.period == pytest.approx(0.2)                               # low tier active rate


@pytest.mark.skipif(sys.platform != "darwin", reason="ax.py imports AppKit")
def test_element_under_a_still_pointer_is_read_once_per_ttl(monkeypatch):
    from server.screen import ax
    monkeypatch.setattr(ax, "_under_cache", (0.0, None, None))
    reads = []
    read = lambda x, y: reads.append((x, y)) or f"el@{x},{y}"
    assert ax._under_mouse((5, 5), now=100.0, read=read) == "el@5,5"
    assert ax._under_mouse((5, 5), now=100.5, read=read) == "el@5,5"
    assert len(reads) == 1
    ax._under_mouse((5, 5), now=100.0 + ax.UNDER_MOUSE_TTL_S + 0.01, read=read)
    ax._under_mouse((6, 5), now=101.2, read=read)                       # moved: read at once
    assert len(reads) == 3
    ax._under_mouse((6, 5), now=101.3, read=read, pid=42)               # another app under a still pointer
    assert len(reads) == 4


@pytest.mark.skipif(sys.platform != "darwin", reason="reader imports Quartz")
def test_reader_heartbeat_backs_off_on_an_unchanged_screen(monkeypatch):
    from server.screen.reader import ScreenReader
    r = ScreenReader(use_ax=False, use_events=False)
    r.profile = P.profile_for(16 * GB, 4)
    assert r.next_wait() == r.interval
    r._unchanged = 10
    assert r.next_wait() == pytest.approx(2 * r.interval)               # no event taps: at most 2x

    class Ev:
        available = True
    r.events = Ev()
    assert r.next_wait() == pytest.approx(r.profile.idle_heartbeat_max)
    r._unchanged = 0
    assert r.next_wait() == r.heartbeat_with_events
    r.events = None


def test_battery_saves_only_on_a_low_tier_mac():
    assert P.saving_rule(low_power_mode=True, on_battery=False, low_tier=False)
    assert not P.saving_rule(low_power_mode=False, on_battery=True, low_tier=False)
    assert P.saving_rule(low_power_mode=False, on_battery=True, low_tier=True)
    assert not P.saving_rule(low_power_mode=False, on_battery=False, low_tier=True)


def test_power_state_is_read_once_per_ttl_across_threads(monkeypatch):
    monkeypatch.delenv("MIYAGI_PERF_SAVING", raising=False)
    monkeypatch.setattr(P.sys, "platform", "darwin")
    monkeypatch.setattr(P, "_power", (-1e18, False, False))
    calls = []

    def battery():
        calls.append(1)
        time.sleep(0.05)            # a slow pmset: every thread arrives while it runs
        return True
    monkeypatch.setattr(P, "_on_battery", battery)
    monkeypatch.setattr(P, "_low_power_mode", lambda: False)
    out = []
    ts = [threading.Thread(target=lambda: out.append(P.power_saving(now=1000.0, low=True))) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(calls) == 1 and out == [True] * 8
    assert P.power_saving(now=1000.0 + P.SAVING_TTL_S - 1, low=False) is False   # cached; normal Mac on battery
    assert len(calls) == 1


def _ax_snap(**kw):
    from server.screen.ax import AXSnapshot
    return AXSnapshot(t=time.time(), app="Code", bundle_id="com.microsoft.VSCode", pid=1, **kw)


@pytest.mark.skipif(sys.platform != "darwin", reason="ax.py imports AppKit")
def test_kick_wakes_an_idle_ax_reader_at_once(monkeypatch):
    from server.screen import ax
    reads = []
    monkeypatch.setattr(ax, "snapshot", lambda: reads.append(time.time()) or _ax_snap(mouse=(1, 1)))
    r = ax.AXReader(profile=P.profile_for(8 * GB, 2))          # low tier: idle = 1 Hz
    r._thread = threading.Thread(target=r._run, daemon=True)
    r._thread.start()
    try:
        deadline = time.time() + 2
        while len(reads) < 2 and time.time() < deadline:          # first read, then one more: now idle
            time.sleep(0.01)
        r._active_at = 0.0                                        # nothing changed for long: the 1 s idle wait
        time.sleep(0.05)
        n, t0 = len(reads), time.time()
        r.kick()
        while len(reads) == n and time.time() - t0 < 1.0:
            time.sleep(0.002)
        assert len(reads) > n and reads[n] - t0 < 0.05            # read within ~50 ms, not at the 1 s tick
        snap = r.wait_fresh(time.time(), timeout=0.3)
        assert snap is not None and snap.t >= t0
    finally:
        r.stop()


@pytest.mark.skipif(sys.platform != "darwin", reason="reader imports Quartz")
def test_check_frame_never_pairs_with_ax_older_than_its_capture(monkeypatch):
    from server.screen import ax, macos
    from server.screen.reader import ScreenReader
    from server.screen.types import Rect
    img = macos.load_cgimage(os.path.join(os.path.dirname(__file__), "..", "fixtures", "vscode_fullscreen_top.png"),
                             cache=True)
    monkeypatch.setattr(macos, "list_windows", lambda *a, **k: [])
    monkeypatch.setattr(macos, "has_permission", lambda: True)
    monkeypatch.setattr(macos, "target_display_id", lambda: None)
    monkeypatch.setattr(macos, "capture_main_display_cli",
                        lambda *a, **k: macos.Frame(img, Rect(0, 0, 1728, 1117), 2.0, time.time()))
    monkeypatch.setattr(macos, "ocr_image", lambda *a, **k: ([], 1.0))
    r = ScreenReader(use_ax=False, use_events=False)
    r.use_sck = False
    seen = []
    monkeypatch.setattr(r, "cursor_context", lambda obs, snap=None: seen.append(snap) or {"x": 0, "y": 0})
    monkeypatch.setattr(r, "_ax_shown", lambda snap, obs: True)

    # an AX reader with only an old snapshot and no thread to read a new one (stalled): the check goes without AX
    stalled = ax.AXReader(profile=P.profile_for(16 * GB, 4))
    stalled.available = True
    stalled._latest = _ax_snap()
    stalled._latest.t -= 0.5                                       # < 2 s old: the latest frame would have used it
    r.ax_reader = stalled
    t0 = time.time()
    r.observe_now(force=True, trigger="check")
    assert seen[-1] is None and time.time() - t0 < 1.0

    # a live reader: the check waits for a snapshot read after the capture and uses that one
    monkeypatch.setattr(ax, "snapshot", lambda: _ax_snap())
    live = ax.AXReader(profile=P.profile_for(8 * GB, 2))
    live.available = True
    live._latest = stalled._latest
    live._thread = threading.Thread(target=live._run, daemon=True)
    r.ax_reader = live
    try:
        live._thread.start()
        time.sleep(0.05)
        live._active_at = 0.0                                      # idling at 1 Hz
        time.sleep(0.05)
        before = time.time()
        r.observe_now(force=True, trigger="check")
        assert seen[-1] is not None and seen[-1].t >= before - 0.001 and seen[-1] is not stalled._latest
        assert r._last_capture <= seen[-1].t
    finally:
        live.stop()


@pytest.mark.skipif(sys.platform != "darwin", reason="reader imports Quartz")
def test_reoccing_an_identical_frame_keeps_the_backoff(monkeypatch):
    from server.screen import macos
    from server.screen.reader import ScreenReader
    from server.screen.types import Rect
    img = macos.load_cgimage(os.path.join(os.path.dirname(__file__), "..", "fixtures", "vscode_fullscreen_top.png"),
                             cache=True)
    monkeypatch.setattr(macos, "list_windows", lambda *a, **k: [])
    monkeypatch.setattr(macos, "has_permission", lambda: True)
    monkeypatch.setattr(macos, "target_display_id", lambda: None)
    monkeypatch.setattr(macos, "capture_main_display_cli",
                        lambda *a, **k: macos.Frame(img, Rect(0, 0, 1728, 1117), 2.0, time.time()))
    monkeypatch.setattr(macos, "ocr_image", lambda *a, **k: ([], 1.0))
    r = ScreenReader(use_ax=False, use_events=False)
    r.use_sck = False
    assert r.observe_now(force=False, trigger="tick") is not None   # first frame
    for _ in range(4):
        assert r.observe_now(force=False, trigger="tick") is None   # unchanged
    assert r._unchanged == 4
    r.max_age = 0.0                                                  # stale: re-OCR'd, but the same picture
    assert r.observe_now(force=False, trigger="tick") is not None
    assert r._unchanged == 4

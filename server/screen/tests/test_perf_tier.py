"""Low-end Mac perf (MacBook Neo, 8 GB): tier detection, adaptive AX rate, idle capture backoff, the thumbnail diff.
Offline and hermetic: no capture, no AX, no model."""
import random
import sys

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

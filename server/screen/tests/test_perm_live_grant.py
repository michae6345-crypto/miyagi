"""Permission matrix, engine side (PR #286 for #282): a grant made while the engine runs must take effect without a
restart where macOS allows it. Accessibility: AXIsProcessTrusted() is read live, so the AX worker that gave up at
start must come back once the grant lands. No OS call is made: ax.trusted() and the worker are fakes."""
from __future__ import annotations

import types

from server.screen.reader import ScreenReader


class FakeAX:
    """Stands in for ax.AXReader: start() reads the (fake) grant once, like the real one."""

    def __init__(self, grant: dict):
        self.grant = grant
        self.available = False
        self.starts = 0
        self.cbs: list = []

    def start(self):
        self.starts += 1
        self.available = bool(self.grant["v"])
        return self

    def on_change(self, cb):
        self.cbs.append(cb)


def _reader(grant: dict) -> ScreenReader:
    r = ScreenReader(use_ax=False, use_events=False)
    r._ax_check = lambda: grant["v"]
    r._thread = types.SimpleNamespace(is_alive=lambda: True)
    return r


def test_ax_granted_after_engine_start_starts_the_ax_worker():
    grant = {"v": False}
    r = _reader(grant)
    r.ax_reader = FakeAX(grant).start()          # engine started before the grant: the worker gave up
    assert r.ax_reader.available is False
    assert r.check_accessibility() is False and r.ax_reader.starts == 1   # still off: no restart attempt
    grant["v"] = True                             # the user flips the switch in System Settings
    assert r.check_accessibility() is True
    assert r.ax_reader.available is True and r.ax_reader.starts == 2
    assert r.ax_reader.cbs == [r._on_ax_change]   # wired to capture pokes, once


def test_running_ax_worker_is_not_restarted_on_every_check():
    grant = {"v": True}
    r = _reader(grant)
    r.ax_reader = FakeAX(grant).start()
    for _ in range(5):
        r.check_accessibility()
    assert r.ax_reader.starts == 1 and r.ax_reader.cbs == []


def test_no_ax_worker_no_crash():
    """use_ax off, or pyobjc ApplicationServices missing: nothing to revive."""
    r = _reader({"v": True})
    r.ax_reader = None
    assert r.check_accessibility() is True


def test_worker_that_still_cannot_start_is_harmless():
    """AXIsProcessTrusted() says yes but the worker's own check still says no (a stale TCC row after an ad-hoc
    re-sign can do this on some builds): no exception, no callback, tried again on the next check."""
    grant = {"v": True}
    r = _reader(grant)
    ax = FakeAX({"v": False}).start()
    r.ax_reader = ax
    assert r.check_accessibility() is True
    assert ax.available is False and ax.cbs == [] and ax.starts == 2
    r.check_accessibility()
    assert ax.starts == 3


def test_worker_start_raising_is_logged_not_raised(caplog):
    grant = {"v": True}
    r = _reader(grant)
    ax = FakeAX({"v": False}).start()

    def boom():
        raise RuntimeError("AX API unavailable")

    ax.start = boom
    r.ax_reader = ax
    import logging
    with caplog.at_level(logging.WARNING, logger="server.screen"):
        assert r.check_accessibility() is True
    assert any("AX reader restart failed" in m for m in caplog.messages)

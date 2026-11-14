"""No-fake rule, error reporting, BYOK key status, Tiger retry/backoff."""
import asyncio
import sys

import pytest

from server.screen.describe import DescribeError, Describer
from server.screen.metrics import TigerWriter

mac = pytest.mark.skipif(sys.platform != "darwin", reason="macOS capture")


@mac
def test_no_permission_raises_and_never_uses_fixture(monkeypatch):
    from server.screen import ScreenPermissionError, macos
    from server.screen.reader import ScreenReader
    monkeypatch.delenv("DEMO", raising=False)
    monkeypatch.delenv("TUT_SCREEN_FIXTURE", raising=False)
    monkeypatch.setattr(macos, "has_permission", lambda: False)
    r = ScreenReader()
    events = []
    r.on_error(events.append)
    with pytest.raises(ScreenPermissionError):
        r.observe_now()
    with pytest.raises(ScreenPermissionError):
        r.observe_now()
    assert r.latest() is None and r.fixture is None
    assert r.status == "no_permission" and "Screen Recording" in r.last_error
    assert len(events) == 1 and isinstance(events[0], ScreenPermissionError)  # transitions only
    with pytest.raises(DescribeError) as ei:
        asyncio.run(r.describe("what is on screen?"))
    assert ei.value.reason == "no_image"
    # permission granted -> recovers, on_error(None)
    monkeypatch.setattr(macos, "has_permission", lambda: True)
    obs = r.observe_now()
    assert obs.source == "live" and r.last_error is None and events[-1] is None


@mac
def test_demo_mode_replays_fixture_and_labels_it(monkeypatch):
    from server.screen import macos
    from server.screen.reader import ScreenReader
    monkeypatch.setenv("DEMO", "1")
    monkeypatch.delenv("TUT_SCREEN_FIXTURE", raising=False)
    monkeypatch.setattr(macos, "has_permission", lambda: False)
    obs = ScreenReader().observe_now()
    assert obs.source.startswith("fixture:") and obs.blocks


def test_describe_errors_instead_of_fake_answers(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    d = Describer()
    assert d.key_status == "missing"
    with pytest.raises(DescribeError) as ei:
        asyncio.run(d.describe(b"jpeg", "q", ("q",)))
    assert ei.value.reason == "missing_key"
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    assert d.key_status == "env"
    d.set_key("from-app")
    assert d.key_status == "ok"
    d.set_key(None)
    assert d.key_status == "env"


def test_tiger_status_states(monkeypatch):
    monkeypatch.delenv("TIGER_DATABASE_URL", raising=False)
    assert TigerWriter().status == "missing"
    assert TigerWriter("postgres://...").status == "invalid"
    monkeypatch.setenv("TIGER_DATABASE_URL", "postgres://u:p@db.example.com:5432/tsdb")
    w = TigerWriter()
    assert w.status == "env"
    w.set_url("postgres://u:p@other.example.com:5432/tsdb")
    assert w.status == "ok"


def test_tiger_retries_with_backoff_and_keeps_points():
    w = TigerWriter("postgresql://u:p@127.0.0.1:1/x?connect_timeout=1")  # nothing listens on :1
    w.write("screen-t", [("loss", 1, 0.5), ("loss", 2, 0.4)])
    assert not w.flush(timeout=2.5)            # can't write...
    assert w.pending == 2                       # ...but nothing is dropped
    assert w._failures >= 1 and w.status == "invalid" and w.last_error
    assert w._next_try > 0                      # backing off

"""Screen tests are offline and hermetic: fake frames, no real capture. The few `live_display` / `live_sck` tests
capture THIS Mac's real screen, so they run only on purpose: SCREEN_ALLOW_LIVE=1 (and Screen Recording granted)."""
import functools
import os
import sys

import pytest


def _live_allowed() -> bool:
    return os.environ.get("SCREEN_ALLOW_LIVE") == "1"


@functools.cache
def _display_available() -> bool:
    """Can we get a live frame at all? Uses `screencapture` (the path that keeps working when replayd
    stalls ScreenCaptureKit and CGDisplayCreateImage). Never called unless SCREEN_ALLOW_LIVE=1: it captures."""
    if sys.platform != "darwin":
        return False
    from server.screen import macos
    if not macos.has_permission():
        return False
    try:
        macos.capture_main_display_cli()
        return True
    except Exception:  # noqa: BLE001
        return False


@functools.cache
def _sck_available() -> bool:
    if not _display_available():
        return False
    try:
        from server.screen.sck import SCKCapturer
        SCKCapturer().capture()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture
def live_display():
    """Live capture of the real screen: only with SCREEN_ALLOW_LIVE=1. Then skip (don't fail) when the display gives
    no image right now: asleep, locked, no permission."""
    if not _live_allowed():
        pytest.skip("captures the real screen: set SCREEN_ALLOW_LIVE=1 to run")
    if not _display_available():
        pytest.skip("live display unavailable right now (asleep / locked / no permission)")


@pytest.fixture
def live_sck(live_display):
    """Skip when ScreenCaptureKit itself is stalled right now (replayd), even though capture works."""
    if not _sck_available():
        pytest.skip("ScreenCaptureKit not answering right now (replayd stalled)")

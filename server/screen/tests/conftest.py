import functools
import sys

import pytest


@functools.cache
def _display_available() -> bool:
    """Can we get a live frame at all? Uses `screencapture` (the path that keeps working when replayd
    stalls ScreenCaptureKit and CGDisplayCreateImage)."""
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
    """Skip (don't fail) when the display gives no image right now: asleep, locked, no permission."""
    if not _display_available():
        pytest.skip("live display unavailable right now (asleep / locked / no permission)")


@pytest.fixture
def live_sck(live_display):
    """Skip when ScreenCaptureKit itself is stalled right now (replayd), even though capture works."""
    if not _sck_available():
        pytest.skip("ScreenCaptureKit not answering right now (replayd stalled)")

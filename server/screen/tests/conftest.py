import sys

import pytest


def _display_available() -> bool:
    if sys.platform != "darwin":
        return False
    import Quartz
    return Quartz.CGPreflightScreenCaptureAccess() and Quartz.CGDisplayCreateImage(Quartz.CGMainDisplayID()) is not None


@pytest.fixture
def live_display():
    """Skip (don't fail) when the display gives no image right now: asleep, screen saver, locked."""
    if not _display_available():
        pytest.skip("live display unavailable right now (asleep / screen saver / locked / no permission)")

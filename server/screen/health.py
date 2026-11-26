"""Pure helpers for telling a healthy frame from a dead one (black / blank), and for saying which binary needs the
Screen Recording grant. No macOS imports: importable and testable anywhere."""
from __future__ import annotations

import os
import sys

BLANK_MAX_LEVEL = 6      # a gray thumbnail whose brightest pixel is this dark is a black frame
BLANK_MAX_SPREAD = 2     # ... or one flat colour (max - min), e.g. a lock-screen blank or a cleared buffer
BLANK_STREAK = 3         # consecutive blank frames before the reader calls the capture broken
FLAT_STREAK = 10         # ... for a flat but NOT black frame (a real solid-colour slide / video): wait much longer


def is_blank_thumb(thumb: bytes | None) -> bool:
    """True for an all-black or single-colour 8-bit gray thumbnail (see `blank_kind` for which)."""
    return blank_kind(thumb) is not None


def blank_kind(thumb: bytes | None) -> str | None:
    """'black' (brightest pixel <= BLANK_MAX_LEVEL), 'flat' (one non-black colour) or None. A really black or
    solid-colour screen (a dark video, a slide) looks the same, so callers wait for a streak: BLANK_STREAK for
    black, the longer FLAT_STREAK for flat."""
    if not thumb:
        return None
    hi, lo = max(thumb), min(thumb)
    if hi <= BLANK_MAX_LEVEL:
        return "black"
    return "flat" if (hi - lo) <= BLANK_MAX_SPREAD else None


BUNDLED_ENV = "MIYAGI_BUNDLED_PYTHON"  # set by the app (localEngine.ts) when the engine runs on miyagi.app's own Python
SETTINGS = "System Settings > Privacy & Security"


def bundled_app() -> bool:
    """The engine runs inside miyagi.app (its bundled Python): macOS lists the grant under miyagi, so the hints name
    miyagi, never python3.12, a Terminal or the engine's binary path."""
    return bool(os.environ.get(BUNDLED_ENV, "").strip())


def engine_binary() -> str:
    """The executable macOS attributes Screen Recording to when the engine is not launched from a granted app."""
    return os.path.realpath(sys.executable) if sys.executable else "python"


def permission_hint() -> str:
    """One line naming what to enable for Screen Recording: miyagi itself in the app, else (a dev engine started from
    a shell) the program running the engine or the app that launched it."""
    if bundled_app():
        return f"Turn on miyagi in {SETTINGS} > Screen Recording, then reopen miyagi."
    return (f"Enable Screen Recording for the program running the engine ({engine_binary()}) "
            "or for the app that launched it, then restart miyagi.")


def accessibility_hint() -> str:
    """One line naming what to enable for Accessibility (same rule as permission_hint)."""
    if bundled_app():
        return f"Turn on miyagi in {SETTINGS} > Accessibility, then reopen miyagi."
    return f"Turn it back on in {SETTINGS} > Accessibility for the app that runs the engine."


def display_changed(prev: tuple[float, float, float, float] | None, cur: tuple[float, float, float, float]) -> bool:
    """The captured display's frame moved or resized: the learner's window changed monitors, a monitor was plugged /
    unplugged, the resolution switched, or the screen rotated."""
    return prev is not None and any(abs(a - b) > 0.5 for a, b in zip(prev, cur))

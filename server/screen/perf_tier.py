"""Low-end Mac tier (MacBook Neo, 8 GB M1/M2 Airs): one place that decides how hard the screen sensors work.

A Mac with <= 8 GB of RAM or <= 2 performance cores is "low": the AX worker polls at 5 Hz instead of 10 (and drops to
1 Hz while nothing changes) and the idle heartbeat backs off further. Low Power Mode or running on battery ("saving")
stretches the heartbeat and halves the active AX rate, on every Mac.

Not done on purpose: capturing smaller frames. Measured offline (Nov 25, three VS Code fixtures): Vision OCR at 1.5 px/pt
took the same time as at 2x (160 vs 164 ms, 216 vs 207 ms: Vision rescales internally) and lost 8-11% of the words.

MIYAGI_PERF_TIER=low|normal forces a tier (auto otherwise). Everything here is pure except `detect()` and
`power_saving()`, which read sysctl / NSProcessInfo / pmset and are cached.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass

log = logging.getLogger("server.screen.perf")

LOW_MEM_BYTES = 8 * 1024 ** 3 + 256 * 1024 ** 2   # <= 8 GB (+ slack: hw.memsize is exact, never above 8 GiB there)
LOW_PERF_CORES = 2                               # A-series (A18 Pro: 2P + 4E)


@dataclass(frozen=True)
class PerfProfile:
    tier: str                         # "low" | "normal"
    reason: str                       # why ("8 GB RAM", "2 performance cores", "MIYAGI_PERF_TIER=low", "")
    mem_gb: float = 0.0
    perf_cores: int = 0
    # knobs the sensors read
    ax_hz: float = 10.0               # AX worker while things change
    ax_idle_hz: float = 2.0           # ... once nothing changed for AX_IDLE_AFTER_S
    idle_heartbeat_max: float = 8.0   # the reader's no-change heartbeat grows up to this (s)

    @property
    def low(self) -> bool:
        return self.tier == "low"


AX_IDLE_AFTER_S = 3.0   # no AX change (text, caret, document, terminal, app, mouse) this long -> idle rate


def profile_for(mem_bytes: int | None, perf_cores: int | None, override: str | None = None) -> PerfProfile:
    """Pure: the tier for a machine. `override` is MIYAGI_PERF_TIER (low | normal | auto/empty)."""
    mem_gb = round((mem_bytes or 0) / 1024 ** 3, 1)
    cores = int(perf_cores or 0)
    o = (override or "").strip().lower()
    if o in ("low", "normal"):
        reason = f"MIYAGI_PERF_TIER={o}"
        low = o == "low"
    else:
        why = []
        if mem_bytes and mem_bytes <= LOW_MEM_BYTES:
            why.append(f"{mem_gb:g} GB RAM")
        if cores and cores <= LOW_PERF_CORES:
            why.append(f"{cores} performance cores")
        low, reason = bool(why), ", ".join(why)
    if low:
        return PerfProfile("low", reason, mem_gb, cores, ax_hz=5.0, ax_idle_hz=1.0, idle_heartbeat_max=10.0)
    return PerfProfile("normal", reason, mem_gb, cores)


def idle_heartbeat(base: float, unchanged: int, saving: bool, cap: float) -> float:
    """Seconds until the next no-trigger capture. `unchanged`: captures in a row that found the screen unchanged.
    1x for the first 2, then +50% per unchanged capture up to `cap`; power saving x1.5 (also capped). Never below
    `base`, and a cap below base means "no backoff". Clicks, typing pauses, app switches and AX changes still capture
    at once (they poke the loop), so backing off only delays noticing a change nothing announced."""
    hb = base * (1.0 + 0.5 * max(0, unchanged - 2))
    if saving:
        hb *= 1.5
    return max(base, min(hb, max(cap, base)))


def ax_period(profile: PerfProfile, idle_for: float, saving: bool = False) -> float:
    """Seconds between AX snapshots: the active rate while things change, the idle rate after AX_IDLE_AFTER_S of
    nothing (any change snaps back at once). Power saving halves the active rate (never below the idle one)."""
    if idle_for >= AX_IDLE_AFTER_S:
        return 1.0 / profile.ax_idle_hz
    hz = profile.ax_hz / 2 if saving else profile.ax_hz
    return 1.0 / max(hz, profile.ax_idle_hz)


# ---------------------------------------------------------------------- detection (cached)

def _sysctl_int(name: str) -> int | None:
    try:
        out = subprocess.run(["sysctl", "-n", name], capture_output=True, text=True, timeout=2, check=False).stdout.strip()
        return int(out) if out else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _mem_bytes() -> int | None:
    try:
        n = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
        if n > 0:
            return int(n)
    except (ValueError, OSError, AttributeError):
        pass
    return _sysctl_int("hw.memsize") if sys.platform == "darwin" else None


def _perf_cores() -> int | None:
    if sys.platform == "darwin":
        n = _sysctl_int("hw.perflevel0.physicalcpu")   # Apple Silicon: P cores only
        if n:
            return n
    return os.cpu_count()


_profile: PerfProfile | None = None
_lock = threading.Lock()


def detect(refresh: bool = False) -> PerfProfile:
    """This Mac's profile (cached for the process)."""
    global _profile
    with _lock:
        if _profile is None or refresh:
            _profile = profile_for(_mem_bytes(), _perf_cores(), os.environ.get("MIYAGI_PERF_TIER"))
            log.info("perf tier %s%s", _profile.tier, f" ({_profile.reason})" if _profile.reason else "")
        return _profile


_saving: tuple[float, bool] = (0.0, False)
SAVING_TTL_S = 60.0


def _low_power_mode() -> bool:
    try:
        from Foundation import NSProcessInfo
        return bool(NSProcessInfo.processInfo().isLowPowerModeEnabled())
    except Exception:  # noqa: BLE001  (no Foundation / older macOS)
        return False


def _on_battery() -> bool:
    try:
        out = subprocess.run(["pmset", "-g", "ps"], capture_output=True, text=True, timeout=2, check=False).stdout
        return "Battery Power" in out
    except (OSError, subprocess.SubprocessError):
        return False


def power_saving(now: float | None = None) -> bool:
    """Low Power Mode on, or running on battery. Read at most once a minute (one `pmset` spawn); macOS only.
    MIYAGI_PERF_SAVING=1/0 forces it."""
    global _saving
    forced = os.environ.get("MIYAGI_PERF_SAVING")
    if forced in ("0", "1"):
        return forced == "1"
    if sys.platform != "darwin":
        return False
    now = time.time() if now is None else now
    t, val = _saving
    if now - t < SAVING_TTL_S:
        return val
    val = _low_power_mode() or _on_battery()
    _saving = (now, val)
    return val

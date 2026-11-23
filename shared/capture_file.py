"""Circle to ask, fast path: read the region the app already captured (action ask {capture: AskCapture}).

The app's helper (app/native/listen/Capture.swift) captures the circled region while Fn+Control is still held and
writes it as a 0600 JPEG, cap-<helper pid>-<uuid>.jpg, in the per-user temp folder miyagi-capture (0700). The ask carries
capture {path, w, h, rect, displayId}. The engine calls take_capture(capture) instead of its own frame grab:

    from shared.capture_file import take_capture, crop_to_screen
    cap = take_capture(payload.capture)      # None: missing, gone or failed a check -> capture as before (ask_frame)
    if cap is not None:
        jpeg = cap.jpeg                      # the image block for the model; crop size cap.w x cap.h pixels
        ...                                  # [DRAW:x,y,r:label] in crop pixels -> crop_to_screen(cap, x, y, r)
                                             # (None: a bad value, skip the mark)

take_capture checks the path (realpath directly inside the capture folder, that name, a regular file owned by this
user with mode 0600, a JPEG whose own frame size is the payload's w x h, not too big), reads it and deletes it, whatever the outcome once the path is ours. It
never raises and never logs the path or the pixels. It also deletes crops older than 30 s left in the folder by a
helper that was killed before its own timers ran (purge_stale). No OCR boxes come with it: an annotate for the answer comes from
the model's [DRAW] line, mapped with crop_to_screen.
"""

from __future__ import annotations

import math
import os
import re
import stat
import tempfile
import time
from dataclasses import dataclass
from typing import Any

MAX_EDGE = 1092  # the helper's long edge (CaptureMath.maxEdge)
MAX_BYTES = 4 * 1024 * 1024  # a 1092 px JPEG at 0.82 is a few hundred KB
# cap-<helper pid>-<uuid>.jpg (each helper deletes only its own); cap-<uuid>.jpg from older helpers is still read.
_NAME = re.compile(r"^cap-(?:[0-9]{1,10}-)?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.jpg$")
# Start-of-frame markers (baseline, extended, progressive, lossless...): not DHT C4, JPG C8 or DAC CC.
_SOF = frozenset({0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF})
DIR_NAME = "miyagi-capture"
STALE_S = 30.0  # the helper's own TTL (CaptureFiles.defaultTTL): anything older was left by a helper that died


@dataclass(frozen=True)
class Capture:
    jpeg: bytes
    w: int  # pixels
    h: int
    rect: tuple[float, float, float, float]  # x, y, w, h: the box captured, screen points (top-left origin)
    displayId: int


def capture_dirs() -> list[str]:
    """Where the helper writes: NSTemporaryDirectory()/miyagi-capture. That is $TMPDIR on macOS, and the per-user
    confstr folder when TMPDIR is unset or differs. Real paths, symlinks resolved."""
    roots: list[str] = []
    for root in (os.environ.get("TMPDIR"), _darwin_temp(), tempfile.gettempdir()):
        if root:
            d = os.path.realpath(os.path.join(root, DIR_NAME))
            if d not in roots:
                roots.append(d)
    return roots


def _darwin_temp() -> str | None:
    try:
        return os.confstr("CS_DARWIN_USER_TEMP_DIR")  # type: ignore[arg-type]
    except (ValueError, OSError, AttributeError):
        return None


def _get(o: Any, k: str) -> Any:
    if isinstance(o, dict):
        return o.get(k)
    return getattr(o, k, None)


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    f = float(v)
    return f if math.isfinite(f) else None


def _dim(v: Any) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return v if isinstance(v, int) and 1 <= v <= MAX_EDGE else None


def _ours(path: Any, dirs: list[str]) -> str | None:
    """The real path when `path` names one of the helper's files, else None (and nothing is touched)."""
    if not isinstance(path, str) or not path.startswith("/") or len(path) > 1024 or "\x00" in path:
        return None
    if not _NAME.match(os.path.basename(path)):
        return None
    real = os.path.realpath(path)
    if os.path.basename(real) != os.path.basename(path) or os.path.dirname(real) not in dirs:
        return None
    return real


def take_capture(capture: Any, *, dirs: list[str] | None = None) -> Capture | None:
    """Read and delete the app's capture. None = no capture, or one that is gone or fails a check. Never raises."""
    if capture is None:
        return None
    try:
        allowed = [os.path.realpath(d) for d in dirs] if dirs is not None else capture_dirs()
        real = _ours(_get(capture, "path"), allowed)
        if real is None:
            purge_stale(allowed)
            return None
        try:
            return _read(real, capture)
        finally:
            try:
                os.unlink(real)  # read or not, the crop goes now (the helper's timer would delete it within 30 s)
            except OSError:
                pass
            purge_stale(allowed)
    except Exception:  # noqa: BLE001 - a bad capture is never worse than no capture
        return None


def purge_stale(dirs: list[str] | None = None, *, max_age: float = STALE_S, now: float | None = None) -> int:
    """Delete the helper's crops older than max_age seconds (by mtime) in the capture folders. The helper deletes each
    one after 30 s with its own timer, but a helper that is SIGKILLed or crashes takes its timers with it, and the files
    would then stay until the next helper start. take_capture calls this on every ask that carries a capture; the
    engine may also call it at startup. Only cap-[<pid>-]<uuid>.jpg regular files owned by this user, directly inside a folder
    that is a real directory of this user, are touched. Returns how many were deleted. Never raises, never logs."""
    gone = 0
    try:
        allowed = [os.path.realpath(d) for d in dirs] if dirs is not None else capture_dirs()
        t = time.time() if now is None else now
        for d in allowed:
            try:
                dst = os.lstat(d)
                if not stat.S_ISDIR(dst.st_mode) or dst.st_uid != os.getuid():
                    continue
                names = os.listdir(d)
            except OSError:
                continue
            for name in names:
                if not _NAME.match(name):
                    continue
                p = os.path.join(d, name)
                try:
                    st = os.lstat(p)
                    if stat.S_ISREG(st.st_mode) and st.st_uid == os.getuid() and t - st.st_mtime > max_age:
                        os.unlink(p)
                        gone += 1
                except OSError:
                    continue
    except Exception:  # noqa: BLE001 - cleanup must never break an ask
        pass
    return gone


def _read(real: str, capture: Any) -> Capture | None:
    w, h = _dim(_get(capture, "w")), _dim(_get(capture, "h"))
    r = _get(capture, "rect")
    rect = tuple(_num(_get(r, k)) for k in ("x", "y", "w", "h")) if r is not None else ()
    disp = _get(capture, "displayId")
    if w is None or h is None or len(rect) != 4 or any(v is None for v in rect) or rect[2] <= 0 or rect[3] <= 0:  # type: ignore[operator]
        return None
    if isinstance(disp, bool) or not isinstance(disp, int) or not 0 <= disp <= 0xFFFFFFFF:
        return None
    dir_st = os.lstat(os.path.dirname(real))
    if not stat.S_ISDIR(dir_st.st_mode) or dir_st.st_uid != os.getuid() or stat.S_IMODE(dir_st.st_mode) & 0o077:
        return None
    fd = os.open(real, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o600:
            return None
        if st.st_nlink != 1 or not 0 < st.st_size <= MAX_BYTES:
            return None
        chunks, left = [], st.st_size
        while left > 0:
            b = os.read(fd, min(left, 1 << 20))
            if not b:
                break
            chunks.append(b)
            left -= len(b)
        data = b"".join(chunks)
    finally:
        os.close(fd)
    if len(data) != st.st_size or data[:2] != b"\xff\xd8":
        return None
    if jpeg_size(data) != (w, h):  # a [DRAW] point is mapped with w and h: they must be the image's real size
        return None
    return Capture(jpeg=data, w=w, h=h, rect=rect, displayId=disp)  # type: ignore[arg-type]


def jpeg_size(data: bytes) -> tuple[int, int] | None:
    """(width, height) from the JPEG's start-of-frame segment (SOF0, SOF2 and the other SOFn), or None: not a JPEG,
    truncated, or no frame header before the scan. Reads only the marker segments, never the pixels."""
    n = len(data)
    if n < 4 or data[0] != 0xFF or data[1] != 0xD8:
        return None
    i = 2
    while i + 1 < n:
        if data[i] != 0xFF:
            return None
        m = data[i + 1]
        if m == 0xFF:  # fill byte before a marker
            i += 1
            continue
        if m == 0x01 or 0xD0 <= m <= 0xD7:  # standalone markers, no length
            i += 2
            continue
        if m in (0xD8, 0xD9, 0xDA):  # a second SOI, EOI or the scan itself before any frame header
            return None
        if i + 4 > n:
            return None
        seg = (data[i + 2] << 8) | data[i + 3]
        if seg < 2 or i + 2 + seg > n:
            return None
        if m in _SOF:
            if seg < 7:
                return None
            h = (data[i + 5] << 8) | data[i + 6]
            w = (data[i + 7] << 8) | data[i + 8]
            return (w, h) if w > 0 and h > 0 else None
        i += 2 + seg
    return None


def crop_to_screen(cap: Any, px: float, py: float, r: float = 0.0) -> tuple[float, float, float] | None:
    """A crop pixel (the model's [DRAW:x,y,r]) -> (x, y, r) in screen points, or None: skip the mark.

    None when px or py is not a finite number (a bad [DRAW] value must not draw at the crop's corner), or when cap is
    not usable (w or h not a positive number, rect missing or not finite, rect.w or rect.h <= 0: a raw payload rather
    than a Capture). The point is clamped to [0, w] x [0, h] and r to [0, max(w, h)] (a non-finite r counts as 0)
    before scaling. Same formula as the helper's CaptureMath.toScreen:
    x = rect.x + px * rect.w / w, y = rect.y + py * rect.h / h, r_pt = r * rect.w / w."""
    try:
        w, h = _num(_get(cap, "w")), _num(_get(cap, "h"))
        rect = _get(cap, "rect")
        if rect is None:
            return None
        vals = rect if isinstance(rect, tuple) else tuple(_get(rect, k) for k in ("x", "y", "w", "h"))
        if len(vals) != 4:
            return None
        rx, ry, rw, rh = (_num(v) for v in vals)
    except Exception:  # noqa: BLE001 - a bad payload means no mark, never a crash
        return None
    if w is None or h is None or w <= 0 or h <= 0:
        return None
    if rx is None or ry is None or rw is None or rh is None or rw <= 0 or rh <= 0:
        return None
    x, y = _num(px), _num(py)
    if x is None or y is None:
        return None
    x = min(max(x, 0.0), w)
    y = min(max(y, 0.0), h)
    rr = min(max(_num(r) or 0.0, 0.0), max(w, h))
    return rx + x * rw / w, ry + y * rh / h, rr * rw / w

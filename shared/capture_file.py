"""Circle to ask, fast path: read the region the app already captured (action ask {capture: AskCapture}).

The app's helper (app/native/listen/Capture.swift) captures the circled region while Fn+Control is still held and
writes it as a 0600 JPEG, cap-<uuid>.jpg, in the per-user temp folder miyagi-capture (0700). The ask carries
capture {path, w, h, rect, displayId}. The engine calls take_capture(capture) instead of its own frame grab:

    from shared.capture_file import take_capture, crop_to_screen
    cap = take_capture(payload.capture)      # None: missing, gone or failed a check -> capture as before (ask_frame)
    if cap is not None:
        jpeg = cap.jpeg                      # the image block for the model; crop size cap.w x cap.h pixels
        ...                                  # [DRAW:x,y,r:label] in crop pixels -> crop_to_screen(cap, x, y, r)

take_capture checks the path (realpath directly inside the capture folder, that name, a regular file owned by this
user with mode 0600, a JPEG, not too big), reads it and deletes it, whatever the outcome once the path is ours. It
never raises and never logs the path or the pixels. No OCR boxes come with it: an annotate for the answer comes from
the model's [DRAW] line, mapped with crop_to_screen.
"""

from __future__ import annotations

import math
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from typing import Any

MAX_EDGE = 1092  # the helper's long edge (CaptureMath.maxEdge)
MAX_BYTES = 4 * 1024 * 1024  # a 1092 px JPEG at 0.82 is a few hundred KB
_NAME = re.compile(r"^cap-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.jpg$")
DIR_NAME = "miyagi-capture"


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
            return None
        try:
            return _read(real, capture)
        finally:
            try:
                os.unlink(real)  # read or not, the crop goes now (the helper's timer would delete it within 30 s)
            except OSError:
                pass
    except Exception:  # noqa: BLE001 - a bad capture is never worse than no capture
        return None


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
    return Capture(jpeg=data, w=w, h=h, rect=rect, displayId=disp)  # type: ignore[arg-type]


def crop_to_screen(cap: Any, px: float, py: float, r: float = 0.0) -> tuple[float, float, float]:
    """A crop pixel (the model's [DRAW:x,y,r]) -> (x, y, r) in screen points. The point is clamped to [0, w] x [0, h]
    first; a non-finite number counts as 0. Same formula as the helper's CaptureMath.toScreen:
    x = rect.x + px * rect.w / w, y = rect.y + py * rect.h / h, r_pt = r * rect.w / w."""
    w, h = float(_get(cap, "w")), float(_get(cap, "h"))
    rect = _get(cap, "rect")
    rx, ry, rw, rh = (rect if isinstance(rect, tuple) else tuple(float(_get(rect, k)) for k in ("x", "y", "w", "h")))

    def fin(v: float) -> float:
        return float(v) if isinstance(v, (int, float)) and math.isfinite(v) else 0.0

    x = min(max(fin(px), 0.0), w)
    y = min(max(fin(py), 0.0), h)
    return rx + x * rw / w, ry + y * rh / h, max(fin(r), 0.0) * rw / w

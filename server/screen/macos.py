"""macOS-only bits: Quartz screen capture, window list, Apple Vision OCR.

Everything here imports pyobjc lazily-at-module-level, so only import this module on darwin.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import time
from dataclasses import dataclass

import objc
import Quartz
import Vision

from server.config import safe_env

from .types import PERMISSION_HELP, Block, Rect, ScreenPermissionError, Window

# Apps whose windows are never "the learner's work" (menu bar extras etc.).
_IGNORED_OWNERS = {"Window Server", "Dock", "Control Center", "SystemUIServer", "Notification Center",
                   "Spotlight", "WindowManager", "TextInputMenuAgent", "Wallpaper"}




class ScreenUnavailableError(RuntimeError):
    """Permission is fine but the display gave no image right now (sleep / lock); retry later."""


SCREENCAPTURE = "/usr/sbin/screencapture"


@dataclass
class Frame:
    image: object          # CGImageRef
    screen: Rect           # captured display bounds in global points
    scale: float           # pixels per point
    t: float


def has_permission() -> bool:
    try:
        return bool(Quartz.CGPreflightScreenCaptureAccess())
    except Exception:  # noqa: BLE001  (very old macOS: just try capturing)
        return True


def request_permission() -> bool:
    try:
        return bool(Quartz.CGRequestScreenCaptureAccess())
    except Exception:  # noqa: BLE001
        return False


def main_display_bounds() -> Rect:
    b = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
    return Rect(b.origin.x, b.origin.y, b.size.width, b.size.height)


def display_bounds(display_id: int | None = None) -> Rect:
    b = Quartz.CGDisplayBounds(display_id if display_id else Quartz.CGMainDisplayID())
    return Rect(b.origin.x, b.origin.y, b.size.width, b.size.height)


def active_displays() -> list[tuple[int, Rect]]:
    """[(display id, bounds in global points)], the main display first (the order `screencapture -D` counts)."""
    try:
        err, ids, _n = Quartz.CGGetActiveDisplayList(16, None, None)
    except Exception:  # noqa: BLE001
        return []
    main = Quartz.CGMainDisplayID()
    ids = sorted(list(ids or []), key=lambda d: d != main)
    return [(int(d), display_bounds(int(d))) for d in ids]


def pick_display(displays: list[tuple[int, Rect]], window: Rect | None = None, point: tuple[float, float] | None = None,
                 main_id: int | None = None) -> int | None:
    """Pure. The display holding most of `window` (the learner's frontmost window); else the one under `point`
    (the cursor); else the main display / first listed. Rects are global points, top-left origin."""
    if not displays:
        return None
    if window is not None and window.w > 0 and window.h > 0:
        best, area = None, 0.0
        for did, b in displays:
            ix = min(window.x2, b.x2) - max(window.x, b.x)
            iy = min(window.y2, b.y2) - max(window.y, b.y)
            if ix > 0 and iy > 0 and ix * iy > area:
                best, area = did, ix * iy
        if best is not None:
            return best
    if point is not None:
        for did, b in displays:
            if b.x <= point[0] < b.x2 and b.y <= point[1] < b.y2:
                return did
    if main_id is not None and any(d == main_id for d, _ in displays):
        return main_id
    return displays[0][0]


def target_display_id() -> int:
    """Which display to read: where the learner's frontmost window is, else under the cursor, else main."""
    main = int(Quartz.CGMainDisplayID())
    try:
        displays = active_displays()
        if len(displays) < 2:
            return main
        front = frontmost_window()
        win = Rect(**front["rect"]) if front else None
        pt = None
        try:
            loc = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
            pt = (float(loc.x), float(loc.y))
        except Exception:  # noqa: BLE001
            pass
        return pick_display(displays, win, pt, main) or main
    except Exception:  # noqa: BLE001
        return main


def display_index(display_id: int) -> int:
    """1-based number `screencapture -D` uses for this display (main first)."""
    for i, (d, _) in enumerate(active_displays(), 1):
        if d == display_id:
            return i
    return 1


def capture_main_display(display_id: int | None = None) -> Frame:
    """Grab one whole display (default: primary; all windows composited, including our overlay)."""
    t = time.time()
    if display_asleep():
        raise ScreenUnavailableError("display asleep")
    did = display_id or Quartz.CGMainDisplayID()
    img = Quartz.CGDisplayCreateImage(did)
    if img is None:
        if not has_permission():
            raise ScreenPermissionError(PERMISSION_HELP)
        raise ScreenUnavailableError("display returned no image (asleep, locked, or switching Spaces?)")
    screen = display_bounds(did)
    scale = Quartz.CGImageGetWidth(img) / screen.w if screen.w else 1.0
    return Frame(img, screen, scale, t)


def display_asleep() -> bool:
    try:
        return bool(Quartz.CGDisplayIsAsleep(Quartz.CGMainDisplayID()))
    except Exception:  # noqa: BLE001
        return False


def capture_main_display_cli(timeout: float = 4.0, display_id: int | None = None) -> Frame:
    """Grab the primary display with Apple's `screencapture` tool (overlay included: mask it).

    A different capture path from ScreenCaptureKit / CGDisplayCreateImage. On macOS 26, replayd
    sometimes drops a third-party process's connection in a loop (XPC_ERROR_CONNECTION_INTERRUPTED
    thousands of times a second): SCK never answers and CGDisplayCreateImage (built on SCK) blocks
    5 s and returns nil, while `screencapture` keeps working. ~130-180 ms + ~15 ms decode at 3456 px.
    The temp PNG is 0600 and deleted before returning.
    """
    t = time.time()
    if display_asleep():
        raise ScreenUnavailableError("display asleep")
    fd, path = tempfile.mkstemp(prefix="miyagi-screen-", suffix=".png")
    os.close(fd)
    try:
        try:
            r = subprocess.run([SCREENCAPTURE, "-x", "-t", "png", "-D", str(display_index(display_id) if display_id else 1), path], capture_output=True,
                               timeout=timeout, check=False, env=safe_env())
        except subprocess.TimeoutExpired as e:
            raise ScreenUnavailableError(f"screencapture timed out after {timeout:.0f} s") from e
        if r.returncode != 0 or os.path.getsize(path) == 0:
            if not has_permission():
                raise ScreenPermissionError(PERMISSION_HELP)
            err = (r.stderr or b"").decode(errors="replace").strip()[:200]
            raise ScreenUnavailableError(f"screencapture failed (exit {r.returncode}): {err or 'no image'}")
        img = load_cgimage(path, cache=True)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    if img is None:
        raise ScreenUnavailableError("screencapture wrote an unreadable image")
    screen = display_bounds(display_id)
    scale = Quartz.CGImageGetWidth(img) / screen.w if screen.w else 1.0
    return Frame(img, screen, scale, t)


def list_windows(screen: Rect | None = None, on_screen_only: bool = True) -> list[Window]:
    """On-screen, normal-layer windows, front to back. Bounds are already points/top-left."""
    opts = (Quartz.kCGWindowListOptionOnScreenOnly if on_screen_only else Quartz.kCGWindowListOptionAll) \
        | Quartz.kCGWindowListExcludeDesktopElements
    infos = Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID) or []
    out: list[Window] = []
    for w in infos:
        if w.get("kCGWindowLayer", 0) != 0 or w.get("kCGWindowAlpha", 1) == 0:
            continue
        owner = w.get("kCGWindowOwnerName") or ""
        if owner in _IGNORED_OWNERS:
            continue
        b = w.get("kCGWindowBounds") or {}
        r = Rect(float(b.get("X", 0)), float(b.get("Y", 0)), float(b.get("Width", 0)), float(b.get("Height", 0)))
        if r.w < 60 or r.h < 40 or (not on_screen_only and not w.get("kCGWindowName")):
            continue
        if screen is not None and r.clamp(screen).w * r.clamp(screen).h <= 0:
            continue
        out.append(Window(app=owner, title=w.get("kCGWindowName") or "", rect=r,
                          window_id=int(w.get("kCGWindowNumber", 0)), pid=int(w.get("kCGWindowOwnerPID", 0))))
    return out


# Never "the frontmost app": our own overlay (Electron in dev, the packaged app) and screen chrome.
_OVERLAY_OWNERS = {"Electron", "Miyagi", "miyagi", "sandhacks-tutor"} | {
    s.strip() for s in os.environ.get("TUT_OVERLAY_APPS", "").split(",") if s.strip()}


def pick_frontmost(infos, ignore: set[str] | None = None) -> dict | None:
    """First normal (layer 0), visible window in CGWindowList's front-to-back order, skipping our
    overlay and system chrome -> {app, pid, title, window_id, rect}. Pure: takes the info dicts."""
    ignore = (ignore or set()) | _IGNORED_OWNERS | _OVERLAY_OWNERS
    for w in infos or []:
        if w.get("kCGWindowLayer", 0) != 0 or w.get("kCGWindowAlpha", 1) == 0:
            continue
        owner = w.get("kCGWindowOwnerName") or ""
        if not owner or owner in ignore:
            continue
        b = w.get("kCGWindowBounds") or {}
        if float(b.get("Width", 0)) < 60 or float(b.get("Height", 0)) < 40:
            continue
        return {"app": owner, "pid": int(w.get("kCGWindowOwnerPID", 0)), "title": w.get("kCGWindowName") or "",
                "window_id": int(w.get("kCGWindowNumber", 0)),
                "rect": {"x": float(b.get("X", 0)), "y": float(b.get("Y", 0)), "w": float(b.get("Width", 0)),
                         "h": float(b.get("Height", 0))}}
    return None


def frontmost_window() -> dict | None:
    """The app whose window is in front on the CURRENT Space, read live from the window server
    (~2-5 ms, no permission needed for the owner name). Follows Space swipes and full-screen apps
    at once, unlike NSWorkspace.frontmostApplication, which goes stale without an AppKit run loop."""
    opts = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    return pick_frontmost(Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID))


def frontmost_app(windows: list[Window] | None = None) -> str:
    """Name of the frontmost app.

    NSWorkspace.frontmostApplication goes stale in a process without a running AppKit
    run loop (like our uvicorn engine), so prefer the owner of the front-most normal window,
    which CGWindowList reports live.
    """
    if windows:
        return windows[0].app
    try:
        from AppKit import NSWorkspace
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        return str(app.localizedName()) if app else ""
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------- change detection

THUMB_W, THUMB_H = 432, 280


def thumbnail(image, size=(THUMB_W, THUMB_H)) -> bytes:
    """Downscale a CGImage to an 8-bit gray bitmap (fast: CoreGraphics does the resample)."""
    w, h = size
    cs = Quartz.CGColorSpaceCreateDeviceGray()
    ctx = Quartz.CGBitmapContextCreate(None, w, h, 8, w, cs, Quartz.kCGImageAlphaNone)
    Quartz.CGContextSetInterpolationQuality(ctx, Quartz.kCGInterpolationLow)
    Quartz.CGContextDrawImage(ctx, Quartz.CGRectMake(0, 0, w, h), image)
    data = Quartz.CGBitmapContextGetData(ctx)
    return bytes(data.as_buffer(w * h))


# ---------------------------------------------------------------- OCR

def _make_request():
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setUsesLanguageCorrection_(False)  # code and numbers: don't "fix" `u_x` into a word
    return req


def ocr_image(image, screen: Rect, scale: float, crop: Rect | None = None) -> tuple[list[Block], float]:
    """Run Vision on a CGImage that covers `screen` at `scale` px/pt.

    Returns (blocks, ms). Block rects are in screen points, top-left origin.
    If `crop` (points) is given, only that region is recognised.
    """
    with objc.autorelease_pool():
        img, origin = image, screen
        if crop is not None:
            c = crop.clamp(screen)
            px = Quartz.CGRectMake((c.x - screen.x) * scale, (c.y - screen.y) * scale, c.w * scale, c.h * scale)
            img = Quartz.CGImageCreateWithImageInRect(image, px)
            origin = c
        iw = Quartz.CGImageGetWidth(img) / scale
        ih = Quartz.CGImageGetHeight(img) / scale
        req = _make_request()
        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(img, None)
        t0 = time.perf_counter()
        ok, err = handler.performRequests_error_([req], None)
        ms = (time.perf_counter() - t0) * 1000
        if not ok:
            raise RuntimeError(f"Vision OCR failed: {err}")
        blocks: list[Block] = []
        for obs in req.results() or []:
            cands = obs.topCandidates_(1)
            if not cands:
                continue
            cand = cands[0]
            text = str(cand.string())
            if not text.strip():
                continue
            bb = obs.boundingBox()  # normalised, bottom-left origin
            x = origin.x + bb.origin.x * iw
            y = origin.y + (1.0 - bb.origin.y - bb.size.height) * ih
            blocks.append(Block(text=text, rect=Rect(x, y, bb.size.width * iw, bb.size.height * ih),
                                confidence=float(cand.confidence())))
        return blocks, ms


# ---------------------------------------------------------------- image I/O (fixtures, debug PNGs)

def load_cgimage(path: str, cache: bool = False):
    """cache=True decodes now (needed when the file is deleted right after)."""
    url = Quartz.CFURLCreateFromFileSystemRepresentation(None, path.encode(), len(path.encode()), False)
    src = Quartz.CGImageSourceCreateWithURL(url, None)
    if src is None:
        raise FileNotFoundError(path)
    opts = {Quartz.kCGImageSourceShouldCacheImmediately: True} if cache else None
    return Quartz.CGImageSourceCreateImageAtIndex(src, 0, opts)


def save_cgimage_png(image, path: str) -> None:
    url = Quartz.CFURLCreateFromFileSystemRepresentation(None, path.encode(), len(path.encode()), False)
    dest = Quartz.CGImageDestinationCreateWithURL(url, "public.png", 1, None)
    Quartz.CGImageDestinationAddImage(dest, image, None)
    if not Quartz.CGImageDestinationFinalize(dest):
        raise OSError(f"could not write {path}")


def cgimage_to_pil(image):
    from PIL import Image
    w, h = Quartz.CGImageGetWidth(image), Quartz.CGImageGetHeight(image)
    cs = Quartz.CGColorSpaceCreateDeviceRGB()
    ctx = Quartz.CGBitmapContextCreate(None, w, h, 8, w * 4, cs,
                                       Quartz.kCGImageAlphaPremultipliedLast | Quartz.kCGBitmapByteOrder32Big)
    Quartz.CGContextDrawImage(ctx, Quartz.CGRectMake(0, 0, w, h), image)
    buf = Quartz.CGBitmapContextGetData(ctx).as_buffer(w * h * 4)
    return Image.frombuffer("RGBA", (w, h), bytes(buf), "raw", "RGBA", 0, 1).convert("RGB")


def capture_window_image(window_id: int):
    """Just one window (used to build privacy-safe fixtures)."""
    return Quartz.CGWindowListCreateImage(Quartz.CGRectNull, Quartz.kCGWindowListOptionIncludingWindow,
                                          window_id, Quartz.kCGWindowImageBoundsIgnoreFraming)

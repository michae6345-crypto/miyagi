"""ScreenCaptureKit capture of the primary display WITHOUT our own overlay (and excluded apps).

SCContentFilter leaves our Electron overlay's windows out of OUR frames, while the overlay stays
visible on screen and in the user's screen recordings (unlike setContentProtection).
~35 ms per full-res frame warm on Apple Silicon. macOS 14+.

Gotcha: pyobjc completion handlers must return None (a lambda returning a value aborts the process).
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time

import Quartz
import ScreenCaptureKit as SCK

from .types import Rect, ScreenPermissionError

log = logging.getLogger("server.screen.sck")

# Our overlay: Electron in dev (com.github.Electron), the packaged app by name/bundle.
DEFAULT_OVERLAY_BUNDLES = {"com.github.Electron"}
DEFAULT_OVERLAY_NAME = re.compile(r"miyagi|sandhacks", re.IGNORECASE)  # + TUT_OVERLAY_BUNDLES env
# Never capture these at all (P1 privacy): password managers, messaging.
DEFAULT_PRIVATE_BUNDLES = {"com.1password.1password", "com.agilebits.onepassword7", "com.bitwarden.desktop",
                           "com.apple.keychainaccess", "com.apple.Passwords", "com.apple.MobileSMS",
                           "com.dashlane.dashlanephonefinal", "com.lastpass.LastPass"}


def _env_set(name: str) -> set[str]:
    return {s.strip() for s in os.environ.get(name, "").split(",") if s.strip()}


class SCKCapturer:
    def __init__(self, overlay_bundles: set[str] | None = None, private_bundles: set[str] | None = None,
                 refresh_s: float = 2.0, timeout_s: float = 3.0):
        self.overlay_bundles = (overlay_bundles if overlay_bundles is not None else DEFAULT_OVERLAY_BUNDLES) \
            | _env_set("TUT_OVERLAY_BUNDLES")
        self.private_bundles = (private_bundles if private_bundles is not None else DEFAULT_PRIVATE_BUNDLES) \
            | _env_set("TUT_PRIVATE_BUNDLES")
        self.refresh_s = refresh_s
        self.timeout_s = timeout_s
        self._content = None
        self._content_t = 0.0
        self._filter = None
        self._display = None
        self.excluded_apps: list[str] = []

    def _is_excluded(self, app) -> bool:
        bid = str(app.bundleIdentifier() or "")
        name = str(app.applicationName() or "")
        if int(app.processID()) == os.getpid():
            return True
        return bid in self.overlay_bundles or bid in self.private_bundles or bool(DEFAULT_OVERLAY_NAME.search(name))

    def _refresh(self) -> None:
        ev, box = threading.Event(), {}

        def done(content, err):
            box["c"], box["e"] = content, err
            ev.set()

        SCK.SCShareableContent.getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_(
            False, True, done)
        if not ev.wait(self.timeout_s):
            raise TimeoutError("SCShareableContent timed out")
        if box.get("e") is not None or box.get("c") is None:
            raise ScreenPermissionError()
        content = box["c"]
        main_id = Quartz.CGMainDisplayID()
        disp = next((d for d in content.displays() if d.displayID() == main_id), None)
        if disp is None:
            raise RuntimeError("primary display not in SCShareableContent")
        excluded = [a for a in content.applications() if self._is_excluded(a)]
        self.excluded_apps = [str(a.applicationName() or a.bundleIdentifier()) for a in excluded]
        self._filter = SCK.SCContentFilter.alloc().initWithDisplay_excludingApplications_exceptingWindows_(
            disp, excluded, [])
        self._display = disp
        self._content, self._content_t = content, time.time()

    def capture(self):
        """-> (CGImage, screen Rect in points, scale). Raises ScreenPermissionError / RuntimeError."""
        if self._filter is None or time.time() - self._content_t > self.refresh_s:
            self._refresh()
        disp = self._display
        f = disp.frame()
        screen = Rect(f.origin.x, f.origin.y, f.size.width, f.size.height)
        scale = float(Quartz.CGDisplayPixelsWide(disp.displayID())) / screen.w if screen.w else 2.0
        mode = Quartz.CGDisplayCopyDisplayMode(disp.displayID())
        if mode is not None and screen.w:
            scale = Quartz.CGDisplayModeGetPixelWidth(mode) / screen.w
        cfg = SCK.SCStreamConfiguration.alloc().init()
        cfg.setWidth_(int(screen.w * scale))
        cfg.setHeight_(int(screen.h * scale))
        cfg.setShowsCursor_(False)
        ev, box = threading.Event(), {}

        def done(img, err):
            box["i"], box["e"] = img, err
            ev.set()

        SCK.SCScreenshotManager.captureImageWithFilter_configuration_completionHandler_(self._filter, cfg, done)
        if not ev.wait(self.timeout_s):
            raise TimeoutError("SCScreenshotManager timed out")
        if box.get("i") is None:
            self._filter = None  # force a refresh next time
            raise RuntimeError(f"ScreenCaptureKit capture failed: {box.get('e')}")
        img = box["i"]
        return img, screen, Quartz.CGImageGetWidth(img) / screen.w

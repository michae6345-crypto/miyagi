"""Real Apple Vision OCR on saved VS Code + Terminal screenshots (macOS only)."""
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="Apple Vision is macOS-only")

FIX = Path(__file__).resolve().parent.parent / "fixtures"
FLAT, DROP = str(FIX / "vscode_terminal_flat.png"), str(FIX / "vscode_terminal_dropping.png")
LOSS = r"epoch\s+(?P<step>\d+).*?loss\s+(?P<value>[0-9.eE+-]+)"


@pytest.fixture(scope="module")
def flat():
    from server.screen import observe_image
    return observe_image(FLAT)


@pytest.fixture(scope="module")
def drop():
    from server.screen import observe_image
    return observe_image(DROP)


def test_blocks_are_in_screen_points_and_assigned_to_windows(flat):
    assert flat.scale == 2.0 and flat.screen.w == 1728
    assert len(flat.blocks) > 100
    for b in flat.blocks:
        assert 0 <= b.rect.x <= 1728 and 0 <= b.rect.y <= 1117
    apps = {b.app for b in flat.blocks}
    assert {"Code", "Terminal"} <= apps


def test_locate_def_pde_residual(flat):
    from server.screen import locate_match
    r = locate_match(flat, "def pde_residual", app="Code")
    assert r is not None
    # line 19 of the editor in this fixture: ~(330..640, 470..495) points
    assert 300 < r.rect.x < 345 and 455 < r.rect.y < 480 and 20 < r.rect.h < 40


def test_locate_return_line(flat):
    from server.screen import locate
    r = locate(flat, "return u_t + beta * u_x", app="vscode")
    assert r is not None and 560 < r.y < 590


def test_screen_contains_scoped_by_app(flat):
    from server.screen import screen_contains
    assert screen_contains(flat, r"def\s+pde_residual", app="Code")
    assert not screen_contains(flat, r"def\s+pde_residual", app="Terminal")
    assert screen_contains(flat, r"loss\s+2\.50", app="Terminal")


def test_overlay_bounds_are_ignored():
    from server.screen import observe_image, screen_contains
    o = observe_image(FLAT, overlay=[{"x": 300, "y": 30, "w": 600, "h": 1000}])
    assert not screen_contains(o, r"def\s+pde_residual")
    assert screen_contains(o, r"loss\s+2\.50", app="Terminal")


def test_metric_reader_flat_vs_dropping(flat, drop):
    from server.screen.metrics import TerminalMetricReader
    pts = TerminalMetricReader("t", {"loss": LOSS}, app="Terminal").feed(flat)
    assert len(pts) >= 35
    vals = [v for _, _, v in pts]
    assert max(vals) - min(vals) < 0.002  # flat at ~0.25: the β=30 failure mode
    pts = TerminalMetricReader("t", {"loss": LOSS}, app="Terminal").feed(drop)
    steps = [s for _, s, _ in pts]
    vals = [v for _, _, v in pts]
    assert len(pts) >= 25 and steps == sorted(steps)
    assert vals[-1] < vals[0] / 2  # clearly dropping


def test_ocr_latency_reasonable(flat):
    # first call includes Vision model warm-up; generous bound so CI on slower Macs passes
    assert flat.ocr_ms < 3000


def test_live_capture_is_primary_full_frame_points(live_display):
    """events.ts: rects are screen POINTS, top-left origin, PRIMARY display's FULL frame
    (y=0 is the very top, menu bar included)."""
    from server.screen import macos
    if not macos.has_permission():
        pytest.skip("no Screen Recording permission")
    from AppKit import NSScreen
    f = macos.capture_main_display()
    full = NSScreen.screens()[0].frame()  # primary display, full frame incl. menu bar
    assert (f.screen.x, f.screen.y) == (0, 0)
    assert (f.screen.w, f.screen.h) == (full.size.width, full.size.height)
    import Quartz
    assert Quartz.CGImageGetHeight(f.image) == round(f.screen.h * f.scale)  # menu bar is in the image


def test_rect_origin_is_top_left(flat):
    # the VS Code title bar (window y=33) must come out near the top, the terminal's last
    # lines near the bottom: i.e. Vision's bottom-left boxes were flipped.
    from server.screen import locate
    top = locate(flat, "pinn_demo", app="Code")
    bottom = locate(flat, "loss 2.5057e-01", app="Terminal")
    assert top is not None and top.y < 60
    assert bottom is not None and bottom.y > 1000

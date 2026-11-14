"""Debug CLI for the screen reader.

    python -m server.screen watch [--interval 2] [--app Terminal] [--json]
    python -m server.screen locate "def pde_residual" [--app Code] [--out locate.png]
    python -m server.screen metrics 'epoch\\s+(?P<step>\\d+).*?loss\\s+(?P<value>[0-9.eE+-]+)' [--lesson demo]
    python -m server.screen bench [-n 10]
    python -m server.screen describe "Is the loss converging?"     # Claude Opus 5.5
    python -m server.screen where "the Run button"                 # Claude Haiku 5.5
    python -m server.screen fixture NAME [--apps Code Terminal]   # save a privacy-safe fixture PNG

Every command takes --image PATH to run on a saved screenshot instead of the live screen.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path


def _obs(args):
    from .reader import ScreenReader, observe_image
    if args.image:
        return observe_image(args.image), None
    r = ScreenReader()
    return r.observe_now(force=True), r


def cmd_watch(args) -> None:
    from .reader import ScreenReader
    r = ScreenReader(interval=args.interval, fixture=args.image)

    def show(obs):
        if args.json:
            print(json.dumps(obs.to_dict()), flush=True)
            return
        print(f"\n=== frame {obs.frame}  t={time.strftime('%H:%M:%S', time.localtime(obs.t))}  "
              f"front={obs.app!r}  windows={len(obs.windows)}  blocks={len(obs.blocks)}  ocr={obs.ocr_ms:.0f}ms")
        for b in obs.blocks_in(args.app)[: args.limit]:
            rr = b.rect
            print(f"  [{(b.app or '-')[:12]:>12}] ({rr.x:6.0f},{rr.y:5.0f} {rr.w:4.0f}x{rr.h:3.0f}) "
                  f"{b.confidence:.2f}  {b.text}")
        sys.stdout.flush()

    r.subscribe(show)
    r.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        r.stop()
        h = r.ocr_ms_history
        if h:
            print(f"\nOCR latency over {len(h)} frames: median {statistics.median(h):.0f}ms, max {max(h):.0f}ms")


def cmd_locate(args) -> None:
    from PIL import ImageDraw

    from . import macos
    from .match import locate_match
    obs, reader = _obs(args)
    res = locate_match(obs, args.match, args.app)
    print(f"frontmost={obs.app!r} blocks={len(obs.blocks)} ocr={obs.ocr_ms:.0f}ms")
    if res is None:
        print("NOT FOUND")
    else:
        print(json.dumps(res.to_dict(), indent=2))
    # draw it
    if args.image:
        pil = macos.cgimage_to_pil(macos.load_cgimage(args.image))
    else:
        pil = reader.screenshot_pil()
    s, sx, sy = obs.scale, obs.screen.x, obs.screen.y
    d = ImageDraw.Draw(pil)
    if args.all:
        for b in obs.blocks:
            d.rectangle([(b.rect.x - sx) * s, (b.rect.y - sy) * s, (b.rect.x2 - sx) * s, (b.rect.y2 - sy) * s],
                        outline=(0, 160, 255), width=1)
    if res:
        r = res.rect
        d.rectangle([(r.x - sx) * s, (r.y - sy) * s, (r.x2 - sx) * s, (r.y2 - sy) * s], outline=(255, 40, 40),
                    width=max(3, int(2 * s)))
    out = Path(args.out)
    pil.save(out)
    print(f"saved {out.resolve()}")
    sys.exit(0 if res else 1)


def cmd_metrics(args) -> None:
    from .reader import ScreenReader
    r = ScreenReader(interval=args.interval, fixture=args.image)
    r.watch_metrics(args.lesson, {args.name: args.pattern},
                    lambda n, s, v: print(f"metric {n} step={s} value={v}", flush=True), app=args.app,
                    on_restart=lambda rid: print(f"-- restart detected, run_id={rid}", flush=True))
    r.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        r.stop()


def cmd_bench(args) -> None:
    from . import macos
    from .reader import load_fixture
    times, caps = [], []
    for i in range(args.n):
        t0 = time.perf_counter()
        if args.image:
            img, screen, scale, _, _ = load_fixture(args.image)
        else:
            f = macos.capture_main_display()
            img, screen, scale = f.image, f.screen, f.scale
        caps.append((time.perf_counter() - t0) * 1000)
        blocks, ms = macos.ocr_image(img, screen, scale)
        times.append(ms)
        print(f"frame {i}: capture {caps[-1]:.0f}ms  ocr {ms:.0f}ms  blocks {len(blocks)}")
    warm = times[1:] or times
    print(f"OCR median {statistics.median(warm):.0f}ms (excl. first), first {times[0]:.0f}ms, "
          f"capture median {statistics.median(caps):.0f}ms")


def cmd_describe(args) -> None:
    from .reader import ScreenReader
    r = ScreenReader(fixture=args.image)
    from .describe import DescribeError
    r.observe_now(force=True)
    try:
        print(asyncio.run(r.describe(args.question)))
    except DescribeError as e:
        print(f"describe failed ({e.reason}): {e.detail}", file=sys.stderr)
        sys.exit(2)


def cmd_where(args) -> None:
    from .describe import DescribeError
    from .reader import ScreenReader
    r = ScreenReader(fixture=args.image)
    r.observe_now(force=True)
    try:
        res = asyncio.run(r.where(args.target, args.app))
    except DescribeError as e:
        print(f"where failed ({e.reason}): {e.detail}", file=sys.stderr)
        sys.exit(2)
    print(json.dumps(res.to_dict(), indent=2) if res else "NOT FOUND")


def cmd_fixture(args) -> None:
    """Compose a fixture from ONLY the named apps' windows (nothing else on screen leaks in)."""
    from PIL import Image

    from . import macos
    screen = macos.main_display_bounds()
    f = macos.capture_main_display()
    scale = f.scale
    wins = [w for w in macos.list_windows(screen, on_screen_only=False)
            if any(a.lower() in w.app.lower() for a in args.apps)
            and (not args.titles or any(t.lower() in w.title.lower() for t in args.titles))]
    canvas = Image.new("RGB", (int(screen.w * scale), int(screen.h * scale)), (40, 44, 52))
    meta_w = []
    for w in reversed(wins):  # back to front
        img = macos.capture_window_image(w.window_id)
        if img is None:
            continue
        pil = macos.cgimage_to_pil(img)
        pil = pil.resize((int(w.rect.w * scale), int(w.rect.h * scale)))
        canvas.paste(pil, (int((w.rect.x - screen.x) * scale), int((w.rect.y - screen.y) * scale)))
    for w in wins:
        meta_w.append({"app": w.app, "title": w.title, "rect": w.rect.to_dict()})
    out_dir = Path(__file__).parent / "fixtures"
    out_dir.mkdir(exist_ok=True)
    png = out_dir / f"{args.name}.png"
    canvas.save(png)
    (out_dir / f"{args.name}.json").write_text(json.dumps(
        {"screen": screen.to_dict(), "scale": scale, "app": wins[0].app if wins else "", "windows": meta_w},
        indent=2) + "\n")
    print(f"saved {png} with {len(wins)} windows")


def cmd_ax(args) -> None:
    """AX spike: what the accessibility tree gives for the frontmost app, every 0.5 s."""
    from . import ax
    if not ax.trusted(prompt=args.prompt):
        print(ax.AX_HELP)
        sys.exit(1)
    end = time.time() + args.seconds
    while time.time() < end:
        snap = ax.snapshot()
        if snap is not None:
            d = snap.to_dict()
            print(json.dumps(d, default=str)[: args.width], flush=True)
            if snap.editor:
                print(f"  caret line {snap.editor.caret_line}: {snap.editor.line_text(snap.editor.caret_line)!r}  "
                      f"rect={snap.editor.line_rect}  text_len={len(snap.editor.text)}  read={snap.read_ms:.0f}ms")
        time.sleep(0.5)


def cmd_cursor(args) -> None:
    """Print the cursor context (what's under the mouse) every 0.5 s."""
    from .reader import ScreenReader
    r = ScreenReader(use_events=False)
    r._start_sensors()
    r.observe_now(force=True)
    end = time.time() + args.seconds
    while time.time() < end:
        print(json.dumps(r.cursor_context()), flush=True)
        time.sleep(0.5)
    r.stop()


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m server.screen")
    p.add_argument("--image", help="run on a saved screenshot instead of the live screen")
    sub = p.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("watch")
    w.add_argument("--interval", type=float, default=2.0)
    w.add_argument("--app")
    w.add_argument("--limit", type=int, default=60)
    w.add_argument("--json", action="store_true")
    w.set_defaults(fn=cmd_watch)
    lo = sub.add_parser("locate")
    lo.add_argument("match")
    lo.add_argument("--app")
    lo.add_argument("--out", default="locate.png")
    lo.add_argument("--all", action="store_true", help="also outline every OCR block")
    lo.set_defaults(fn=cmd_locate)
    me = sub.add_parser("metrics")
    me.add_argument("pattern")
    me.add_argument("--name", default="loss")
    me.add_argument("--lesson", default="debug")
    me.add_argument("--app")
    me.add_argument("--interval", type=float, default=2.0)
    me.set_defaults(fn=cmd_metrics)
    b = sub.add_parser("bench")
    b.add_argument("-n", type=int, default=8)
    b.set_defaults(fn=cmd_bench)
    de = sub.add_parser("describe")
    de.add_argument("question")
    de.set_defaults(fn=cmd_describe)
    wh = sub.add_parser("where")
    wh.add_argument("target")
    wh.add_argument("--app")
    wh.set_defaults(fn=cmd_where)
    fx = sub.add_parser("fixture")
    fx.add_argument("name")
    fx.add_argument("--apps", nargs="+", default=["Code", "Terminal"])
    fx.add_argument("--titles", nargs="*", help="only windows whose title contains one of these")
    fx.set_defaults(fn=cmd_fixture)
    axp = sub.add_parser("ax")
    axp.add_argument("--seconds", type=float, default=10)
    axp.add_argument("--width", type=int, default=600)
    axp.add_argument("--prompt", action="store_true", help="show the macOS Accessibility prompt")
    axp.set_defaults(fn=cmd_ax)
    cu = sub.add_parser("cursor")
    cu.add_argument("--seconds", type=float, default=10)
    cu.set_defaults(fn=cmd_cursor)
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()

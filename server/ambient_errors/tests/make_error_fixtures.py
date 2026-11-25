"""Render one window per error kind and record its Apple Vision OCR (macOS only; no model, no network).

    python -m server.ambient_errors.tests.make_error_fixtures [name ...] [--png DIR]

Writes server/ambient_errors/tests/fixtures/<name>.ocr.json: a recorded ScreenObservation (RAW Vision blocks in
screen points, `postprocessed: false`, as server/screen's own fixtures), so the tests read what OCR really makes of a
traceback (dropped indentation, split rows, curly quotes) offline. The exact text of each window is FIXTURES[name].text
(the Accessibility path reads that, and it is the truth the tests compare to). PNGs go to --png (default: not kept).
"""
from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

FIX = Path(__file__).resolve().parent / "fixtures"
W, H, S = 1728, 1117, 2
MENLO = "/System/Library/Fonts/Menlo.ttc"
UI = "/System/Library/Fonts/SFNS.ttf"


@dataclass(frozen=True)
class Spec:
    name: str
    app: str
    title: str
    text: str
    win: tuple = (160.0, 110.0, 1180.0, 640.0)  # x, y, w, h in points
    panel_header: bool = False  # VS Code: draw the panel tab row above the text (the integrated terminal)
    editor: str = ""  # VS Code: editor rows above the panel


PY = """sam@mac weather-app % python3 app.py
Traceback (most recent call last):
  File "/Users/sam/code/weather-app/app.py", line 3, in <module>
    import pandas as pd
ModuleNotFoundError: No module named 'pandas'
sam@mac weather-app % """

NODE = """sam@mac api % node server.js
/Users/sam/code/api/server.js:12
const port = config.port;
                    ^

TypeError: Cannot read properties of undefined (reading 'port')
    at Object.<anonymous> (/Users/sam/code/api/server.js:12:21)
    at Module._compile (node:internal/modules/cjs/loader:1554:14)
    at Object..js (node:internal/modules/cjs/loader:1706:10)
    at Module.load (node:internal/modules/cjs/loader:1289:32)

Node.js v22.11.0
sam@mac api % """

TSC = """sam@mac web % npx tsc --noEmit
src/index.ts:14:7 - error TS2322: Type 'string' is not assignable to type 'number'.

14 const total: number = "42";
         ~~~~~

Found 1 error in src/index.ts:14

sam@mac web % """

PIP = """(.venv) sam@mac ml % pip install tensorflow==2.3
ERROR: Could not find a version that satisfies the requirement tensorflow==2.3 (from versions: 2.16.1, 2.17.0)
ERROR: No matching distribution found for tensorflow==2.3
(.venv) sam@mac ml % """

NPM = """sam@mac web % npm install reactt
npm error code E404
npm error 404 Not Found - GET https://registry.npmjs.org/reactt - Not found
npm error 404
npm error 404  'reactt@*' is not in this registry.
npm error 404
npm error 404 Note that you can also install from a
npm error 404 tarball, folder, http url, or git url.
npm error A complete log of this run can be found in: /Users/sam/.npm/_logs/2026-11-24T18_40_12_118Z-debug-0.log
sam@mac web % """

GIT = """sam@mac api % git push
To github.com:sam/api.git
 ! [rejected]        main -> main (fetch first)
error: failed to push some refs to 'github.com:sam/api.git'
hint: Updates were rejected because the remote contains work that you do not
hint: have locally. This is usually caused by another repository pushing to
hint: the same ref. If you want to integrate the remote changes, use
hint: 'git pull' before pushing again.
sam@mac api % """

NOTEBOOK = """[3]   import pandas as pd
      weather = pd.read_csv("weather.csv")

[4]   df.head()

---------------------------------------------------------------------------
NameError                                 Traceback (most recent call last)
Cell In[4], line 1
----> 1 df.head()

NameError: name 'df' is not defined"""

CLEAN = """sam@mac weather-app % python3 app.py
Loaded 365 rows from weather.csv
Mean temperature: 14.2 C
sam@mac weather-app % git status
On branch main
nothing to commit, working tree clean
sam@mac weather-app % """

VSCODE_EDITOR = """1   import { readFileSync } from "fs";
2
3   export function total(rows: number[]): number {
4     return rows.reduce((a, b) => a + b, 0);
5   }"""

FIXTURES = {s.name: s for s in [
    Spec("python_traceback", "Terminal", "weather-app — -zsh — 120×34", PY),
    Spec("node_stack", "Terminal", "api — -zsh — 120×34", NODE),
    Spec("tsc_error", "Code", "index.ts — web", TSC, win=(0.0, 33.0, 1320.0, 1000.0), panel_header=True,
         editor=VSCODE_EDITOR),
    Spec("pip_failure", "Terminal", "ml — -zsh — 120×34", PIP, win=(120.0, 110.0, 1480.0, 520.0)),
    Spec("npm_failure", "iTerm2", "web (-zsh)", NPM, win=(80.0, 110.0, 1560.0, 640.0)),
    Spec("git_error", "Terminal", "api — -zsh — 120×34", GIT),
    Spec("jupyter_cell", "Code", "explore.ipynb — weather-app", NOTEBOOK),
    Spec("clean_run", "Terminal", "weather-app — -zsh — 120×34", CLEAN),
]}


def render(spec: Spec):
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (W * S, H * S), (58, 68, 92))
    d = ImageDraw.Draw(img)
    mono = ImageFont.truetype(MENLO, 13 * S)
    ui = ImageFont.truetype(UI, 12 * S)
    x, y, w, h = spec.win
    P = lambda v: round(v * S)  # noqa: E731
    d.rectangle([P(x), P(y), P(x + w), P(y + h)], fill=(30, 30, 30))
    d.rectangle([P(x), P(y), P(x + w), P(y + 28)], fill=(50, 50, 50))
    d.text((P(x + w / 2 - 6 * len(spec.title) / 2 * 0.9), P(y + 7)), spec.title, font=ui, fill=(200, 200, 200))
    ty = y + 40
    if spec.editor:
        for row in spec.editor.splitlines():
            d.text((P(x + 60), P(ty)), row, font=mono, fill=(212, 212, 212))
            ty += 19
        ty += 30
    if spec.panel_header:
        d.line([P(x), P(ty - 8), P(x + w), P(ty - 8)], fill=(70, 70, 70), width=S)
        hx = x + 20
        for tab in ("PROBLEMS", "OUTPUT", "DEBUG CONSOLE", "TERMINAL", "PORTS"):
            d.text((P(hx), P(ty)), tab, font=ui, fill=(230, 230, 230) if tab == "TERMINAL" else (150, 150, 150))
            hx += 8 * len(tab) + 28
        ty += 30
    for row in spec.text.splitlines():
        d.text((P(x + 14), P(ty)), row, font=mono, fill=(220, 220, 220))
        ty += 19
    return img


def main(argv: list[str]) -> None:
    from server.screen import macos
    from server.screen import match as M
    from server.screen.types import Rect, ScreenObservation, Window

    png_dir = None
    if "--png" in argv:
        k = argv.index("--png")
        png_dir = Path(argv[k + 1])
        argv = argv[:k] + argv[k + 2:]
    only = set(argv)
    FIX.mkdir(parents=True, exist_ok=True)
    screen = Rect(0, 0, W, H)
    with tempfile.TemporaryDirectory() as tmp:
        for spec in FIXTURES.values():
            if only and spec.name not in only:
                continue
            png = (png_dir or Path(tmp)) / f"{spec.name}.png"
            png.parent.mkdir(parents=True, exist_ok=True)
            render(spec).save(png, optimize=True)
            windows = [Window(spec.app, spec.title, Rect(*spec.win))]
            blocks, ms = macos.ocr_image(macos.load_cgimage(str(png), cache=True), screen, float(S))
            blocks = M.reading_order(M.assign_windows(blocks, windows))
            obs = ScreenObservation(t=0.0, app=spec.app, windows=windows, blocks=blocks, screen=screen,
                                    scale=float(S), ocr_ms=ms, frame=1, source=f"fixture:{spec.name}.png")
            rec = obs.to_dict()
            rec["postprocessed"] = False  # RAW Vision output: loaders apply match.postprocess like a live frame
            (FIX / f"{spec.name}.ocr.json").write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
            print(f"{spec.name}: {len(blocks)} blocks, OCR {ms:.0f} ms")


if __name__ == "__main__":
    main(sys.argv[1:])

"""Render full-screen VS Code / Cursor screenshots and record their Apple Vision OCR.

    python -m server.screen.tests.make_editor_fixtures

Writes, for each fixture in FIXTURES, into server/screen/fixtures/:
  <name>.png        the rendered screen (1728x1117 pt @2x, full-screen app: no menu bar)
  <name>.json       sidecar (screen, scale, app, windows), so `observe_image(<name>.png)` works
  <name>.ocr.json   the RECORDED observation (Vision blocks in screen points), so tests run offline
                    on any OS via `ScreenObservation.from_dict`
  <name>.truth.json what was drawn where: per file line, its row rect (ground truth for tests)

The renderer mimics the Dark+ layout (tabs, breadcrumbs, line-number gutter, code, minimap,
panel, status bar) with Menlo; geometry follows VS Code's defaults (font 12 / line 18).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FIX = Path(__file__).resolve().parent.parent / "fixtures"
SRC = FIX / "editor_src" / "pinn_convection.py.txt"
W, H, S = 1728, 1117, 2  # points, scale

MENLO = "/System/Library/Fonts/Menlo.ttc"
UI = "/System/Library/Fonts/SFNS.ttf"

KW = {"def", "class", "return", "import", "from", "for", "in", "if", "with", "as", "None", "True", "False",
      "lambda", "not", "and", "or", "while", "else", "elif"}
TOKEN = re.compile(r'(#.*$)|("[^"]*"|\'[^\']*\')|(\b\d+(?:\.\d+)?(?:e-?\d+)?\b)|(\b[A-Za-z_]\w*\b)|(.)')
C = {"bg": (30, 30, 30), "side": (37, 37, 38), "act": (51, 51, 51), "tabs": (45, 45, 45), "tab": (30, 30, 30),
     "status": (0, 122, 204), "panel": (30, 30, 30), "fg": (212, 212, 212), "kw": (86, 156, 214),
     "str": (206, 145, 120), "com": (106, 153, 85), "num": (181, 206, 168), "gut": (133, 133, 133),
     "gut_cur": (198, 198, 198), "cur": (40, 40, 40), "ui": (204, 204, 204), "dim": (150, 150, 150)}


@dataclass
class Spec:
    name: str
    app: str
    title: str
    first_line: int
    font: float = 12.0
    line_h: float = 18.0
    sidebar: bool = True
    panel: bool = True
    caret_line: int | None = None


FIXTURES = [
    Spec("vscode_fullscreen_top", "Code", "pinn_convection.py — pinn_demo", first_line=1, caret_line=9),
    Spec("vscode_fullscreen_scrolled", "Code", "pinn_convection.py — pinn_demo", first_line=44,
         caret_line=51),
    Spec("cursor_fullscreen_bigfont", "Cursor", "● pinn_convection.py — pinn_demo", first_line=70,
         font=14.0, line_h=21.0, sidebar=False, panel=False, caret_line=80),
]


def P(v: float) -> int:
    return round(v * S)


def render(spec: Spec, src_lines: list[str]):
    img = Image.new("RGB", (W * S, H * S), C["bg"])
    d = ImageDraw.Draw(img)
    mono = ImageFont.truetype(MENLO, P(spec.font))
    ui = ImageFont.truetype(UI, P(12))
    ui_small = ImageFont.truetype(UI, P(11))

    act_w = 48
    side_w = 252 if spec.sidebar else 0
    ex = act_w + side_w                       # editor x
    tabs_h, crumbs_h, status_h = 35, 22, 22
    top = tabs_h + crumbs_h                    # first editor row y
    status_y = H - status_h
    panel_y = 800 if spec.panel else status_y
    mini_w, scroll_w = 110, 14
    gutter_right = ex + 6 + 5 * spec.font * 0.6 + 8   # right edge of the line numbers
    code_x = gutter_right + 26                        # glyph margin + folding area
    text_right = W - mini_w - scroll_w

    # chrome
    d.rectangle([0, 0, P(act_w), P(H)], fill=C["act"])
    if spec.sidebar:
        d.rectangle([P(act_w), 0, P(ex), P(H)], fill=C["side"])
        d.text((P(act_w + 20), P(12)), "EXPLORER", font=ui_small, fill=C["dim"])
        d.text((P(act_w + 12), P(40)), "PINN_DEMO", font=ui_small, fill=C["ui"])
        for i, f in enumerate(["data", "outputs", "pinn_convection.py", "train.py", "README.md",
                               "requirements.txt"]):
            d.text((P(act_w + 28), P(64 + i * 22)), f, font=ui, fill=C["ui"])
    d.rectangle([P(ex), 0, P(W), P(tabs_h)], fill=C["tabs"])
    tx = ex
    for i, t in enumerate(["pinn_convection.py", "train.py", "README.md"]):
        tw = 40 + len(t) * 7.2
        if i == 0:
            d.rectangle([P(tx), 0, P(tx + tw), P(tabs_h)], fill=C["tab"])
        d.text((P(tx + 14), P(10)), t, font=ui, fill=C["ui"] if i == 0 else C["dim"])
        tx += tw
    d.text((P(ex + 14), P(tabs_h + 4)), "pinn_demo  ›  pinn_convection.py  ›  pde_residual", font=ui_small,
           fill=C["dim"])

    # editor rows
    truth = {}
    rows = int((panel_y - top) // spec.line_h)
    for k in range(rows):
        n = spec.first_line + k
        y = top + k * spec.line_h
        if n > len(src_lines):
            break
        if n == spec.caret_line:
            d.rectangle([P(ex), P(y), P(text_right), P(y + spec.line_h) - 1], fill=C["cur"])
        num = str(n)
        nw = d.textlength(num, font=mono) / S
        ty = y + (spec.line_h - spec.font * 1.17) / 2
        d.text((P(gutter_right - nw), P(ty)), num, font=mono,
               fill=C["gut_cur"] if n == spec.caret_line else C["gut"])
        x = code_x
        line = src_lines[n - 1]
        for m in TOKEN.finditer(line):
            tok = m.group(0)
            col = (C["com"] if m.group(1) else C["str"] if m.group(2) else C["num"] if m.group(3)
                   else C["kw"] if m.group(4) and tok in KW else C["fg"])
            d.text((P(x), P(ty)), tok, font=mono, fill=col)
            x += d.textlength(tok, font=mono) / S
        truth[n] = {"y": y, "h": spec.line_h, "text": line}
        # minimap: coloured dashes, no readable text
        if line.strip():
            ind = len(line) - len(line.lstrip())
            d.rectangle([P(W - mini_w - scroll_w + 6 + ind), P(top + k * 2), P(W - mini_w - scroll_w + 6
                         + min(len(line), 100)), P(top + k * 2) + 2], fill=(90, 90, 90))
    d.rectangle([P(W - scroll_w), P(top), P(W), P(panel_y)], fill=(40, 40, 40))

    # panel with a terminal
    if spec.panel:
        d.rectangle([P(ex), P(panel_y), P(W), P(status_y)], fill=C["panel"])
        d.line([P(ex), P(panel_y), P(W), P(panel_y)], fill=(70, 70, 70), width=2)
        d.text((P(ex + 14), P(panel_y + 8)), "PROBLEMS    OUTPUT    DEBUG CONSOLE    TERMINAL    PORTS",
               font=ui_small, fill=C["ui"])
        term = ["tripi@mac pinn_demo % python pinn_convection.py"]
        loss = 12.034
        for e in range(0, 1100, 100):
            term.append(f"epoch {e:5d} | loss {loss:.4e} | pde {loss / 40:.3e}")
            loss *= 0.71
        for i, t in enumerate(term[:13]):
            d.text((P(ex + 14), P(panel_y + 36 + i * 17)), t, font=ImageFont.truetype(MENLO, P(12)), fill=C["fg"])

    d.rectangle([0, P(status_y), P(W), P(H)], fill=C["status"])
    cl = spec.caret_line or spec.first_line
    d.text((P(W - 520), P(status_y + 4)), f"Ln {cl}, Col 5    Spaces: 4    UTF-8    LF    Python    3.11.9",
           font=ui_small, fill=(255, 255, 255))
    geo = {"text_left": code_x, "text_right": text_right, "gutter_right": gutter_right, "top": top,
           "bottom": top + rows * spec.line_h, "line_h": spec.line_h,
           "visible": [spec.first_line, min(len(src_lines), spec.first_line + rows - 1)]}
    return img, truth, geo


def main() -> None:
    from server.screen import macos
    from server.screen import match as M
    from server.screen.types import Rect, ScreenObservation, Window

    src_lines = SRC.read_text().split("\n")
    if src_lines and src_lines[-1] == "":
        src_lines.pop()
    screen = Rect(0, 0, W, H)
    for spec in FIXTURES:
        img, truth, geo = render(spec, src_lines)
        png = FIX / f"{spec.name}.png"
        img.save(png, optimize=True)
        windows = [Window(spec.app, spec.title, Rect(0, 0, W, H))]
        (FIX / f"{spec.name}.json").write_text(json.dumps(
            {"screen": screen.to_dict(), "scale": float(S), "app": spec.app,
             "windows": [w.to_dict() for w in windows]}, indent=2) + "\n")
        cg = macos.load_cgimage(str(png))
        blocks, ms = macos.ocr_image(cg, screen, float(S))
        blocks = M.reading_order(M.assign_windows(blocks, windows))
        obs = ScreenObservation(t=0.0, app=spec.app, windows=windows, blocks=blocks, screen=screen,
                                scale=float(S), ocr_ms=ms, frame=1, source=f"fixture:{png.name}")
        (FIX / f"{spec.name}.ocr.json").write_text(json.dumps(obs.to_dict(), indent=1) + "\n")
        (FIX / f"{spec.name}.truth.json").write_text(json.dumps(
            {"geometry": geo, "lines": {str(k): v for k, v in truth.items()}}, indent=1) + "\n")
        print(f"{spec.name}: {len(blocks)} blocks, OCR {ms:.0f} ms, visible {geo['visible']}")


if __name__ == "__main__":
    main()

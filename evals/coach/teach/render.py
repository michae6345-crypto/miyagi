"""Full-screen VS Code (lesson mode: the editor IS the lesson) with an optional integrated terminal panel.

Same geometry and Dark+ colours as E6's `server/screen/tests/make_editor_fixtures.py` (1728x1117 pt @2x,
no menu bar, tabs 35 / breadcrumbs 22 / panel at y=800 / status bar 22), parameterised for one learner
state: folder, file, unsaved dot, code, terminal lines (None = panel closed). OCR'd with the engine's own
`observe_image`, so the observation has the same shape and noise as a live frame.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H, S = 1728, 1117, 2
MENLO = "/System/Library/Fonts/Menlo.ttc"
UI = "/System/Library/Fonts/SFNS.ttf"
KW = {"def", "class", "return", "import", "from", "for", "in", "if", "with", "as", "None", "True", "False",
      "lambda", "not", "and", "or", "while", "else", "elif", "print"}
TOKEN = re.compile(r'(#.*$)|("""[^"]*"""|"[^"]*"|\'[^\']*\')|(\b\d+(?:\.\d+)?\b)|(\b[A-Za-z_]\w*\b)|(.)')
C = {"bg": (30, 30, 30), "side": (37, 37, 38), "act": (51, 51, 51), "tabs": (45, 45, 45), "tab": (30, 30, 30),
     "status": (0, 122, 204), "panel": (30, 30, 30), "fg": (212, 212, 212), "kw": (86, 156, 214),
     "str": (206, 145, 120), "com": (106, 153, 85), "num": (181, 206, 168), "gut": (133, 133, 133),
     "gut_cur": (198, 198, 198), "cur": (40, 40, 40), "ui": (204, 204, 204), "dim": (150, 150, 150),
     "err": (241, 76, 76)}


def P(v: float) -> int:
    return round(v * S)


def render(png: Path, *, folder: str, file: str, code: str, tree: list[str], dirty: bool = False,
           terminal: list[str] | None = None, caret_line: int = 1) -> dict:
    """Draw the screen, write <png> + sidecar <png>.json. -> {line: rect} of the drawn code rows."""
    img = Image.new("RGB", (W * S, H * S), C["bg"])
    d = ImageDraw.Draw(img)
    mono = ImageFont.truetype(MENLO, P(12))
    ui = ImageFont.truetype(UI, P(12))
    ui_small = ImageFont.truetype(UI, P(11))
    act_w, side_w = 48, 252
    ex = act_w + side_w
    tabs_h, crumbs_h, status_h = 35, 22, 22
    top = tabs_h + crumbs_h
    status_y = H - status_h
    panel_y = 800 if terminal is not None else status_y
    line_h = 18.0
    gutter_right = ex + 6 + 5 * 12 * 0.6 + 8
    code_x = gutter_right + 26

    d.rectangle([0, 0, P(act_w), P(H)], fill=C["act"])
    d.rectangle([P(act_w), 0, P(ex), P(H)], fill=C["side"])
    d.text((P(act_w + 20), P(12)), "EXPLORER", font=ui_small, fill=C["dim"])
    d.text((P(act_w + 12), P(40)), folder.upper(), font=ui_small, fill=C["ui"])
    for i, f in enumerate(tree):
        d.text((P(act_w + 28), P(64 + i * 22)), f, font=ui, fill=C["ui"])
    d.rectangle([P(ex), 0, P(W), P(tabs_h)], fill=C["tabs"])
    tab = f"{file}  ●" if dirty else file
    tw = 40 + len(tab) * 7.2
    d.rectangle([P(ex), 0, P(ex + tw), P(tabs_h)], fill=C["tab"])
    d.text((P(ex + 14), P(10)), tab, font=ui, fill=C["ui"])
    d.text((P(ex + 14), P(tabs_h + 4)), f"{folder}  ›  {file}", font=ui_small, fill=C["dim"])

    lines = code.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    rows: dict[int, dict] = {}
    for k in range(int((panel_y - top) // line_h)):
        n = k + 1
        y = top + k * line_h
        if n > max(1, len(lines)):
            break
        if n == caret_line:
            d.rectangle([P(ex), P(y), P(W - 124), P(y + line_h) - 1], fill=C["cur"])
        num = str(n)
        ty = y + (line_h - 12 * 1.17) / 2
        d.text((P(gutter_right - d.textlength(num, font=mono) / S), P(ty)), num, font=mono,
               fill=C["gut_cur"] if n == caret_line else C["gut"])
        # token by token with Dark+ colours, exactly like E6's fixtures. (Tried one run per line: Vision
        # then dropped most lines of a sparse frame. Either way it reads "def add(a, b):" as "… b) :".)
        x = code_x
        src = lines[n - 1] if n <= len(lines) else ""
        for m in TOKEN.finditer(src):
            tok = m.group(0)
            col = (C["com"] if m.group(1) else C["str"] if m.group(2) else C["num"] if m.group(3)
                   else C["kw"] if m.group(4) and tok in KW else C["fg"])
            d.text((P(x), P(ty)), tok, font=mono, fill=col)
            x += d.textlength(tok, font=mono) / S
        rows[n] = {"x": code_x, "y": y, "w": x - code_x, "h": line_h, "text": src}

    if terminal is not None:
        d.rectangle([P(ex), P(panel_y), P(W), P(status_y)], fill=C["panel"])
        d.line([P(ex), P(panel_y), P(W), P(panel_y)], fill=(70, 70, 70), width=2)
        d.text((P(ex + 14), P(panel_y + 8)), "PROBLEMS    OUTPUT    DEBUG CONSOLE    TERMINAL    PORTS",
               font=ui_small, fill=C["ui"])
        shown = terminal[-16:]
        for i, t in enumerate(shown):
            bad = re.search(r"Error|Traceback|error:", t)
            d.text((P(ex + 14), P(panel_y + 36 + i * 17)), t, font=mono, fill=C["err"] if bad else C["fg"])

    d.rectangle([0, P(status_y), P(W), P(H)], fill=C["status"])
    d.text((P(W - 520), P(status_y + 4)), f"Ln {caret_line}, Col 1    Spaces: 4    UTF-8    LF    Python    3.12.7",
           font=ui_small, fill=(255, 255, 255))

    png.parent.mkdir(parents=True, exist_ok=True)
    img.save(png, optimize=True)
    title = f"{'● ' if dirty else ''}{file} — {folder}"
    png.with_suffix(".json").write_text(json.dumps(
        {"screen": {"x": 0, "y": 0, "w": W, "h": H}, "scale": float(S), "app": "Code",
         "windows": [{"app": "Code", "title": title, "rect": {"x": 0, "y": 0, "w": W, "h": H}}]}, indent=1))
    return rows

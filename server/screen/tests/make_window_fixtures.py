"""Render WINDOWED VS Code screenshots (menu bar, title bar with the command-center folder, dirty
tab, Dark+ token colours, an optional Pylance hover) and record their Apple Vision OCR.

    python -m server.screen.tests.make_window_fixtures

Writes <name>.png / .json / .ocr.json / .truth.json into server/screen/fixtures/ (like
make_editor_fixtures.py). Truth holds the menu-bar item rects, the hover box, the window parts and
every drawn code row.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FIX = Path(__file__).resolve().parent.parent / "fixtures"
W, H, S = 1728, 1117, 2
MENLO = "/System/Library/Fonts/Menlo.ttc"
UI = "/System/Library/Fonts/SFNS.ttf"

CALC = '''"""A tiny calculator for the python-calculator lesson."""


def add(a, b):
    return a + b


def subtract(a, b):
    return a - b


def multiply(a, b):
    return a * b


def divide(a, b):
    if b == 0:
        raise ZeroDivisionError("division by zero")
    return a / b


if __name__ == "__main__":
    print(add(2, 3))
'''.splitlines()

KW = {"def", "return", "if", "raise", "import", "from", "class", "for", "in", "while", "else", "elif"}
TOKEN = re.compile(r'(#.*$)|("[^"]*"|\'[^\']*\')|(\b\d+(?:\.\d+)?\b)|(\b[A-Za-z_]\w*\b)|(.)')
C = {"bg": (30, 30, 30), "side": (37, 37, 38), "act": (51, 51, 51), "tabs": (37, 37, 38), "tab": (30, 30, 30),
     "title": (31, 31, 31), "status": (0, 122, 204), "fg": (212, 212, 212), "kw": (86, 156, 214),
     "kw2": (197, 134, 192), "fn": (220, 220, 170), "param": (156, 220, 254), "cls": (78, 201, 176),
     "str": (206, 145, 120), "num": (181, 206, 168), "com": (106, 153, 85), "gut": (110, 118, 129),
     "gut_cur": (204, 204, 204), "cur": (40, 40, 40), "ui": (204, 204, 204), "dim": (150, 150, 150),
     "menubar": (226, 226, 226), "menu_fg": (20, 20, 20), "hover_bg": (37, 37, 38), "hover_border": (69, 69, 69),
     "desktop": (58, 68, 92)}


@dataclass
class Spec:
    name: str
    folder: str = "python-calculator-e430dc"
    file: str = "calculator.py"
    crumbs: tuple = ("python-calculator-e430dc", "src", "calculator.py", "add")
    dirty: bool = True
    hover: bool = False
    caret_line: int = 4
    win: tuple = (0.0, 33.0, 1320.0, 1000.0)     # x, y, w, h (points): below the menu bar
    menu_bar: bool = True
    other_tabs: tuple = ("test_calculator.py",)
    extra: dict = field(default_factory=dict)


FIXTURES = [
    Spec("vscode_window_calc_hover", hover=True),
    Spec("vscode_window_calc_clean", dirty=False),
]

MENU = ["Code", "File", "Edit", "Selection", "View", "Go", "Run", "Terminal", "Window", "Help"]


def P(v: float) -> int:
    return round(v * S)


def _tokens(line: str):
    """(text, colour) with Dark+ semantic colours: def NAME -> yellow, its params -> light blue."""
    out, prev_kw, in_params = [], None, False
    for m in TOKEN.finditer(line):
        tok = m.group(0)
        if m.group(1):
            col = C["com"]
        elif m.group(2):
            col = C["str"]
        elif m.group(3):
            col = C["num"]
        elif m.group(4):
            if tok in KW:
                col = C["kw2"] if tok in ("return", "if", "raise", "else", "elif", "for", "while", "in") else C["kw"]
            elif prev_kw == "def":
                col = C["fn"]
            elif in_params:
                col = C["param"]
            elif tok in ("ZeroDivisionError", "print"):
                col = C["cls"] if tok[0].isupper() else C["fn"]
            else:
                col = C["param"] if tok in ("a", "b") else C["fg"]
            prev_kw = tok
        else:
            col = C["fg"]
            if tok == "(" and prev_kw not in (None, "def"):
                in_params = line.lstrip().startswith("def ")
            if tok == ")":
                in_params = False
            if tok.strip():
                prev_kw = None if tok != "(" else prev_kw
        out.append((tok, col))
    return out


def render(spec: Spec):
    img = Image.new("RGB", (W * S, H * S), C["desktop"])
    d = ImageDraw.Draw(img)
    mono = ImageFont.truetype(MENLO, P(12))
    ui, ui_small = ImageFont.truetype(UI, P(12)), ImageFont.truetype(UI, P(11))
    menu_font = ImageFont.truetype(UI, P(13))
    truth: dict = {"menu": {}, "lines": {}}

    # macOS menu bar (VS Code frontmost)
    if spec.menu_bar:
        d.rectangle([0, 0, P(W), P(33)], fill=C["menubar"])
        x = 48.0
        for i, item in enumerate(MENU):
            f = ImageFont.truetype(UI, P(13)) if i else menu_font
            tw = d.textlength(item, font=f) / S
            d.text((P(x), P(9)), item, font=f, fill=C["menu_fg"])
            truth["menu"][item] = {"x": x - 8, "y": 0, "w": tw + 16, "h": 33}
            x += tw + 22
        d.text((P(W - 190), P(9)), "Sat Nov 14  4:12 PM", font=menu_font, fill=C["menu_fg"])

    wx, wy, ww, wh = spec.win
    d.rectangle([P(wx), P(wy), P(wx + ww), P(wy + wh)], fill=C["bg"])
    # title bar: traffic lights + command center with the folder name
    d.rectangle([P(wx), P(wy), P(wx + ww), P(wy + 35)], fill=C["title"])
    for i, col in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        cx = wx + 20 + i * 20
        d.ellipse([P(cx - 6), P(wy + 12), P(cx + 6), P(wy + 24)], fill=col)
    cc_w = 300
    cc_x = wx + ww / 2 - cc_w / 2
    d.rounded_rectangle([P(cc_x), P(wy + 7), P(cc_x + cc_w), P(wy + 29)], radius=P(6), fill=(42, 42, 42),
                        outline=(70, 70, 70), width=2)
    d.text((P(cc_x + cc_w / 2 - len(spec.folder) * 3.2), P(wy + 11)), spec.folder, font=ui, fill=C["ui"])
    truth["command_center"] = {"x": cc_x, "y": wy + 7, "w": cc_w, "h": 22, "text": spec.folder}

    act_w, side_w = 48, 240
    ex = wx + act_w + side_w
    top_bar = wy + 35
    d.rectangle([P(wx), P(top_bar), P(wx + act_w), P(wy + wh)], fill=C["act"])
    d.rectangle([P(wx + act_w), P(top_bar), P(ex), P(wy + wh)], fill=C["side"])
    d.text((P(wx + act_w + 20), P(top_bar + 12)), "EXPLORER", font=ui_small, fill=C["dim"])
    d.text((P(wx + act_w + 12), P(top_bar + 38)), spec.folder.upper(), font=ui_small, fill=C["ui"])
    for i, f in enumerate(["src", "calculator.py", "tests", "test_calculator.py", "README.md"]):
        d.text((P(wx + act_w + (28 if i in (0, 2, 4) else 44)), P(top_bar + 62 + i * 22)), f, font=ui, fill=C["ui"])

    # tabs: active tab shows ● when dirty, x otherwise
    tabs_h, crumbs_h = 35, 22
    d.rectangle([P(ex), P(top_bar), P(wx + ww), P(top_bar + tabs_h)], fill=C["tabs"])
    tx = ex
    for i, t in enumerate((spec.file,) + tuple(spec.other_tabs)):
        tw = 50 + len(t) * 7.2
        if i == 0:
            d.rectangle([P(tx), P(top_bar), P(tx + tw), P(top_bar + tabs_h)], fill=C["tab"])
            mark = "●" if spec.dirty else "×"
            d.text((P(tx + tw - 22), P(top_bar + 9)), mark, font=ui, fill=C["ui"])
            truth["active_tab"] = {"x": tx, "y": top_bar, "w": tw, "h": tabs_h}
        d.text((P(tx + 14), P(top_bar + 10)), t, font=ui, fill=C["ui"] if i == 0 else C["dim"])
        tx += tw
    d.text((P(ex + 14), P(top_bar + tabs_h + 4)), "  ›  ".join(spec.crumbs), font=ui_small, fill=C["dim"])

    # editor rows
    lh, font_pt = 18.0, 12.0
    top = top_bar + tabs_h + crumbs_h
    status_y = wy + wh - 22
    gutter_right = ex + 6 + 5 * font_pt * 0.6 + 8
    code_x = gutter_right + 26
    rows = int((status_y - top) // lh)
    for k in range(rows):
        n = 1 + k
        if n > len(CALC):
            break
        y = top + k * lh
        if n == spec.caret_line:
            d.rectangle([P(ex), P(y), P(wx + ww - 14), P(y + lh) - 1], fill=C["cur"])
        ty = y + (lh - font_pt * 1.17) / 2
        num = str(n)
        d.text((P(gutter_right - d.textlength(num, font=mono) / S), P(ty)), num, font=mono,
               fill=C["gut_cur"] if n == spec.caret_line else C["gut"])
        x = code_x
        for tok, col in _tokens(CALC[n - 1]):
            d.text((P(x), P(ty)), tok, font=mono, fill=col)
            x += d.textlength(tok, font=mono) / S
        truth["lines"][str(n)] = {"y": y, "h": lh, "text": CALC[n - 1]}
    truth["editor"] = {"x": ex, "y": top, "w": wx + ww - ex, "h": status_y - top}

    # Pylance hover on `add` (line 4): a bordered box BELOW the line, over lines 5-9
    if spec.hover:
        hx = code_x + d.textlength("def ", font=mono) / S - 4
        hy = top + 4 * lh + 2
        hw, hh = 330, 96
        d.rectangle([P(hx), P(hy), P(hx + hw), P(hy + hh)], fill=C["hover_bg"], outline=C["hover_border"], width=2)
        hover_lines = [("(function) def add(", 8), ("    a: Any,", 26), ("    b: Any", 44), (") -> Any", 62)]
        for t, dy in hover_lines:
            xx = hx + 10
            for tok, col in _tokens(t.replace("(function) ", "")) if not t.startswith("(function)") else [
                    ("(function) ", C["fg"]), ("def ", C["kw"]), ("add", C["fn"]), ("(", C["fg"])]:
                d.text((P(xx), P(hy + dy)), tok, font=mono, fill=col)
                xx += d.textlength(tok, font=mono) / S
        d.line([P(hx), P(hy + 82), P(hx + hw), P(hy + 82)], fill=C["hover_border"], width=2)
        d.text((P(hx + 10), P(hy + 84)), "Add two numbers.", font=ui_small, fill=C["dim"])
        truth["hover"] = {"x": hx, "y": hy, "w": hw, "h": hh}

    d.rectangle([P(wx), P(status_y), P(wx + ww), P(wy + wh)], fill=C["status"])
    d.text((P(wx + ww - 420), P(status_y + 4)), f"Ln {spec.caret_line}, Col 9    Spaces: 4    UTF-8    LF    Python",
           font=ui_small, fill=(255, 255, 255))
    truth["window"] = {"x": wx, "y": wy, "w": ww, "h": wh}
    return img, truth


def main() -> None:
    from server.screen import macos
    from server.screen import match as M
    from server.screen.types import Rect, ScreenObservation, Window

    screen = Rect(0, 0, W, H)
    for spec in FIXTURES:
        img, truth = render(spec)
        png = FIX / f"{spec.name}.png"
        img.save(png, optimize=True)
        title = ("● " if spec.dirty else "") + f"{spec.file} — {spec.folder}"
        windows = [Window("Code", title, Rect(*spec.win))]
        (FIX / f"{spec.name}.json").write_text(json.dumps(
            {"screen": screen.to_dict(), "scale": float(S), "app": "Code",
             "windows": [w.to_dict() for w in windows]}, indent=2) + "\n")
        cg = macos.load_cgimage(str(png))
        blocks, ms = macos.ocr_image(cg, screen, float(S))
        blocks = M.reading_order(M.assign_windows(blocks, windows))
        obs = ScreenObservation(t=0.0, app="Code", windows=windows, blocks=blocks, screen=screen,
                                scale=float(S), ocr_ms=ms, frame=1, source=f"fixture:{png.name}")
        rec = obs.to_dict()
        rec["postprocessed"] = False    # RAW Vision output: loaders apply match.postprocess like a live frame
        (FIX / f"{spec.name}.ocr.json").write_text(json.dumps(rec, indent=1) + "\n")
        (FIX / f"{spec.name}.truth.json").write_text(json.dumps(truth, indent=1) + "\n")
        print(f"{spec.name}: {len(blocks)} blocks, OCR {ms:.0f} ms")


if __name__ == "__main__":
    main()

"""Draw a realistic macOS screen (VS Code + Terminal [+ Chrome]) for one eval case, then OCR it with
the engine's own reader (`server.screen.reader.observe_image`: Apple Vision, window assignment, reading
order). The PNG + sidecar JSON use the exact fixture format of `server/screen/fixtures/`, so the
observation the coach gets has the same shape, OCR noise included, as a live frame.

Geometry is in screen POINTS (top-left origin), drawn at Retina scale 2 like the real fixtures.
`Screen.render()` also returns where every text line was drawn, so a case can put the cursor
"on line 7 of Timer.js" or "on the error line in Terminal" and the grader knows which rect is right.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H, SCALE = 1728, 1117, 2.0
MENU_H = 33
MONO = "/System/Library/Fonts/Menlo.ttc"
UI = "/System/Library/Fonts/SFNS.ttf"

BG = (30, 30, 30)
EDITOR_BG = (31, 31, 31)
SIDEBAR_BG = (24, 24, 24)
TITLE_BG = (40, 40, 40)
TEXT = (212, 212, 212)
DIM = (133, 133, 133)
TERM_BG = (22, 22, 22)
TERM_FG = (230, 230, 230)

_fonts: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def font(path: str, pt: float) -> ImageFont.FreeTypeFont:
    px = int(round(pt * SCALE))
    key = (path, px)
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(path, px)
    return _fonts[key]


@dataclass
class Drawn:
    app: str
    kind: str  # editor | gutter | terminal | browser | ui
    text: str
    rect: tuple[float, float, float, float]  # points
    line: int | None = None  # 1-based editor line, if any
    file: str | None = None


@dataclass
class Window:
    app: str
    title: str
    rect: tuple[float, float, float, float]

    def to_dict(self) -> dict:
        x, y, w, h = self.rect
        return {"app": self.app, "title": self.title, "rect": {"x": x, "y": y, "w": w, "h": h}}


# ---------------------------------------------------------------- syntax colours (VS Code Dark+)

KW_CTRL = r"\b(import|from|export|default|return|if|else|for|in|while|as|def|class|try|except|with|async|await)\b"
KW_DECL = r"\b(const|let|var|function|new|true|false|null|undefined|None|True|False|lambda)\b"
TOKEN = re.compile(
    r"(?P<comment>//.*$|#.*$)|(?P<string>'[^']*'|\"[^\"]*\"|`[^`]*`)|(?P<ctrl>" + KW_CTRL[2:-2] + r")\b|"
    r"(?P<decl>" + KW_DECL[2:-2] + r")\b|(?P<num>\b\d+(\.\d+)?\b)|(?P<fn>\b[A-Za-z_]\w*(?=\())|(?P<tag></?[A-Z]\w*)"
)
COLORS = {"comment": (106, 153, 85), "string": (206, 145, 120), "ctrl": (197, 134, 192), "decl": (86, 156, 214),
          "num": (181, 206, 168), "fn": (220, 220, 170), "tag": (78, 201, 176)}


def draw_code(d: ImageDraw.ImageDraw, x: float, y: float, text: str, f, lang: str) -> None:
    """Draw one source line with simple Dark+ token colours (OCR sees plain text either way)."""
    pos = 0
    cw = f.getlength("M") / SCALE
    for m in TOKEN.finditer(text):
        if m.start() > pos:
            d.text(((x + pos * cw) * SCALE, y * SCALE), text[pos:m.start()], fill=TEXT, font=f)
        kind = m.lastgroup or ""
        if kind == "comment" and lang == "js" and text[m.start()] == "#":
            kind = ""
        if kind == "comment" and lang in ("py", "todo") and text[m.start()] == "/":
            kind = ""
        d.text(((x + m.start() * cw) * SCALE, y * SCALE), m.group(0), fill=COLORS.get(kind, TEXT), font=f)
        pos = m.end()
    if pos < len(text):
        d.text(((x + pos * cw) * SCALE, y * SCALE), text[pos:], fill=TEXT, font=f)


# ---------------------------------------------------------------- the screen

@dataclass
class Screen:
    front_app: str = "Code"
    windows: list[Window] = field(default_factory=list)  # front-to-back (fixture order)
    drawn: list[Drawn] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.img = Image.new("RGB", (int(W * SCALE), int(H * SCALE)), BG)
        self.d = ImageDraw.Draw(self.img)
        self._menu_bar()

    # -- primitives
    def rect(self, x, y, w, h, fill, outline=None):
        self.d.rectangle([x * SCALE, y * SCALE, (x + w) * SCALE - 1, (y + h) * SCALE - 1], fill=fill, outline=outline)

    def text(self, x, y, s, f, fill=TEXT, app="", kind="ui", **kw) -> Drawn:
        self.d.text((x * SCALE, y * SCALE), s, fill=fill, font=f)
        l, t, r, b = self.d.textbbox((x * SCALE, y * SCALE), s, font=f)
        dr = Drawn(app, kind, s, (l / SCALE, t / SCALE, (r - l) / SCALE, (b - t) / SCALE), **kw)
        self.drawn.append(dr)
        return dr

    def _menu_bar(self) -> None:
        self.rect(0, 0, W, MENU_H, (44, 44, 46))
        f = font(UI, 13.5)
        x = 40
        for i, m in enumerate([self.front_app, "File", "Edit", "Selection", "View", "Go", "Run", "Window", "Help"]):
            self.d.text((x * SCALE, 9 * SCALE), m, fill=(235, 235, 235), font=font(UI, 13.5) if i else ImageFont.truetype(UI, int(13.5 * SCALE)))
            x += f.getlength(m) / SCALE + 22
        self.d.text(((W - 170) * SCALE, 9 * SCALE), "Sat Nov 14  3:12 PM", fill=(235, 235, 235), font=f)

    def _title_bar(self, win: Window, h: float = 28) -> None:
        x, y, w, _ = win.rect
        self.rect(x, y, w, h, TITLE_BG)
        for i, c in enumerate([(255, 95, 87), (254, 188, 46), (40, 200, 64)]):
            cx, cy = x + 16 + i * 20, y + h / 2
            self.d.ellipse([(cx - 6) * SCALE, (cy - 6) * SCALE, (cx + 6) * SCALE, (cy + 6) * SCALE], fill=c)
        f = font(UI, 13)
        tw = f.getlength(win.title) / SCALE
        self.text(x + (w - tw) / 2, y + 7, win.title, f, fill=(200, 200, 200), app=win.app)

    # -- VS Code
    def vscode(self, rect, *, folder: str, tree: list[tuple[int, str]], tabs: list[str], active: str,
               file_path: str, lines: list[str], lang: str, cursor_line: int = 1, dirty: bool = False,
               notebook: list[dict] | None = None, first_line: int = 1) -> Window:
        title = f"{'● ' if dirty else ''}{active} — {folder}"
        win = Window("Code", title, rect)
        self.windows.append(win)
        x, y, w, h = rect
        self.rect(x, y, w, h, EDITOR_BG, outline=(60, 60, 60))
        self._title_bar(win, 35)
        top = y + 35
        # activity bar + sidebar
        self.rect(x, top, 48, h - 35 - 22, (24, 24, 24))
        side_w = 220
        self.rect(x + 48, top, side_w, h - 35 - 22, SIDEBAR_BG)
        f_ui = font(UI, 12.5)
        self.text(x + 60, top + 10, "EXPLORER", font(UI, 11), fill=DIM, app="Code")
        self.text(x + 60, top + 34, folder.upper(), font(UI, 11.5), fill=TEXT, app="Code")
        ty = top + 56
        for depth, name in tree:
            self.text(x + 66 + depth * 12, ty, name, f_ui, fill=TEXT if name != active else (255, 255, 255), app="Code")
            ty += 22
        ex = x + 48 + side_w
        ew = w - 48 - side_w
        # tabs
        self.rect(ex, top, ew, 35, (24, 24, 24))
        tx = ex
        for t in tabs:
            tw = f_ui.getlength(t) / SCALE + 44
            self.rect(tx, top, tw, 35, EDITOR_BG if t == active else (45, 45, 45))
            self.text(tx + 14, top + 10, t, f_ui, fill=(255, 255, 255) if t == active else DIM, app="Code")
            tx += tw
        # breadcrumbs
        crumbs = " › ".join(file_path.split("/"))
        self.text(ex + 14, top + 41, crumbs, font(UI, 11.5), fill=DIM, app="Code")
        body_top = top + 62
        # status bar
        self.rect(x, y + h - 22, w, 22, (0, 122, 204))
        status = f"Ln {cursor_line}, Col 1   Spaces: {2 if lang == 'js' else 4}   UTF-8   LF   " + \
                 {"js": "JavaScript", "py": "Python", "todo": "Git Rebase Message", "ipynb": "Python 3.12.7 (.venv)"}.get(lang, "Plain Text")
        sf = font(UI, 11.5)
        self.text(x + w - sf.getlength(status) / SCALE - 16, y + h - 18, status, sf, fill=(255, 255, 255), app="Code")
        self.text(x + 12, y + h - 18, "main*" if lang != "todo" else "feature/login", sf, fill=(255, 255, 255), app="Code")
        if notebook is not None:
            self._notebook(ex, body_top, ew, y + h - 22 - body_top, notebook, file_path)
            return win
        f = font(MONO, 12)
        lh = 18
        for i, src in enumerate(lines):
            n = first_line + i
            ly = body_top + i * lh
            if ly + lh > y + h - 22:
                break
            if n == cursor_line:
                self.rect(ex, ly - 2, ew, lh, (40, 40, 40))
            num = f"{n:>3}"
            self.text(ex + 6, ly, num, f, fill=(110, 118, 129) if n != cursor_line else (198, 198, 198), app="Code",
                      kind="gutter", line=n, file=file_path)
            if src.strip():
                self.text_code(ex + 50, ly, src, f, lang, line=n, file=file_path)
        return win

    def text_code(self, x, y, src, f, lang, *, line, file):
        draw_code(self.d, x, y, src, f, lang)
        lead = len(src) - len(src.lstrip())
        cw = f.getlength("M") / SCALE
        s = src.strip()
        l, t, r, b = self.d.textbbox(((x + lead * cw) * SCALE, y * SCALE), s, font=f)
        self.drawn.append(Drawn("Code", "editor", s, (l / SCALE, t / SCALE, (r - l) / SCALE, (b - t) / SCALE), line=line, file=file))

    def _notebook(self, x, y, w, h, cells: list[dict], file_path: str) -> None:
        """VS Code's notebook editor: [n] gutter, a code box per cell, plain-text outputs below it."""
        f = font(MONO, 12)
        lh = 18
        cy = y + 6
        line_no = 0
        for cell in cells:
            src = cell["source"].splitlines()
            box_h = len(src) * lh + 16
            if cy + 20 > y + h:
                break
            self.rect(x + 46, cy, w - 66, box_h, (37, 37, 38), outline=(60, 60, 60))
            if cell.get("count") is not None:
                self.text(x + 8, cy + 8, f"[{cell['count']}]", font(MONO, 11), fill=DIM, app="Code", kind="gutter")
            for i, s in enumerate(src):
                line_no += 1
                if s.strip():
                    self.text_code(x + 60, cy + 8 + i * lh, s, f, "py", line=line_no, file=file_path)
            cy += box_h + 6
            for out in cell.get("outputs", []):
                for s in out.splitlines() or [""]:
                    if cy + lh > y + h:
                        break
                    if s.strip():
                        col = (241, 76, 76) if re.match(r"^\w*(Error|Exception)\b", s) else TEXT
                        self.text(x + 60, cy, s[:118], font(MONO, 11.5), fill=col, app="Code", kind="output")
                    cy += lh - 1
            cy += 12

    # -- Terminal.app
    def terminal(self, rect, *, title: str, lines: list[str]) -> Window:
        win = Window("Terminal", title, rect)
        self.windows.append(win)
        x, y, w, h = rect
        self.rect(x, y, w, h, TERM_BG, outline=(70, 70, 70))
        self._title_bar(win)
        f = font(MONO, 12)
        lh = 15
        cols = int((w - 16) / (f.getlength("M") / SCALE))
        wrapped: list[str] = []
        for ln in lines:
            ln = ln.expandtabs(8)
            while len(ln) > cols:
                wrapped.append(ln[:cols])
                ln = ln[cols:]
            wrapped.append(ln)
        rows = int((h - 28 - 12) / lh)
        shown = wrapped[-rows:]
        for i, ln in enumerate(shown):
            if ln.strip():
                col = TERM_FG
                if re.search(r"\b(error|ERROR|CONFLICT|fatal|Failed)\b", ln):
                    col = (255, 110, 103)
                self.text(x + 8, y + 34 + i * lh, ln, f, fill=col, app="Terminal", kind="terminal")
        return win

    # -- Chrome showing the app
    def chrome(self, rect, *, tab: str, url: str, body: list[tuple[str, float]]) -> Window:
        win = Window("Google Chrome", f"{tab} - Google Chrome", rect)
        self.windows.append(win)
        x, y, w, h = rect
        self.rect(x, y, w, h, (255, 255, 255), outline=(70, 70, 70))
        self.rect(x, y, w, 76, (53, 54, 58))
        for i, c in enumerate([(255, 95, 87), (254, 188, 46), (40, 200, 64)]):
            cx, cy = x + 16 + i * 20, y + 18
            self.d.ellipse([(cx - 6) * SCALE, (cy - 6) * SCALE, (cx + 6) * SCALE, (cy + 6) * SCALE], fill=c)
        self.rect(x + 80, y + 6, 220, 28, (80, 80, 84))
        self.text(x + 96, y + 12, tab, font(UI, 12), fill=(230, 230, 230), app="Google Chrome")
        self.rect(x + 80, y + 42, w - 100, 26, (32, 33, 36))
        self.text(x + 96, y + 47, url, font(UI, 12.5), fill=(230, 230, 230), app="Google Chrome")
        by = y + 110
        for s, pt in body:
            dr = self.text(x + 40, by, s, font(UI, pt), fill=(20, 20, 20), app="Google Chrome", kind="browser")
            by += dr.rect[3] + 18
        return win

    # -- output
    def save(self, png: Path) -> None:
        png.parent.mkdir(parents=True, exist_ok=True)
        self.img.save(png, optimize=True)
        meta = {"screen": {"x": 0.0, "y": 0.0, "w": float(W), "h": float(H)}, "scale": SCALE,
                "app": self.front_app, "windows": [w.to_dict() for w in reversed(self.windows)]}  # front-to-back
        png.with_suffix(".json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))

    def find(self, pattern: str, app: str | None = None, kind: str | None = None) -> Drawn | None:
        rx = re.compile(pattern)
        for dr in self.drawn:
            if (app is None or dr.app == app) and (kind is None or dr.kind == kind) and rx.search(dr.text):
                return dr
        return None


def centre(dr: Drawn, dx: float = 0.0) -> tuple[float, float]:
    x, y, w, h = dr.rect
    return (round(x + min(w / 2, 60) + dx, 1), round(y + h / 2, 1))


def ocr(png: Path):
    """The engine's own path: Vision OCR + window assignment + reading order on the saved screenshot."""
    from server.screen.reader import observe_image

    return observe_image(str(png))

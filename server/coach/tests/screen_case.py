"""A synthetic but realistic screen for tests and recordings: an editor pane with the hero code and a
terminal pane with the oscillating loss, rendered at Retina scale, one box per line (as AX/OCR give).
No binary fixture is committed; the image is drawn on the fly (Menlo if present, else Pillow's font).
"""

from __future__ import annotations

from server.coach.case_diffusion import HIGH_LR_CODE
from server.coach.screen import Box, ScreenContext

SCREEN_W, SCREEN_H, SCALE = 1440, 900, 2.0
EDITOR = (0, 30, 860, 860)  # x, y, w, h in points
TERMINAL = (870, 420, 570, 470)
LINE_H = 15
TERMINAL_LINES = [
    "$ python pinn_diffusion.py",
    "iter 3000 | loss 1.9300 | rel_l2 0.98",
    "iter 3250 | loss 0.4800 | rel_l2 0.66",
    "iter 3500 | loss 2.1200 | rel_l2 1.01",
    "iter 3750 | loss 0.6200 | rel_l2 0.71",
    "iter 4000 | loss 1.3700 | rel_l2 0.86",
    "iter 4250 | loss 0.3900 | rel_l2 0.60",
    "iter 4500 | loss 1.8800 | rel_l2 0.97",
    "iter 4750 | loss 0.5700 | rel_l2 0.68",
    "iter 5000 | loss 0.8400 | rel_l2 0.71",
]


def _font(px: int):
    from PIL import ImageFont

    for path in ("/System/Library/Fonts/Menlo.ttc", "/System/Library/Fonts/Monaco.ttf"):
        try:
            return ImageFont.truetype(path, px)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=px)
    except TypeError:
        return ImageFont.load_default()


def make_screen(code: str = HIGH_LR_CODE, cursor: tuple[float, float] | None = None) -> ScreenContext:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (int(SCREEN_W * SCALE), int(SCREEN_H * SCALE)), (30, 30, 30))
    d = ImageDraw.Draw(img)
    font = _font(int(11 * SCALE))
    boxes: list[Box] = []

    def pane(rect, title, lines, app, numbered):
        x, y, w, h = rect
        d.rectangle([x * SCALE, y * SCALE, (x + w) * SCALE, (y + h) * SCALE], fill=(37, 37, 38), outline=(70, 70, 70))
        d.text(((x + 8) * SCALE, (y + 4) * SCALE), title, fill=(200, 200, 200), font=font)
        boxes.append(Box(0, title, x + 8, y + 4, 7 * len(title), 13, source="ax", app=app, role="AXTitle"))
        for i, text in enumerate(lines):
            ly = y + 24 + i * LINE_H
            if ly + LINE_H > y + h:
                break
            tx = x + (44 if numbered else 8)
            if numbered:
                d.text(((x + 8) * SCALE, ly * SCALE), f"{i + 1:>3}", fill=(110, 110, 110), font=font)
            if text.strip():
                d.text((tx * SCALE, ly * SCALE), text, fill=(212, 212, 212), font=font)
                boxes.append(Box(0, text.strip(), tx + 6.6 * (len(text) - len(text.lstrip())), ly, 6.6 * len(text.strip()), 13, source="ax" if numbered else "ocr", app=app))

    pane(EDITOR, "pinn_diffusion.py — pinn_demo", HIGH_LR_CODE.splitlines() if code is None else code.splitlines(), "Code", True)
    pane(TERMINAL, "Terminal — python", TERMINAL_LINES, "Terminal", False)
    if cursor is None:  # resting on the terminal's last loss line
        cursor = (TERMINAL[0] + 120, TERMINAL[1] + 24 + (len(TERMINAL_LINES) - 1) * LINE_H + 6)
    return ScreenContext(image=img, cursor=cursor, boxes=boxes, scale=SCALE, app="Terminal", file="pinn_diffusion.py").numbered()


def box_id_containing(screen: ScreenContext, needle: str) -> int:
    return next(b.id for b in screen.boxes if needle in b.text)

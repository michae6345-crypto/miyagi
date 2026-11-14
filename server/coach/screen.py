"""What the coach sees: a set-of-mark screen payload (docs/research/screen-understanding.md, L4).

Input: a screenshot plus text boxes from the accessibility tree / OCR (E6 `server.screen`),
all rects in macOS screen POINTS with a top-left origin (same space as the `spotlight` event),
and the cursor position. Output for the model:
  1. a 1280-px-wide overview with every box outlined and numbered and the cursor drawn;
  2. a full-resolution 400x400 crop around the cursor (code is unreadable at 1280);
  3. the numbered box list (id, source, app, text, rect);
  4. "Cursor at (x, y) over [id] "<text>" (<app>), line N of <file>".
The model answers with box ids; `resolve_targets` turns them back into screen rects.
"""

from __future__ import annotations

import base64
import io
import json
import math
from dataclasses import dataclass, field
from typing import Any

OVERVIEW_WIDTH = 1280
CROP_PX = 400
MAX_BOXES = 120


@dataclass
class Box:
    id: int
    text: str
    x: float
    y: float
    w: float
    h: float
    source: str = "ocr"  # "ax" | "ocr"
    app: str = ""
    role: str = ""

    def contains(self, px: float, py: float) -> bool:
        return self.x <= px <= self.x + self.w and self.y <= py <= self.y + self.h

    def distance(self, px: float, py: float) -> float:
        dx = max(self.x - px, 0.0, px - (self.x + self.w))
        dy = max(self.y - py, 0.0, py - (self.y + self.h))
        return math.hypot(dx, dy)

    def rect(self) -> dict:
        return {"x": round(self.x, 1), "y": round(self.y, 1), "w": round(self.w, 1), "h": round(self.h, 1)}


def _rect(r: Any) -> tuple[float, float, float, float]:
    if isinstance(r, dict):
        return float(r["x"]), float(r["y"]), float(r.get("w", r.get("width"))), float(r.get("h", r.get("height")))
    if hasattr(r, "x") and hasattr(r, "w"):
        return float(r.x), float(r.y), float(r.w), float(r.h)
    x, y, w, h = r
    return float(x), float(y), float(w), float(h)


def _get(o: Any, k: str, default: Any = None) -> Any:
    return o.get(k, default) if isinstance(o, dict) else getattr(o, k, default)


@dataclass
class ScreenContext:
    """One captured moment. `image` is a PIL image, PNG/JPEG bytes, or a file path."""

    image: Any
    cursor: tuple[float, float]
    boxes: list[Box]
    scale: float = 2.0  # image pixels per point (Retina = 2)
    origin: tuple[float, float] = (0.0, 0.0)  # screen point at image pixel (0, 0)
    app: str = ""
    file: str = ""  # focused editor file (AX `AXDocument`)
    line: int | None = None  # caret / hovered line (AX)
    element: str = ""  # AX element under the cursor, e.g. 'AXButton "Run"'
    _img: Any = field(default=None, repr=False)

    @classmethod
    def from_observation(cls, obs: Any, image: Any, cursor: tuple[float, float], **extra: Any) -> ScreenContext:
        """Adapter for E6 `ScreenObservation` (or a dict): `blocks[{text, rect, app}]`, `scale`, `screen`."""
        blocks = _get(obs, "blocks", []) or []
        boxes = []
        for b in blocks:
            text = str(_get(b, "text", "")).strip()
            if not text:
                continue
            x, y, w, h = _rect(_get(b, "rect"))
            boxes.append(Box(0, text, x, y, w, h, source=_get(b, "source", "ocr") or "ocr", app=_get(b, "app", "") or "", role=_get(b, "role", "") or ""))
        screen = _get(obs, "screen")
        origin = _rect(screen)[:2] if screen is not None else (0.0, 0.0)
        ctx = cls(image=image, cursor=cursor, boxes=boxes, scale=float(_get(obs, "scale", 2.0) or 2.0), origin=origin, app=_get(obs, "app", "") or "", **extra)
        return ctx.numbered()

    def numbered(self) -> ScreenContext:
        """Keep the MAX_BOXES boxes nearest the cursor, numbered 1..N in reading order."""
        cx, cy = self.cursor
        keep = sorted(self.boxes, key=lambda b: b.distance(cx, cy))[:MAX_BOXES]
        keep.sort(key=lambda b: (round(b.y / 4), b.x))
        for i, b in enumerate(keep, start=1):
            b.id = i
        self.boxes = keep
        return self

    # ---------- geometry ---------------------------------------------------------------
    def pil(self):
        if self._img is None:
            from PIL import Image

            img = self.image
            if isinstance(img, (bytes, bytearray)):
                img = Image.open(io.BytesIO(img))
            elif isinstance(img, str):
                img = Image.open(img)
            self._img = img.convert("RGB")
        return self._img

    def to_px(self, x: float, y: float) -> tuple[float, float]:
        return (x - self.origin[0]) * self.scale, (y - self.origin[1]) * self.scale

    def box_under_cursor(self) -> Box | None:
        cx, cy = self.cursor
        inside = [b for b in self.boxes if b.contains(cx, cy)]
        if inside:
            return min(inside, key=lambda b: b.w * b.h)
        near = min(self.boxes, key=lambda b: b.distance(cx, cy), default=None)
        return near if near is not None and near.distance(cx, cy) <= 40 else None

    def by_id(self) -> dict[int, Box]:
        return {b.id: b for b in self.boxes}

    # ---------- what the model reads ---------------------------------------------------
    def cursor_line(self) -> str:
        cx, cy = self.cursor
        s = f"Cursor at ({cx:.0f}, {cy:.0f})"
        if b := self.box_under_cursor():
            s += f' over [{b.id}] "{b.text[:80]}"' + (f" ({b.app})" if b.app else "")
        if self.element:
            s += f", element {self.element}"
        if self.line is not None:
            s += f", line {self.line}" + (f" of {self.file}" if self.file else "")
        elif self.file:
            s += f", file {self.file}"
        return s

    def box_list(self) -> str:
        return "\n".join(
            f"[{b.id}] {b.source}{'/' + b.role if b.role else ''}{' ' + b.app if b.app else ''} "
            f"@({b.x:.0f},{b.y:.0f},{b.w:.0f}x{b.h:.0f}) {b.text[:120]!r}"
            for b in self.boxes
        )

    def text(self) -> str:
        return (
            f"SCREEN (frontmost app: {self.app or 'unknown'}). Two images follow: the whole screen at "
            f"{OVERVIEW_WIDTH} px wide and a full-resolution {CROP_PX}x{CROP_PX} px crop around the cursor. "
            "Every text box is outlined and numbered; the red ring is the cursor.\n"
            f"{self.cursor_line()}\nBOXES (id source app @(x,y,w x h in screen points) text):\n{self.box_list()}"
        )

    # ---------- images -----------------------------------------------------------------
    def _draw(self, img, to_img, font_px: int, only: set[int] | None = None):
        from PIL import ImageDraw, ImageFont

        d = ImageDraw.Draw(img)
        try:
            font = ImageFont.load_default(size=font_px)
        except TypeError:  # Pillow < 10.1
            font = ImageFont.load_default()
        for b in self.boxes:
            if only is not None and b.id not in only:
                continue
            x0, y0 = to_img(b.x, b.y)
            x1, y1 = to_img(b.x + b.w, b.y + b.h)
            d.rectangle([x0, y0, x1, y1], outline=(0, 140, 255), width=1)
            # label in the left margin, vertically centred, so it never hides the box's own text
            label = str(b.id)
            tw = d.textlength(label, font=font)
            lx = x0 - tw - 6 if x0 - tw - 6 >= 0 else max(0.0, x0) + 1
            ly = max(0.0, (y0 + y1) / 2 - font_px / 2 - 1)
            d.rectangle([lx, ly, lx + tw + 4, ly + font_px + 2], fill=(0, 140, 255))
            d.text((lx + 2, ly), label, fill=(255, 255, 255), font=font)
        cx, cy = to_img(*self.cursor)
        r = max(6, font_px)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 0, 0), width=3)
        d.line([cx - 2 * r, cy, cx + 2 * r, cy], fill=(255, 0, 0), width=1)
        d.line([cx, cy - 2 * r, cx, cy + 2 * r], fill=(255, 0, 0), width=1)
        return img

    def overview(self):
        """Whole screen downscaled to OVERVIEW_WIDTH px wide, boxes numbered, cursor drawn."""
        src = self.pil()
        f = OVERVIEW_WIDTH / src.width
        img = src.resize((OVERVIEW_WIDTH, max(1, round(src.height * f))))

        def to_img(x, y):
            px, py = self.to_px(x, y)
            return px * f, py * f

        return self._draw(img, to_img, font_px=10)

    def crop(self):
        """Full-resolution CROP_PX square centred on the cursor (clamped to the image)."""
        src = self.pil()
        px, py = self.to_px(*self.cursor)
        w, h = min(CROP_PX, src.width), min(CROP_PX, src.height)
        x0 = int(min(max(px - w / 2, 0), src.width - w))
        y0 = int(min(max(py - h / 2, 0), src.height - h))
        img = src.crop((x0, y0, x0 + w, y0 + h))

        def to_img(x, y):
            qx, qy = self.to_px(x, y)
            return qx - x0, qy - y0

        visible = {b.id for b in self.boxes if _overlaps(self.to_px(b.x, b.y), self.to_px(b.x + b.w, b.y + b.h), (x0, y0, x0 + w, y0 + h))}
        return self._draw(img, to_img, font_px=14, only=visible)

    def jpeg(self, img, quality: int = 80) -> bytes:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        return buf.getvalue()

    def claude_content(self) -> list[dict]:
        """Anthropic content blocks: instructions/context text first, then the two images."""
        def block(b: bytes) -> dict:
            return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(b).decode()}}

        return [{"type": "text", "text": self.text()}, block(self.jpeg(self.overview())), block(self.jpeg(self.crop()))]

    def resolve_targets(self, targets: list[dict]) -> list[dict]:
        """Model output [{box_id, label}] → [{boxId, label, text, rect}] in screen points; unknown ids dropped."""
        ids = self.by_id()
        out = []
        for t in targets or []:
            b = ids.get(int(t.get("box_id", -1)))
            if b is not None and all(o["boxId"] != b.id for o in out):
                out.append({"boxId": b.id, "label": str(t.get("label", ""))[:40], "text": b.text, "rect": b.rect()})
        return out


def parse_targets_prefix(snapshot: str) -> list[dict] | None:
    """The `targets` array from a partial JSON reply, as soon as its closing bracket has streamed."""
    i = snapshot.find('"targets"')
    if i < 0:
        return None
    j = snapshot.find("[", i)
    if j < 0:
        return None
    try:
        val, _ = json.JSONDecoder().raw_decode(snapshot[j:])
    except json.JSONDecodeError:
        return None
    return val if isinstance(val, list) else None


class TargetStream:
    """`on_text` handler: fires `on_targets(resolved)` once, the moment the targets array is complete."""

    def __init__(self, screen: ScreenContext, on_targets):
        self.screen, self.on_targets, self.fired = screen, on_targets, None

    async def __call__(self, delta: str, snapshot: str) -> None:
        if self.fired is not None or self.on_targets is None:
            return
        if (t := parse_targets_prefix(snapshot)) is not None:
            self.fired = self.screen.resolve_targets(t)
            r = self.on_targets(self.fired)
            if hasattr(r, "__await__"):
                await r


def _overlaps(p0, p1, rect) -> bool:
    x0, y0, x1, y1 = rect
    return not (p1[0] < x0 or p0[0] > x1 or p1[1] < y0 or p0[1] > y1)


TARGETS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {"box_id": {"type": "integer"}, "label": {"type": "string"}},
        "required": ["box_id", "label"],
        "additionalProperties": False,
    },
}

TARGETS_RULES = """
SCREEN TARGETS: when a SCREEN is attached, "targets" comes first in your JSON: up to 3 box ids from the BOXES list for exactly what the learner should look at or change, most important first, each with a label of at most 3 words (e.g. "learning rate", "loss term"). Only ids that exist in the list; [] if nothing on screen is relevant. Read code from the full-resolution crop when the overview is too small."""

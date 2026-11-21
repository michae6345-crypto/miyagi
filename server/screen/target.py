"""Pick WHAT to box on screen: Claude Haiku vision + set-of-marks over the OCR (VS Code only).

    res = await pick_target(frame, obs, "the VS Code integrated terminal panel")       # pure
    res = await pick_on_screen("the line where the learner types `def add(a, b):`")   # live reader
    -> {"rect": {x, y, w, h}, "box_ids": [12], "label": "code L4: def add(a, b):", "kind": "code",
        "confidence": 0.93, "reason": "...", "ms": 910, "api_ms": 860, "cached": False} | None

How:
1. Candidates = E6's `marks.candidates(obs)`: regions with fixed ids (1 terminal, 2 editor,
   3 explorer, 4 terminal_menu, 5 run_button), then editor rows from id 10 (code and blank, even
   when Vision reads no line numbers), then other OCR lines; never the breadcrumb, tab bar, title
   bar, hover tooltips or a side bar such as Chat. Callers can add `extra` marks (ids from 500).
   Miyagi's own UI is never a candidate: lines under the app's `overlay.bounds` (frame-time and
   current) are dropped and blacked out, and so are lines that read as text Miyagi itself is showing
   (`note_ui_text`, fed from every emitted card / caption / step), for when the bounds miss it.
2. The frame is cropped to the candidates, downscaled to <= 1280 px wide, and every candidate gets
   a small numbered tag. ONE Haiku request (`claude-haiku-5-5`, thinking off, effort low,
   max_tokens 160, structured output `output_config.format` = SCHEMA) returns JSON
   `{"ids": [...], "confidence": 0..1, "why": "..."}`; parse_answer still reads it leniently.
3. Ids map back to the candidates' rects (screen points, top-left of the primary display: the
   `spotlight` space). Several ids are merged only when they are adjacent rows of one block.
4. Low confidence (< MIYAGI_VISION_MIN_CONF, default 0.6), no ids, a timeout (2.5 s), an API error,
   or the budget (MIYAGI_VISION_MAX_CALLS_PER_MIN, default 6) -> None: no box beats a wrong box,
   and the caller's own locate path stays in charge.

Cache: by (frame content hash, intent, app). The frame hash is the hash of the candidate set (ids,
kinds, OCR text, rects snapped to 4 pt), i.e. what the model is shown; a blinking caret or a
cursor move doesn't bust it, a changed line does. Answers (including "nothing") are kept 120 s.
Per question (intent: the step's action + code, so per step) the last answer is also kept and reused
across frames: a pick stands while its rows are still in place and the rows above them are unchanged
(the learner typing into / below the picked line doesn't re-ask); "nothing" is held 6 s; an error,
timeout or low-confidence pick is retried only after a backoff (3, 6, 12, 24, 30 s). One call per
question at a time. The 6 calls/min budget stays.
Cost: every call logs input/output tokens and a running $ estimate; `stats()` returns the totals.
Sampling: Haiku 5.5 rejects `temperature` != default, so it isn't sent. Determinism comes from
thinking off + effort low + strict JSON + the cache.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import logging
import math
import os
import re
import time
from collections import OrderedDict, deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from . import marks as MK
from . import match as M
from .types import Block, Rect, ScreenObservation

log = logging.getLogger("server.screen.target")

MODEL = os.environ.get("MIYAGI_VISION_MODEL", "claude-haiku-5-5")
MAX_TOKENS = 160
MAX_W = 1280
EXTRA_ID = 500                         # our extra candidates; E6's ids (1-4, 10..) stay untouched
CACHE_TTL = 120.0
CACHE_MAX = 128
RETRY_BASE_S, RETRY_MAX_S = 3.0, 30.0  # a failed / low-confidence pick is asked again after 3, 6, 12, 24, 30 s
NONE_HOLD_S = 2.0                      # "nothing matches" held 2 s on a changed screen (< _lesson_spot's 3 s retry)
OVERLAY_PAD = 6.0                      # pt around each overlay.bounds rect (edges, shadows, a late report)
UI_TEXT_TTL = 600.0                    # s a string Miyagi showed counts as "ours" (note_ui_text)

# Structured output: the answer is always this JSON object (ids first, so a cut-off answer still has them).
SCHEMA = {
    "type": "object",
    "properties": {"ids": {"type": "array", "items": {"type": "integer"}},
                   "confidence": {"type": "number"},
                   "why": {"type": "string"}},
    "required": ["ids", "confidence", "why"],
    "additionalProperties": False,
}
_FORMAT_OK = True                      # off for the process if the API ever rejects output_config.format

SYSTEM = (
    "You choose what a coding tutor highlights on a learner's screen (VS Code on macOS). The screenshot "
    "has numbered tags: a yellow tag sits just left of a line of text (for editor rows it is in the "
    "line-number gutter; `blank` rows are empty lines), a cyan tag marks a region outlined in cyan: a "
    "panel (terminal, editor, explorer) or one control (terminal_menu = the Terminal menu in the menu "
    "bar, run_button = the Run ▷ button). The list gives each tag's id, kind and OCR text; OCR can "
    "garble or drop characters, so check the image.\n"
    "Pick the id(s) that exactly match the request. Several ids only for adjacent rows of one block of "
    "code. If the request is where the learner should TYPE code that is not on screen yet, pick the "
    "blank line where it goes. Breadcrumbs, editor tabs and hover tooltips are never the answer. If "
    "nothing on screen matches, return no ids: a wrong highlight is worse than none.\n"
    'Reply with JSON only: {"ids": [<int>, ...], "confidence": <0..1, how sure the ids are exactly '
    'right>, "why": "<at most 12 words>"}'
)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


# ---------------------------------------------------------------------- candidates

@dataclass
class Cand:
    id: int
    kind: str                     # region | code | blank | text | toolbar
    text: str
    rect: Rect
    line: int | None = None       # editor file line (code / blank rows), when the gutter was read
    region: str | None = None     # region name, or the region a line sits in
    occluded: bool = False

    def tag(self) -> str:
        if self.kind == "region":
            return "region"
        if self.kind in ("code", "blank"):
            t = f"{self.kind} L{self.line}" if self.line else self.kind
            return t + (", partly under a tooltip" if self.occluded else "")
        if self.kind == "toolbar":
            return "toolbar icon"
        return self.region or "screen"

    def label(self) -> str:
        if self.kind == "region":
            return f"{self.text} region"
        if self.kind == "blank":
            return f"{self.tag()} (empty line)"
        return f"{self.tag()}: {self.text}"


def _front_window(obs: ScreenObservation, app: str | None):
    for w in obs.windows:  # front to back
        if (M.app_matches(app, w.app, w.title) if app else True) and any(
                b.app == w.app and b.window == w.title for b in obs.blocks):
            return w
    return None


def build_candidates(obs: ScreenObservation, app: str | None = "Code", *, regions: dict | None = None,
                     exclude: Sequence = (), extra: Iterable = ()) -> list[Cand]:
    """E6's set-of-marks candidates (regions 1-5 incl. the run ▷, editor code/blank rows even without a
    readable gutter, other OCR lines; never breadcrumb / tab bar / tooltips / side bar) + `extra`.
    `regions`: stabilized region rects (reader.locate_region) or None (computed from `obs`).
    `exclude`: our overlay's rects; lines whose centre is inside (OVERLAY_PAD around) are dropped (regions are kept).
    `extra`: (kind, text, rect) tuples, ids from EXTRA_ID."""
    cands = [Cand(c.id, c.kind, c.text, c.rect, c.line, c.region, c.occluded)
             for c in MK.candidates(obs, None, app, regions=regions)]
    for i, (kind, text, rect) in enumerate(extra):
        cands.append(Cand(EXTRA_ID + i, kind, text, Rect.from_any(rect)))
    if exclude:
        ex = [Rect.from_any(r).pad(OVERLAY_PAD) for r in exclude]
        cands = [c for c in cands if c.kind == "region" or not any(r.contains(c.rect) for r in ex)]
    if obs.screen.w:
        cands = [c for c in cands if c.rect.clamp(obs.screen).w > 2 and c.rect.clamp(obs.screen).h > 2]
    return cands


def listing(cands: list[Cand], max_chars: int = 110) -> str:
    """One row per tag, editor rows in screen order: `12 [code L4] def add(a, b):`."""
    def order(c: Cand):
        grp = 0 if c.kind == "region" else 1 if c.kind in ("code", "blank") else 3 if c.kind == "toolbar" else 2
        return (grp, c.rect.x if grp == 1 else 0, c.rect.cy if grp in (1, 2) else c.id, c.id)
    rows = []
    for c in sorted(cands, key=order):
        t = "(empty line)" if c.kind == "blank" else c.text
        t = t if len(t) <= max_chars else t[: max_chars - 1] + "…"
        rows.append(f"{c.id} [{c.tag()}] {t}")
    return "\n".join(rows)


def signature(cands: list[Cand]) -> str:
    """The frame hash used by the cache: what the model is shown, snapped to 4 pt."""
    h = hashlib.blake2b(digest_size=16)
    for c in cands:
        r = c.rect
        h.update(f"{c.id}|{c.kind}|{c.text}|{round(r.x / 4)},{round(r.y / 4)},{round(r.w / 4)},"
                 f"{round(r.h / 4)}\n".encode())
    return h.hexdigest()


# ---------------------------------------------------------------------- marks image

_FONT_CACHE: dict[int, Any] = {}


def _font(size: int):
    from PIL import ImageFont
    f = _FONT_CACHE.get(size)
    if f is None:
        try:
            f = ImageFont.load_default(size=size)
        except TypeError:                     # Pillow < 10.1
            f = ImageFont.load_default()
        _FONT_CACHE[size] = f
    return f


def render_marks(frame, cands: list[Cand], obs: ScreenObservation, exclude: Sequence = (),
                 max_w: int = MAX_W, app: str | None = "Code") -> tuple[bytes, tuple[int, int]]:
    """Crop the frame to the front editor window + the candidates, downscale so neither side is over
    `max_w` px, draw the numbered tags -> JPEG."""
    from PIL import Image, ImageDraw
    scr = obs.screen if obs.screen.w else Rect(0, 0, frame.width / (obs.scale or 1.0), frame.height / (obs.scale or 1.0))
    s = frame.width / scr.w                                    # px per point
    win = _front_window(obs, app)
    u = win.rect if win is not None else cands[0].rect
    for c in cands:
        u = u.union(c.rect)
    u = u.pad(16).clamp(scr)
    box = (max(0, int((u.x - scr.x) * s)), max(0, int((u.y - scr.y) * s)),
           min(frame.width, math.ceil((u.x2 - scr.x) * s)), min(frame.height, math.ceil((u.y2 - scr.y) * s)))
    img = frame.crop(box).convert("RGB")
    k = min(1.0, max_w / img.width, max_w / img.height)
    if k < 1.0:
        img = img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))), Image.Resampling.LANCZOS)
    f = s * k                                                   # output px per point
    ox, oy = box[0] / s + scr.x, box[1] / s + scr.y             # crop origin in points

    def P(x: float, y: float) -> tuple[float, float]:
        return (x - ox) * f, (y - oy) * f

    d = ImageDraw.Draw(img, "RGBA")
    for r in exclude:                                           # our overlay: never shown to the model
        r = Rect.from_any(r).pad(OVERLAY_PAD)
        d.rectangle([*P(r.x, r.y), *P(r.x2, r.y2)], fill=(0, 0, 0, 255))
    font = _font(max(10, min(14, round(11 * max(1.0, f)))))

    def tag(x: float, y: float, text: str, fill) -> None:
        l, t, rr, b = d.textbbox((0, 0), text, font=font)
        w, h = rr - l + 4, b - t + 2
        x = min(max(0, x), img.width - w)
        y = min(max(0, y), img.height - h)
        d.rectangle([x, y, x + w, y + h], fill=fill, outline=(0, 0, 0, 255))
        d.text((x + 2 - l, y + 1 - t), text, fill=(0, 0, 0, 255), font=font)

    def size(text: str) -> tuple[int, int]:
        l, t, rr, b = d.textbbox((0, 0), text, font=font)
        return rr - l + 4, b - t + 2

    for c in sorted(cands, key=lambda c: c.kind != "region"):  # region outlines under the line tags
        x1, y1 = P(c.rect.x, c.rect.y)
        x2, y2 = P(c.rect.x2, c.rect.y2)
        w, h = size(str(c.id))
        if c.kind == "region":
            d.rectangle([x1, y1, x2, y2], outline=(0, 200, 255, 255), width=2)
            if y2 - y1 < 3 * h:
                tag((x1 + x2 - w) / 2, y2 + 1, str(c.id), (0, 200, 255, 255))
            else:
                tag(x2 - w - 3, y1 + 3, str(c.id), (0, 200, 255, 255))
        elif c.kind == "toolbar":
            d.rectangle([x1, y1, x2, y2], outline=(255, 64, 200, 255), width=1)
            tag((x1 + x2 - w) / 2, y2 + 1, str(c.id), (255, 120, 220, 255))
        else:
            if c.kind == "text":
                d.rectangle([x1 - 1, y1 - 1, x2 + 1, y2 + 1], outline=(255, 214, 0, 150), width=1)
            tag(x1 - w - 3, (y1 + y2 - h) / 2, str(c.id), (255, 214, 0, 255))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=82)
    return buf.getvalue(), img.size


# ---------------------------------------------------------------------- answer

_DECODER = json.JSONDecoder()


def _first_object(text: str) -> dict | None:
    """The first JSON object in `text` that has "ids" / "id" (else the first object at all): prose, code fences or
    a second object around it are ignored. A cut-off object (max_tokens) -> its "ids" and "confidence", if both
    made it out."""
    first = None
    for m in re.finditer(r"\{", text):
        try:
            obj, _end = _DECODER.raw_decode(text, m.start())
        except ValueError:
            continue
        if isinstance(obj, dict):
            if "ids" in obj or "id" in obj:
                return obj
            first = first if first is not None else obj
    if first is not None:
        return first
    ids = re.search(r'"ids?"\s*:\s*(\[[^\]\[{}]*\]|-?\d+|null)', text)
    conf = re.search(r'"confidence"\s*:\s*"?(-?\d+(?:\.\d+)?)', text)
    if ids is None or conf is None:
        return None
    try:
        return {"ids": json.loads(ids.group(1)), "confidence": conf.group(1)}
    except ValueError:
        return None


def parse_answer(text: str) -> tuple[list[int], float, str] | None:
    """`{"ids": [12], "confidence": 0.9, "why": "..."}` -> (ids, confidence 0..1, why). Lenient (see _first_object):
    code fences / stray prose around it are tolerated; None when there's no JSON answer in it."""
    d = _first_object(text or "")
    if d is None:
        return None
    raw = d.get("ids", d.get("id", []))
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raw = [raw]
    ids: list[int] = []
    for i in raw:
        try:
            v = int(str(i).strip().lstrip("#"))
        except ValueError:
            continue
        if v not in ids:
            ids.append(v)
    try:
        conf = float(d.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    conf = 0.0 if math.isnan(conf) else min(1.0, max(0.0, conf))
    return ids, conf, str(d.get("why") or "")[:200]


def _group(c: Cand) -> str:
    return "editor" if c.kind in ("code", "blank") else f"{c.kind}:{c.region}"


def merge(cands: list[Cand], ids: list[int]) -> tuple[list[Cand], Rect] | None:
    """The first valid id wins; later ids join it only when they're adjacent rows of the same group
    (one block of code / consecutive terminal lines). Regions and icons never merge."""
    by = {c.id: c for c in cands}
    picked = [by[i] for i in ids if i in by]
    if not picked:
        return None
    first = picked[0]
    group, r = [first], first.rect
    if first.kind not in ("region", "toolbar"):
        for c in picked[1:]:
            if _group(c) != _group(first) or len(group) >= 15:
                continue
            h = max(8.0, min(c.rect.h, first.rect.h))
            gap = max(c.rect.y - r.y2, r.y - c.rect.y2)
            xover = min(c.rect.x2, r.x2) - max(c.rect.x, r.x)
            if gap <= 1.6 * h and xover > 0:
                group.append(c)
                r = r.union(c.rect)
    return group, r


# ---------------------------------------------------------------------- budget, cache, stats

class _Budget:
    def __init__(self) -> None:
        self.calls: deque[float] = deque()

    def allow(self, now: float) -> bool:
        limit = _env_int("MIYAGI_VISION_MAX_CALLS_PER_MIN", 6)
        while self.calls and now - self.calls[0] > 60.0:
            self.calls.popleft()
        if limit <= 0 or len(self.calls) >= limit:
            return False
        self.calls.append(now)
        return True


@dataclass
class _Memo:
    """The last answer to one question (intent), whatever the frame: see _memo_answer."""
    t: float
    outcome: str
    conf: float
    res: dict | None
    rows: list[Cand]              # "picked": the picked rows, as they were
    context: tuple                # "picked": _context() of those rows when picked
    retry_at: float               # failed / "none": not asked again before this (_now())
    fails: int                    # consecutive failed / low-confidence asks


_now = time.monotonic             # the cache / memo clock (tests move it)
_BUDGET = _Budget()
_CACHE: OrderedDict[str, tuple[float, dict | None]] = OrderedDict()
_MEMO: OrderedDict[str, _Memo] = OrderedDict()
_INFLIGHT: dict[str, asyncio.Future] = {}
_CLIENTS: dict[str, Any] = {}
_STATS: dict[str, Any] = {}
_LAT: deque[float] = deque(maxlen=500)
_UI_TEXT: deque[tuple[float, str]] = deque(maxlen=64)


def reset() -> None:
    """Clear cache, budget and stats (tests)."""
    global _FORMAT_OK
    _FORMAT_OK = True
    _CACHE.clear()
    _MEMO.clear()
    _INFLIGHT.clear()
    _BUDGET.calls.clear()
    _LAT.clear()
    _UI_TEXT.clear()
    _STATS.clear()
    _STATS.update(calls=0, cache_hits=0, budget_skips=0, timeouts=0, errors=0, no_key=0, low_confidence=0,
                  none=0, picked=0, held=0, ours_dropped=0, input_tokens=0, output_tokens=0, cost_usd=0.0)


reset()


def stats() -> dict:
    """Totals since start: calls, cache hits, budget skips, timeouts, tokens, $ estimate, latency."""
    lat = sorted(_LAT)

    def pct(p: float) -> float | None:
        return round(lat[min(len(lat) - 1, int(p * len(lat)))], 1) if lat else None

    return {**_STATS, "cost_usd": round(_STATS["cost_usd"], 6), "api_ms_p50": pct(0.5), "api_ms_p95": pct(0.95)}


def _client_for(api_key: str | None):
    """A client for `api_key`, else server.config's key (Settings key > miyagi cloud token > .env). A cloud token
    goes to the miyagi cloud, any other key straight to Anthropic (server.config.anthropic_kwargs)."""
    from server import config as server_config

    key = api_key or server_config.get_key("anthropic") or ""
    if not key:
        return None
    kw = server_config.anthropic_kwargs("screen", key=key)
    h = hashlib.sha256(f"{key}\n{kw.get('base_url')}".encode()).hexdigest()
    c = _CLIENTS.get(h)
    if c is None:
        import anthropic
        c = anthropic.AsyncAnthropic(max_retries=0, **kw)
        _CLIENTS[h] = c
    return c


def _cost(resp, usage) -> float:
    """Dollars of one pick from the shared price table, also recorded in the lesson's session tally (screen)."""
    from server.lesson import cost as cost_mod

    m = getattr(resp, "model", None)
    m = m if isinstance(m, str) and m else MODEL
    try:
        return cost_mod.record_usage(m, usage or {}, source="screen", label="screen target")
    except Exception:  # noqa: BLE001 - cost accounting never breaks a pick
        log.debug("pick_target: cost record failed", exc_info=True)
        return 0.0


# ---------------------------------------------------------------------- the pick

# Outcome of one pick (pick_with_outcome / confirm_spot):
#   picked          the model chose a target, confidence >= the floor        -> the result dict
#   none            the model says nothing on screen matches                 -> None
#   low_confidence  it chose, but below the floor                            -> None
#   no_candidates | budget | no_key | timeout | error                       -> None (couldn't ask)
ASKED = ("picked", "none", "low_confidence")


def _as_obs(frame, ocr_boxes, app: str | None, screen) -> ScreenObservation:
    if isinstance(ocr_boxes, ScreenObservation):
        return ocr_boxes
    blocks = [b if isinstance(b, Block) else Block(b["text"], Rect.from_any(b["rect"]), float(b.get("confidence", 1.0)),
                                                   b.get("app"), b.get("window")) for b in ocr_boxes]
    scr = Rect.from_any(screen) if screen is not None else Rect(0, 0, float(frame.width), float(frame.height))
    return ScreenObservation(t=time.time(), app=app or "", blocks=blocks, screen=scr, scale=frame.width / scr.w)


async def pick_target(frame, ocr_boxes, intent: str, *, app: str | None = "Code", client=None,
                      api_key: str | None = None, regions: dict | None = None, exclude: Sequence = (),
                      extra: Iterable = (), screen=None, timeout: float | None = None,
                      min_conf: float | None = None) -> dict | None:
    """Which on-screen target matches `intent`? -> {rect, box_ids, label, kind, line, region,
    confidence, reason, ms, api_ms, cached, ...} or None (see module doc). `frame`: PIL image of the
    primary display (our overlay already masked); `ocr_boxes`: the ScreenObservation OCR'd from
    that frame (or a list of Blocks + `screen=` in points). `client`: AsyncAnthropic-like (tests: a stub)."""
    res, _, _ = await pick_with_outcome(frame, ocr_boxes, intent, app=app, client=client, api_key=api_key,
                                        regions=regions, exclude=exclude, extra=extra, screen=screen,
                                        timeout=timeout, min_conf=min_conf)
    return res


async def pick_with_outcome(frame, ocr_boxes, intent: str, *, app: str | None = "Code", client=None,
                            api_key: str | None = None, regions: dict | None = None, exclude: Sequence = (),
                            extra: Iterable = (), screen=None, timeout: float | None = None,
                            min_conf: float | None = None) -> tuple[dict | None, str, float]:
    """`pick_target` plus why: -> (result | None, outcome, model confidence). See ASKED / outcomes."""
    t0 = time.perf_counter()
    intent = (intent or "").strip()
    if not intent or frame is None:
        return None, "no_candidates", 0.0
    obs = _as_obs(frame, ocr_boxes, app, screen)
    cands = build_candidates(obs, app, regions=regions, exclude=exclude, extra=extra)
    cands, ours = _drop_ours(cands, intent)
    if not cands:
        return None, "no_candidates", 0.0
    qkey = hashlib.blake2b(f"{MODEL}|{app}|{intent.lower()}".encode(), digest_size=16).hexdigest()
    key = hashlib.blake2b(f"{MODEL}|{app}|{intent.lower()}|{signature(cands)}".encode(), digest_size=16).hexdigest()
    found, val = _cache_get(key)
    if found:
        _STATS["cache_hits"] += 1
        return val
    if (held := _memo_answer(qkey, cands, obs)) is not None:
        return held
    if qkey in _INFLIGHT:                      # the same question is already being asked (maybe on an older frame)
        try:
            res, outcome, conf = await asyncio.shield(_INFLIGHT[qkey])
        except Exception:  # noqa: BLE001
            return None, "error", 0.0
        return (dict(res, cached=True) if res else None), outcome, conf
    fut = asyncio.get_running_loop().create_future()
    _INFLIGHT[qkey] = fut
    out: tuple[dict | None, str, float] = (None, "error", 0.0)
    mask = [*exclude, *(c.rect for c in ours)]
    try:
        out = await _ask(frame, obs, cands, intent, key, client, api_key, mask, timeout, min_conf, t0, app)
        _remember(qkey, cands, *out)
        return out
    finally:
        _INFLIGHT.pop(qkey, None)
        if not fut.done():
            fut.set_result(out)


async def _ask(frame, obs, cands, intent, key, client, api_key, exclude, timeout, min_conf, t0,
               app) -> tuple[dict | None, str, float]:
    if not _BUDGET.allow(time.monotonic()):
        _STATS["budget_skips"] += 1
        log.warning("pick_target: budget of %d calls/min reached, skipped %r",
                    _env_int("MIYAGI_VISION_MAX_CALLS_PER_MIN", 6), intent[:60])
        return None, "budget", 0.0
    client = client or _client_for(api_key)
    if client is None:
        _STATS["no_key"] += 1
        if _STATS["no_key"] == 1:
            log.warning("pick_target: no Anthropic key (config.keys.anthropic / ANTHROPIC_API_KEY): skipped")
        return None, "no_key", 0.0
    global _FORMAT_OK
    jpeg, size = await asyncio.to_thread(render_marks, frame, cands, obs, exclude, MAX_W, app)
    text = f"Request: {intent}\n\nTags (id [kind] OCR text):\n{listing(cands)}"
    fmt = {"format": {"type": "json_schema", "schema": SCHEMA}} if _FORMAT_OK else {}
    kwargs = {"model": MODEL, "max_tokens": MAX_TOKENS, "system": SYSTEM,
              "thinking": {"type": "disabled"}, "output_config": {"effort": "low", **fmt},
              "messages": [{"role": "user", "content": [
                  {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                               "data": base64.standard_b64encode(jpeg).decode("ascii")}},
                  {"type": "text", "text": text}]}]}
    t = timeout if timeout is not None else _env_float("MIYAGI_VISION_TIMEOUT_S", 2.5)
    c = client.with_options(timeout=t, max_retries=0) if hasattr(client, "with_options") else client
    _STATS["calls"] += 1
    ta = time.perf_counter()
    try:
        resp = await asyncio.wait_for(c.messages.create(**kwargs), t)
    except TimeoutError:
        _STATS["timeouts"] += 1
        log.info("pick_target: timeout after %.1fs for %r", t, intent[:60])
        return None, "timeout", 0.0
    except Exception as e:  # noqa: BLE001  (auth / rate limit / overload / network: the locate path wins)
        timed_out = "Timeout" in type(e).__name__
        _STATS["timeouts" if timed_out else "errors"] += 1
        from server import config as server_config
        server_config.cloud_error(e)  # an unknown install token heals in the app (cloud.token_invalid)
        log.warning("pick_target: %s: %s", type(e).__name__, str(e)[:200])
        if fmt and getattr(e, "status_code", None) == 400 and re.search(r"output_config|schema", str(e), re.I):
            _FORMAT_OK = False                 # this API / model won't take the schema: plain JSON from now on
            log.warning("pick_target: structured output rejected; asking for plain JSON (parsed leniently)")
        return None, "timeout" if timed_out else "error", 0.0
    api_ms = (time.perf_counter() - ta) * 1000
    _LAT.append(api_ms)
    usage = getattr(resp, "usage", None)
    inp, out = int(getattr(usage, "input_tokens", 0) or 0), int(getattr(usage, "output_tokens", 0) or 0)
    cost = _cost(resp, usage)
    _STATS["input_tokens"] += inp
    _STATS["output_tokens"] += out
    _STATS["cost_usd"] += cost
    answer = "".join(getattr(b, "text", "") for b in getattr(resp, "content", []) or []
                     if getattr(b, "type", None) == "text")
    parsed = parse_answer(answer) if getattr(resp, "stop_reason", None) != "refusal" else None
    log.info("pick_target %r -> %s | %d cands, %d masked, img %dx%d, in=%d out=%d $%.5f (total $%.4f, %d calls) %.0fms",
             intent[:60], answer.strip()[:120], len(cands), len(exclude), size[0], size[1], inp, out, cost,
             _STATS["cost_usd"], _STATS["calls"], api_ms)
    if parsed is None:
        _STATS["errors"] += 1
        return None, "error", 0.0              # not cached: a garbled answer may be a one-off
    ids, conf, why = parsed
    res, outcome = _result(cands, ids, conf, why, obs, min_conf)
    if res is not None:
        res.update(ms=round((time.perf_counter() - t0) * 1000), api_ms=round(api_ms), cached=False,
                   input_tokens=inp, output_tokens=out, cost_usd=round(cost, 6))
    _STATS[outcome] = _STATS.get(outcome, 0) + 1
    _cache_put(key, (res, outcome, conf))
    return (dict(res) if res else None), outcome, conf


def _result(cands: list[Cand], ids: list[int], conf: float, why: str, obs: ScreenObservation,
            min_conf: float | None) -> tuple[dict | None, str]:
    if not ids:
        return None, "none"
    thr = min_conf if min_conf is not None else _env_float("MIYAGI_VISION_MIN_CONF", 0.6)
    if conf < thr:
        log.info("pick_target: confidence %.2f < %.2f (ids %s): no box", conf, thr, ids)
        return None, "low_confidence"
    m = merge(cands, ids)
    if m is None:
        return None, "low_confidence"          # ids that aren't marks: treat as unsure, not as "nothing"
    group, r = m
    first = group[0]
    if first.kind not in ("region", "toolbar"):
        r = Rect(r.x - 2, r.y - 2, r.w + 4, r.h + 4)
    if obs.screen.w:
        r = r.clamp(obs.screen)
    if r.w < 6 or r.h < 6:
        return None, "low_confidence"
    label = first.label() + (f" (+{len(group) - 1} more rows)" if len(group) > 1 else "")
    return ({"rect": r.to_dict(), "box_ids": [c.id for c in group], "label": label, "kind": first.kind,
             "line": first.line, "region": first.region, "confidence": round(conf, 3), "reason": why}, "picked")


def _cache_get(key: str):
    hit = _CACHE.get(key)
    if hit is None or _now() - hit[0] > CACHE_TTL:
        _CACHE.pop(key, None)
        return False, None
    _CACHE.move_to_end(key)
    res, outcome, conf = hit[1]
    return True, ((dict(res, cached=True) if res else None), outcome, conf)


def _cache_put(key: str, val) -> None:
    _CACHE[key] = (_now(), val)
    _CACHE.move_to_end(key)
    while len(_CACHE) > CACHE_MAX:
        _CACHE.popitem(last=False)


# ---------------------------------------------------------------------- per-question memory (frames change)

def _same_row(p: Cand, c: Cand) -> bool:
    """Is `c` (this frame) the row `p` was when it was picked? The same kind of place at the same position (within a
    third of a row), the same file line when both are known, and the same text or text that grew / shrank from it
    (the learner typing there). Regions / icons: same name, within 12 pt."""
    if p.kind in ("region", "toolbar") or c.kind in ("region", "toolbar"):
        return c.kind == p.kind and c.text == p.text and all(
            abs(a - b) <= 12 for a, b in zip((c.rect.x, c.rect.y, c.rect.x2, c.rect.y2),
                                             (p.rect.x, p.rect.y, p.rect.x2, p.rect.y2)))
    if _group(c) != _group(p) or abs(c.rect.cy - p.rect.cy) > max(3.0, p.rect.h / 3):
        return False
    if min(c.rect.x2, p.rect.x2) - max(c.rect.x, p.rect.x) <= 0 and abs(c.rect.x - p.rect.x) > 24:
        return False
    if p.line and c.line:
        return p.line == c.line
    a, b = M.squash(p.text), M.squash(c.text)
    return not a or not b or a.startswith(b) or b.startswith(a)


def _context(cands: list[Cand], rows: list[Cand]) -> tuple:
    """What a pick of `rows` depends on besides the rows themselves: the other rows of their group (the editor's, or
    one panel's lines) ABOVE them, by position (8 pt) and text. Typing into or below the picked rows keeps it; a
    scroll or an edit above them changes it. Regions / icons: nothing else."""
    first = rows[0]
    if first.kind in ("region", "toolbar"):
        return ()
    g, top, ids = _group(first), min(c.rect.y for c in rows), {c.id for c in rows}
    return tuple(sorted((round(c.rect.cy / 8), M.squash(c.text)) for c in cands
                        if c.id not in ids and c.kind not in ("region", "toolbar") and _group(c) == g
                        and c.rect.cy < top))


def _carry(m: _Memo, cands: list[Cand], obs: ScreenObservation) -> dict | None:
    """A remembered pick on this frame: the same rows (new rects) when all are still there and the rows above them
    are unchanged; None otherwise (ask again)."""
    rows = []
    for p in m.rows:
        c = next((c for c in cands if c.id not in {r.id for r in rows} and _same_row(p, c)), None)
        if c is None:
            return None
        rows.append(c)
    if not rows or m.res is None or _context(cands, rows) != m.context:
        return None
    first, r = rows[0], rows[0].rect
    for c in rows[1:]:
        r = r.union(c.rect)
    if first.kind not in ("region", "toolbar"):
        r = Rect(r.x - 2, r.y - 2, r.w + 4, r.h + 4)
    if obs.screen.w:
        r = r.clamp(obs.screen)
    label = first.label() + (f" (+{len(rows) - 1} more rows)" if len(rows) > 1 else "")
    return dict(m.res, rect=r.to_dict(), box_ids=[c.id for c in rows], label=label, kind=first.kind,
                line=first.line, region=first.region, cached=True)


def _memo_answer(qkey: str, cands: list[Cand], obs: ScreenObservation) -> tuple[dict | None, str, float] | None:
    """The last answer to this question, when it still holds on this frame (else None: ask):
    - picked: the same rows in place and nothing above them changed (_carry) -> the pick, re-placed;
    - none: within NONE_HOLD_S; error / timeout / low_confidence: until the backoff is over -> that outcome again."""
    m = _MEMO.get(qkey)
    if m is None or _now() - m.t > CACHE_TTL:
        _MEMO.pop(qkey, None)
        return None
    if m.outcome == "picked":
        res = _carry(m, cands, obs)
        if res is None:
            return None
        _STATS["cache_hits"] += 1
        return res, "picked", m.conf
    if _now() < m.retry_at:
        _STATS["held"] += 1
        return None, m.outcome, m.conf
    return None


def _remember(qkey: str, cands: list[Cand], res: dict | None, outcome: str, conf: float) -> None:
    """Keep what one ask learned for this question (see _memo_answer). Budget / no key: nothing was asked."""
    if outcome not in (*ASKED, "error", "timeout"):
        return
    now, prev = _now(), _MEMO.get(qkey)
    if outcome == "picked":
        by = {c.id: c for c in cands}
        rows = [by[i] for i in (res or {}).get("box_ids") or [] if i in by]
        if not rows:
            return
        m = _Memo(now, outcome, conf, dict(res), rows, _context(cands, rows), now, 0)
    elif outcome == "none":
        m = _Memo(now, outcome, conf, None, [], (), now + NONE_HOLD_S, 0)
    else:
        fails = (prev.fails + 1) if prev is not None and prev.fails else 1
        wait = min(RETRY_MAX_S, RETRY_BASE_S * 2 ** (fails - 1))
        m = _Memo(now, outcome, conf, None, [], (), now + wait, fails)
        log.info("pick_target: %s; asking again in %.0f s at the earliest", outcome, wait)
    _MEMO[qkey] = m
    _MEMO.move_to_end(qkey)
    while len(_MEMO) > CACHE_MAX:
        _MEMO.popitem(last=False)


# ---------------------------------------------------------------------- Miyagi's own text

def note_ui_text(texts: Iterable[str]) -> None:
    """Strings Miyagi is showing (card title / body, captions, step lines; never code): an OCR line that reads as one
    of them is our overlay seen through a gap in `overlay.bounds`, never a target (_drop_ours)."""
    now = _now()
    for t in texts:
        s = M.squash(re.sub(r"`[^`]*`", " ", str(t or "")))   # code spans out: the learner may type those
        if len(s) < 12:
            continue
        for i, (_, u) in enumerate(_UI_TEXT):
            if u == s:                                          # shown again: its clock restarts
                del _UI_TEXT[i]
                break
        _UI_TEXT.append((now, s))


def _drop_ours(cands: list[Cand], intent: str) -> tuple[list[Cand], list[Cand]]:
    """-> (candidates, the ones dropped as Miyagi's own text): a line (>= 12 letters) that is a whole string Miyagi
    showed in the last UI_TEXT_TTL s, or a wrapped piece of one (>= 30% of it; an editor row: >= half). Never a line
    of the code the question asks for (its `(code: ...)` part); its prose is Miyagi's caption / action line, so a
    line restating it is ours."""
    now = _now()
    ui = [u for t, u in _UI_TEXT if now - t <= UI_TEXT_TTL]
    if not ui:
        return cands, []
    asked = M.squash(intent.partition("(code:")[2])           # "" when the question has no code
    keep, ours = [], []
    for c in cands:
        s = M.squash(c.text) if c.kind != "region" else ""
        part = 0.5 if c.kind in ("code", "blank") else 0.3
        if len(s) >= 12 and s not in asked and any(s in u and len(s) >= part * len(u) for u in ui):
            ours.append(c)
        else:
            keep.append(c)
    if ours:
        _STATS["ours_dropped"] += len(ours)
        log.info("pick_target: %d line(s) of Miyagi's own UI left out (%s)", len(ours), ours[0].text[:60])
    return keep, ours


# ---------------------------------------------------------------------- verifier

NONE_CONF = 0.75     # "nothing on screen matches" must be at least this sure to remove a box


def verdict(rect, res: dict | None, outcome: str, conf: float,
            move_conf: float | None = None) -> tuple[dict | None, str]:
    """Combine the engine's own box with a pick -> (rect to show | None, why):
    - pick overlaps the box -> keep the box ("agree"); a confident pick elsewhere -> the pick ("moved"),
      except a whole panel, or a block taller than ~3 lines, replacing a single row (never more precise than a row);
      move_conf (t5): a box the engine took from the file itself moves only on a pick at least this sure
      ("kept:unsure_move" below it);
    - the model is sure nothing matches (conf >= NONE_CONF) -> None ("none": no box);
    - low confidence, timeout, budget, no key, error -> keep the box ("kept:<outcome>")."""
    box = Rect.from_any(rect).to_dict()
    if res is not None:
        if overlaps(box, res["rect"], 0.3):
            return box, "agree"
        if res.get("kind") == "region" and res["rect"]["h"] >= 80 and box["h"] < 80:
            return box, "kept:region"
        if box["h"] < 80 and res["rect"]["h"] > 3 * max(box["h"], 20.0) + 12:  # e.g. 15 merged terminal rows
            return box, "kept:tall"
        if move_conf is not None and conf < move_conf:
            return box, "kept:unsure_move"
        return dict(res["rect"]), "moved"
    if outcome == "none" and conf >= NONE_CONF:
        return None, "none"
    return box, f"kept:{outcome}"


async def confirm_spot(rect, frame, ocr_boxes, intent: str, move_conf: float | None = None,
                       **kw) -> tuple[dict | None, str]:
    """Verifier for a box the engine located itself (text match / gutter line / region): see verdict()."""
    res, outcome, conf = await pick_with_outcome(frame, ocr_boxes, intent, **kw)
    return verdict(rect, res, outcome, conf, move_conf)


# ---------------------------------------------------------------------- live

def _live_args(reader, app: str | None) -> dict:
    regions = {}
    try:
        for n in MK.REGION_IDS:
            r = reader.locate_region(n, app)
            if r is not None:
                regions[n] = r
    except Exception:
        log.exception("pick_on_screen: regions")
        regions = {}
    desc = getattr(reader, "_describer", None)
    key = desc._key() if desc is not None and hasattr(desc, "_key") else None
    ov = reader.overlay_rects() if hasattr(reader, "overlay_rects") else getattr(reader, "_overlay", [])
    return {"regions": regions or None, "api_key": key or None, "exclude": list(ov or [])}


async def pick_on_screen(intent: str, app: str | None = "Code", reader=None, **kw) -> dict | None:
    """`pick_target` on the live reader's latest frame: image + OCR of the same frame, stabilized
    region rects, our overlay masked, the AX run button when Accessibility gives it, BYOK key."""
    from .reader import get_reader
    reader = reader or get_reader()
    frame, obs = await asyncio.to_thread(reader.latest_frame)
    if frame is None or obs is None:
        return None
    args = await asyncio.to_thread(_live_args, reader, app)  # AX + region reads: never on the event loop
    return await pick_target(frame, obs, intent, app=app, **args, **kw)


async def confirm_on_screen(rect, intent: str, app: str | None = "Code", reader=None,
                            **kw) -> tuple[dict | None, str]:
    """`confirm_spot` on the live reader's latest frame (see verdict())."""
    from .reader import get_reader
    reader = reader or get_reader()
    frame, obs = await asyncio.to_thread(reader.latest_frame)
    if frame is None or obs is None:
        return Rect.from_any(rect).to_dict(), "kept:no_frame"
    args = await asyncio.to_thread(_live_args, reader, app)  # AX + region reads: never on the event loop
    return await confirm_spot(rect, frame, obs, intent, app=app, **args, **kw)


def overlaps(a, b, min_frac: float = 0.5) -> bool:
    """Do two rects ({x,y,w,h} or Rect) mostly cover the same thing? (verifier helper: does the
    vision pick agree with a deterministic spotlight?)"""
    a, b = Rect.from_any(a), Rect.from_any(b)
    iw = min(a.x2, b.x2) - max(a.x, b.x)
    ih = min(a.y2, b.y2) - max(a.y, b.y)
    if iw <= 0 or ih <= 0:
        return False
    inter = iw * ih
    return inter >= min_frac * min(a.w * a.h, b.w * b.h)


__all__ = ["ASKED", "Cand", "build_candidates", "confirm_on_screen", "confirm_spot", "listing", "merge", "note_ui_text",
           "overlaps", "parse_answer", "pick_on_screen", "pick_target", "pick_with_outcome", "render_marks", "reset",
           "signature", "stats", "verdict"]

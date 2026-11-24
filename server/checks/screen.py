"""Screen-first helpers: OCR text out of a ScreenObservation, metrics off terminal text.

Accepted screen shapes (whatever E6's ``server.screen.latest()`` returns, dict or object):

* ScreenObservation ``{t, app, windows: [{app, title, rect}], blocks: [{text, rect, confidence, app?}]}``.
  A block belongs to the frontmost window (first in ``windows``) whose rect contains its centre,
  unless it carries its own ``app``.
* Already split per app: ``{"Terminal": ["line", ...] | "text", "Code": ...}``.

Rects may be ``{x, y, w|width, h|height}`` or ``[x, y, w, h]``.
App matching is case-insensitive substring (``"code"`` matches ``"Code"`` / ``"Visual Studio Code"``).
"""
from __future__ import annotations

import re
from typing import Any
from server.safety.patterns import safe_compile

MIN_CONFIDENCE = 0.3  # drop OCR blocks Vision is unsure about


def _get(o: Any, k: str, default: Any = None) -> Any:
    if isinstance(o, dict):
        return o.get(k, default)
    return getattr(o, k, default)


def _rect(r: Any) -> tuple[float, float, float, float] | None:
    if r is None:
        return None
    if isinstance(r, (list, tuple)) and len(r) == 4:
        return tuple(float(v) for v in r)  # type: ignore[return-value]
    x, y = _get(r, "x"), _get(r, "y")
    w = _get(r, "w", _get(r, "width"))
    h = _get(r, "h", _get(r, "height"))
    if None in (x, y, w, h):
        return None
    return float(x), float(y), float(w), float(h)


def _inside(pt: tuple[float, float], r: tuple[float, float, float, float]) -> bool:
    return r[0] <= pt[0] <= r[0] + r[2] and r[1] <= pt[1] <= r[1] + r[3]


def app_matches(want: str | None, app: str | None) -> bool:
    if not want:
        return True
    return bool(app) and want.lower() in str(app).lower()


def _is_observation(screen: Any) -> bool:
    return _get(screen, "blocks") is not None


def screen_lines(screen: Any, app: str | None = None) -> list[str] | None:
    """OCR lines on screen, optionally only those in ``app``'s windows.

    Returns None when there is no observation, or when ``app`` is given but not on screen
    (callers treat that as "can't tell yet").
    """
    if screen is None:
        return None
    if not _is_observation(screen):
        if not isinstance(screen, dict):
            return None
        lines: list[str] = []
        seen = False
        for name, val in screen.items():
            if app_matches(app, name):
                seen = True
                lines.extend(val.splitlines() if isinstance(val, str) else [str(x) for x in val])
        return lines if seen else None

    windows = [(w, _rect(_get(w, "rect"))) for w in (_get(screen, "windows") or [])]
    if app and not any(app_matches(app, _get(w, "app")) for w, _ in windows) \
            and not app_matches(app, _get(screen, "app")) \
            and not any(app_matches(app, _get(b, "app")) for b in _get(screen, "blocks") or []):
        return None
    out = []
    for b in _get(screen, "blocks") or []:
        text = _get(b, "text")
        if not text:
            continue
        conf = _get(b, "confidence")
        if conf is not None and conf < MIN_CONFIDENCE:
            continue
        if app:
            owner = _get(b, "app")
            if owner is None:
                r = _rect(_get(b, "rect"))
                if r is not None and windows:
                    centre = (r[0] + r[2] / 2, r[1] + r[3] / 2)
                    owner = next((_get(w, "app") for w, wr in windows if wr and _inside(centre, wr)), None)
                elif not windows:
                    owner = _get(screen, "app")  # no window geometry: assume the frontmost app
            if not app_matches(app, owner):
                continue
        out.append(str(text))
    return out


def screen_text(screen: Any, app: str | None = None) -> str | None:
    lines = screen_lines(screen, app)
    return None if lines is None else "\n".join(lines)


def search_screen(pattern: str, text: str) -> re.Match[str] | None:
    """Regex search tolerant to OCR line wrapping: tries the raw text, then whitespace-collapsed."""
    rx = safe_compile(pattern, re.MULTILINE)  # re.error for a catastrophic lesson pattern (server.safety.patterns)
    return rx.search(text) or rx.search(re.sub(r"\s+", " ", text))


_PUNCT_GAP = re.compile(r"\s*([.()\[\],])\s*")


def search_wrapped(pattern: str, text: str) -> re.Match[str] | None:
    """search_screen, plus the forms a wrapped code line takes in OCR (t9 V2: VS Code's word wrap read as
    "…datasets.mnist." / "load_data()"): consecutive lines joined with nothing, and whitespace around . ( ) [ ] ,
    dropped. For "the code / output is there" checks only: an absent check keeps search_screen (a join must never
    invent an error)."""
    m = search_screen(pattern, text)
    if m or not text:
        return m
    rx = safe_compile(pattern, re.MULTILINE)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return rx.search("".join(lines)) or rx.search(_PUNCT_GAP.sub(r"\1", " ".join(lines)))


_NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _ocr_float(s: str) -> float | None:
    """OCR-tolerant float: 'O.25' → 0.25, '1,234' → 1234, '2.5e-0З' fails → None."""
    low = s.strip().lower()
    if low.lstrip("+-") in ("nan", "inf", "infinity"):
        return float(low)  # divergence must reach the evaluator, not be skipped
    s = s.strip().replace("O", "0").replace("o", "0").replace(",", "").replace("—", "-").replace("−", "-")
    m = _NUM.search(s)
    try:
        return float(m.group(0)) if m else None
    except ValueError:
        return None


_NONFINITE = r"(?i:[-+]?(?:nan|inf(?:inity)?))"


def _value_group_span(pattern: str) -> tuple[int, int] | None:
    """(start of the group body, index of its closing paren) for the ``(?P<value>...)`` group, or None."""
    key = "(?P<value>"
    at = pattern.find(key)
    if at < 0:
        return None
    start, depth, i, in_class = at + len(key), 1, at + len(key), False
    while i < len(pattern):
        c = pattern[i]
        if c == "\\":
            i += 2
            continue
        if in_class:
            in_class = c != "]"
        elif c == "[":
            in_class = True
            if pattern[i + 1:i + 2] == "^":
                i += 1
            if pattern[i + 1:i + 2] == "]":
                i += 1
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return start, i
        i += 1
    return None


def nonfinite_tolerant(pattern: str) -> str:
    """A lesson's value class like ``[0-9Oo.eE+-]+`` can't read ``nan``/``inf``, so a diverged loss line was
    skipped and an older finite value was graded. Let the ``value`` group also match nan/inf (any case, signed);
    _ocr_float turns them into float values the divergence guard fails on."""
    span = _value_group_span(pattern)
    if span is None:
        return pattern
    a, b = span
    return pattern[:a] + _NONFINITE + "|" + pattern[a:b] + pattern[b:]


def wrapper_tolerant(pattern: str) -> str:
    """A value printed inside a wrapper: ``loss tensor(0.2614, grad_fn=<MseLossBackward0>)`` (a PyTorch tensor printed
    without ``.item()``), ``np.float32(0.5)``, ``array(0.25)``. The ``value`` group may follow an optional
    ``name(`` so the number inside is read; the pattern is otherwise unchanged."""
    at = pattern.find("(?P<value>")
    if at < 0:
        return pattern
    return pattern[:at] + r"(?:[A-Za-z_][\w.]*\()?" + pattern[at:]


def extract_metrics(pattern: str, text: str) -> list[tuple[int, float]]:
    """Apply a check's ``metric_pattern`` to terminal text → ``[(step, value), ...]``.

    The pattern should have named groups ``step`` and ``value``; without ``value`` the last
    group is used, and without ``step`` the line order is the step (0, 1, 2, ...).
    Duplicate steps (the same line visible across screenshots) keep the last value.
    """
    rx = safe_compile(wrapper_tolerant(nonfinite_tolerant(pattern)))
    pts: dict[int, float] = {}
    order = 0
    for line in text.splitlines():
        m = rx.search(line)
        if not m:
            continue
        gd = m.groupdict()
        raw_v = gd.get("value") if "value" in gd else (m.group(m.lastindex) if m.lastindex else None)
        v = _ocr_float(raw_v) if raw_v is not None else None
        if v is None:
            continue
        if gd.get("step") is not None:
            s = _ocr_float(gd["step"])
            if s is None:
                continue
            step = int(s)
        else:
            step = order
        order += 1
        pts[step] = v
    return sorted(pts.items())

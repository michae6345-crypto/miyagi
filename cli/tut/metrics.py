"""Line handling: ANSI stripping and the ::metric:: protocol (shared/contracts/metric-protocol.md)."""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass

PREFIX = "::metric::"
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]")
_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?|[-+]?(?:nan|inf|infinity)"
_FIELD = {
    "step": re.compile(r'"?step"?\s*[:=]\s*(?:tensor\()?(' + _NUM + ")", re.I),
    "name": re.compile(r'"?name"?\s*[:=]\s*"([^"]*)"', re.I),
    "value": re.compile(r'"?value"?\s*[:=]\s*(?:tensor\()?(?:array\()?(' + _NUM + ")", re.I),
}


@dataclass(frozen=True)
class Metric:
    step: int
    name: str
    value: float

    @property
    def finite(self) -> bool:
        return math.isfinite(self.value)


def strip_ansi(s: str) -> str:
    return _ANSI.sub("", s)


def clean_line(raw: str) -> str:
    """Text as a human saw it: no ANSI, and for \\r progress bars only the last frame."""
    s = strip_ansi(raw).rstrip("\r")
    if "\r" in s:
        s = s.rsplit("\r", 1)[-1]
    return s


def parse_metric(line: str) -> Metric | None:
    """Parse one output line. Returns None unless it is a ::metric:: line.

    Strict JSON first; falls back to field regexes so common slips still count:
    `nan`/`inf` values, `tensor(0.25, grad_fn=...)` values, single quotes.
    """
    s = clean_line(line).strip()
    if not s.startswith(PREFIX):
        return None
    body = s[len(PREFIX):].strip()
    try:
        d = json.loads(body)
        return Metric(int(d["step"]), str(d["name"]), float(d["value"]))
    except (ValueError, KeyError, TypeError):
        pass
    body = body.replace("'", '"')
    m = {k: rx.search(body) for k, rx in _FIELD.items()}
    if not all(m.values()):
        return None
    try:
        return Metric(int(float(m["step"].group(1))), m["name"].group(1), float(m["value"].group(1)))
    except ValueError:
        return None

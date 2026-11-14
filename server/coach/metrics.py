"""Turn raw metric series into a compact, model-friendly summary + flags.

Accepts what the orchestrator has on hand:
- `dict[name, list[(step, value)]]` (RunContext.metrics), or
- an already-written string, or
- a dict that is already a summary (passed through as JSON).
"""

from __future__ import annotations

import itertools
import json
import math
from typing import Any

Series = list[tuple[int, float]]


def _is_series(v: Any) -> bool:
    return isinstance(v, (list, tuple)) and (not v or isinstance(v[0], (list, tuple)))


def _fmt(x: float) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return str(x)
    return f"{x:.3g}"


def series_flags(points: Series) -> set[str]:
    flags: set[str] = set()
    vals = [float(v) for _, v in points]
    if not vals:
        return flags
    if any(not math.isfinite(v) for v in vals):
        return {"nan", "diverging"}
    first, last, lo = vals[0], vals[-1], min(vals)
    if len(vals) >= 4 and last > max(first, 1e-12) * 1.5 and last > lo * 3:
        flags.add("diverging")
    if len(vals) >= 6:
        tail = vals[len(vals) // 2 :]
        start = tail[0]
        rel = (start - tail[-1]) / max(abs(start), 1e-12)
        if rel < 0.1 and abs(tail[-1]) > 1e-3 and "diverging" not in flags:
            flags.add("plateau")
        diffs = [b - a for a, b in itertools.pairwise(vals)]
        ups = sum(d > 0 for d in diffs)
        if len(diffs) >= 6 and ups / len(diffs) > 0.4 and "plateau" not in flags:
            flags.add("noisy")
    return flags


def summarize(metrics: Any) -> tuple[str, set[str]]:
    """Return (summary text, flags) for the prompt and the triage."""
    if metrics is None:
        return "no metrics recorded", set()
    if isinstance(metrics, str):
        low = metrics.lower()
        flags = {f for f in ("plateau", "diverging", "nan", "noisy", "imbalance") if f in low}
        if "flat" in low or "stall" in low:
            flags.add("plateau")
        return metrics, flags
    if isinstance(metrics, dict) and metrics and all(_is_series(v) for v in metrics.values()):
        lines, flags = [], set()
        for name in sorted(metrics):
            pts = [(int(s), float(v)) for s, v in metrics[name]]
            if not pts:
                continue
            f = series_flags(pts)
            if name == "loss" or name.endswith("/loss") or name.startswith("loss"):
                flags |= f
            vals = [v for _, v in pts]
            lines.append(
                f"{name}: steps {pts[0][0]}..{pts[-1][0]} (n={len(pts)}), "
                f"first {_fmt(vals[0])}, min {_fmt(min(vals))}, last {_fmt(vals[-1])}"
                + (f" [{', '.join(sorted(f))}]" if f else "")
            )
        flags |= _imbalance(metrics)
        return "\n".join(lines) or "no metrics recorded", flags
    if isinstance(metrics, dict):
        text = json.dumps(metrics, sort_keys=True, default=str)
        return summarize(text)[0], {str(f) for f in metrics.get("flags", [])} | summarize(text)[1]
    return str(metrics), set()


def _imbalance(metrics: dict) -> set[str]:
    """Residual loss falling while IC/BC loss stays put -> imbalance."""
    def last_ratio(name: str) -> float | None:
        pts = metrics.get(name)
        if not pts or len(pts) < 4:
            return None
        a, b = float(pts[0][1]), float(pts[-1][1])
        return b / a if a else None

    res = next((last_ratio(n) for n in ("loss/residual", "loss_residual", "loss/pde", "loss_pde", "lossPDE") if n in metrics), None)
    bc = next((last_ratio(n) for n in ("loss/ic", "loss/bc", "loss_ic", "loss_bc", "lossBC") if n in metrics), None)
    if res is not None and bc is not None and res < 0.1 and bc > 0.7:
        return {"imbalance"}
    return set()

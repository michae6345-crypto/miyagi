"""Step check evaluator: ``evaluate_step(step, ctx) -> list[CheckResult]``.

Pure function: it reads the workdir and the run context it is given and never
calls the network, the DB or a model. The orchestrator builds the ``RunContext``
from ``tut run`` events (``/ingest``) and calls this on file saves and run ends.

Status semantics (``CheckStatus`` in ``shared/contracts/events.ts``):

* ``pass``    the check is satisfied.
* ``fail``    the check is definitely not satisfied right now (file missing,
              regex absent, run exited non-zero, loss curve flat, threshold
              missed by ``by_step``...). The orchestrator's don't-nag gate decides
              when a fail becomes an ``offtrack`` card.
* ``pending`` not enough evidence yet (no run, still collecting points, visual
              verdict not supplied).
"""
from __future__ import annotations

import dataclasses
import math
import os
import re
import shlex
import statistics
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

from .screen import extract_metrics, screen_text, search_screen

CheckStatus = Literal["pending", "pass", "fail"]


class CheckResult(TypedDict):
    checkId: str
    label: str
    status: CheckStatus
    detail: str


@dataclass
class RunContext:
    """Everything a check may look at.

    ``metrics`` maps a metric name to ``[(step, value), ...]`` in arrival order
    (the evaluator sorts by step itself). ``output_tail`` is the last lines of the
    most recent run (str or list of lines). ``exit_code`` is None while running or
    before any run. ``visual`` holds verdicts the orchestrator obtained from a
    vision model: ``{check_id: {"pass": bool, "detail": str}}``.

    Screen-first: ``screen`` is the latest ScreenObservation from ``server.screen``
    (dict or object, or ``{app: [lines]}``; see ``screen.py``). Metrics read off
    the screen by E6 should be merged into ``metrics`` by the orchestrator; when a
    metric check has a ``metric_pattern`` and ``metrics`` has nothing for it, the
    evaluator parses the visible terminal text (and the run output) itself.
    """

    workdir: str = "."
    exit_code: int | None = None
    output_tail: list[str] | str = field(default_factory=list)
    metrics: dict[str, list[tuple[int, float]]] = field(default_factory=dict)
    command: str | None = None
    running: bool = False
    visual: dict[str, dict[str, Any]] = field(default_factory=dict)
    screen: Any = None

    @property
    def has_run(self) -> bool:
        return self.running or self.exit_code is not None or self.command is not None

    @property
    def run_finished(self) -> bool:
        return not self.running and self.exit_code is not None

    def add_metric(self, name: str, step: int, value: float) -> None:
        self.metrics.setdefault(name, []).append((int(step), float(value)))

    def output_text(self) -> str:
        if isinstance(self.output_tail, str):
            return self.output_tail
        return "\n".join(self.output_tail)


# ---------------------------------------------------------------- tunables
# metric_threshold: compare the median of the last N points (<= by_step) so a single
# noisy minibatch can neither pass nor fail the check.
THRESHOLD_SMOOTH_POINTS = 5

# metric_trend: see _metric_trend() for the full test. A trend passes only when it is BOTH
# statistically significant (Mann-Kendall) AND big enough to matter (Theil-Sen effect size).
TREND_MIN_POINTS = 8           # need at least this many finite points in the window
TREND_MIN_COVERAGE = 0.5       # ...spanning at least half of `window` steps
NOT_FLAT_MIN_REL_CHANGE = 0.05  # |relative change| over the window must be >= 5%
DECREASING_MIN_REL_DROP = 0.02  # "decreasing" needs >= 2% robust drop
MK_Z_TWO_SIDED = 2.576         # not_flat: Mann-Kendall p < 0.01 (two-sided)
MK_Z_ONE_SIDED = 2.326         # decreasing: Mann-Kendall p < 0.01 (one-sided, downward)
DEFAULT_TREND_WINDOW = 1000
MAX_TS_POINTS = 200            # Theil-Sen / Mann-Kendall are O(n^2); thin longer windows

_OPS = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
}


def _result(check: dict, status: CheckStatus, detail: str) -> CheckResult:
    return {
        "checkId": str(check.get("id", "")),
        "label": str(check.get("label", check.get("id", ""))),
        "status": status,
        "detail": detail,
    }


def _fmt(v: float) -> str:
    if v == 0 or 1e-3 <= abs(v) < 1e4:
        return f"{v:.4g}"
    return f"{v:.2e}"


def _resolve(workdir: str, rel: str) -> str:
    return rel if os.path.isabs(rel) else os.path.normpath(os.path.join(workdir, rel))


def _compile(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.MULTILINE)


# ---------------------------------------------------------------- per type
def _file_exists(check: dict, ctx: RunContext) -> CheckResult:
    rel = check.get("file")
    if not rel:
        return _result(check, "fail", "check has no 'file'")
    if os.path.exists(_resolve(ctx.workdir, rel)):
        return _result(check, "pass", f"{rel} exists")
    return _result(check, "fail", f"{rel} not found")


def _file_contains(check: dict, ctx: RunContext) -> CheckResult:
    rel, pattern = check.get("file"), check.get("pattern")
    if not rel or not pattern:
        return _result(check, "fail", "check needs 'file' and 'pattern'")
    path = _resolve(ctx.workdir, rel)
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except FileNotFoundError:
        return _result(check, "fail", f"{rel} not found")
    except OSError as exc:
        return _result(check, "fail", f"cannot read {rel}: {exc.strerror}")
    try:
        m = _compile(pattern).search(text)
    except re.error as exc:
        return _result(check, "fail", f"invalid pattern: {exc}")
    if m:
        line = text.count("\n", 0, m.start()) + 1
        return _result(check, "pass", f"found in {rel}:{line}")
    return _result(check, "fail", f"pattern not found in {rel}")


def _script_tokens(command: str) -> list[str]:
    """Tokens that identify *what* is run: drop flags/values, interpreter wrappers."""
    try:
        toks = shlex.split(command)
    except ValueError:
        toks = command.split()
    skip = {"python", "python3", "uv", "run", "tut", "-m", "-u", "node", "bash", "sh", "npx"}
    out = []
    for t in toks:
        if t.startswith("-"):
            if out:
                break  # flags after the script/module may legitimately differ
            continue  # interpreter flags (-u, -O, ...) before the script
        if "=" in t and not out:
            continue  # env assignments like CUDA_VISIBLE_DEVICES=0
        if os.path.basename(t) in skip or re.fullmatch(r"python3(\.\d+)?", os.path.basename(t)):
            continue
        out.append(os.path.basename(t))
    return out


def _command_matches(expected: str | None, actual: str | None) -> bool:
    if not expected or not actual:
        return True
    want = _script_tokens(expected)
    if not want:
        return True
    got = _script_tokens(actual)
    return all(w in got for w in want)


def _command_exit_ok(check: dict, ctx: RunContext) -> CheckResult:
    want = check.get("command")
    hint = f"run `tut run {want}`" if want else "run your script with `tut run`"
    if not ctx.has_run:
        return _result(check, "pending", hint)
    if not _command_matches(want, ctx.command):
        return _result(check, "pending", f"last run was `{ctx.command}`; {hint}")
    if ctx.running or ctx.exit_code is None:
        return _result(check, "pending", "running…")
    if ctx.exit_code == 0:
        return _result(check, "pass", "exited 0")
    return _result(check, "fail", f"exited with code {ctx.exit_code}")


def _output_contains(check: dict, ctx: RunContext) -> CheckResult:
    pattern = check.get("pattern")
    if not pattern:
        return _result(check, "fail", "check has no 'pattern'")
    text = ctx.output_text()
    try:
        m = _compile(pattern).search(text)
    except re.error as exc:
        return _result(check, "fail", f"invalid pattern: {exc}")
    if m:
        return _result(check, "pass", f"output matched: {m.group(0)[:80]!r}")
    if not ctx.has_run:
        return _result(check, "pending", "no run yet")
    if ctx.run_finished:
        return _result(check, "fail", "pattern not in output")
    return _result(check, "pending", "waiting for output…")


def _metric_name(check: dict) -> str | None:
    return check.get("metric") or (str(check.get("id")) if check.get("metric_pattern") else None)


def _raw_series(ctx: RunContext, name: str, check: dict | None = None) -> list[tuple[int, float]]:
    """All points sorted by step, None/NaN/inf kept as float (NaN for None)."""
    raw = list(ctx.metrics.get(name, []))
    pattern = (check or {}).get("metric_pattern")
    if not raw and pattern:
        texts = [screen_text(ctx.screen, check.get("app")) or "", ctx.output_text()]
        merged: dict[int, float] = {}
        for t in texts:
            merged.update(extract_metrics(pattern, t))
        raw = sorted(merged.items())
    pts = [(int(s), math.nan if v is None else float(v)) for s, v in raw]
    pts.sort(key=lambda p: p[0])
    return pts


def _series(ctx: RunContext, name: str, check: dict | None = None) -> list[tuple[int, float]]:
    return [p for p in _raw_series(ctx, name, check) if math.isfinite(p[1])]


def _diverged(ctx: RunContext, name: str, check: dict, since_step: int | None = None) -> CheckResult | None:
    """Fail when the metric went NaN/inf: as its latest point, or anywhere at/after ``since_step``.

    A diverged run must never be graded on the stale finite values logged before it blew up.
    """
    raw = _raw_series(ctx, name, check)
    if not raw:
        return None
    bad = [p for p in raw if not math.isfinite(p[1]) and (since_step is None or p[0] >= since_step)]
    if not math.isfinite(raw[-1][1]):
        bad.append(raw[-1])
    if not bad:
        return None
    s, v = bad[-1]
    return _result(check, "fail", f"{name} diverged: {v} at step {s}")


def _metric_threshold(check: dict, ctx: RunContext) -> CheckResult:
    name, op, target = _metric_name(check), check.get("op"), check.get("value")
    if not name or op not in _OPS or target is None:
        return _result(check, "fail", "check needs 'metric' (or 'metric_pattern'), 'op' and 'value'")
    by_step = check.get("by_step")
    div = _diverged(ctx, name, check)
    if div:
        return div
    pts = _series(ctx, name, check)
    if not pts:
        if ctx.run_finished:
            return _result(check, "fail", f"run logged no '{name}' metric")
        return _result(check, "pending", f"waiting for '{name}'")
    eligible = [p for p in pts if by_step is None or p[0] <= by_step]
    latest_step = pts[-1][0]
    if eligible:
        recent = [v for _, v in eligible[-THRESHOLD_SMOOTH_POINTS:]]
        current = statistics.median(recent)
        at = eligible[-1][0]
        if _OPS[op](current, float(target)):
            return _result(check, "pass", f"{name} {_fmt(current)} {op} {_fmt(float(target))} at step {at}")
        msg = f"{name} {_fmt(current)} at step {at}, need {op} {_fmt(float(target))}"
    else:
        msg = f"no '{name}' points at or before step {by_step}"
    if by_step is not None and latest_step >= by_step:
        return _result(check, "fail", msg + f" by step {by_step}")
    if ctx.run_finished:
        return _result(check, "fail", msg)
    return _result(check, "pending", msg)


def _theil_sen_slope(xs: list[float], ys: list[float]) -> float:
    slopes = []
    n = len(xs)
    for i in range(n):
        for j in range(i + 1, n):
            dx = xs[j] - xs[i]
            if dx != 0:
                slopes.append((ys[j] - ys[i]) / dx)
    return statistics.median(slopes) if slopes else 0.0


def _thin(pts: list[tuple[int, float]], k: int) -> list[tuple[int, float]]:
    if len(pts) <= k:
        return pts
    stride = len(pts) / k
    return [pts[int(i * stride)] for i in range(k - 1)] + [pts[-1]]


def trend_stats(pts: list[tuple[int, float]]) -> dict[str, float]:
    """Robust trend statistics over a window of (step, value) points.

    Two independent estimates of the relative change across the window:

    * ``rel_median``: 1 - median(last third) / median(first third). Insensitive to
      spikes and minibatch noise.
    * ``rel_theil_sen``: relative change implied by the Theil–Sen slope (median of
      pairwise slopes) across the window span. Fit on log10(value) when every value
      is positive (losses span decades), else on raw values scaled by |first median|.

    Positive numbers mean the metric went *down* (improvement for a loss).
    """
    pts = _thin(pts, MAX_TS_POINTS)
    xs = [float(s) for s, _ in pts]
    ys = [v for _, v in pts]
    third = max(1, len(ys) // 3)
    first, last = statistics.median(ys[:third]), statistics.median(ys[-third:])
    span = xs[-1] - xs[0]
    positive = all(v > 0 for v in ys)
    if positive:
        slope = _theil_sen_slope(xs, [math.log10(v) for v in ys])
        rel_ts = 1.0 - 10 ** (slope * span)
        rel_med = 1.0 - last / first
    else:
        slope = _theil_sen_slope(xs, ys)
        scale = abs(first) or 1e-12
        rel_ts = -(slope * span) / scale
        rel_med = (first - last) / scale
    return {"rel_median": rel_med, "rel_theil_sen": rel_ts, "first": first, "last": last, "span": span,
            "slope": slope, "mk_z": mann_kendall_z(ys), "n": len(ys)}


def mann_kendall_z(ys: list[float]) -> float:
    """Mann-Kendall trend statistic as a z-score (negative = downward trend).

    S = sum over pairs of sign(y_j - y_i); Var(S) = n(n-1)(2n+5)/18 minus the tie
    correction; z = (S -/+ 1)/sqrt(Var). Rank-based, so it is immune to the noise scale
    and to outliers: noise alone stays below |z| ~ 2.6 in 99% of windows.
    """
    n = len(ys)
    if n < 3:
        return 0.0
    s = 0
    for i in range(n - 1):
        yi = ys[i]
        for j in range(i + 1, n):
            d = ys[j] - yi
            s += (d > 0) - (d < 0)
    ties: dict[float, int] = {}
    for y in ys:
        ties[y] = ties.get(y, 0) + 1
    var = (n * (n - 1) * (2 * n + 5) - sum(t * (t - 1) * (2 * t + 5) for t in ties.values() if t > 1)) / 18
    if var <= 0 or s == 0:
        return 0.0
    return (s - 1) / math.sqrt(var) if s > 0 else (s + 1) / math.sqrt(var)


def _metric_trend(check: dict, ctx: RunContext) -> CheckResult:
    """``not_flat`` / ``decreasing`` over the last ``window`` training steps.

    Window = points with step >= latest_step - window. Pending until the window
    has >= TREND_MIN_POINTS finite points covering >= TREND_MIN_COVERAGE of it.

    Two gates, both required (the classic Mann-Kendall + Sen's slope pairing):

    1. **Significance**: the Mann-Kendall z-score of the window. Rank-based, so it scales
       with the noise automatically; pure noise passes this in about 1% of windows.
    2. **Effect size**: the Theil–Sen relative change across the window (on log10 values
       when all are positive). This keeps a real but negligible drift (a PINN plateau
       creeping 0.2504 → 0.2490, which MK flags as "significant" when there are
       thousands of points) from counting as progress.

    * ``not_flat``: |z| >= MK_Z_TWO_SIDED (p<0.01) and |Theil–Sen change| >= 5%, same
      direction. Direction-agnostic (literally "not flat"); use ``decreasing`` when the
      direction matters.
    * ``decreasing``: z <= -MK_Z_ONE_SIDED (p<0.01) and a Theil–Sen drop >= 2%.

    A NaN/inf anywhere in the window (or as the latest point) fails the check: divergence.
    """
    name = _metric_name(check)
    trend = check.get("trend")
    if not name or trend not in ("not_flat", "decreasing"):
        return _result(check, "fail", "check needs 'metric' (or 'metric_pattern') and trend 'not_flat'|'decreasing'")
    window = int(check.get("window") or DEFAULT_TREND_WINDOW)
    pts = _series(ctx, name, check)
    if not pts:
        if ctx.run_finished:
            return _result(check, "fail", f"run logged no '{name}' metric")
        return _result(check, "pending", f"waiting for '{name}'")
    latest = pts[-1][0]
    div = _diverged(ctx, name, check, since_step=latest - window)
    if div:
        return div
    win = [p for p in pts if p[0] >= latest - window]
    span = win[-1][0] - win[0][0]
    if len(win) < TREND_MIN_POINTS or span < TREND_MIN_COVERAGE * window:
        msg = f"collecting {name}: {len(win)} pts over {span}/{window} steps"
        if ctx.run_finished:
            return _result(check, "fail", msg + " (run ended)")
        return _result(check, "pending", msg)

    st = trend_stats(win)
    rt, z = st["rel_theil_sen"], st["mk_z"]
    desc = (f"{name} {_fmt(st['first'])} → {_fmt(st['last'])} over last {int(st['span'])} steps "
            f"({-rt * 100:+.1f}%, trend z={z:+.1f})")
    if trend == "decreasing":
        ok = z <= -MK_Z_ONE_SIDED and rt >= DECREASING_MIN_REL_DROP
        return _result(check, "pass" if ok else "fail", desc + ("" if ok else " — not decreasing"))
    ok = abs(z) >= MK_Z_TWO_SIDED and abs(rt) >= NOT_FLAT_MIN_REL_CHANGE and (rt > 0) == (z < 0)
    return _result(check, "pass" if ok else "fail", desc + ("" if ok else " — plateau"))


def _screen(check: dict, ctx: RunContext, absent: bool) -> CheckResult:
    pattern, app = check.get("pattern"), check.get("app")
    if not pattern:
        return _result(check, "fail", "check has no 'pattern'")
    where = f" in {app}" if app else " on screen"
    text = screen_text(ctx.screen, app)
    if text is None:
        return _result(check, "pending", f"{app} not visible" if app and ctx.screen is not None else "waiting for screen")
    try:
        m = search_screen(pattern, text)
    except re.error as exc:
        return _result(check, "fail", f"invalid pattern: {exc}")
    if absent:
        if m:
            return _result(check, "fail", f"still showing {m.group(0)[:80]!r}{where}")
        return _result(check, "pass", f"not showing{where}")
    if m:
        return _result(check, "pass", f"seen{where}: {m.group(0)[:80]!r}")
    return _result(check, "fail", f"not seen{where}")


def _screen_contains(check: dict, ctx: RunContext) -> CheckResult:
    return _screen(check, ctx, absent=False)


def _screen_absent(check: dict, ctx: RunContext) -> CheckResult:
    return _screen(check, ctx, absent=True)


def _visual(check: dict, ctx: RunContext) -> CheckResult:
    verdict = ctx.visual.get(str(check.get("id")))
    if not verdict:
        return _result(check, "pending", "awaiting visual check")
    status: CheckStatus = "pass" if verdict.get("pass") else "fail"
    return _result(check, status, str(verdict.get("detail", "")))


_HANDLERS = {
    "screen_contains": _screen_contains,
    "screen_absent": _screen_absent,
    "file_exists": _file_exists,
    "file_contains": _file_contains,
    "command_exit_ok": _command_exit_ok,
    "output_contains": _output_contains,
    "metric_threshold": _metric_threshold,
    "metric_trend": _metric_trend,
    "visual": _visual,
}
FILE_CHECK_TYPES = frozenset({"file_exists", "file_contains"})
SCREEN_CHECK_TYPES = frozenset({"screen_contains", "screen_absent"})
RUN_CHECK_TYPES = frozenset({"command_exit_ok", "output_contains", "metric_threshold", "metric_trend"})


def evaluate_check(check: dict, ctx: RunContext) -> CheckResult:
    handler = _HANDLERS.get(check.get("type", ""))
    if handler is None:
        return _result(check, "fail", f"unsupported check type {check.get('type')!r}")
    try:
        return handler(check, ctx)
    except Exception as exc:  # noqa: BLE001 — a malformed check must never crash the engine
        return _result(check, "fail", f"check error: {type(exc).__name__}: {exc}")


CheckList = Literal["checks", "precision", "all"]


def evaluate_step(step: dict, ctx: RunContext | None = None, types: Iterable[str] | None = None,
                  screen: Any = None, which: CheckList = "checks") -> list[CheckResult]:
    """Evaluate a step's checks (or only those whose type is in ``types``).

    ``which`` picks the list: ``"checks"`` (default, the screen-gradable list that gates the
    step), ``"precision"`` (the optional ``precision_checks`` backups: file_*, command_exit_ok,
    ::metric:: names; only meaningful with a workdir or ``tut run``), or ``"all"`` (both).
    ``screen`` (a ScreenObservation) overrides ``ctx.screen``; ``ctx`` may be omitted.
    """
    ctx = ctx or RunContext()
    if screen is not None:
        ctx = dataclasses.replace(ctx, screen=screen)
    if which == "checks":
        checks = step.get("checks") or []
    elif which == "precision":
        checks = step.get("precision_checks") or []
    elif which == "all":
        checks = [*(step.get("checks") or []), *(step.get("precision_checks") or [])]
    else:
        raise ValueError(f"which must be 'checks', 'precision' or 'all', not {which!r}")
    wanted = set(types) if types is not None else None
    return [evaluate_check(c, ctx) for c in checks if wanted is None or c.get("type") in wanted]


class StepGate(TypedDict):
    passed: bool
    via: Literal["checks", "precision"] | None
    checks: list[CheckResult]
    precision: list[CheckResult]


def evaluate_gate(step: dict, ctx: RunContext | None = None, screen: Any = None,
                  precision_mode: bool = False) -> StepGate:
    """Does the step pass? The one call the orchestrator needs.

    * Screen mode (default): only ``checks`` are evaluated and they alone decide.
      ``precision_checks`` are not evaluated, so they can never block the step.
    * Precision mode: both lists are evaluated; the step passes when ALL ``checks`` pass
      OR (``precision_checks`` is non-empty and ALL of them pass). Precision is an extra
      route to green (e.g. OCR misses a line), never an extra hurdle.
    """
    checks = evaluate_step(step, ctx, screen=screen, which="checks")
    prec = evaluate_step(step, ctx, screen=screen, which="precision") if precision_mode else []
    if step_passed(checks):
        via: Literal["checks", "precision"] | None = "checks"
    elif precision_mode and step_passed(prec):
        via = "precision"
    else:
        via = None
    return {"passed": via is not None, "via": via, "checks": checks, "precision": prec}


def step_passed(results: list[CheckResult]) -> bool:
    """A step passes only when it has checks and ALL of them pass."""
    return bool(results) and all(r["status"] == "pass" for r in results)

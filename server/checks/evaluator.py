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

from .notebook import Notebook, find_notebook, read_notebook
from .screen import extract_metrics, screen_lines, screen_text, search_screen, search_wrapped

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
    # True once the step's video segment has played (the learner has been told what to do).
    # None = the orchestrator doesn't say: treated as done, so a hidden app never leaves a
    # check pending forever. See _not_visible().
    segment_done: bool | None = None
    # The lesson's editor app ("Code" in a "Just teach me" VS Code lesson), else None. Its terminal is then the
    # learner's terminal: the details say "VS Code's terminal", never Terminal.app.
    editor: str | None = None
    # t9: the learner's notebook (server.checks.notebook.Notebook) on a notebook step; evaluate_step reads it from
    # the lesson folder when the orchestrator doesn't hand one in. False: none (looked, nothing there). t10:
    # evaluate_step narrows it to the step's own cells (Notebook.only): outputs / errors / ran are those cells' only.
    notebook: Any = None

    @property
    def after_segment(self) -> bool:
        return self.segment_done is not False

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
    """A value the way a training script prints it: plain decimals (test 8: 0.0009, never 9.00e-04)."""
    if v == 0 or not math.isfinite(v) or 1e-3 <= abs(v) < 1e4:
        return f"{v:.4g}"
    if abs(v) >= 1e4:
        return f"{v:.0f}"
    digits = 3 - math.floor(math.log10(abs(v)))  # 4 significant digits, no exponent
    return f"{v:.{digits}f}".rstrip("0").rstrip(".")


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
    if rel.strip().lower().endswith(".ipynb") and not os.path.exists(path) and os.path.isabs(str(ctx.workdir or "")):
        # t10: the video's Untitled.ipynb is the learner's mnist.ipynb ("Still to do: evaluate saved in notebook")
        if (found := find_notebook(ctx.workdir, [rel])) is not None:
            path, rel = str(found), found.name
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
    return _result(check, "fail", f"not in {rel} yet")


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


def _notebook_points(ctx: RunContext, check: dict | None) -> list[tuple[int, float]]:
    """t10 (the s5 blocker): a metric the step's own notebook cell printed, e.g. Keras's `accuracy: 0.9858` epoch lines
    (ANSI codes stripped by notebook.read_notebook). The run happened in the kernel, so no `tut run` / terminal
    output and often no screen ever shows them: the notebook file is where they are."""
    nb, pattern = ctx.notebook, (check or {}).get("metric_pattern")
    if not pattern or not isinstance(nb, Notebook) or not nb.outputs:
        return []
    return [(int(s), float(v)) for s, v in extract_metrics(pattern, "\n".join(nb.outputs))]


def _raw_series(ctx: RunContext, name: str, check: dict | None = None) -> list[tuple[int, float]]:
    """All points sorted by step, None/NaN/inf kept as float (NaN for None)."""
    raw = list(ctx.metrics.get(name, []))
    pattern = (check or {}).get("metric_pattern")
    if pattern and (nb_pts := _notebook_points(ctx, check)):
        raw = nb_pts  # the step's cell output on disk is exact; the screen / a terminal only saw part of it
    elif not raw and pattern:
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


def _no_metric(ctx: RunContext, name: str) -> str:
    """A finished run that printed no `name`, in plain words (test 7: a crash has no loss; the row says so and never
    shows an older run's): "no loss: the run stopped with an error" / "the run printed no loss"."""
    label = name.replace("_", " ")
    return f"no {label}: the run stopped with an error" if ctx.exit_code else f"the run printed no {label}"


def _waiting_for_metric(check: dict, ctx: RunContext, name: str) -> CheckResult:
    """No points yet. A screen-read metric whose app isn't on screen can't arrive by waiting:
    say which app to open, and (once the segment is over) fail so stuck/idle help can kick in."""
    app = check.get("app")
    if (check.get("metric_pattern") and app and ctx.screen is not None and not ctx.running
            and screen_text(ctx.screen, app) is None):
        return _result(check, "fail" if ctx.after_segment else "pending", f"open {app} so I can read {name}")
    where = f" in {app}" if app and check.get("metric_pattern") else ""
    return _result(check, "pending", f"waiting for the run's {name.replace('_', ' ')} lines{where}")  # t8: plain words


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
            return _result(check, "fail", _no_metric(ctx, name))
        return _waiting_for_metric(check, ctx, name)
    eligible = [p for p in pts if by_step is None or p[0] <= by_step]
    latest_step = pts[-1][0]
    # a notebook cell's Keras lines are per-epoch averages already: its last one is the result (t10: 0.9858)
    nb = ctx.notebook if _notebook_points(ctx, check) else None
    if eligible:
        recent = [v for _, v in eligible[-(1 if nb is not None else THRESHOLD_SMOOTH_POINTS):]]
        current = statistics.median(recent)
        at = eligible[-1][0]
        if _OPS[op](current, float(target)):
            where = f"in {nb.path.name}" if nb is not None else f"at step {at}"
            return _result(check, "pass", f"{name} {_fmt(current)} {op} {_fmt(float(target))} {where}")
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
            return _result(check, "fail", _no_metric(ctx, name))
        return _waiting_for_metric(check, ctx, name)
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
    where = f" in {_app_name(app, ctx)}" if app else " on screen"
    # the notebook as this step sees it (t10): every cell's source, but the outputs of the cells holding its own code
    nb = ctx.notebook if isinstance(ctx.notebook, Notebook) and app not in _TERMINAL_APPS else None
    output = not absent and app not in _TERMINAL_APPS and is_output_check(check)
    try:
        if nb is not None and absent and nb.errors and (e := search_screen(pattern, "\n".join(nb.errors))):
            return _result(check, "fail", f"the cell printed {e.group(0)[:80]!r}")  # t9 V3: a cell's error output
        if nb is not None and absent and not nb.executed:
            # t10: "No predict errors · not showing on screen" passed before the step's cell existed: no run, no verdict
            return _result(check, "pending", "checked when the cell runs")
        if nb is not None and not absent:  # t9 V2/V3: the notebook's cells as typed / what they printed decide first
            if search_wrapped(pattern, nb.output_text if output else nb.source_text):
                return _result(check, "pass", f"{'printed' if output else 'typed'} in {nb.path.name}")
            if output and _plotted(pattern, nb):
                return _result(check, "pass", f"plotted in {nb.path.name}")
    except re.error as exc:
        return _result(check, "fail", f"invalid pattern: {exc}")
    if output and nb is not None and not nb.executed:
        # t10: the step's cell hasn't run (or isn't written): whatever the screen shows is another cell's output
        # ("predict progress printed" passed on the TRAINING cell's "ms/step" before any s6 code existed)
        return _result(check, "fail", "not printed yet: run the cell")
    text = screen_text(ctx.screen, app)
    if text is None:
        return _not_visible(check, ctx, absent)
    if output:  # t9 V3: the print() line on screen is code, never the output it promises
        text = "\n".join(ln for ln in screen_lines(ctx.screen, app) or [] if not _code_line(ln, check.get("_code")))
    try:
        m = search_screen(pattern, text) if absent else search_wrapped(pattern, text)
    except re.error as exc:
        return _result(check, "fail", f"invalid pattern: {exc}")
    if output and not m:
        return _result(check, "fail", "not printed yet: run the cell" if nb is not None and not nb.executed
                       else "not printed yet")
    if absent:
        if m:
            return _result(check, "fail", f"still showing {m.group(0)[:80]!r}{where}")
        return _result(check, "pass", f"not showing{where}")
    if m:
        return _result(check, "pass", f"seen{where}")
    if app in _TERMINAL_APPS:  # the terminal is on screen, the output isn't: say that, not where to open it
        return _result(check, "fail", "not printed by the last run: run it again" if ctx.run_finished
                       else f"not printed{where} yet")
    # learner words (E2): the file the code goes in when known ("not in calculator.py yet"), else the app
    f = os.path.basename(str(check.get("file") or ""))
    return _result(check, "fail", f"not in {f} yet" if f else f"not{where} yet" if app else "not showing yet")


# a plot's own words, set in the cell's source: ax2.set_title('Class Probability'), plt.xlabel("Epoch"), ...
_PLOT_TEXT = re.compile(r"\b(?:set_title|suptitle|title|set_xlabel|set_ylabel|xlabel|ylabel|text|annotate|legend|"
                        r"set_label)\s*\(")


def _plotted(pattern: str, nb: Notebook) -> bool:
    """t10 (s6 "Class Probability title shown"): words that exist only inside a figure (a PNG output: no text the
    notebook holds, and OCR sees it only once the learner scrolls the plot into view). Passes when one of the step's
    cells ran without an error, displayed an image, and its source puts those words on the plot (set_title, xlabel,
    legend ...). OCR of the plot stays a second way to pass."""
    rx = re.compile(pattern, re.MULTILINE)
    for c in nb.cells:
        if not c.executed or c.errors or not any(str(m).startswith("image/") for m in c.images):
            continue
        if any(_PLOT_TEXT.search(ln) and rx.search(ln) for ln in c.source.splitlines()):
            return True
    return False


def _not_visible(check: dict, ctx: RunContext, absent: bool) -> CheckResult:
    """The check's app (or the whole screen) can't be seen. Never "pending forever":

    * screen_absent: nothing bad is visible, so once the segment is over it passes (a hidden
      Terminal can't be showing a Traceback). It fails only when the pattern is actually seen.
    * screen_contains: waiting can't help, so it says which app to open, and once the segment is
      over it fails with that hint (a fail is what lets the orchestrator's idle/stuck help fire).
      With no screen reading at all it stays pending: that's not the learner's fault.
    * A terminal check is graded on the step's last finished run instead (VS Code's command_end,
      `tut run`, Run it for me: the real output), and on a run step (``run``, set by evaluate_step)
      a screen_absent one waits for that run: nothing has run yet that could show the error (t3:
      "No Python error shown" passed 2 ms into the step, then stayed green over a SyntaxError).
    """
    app = check.get("app")
    no_screen = ctx.screen is None
    if app in _TERMINAL_APPS and ctx.run_finished:
        return _on_run_output(check, ctx, absent)
    if no_screen:
        # t9 V1: no frame yet (the reader resumes ~10 ms after step.started, or is off): nothing was looked at, so
        # nothing passes or fails. A screen_absent row passed "screen reading is off, so nothing to flag" and the
        # app kept it green (a pass never goes back to pending); the next real frame grades it.
        return _result(check, "pending", "checked when it runs" if absent and check.get("run") and app in _TERMINAL_APPS
                       else "waiting for the screen")
    if absent:
        if check.get("run") and app in _TERMINAL_APPS:
            return _result(check, "pending", "checked when it runs")
        if ctx.after_segment:
            why = f"{app} is not on screen" if app else "nothing on screen"
            return _result(check, "pass", f"{why}, so nothing to flag")
        return _result(check, "pending", f"{app} not open yet")
    if not app:
        hint = "nothing on screen yet"
    elif app in _TERMINAL_APPS and ctx.editor == "Code":  # a VS Code lesson runs code in VS Code's own terminal
        hint = "Open VS Code's terminal (⌃`) so I can check it."
    else:
        hint = f"Open {_APP_NAMES.get(app, app)} so I can check it."
    return _result(check, "fail" if ctx.after_segment and app else "pending", hint)


def _on_run_output(check: dict, ctx: RunContext, absent: bool) -> CheckResult:
    """A terminal check the screen can't read, graded on the output of the step's last finished run."""
    try:
        m = search_screen(str(check.get("pattern") or ""), ctx.output_text())
    except re.error as exc:
        return _result(check, "fail", f"invalid pattern: {exc}")
    if absent:
        if m:
            return _result(check, "fail", f"the last run printed {m.group(0)[:80]!r}")
        return _result(check, "pass", "not in the last run's output")
    return _result(check, "pass", "printed by the last run") if m else \
        _result(check, "fail", "the last run didn't print it")


_APP_NAMES = {"Code": "VS Code", "Terminal": "the Terminal", "iTerm2": "iTerm"}  # what the learner calls them
_TERMINAL_APPS = ("Terminal", "iTerm2")


def _app_name(app: str, ctx: RunContext) -> str:
    """What the learner calls the check's app; in a VS Code lesson the terminal is VS Code's own."""
    if app in _TERMINAL_APPS and ctx.editor == "Code":
        return "VS Code's terminal"
    return _APP_NAMES.get(app, app)


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
    f = _step_file(step)  # a VS Code check not seen yet names the file the code goes in ("not in calculator.py yet")
    checks = [{**c, "file": f} if f and c.get("type") == "screen_contains" and c.get("app") == "Code"
              and not c.get("file") else c for c in checks]
    # a run step's "no error in the terminal" waits for the run (_not_visible) instead of passing on a hidden terminal
    run = step.get("kind") == "run" or any(str(t.get("file") or "").strip().lower() in ("(terminal)", "terminal")
                                           for t in step.get("targets") or []) or _command_step(step)
    checks = [{**c, "run": True} if run and c.get("type") == "screen_absent" and c.get("app") in _TERMINAL_APPS
              else c for c in checks]
    ctx = _with_step_notebook(step, ctx)
    code = "\n".join([str(step.get("code") or "")] + [str(t.get("match") or "") for t in step.get("targets") or []]
                     + (ctx.notebook.sources if isinstance(ctx.notebook, Notebook) else []))
    checks = [{**c, "_code": code} if c.get("type") == "screen_contains" and is_output_check(c) else c for c in checks]
    return [evaluate_check(c, ctx) for c in checks if wanted is None or c.get("type") in wanted]


_NOTEBOOK_RUN = re.compile(r"shift\s*\+\s*enter|\bcells?\b|\bnotebook\b|\bjupyter\b|\bcolab\b", re.I)
# printed / shown results, never "output layer" / "print statement" (t9: s4c4 "Softmax output layer added" is code)
_OUTPUT_LABEL = re.compile(r"\b(printed|prints|shown|shows|displayed|logged|rendered|plotted)\b"
                           r"|\b(cell|run|program|console|terminal|printed|progress)\s+output\b"
                           r"|\boutput\s+(shown|printed|appears|visible|displayed)\b", re.I)
# a pattern that looks like code: an escaped ( ) or =, an attribute dot (mnist\.load_data), a CamelCase name
_CODE_PATTERN = re.compile(r"\\[()]|=|\\\.[A-Za-z_]|[a-z][A-Z]")
# a code line on screen: a print( call, a string literal opening after ( or closing before , / ), an f-string
_CODE_MARK = re.compile(r"\bprint\s*\(|\(\s*[fbr]?['\"]|['\"]\s*[,)]|\bf['\"]")


def _with_step_notebook(step: dict, ctx: RunContext) -> RunContext:
    """ctx with the step's notebook: read from the lesson folder on a notebook step (t9), then narrowed to the cells
    holding the step's own code (t10: its output / error / metric checks never read another cell's output; s7
    "evaluate progress output shown" passed on the training cell's progress bars). Idempotent."""
    if ctx.notebook is None and is_notebook_step(step) and os.path.isabs(str(ctx.workdir or "")):
        ctx = dataclasses.replace(ctx, notebook=read_notebook(find_notebook(ctx.workdir, _files(step))) or False)
    if isinstance(ctx.notebook, Notebook) and ctx.notebook.cells:
        ctx = dataclasses.replace(ctx, notebook=ctx.notebook.only(step_cells(ctx.notebook, step)))
    return ctx


_RUN_THE_CELL = re.compile(r"shift\s*\+\s*enter|\brun\s+(?:the|this|each|all|every)\s+cells?\b", re.I)


def cell_not_run(step: dict, ctx: RunContext | None) -> bool:
    """t10 (CP7: s2 passed with its corrected cell written but never run): a "Run the cell (Shift+Enter)" step whose
    code is in the notebook, in cells none of which has run (no execution count, no output). Such a step can't pass,
    whichever list or route says green."""
    if ctx is None or not _RUN_THE_CELL.search(str(step.get("run_command") or "")):
        return False
    nb = _with_step_notebook(step, ctx).notebook
    return isinstance(nb, Notebook) and bool(nb.cells) and not nb.executed


_CELL_ACTION = re.compile(r"shift\s*\+\s*enter|^\s*(?:run|execute|press|click)\s+(?:the|a|all|each|this)\b", re.I)


def _command_step(step: dict) -> bool:
    """A step whose work is a shell command (no code to type): its "No terminal errors" waits for that run instead of
    passing on a hidden terminal (t10: s1 "source .venv/bin/activate && jupyter notebook"). Never "Run the cell"."""
    rc = str(step.get("run_command") or "").strip()
    return bool(rc) and not _CELL_ACTION.search(rc) and not str(step.get("code") or "").strip()


def _anchors(step: dict) -> tuple[list[re.Pattern[str]], list[re.Pattern[str]]]:
    """The step's own code as patterns: (its targets' match text, whitespace aside; its code checks' regexes, never an
    output check's (that is what it prints), plus its notebook file_contains patterns)."""
    def rx(p: str) -> re.Pattern[str] | None:
        try:
            return re.compile(p, re.MULTILINE)
        except re.error:
            return None

    targets = []
    for t in step.get("targets") or []:
        flat = "".join(str(t.get("match") or "").split())
        if len(flat) >= 6:
            targets.append(rx(r"\s*".join(re.escape(ch) for ch in flat)))
    code = [rx(str(c["pattern"])) for c in step.get("checks") or [] if c.get("type") == "screen_contains"
            and c.get("pattern") and c.get("app") not in _TERMINAL_APPS and not is_output_check(c)]
    code += [rx(str(c["pattern"])) for c in step.get("precision_checks") or [] if c.get("type") == "file_contains"
             and c.get("pattern") and str(c.get("file") or "").lower().endswith(".ipynb")]
    return [r for r in targets if r], [r for r in code if r]


def step_cells(nb: Notebook, step: dict) -> list[int]:
    """t10: indices (into nb.cells) of the code cells holding the step's own code. The cells with its target text
    (model.fit(, plt.subplots(1, 10 ...) plus any cell with two or more of its code patterns; when no cell has the
    target text, any cell with one of its code patterns (s3's plt.subplots( is in s6's view_classify too, so a lone
    code pattern only counts without a target match). No patterns at all: a line of its `code`. [] = not there yet."""
    targets, code = _anchors(step)

    def hits(rxs: list[re.Pattern[str]], src: str) -> int:
        flat = re.sub(r"\s+", " ", src)
        return sum(1 for r in rxs if r.search(src) or r.search(flat))

    by_target = [i for i, c in enumerate(nb.cells) if hits(targets, c.source)]
    if by_target:
        return sorted(set(by_target) | {i for i, c in enumerate(nb.cells) if hits(code, c.source) >= 2})
    if code:
        return [i for i, c in enumerate(nb.cells) if hits(code, c.source)]
    lines = {" ".join(ln.split()) for ln in str(step.get("code") or "").splitlines() if len(ln.strip()) >= 16}
    return [i for i, c in enumerate(nb.cells) if lines and any(" ".join(ln.split()) in lines
                                                                 for ln in c.source.splitlines())]


def _files(step: dict) -> list[str]:
    return [str(x.get("file") or "") for x in [*(step.get("targets") or []), *(step.get("checks") or []),
                                               *(step.get("precision_checks") or [])]] + [str(step.get("file") or "")]


def is_notebook_step(step: dict) -> bool:
    """A step done in a Jupyter notebook: a target / check file is an .ipynb, or its run is a cell run."""
    if any(f.strip().lower().endswith(".ipynb") for f in _files(step)):
        return True
    return bool(_NOTEBOOK_RUN.search(str(step.get("run_command") or "")))


def is_output_check(check: dict) -> bool:
    """t9 V3: a screen_contains check about what the code PRINTS ("Image shape line printed"), graded on output only,
    never on the code that prints it. An explicit ``output`` (bool) on the check decides; else its label says so
    (printed / output / shown / displayed ...). Terminal checks keep their own rules."""
    if check.get("type") != "screen_contains" or check.get("app") in _TERMINAL_APPS:
        return False
    if isinstance(check.get("output"), bool):
        return check["output"]
    if _CODE_PATTERN.search(str(check.get("pattern") or "")):
        return False  # a pattern for code (model\.predict\(): a code check, whatever its label says
    return bool(_OUTPUT_LABEL.search(str(check.get("label") or "")))


def _code_line(line: str, code: str | None) -> bool:
    """Is this OCR line the learner's code rather than output? A print( / string-literal line, or a whole line of the
    step's code / the notebook's cells (whitespace aside)."""
    if _CODE_MARK.search(line):
        return True
    norm = " ".join(line.split())
    return bool(norm) and any(norm == " ".join(c.split()) for c in (code or "").splitlines())


def _step_file(step: dict) -> str:
    """The step's file (its first target's, check's or own ``file``), for the learner-worded details. A run step's
    "(terminal)" / "terminal" is a place, not a file."""
    names = [t.get("file") for t in step.get("targets") or []]
    names += [c.get("file") for c in (step.get("checks") or []) + (step.get("precision_checks") or [])]
    for n in [*names, step.get("file")]:
        n = str(n or "").strip()
        if n and not n.startswith("(") and n.lower() not in ("terminal", "the terminal", "shell"):
            return n
    return ""


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
    if cell_not_run(step, ctx):
        # t10: typed is not run. When no row already says why (an error / output check waits for the run), one does.
        if step_passed(checks):
            checks = [*checks, {"checkId": f"{step.get('id', '')}-cell", "label": "Cell run", "status": "pending",
                                "detail": "run the cell (Shift+Enter)"}]
        return {"passed": False, "via": None, "checks": checks, "precision": prec}
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


# ---------------------------------------------------------------- lesson-file and run evidence
# Used by the orchestrator in "Just teach me" lessons, where the step's file in the lesson folder is the truth and
# the screen is only one way of seeing it (QA 11-14: a second VS Code window in front un-passed checks, and a run
# step passed on the code alone).

def screen_check_on_file(check: dict, path: str | os.PathLike | None, window_open: bool = True) -> CheckResult:
    """Grade a ``screen_contains`` check on the lesson's file on disk instead of the screen, for when the screen
    can't show the lesson's editor window (another folder's window is the one in front, or no editor text is in the
    frame). ``path`` is the step's file in the lesson folder (missing = empty). ``window_open``: a lesson editor
    window exists somewhere (another Space, behind, still opening).

    pass when the pattern is in the file; otherwise fail "not in <file> yet", or "Open VS Code so I can check it."
    only when no lesson window exists at all AND the file can't be read (live test 3: s2c3 said "Open VS Code so I
    can check it." while the rows above it said "found in weather.py": a readable file answers the question)."""
    pattern = check.get("pattern")
    if not pattern:
        return _result(check, "fail", "check has no 'pattern'")
    name = os.path.basename(os.fspath(path)) if path else "the lesson file"
    text, readable = "", False
    if path:
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text, readable = fh.read(), True
        except OSError:
            text = ""
    try:
        m = search_screen(pattern, text) if text else None
    except re.error as exc:
        return _result(check, "fail", f"invalid pattern: {exc}")
    if m:
        return _result(check, "pass", f"found in {name}")
    if not window_open and not readable:
        app = check.get("app")
        return _result(check, "fail", f"Open {_APP_NAMES.get(app, app)} so I can check it." if app
                       else f"not in {name} yet")
    return _result(check, "fail", f"not in {name} yet")


def command_matches(expected: str | None, actual: str | None) -> bool:
    """Does the command that ran (``actual``) run what ``expected`` runs? Interpreter wrappers and flags are ignored
    (``python3 calculator.py`` == ``tut run python calculator.py``); an empty side never matches. A command with no
    script (``python3 --version``, ``node -v``, ``python3``) must end ``actual`` as a whole (python == python3)."""
    if not expected or not actual:
        return False
    if not _script_tokens(expected):
        return _ends_with(actual, _seq(expected))
    # A Python run is ANY python invocation of the script: VS Code's Run ▷ ("/abs/.venv/bin/python" "/abs/nn.py"),
    # `tut run python nn.py`, `uv run nn.py`; never another program that names the file (`cat nn.py`, `code nn.py`).
    if _runs_python(expected) and not _runs_python(actual):
        return False
    return _command_matches(expected, actual)


_INTERP = re.compile(r"python(3(\.\d+)?)?")
_PY_RUNNERS = {"python", "tut", "uv", "ipython", "pipenv", "poetry"}


def _runs_python(command: str) -> bool:
    """Does ``command`` start Python: a python interpreter (any path / version: ``.venv/bin/python``,
    ``python3.12``) or a runner that does (``tut``, ``uv``)?"""
    for t in _words(command):
        if "=" in t and not t.startswith(("/", ".")):
            continue  # env assignments (X=1 python3 nn.py)
        name = os.path.basename(t)
        if name in _PY_RUNNERS or re.fullmatch(r"python[\d.]*t?", name):
            return True
    return False
# Python's crash output (a traceback, or a SyntaxError / IndentationError line) and the shell's "can't run it"
_RUN_ERROR = re.compile(r"^\s*[A-Z]\w*(Error|Exception):|Traceback \(most recent call last\)|command not found"
                        r"|No such file or directory|can't open file")


def _words(text: str) -> list[str]:
    try:
        return shlex.split(text)
    except ValueError:
        return text.split()


def _program(token: str) -> str:
    """``/usr/bin/python3.12`` -> ``python``; other programs by their file name."""
    name = os.path.basename(token)
    return "python" if _INTERP.fullmatch(name) else name


def _seq(text: str) -> list[str]:
    """A command as words for a whole-command match: programs by name (``python3`` -> ``python``), flags without
    their dashes (OCR may read ``--version`` as ``—version``)."""
    return [w for w in (_program(t).lstrip("-\u2013\u2014") for t in _words(text)) if w]


def _ends_with(text: str, whole: list[str]) -> bool:
    """Does ``text`` (a terminal row, or a command line such as ``cd x && python3 --version``) end with the command
    ``whole`` (from ``_seq``)?"""
    got = _seq(text)
    return bool(whole) and got[-len(whole):] == whole


def run_output(lines: Iterable[str], expect: Iterable[str] = ()) -> tuple[bool, bool]:
    """``(error, shows)`` for a run's output ``lines``: ``shows`` = one of the ``expect`` regexes (the step's expected
    output) is in it; ``error`` = it shows a crash (a traceback, an ``XError:`` line, "command not found", ...) that
    the step didn't ask for. An expected pattern found in the error lines ("run it and see the ZeroDivisionError")
    makes the crash the step's point, not a failure; expected output printed before a crash doesn't."""
    lines = [str(x) for x in lines]
    text = "\n".join(lines)
    errs = "\n".join(x for x in lines if _RUN_ERROR.search(x))
    shows = wanted = False
    for pattern in expect:
        try:
            shows = shows or bool(search_screen(pattern, text))
            wanted = wanted or bool(errs and search_screen(pattern, errs))
        except re.error:
            continue
    return bool(errs) and not wanted, shows


def terminal_runs(command: str, rows: list[str], expect: Iterable[str] = ()) -> tuple[int, bool, bool]:
    """``(runs, error, shows)`` for terminal ``rows`` (visual lines, top to bottom): how many times they show
    ``command`` being RUN, and for the output after the last such run ``run_output``'s ``(error, shows)``: a crash
    the step didn't ask for, and the step's expected output (``expect`` regexes, e.g. ``^5$``).

    A run is a row that names what the command runs (its script tokens, plus its program: ``python``/``python3``,
    or ``tut``; a command with no script, ``python3 --version``, ends the row whole) with at least one row after it
    (Enter was pressed: output or a new prompt). A command typed but not yet run is the bottom row, so it never
    counts; neither does a traceback line that mentions the file. When a later row runs the same program (another
    script, or this one misread by OCR: ``calculator.pv``), the output under the last run seen may not be the latest
    run's, so it never counts as shown."""
    want = _script_tokens(command)
    head = next((_program(t) for t in _words(command) if "=" not in t), "")  # skip env assignments (X=1 cmd)
    whole = [] if want else _seq(command)
    if not head or not (want or whole):
        return 0, False, False

    def runs_program(row: str) -> bool:
        names = {_program(t) for t in _words(row)}
        return head in names or "tut" in names

    def is_run(row: str) -> bool:
        if whole:
            return _ends_with(row, whole)
        return all(w in _script_tokens(row) for w in want) and runs_program(row)

    n, last = 0, None
    for i, row in enumerate(rows[:-1]):
        if is_run(row):
            n, last = n + 1, i
    if last is None:
        return 0, False, False
    err, shows = run_output(rows[last + 1:], expect)
    if shows and any(runs_program(r) for r in rows[last + 1:-1]):
        shows = False
    return n, err, shows

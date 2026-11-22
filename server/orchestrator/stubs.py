"""Canned stand-ins for the modules other sessions own (lesson, checks, coach, finder,
diagrams). Signatures follow shared/contracts/engine-internal.md. They return
PINN-flavoured data so the whole loop works before the real modules land.

`evaluate_step` here is a small but real evaluator (not canned): the state machine
needs honest pass/fail to be testable.
"""

from __future__ import annotations

import copy
import json
import math
import re
from pathlib import Path
from typing import Any

from .config import FIXTURES
from .context import RunContext

# ---------------------------------------------------------------- finder

SEARCH_RESULTS = [
    {
        "id": "r1", "kind": "video", "score": 0.94,
        "title": "Physics-informed neural networks: convection in PyTorch",
        "meta": "YouTube · 9 min",
        "reason": "Codes the convection PINN step by step; matches your goal exactly.",
        "url": "https://www.youtube.com/watch?v=STUB_PINN_VID",
    },
    {
        "id": "r2", "kind": "paper", "score": 0.88,
        "title": "Characterizing possible failure modes in PINNs",
        "meta": "NeurIPS 2021 · Krishnapriyan et al.",
        "reason": "Explains why convection at large β fails and how a curriculum fixes it.",
        "url": "https://arxiv.org/abs/2109.01050",
    },
    {
        "id": "r3", "kind": "notebook", "score": 0.71,
        "title": "PINN convection notebook",
        "meta": "Colab · PyTorch",
        "reason": "Runnable reference code; fewer explanations.",
        "url": "https://colab.research.google.com/",
    },
]


async def search(query: str) -> list[dict]:
    return copy.deepcopy(SEARCH_RESULTS)


# ---------------------------------------------------------------- lesson


def load_fixture_lesson() -> dict:
    return json.loads((FIXTURES / "pinn_lesson.json").read_text(encoding="utf-8"))


def text_lesson(graph: dict, goal: str = "") -> dict:
    """A video lesson made into a "lesson" mode one (no video): DEMO's stand-in for E2's build_text_lesson."""
    g = json.loads(json.dumps(graph))
    g.setdefault("lesson", {})["mode"] = "lesson"
    if goal:
        g["lesson"]["goal"] = goal
    for st in g.get("steps", []):
        st.pop("video", None)
    g["sources"] = [s for s in g.get("sources", []) if s.get("kind") != "video"]
    return g


async def build_text_lesson(goal: str, workdir: str) -> dict:
    return text_lesson(load_fixture_lesson(), goal)


async def build_lesson(source_url: str, goal: str, workdir: str) -> dict:
    graph = load_fixture_lesson()
    if goal:
        graph["lesson"]["goal"] = goal
    return graph


# ---------------------------------------------------------------- checks

_OPS = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
}


def _res(check: dict, status: str, detail: str | None = None) -> dict:
    out = {"checkId": check["id"], "label": check.get("label", check["id"]), "status": status}
    if detail:
        out["detail"] = detail
    return out


def _fmt(v: float) -> str:
    return f"{v:.3g}"


def _screen_text(screen, app: str | None) -> str | None:
    """screen = {app: [lines]} (ScreenObservation.lines_by_app()) or a plain string."""
    if screen is None:
        return None
    if isinstance(screen, str):
        return screen
    chunks = [("\n".join(v) if isinstance(v, list) else str(v)) for a, v in screen.items()
              if not app or app.lower() in (a or "").lower()]
    return "\n".join(chunks) if chunks else None


def _eval_screen(check: dict, ctx: RunContext, absent: bool) -> dict:
    text = _screen_text(getattr(ctx, "screen", None), check.get("app"))
    if text is None:
        return _res(check, "pending", "not on screen yet")
    try:
        found = re.search(check.get("pattern", ""), text, re.I | re.M) is not None
    except re.error:
        found = check.get("pattern", "") in text
    if absent:
        return _res(check, "fail" if found else "pass")
    return _res(check, "pass" if found else "fail")


def _eval_check(check: dict, ctx: RunContext) -> dict:
    t = check.get("type")
    wd = Path(ctx.workdir)
    if t in ("screen_contains", "screen_absent"):
        return _eval_screen(check, ctx, absent=t == "screen_absent")
    if t == "file_exists":
        ok = (wd / check["file"]).exists()
        return _res(check, "pass" if ok else "fail", None if ok else f"{check['file']} not found")
    if t == "file_contains":
        p = wd / check["file"]
        if not p.exists():
            return _res(check, "fail", f"{check['file']} not found")
        try:
            text = p.read_text(errors="replace")
        except OSError as e:
            return _res(check, "fail", str(e))
        ok = re.search(check["pattern"], text, re.MULTILINE) is not None
        return _res(check, "pass" if ok else "fail")
    if t == "command_exit_ok":
        run = ctx.last_run
        if run is None or run.running:
            return _res(check, "pending", "waiting for a run" if run is None else "running")
        ok = run.exit_code == 0
        return _res(check, "pass" if ok else "fail", None if ok else f"exit code {run.exit_code}")
    if t == "output_contains":
        run = ctx.last_run
        if run is None:
            return _res(check, "pending", "waiting for a run")
        ok = re.search(check["pattern"], "\n".join(run.output_tail), re.MULTILINE) is not None
        if ok:
            return _res(check, "pass")
        return _res(check, "pending" if run.running else "fail")
    if t == "metric_threshold":
        return _eval_threshold(check, ctx)
    if t == "metric_trend":
        return _eval_trend(check, ctx)
    if t == "visual":
        return _res(check, "pending", "visual checks need the real checks module")
    return _res(check, "pending", f"unknown check type {t}")


def _eval_threshold(check: dict, ctx: RunContext) -> dict:
    run = ctx.last_run
    pts = ctx.metrics.get(check["metric"], [])
    if any(v is None for _, v in pts):
        return _res(check, "fail", f"{check['metric']} became NaN/inf")
    if not pts:
        return _res(check, "pending", "waiting for metrics")
    op = _OPS[check.get("op", "<")]
    by = check.get("by_step")
    eligible = [(s, v) for s, v in pts if by is None or s <= by]
    hit = next(((s, v) for s, v in eligible if op(v, check["value"])), None)
    s_last, v_last = pts[-1]
    if hit:
        return _res(check, "pass", f"{check['metric']} {_fmt(hit[1])} at step {hit[0]}")
    detail = f"{check['metric']} {_fmt(v_last)} at step {s_last}"
    if (by is not None and s_last > by) or (run is not None and not run.running):
        return _res(check, "fail", detail)
    return _res(check, "pending", detail)


def _eval_trend(check: dict, ctx: RunContext) -> dict:
    pts = ctx.metrics.get(check["metric"], [])
    if any(v is None for _, v in pts):
        return _res(check, "fail", f"{check['metric']} became NaN/inf")
    window = int(check.get("window") or 500)
    if len(pts) < 5:
        return _res(check, "pending", "waiting for metrics")
    s_last, v_last = pts[-1]
    peak = max(v for _, v in pts)
    # dropped by an order of magnitude overall: clearly not stuck
    if peak > 0 and v_last < 0.1 * peak:
        return _res(check, "pass", f"{check['metric']} {_fmt(v_last)}")
    recent = [(s, v) for s, v in pts if s >= s_last - window]
    if s_last - pts[0][0] < window or len(recent) < 4:
        return _res(check, "pending", f"{check['metric']} {_fmt(v_last)}")
    q = max(1, len(recent) // 4)
    head = sum(v for _, v in recent[:q]) / q
    tail = sum(v for _, v in recent[-q:]) / q
    drop = (head - tail) / max(abs(head), 1e-12)
    trend = check.get("trend", "not_flat")
    ok = drop > 0 if trend == "decreasing" else drop >= 0.10
    if ok:
        return _res(check, "pass", f"{check['metric']} {_fmt(v_last)}")
    return _res(check, "fail", f"{check['metric']} flat at {_fmt(v_last)} for {window} steps")


def evaluate_step(step: dict, ctx: RunContext, which: str = "checks") -> list[dict]:
    key = "precision_checks" if which == "precision" else "checks"
    return [_eval_check(c, ctx) for c in step.get(key) or []]


def _all_pass(results: list[dict]) -> bool:
    return bool(results) and all(r["status"] == "pass" for r in results)


def evaluate_gate(step: dict, ctx: RunContext, screen=None, precision_mode: bool = False) -> dict:
    """Same contract as server.checks.evaluate_gate: `checks` gate the step; in precision mode
    all-passing `precision_checks` are an extra route to green, never an extra hurdle."""
    if screen is not None:
        ctx.screen = screen
    checks = evaluate_step(step, ctx)
    prec = evaluate_step(step, ctx, "precision") if precision_mode else []
    via = "checks" if _all_pass(checks) else ("precision" if precision_mode and _all_pass(prec) else None)
    return {"passed": via is not None, "via": via, "checks": checks, "precision": prec}


# ---------------------------------------------------------------- coach

PINN_CITATION = {
    "label": "Krishnapriyan et al., NeurIPS 2021",
    "url": "https://arxiv.org/abs/2109.01050",
}
CURRICULUM_LINE = "for beta in [1, 5, 10, 20, 30]:  # β curriculum\n    train_stage(model, beta)"


def _find_line(code: str, pattern: str) -> tuple[int, str] | None:
    for i, line in enumerate(code.splitlines(), start=1):
        if re.search(pattern, line):
            return i, line.strip()
    return None


async def diagnose(step: dict, failed_checks: list[dict], metrics_summary: dict, code_excerpt: str, **_: Any) -> dict:
    if any(isinstance(v, list) for v in (metrics_summary or {}).values()):  # raw series -> summary
        from .context import metrics_summary as _summ

        metrics_summary = _summ(metrics_summary)
    metric_fail = any(c.get("type", "").startswith("metric") for c in failed_checks)
    if metric_fail:
        loss = metrics_summary.get("loss", {}).get("last")
        flat = f" near {_fmt(loss)}" if loss is not None else ""
        out: dict[str, Any] = {
            "stepId": step["id"],
            "severity": "warn",
            "title": "Loss plateaued at large β",
            "body": f"Known PINN failure: at large β the loss stalls{flat}. "
                    "Train with a β curriculum: start at β = 1, ramp up to 30.",
            "citation": PINN_CITATION,
            "actions": ["explain", "show_me", "hint", "apply_fix"],
        }
        hit = _find_line(code_excerpt or "", r"beta\s*=\s*\d+|--beta")
        if hit:
            out["diff"] = {"expected": CURRICULUM_LINE, "yours": hit[1], "file": "pinn_convection.py", "line": hit[0]}
        return out
    first = failed_checks[0] if failed_checks else {"label": step.get("title", "this step")}
    hints = step.get("hints") or [step.get("instructions", "")]
    return {
        "stepId": step["id"],
        "severity": "warn",
        "title": f"Not yet: {first.get('label', '')}"[:60],
        "body": hints[0],
        "actions": ["explain", "show_me", "hint"],
    }


def _video_jump(step: dict) -> dict | None:
    exps = step.get("explanations") or []
    if not exps:
        return None
    e = exps[0]
    t = float(e.get("t", 0))
    return {"t": t, "label": f"{e.get('topic', 'Explained')} · {int(t) // 60}:{int(t) % 60:02d}"}


async def explain(step: dict, question: str | None, context: dict) -> dict:
    card: dict[str, Any] = {
        "stepId": step["id"],
        "kind": "answer" if question else "explain",
        "title": step.get("title", "This step"),
        "body": step.get("instructions", ""),
    }
    if "β" in step.get("title", "") or "beta" in (question or "").lower():
        card["title"] = "Why large β breaks PINNs"
        card["body"] = ("Large β makes the residual landscape sharp, so gradient descent stalls. "
                        "Easing β up lets the network track the solution.")
    vj = _video_jump(step)
    if vj:
        card["videoJump"] = vj
    return card


def hint(step: dict, level: int) -> dict:
    hints = step.get("hints") or [step.get("instructions", "Re-watch this step.")]
    i = max(0, min(level, len(hints) - 1))
    card: dict[str, Any] = {
        "stepId": step["id"],
        "kind": "hint",
        "title": f"Hint {i + 1} of {len(hints)}",
        "body": hints[i],
    }
    vj = _video_jump(step)
    if vj and i >= 1:
        card["videoJump"] = vj
    return card


def apply_fix(diff: dict, file_text: str) -> str | None:
    """Replace the single line equal to diff.yours with diff.expected (multi-line ok), keeping indentation."""
    yours, expected = (diff.get("yours") or "").strip(), diff.get("expected") or ""
    if not yours or not expected:
        return None
    lines = file_text.splitlines(keepends=True)
    hits = [i for i, ln in enumerate(lines) if ln.strip() == yours.splitlines()[0].strip()]
    if len(hits) != 1:
        return None
    i = hits[0]
    indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
    repl = [indent + ln + "\n" for ln in expected.splitlines()]
    return "".join(lines[:i] + repl + lines[i + max(1, len(yours.splitlines())):])


async def fix_outdated(error_text: str, libraries: dict) -> dict | None:
    return None


# ---------------------------------------------------------------- diagrams


def build_diagram(kind: str, step: dict | None, ctx: RunContext | None) -> dict:
    if kind == "gradients":
        layers = ["layer1", "layer2", "layer3", "layer4", "out"]
        metrics = ctx.metrics if ctx else {}
        real = [n for n in metrics if n.startswith("grad_norm/")]
        if real:
            names = sorted(real)
            epochs = [s for s, _ in metrics[names[0]]][-20:]
            norms = [[v for _, v in metrics[n]][-20:] for n in names]
            return {"kind": "gradients", "caption": "Gradient norm per layer during training",
                    "data": {"layers": [n.split("/", 1)[1] for n in names], "epochs": epochs, "norms": norms}}
        epochs = [i * 250 for i in range(12)]
        norms = [[round(1e-1 * math.exp(-0.35 * i) * (0.4 ** li), 8) for i in range(12)] for li in range(len(layers))]
        return {"kind": "gradients", "caption": "Early layers stop learning: gradients vanish at β = 30",
                "data": {"layers": layers, "epochs": epochs, "norms": norms}}
    if kind == "heatmap":
        nx, nt, beta = 32, 16, 30.0
        xs = [2 * math.pi * i / (nx - 1) for i in range(nx)]
        ts = [j / (nt - 1) for j in range(nt)]
        exact = [[round(math.sin(x - beta * t), 4) for x in xs] for t in ts]
        pred = [[round(math.sin(x) * math.exp(-3 * t), 4) for x in xs] for t in ts]
        return {"kind": "heatmap", "caption": "Predicted u(x,t) misses the fast-moving wave",
                "data": {"x": xs, "t": ts, "predicted": pred, "exact": exact}}
    return {"kind": "network", "caption": "u(x,t) from a tanh MLP; autograd gives u_t and u_x",
            "data": {"layers": [2, 50, 50, 50, 50, 1], "activation": "tanh",
                     "derivatives": ["u_t", "u_x"], "residual": "u_t + β·u_x"}}


async def diagrams_build(kind: str, step: dict | None = None, ctx: RunContext | None = None) -> dict:
    return build_diagram(kind, step, ctx)

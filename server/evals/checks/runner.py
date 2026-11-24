"""Score the deterministic step checks (server.checks.evaluate_gate) on the cases in cases/*.json.

Each case is one moment of a real lesson: a step (by reference into a lesson JSON in the repo, or inline), the
learner's workspace at that moment (files in the lesson folder, a notebook, what the screen shows, the last run,
metrics) and the verdict a careful human tutor would give: "pass" (the step is done) or "not_yet". The runner builds
the lesson folder in a temp dir, calls evaluate_gate exactly as the orchestrator does, and compares.

"pass" is the positive class:
  precision = of the steps the checks passed, how many really were done   (1 - precision: false passes)
  recall    = of the steps that were done, how many the checks passed     (1 - recall: false "not yet"s)
A false pass is the worse error (the learner moves on with broken work), so failures are listed false passes first.

Held-out cases ("heldOut": true) are scored and reported on their own and never used to tune the checks: the train
set's scores, wrong verdicts and baseline are what a fix works against; the held-out set only says whether a fix
generalises. The report gives held-out scores and the ids of its wrong verdicts, never their rows (--held-out shows
them, for a human reviewing the set, not for a fix loop).

No model call, no network, no screen: pure functions on files written to a temp folder.
"""
from __future__ import annotations

import copy
import json
import math
import os
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]  # the repo root
HERE = Path(__file__).resolve().parent
CASES_DIR = HERE / "cases"
BASELINE = HERE / "baseline.json"

VERDICTS = ("pass", "not_yet")
KINDS = ("jupyter", "vscode", "terminal", "metric")
TRAPS = ("none", "false_pass", "false_fail")


# ------------------------------------------------------------------ loading
def load_cases(directory: Path = CASES_DIR) -> list[dict]:
    cases = []
    for p in sorted(directory.glob("*.json")):
        case = json.loads(p.read_text(encoding="utf-8"))
        case.setdefault("id", p.stem)
        case["_path"] = str(p.relative_to(ROOT))
        problems = validate_case(case)
        if problems:
            raise ValueError(f"{p.name}: " + "; ".join(problems))
        cases.append(case)
    ids = [c["id"] for c in cases]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"duplicate case ids: {sorted(dupes)}")
    return cases


def validate_case(case: dict) -> list[str]:
    out = []
    if case.get("expected") not in VERDICTS:
        out.append(f"expected must be one of {VERDICTS}")
    if case.get("kind") not in KINDS:
        out.append(f"kind must be one of {KINDS}")
    if case.get("trap", "none") not in TRAPS:
        out.append(f"trap must be one of {TRAPS}")
    if not isinstance(case.get("step"), dict):
        out.append("step must be an object")
    if not str(case.get("why") or "").strip():
        out.append("why (the reason for the expected verdict) is required")
    if not isinstance(case.get("heldOut", False), bool):
        out.append("heldOut must be true or false")
    return out


def is_held_out(case: dict) -> bool:
    """A held-out case: scored and reported apart, never used to tune a fix."""
    return case.get("heldOut") is True


_LESSONS: dict[str, dict] = {}


def resolve_step(case: dict) -> dict:
    """The case's step: {"lesson": <repo path>, "id": <step id>} (+ optional "patch": shallow overrides, and
    "drop_checks": check ids to remove), or an inline step with its own "checks"."""
    spec = case["step"]
    if "lesson" in spec:
        path = spec["lesson"]
        if path not in _LESSONS:
            _LESSONS[path] = json.loads((ROOT / path).read_text(encoding="utf-8"))
        lesson = _LESSONS[path]
        steps = lesson.get("steps") or (lesson.get("lesson") or {}).get("steps") or []
        try:
            step = copy.deepcopy(next(s for s in steps if s.get("id") == spec["id"]))
        except StopIteration:
            raise ValueError(f"{case['id']}: no step {spec['id']!r} in {path}") from None
    else:
        step = {k: copy.deepcopy(v) for k, v in spec.items() if k not in ("patch", "drop_checks")}
    step.update(copy.deepcopy(spec.get("patch") or {}))
    drop = set(spec.get("drop_checks") or [])
    if drop:
        for key in ("checks", "precision_checks"):
            step[key] = [c for c in step.get(key) or [] if c.get("id") not in drop]
    return step


# ------------------------------------------------------------------ the learner's workspace
def _notebook(spec: dict) -> dict:
    """An .ipynb from {"from": <repo path>, "keep_cells": n, "unrun": [i], "replace": [[i, old, new]],
    "append": [cell], "counts": [n | null, ...], "kernel": str, "kernel_version": str} or {"cells": [cell, ...]}.
    A cell: {"source": str, "run": bool, "count": int, "stdout": str, "error": "Name: msg", "image": bool,
    "markdown": bool}. "count" is the cell's execution count (default: its position); "counts" sets the counts of
    the whole notebook's cells in order (run order, a kernel restart), null leaving one as it is."""
    if "from" in spec:
        nb = json.loads((ROOT / spec["from"]).read_text(encoding="utf-8"))
        if "keep_cells" in spec:
            nb["cells"] = nb["cells"][: int(spec["keep_cells"])]
    else:
        nb = {"cells": [], "metadata": {"kernelspec": {"display_name": ".venv", "language": "python",
                                                       "name": "python3"}},
              "nbformat": 4, "nbformat_minor": 5}
    for i in spec.get("unrun") or []:
        nb["cells"][i]["execution_count"] = None
        nb["cells"][i]["outputs"] = []
    for i, old, new in spec.get("replace") or []:
        cell = nb["cells"][i]
        cell["source"] = "".join(cell["source"]).replace(old, new) if isinstance(cell["source"], list) \
            else cell["source"].replace(old, new)
        for out in cell.get("outputs") or []:
            if "text" in out:
                out["text"] = "".join(out["text"]).replace(old, new) if isinstance(out["text"], list) \
                    else out["text"].replace(old, new)
    for n, c in enumerate([*(spec.get("cells") or []), *(spec.get("append") or [])]):
        nb["cells"].append(_cell(c, n))
    for cell, count in zip(nb["cells"], spec.get("counts") or []):
        if count is not None and cell.get("cell_type") == "code":
            cell["execution_count"] = int(count)
    meta = nb.setdefault("metadata", {})
    if "kernel" in spec:
        meta.setdefault("kernelspec", {})["display_name"] = spec["kernel"]
    if "kernel_version" in spec:
        meta.setdefault("language_info", {})["version"] = spec["kernel_version"]
    return nb


def _cell(c: dict, n: int) -> dict:
    if c.get("markdown"):
        return {"cell_type": "markdown", "id": f"m{n}", "metadata": {}, "source": c.get("source", "")}
    outputs: list[dict] = []
    if c.get("stdout"):
        outputs.append({"output_type": "stream", "name": "stdout", "text": c["stdout"]})
    if c.get("image"):
        outputs.append({"output_type": "display_data", "metadata": {},
                        "data": {"image/png": "iVBORw0KGgo=", "text/plain": "<Figure size 600x900 with 2 Axes>"}})
    if c.get("error"):
        name, _, msg = str(c["error"]).partition(":")
        outputs.append({"output_type": "error", "ename": name.strip(), "evalue": msg.strip(),
                        "traceback": ["Traceback (most recent call last)", f"{name.strip()}: {msg.strip()}"]})
    ran = bool(c.get("run", bool(outputs)))
    count = int(c["count"]) if c.get("count") is not None else n + 1
    return {"cell_type": "code", "id": f"c{n}", "metadata": {}, "execution_count": count if ran else None,
            "outputs": outputs if ran else [], "source": c.get("source", "")}


def build_workdir(files: dict[str, Any], root: Path) -> None:
    """Write the case's lesson folder: a str is a text file, {"notebook": {...}} an .ipynb, {"dir": true} a folder."""
    for rel, spec in (files or {}).items():
        p = root / rel
        if os.path.isabs(rel) or ".." in Path(rel).parts:
            raise ValueError(f"case file {rel!r} must stay in the lesson folder")
        if isinstance(spec, dict) and spec.get("dir"):
            p.mkdir(parents=True, exist_ok=True)
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(spec, dict) and "notebook" in spec:
            p.write_text(json.dumps(_notebook(spec["notebook"])), encoding="utf-8")
        elif isinstance(spec, str):
            p.write_text(spec, encoding="utf-8")
        else:
            raise ValueError(f"case file {rel!r}: a string, {{'notebook': ...}} or {{'dir': true}}")


def _num(v: Any) -> float:
    return math.nan if v is None or v == "nan" else float(v)


def make_context(ws: dict, workdir: str):
    from server.checks import RunContext

    run = ws.get("run") or {}
    metrics = {k: [(int(s), _num(v)) for s, v in pts] for k, pts in (ws.get("metrics") or {}).items()}
    return RunContext(
        workdir=workdir,
        exit_code=run.get("exit_code"),
        output_tail=run.get("output_tail") or [],
        command=run.get("command"),
        running=bool(run.get("running", False)),
        metrics=metrics,
        visual=ws.get("visual") or {},
        screen=ws.get("screen"),
        segment_done=ws.get("segment_done", True),
        editor=ws.get("editor"),
    )


# ------------------------------------------------------------------ running
@dataclass
class Outcome:
    case: dict
    got: str
    via: str | None
    rows: list[dict] = field(default_factory=list)
    error: str | None = None
    ms: float = 0.0

    @property
    def expected(self) -> str:
        return self.case["expected"]

    @property
    def correct(self) -> bool:
        return self.got == self.expected

    @property
    def label(self) -> str:
        if self.correct:
            return "TP" if self.got == "pass" else "TN"
        return "FP" if self.got == "pass" else "FN"


def run_case(case: dict) -> Outcome:
    from server.checks import evaluate_gate

    t0 = time.perf_counter()
    step = resolve_step(case)
    ws = case.get("workspace") or {}
    with tempfile.TemporaryDirectory(prefix="miyagi-check-eval-") as tmp:
        root = Path(tmp).resolve()
        try:
            build_workdir(ws.get("files") or {}, root)
            ctx = make_context(ws, str(root))
            gate = evaluate_gate(step, ctx, precision_mode=bool(case.get("precision_mode")))
        except Exception as exc:  # noqa: BLE001 - a broken case is a scored "not_yet" with the reason
            return Outcome(case, "not_yet", None, error=f"{type(exc).__name__}: {exc}",
                           ms=(time.perf_counter() - t0) * 1000)
    rows = [*gate["checks"], *gate["precision"]]
    return Outcome(case, "pass" if gate["passed"] else "not_yet", gate["via"], rows,
                   ms=(time.perf_counter() - t0) * 1000)


def run_all(cases: list[dict] | None = None) -> list[Outcome]:
    return [run_case(c) for c in (cases if cases is not None else load_cases())]


# ------------------------------------------------------------------ scoring
def score(outcomes: list[Outcome]) -> dict[str, Any]:
    n = len(outcomes)
    tp = sum(o.label == "TP" for o in outcomes)
    tn = sum(o.label == "TN" for o in outcomes)
    fp = sum(o.label == "FP" for o in outcomes)
    fn = sum(o.label == "FN" for o in outcomes)

    def ratio(a: int, b: int) -> float:
        return round(a / b, 4) if b else 1.0

    out: dict[str, Any] = {
        "cases": n, "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "accuracy": ratio(tp + tn, n),
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
        # of the steps not done, how many the checks waved through
        "false_pass_rate": round(fp / (fp + tn), 4) if fp + tn else 0.0,
    }
    p, r = out["precision"], out["recall"]
    out["f1"] = round(2 * p * r / (p + r), 4) if p + r else 0.0
    return out


def breakdown(outcomes: list[Outcome], key: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[Outcome]] = {}
    for o in outcomes:
        groups.setdefault(str(o.case.get(key, "none")), []).append(o)
    return {k: score(v) for k, v in sorted(groups.items())}


def failures(outcomes: list[Outcome]) -> list[Outcome]:
    """Wrong verdicts, worst first: false passes, then false not-yets, each by case id."""
    order = {"FP": 0, "FN": 1}
    return sorted((o for o in outcomes if not o.correct), key=lambda o: (order[o.label], o.case["id"]))


def split(outcomes: list[Outcome]) -> tuple[list[Outcome], list[Outcome]]:
    """(train, held-out) outcomes."""
    return ([o for o in outcomes if not is_held_out(o.case)], [o for o in outcomes if is_held_out(o.case)])


def _failure(o: Outcome) -> dict[str, Any]:
    return {"id": o.case["id"], "label": o.label, "expected": o.expected, "got": o.got,
            "kind": o.case["kind"], "trap": o.case.get("trap", "none"), "why": o.case["why"],
            "rows": [f"{r['checkId']} {r['status']}: {r['label']} ({r['detail']})" for r in o.rows],
            **({"error": o.error} if o.error else {})}


def summary(outcomes: list[Outcome], held_out_detail: bool = False) -> dict[str, Any]:
    """"overall", "by_kind", "by_trap" and "failures" are the TRAIN set (what a fix works against). "held_out" is
    scored apart, with only the ids and labels of its wrong verdicts (their rows with ``held_out_detail``)."""
    train, held = split(outcomes)
    return {
        "overall": score(train),
        "by_kind": breakdown(train, "kind"),
        "by_trap": breakdown(train, "trap"),
        "failures": [_failure(o) for o in failures(train)],
        "held_out": {
            **score(held),
            "by_kind": breakdown(held, "kind"),
            "failures": [_failure(o) if held_out_detail else {"id": o.case["id"], "label": o.label}
                         for o in failures(held)],
        },
        "all": score(outcomes),
    }


# ------------------------------------------------------------------ report
def _fmt_score(s: dict) -> str:
    return (f"acc {s['accuracy']:.3f}  prec {s['precision']:.3f}  rec {s['recall']:.3f}  "
            f"f1 {s['f1']:.3f}  fpr {s['false_pass_rate']:.3f}  "
            f"(n={s['cases']} TP={s['tp']} TN={s['tn']} FP={s['fp']} FN={s['fn']})")


def _fmt_failure(f: dict) -> list[str]:
    what = "FALSE PASS" if f["label"] == "FP" else "FALSE NOT-YET"
    if "why" not in f:  # a held-out verdict without its detail
        return [f"  [{what}] {f['id']}"]
    out = [f"  [{what}] {f['id']} ({f['kind']}, trap={f['trap']}): expected {f['expected']}, got {f['got']}",
           f"      why: {f['why']}"]
    if f.get("error"):
        out.append(f"      error: {f['error']}")
    return out + [f"      {r}" for r in f["rows"]]


def report(outcomes: list[Outcome], verbose: bool = False, wall_s: float | None = None,
           held_out_detail: bool = False) -> str:
    s = summary(outcomes, held_out_detail=held_out_detail)
    lines = ["Step-check eval (server.checks.evaluate_gate, offline, no model call)", ""]
    lines.append("train set (fixes are tuned on these):")
    lines.append(f"{'overall':<18}" + _fmt_score(s["overall"]))
    for k, v in s["by_kind"].items():
        lines.append(f"{'kind ' + k:<18}" + _fmt_score(v))
    for k, v in s["by_trap"].items():
        lines.append(f"{'trap ' + k:<18}" + _fmt_score(v))
    held = s["held_out"]
    if held["overall"]["cases"]:
        lines.append("")
        lines.append("held-out cases (scored on their own, never used to tune a fix):")
        lines.append(f"{'held-out':<18}" + _fmt_score(held["overall"]))
        for k, v in held["by_kind"].items():
            lines.append(f"{'kind ' + k:<18}" + _fmt_score(v))
    if wall_s is not None:
        lines.append(f"\n{len(outcomes)} cases in {wall_s:.2f}s")
    lines.append("")
    lines.append(f"{len(fails)} wrong verdict(s), worst first:" if fails else "no wrong verdicts")
    for f in fails:
        lines += _fmt_failure(f)
    h = s["held_out"]
    lines.append("")
    lines.append("held-out set (scored apart; NEVER tune a fix on these):")
    if h["cases"]:
        lines.append(f"{'held-out':<18}" + _fmt_score(h))
        for k, v in h["by_kind"].items():
            lines.append(f"{'kind ' + k:<18}" + _fmt_score(v))
        lines.append(f"{len(h['failures'])} wrong verdict(s), worst first:" if h["failures"] else "no wrong verdicts")
        for f in h["failures"]:
            lines += _fmt_failure(f)
    else:
        lines.append("  no held-out cases")
    lines.append("")
    lines.append(f"{'all cases':<18}" + _fmt_score(s["all"]))
    if verbose:
        lines.append("")
        lines.append("all cases (H = held out):")
        for o in outcomes:
            tag = "H" if is_held_out(o.case) else " "
            lines.append(f"  {tag} {o.label} {o.case['id']:<52} expected {o.expected:<8} got {o.got:<8} via {o.via}"
                         f"  {o.ms:.0f} ms")
    return "\n".join(lines)


_BASELINE_KEYS = ("cases", "accuracy", "precision", "recall", "fp", "fn")


def baseline_from(outcomes: list[Outcome]) -> dict[str, Any]:
    train, held = split(outcomes)
    s, h = score(train), score(held)
    return {
        "_comment": "Written by `python -m server.evals.checks --write-baseline`. The top-level scores and known_wrong "
                    "are the TRAIN set: test_check_evals.py fails when a score drops below these or a train case "
                    "outside known_wrong gets a wrong verdict. held_out is scored apart and guarded only in "
                    "aggregate (never tune a fix on it). Raise it when the checks get better.",
        **{k: s[k] for k in _BASELINE_KEYS},
        "known_wrong": {o.case["id"]: o.label for o in failures(train)},
        "held_out": {**{k: h[k] for k in _BASELINE_KEYS},
                     "known_wrong": {o.case["id"]: o.label for o in failures(held)}},
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="python -m server.evals.checks", description=__doc__.split("\n\n")[0])
    ap.add_argument("-k", help="only cases whose id contains this")
    ap.add_argument("-v", "--verbose", action="store_true", help="list every case")
    ap.add_argument("--json", action="store_true", help="print the summary as JSON")
    ap.add_argument("--held-out", action="store_true",
                    help="also show the held-out wrong verdicts' rows (for reviewing the set, never for a fix loop)")
    ap.add_argument("--write-baseline", action="store_true", help=f"write {BASELINE.name} from this run")
    args = ap.parse_args(argv)

    cases = load_cases()
    if args.k:
        cases = [c for c in cases if args.k in c["id"]]
    t0 = time.perf_counter()
    outcomes = run_all(cases)
    wall = time.perf_counter() - t0
    if args.json:
        print(json.dumps({**summary(outcomes, held_out_detail=args.held_out), "wall_s": round(wall, 3)}, indent=1))
    else:
        print(report(outcomes, verbose=args.verbose, wall_s=wall, held_out_detail=args.held_out))
    if args.write_baseline:
        if args.k:
            print("--write-baseline needs the full set (no -k)", file=sys.stderr)
            return 2
        BASELINE.write_text(json.dumps(baseline_from(outcomes), indent=1) + "\n", encoding="utf-8")
        print(f"\nwrote {BASELINE.relative_to(ROOT)}")
    return 0

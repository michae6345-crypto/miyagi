"""Precision report: score a generated step graph against a hand-written expected graph.

Fixtures (server/lesson/fixtures/*.json) are ordinary step graphs plus, per step, an
optional `solution` string: the code a correct learner has written by the end of that
step. Generated `file_contains` regexes are run against it, so "does the check accept
correct code?" is measured, not eyeballed. An optional `starter` (code before the step)
measures the opposite: a check that already passes on the starter code is vacuous.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter

from .schema import lint, schema_errors

START_TOLERANCE_S = 30.0


def _iou(a: dict, b: dict) -> float:
    lo, hi = max(a["start"], b["start"]), min(a["end"], b["end"])
    inter = max(0.0, hi - lo)
    union = max(a["end"], b["end"]) - min(a["start"], b["start"])
    return inter / union if union > 0 else 0.0


def align(pred: list[dict], exp: list[dict]) -> list[tuple[int, int, float]]:
    """Greedy one-to-one matching of steps by temporal IoU (ties -> closer start)."""
    pairs = []
    for i, p in enumerate(pred):
        for j, e in enumerate(exp):
            if p.get("video") and e.get("video"):
                iou = _iou(p["video"], e["video"])
                if iou > 0:
                    pairs.append((iou, -abs(p["video"]["start"] - e["video"]["start"]), i, j))
    pairs.sort(reverse=True)
    used_p, used_e, out = set(), set(), []
    for iou, _, i, j in pairs:
        if i not in used_p and j not in used_e:
            used_p.add(i)
            used_e.add(j)
            out.append((i, j, iou))
    return sorted(out, key=lambda t: t[1])


def _regex_accepts(pattern: str, code: str) -> bool | None:
    try:
        return re.search(pattern, code, re.M) is not None
    except re.error:
        return None


def report(pred: dict, exp: dict, known_metrics: set[str] | None = None, known_files: set[str] | None = None) -> dict:
    ps, es = pred.get("steps", []), exp.get("steps", [])
    matches = align(ps, es)
    n_m = len(matches)
    precision = n_m / len(ps) if ps else 0.0
    recall = n_m / len(es) if es else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    start_err = [abs(ps[i]["video"]["start"] - es[j]["video"]["start"]) for i, j, _ in matches]
    end_err = [abs(ps[i]["video"]["end"] - es[j]["video"]["end"]) for i, j, _ in matches]

    type_hits = type_total = 0
    accept = accept_total = vacuous = vacuous_total = 0
    per_step = []
    for i, j, iou in matches:
        p, e = ps[i], es[j]
        want = Counter(c["type"] for c in e.get("checks", []))
        got = Counter(c["type"] for c in p.get("checks", []))
        hit = sum(min(n, got[t]) for t, n in want.items())
        type_hits += hit
        type_total += sum(want.values())
        row = {
            "expected": e["title"],
            "got": p["title"],
            "iou": round(iou, 2),
            "d_start_s": round(p["video"]["start"] - e["video"]["start"], 1),
            "check_types": f"{hit}/{sum(want.values())}",
        }
        sol, starter = e.get("solution"), e.get("starter")
        pats = [c["pattern"] for c in p.get("checks", []) if c["type"] == "file_contains" and c.get("pattern")]
        if sol and pats:
            ok = [_regex_accepts(x, sol) for x in pats]
            accept += sum(1 for v in ok if v)
            accept_total += len(ok)
            row["regex_accepts_solution"] = f"{sum(1 for v in ok if v)}/{len(ok)}"
        if starter is not None and pats:
            bad = [_regex_accepts(x, starter) for x in pats]
            vacuous += sum(1 for v in bad if v)
            vacuous_total += len(bad)
        per_step.append(row)

    exp_libs = set((exp.get("lesson") or {}).get("libraries", {}))
    got_libs = {k.lower() for k in (pred.get("lesson") or {}).get("libraries", {})}
    lib_recall = sum(1 for k in exp_libs if k.lower() in got_libs) / len(exp_libs) if exp_libs else None

    n_checks = sum(len(s.get("checks", [])) for s in ps)
    problems = lint(pred, known_metrics, known_files)
    return {
        "steps": {"predicted": len(ps), "expected": len(es), "matched": n_m, "precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3)},
        "timing": {
            "median_start_err_s": round(statistics.median(start_err), 1) if start_err else None,
            "median_end_err_s": round(statistics.median(end_err), 1) if end_err else None,
            f"starts_within_{int(START_TOLERANCE_S)}s": f"{sum(1 for d in start_err if d <= START_TOLERANCE_S)}/{n_m}",
        },
        "checks": {
            "total": n_checks,
            "type_recall": round(type_hits / type_total, 3) if type_total else None,
            "regex_accepts_solution": round(accept / accept_total, 3) if accept_total else None,
            "regex_vacuous_on_starter": round(vacuous / vacuous_total, 3) if vacuous_total else None,
            "visual_checks": sum(1 for s in ps for c in s.get("checks", []) if c.get("type") == "visual"),
            "lint_problems": len(problems),
        },
        "libraries_recall": round(lib_recall, 3) if lib_recall is not None else None,
        "schema_valid": not schema_errors(pred),
        "per_step": per_step,
        "unmatched_expected": [es[j]["title"] for j in range(len(es)) if j not in {m[1] for m in matches}],
        "unmatched_predicted": [ps[i]["title"] for i in range(len(ps)) if i not in {m[0] for m in matches}],
        "lint": problems,
    }


def format_report(r: dict) -> str:
    s, t, c = r["steps"], r["timing"], r["checks"]
    lines = [
        f"steps     P={s['precision']:.2f} R={s['recall']:.2f} F1={s['f1']:.2f}  ({s['matched']} matched; {s['predicted']} predicted, {s['expected']} expected)",
        f"timing    median |Δstart|={t['median_start_err_s']}s  |Δend|={t['median_end_err_s']}s  " + "  ".join(f"{k}={v}" for k, v in t.items() if k.startswith("starts")),
        f"checks    {c['total']} total, type recall={c['type_recall']}, regex accepts solution={c['regex_accepts_solution']}, "
        f"vacuous on starter={c['regex_vacuous_on_starter']}, visual={c['visual_checks']}, lint problems={c['lint_problems']}",
        f"libraries recall={r['libraries_recall']}   schema valid={r['schema_valid']}",
        "",
        f"{'expected step':32} {'generated step':32} {'IoU':>4} {'Δstart':>7} types  regex",
    ]
    for row in r["per_step"]:
        lines.append(f"{row['expected'][:32]:32} {row['got'][:32]:32} {row['iou']:>4} {row['d_start_s']:>7} {row['check_types']:>5}  {row.get('regex_accepts_solution', '-')}")
    if r["unmatched_expected"]:
        lines.append("missed: " + "; ".join(r["unmatched_expected"]))
    if r["unmatched_predicted"]:
        lines.append("extra:  " + "; ".join(r["unmatched_predicted"]))
    for p in r["lint"][:15]:
        lines.append("lint: " + p)
    return "\n".join(lines)

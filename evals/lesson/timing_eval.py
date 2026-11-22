"""Offline: how far are built lessons' step starts from the gold timings, before and after server/lesson/timing.py?

Gold = the video's chapter marks (S3's eval and the PINN fixture use the same gold: "step bounds = the video's chapter
marks"). Inputs are what earlier eval runs saved, nothing is fetched and no model is called:
- graphs: evals/lesson/results*/<id>.json (run.py output: {meta, graph});
- captions + chapters: <id>.transcript.json saved next to them by run.py (gitignored: YouTube's captions are not
  committed), found in any results dir, or in --captions DIR.

For every graph whose video has chapters, three versions of its step starts are scored:
- built: as the engine wrote them;
- pinned: timing.pin_starts with chapters + caption lines (what the Claude path now does);
- captions_only: timing.pin_starts with the caption lines alone (chapters withheld from the pin, so this one is not
  scored against marks it was allowed to snap to).
"pinned" is circular: it snaps to the same chapter marks it is scored against. The held-out rows are not:
- held_out (leave one chapter out): for each chapter mark k, the built step nearest to k (within HELD_OUT_PAIR_S) is
  scored on k twice: as built ("held_out_built") and after pin_starts with every chapter mark EXCEPT k plus the
  caption lines ("held_out_pinned"). A pin that helps moves that step toward a mark it never saw; one that snaps it to
  a neighbouring mark gets worse. Each step is paired with at most one mark (the nearest).
Two error measures per step start:
- nearest: seconds to the nearest chapter mark (report.md's "step starts vs chapter marks");
- aligned: steps matched one-to-one to chapter segments by time IoU (server/lesson/precision.align), start error of
  the matched pairs (a step that starts mid-chapter on purpose is not penalised).

    python evals/lesson/timing_eval.py                       # every results*/ dir, grouped by engine
    python evals/lesson/timing_eval.py --json                # machine-readable
    python evals/lesson/timing_eval.py --captions DIR results-dec3653-claude
"""

from __future__ import annotations

import argparse
import copy
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.lesson import timing  # noqa: E402
from server.lesson.precision import align  # noqa: E402


def _captions(dirs: list[Path], extra: Path | None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for d in ([extra] if extra else []) + dirs + sorted(HERE.glob("results*")):
        if d and d.is_dir():
            for f in d.glob("*.transcript.json"):
                out.setdefault(f.name.removesuffix(".transcript.json"), json.loads(f.read_text(encoding="utf-8")))
    return out


def _gold(cap: dict) -> list[dict]:
    ch = sorted(cap.get("chapters") or [], key=lambda c: c["t"])
    end = float(cap.get("length_s") or (ch[-1]["t"] + 60 if ch else 0))
    return [{"video": {"start": float(c["t"]), "end": float(ch[i + 1]["t"]) if i + 1 < len(ch) else end}}
            for i, c in enumerate(ch)]


def _errors(starts: list[dict], gold: list[dict]) -> tuple[list[float], list[float]]:
    marks = [g["video"]["start"] for g in gold]
    nearest = [min(abs(s["start"] - m) for m in marks) for s in starts]
    pairs = align([{"video": s} for s in starts], gold)
    aligned = [abs(starts[i]["start"] - gold[j]["video"]["start"]) for i, j, _ in pairs]
    return nearest, aligned


HELD_OUT_PAIR_S = 60.0


def _held_out(built: list[dict], cap: dict) -> tuple[list[float], list[float]]:
    """Leave-one-chapter-out errors: (as built, pinned without that mark) for every (mark, nearest step) pair."""
    chapters = sorted(cap.get("chapters") or [], key=lambda c: c["t"])
    pairs: dict[int, tuple[float, int]] = {}  # step index -> (distance, chapter index): one mark per step
    for k, c in enumerate(chapters):
        if not built:
            break
        j = min(range(len(built)), key=lambda i: abs(built[i]["start"] - float(c["t"])))
        d = abs(built[j]["start"] - float(c["t"]))
        if d <= HELD_OUT_PAIR_S and (j not in pairs or d < pairs[j][0]):
            pairs[j] = (d, k)
    before, after = [], []
    for j, (d, k) in sorted(pairs.items()):
        steps = copy.deepcopy(built)
        timing.pin_starts(steps, cap.get("transcript"), chapters[:k] + chapters[k + 1:])
        before.append(d)
        after.append(abs(steps[j]["start"] - float(chapters[k]["t"])))
    return before, after


def _summary(nearest: list[float], aligned: list[float]) -> dict:
    if not nearest:
        return {"n": 0}
    return {"n": len(nearest), "median": round(statistics.median(nearest), 2), "mean": round(statistics.mean(nearest), 1),
            "within_10s": round(sum(e <= 10 for e in nearest) / len(nearest), 2),
            "aligned_median": round(statistics.median(aligned), 2) if aligned else None,
            "aligned_within_10s": round(sum(e <= 10 for e in aligned) / len(aligned), 2) if aligned else None}


def evaluate(dirs: list[Path] | None = None, captions: Path | None = None) -> dict:
    """{engine path: {built|pinned|captions_only: summary, lessons: n}, plus per-video rows under "_videos"}."""
    dirs = [Path(d) for d in dirs] if dirs else sorted(HERE.glob("results*"))
    caps = _captions(dirs, captions)
    acc: dict[str, dict[str, list]] = {}
    per_video: dict[tuple, dict[str, list]] = {}
    lessons: dict[str, int] = {}
    for d in dirs:
        for f in sorted(d.glob("*.json")):
            if f.name.endswith(".transcript.json") or f.name == "grades.json":
                continue
            data = json.loads(f.read_text(encoding="utf-8"))
            g = data.get("graph") or {}
            vid = (data.get("meta") or {}).get("id") or f.stem
            cap = caps.get(vid)
            if not g.get("steps") or not cap or not cap.get("chapters"):
                continue
            path = (data.get("meta") or {}).get("path") or (g.get("lesson") or {}).get("builtBy") or "unknown"
            gold = _gold(cap)
            built = [{"start": float(s["video"]["start"]), "end": float(s["video"]["end"])} for s in g["steps"] if s.get("video")]
            versions = {"built": built}
            if path == "claude":  # the pin runs on the Claude (transcript) path only
                versions["pinned"] = copy.deepcopy(built)
                timing.pin_starts(versions["pinned"], cap.get("transcript"), cap.get("chapters"))
                versions["captions_only"] = copy.deepcopy(built)
                timing.pin_starts(versions["captions_only"], cap.get("transcript"), [])
            lessons[path] = lessons.get(path, 0) + 1
            scored = {name: _errors(starts, gold) for name, starts in versions.items()}
            if path == "claude":  # leave one chapter out: the non-circular measure
                hb, hp = _held_out(built, cap)
                scored["held_out_built"], scored["held_out_pinned"] = (hb, []), (hp, [])
            for name, (n, a) in scored.items():
                slot = acc.setdefault(path, {}).setdefault(name, [[], []])
                slot[0].extend(n)
                slot[1].extend(a)
                pv = per_video.setdefault((path, vid), {}).setdefault(name, [[], []])
                pv[0].extend(n)
                pv[1].extend(a)
    out: dict = {p: {k: _summary(*v) for k, v in by.items()} | {"lessons": lessons[p]} for p, by in acc.items()}
    out["_videos"] = {f"{p}/{v}": {k: _summary(*x) for k, x in by.items()} for (p, v), by in sorted(per_video.items())}
    return out


def _table(res: dict) -> str:
    rows = ["| Engine | Version | Steps | Median (nearest mark) | Within 10 s | Mean | Median (IoU-aligned) | Within 10 s (aligned) |",
            "|---|---|---|---|---|---|---|---|"]
    for p, by in res.items():
        if p.startswith("_"):
            continue
        for name in ("built", "pinned", "captions_only", "held_out_built", "held_out_pinned"):
            s = by.get(name)
            if s and s.get("n"):
                al = (f"{s['aligned_median']} s | {s['aligned_within_10s']:.0%}" if s.get("aligned_median") is not None
                      else "- | -")
                rows.append(f"| {p} ({by['lessons']} lessons) | {name} | {s['n']} | {s['median']} s | {s['within_10s']:.0%} | "
                            f"{s['mean']} s | {al} |")
    return "\n".join(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("dirs", nargs="*", help="results dirs (default: every evals/lesson/results*/)")
    ap.add_argument("--captions", help="extra dir of <id>.transcript.json files")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    dirs = [Path(d) if Path(d).is_absolute() or Path(d).exists() else HERE / d for d in a.dirs] or None
    res = evaluate(dirs, Path(a.captions) if a.captions else None)
    if a.json:
        print(json.dumps(res, indent=1))
    else:
        print(_table(res))
        if not any(not k.startswith("_") for k in res):
            print("\nno graph with saved captions + chapters found (run.py saves <id>.transcript.json; they are gitignored)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

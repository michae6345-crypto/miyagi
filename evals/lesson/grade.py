"""Automatic grading of built lessons (evals/lesson/results/<id>.json). Used by run.py.

Signals per lesson:
- contract: schema_errors() from server.lesson.schema, plus its lint();
- steps: count, video ranges ordered / non-overlapping / inside the real video length, coverage;
- checks: regex compiles, app is one the screen module knows and fits the stack, generic patterns,
  Python-only error patterns in non-Python stacks, Terminal/metric patterns tested against REAL tool
  output for the stack (TOOL_OUTPUT below: exact lines printed by git, cargo, uvicorn, vite, pytest...);
- grounding: identifiers in Code checks / step titles found in the transcript within the step's range;
- leakage: PINN/physics/diffusion/torch/demo-path words anywhere in the lesson text;
- time-to-lesson: wall seconds from run.py.
The auto score is a rough 0-10 composite; report.md adds a manual read on top.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Real output lines (verbatim formats of the tools; values are arbitrary). A Terminal/browser screen check
# or metric_pattern that matches none of its stack's lines is "unverified", not necessarily wrong.
TOOL_OUTPUT = {
    "react-useeffect": [
        "  VITE v5.0.10  ready in 312 ms",
        "  ➜  Local:   http://localhost:5173/",
        "  ➜  Network: use --host to expose",
        "> react-app@0.0.0 dev",
        "> vite",
        "added 270 packages, and audited 271 packages in 18s",
        "Compiled successfully!",
        "webpack compiled successfully",
        "Uncaught TypeError: Cannot read properties of undefined (reading 'map')",
        "Warning: Each child in a list should have a unique \"key\" prop.",
        "Count: 3",
        "Width: 1280px",
        "Height: 720px",
    ],
    "git-rebase": [
        "Switched to a new branch 'feature'",
        "Switched to branch 'main'",
        "[main 1a2b3c4] Add login form",
        "[feature 9f8e7d6] Update README",
        " 1 file changed, 2 insertions(+), 1 deletion(-)",
        "Auto-merging README.md",
        "CONFLICT (content): Merge conflict in README.md",
        "error: could not apply 1a2b3c4... Add login form",
        "hint: Resolve all conflicts manually, mark them as resolved with",
        "interactive rebase in progress; onto 5e6f7a8",
        "You are currently rebasing branch 'feature' on '5e6f7a8'.",
        "Successfully rebased and updated refs/heads/feature.",
        "* 9f8e7d6 (HEAD -> feature) Update README",
        "* 5e6f7a8 (main) Add footer",
        "<<<<<<< HEAD",
        "=======",
        ">>>>>>> 1a2b3c4 (Add login form)",
        "On branch feature",
        "nothing to commit, working tree clean",
        "Fast-forward",
    ],
    "pandas-30min": [
        "[891 rows x 12 columns]",
        "RangeIndex: 891 entries, 0 to 890",
        "Data columns (total 12 columns):",
        "dtypes: float64(2), int64(5), object(5)",
        "memory usage: 83.7+ KB",
        "Name: Age, dtype: float64",
        "Length: 891, dtype: int64",
        "Successfully installed numpy-2.1.0 pandas-2.2.2",
        "(891, 12)",
        "count    714.000000",
        "mean      29.699118",
        "KeyError: 'Agee'",
        "Traceback (most recent call last):",
    ],
    "rust-cli": [
        "     Created binary (application) `mycli` package",
        "   Compiling mycli v0.1.0 (/Users/me/mycli)",
        "    Finished `dev` profile [unoptimized + debuginfo] target(s) in 1.23s",
        "    Finished dev [unoptimized + debuginfo] target(s) in 0.52s",
        "     Running `target/debug/mycli add hello`",
        "error[E0425]: cannot find value `args` in this scope",
        "error: could not compile `mycli` (bin \"mycli\") due to 1 previous error",
        "warning: unused variable: `x`",
        "thread 'main' panicked at src/main.rs:5:10:",
        "Usage: mycli [OPTIONS] <COMMAND>",
        "test result: ok. 3 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s",
        "    Updating crates.io index",
        "      Adding clap v4.5.4 to dependencies",
        "Hello, world!",
    ],
    "fastapi-rest": [
        "INFO:     Will watch for changes in these directories: ['/Users/me/api']",
        "INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)",
        "INFO:     Started reloader process [12345] using StatReload",
        "INFO:     Application startup complete.",
        "INFO:     127.0.0.1:52345 - \"GET /items/1 HTTP/1.1\" 200 OK",
        "INFO:     127.0.0.1:52345 - \"POST /items HTTP/1.1\" 200 OK",
        "INFO:     127.0.0.1:52345 - \"GET /items/9 HTTP/1.1\" 404 Not Found",
        "INFO:     127.0.0.1:52345 - \"POST /items HTTP/1.1\" 422 Unprocessable Entity",
        "{\"detail\":\"Item 9 not found\"}",
        "{\"text\":\"apple\",\"is_done\":false}",
        "Successfully installed fastapi-0.103.1 uvicorn-0.23.2",
        "FastAPI - Swagger UI",
        "Request URL",
        "Response body",
        "===== 3 passed in 0.12s =====",
        "Traceback (most recent call last):",
    ],
}

PYTHON_STACKS = {"pandas-30min", "fastapi-rest"}
# Which screen apps make sense per stack (screen module app names). Anything else is flagged.
STACK_APPS = {
    "react-useeffect": {"Code", "Cursor", "Terminal", "iTerm2", "Google Chrome", "Safari"},
    "git-rebase": {"Terminal", "iTerm2", "Code", "Cursor"},
    "pandas-30min": {"Code", "Cursor", "Jupyter", "Terminal", "iTerm2", "Google Chrome", "Safari", "PyCharm"},
    "rust-cli": {"Code", "Cursor", "Terminal", "iTerm2"},
    "fastapi-rest": {"Code", "Cursor", "Terminal", "iTerm2", "Google Chrome", "Safari", "PyCharm"},
}
LEAK = re.compile(r"pinn|physics|convection|diffusion|\bpde\b|demo/pinn|pinn-lab|lossPDE|collocation|requires_grad|create_graph|"
                  r"autograd|\btorch\b|pytorch|loss\b|epoch|::metric::|log_metric|training", re.I)
GENERIC = re.compile(r"^\(?\??(?:traceback|error|err!?|exception|warning)(?:[|)](?:traceback|error|err!?|exception|warning|:|\\w\+|\s)*)*\)?:?$", re.I)
STOP = set("this that with from have will your into then them they when what which there their about would could should "
           "make sure just like going here code file step learner video tutorial using first next same also".split())


def _rx(p: str):
    try:
        return re.compile(p)
    except re.error:
        return None


def _words(s: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", s or "")} - STOP


def _tokens_from_regex(p: str) -> set[str]:
    p = re.sub(r"\\[sSwWdDb]|\(\?P<\w+>|[\\^$.*+?()\[\]{}|]", " ", p or "")
    return _words(p)


def grade_lesson(rec: dict, vid: dict, transcript: dict | None) -> dict:
    from server.lesson.schema import SCREEN_APPS, lint, schema_errors

    meta, graph = rec.get("meta") or {}, rec.get("graph")
    g = {"id": vid["id"], "path": meta.get("path"), "model": meta.get("model"), "wall_s": meta.get("wall_s"),
         "error": (rec.get("error") or "")[:600] or None, "flags": []}
    if not graph:
        g["auto_score"] = 0.0
        return g
    length = (transcript or {}).get("length_s") or meta.get("length_s") or vid.get("length_s")
    lines = (transcript or {}).get("transcript") or []
    steps = graph.get("steps") or []
    g["schema_errors"] = schema_errors(graph)
    g["lint"] = lint(graph)
    g["steps"] = len(steps)
    g["titles"] = [s.get("title") for s in steps]
    g["build_warnings"] = (graph.get("build") or {}).get("warnings") or []

    # --- video ranges
    ranges = [((s.get("video") or {}).get("start"), (s.get("video") or {}).get("end")) for s in steps]
    ordered = all(a is not None and b is not None and a < b for a, b in ranges) and all(
        ranges[i][1] <= ranges[i + 1][0] + 0.01 for i in range(len(ranges) - 1))
    inside = all(b <= length + 2 for _, b in ranges) if length else None
    covered = sum(b - a for a, b in ranges) / length if length else None
    g.update(ranges=ranges, ranges_ordered=ordered, ranges_inside_video=inside, coverage=round(covered, 2) if covered else None, length_s=length)
    if not ordered:
        g["flags"].append("video ranges overlap or are out of order")
    if inside is False:
        g["flags"].append(f"a step ends after the video ({max(b for _, b in ranges):.0f}s > {length}s)")
    if covered is not None and covered < 0.4:
        g["flags"].append(f"steps cover only {covered:.0%} of the video")

    # --- checks
    samples = TOOL_OUTPUT.get(vid["id"], [])
    allowed_apps = STACK_APPS.get(vid["id"], set(SCREEN_APPS))
    checks = []
    for s in steps:
        t0, t1 = (s.get("video") or {}).get("start", 0), (s.get("video") or {}).get("end", 0)
        window = " ".join(l["text"] for l in lines if t0 - 30 <= l["t"] <= t1 + 30)
        for c in s.get("checks") or []:
            row = {"step": s["id"], "id": c.get("id"), "type": c["type"], "app": c.get("app"), "pattern": c.get("pattern"),
                   "metric_pattern": c.get("metric_pattern"), "issues": []}
            pat = c.get("pattern") or c.get("metric_pattern") or ""
            rx = _rx(pat)
            if rx is None:
                row["issues"].append("regex does not compile")
            elif rx.search(""):
                row["issues"].append("matches the empty string (always passes)")
            if c["type"].startswith("screen_"):
                if c.get("app") not in SCREEN_APPS:
                    row["issues"].append(f"app {c.get('app')!r} unknown to the screen module")
                elif c.get("app") not in allowed_apps:
                    row["issues"].append(f"app {c.get('app')!r} unlikely for this stack")
                if GENERIC.match(c.get("pattern") or ""):
                    row["generic"] = True
                if c["type"] == "screen_absent" and vid["id"] not in PYTHON_STACKS and re.search(r"traceback", c.get("pattern") or "", re.I):
                    row["issues"].append("Python 'Traceback' pattern in a non-Python stack")
                if c["type"] == "screen_contains" and rx is not None and len(re.sub(r"\\.|[^A-Za-z0-9]", "", pat)) < 4:
                    row["issues"].append("too short to be distinctive")
                if c.get("app") in ("Terminal", "iTerm2", "Google Chrome", "Safari") and rx is not None and samples:
                    row["matches_real_output"] = any(rx.search(x) for x in samples)
                if c.get("app") in ("Code", "Cursor", "Jupyter", "PyCharm") and c["type"] == "screen_contains":
                    toks = _tokens_from_regex(pat)
                    row["grounded_in_transcript"] = bool(toks & _words(window)) if toks else None
            else:  # metric_*
                mp = c.get("metric_pattern") or ""
                mrx = _rx(mp)
                if not mp:
                    row["issues"].append("metric check without metric_pattern (cannot read it off the screen)")
                elif mrx is not None and samples:
                    hit = [x for x in samples if (m := mrx.search(x)) and "value" in mrx.groupindex]
                    row["matches_real_output"] = bool(hit)
            checks.append(row)
    g["checks"] = checks
    screen = [c for c in checks if c["type"].startswith("screen_contains")]
    g["n_checks"] = len(checks)
    g["n_metric"] = sum(c["type"].startswith("metric_") for c in checks)
    g["n_generic"] = sum(bool(c.get("generic")) for c in checks)
    g["n_issues"] = sum(bool(c["issues"]) for c in checks)
    out_checks = [c for c in checks if "matches_real_output" in c]
    g["real_output_verified"] = f"{sum(c['matches_real_output'] for c in out_checks)}/{len(out_checks)}"
    code_checks = [c for c in checks if c.get("grounded_in_transcript") is not None]
    g["code_checks_grounded"] = f"{sum(c['grounded_in_transcript'] for c in code_checks)}/{len(code_checks)}"
    only_generic = [s["id"] for s in steps if s.get("checks") and all(
        GENERIC.match(c.get("pattern") or "") for c in s["checks"] if c["type"].startswith("screen_")) and not any(
        c["type"].startswith("metric_") for c in s["checks"])]
    if only_generic:
        g["flags"].append(f"steps gradable only by a generic error-absence check: {only_generic}")
    g["steps_without_specific_check"] = only_generic

    # --- step titles grounded in the transcript window
    tg = []
    for s in steps:
        t0, t1 = (s.get("video") or {}).get("start", 0), (s.get("video") or {}).get("end", 0)
        window = _words(" ".join(l["text"] for l in lines if t0 - 15 <= l["t"] <= t1 + 15))
        tg.append(bool(_words(s.get("title", "") + " " + s.get("instructions", "")) & window) if lines else None)
    g["steps_grounded"] = f"{sum(bool(x) for x in tg)}/{len(tg)}" if lines else "no transcript"

    # --- explanations / hints inside their step
    bad_expl = [s["id"] for s in steps for e in s.get("explanations") or [] if not (
        (s.get("video") or {}).get("start", 0) - 1 <= e.get("t", -1) <= (s.get("video") or {}).get("end", 0) + 1)]
    if bad_expl:
        g["flags"].append(f"explanation timestamps outside their step: {sorted(set(bad_expl))}")

    # --- leakage
    text = json.dumps({k: v for k, v in graph.items() if k not in ("sources", "build")})
    leaks = sorted({m.group(0).lower() for m in LEAK.finditer(text)})
    g["leakage"] = leaks
    if leaks:
        g["flags"].append(f"PINN/ML vocabulary in a non-ML lesson: {leaks}")

    # --- composite (rough; the manual score in report.md is the real verdict)
    score = 0.0
    if not g["schema_errors"]:
        score += 1.5
    score += 1.0 if 4 <= len(steps) <= 10 else 0.4
    score += 1.0 if ordered and inside is not False else 0.0
    score += 0.5 if covered and covered >= 0.5 else 0.0
    if checks:
        specific = 1 - (g["n_generic"] + g["n_issues"]) / len(checks)
        score += 2.5 * max(0.0, specific)
        score -= 1.0 * len(only_generic) / max(1, len(steps))
    if out_checks:
        score += 1.5 * sum(c["matches_real_output"] for c in out_checks) / len(out_checks)
    if code_checks:
        score += 1.0 * sum(c["grounded_in_transcript"] for c in code_checks) / len(code_checks)
    if not leaks:
        score += 1.0
    g["auto_score"] = round(max(0.0, min(10.0, score)), 1)
    return g


def grade_all(out: Path, videos: list[dict]) -> list[dict]:
    res = []
    for v in videos:
        p = out / f"{v['id']}.json"
        if not p.is_file():
            res.append({"id": v["id"], "auto_score": 0.0, "error": "not built"})
            continue
        tp = out / f"{v['id']}.transcript.json"
        res.append(grade_lesson(json.loads(p.read_text()), v, json.loads(tp.read_text()) if tp.is_file() else None))
    # canned content: the same hint / mistake text appearing in more than one lesson
    seen: dict[str, set[str]] = {}
    for v in videos:
        p = out / f"{v['id']}.json"
        g = json.loads(p.read_text()).get("graph") if p.is_file() else None
        for s in (g or {}).get("steps", []):
            for h in (s.get("hints") or []) + (s.get("common_mistakes") or []):
                seen.setdefault(h.strip().lower(), set()).add(v["id"])
    canned = {h: sorted(ids) for h, ids in seen.items() if len(ids) > 1}
    for r in res:
        r["canned_across_lessons"] = [h for h, ids in canned.items() if r["id"] in ids]
    return res

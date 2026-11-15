"""teach.json -> the PASS/FAIL table + every failing text, grouped (no API calls).

usage: python -m evals.coach.teach.summarize [results/teach.json] > results/teach.md
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RULES = ["words", "file", "app", "cursor", "label", "one"]
RUN_STEPS = {("A", "s2"), ("B", "s2"), ("C", "s2")}


def behaviour(r: dict) -> tuple[bool, str]:
    """Did the step pass / stay open the way it should for this state?"""
    st, passed = r["state"], r.get("passed")
    run_step = (r["lesson"], r["step"]) in RUN_STEPS
    titles = [c["title"] for c in r.get("copy", []) if c["src"] in ("card", "offtrack")]
    if st == "right":
        return (bool(passed), "passed" if passed else "did NOT pass with the right code")
    if st == "terminal_closed":
        if run_step:
            return (not passed, "passed without running the program" if passed else "stayed open (not run yet)")
        return (True, "passed (code saved; no terminal needed)" if passed else "stayed open")
    if passed:
        return (False, {"empty": "passed on an empty file", "unsaved": "passed before the file was saved",
                        "wrong_folder": "passed on code in another folder", "typo": "passed with the typo"}[st])
    if not titles:
        return (False, "stayed open, but no card ever told the learner what to do")
    return (True, "stayed open")


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "results" / "teach.json"
    runs = json.loads(path.read_text())
    rows, fails = [], defaultdict(lambda: {"rules": set(), "where": []})
    grid: dict = defaultdict(dict)
    for r in runs:
        if r.get("crash"):
            rows.append((r["lesson"], r["step"], r["state"], "CRASH", r["crash"], ""))
            continue
        ok_b, why = behaviour(r)
        bad_copy = []
        for c in r["copy"]:
            broken = [k for k in RULES if c["grades"].get(k) is False]
            if broken:
                key = (c["src"], c["title"], c["body"])
                fails[key]["rules"] |= set(broken)
                fails[key]["where"].append(f"{r['lesson']}-{r['step']}-{r['state']}")
                if c["src"] in ("card", "offtrack"):  # the verdict is about cards; action lines / captions listed below
                    bad_copy.append(f"{c['src']}:{'/'.join(broken)}")
        verdict = "PASS" if ok_b and not bad_copy else "FAIL"
        grid[(r["state"], r["step"])][r["lesson"]] = verdict
        shown = "; ".join(dict.fromkeys(c["title"] or c["body"][:40] for c in r["copy"] if c["src"] in ("card", "offtrack")))
        rows.append((r["lesson"], r["step"], r["state"], verdict, why, shown or "(no card)"))

    print("| state | step 1 (A / B / C) | step 2 (A / B / C) | step 3 (A / B / C) |")
    print("|---|---|---|---|")
    for st in ["empty", "unsaved", "wrong_folder", "typo", "terminal_closed", "right"]:
        cells = []
        for sid in ("s1", "s2", "s3"):
            g = grid.get((st, sid), {})
            cells.append(" / ".join(g.get(lid, "—") for lid in ("A", "B", "C")))
        print(f"| {st} | " + " | ".join(cells) + " |")
    print()
    print("| lesson | step | state | result | behaviour | cards shown |")
    print("|---|---|---|---|---|---|")
    for row in rows:
        print("| " + " | ".join(str(x).replace("|", "\\|") for x in row) + " |")
    for heading, srcs in (("Failing card texts (unique)", ("card", "offtrack")),
                          ("Step action lines and spotlight captions that break a rule", ("step.started", "spotlight"))):
        print(f"\n### {heading}\n")
        print("| source | title | body | rules broken | seen in |")
        print("|---|---|---|---|---|")
        for (src, title, body), v in sorted(fails.items(), key=lambda kv: -len(kv[1]["where"])):
            if src not in srcs:
                continue
            where = v["where"]
            w = ", ".join(where[:6]) + (f" (+{len(where) - 6})" if len(where) > 6 else "")
            print(f"| {src} | {title.replace('|', '/')} | {body.replace('|', '/')} | {', '.join(sorted(v['rules']))} | {w} |")


if __name__ == "__main__":
    main()

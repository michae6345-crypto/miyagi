"""Print the measured columns of the report table from results/*.json (no API calls).

Diagnosis correctness is graded by hand in report.md (`diagnosis_auto` is only the regex pre-check from
cases.py); everything else here is measured.
usage: .venv/bin/python -m evals.coach.summary
"""

from __future__ import annotations

import json

from . import cases as C
from .run_coach import RESULTS


def yn(v) -> str:
    return "—" if v is None else ("yes" if v else "NO")


def main() -> None:
    print("| case | fires (orch) | fires (screen only) | route | auto-diag | target 1st/any | spotlight | patch lines (via) | check after | gate after | targets s | card s |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for case in C.CASES:
        p = RESULTS / f"{case.id}.json"
        if not p.exists():
            continue
        r = json.loads(p.read_text())
        t = r.get("targets") or {}
        pa = r.get("patch") or {}
        ca = r.get("check_after") or {}
        tri = ((r.get("meta") or {}).get("triage") or {})
        via = (pa.get("_meta") or {}).get("via") or ("error" if pa.get("error") else "—")
        print(f"| {case.id} | {yn(r.get('fires'))} | {yn(r.get('fires_screen_only'))} | {tri.get('route')} ({tri.get('by')}) | "
              f"{yn(r.get('diagnosis_auto'))} | {yn(t.get('first'))}/{yn(t.get('any'))} | {yn((r.get('spotlight') or {}).get('on_line'))} | "
              f"{pa.get('changed_lines', '—')} ({via}) | {yn(ca.get('ok'))} | {yn((r.get('gate_after') or {}).get('passed'))} | "
              f"{r.get('targets_s') or '—'} | {r.get('card_s')} |")


if __name__ == "__main__":
    main()

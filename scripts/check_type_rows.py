"""Offline: the line the curated NN lesson's type box goes on, per step (no engine, no screen, no model call).

Starts from demo/nn-start.py, pastes each type step's code under its section comment the way the learner does, and
prints the line LessonSession._insert_plan picks before each step: it must be the comment's line + 1 (or, when the
learner already typed part of that step under the comment, the line after their last typed line), never the comment.

    python scripts/check_type_rows.py        -> exit 1 if a row is wrong
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server.orchestrator.modules import Modules
from server.orchestrator.session import LessonSession

graph = json.loads((ROOT / "demo/cache/lessons/text-nn-from-scratch.json").read_text())
starter = (ROOT / "demo/nn-start.py").read_text()


async def _emit(*_a, **_k):
    return None


s = LessonSession(_emit, Modules(demo=False, force_stubs="all"), screen=None)
graph["lesson"]["mode"] = "lesson"
s.graph, s.has_python = graph, True
s._unsaved_texts = lambda paths: [None for _ in paths]  # the file on disk (no VS Code buffer offline)
bad = 0
with tempfile.TemporaryDirectory() as d:
    s.workdir = d
    nn = Path(d) / "nn.py"
    text = starter
    for st in graph["steps"]:
        if st.get("run_command"):
            continue
        anchor = st["targets"][0]["match"]
        code = st["code"].rstrip("\n").splitlines()
        cases = (("fresh", []), ("first 3 lines typed", code[:3]),
                 ("3 lines typed, line 1 with a typo", [code[0].replace("(", "", 1).replace(" =", "=", 1)[:-2]]
                  + code[1:3]))
        for label, typed in cases:
            lines = text.splitlines()
            c = lines.index(anchor) + 1  # the comment's line (1-based)
            cur = lines[:c] + typed + (lines[c + 1:] if typed else lines[c:])  # typed onto the blank line under it
            nn.write_text("\n".join(cur) + "\n")
            plan = s._insert_plan(st)
            prog = s._code_progress(st) if plan is None else None
            row = plan["ins"] if plan else (prog or {}).get("line")
            src = "insert plan" if plan else f"progress ({(prog or {}).get('kind')})"
            last = max([c] + [i + 1 for i, ln in enumerate(cur[:c + len(typed)]) if i >= c and ln.strip()])
            want = c + 1 if not typed else last + 1
            ok = row == want and row != c
            bad += not ok
            print(f"{'ok ' if ok else 'BAD'} {st['id']} {anchor!r:16} {label:34} comment line {c:>2} -> box line "
                  f"{row} (want {want}, {src}){'  new line' if plan and plan.get('new_line') else ''}")
        lines = text.splitlines()
        c = lines.index(anchor) + 1
        text = "\n".join(lines[:c] + code + lines[c:]) + "\n"  # pasted under the comment, as the step says
print("all rows right" if not bad else f"{bad} wrong")
sys.exit(1 if bad else 0)

"""Offline: cmd_typos's verdict for every case in its table (no engine, no model call).

    python scripts/check_cmd_typos.py        -> one line per case; exit 1 if a verdict's kind isn't the expected one
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.orchestrator.cmd_typos import CASES, diagnose

bad = 0
for typed, expected, kw, want in CASES:
    v = diagnose(typed, expected, **kw)
    got = v["kind"] if v else None
    ok = got == want
    bad += not ok
    shown = f"{v['caption']!r}  fix={v['fix']!r}" if v else "no card (the coach decides)"
    print(f"{'ok ' if ok else 'BAD'} {typed or '<nn.py line>'!r:28} want {expected!r:26} -> {got!s:12} {shown}")
print(f"{len(CASES) - bad}/{len(CASES)} as expected")
sys.exit(1 if bad else 0)

"""Where would the ORCHESTRATOR put the spotlight for each card? (no API calls)

session._coach: spot = _locate(re.escape(first line of diff.yours)) on the live screen; only if that
misses does it use the coach's own `targets[0]` (set-of-mark box). This re-OCRs the saved case screen
and runs the same `locate_match` the ScreenBridge uses, then checks the rect sits on the right line.

usage: .venv/bin/python -m evals.coach.spotlight   (after run_coach; updates results/<id>.json "spotlight")
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from server.screen.match import locate_match

from . import cases as C
from .run_coach import RESULTS, SHOTS, _on_line, expected_rects, target_hits
from .screens import ocr


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="spot-"))
    for case in C.CASES:
        rp = RESULTS / f"{case.id}.json"
        if not rp.exists():
            continue
        res = json.loads(rp.read_text())
        card = res.get("card") or {}
        built = C.build(case, work / case.id)  # same drawing -> the expected line rects
        rects = expected_rects(built, case.target_rx)
        obs = ocr(SHOTS / case.id / "screen.png")
        first = ((card.get("diff") or {}).get("yours") or "").strip().splitlines()[:1]
        spot, via = None, None
        if first:
            m = locate_match(obs, re.escape(first[0]), None)
            if m is not None:
                spot, via = m.rect.to_dict(), "diff.yours"
        if spot is None and card.get("targets"):
            spot, via = card["targets"][0]["rect"], "coach target[0]"
        if spot is None:
            via = "step target (fallback)"
        res["targets"] = target_hits(card, rects)  # re-scored with the case's current target lines
        res["spotlight"] = {"via": via, "rect": spot, "on_line": bool(spot and any(_on_line(spot, e) for e in rects))}
        rp.write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str))
        print(case.id, res["spotlight"])


if __name__ == "__main__":
    main()

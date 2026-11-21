#!/usr/bin/env python3
"""Offline check of E5's hint ladder (server.coach.hint) on cached lessons. Zero API calls by construction:
every key is blanked and HTTP(S) goes to a dead proxy, so a network call would fail instead of costing money.

  .venv/bin/python scripts/stage_hints.py

Checks per step (levels 0-3): level 0 is a question, level 1 is "Rewatch m:ss, where …" with a videoJump,
level 2 is present (not skipped), titles are step-specific (differ between steps), and no two levels repeat.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "ELEVENLABS_API_KEY"):
    os.environ[k] = ""  # load_dotenv never overrides an existing (even empty) variable
os.environ["HTTPS_PROXY"] = os.environ["HTTP_PROXY"] = "http://127.0.0.1:9"
os.environ["ALL_PROXY"] = "http://127.0.0.1:9"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server import coach  # noqa: E402

LESSONS = {
    "PINN hero": "AXXnSzmpyoI",
    "React useEffect": "V8FvyuObouc",
    "notebook (linear regression)": "Jj7WD71qQWE",
    "PINN convection": "unBU1PwCnvQ",
}


def find_graph(video_id: str) -> dict | None:
    best = None
    for p in (ROOT / "demo" / "cache" / "lessons").glob("*.json"):
        try:
            g = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        if (g.get("sources") or [{}])[0].get("videoId") == video_id:
            if best is None or p.stat().st_mtime > best[0]:
                best = (p.stat().st_mtime, g)
    return best[1] if best else None


def main() -> None:
    rows, fails = [], 0
    for name, vid in LESSONS.items():
        g = find_graph(vid)
        if not g:
            print(f"== {name}: no cached lesson for {vid}")
            continue
        coach.set_lesson(g)
        print(f"\n== {name}: {g['lesson'].get('title')!r}")
        titles_by_step = []
        for step in g["steps"][:2]:
            print(f"  {step['id']} {step['title']!r}")
            cards = [coach.public(coach.hint(step, lvl)) if hasattr(coach, "public") else coach.hint(step, lvl)
                     for lvl in range(4)]
            probs = []
            for lvl, c in enumerate(cards):
                vj = c.get("videoJump")
                print(f"    L{lvl} [{c.get('levelName')}] {c.get('title')!r}\n        {c.get('body')!r}"
                      + (f"  videoJump {vj}" if vj else ""))
            names = [c.get("levelName") for c in cards]
            if "?" not in (cards[0].get("body") or ""):
                probs.append("level 0 is not a question")
            if not (cards[1].get("body") or "").startswith("Rewatch") or not cards[1].get("videoJump"):
                probs.append("level 1 isn't 'Rewatch m:ss, …' with a videoJump")
            if len({c.get("level") for c in cards[:3]}) < 3 or 2 not in [c.get("level") for c in cards[:3]]:
                probs.append(f"levels for 3 presses = {[c.get('level') for c in cards[:3]]} (level 2 skipped)")
            bodies = [c.get("body") for c in cards]
            if len(set(bodies)) < len(bodies):
                probs.append("two levels have the same body")
            titles_by_step.append([c.get("title") for c in cards])
            for p in probs:
                print(f"    FAIL {p}")
            fails += len(probs)
            rows.append({"lesson": name, "step": step["id"], "levels": names, "titles": [c.get("title") for c in cards],
                         "problems": probs})
        if len(titles_by_step) == 2 and titles_by_step[0] == titles_by_step[1]:
            print("    FAIL titles are the same on step 1 and step 2")
            fails += 1
    print(f"\n{'PASS' if not fails else f'{fails} FAIL'}: hint ladder on {len(rows)} lesson-steps (offline, 0 API calls)")
    (ROOT / "demo" / "runs").mkdir(parents=True, exist_ok=True)
    with (ROOT / "demo" / "runs" / "stage-hints.jsonl").open("a") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()

"""Live: what React / pandas / Blender lessons need, checked on this Mac (read-only; installs nothing).

    .venv/bin/python -m server.workspace.tests.live_setup [react pandas blender] [--fresh]
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

import server.orchestrator.config  # noqa: F401  (loads the shared .env)
from server.workspace import editor_needed, missing, requirements, setup_card
from server.workspace.paths import REPO_ROOT, lessons_root

LESSONS = {
    "react": REPO_ROOT / "demo/cache/lessons/516197461c0dacf3.json",
    "pandas": Path(__file__).parent / "fixtures/pandas_pokemon.json",
    "blender": Path(__file__).parent / "fixtures/blender_donut.json",
    "support": Path(__file__).parent / "fixtures/nocode_support_agents.json",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("which", nargs="*", default=list(LESSONS))
    ap.add_argument("--fresh", action="store_true", help="ask Claude again (drop the cached tool lists)")
    a = ap.parse_args()
    if a.fresh:
        shutil.rmtree(lessons_root() / ".miyagi-state" / "requirements", ignore_errors=True)
    for name in a.which:
        graph = json.loads(LESSONS[name].read_text(encoding="utf-8"))
        t0 = time.monotonic()
        items = requirements(graph)
        print(f"\n=== {name} ({time.monotonic() - t0:.1f}s) editor needed: {editor_needed(items)}")
        for it in items:
            mark = "ok " if it.get("ok") else ("OLD" if it.get("installed") else "-- ")
            need = "" if it["needed"] else " (optional)"
            ver = f" {it['version']}" if it.get("version") else ""
            mn = f" (needs >= {it['min_version']})" if it.get("min_version") else ""
            print(f"  [{mark}] {it['label']}{ver}{mn}{need}: {it['why']}")
            if not it.get("ok"):
                print(f"         install: {it['install']['command'] or it['install']['url']}")
        print("  missing:", [it["tool"] for it in missing(items)])
        card = setup_card(items)
        print("  card:", card["title"], "|", card["body"], "|", card["actions"])


if __name__ == "__main__":
    main()

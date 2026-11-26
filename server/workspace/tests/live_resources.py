"""Live: find + download the tutorial's own materials for Karpathy's GPT video and the cached React lesson.

    .venv/bin/python -m server.workspace.tests.live_resources [karpathy react] [--fresh]
"""

from __future__ import annotations

import argparse
import json
import shutil
import time

from server.workspace import download_resources, download_summary, find_resources
from server.workspace.paths import REPO_ROOT, folder_name, lessons_root

KARPATHY = {"lesson": {"id": "lesson-karpathy-gpt-live", "title": "Let's build GPT: from scratch, in code, spelled out"},
            "sources": [{"id": "src1", "kind": "video", "title": "Let's build GPT", "url": "https://www.youtube.com/watch?v=kCc8FmEb1nY",
                         "videoId": "kCc8FmEb1nY"}], "steps": []}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("which", nargs="*", default=["karpathy", "react"])
    ap.add_argument("--fresh", action="store_true")
    a = ap.parse_args()
    graphs = {"karpathy": KARPATHY, "react": json.loads((REPO_ROOT / "demo/cache/lessons/516197461c0dacf3.json").read_text(encoding="utf-8"))}
    for name in a.which:
        g = graphs[name]
        if a.fresh:
            shutil.rmtree(lessons_root() / folder_name(g) / "tutorial", ignore_errors=True)
        t0 = time.monotonic()
        found = find_resources(g, use_cache=not a.fresh)
        print(f"\n=== {name}: found {len(found)} in {time.monotonic() - t0:.1f}s")
        for r in found:
            print(f"  {r['kind']:8} {r['name']:32} {r['url']}")
        t0 = time.monotonic()
        out = download_resources(g, resources=found)
        print(f"  download {time.monotonic() - t0:.1f}s")
        for r in out:
            print("   ", {k: v for k, v in r.items() if k != "url"})
        print("  summary:", download_summary(out))


if __name__ == "__main__":
    main()

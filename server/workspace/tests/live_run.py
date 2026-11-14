"""Live run: real Claude, real folders under ~/miyagi/lessons (or MIYAGI_LESSONS_DIR).

    .venv/bin/python -m server.workspace.tests.live_run              # React, git, pandas
    .venv/bin/python -m server.workspace.tests.live_run --open pandas # also open VS Code
    .venv/bin/python -m server.workspace.tests.live_run --fresh       # wipe those folders first

Uses the cached step graphs in demo/cache/lessons/ (React, git) and the hand-written pandas graph
in tests/fixtures/. Prints what was created; never prints keys.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import time
from pathlib import Path

import server.orchestrator.config  # noqa: F401  (loads the shared .env)
from server.workspace import (
    folder_name,
    lessons_root,
    open_editor,
    open_file_for,
    prepare,
    read_state,
)
from server.workspace.paths import REPO_ROOT

LESSONS = {
    "react": (REPO_ROOT / "demo/cache/lessons/516197461c0dacf3.json", "learn React basics by building components"),
    "git": (REPO_ROOT / "demo/cache/lessons/8b6203eb5ec8c6f6.json", "learn the basic git commands"),
    "pandas": (Path(__file__).parent / "fixtures/pandas_pokemon.json", "learn pandas: read a CSV, sort, filter and group data"),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("which", nargs="*", default=list(LESSONS))
    ap.add_argument("--open", action="store_true", help="open each folder in VS Code")
    ap.add_argument("--fresh", action="store_true", help="delete the lesson folders first")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    for name in a.which:
        path, goal = LESSONS[name]
        graph = json.loads(path.read_text())
        if a.fresh:
            d = lessons_root() / folder_name(graph)
            shutil.rmtree(d, ignore_errors=True)
            (lessons_root() / ".miyagi-state" / f"{d.name}.json").unlink(missing_ok=True)
        t0 = time.monotonic()
        wd = prepare(graph, goal)
        st = read_state(wd) or {}
        print(f"\n=== {name}: {wd}  ({time.monotonic() - t0:.1f}s, model {st.get('model')})")
        print(f"stack={st.get('stack')!r} summary={st.get('summary')!r}")
        print(f"setup={st.get('setup')} open_file={st.get('open_file')!r} git={st.get('git')}")
        print(f"files={st.get('files')}")
        print(f"dropped={st.get('dropped')}")
        if st.get("error"):
            print(f"ERROR {st['error']}")
        for f in st.get("files") or []:
            text = (wd / f).read_text(errors="replace")
            print(f"--- {f} ({len(text)} chars)\n{text[:600]}{'...' if len(text) > 600 else ''}")
        if a.open:
            print("open_editor:", open_editor(wd, open_file_for(wd)))


if __name__ == "__main__":
    main()

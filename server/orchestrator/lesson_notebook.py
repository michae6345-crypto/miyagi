"""A VS Code notebook lesson's own notebook (desktop test 10, Nov 15: CP3, CP4, CP6, CP10, CP15).

server/lesson/notebook_steps.py names the lesson's notebook (lesson["notebook"], e.g. mnist.ipynb) and points every step
at it. Here, in the running session:
- create(s): load_graph makes that notebook (empty, .venv kernel) in the lesson folder before step 1 starts, so step 2's
  "Run the cell" has a cell to run (test 10: nothing made it; the video makes Untitled.ipynb in a browser Jupyter);
- open_when_up(s, path): the lesson's VS Code window opens on the folder, then the companion extension (POST /open,
  0.0.6 opens a notebook in the notebook editor) shows the notebook in that window (test 10 opened .venv/bin/activate);
- learner_card(s, card): a card's copy never says Untitled.ipynb or "in Jupyter or Colab" (the s2 hint's Where row).
Hooks in LessonSession are one line each."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from server.lesson.notebook_steps import empty_notebook, fix_copy

log = logging.getLogger("orchestrator.lesson_notebook")

OPEN_WAIT_S = 20.0  # the lesson's VS Code window comes up a few seconds after `code <folder>`


def name(s: Any) -> str | None:
    """The lesson's notebook when this is a VS Code notebook lesson (never a Colab one), else None."""
    if not getattr(s, "notebook_lesson", False) or not getattr(s, "graph", None):
        return None
    nb = (s.graph.get("lesson") or {}).get("notebook")
    return nb if isinstance(nb, str) and nb.endswith(".ipynb") else None


def create(s: Any) -> Path | None:
    """Make the lesson's notebook in the lesson folder when it isn't there yet. -> its path (None: not a VS Code
    notebook lesson, or it couldn't be written). Never overwrites the learner's notebook; never raises."""
    nb = name(s)
    folder = Path(getattr(s, "workdir", "") or "")
    if not nb or not folder.is_dir():
        return None
    p = folder / nb
    if p.exists():
        return p
    try:
        p.write_text(json.dumps(empty_notebook(), indent=1) + "\n", encoding="utf-8")
    except OSError as e:
        log.warning("could not create the lesson notebook %s: %s", p, e)
        return None
    log.info("notebook lesson: created %s (.venv kernel)", p)
    return p


def first_file(s: Any) -> str | None:
    """The file VS Code should open first in a VS Code notebook lesson when the step names none yet (the auto-open
    runs before step 1 starts): the lesson's notebook, made if missing. None = not a notebook lesson. Never raises.
    Michael, Nov 15 10:45: VS Code opened on README.md and the drawer covered the Explorer, so the learner had to
    move the drawer to open mnist.ipynb."""
    try:
        nb = name(s)
        if not nb:
            return None
        p = create(s) or (Path(getattr(s, "workdir", "") or "") / nb)
        return str(p) if p.is_file() else None
    except Exception:  # noqa: BLE001 - a convenience: VS Code still opens on the folder
        log.exception("lesson notebook lookup failed")
        return None


async def open_when_up(s: Any, path: str) -> bool:
    """Show the notebook in the lesson's own VS Code window once that window answers (companion extension), without
    taking focus. True = shown. Gives up after OPEN_WAIT_S, on another lesson, or without the extension (tests)."""
    lid = ((s.graph or {}).get("lesson") or {}).get("id")
    root = Path(s.workdir).resolve()
    loop = asyncio.get_running_loop()
    end = loop.time() + OPEN_WAIT_S
    while loop.time() < end:
        if ((s.graph or {}).get("lesson") or {}).get("id") != lid:
            return False
        ext = await asyncio.to_thread(s._vscode_ext)
        if ext is None or not hasattr(ext, "windows") or not hasattr(ext, "open_file"):
            return False

        def show() -> bool | None:
            win = next((w for w in ext.windows() if any(Path(f).resolve() == root for f in w.get("folders") or [])), None)
            if win is None:
                return None  # not up yet
            if win.get("file") and Path(str(win["file"])).resolve() == Path(path).resolve():
                return True
            res = ext.open_file(path, None, folder=s.workdir, preserve_focus=True, port=win.get("port"))
            return bool(isinstance(res, dict) and res.get("ok"))

        try:
            shown = await asyncio.to_thread(show)
        except Exception:  # noqa: BLE001 - a convenience: the lesson runs without it
            log.exception("opening the lesson notebook failed")
            return False
        if shown is not None:
            log.info("notebook lesson: %s %s in the lesson's VS Code window", Path(path).name,
                     "opened" if shown else "could not be opened")
            return shown
        await asyncio.sleep(0.5)
    return False


def learner_card(s: Any, card: dict) -> dict:
    """The card with the lesson's notebook name and VS Code in its copy (where / title / body)."""
    nb = name(s)
    if not nb or not isinstance(card, dict):
        return card
    out = dict(card)
    for k in ("where", "title", "body"):
        if isinstance(out.get(k), str):
            out[k] = fix_copy(out[k], nb)
    return out

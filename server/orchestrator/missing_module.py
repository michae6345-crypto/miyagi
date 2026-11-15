"""A run that stopped on a package the lesson needs (ModuleNotFoundError / ImportError: No module named 'numpy').

Michael, Nov 15 QA: "I had to externally download NumPy myself because when it says download NumPy, [Miyagi] didn't
download it." He had skipped the setup card; the nn4 run then failed with ModuleNotFoundError, the coach said "In VS
Code's terminal, install it, then rerun nn.py" and the "Not yet" cards offered only Run it for me / Skip step.

Now the run's failure itself brings up the one-press Install (the setup card's own installer, S2: pip into the lesson's
.venv), with no model call:

  offer / check_run    "NumPy isn't installed yet. Install it?" [install, skip_step] with the setup row (the app draws
                       Install on a setup row only; it sends `install` with the row's tool id)
  after_install        "Installed. Run it again." (Run it for me), or the rerun when the learner had pressed Run it for
                       me; a failed install shows the exact command to type instead
  in the .venv already the learner's terminal isn't the .venv's (opened before it existed): "Open a new terminal", or
                       the exact `python3 -m pip install numpy` for that terminal's Python
  add_command          any other card that says "install" for a missing module carries the exact command
"""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger("orchestrator.missing_module")

# "No module named 'numpy'", OCR'd quotes ("loduleNotFoundError: No module named \"numpy'"), Python 2's bare name
NO_MODULE = re.compile(r"No module named\s+['\"‘’“”`]?([A-Za-z_][\w.]*)")
PRETTY = {"numpy": "NumPy", "pandas": "pandas", "matplotlib": "Matplotlib", "scipy": "SciPy", "torch": "PyTorch",
          "sklearn": "scikit-learn", "tensorflow": "TensorFlow", "cv2": "OpenCV", "PIL": "Pillow"}
PIP = {"sklearn": "scikit-learn", "cv2": "opencv-python", "PIL": "pillow", "yaml": "pyyaml", "bs4": "beautifulsoup4"}
OFFER_ACTIONS = ["install", "skip_step"]  # Install itself is the setup row's button (the app's ACTION has no install)
RERUN_WINDOW_S = 10.0  # a VS Code run that started this close to a Run it for me press was that press


def missing_module(lines: list[str] | None) -> str | None:
    """The top-level module a traceback says is missing ('numpy' from numpy.linalg), else None."""
    found = NO_MODULE.findall("\n".join(str(x) for x in lines or []))
    return found[-1].split(".")[0] if found else None


def install_command(mod: str, item: dict | None = None) -> str:
    """The exact command for VS Code's terminal: `python3 -m pip install numpy` (that terminal's own Python)."""
    pkg = ((item or {}).get("pip_name") or "").strip() or PIP.get(mod, mod)
    return f"python3 -m pip install {pkg}"


def pretty(mod: str, item: dict | None = None) -> str:
    return PRETTY.get(mod) or (item or {}).get("label") or mod


def in_venv(workdir: str | Path, mod: str) -> bool:
    """Is `mod` installed in the lesson's own .venv (where the setup card's Install puts it)?"""
    lib = Path(workdir) / ".venv" / "lib"
    return any(any(lib.glob(f"python*/site-packages/{mod}{tail}")) for tail in ("/__init__.py", ".py", ".*.so"))


def lesson_item(session: Any, mod: str) -> dict | None:
    """The lesson's setup item (S2's requirements) for `mod`, installable with pip, else None: a module the lesson
    doesn't need (a typo, `import nunpy`) never gets an Install button. Blocking (the curated lesson's requirements
    come from its cache, no Claude call): run it in a thread."""
    items = list(getattr(session, "reqs", None) or [])
    if not items:  # no setup check ran (or it's still running): the curated lesson knows its own
        from . import curated

        if not curated.active(session):
            return None
        from . import workspace as wsmod

        items = list(wsmod.requirements(session.graph, session.workdir) or [])
        if items:
            session.reqs = items  # _install looks the tool up there
    return _match(items, mod)


def _match(items: list[dict], mod: str) -> dict | None:
    """The setup item for a missing module. Also by its pip name (`sklearn` -> scikit-learn, `cv2` -> opencv-python,
    `PIL` -> pillow) when the lesson's item named only the pip package, so those still get their Install button."""
    from server.workspace.setup import IMPORT_ALIASES

    wanted = {mod, PIP.get(mod, mod)}
    for it in items:
        names = {(it.get(k) or "").strip() for k in ("import_name", "pip_name", "tool")}
        for n in list(names):
            names.update(IMPORT_ALIASES.get(n.lower(), []))
        if wanted & names and ((it.get("install") or {}).get("method") == "pip" or it.get("kind") == "python_package"):
            return it
    return None


def _failed_run(session: Any, ctx: Any = None) -> Any:
    run = getattr(ctx, "last_run", None) if ctx is not None else None
    if run is None:
        runs = getattr(session, "step_runs", None) or []
        run = runs[-1] if runs else None
    if run is None or getattr(run, "running", False) or getattr(run, "exit_code", None) in (0, None):
        return None
    return run


def _pressed_run(session: Any, run: Any) -> bool:
    """Was this run the learner's Run it for me (then the fix reruns it for them)?"""
    rid = str(getattr(run, "run_id", "") or "")
    if rid.startswith("run-for-me-"):
        return True
    t = float(getattr(session, "_ext_run_t", 0.0) or 0.0)
    m = re.search(r"-(\d{12,})$", rid)  # vscode-<id>-<startedAt ms>
    return bool(t and m and abs(int(m[1]) / 1000 - t) < RERUN_WINDOW_S)


def check_run(session: Any, step: dict, ctx: Any) -> bool:
    """The speaking decision's first look (_consider_speaking): did the step's last run stop on a package the lesson
    needs? Then the Install card goes out (once per run; the learner's screen when no run was reported) and the coach
    isn't asked to explain it: True. A later trigger on the same run stays quiet: True."""
    run = _failed_run(session, ctx)
    if run is not None:
        lines, key, rerun = list(run.output_tail or []), ("run", run.run_id), _pressed_run(session, run)
    else:
        lines, key, rerun = session._screen_error_lines(), ("screen", session.step_gen), False
    mod = missing_module(lines)
    reqs = list(getattr(session, "reqs", None) or [])
    if not mod or (reqs and _match(reqs, mod) is None):  # not a lesson package (a typo?): the coach explains it
        return False
    seen = session.__dict__.setdefault("_mm_seen", {})
    if key in seen:
        return seen[key]
    seen[key] = True  # decided below in the background; a repeat trigger meanwhile stays quiet
    if run is None and in_venv(session.workdir, mod):
        seen[key] = False  # an old traceback on screen; the .venv has it: nothing to offer
        return False
    session._spawn(offer(session, step, mod, rerun=rerun, from_run=run is not None, key=key))
    return True


async def reoffer(session: Any, step: dict) -> bool:
    """Check on a step whose last run stopped on a lesson package: the Install card again, not "Not yet"."""
    run = _failed_run(session)
    mod = missing_module(list(run.output_tail or [])) if run is not None else None
    if not mod:
        return False
    return await offer(session, step, mod, rerun=_pressed_run(session, run), from_run=True)


async def offer(session: Any, step: dict, mod: str, *, rerun: bool = False, from_run: bool = True,
                key: tuple | None = None) -> bool:
    """Send the Install card for `mod` (or, already in the .venv, the new-terminal card). False when `mod` isn't one
    of the lesson's packages: the coach explains it as usual."""
    from . import workspace as wsmod

    item = await asyncio.to_thread(lesson_item, session, mod)
    if item is None or session.step is not step or session.passed:
        if key is not None:  # the coach may explain this run after all (the next trigger)
            session.__dict__.setdefault("_mm_seen", {})[key] = False
        return False
    name, cmd = pretty(mod, item), install_command(mod, item)
    run_step = bool(session.lesson_mode and session._run_command(step))
    if in_venv(session.workdir, mod):  # Installed for the lesson, but this terminal's python3 isn't the .venv's
        if not from_run:
            return False
        await asyncio.to_thread(wsmod.python_terminal_settings, session.workdir)  # new terminals: the .venv first
        from . import curated

        curated.prepare_step(session, step)  # Run it for me: .venv/bin/python nn.py
        card = {"stepId": step["id"], "kind": "answer", "title": f"This terminal's Python doesn't have {name}",
                "body": f"{name} is in the lesson's .venv. Open a new terminal (Terminal > New Terminal) and run it "
                        "again, or install it for this terminal's Python:",
                "output": cmd, "actions": (["run_command"] if run_step else []) + ["skip_step"]}
    else:
        base = await asyncio.to_thread(wsmod.setup_card, [{**item, "needed": True, "ok": False, "installed": False}])
        card = {**(base or {"kind": "setup"}), "stepId": step["id"], "title": f"{name} isn't installed yet. Install it?",
                "body": "It goes into this lesson's own Python (.venv).", "actions": list(OFFER_ACTIONS)}
        if not base:  # S2's card builder isn't here: no Install row, so the exact command instead
            card.update(kind="answer", body="Run this in VS Code's terminal:", output=cmd, actions=["skip_step"])
        session._mm_offer = {"tool": item.get("tool") or mod, "mod": mod, "name": name, "cmd": cmd,
                             "gen": session.step_gen, "rerun": rerun, "card": card}
    log.info("run stopped on missing %s: %r", mod, card["title"])
    session._record("missing_module", {"module": mod, "in_venv": card["kind"] == "answer", "rerun": rerun}, step)
    await session._status("offtrack" if session.last_offtrack else "watching")
    await session._emit_card(card, window_s=1.0)
    return True


async def after_install(session: Any, tool: str, res: dict) -> bool:
    """_install finished a package a run stopped on: rerun it (the learner had pressed Run it for me) or "Installed.
    Run it again."; a failed install says why with the exact command. False: no such run (the setup card's own
    install: _install answers as before)."""
    o = getattr(session, "_mm_offer", None)
    step = session.step
    if not o or o["tool"] != tool:
        return False
    if o["gen"] != session.step_gen or step is None or session.passed:
        session._mm_offer = None
        return False
    if not res.get("ok"):
        reason = (str(res.get("error") or "unknown error").strip().splitlines() or ["unknown error"])[-1]
        await session._emit_card({**o["card"], "title": f"Couldn't install {o['name']}",
                                  "body": f"{reason[:140]}. Press Retry, or run this in VS Code's terminal:",
                                  "output": o["cmd"]}, window_s=0.0)
        return True  # o stays: Retry comes back here
    session._mm_offer = None
    from . import curated
    from . import workspace as wsmod

    await asyncio.to_thread(wsmod.python_terminal_settings, session.workdir)  # new terminals: .venv/bin first on PATH
    curated.prepare_step(session, step)  # Run it for me (curated): .venv/bin/python nn.py
    run_step = bool(session.lesson_mode and session._run_command(step))
    session._record("missing_module_installed", {"module": o["mod"], "rerun": o["rerun"] and run_step}, step)
    if o["rerun"] and run_step:
        await session._card(step, f"{o['name']} installed", "Running it again…", kind="answer")
        await session._run_for_me(step)
        return True
    await session._emit_card({"stepId": step["id"], "kind": "answer", "title": "Installed. Run it again.",
                              "body": f"{o['name']} is in this lesson's .venv now. If it still says No module named "
                                      f"'{o['mod']}', open a new terminal (Terminal > New Terminal) and run it there.",
                              **({"actions": ["run_command"]} if run_step else {})}, window_s=0.0)
    return True


async def install(session: Any, text: str | None) -> None:
    """The Install press (action install): its text is the setup row's tool id; a plain `install` (no text) means the
    package this card is about: the run's missing one, else the setup card's first missing pip row. The item comes
    from the setup check (session.reqs), or the curated lesson's own list when no check ran, so it never ends on
    "Unknown tool for this lesson"."""
    tool = (text or "").strip()
    if not tool:
        o = getattr(session, "_mm_offer", None) or {}
        rows = [x for x in ((getattr(session, "_setup_card", None) or {}).get("setup") or {}).get("items") or []
                if x.get("needed") and not x.get("ok") and (x.get("install") or {}).get("method") == "pip"]
        tool = o.get("tool") or (rows[0]["tool"] if rows else "")
        if not tool:
            miss = [it for it in getattr(session, "reqs", None) or []
                    if it.get("needed") and not it.get("ok") and (it.get("install") or {}).get("method") == "pip"]
            tool = miss[0]["tool"] if miss else ""
    item = next((it for it in getattr(session, "reqs", None) or [] if it.get("tool") == tool), None)
    if item is None and tool:
        item = await asyncio.to_thread(lesson_item, session, tool)
    log.info("install %r (pressed: %r)%s", tool, text, "" if item else ": no setup item")
    await session._install(tool, item=item)


def setup_without_open(session: Any, payload: dict) -> dict:
    """No "Open VS Code" on a setup card once the lesson's editor is open (every "Just teach me" lesson, a video
    lesson after Open / auto-open): Michael, Nov 15, pressed the big Open instead of NumPy's Install. Install stays."""
    acts = payload.get("actions") or []
    if payload.get("kind") != "setup" or "open_editor" not in acts:
        return payload
    if not (getattr(session, "lesson_mode", False) or getattr(session, "editor_open", False)):
        return payload
    return {**payload, "actions": [a for a in acts if a != "open_editor"]}


def add_command(card: dict, lines: list[str] | None) -> None:
    """A coach card that tells the learner to install a missing module carries the exact command (never just
    "install it"). In place."""
    mod = missing_module(lines)
    text = f"{card.get('title') or ''} {card.get('body') or ''}"
    if not mod or not re.search(r"\binstall", text, re.I) or "pip install" in text:
        return
    card["body"] = f"{(card.get('body') or '').rstrip()} Run: {install_command(mod)}".strip()


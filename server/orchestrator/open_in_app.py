"""Open in Blender (Nov 24): the setup card of a Blender lesson opens the lesson's scene in the learner's Blender with
the miyagi bridge already running, so no add-on install is needed.

    blend_path(s)          <lesson folder>/<stem>.blend for a Blender lesson (graph.lesson.app.tool == "blender"),
                           else None. The stem: the first step whose "file" is a .blend, else the first file_contains
                           check on "<stem>.scene.json" (app_lesson.SCENE_GUIDE). A bare file name only.
    offer_card(s, items)   the setup card {title "Blender is ready", body "Open donut.blend in Blender?", actions
                           ["open_in_app"], setup.actionLabels.open_in_app "Open in Blender", setup.holdVideo False};
                           None when it does not apply (no Blender, no scene, workspace off). With
                           APP_RENDERS_OPEN_IN_APP False: the old passing note (setup_apps.note_card).
    open_card(s, items)    the same card, never the note: None when it does not apply or the flag is off.
    act(s, text)           the button: already open -> a note; another Blender without the bridge -> "quit first";
                           missing or 0-byte scene -> made from Blender's factory scene (headless, blender.create_blend);
                           then ONE launch through s.workspace.run (Workspace._spawn: Popen, new session, child_env), at
                           most once per LAUNCH_GRACE_S per file. Once the bridge answers for the file, the on-screen
                           coach looks again for the step that was current at the press. Never raises.

Nothing here calls subprocess: Blender for the learner starts only through s.workspace.run, and the headless create
through blender.run_blender (its clean env). Every card it sends is <= 12 words.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from pathlib import Path
from typing import Any

from server.workspace import blender
from server.workspace import blender_ext as bx

from . import onscreen_coach, setup_apps

log = logging.getLogger("orchestrator.open_in_app")

APP_RENDERS_OPEN_IN_APP = True  # the app draws the open_in_app button (lane "app"); False: the old passing note
TOOL = "blender"
LABEL = "Blender"
LAUNCH_GRACE_S = 45.0  # a second press this soon after a launch never launches again (Blender takes a while to open)
WATCH_S = 30.0  # after a launch: how long to wait for the bridge to answer for the file
WATCH_POLL_S = 1.0
MAX_WORDS = 12

_NAME = re.compile(r"[A-Za-z0-9 _.\-]+")
BLEND = ".blend"
SCENE_JSON = ".scene.json"

TITLE = f"{LABEL} is ready"
LABEL_OPEN = f"Open in {LABEL}"
ALREADY_OPEN = f"Already open in {LABEL}"
QUIT_FIRST = f"Quit {LABEL}, then press Open in {LABEL} again."
OPENING = f"{LABEL} is opening. Give it a moment."
NO_BLENDER = f"{LABEL} isn't on this Mac yet."
NO_SCENE = f"This lesson has no {LABEL} scene to open."
OTHER_APP = f"Only {LABEL} opens from here for now."
CREATE_FAILED = "Couldn't make the scene file. Try again."
LAUNCH_FAILED = f"Couldn't start {LABEL}. Try again."


# ------------------------------------------------------------------ which file

def _tool(s: Any) -> str:
    app = ((getattr(s, "graph", None) or {}).get("lesson") or {}).get("app")
    return str(app.get("tool") or "").strip().lower() if isinstance(app, dict) else ""


def is_blender_lesson(s: Any) -> bool:
    return _tool(s) == TOOL


def safe_name(raw: Any, suffix: str) -> str | None:
    """raw when it is a bare file name ending in suffix ([A-Za-z0-9 _.-] only), else None: never an absolute path, a
    '..', a slash, a hidden file or an empty stem."""
    if not isinstance(raw, str):
        return None
    name = raw.strip()
    if not name.lower().endswith(suffix) or "/" in name or "\\" in name or ".." in name or name.startswith((".", "~")):
        return None
    if not _NAME.fullmatch(name) or not name[: -len(suffix)].strip(" ."):
        return None
    return name


def _steps(s: Any) -> list[dict]:
    steps = (getattr(s, "graph", None) or {}).get("steps") or getattr(s, "steps", None) or []
    return [st for st in steps if isinstance(st, dict)]


def blend_name(s: Any) -> str | None:
    """"donut.blend": the first step whose file is a .blend, else the first file_contains check on "donut.scene.json".
    Unsafe names (absolute, '..', a folder) are skipped, never followed."""
    steps = _steps(s)
    for st in steps:
        f = st.get("file")
        if isinstance(f, str) and f.strip().lower().endswith(BLEND):
            if name := safe_name(f, BLEND):
                return name
            log.info("open_in_app: unsafe step file %r skipped", f[:120])
    for st in steps:
        for c in st.get("checks") or []:
            if not isinstance(c, dict) or c.get("type") != "file_contains":
                continue
            f = c.get("file")
            if isinstance(f, str) and f.strip().lower().endswith(SCENE_JSON):
                if name := safe_name(f, SCENE_JSON):
                    return name[: -len(SCENE_JSON)] + BLEND
                log.info("open_in_app: unsafe scene check file %r skipped", f[:120])
    return None


def blend_path(s: Any) -> Path | None:
    """<s.workdir>/<stem>.blend, resolved, for a Blender lesson; None otherwise or when it would leave s.workdir."""
    if not is_blender_lesson(s):
        return None
    name, wd = blend_name(s), getattr(s, "workdir", None)
    if not name or not wd:
        return None
    try:
        root = Path(wd).expanduser().resolve()
        path = (root / name).resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    if path == root or not path.is_relative_to(root):  # a symlink out of the lesson folder
        log.info("open_in_app: %s leaves the lesson folder", name)
        return None
    return path


# ------------------------------------------------------------------ the card

def _row(items: list[dict]) -> dict | None:
    return next((it for it in items or [] if isinstance(it, dict) and str(it.get("tool") or "").lower() == TOOL
                 and it.get("kind") != "editor"), None)


def _blender_found(row: dict | None) -> bool:
    if row is not None and (row.get("ok") or row.get("installed")):
        return True
    try:
        return blender.find_blender() is not None
    except Exception:  # noqa: BLE001 - a failed look is "not found"
        return False


def _short(text: str, fallback: str) -> str:
    return text if len(text.split()) <= MAX_WORDS else fallback


def open_card(s: Any, items: list[dict]) -> dict | None:
    """The Open in Blender setup card, or None (flag off, workspace off, not a Blender lesson, no scene name, no
    Blender on this Mac). setup.items: the Blender row only."""
    if not APP_RENDERS_OPEN_IN_APP:
        return None
    ws = getattr(s, "workspace", None)
    if ws is None or not getattr(ws, "enabled", False):
        return None
    path = blend_path(s)
    if path is None:
        return None
    row = _row(items)
    if not _blender_found(row):
        return None
    try:
        from server.workspace import setup as S

        card = S.setup_card([row] if row else [])
    except Exception:  # an odd row: no offer (the old note stays)
        log.exception("open_in_app: setup card failed")
        return None
    card.update(title=TITLE, body=_short(f"Open {path.name} in {LABEL}?", f"Open the lesson's scene in {LABEL}?"),
                actions=["open_in_app"])
    setup = card.setdefault("setup", {})
    setup["actionLabels"] = {"open_in_app": LABEL_OPEN}
    setup["holdVideo"] = False
    return card


def offer_card(s: Any, items: list[dict]) -> dict | None:
    """open_card; with APP_RENDERS_OPEN_IN_APP off, the old passing note ("Blender is ready", no buttons)."""
    if not APP_RENDERS_OPEN_IN_APP:
        note = setup_apps.ready_note(items or [])
        return setup_apps.note_card(note) if note else None
    return open_card(s, items)


# ------------------------------------------------------------------ the button

def _state(s: Any) -> dict:
    st = getattr(s, "_open_in_app", None)
    if not isinstance(st, dict):
        st = {"lock": asyncio.Lock(), "launched": {}, "watch": None}
        s._open_in_app = st
    return st


def _now(s: Any) -> float:
    clock = getattr(s, "clock", None)
    return float(clock()) if callable(clock) else time.monotonic()


def _instances() -> list[dict]:
    try:
        return list(bx.instances() or [])
    except Exception:  # noqa: BLE001 - no answer is "no Blender with the bridge"
        return []


def _running_pids() -> list[int]:
    """pids of every running Blender (NSWorkspace, bundle org.blenderfoundation.blender); [] off macOS."""
    try:
        import AppKit
    except ImportError:
        return []
    try:
        apps = AppKit.NSRunningApplication.runningApplicationsWithBundleIdentifier_(blender.BUNDLE_ID) or []
        return [int(a.processIdentifier()) for a in apps if not a.isTerminated()]
    except Exception:  # noqa: BLE001
        return []


def running_without_bridge(found: list[dict]) -> bool:
    """A Blender runs that no bridge answers for (opened by the learner, without start_bridge.py): launching another
    would leave the learner with two. The seam tests replace."""
    pids = set(_running_pids())
    if not pids:
        return False
    bridged = {h.get("pid") for h in found if isinstance(h.get("pid"), int)}
    unknown = sum(1 for h in found if not isinstance(h.get("pid"), int))  # an older bridge without a pid
    return len(pids - bridged) > unknown


def _without_bridge(argv: list[str]) -> list[str]:
    """launch_argv minus its '--python <start_bridge.py>' pair (an old packaged app without blender-addon/)."""
    out = list(argv)
    if "--python" in out:
        i = out.index("--python")
        del out[i:i + 2]
    return out


async def _say(s: Any, text: str) -> None:
    await s.emit("card", setup_apps.note_card(text))


async def act(s: Any, text: str | None = None) -> None:
    """The setup card's Open in Blender. Every failure is one short card; nothing raises."""
    try:
        await _act(s, text)
    except Exception:  # never a crash for a button
        log.exception("open_in_app failed")
        try:
            await _say(s, LAUNCH_FAILED)
        except Exception:
            log.exception("open_in_app: the failure card failed too")


async def _act(s: Any, text: str | None) -> None:
    tool = (text or "").strip().lower()
    if tool and tool != TOOL:
        await _say(s, OTHER_APP)
        return
    path = blend_path(s)
    if path is None:
        await _say(s, NO_SCENE)
        return
    exe = await asyncio.to_thread(blender.find_blender)
    if not exe:
        await _say(s, NO_BLENDER)
        return
    st = _state(s)
    async with st["lock"]:  # two presses at once: the second waits, then sees the first's launch
        found = await asyncio.to_thread(_instances)
        if bx.pick(found, path) is not None:
            await _say(s, ALREADY_OPEN)
            return
        last = st["launched"].get(str(path))
        if last is not None and _now(s) - last < LAUNCH_GRACE_S:
            await _say(s, OPENING)
            return
        if await asyncio.to_thread(running_without_bridge, found):
            await _say(s, QUIT_FIRST)
            return
        # missing, or 0 bytes (lesson mode touches step files): Blender's factory scene, made headless
        if not blender.has_content(path) and not await asyncio.to_thread(blender.create_blend, path, blender=exe):
            await _say(s, CREATE_FAILED)
            return
        argv = bx.launch_argv(path, blender=exe)
        if not argv:
            await _say(s, NO_BLENDER)
            return
        if not Path(bx.BRIDGE_START).is_file():
            log.warning("open_in_app: %s is missing (blender-addon not bundled): opening Blender without the bridge",
                        bx.BRIDGE_START)
            argv = _without_bridge(argv)
        ws = getattr(s, "workspace", None)
        if ws is None or not ws.run(argv):
            await _say(s, LAUNCH_FAILED)
            return
        st["launched"][str(path)] = _now(s)
        log.info("open_in_app: launched Blender on %s", path)
        await _say(s, _short(f"Opening {path.name} in {LABEL}", f"Opening {LABEL}"))
        gen, step = getattr(s, "step_gen", None), getattr(s, "step", None)
        st["watch"] = s._spawn(_watch(s, path, gen, step), timer=True)


def _current(s: Any, gen: Any, step: Any) -> bool:
    return step is not None and getattr(s, "step_gen", None) == gen and getattr(s, "step", None) is step


def _app_lesson(s: Any) -> bool:
    try:
        return bool(onscreen_coach.is_app_lesson(s))
    except Exception:  # noqa: BLE001 - unsure: no circle (a wrong circle is worse than none)
        return False


async def _watch(s: Any, path: Path, gen: Any, step: Any) -> bool:
    """Poll the bridge every WATCH_POLL_S for up to WATCH_S. Once it answers for path, and the step of the press is
    still current in an app lesson, the on-screen coach looks for that step again (once). -> True when it did."""
    waited = 0.0
    while waited < WATCH_S:
        await asyncio.sleep(WATCH_POLL_S)
        waited += WATCH_POLL_S
        if not _current(s, gen, step):
            return False
        found = await asyncio.to_thread(_instances)
        if bx.pick(found, path) is None:
            continue
        if not _current(s, gen, step) or not _app_lesson(s):
            return False
        s._spawn(onscreen_coach.on_step(s, gen, step))
        return True
    log.info("open_in_app: no bridge answered for %s within %.0f s", path, WATCH_S)
    return False

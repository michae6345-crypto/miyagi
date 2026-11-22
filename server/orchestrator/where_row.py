"""The Where row ("Open nn.py in VS Code" + its Open button) only when the step's file is NOT already the active file
of the lesson's VS Code window, and an Open that reveals the file in that EXISTING window.

Michael, live (Just teach me: build a neural network): an Explain card carried "Open nn.py in VS Code" + Open while
nn.py was open and in front ("What do you mean, Open nn.py? It's open"), and Open felt "like opening up another link"
(two `code` CLI launches, the second one `code -r`, which reuses whichever window was last active).

Hooks in LessonSession (kept tiny for merges):
- `emit()`: `payload = await where_row.filter_card(self, payload)` for every card that offers a Where row / Open
  (card["where"] or the open_editor action). When the step's file is the lesson window's active file, the row and the
  Open action are dropped; a "where" card that only says "Open <that file>" is dropped whole (Show me then answers
  "Nothing to point at", never a wrong instruction).
- `_open_editor()`: `where_row.reveal(folder, file, line)` first: the companion extension shows the file in the window
  that has the lesson folder open (showTextDocument, never a new window, never a browser), then raises that window.

Active file, best first (cheap, no OCR, no model): the companion extension's window whose folders hold the lesson
folder; else that window's title ("● nn.py — build-a-nn-5bfcf1") from E6's window list, else from CGWindowList.
Unknown -> the card goes out unchanged (the old behavior). The row also stays when the lesson's window isn't on
screen (another project's VS Code window in front, or no VS Code window at all): there Open is the right answer.
"""
from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from server.config import safe_env

log = logging.getLogger("orchestrator.where_row")

CODE_APPS = {"code", "vs code", "vscode", "visual studio code"}
VSCODE_BUNDLE = "com.microsoft.VSCode"
KEEP_KINDS = {"setup", "preflight", "step"}  # setup/preflight Open = open the editor at all; "step" = Wrong folder?
OPEN_FILE = re.compile(r"\bopen\s+([\w.-]+\.\w+)", re.IGNORECASE)


def offers_open(card: dict | None) -> bool:
    return bool(card) and bool(card.get("where") or "open_editor" in (card.get("actions") or []))


def _inside(child: str | Path, parent: str | Path) -> bool:
    try:
        Path(child).expanduser().resolve().relative_to(Path(parent).expanduser().resolve())
        return True
    except (ValueError, OSError):
        return False


def _lesson_ext_window(folder: str) -> tuple[dict | None, list[dict]]:
    """(the extension window whose workspace folders hold `folder`, every extension window). (None, []) w/o extension."""
    try:
        from server.workspace import vscode_ext as vx

        wins = vx.windows()
    except Exception:  # noqa: BLE001 - the extension is a refinement
        return None, []
    return next((w for w in wins if any(_inside(folder, f) for f in w.get("folders") or [])), None), wins


def lesson_active_file(folder: str | None, windows: list | None = None) -> dict | None:
    """{file, dirty, source} of the lesson's VS Code window (file None: no editor / Untitled), or None when unknown.
    Blocking (<= 0.3 s extension timeout): from async code use asyncio.to_thread."""
    if not folder:
        return None
    w, _ = _lesson_ext_window(folder)
    if w is not None:
        f = str(w.get("file") or "")
        real = bool(f) and "://" not in f and not f.startswith("untitled:")
        return {"file": Path(f).name if real else None, "dirty": bool(w.get("dirty")), "source": "extension"}
    titles = [getattr(x, "title", "") or "" for x in windows or [] if (getattr(x, "app", "") or "").lower() in CODE_APPS]
    try:
        from server.workspace.active import vscode_windows

        rows = vscode_windows(titles) if titles else vscode_windows()
    except Exception:  # noqa: BLE001
        rows = []
    name = Path(folder).name
    for r in rows:
        if r.get("folder_name") == name:
            return {"file": r.get("file"), "dirty": bool(r.get("dirty")), "source": "title"}
    return None


def _code_on_screen(obs: Any) -> bool | None:
    """Is a (lesson) VS Code window on screen? None = unknown (no frame / no window list)."""
    wins = getattr(obs, "windows", None) if obs is not None else None
    if not wins:
        return None
    return any((getattr(w, "app", "") or "").lower() in CODE_APPS for w in wins)


def _names(s: Any, card: dict) -> set[str]:
    """The file(s) this card would send the learner to open: the step's file + any "Open <file>" in its text."""
    sid = card.get("stepId")
    step = next((st for st in getattr(s, "steps", None) or [] if st.get("id") == sid), None) if sid else None
    step = step or getattr(s, "step", None)
    out: set[str] = set()
    if step is not None:
        try:
            f = s._step_file(step) or step.get("file") or ""
        except Exception:  # noqa: BLE001
            f = step.get("file") or ""
        if f and f != "(terminal)":
            out.add(Path(f).name.lower())
    for text in (card.get("where"), card.get("title"), card.get("body")):
        out |= {m.lower() for m in OPEN_FILE.findall(str(text or ""))}
    return out


def strip_open(card: dict, name: str) -> dict | None:
    """`card` without its Where row and Open action; None for a "where" card that only says "Open <name>"."""
    text = f"{card.get('title', '')} {card.get('body', '')}".lower()
    if card.get("kind") == "where" and name in text and re.search(r"\bopen\b", text):
        return None
    out = {k: v for k, v in card.items() if k != "where"}
    if "actions" in out:
        out["actions"] = [a for a in out.get("actions") or [] if a != "open_editor"]
        if not out["actions"]:
            del out["actions"]
    return out


OPEN_SENTENCE = re.compile(r"\s*Open the lesson folder in [^?.]+[?.]")


async def setup_without_open(s: Any, card: dict) -> dict:
    """A setup card without "Open Visual Studio Code" when the lesson's VS Code window is already open (companion
    extension window holding the folder, else a window title naming it). t5 02:11:33: "Ready to go" offered Open while
    VS Code had the lesson folder open in front. Nothing left to install: Skip reads "Done". Never raises."""
    if "open_editor" not in (card.get("actions") or []) or getattr(getattr(s, "screen", None), "reader", None) is None:
        return card  # (no real screen reader: tests never read the learner's real VS Code)
    folder = getattr(s, "workdir", None)
    if not folder:
        return card
    try:
        found = await asyncio.to_thread(lesson_active_file, folder, getattr(getattr(s, "last_obs", None), "windows", None))
    except Exception:  # noqa: BLE001 - a refinement: the card goes out as before
        log.exception("where_row: lesson-window check failed")
        return card
    if found is None:
        return card  # no window of the lesson folder: Open is the right answer
    out = {**card, "actions": [a for a in card["actions"] if a != "open_editor"]}
    out["body"] = OPEN_SENTENCE.sub("", out.get("body") or "").strip() or out.get("body") or ""
    if "install" not in out["actions"] and isinstance(out.get("setup"), dict):
        out["setup"] = {**out["setup"], "actionLabels": {**(out["setup"].get("actionLabels") or {}), "skip_setup": "Done"}}
    log.info("where_row: the lesson's VS Code window is open (%s): no Open on setup card %r", found.get("source"),
             card.get("title"))
    return out


async def filter_card(s: Any, card: dict) -> dict | None:
    """The card to send (maybe without its Where row / Open), or None to send nothing. Never raises."""
    if card.get("kind") == "setup":
        return await setup_without_open(s, card)
    if not offers_open(card) or card.get("kind") in KEEP_KINDS or "use_this_folder" in (card.get("actions") or []):
        return card
    if getattr(getattr(s, "screen", None), "reader", None) is None:
        return card  # no real screen reader (tests, fixtures): never read the learner's real VS Code
    try:
        names = _names(s, card)
        folder = getattr(s, "workdir", None)
        if not names or not folder:
            return card
        if s._lesson_window_hidden() or _code_on_screen(getattr(s, "last_obs", None)) is False:
            return card  # the lesson's window isn't the one on screen: Open brings it forward
        active = await asyncio.to_thread(lesson_active_file, folder, getattr(getattr(s, "last_obs", None), "windows", None))
        name = str((active or {}).get("file") or "").lower()
        if not name or name not in names:
            return card
    except Exception:  # noqa: BLE001 - a refinement: the card goes out as before
        log.exception("where_row: active-file check failed")
        return card
    out = strip_open(card, name)
    log.info("where_row: %s is already the active file (%s): %s %r", name, (active or {}).get("source"),
             "dropped the where card" if out is None else "no Where row / Open on", card.get("title"))
    return out


def _raise_window(folder: str, last_focused: bool) -> None:
    """Bring the lesson's VS Code window forward. It was the last focused VS Code window: activate VS Code (no CLI);
    else `code <folder>` (the folder is open there, so VS Code focuses that window; no -n, no -r, no -g)."""
    mac = sys.platform == "darwin"  # `open -b` is macOS only: elsewhere `code <folder>` raises the window too
    if last_focused and mac:
        argv = ["open", "-b", VSCODE_BUNDLE]
    else:
        from . import workspace as wsmod

        cli = wsmod.code_cli()
        if not cli and not mac:
            return
        argv = [cli, folder] if cli else ["open", "-b", VSCODE_BUNDLE]
    try:
        subprocess.run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5, check=False,
                       start_new_session=True, env=safe_env())  # `code` may start VS Code: no keys in its env
    except (OSError, subprocess.TimeoutExpired) as e:
        log.info("where_row: raising the lesson window: %s", e)


def reveal(folder: str | None, file: str | None, line: int | None = None) -> bool:
    """Open: show `file` (at `line`) in the EXISTING VS Code window that has `folder` open, via the companion
    extension, then raise that window. False when no extension window has the folder (the caller falls back to the
    `code` CLI). Blocking: from async code use asyncio.to_thread."""
    if not folder or not file:
        return False
    w, wins = _lesson_ext_window(folder)
    if w is None:
        return False
    from server.workspace import vscode_ext as vx

    res = vx.open_file(file, line, folder=folder, port=int(w["port"]))
    if not (res and res.get("ok")):
        log.info("where_row: extension couldn't open %s (%s); falling back", Path(file).name, (res or {}).get("error"))
        return False
    if not w.get("windowFocused"):
        _raise_window(folder, last_focused=bool(wins) and wins[0] is w)
    log.info("where_row: revealed %s%s in the lesson's VS Code window (port %s)", Path(file).name,
             f":{line}" if line else "", w.get("port"))
    return True

"""Point at what the coach is talking about, fast (Explain / Show me / Hint must never feel dead).

`point()` returns `{"targets": [...], "where": str | None, "via": ...}`:
1. deterministic first (no model, ~1 ms): the diagnosed line (`diff.yours`), the step's own
   `targets[].match`, the file name in a window title;
2. else Claude Haiku over the numbered box list (thinking off, text only; ~1 s);
3. nothing relevant on screen → no target, and `where` says where to go ("Open pinn_diffusion.py
   in your editor", "Switch to your terminal and run `python train.py`"). Never a fake target.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from . import llm
from .common import get_lesson
from .screen import ScreenContext

log = logging.getLogger("coach.pointing")

POINT_SYSTEM = """You point a learner at the right place on their screen for a tutorial overlay. You get the step, what the coach is talking about, and the numbered text boxes on screen (from OCR / accessibility, with app names and positions). Return the ids of the boxes that ARE that place (the exact code line, setting, button or terminal line), best first, at most 3. If nothing on screen is that place (for example the code file is not open), return [] and say in `where`, in at most 12 words, where the learner should go first ("Open pinn_diffusion.py in your editor"). Never pick a box just because it shares a word."""

POINT_SCHEMA = {
    "type": "object",
    "properties": {
        "box_ids": {"type": "array", "items": {"type": "integer"}},
        "where": {"type": "string"},
    },
    "required": ["box_ids", "where"],
    "additionalProperties": False,
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def _first_line(text: str) -> str:
    return next((ln.strip() for ln in (text or "").splitlines() if ln.strip()), "")


FILE_NAME = re.compile(r"\b([\w.-]+\.(?:py|ipynb|js|jsx|ts|tsx|html|css|md|json|txt|csv|sh|rs|go|java|c|cpp|rb))\b")
UNTITLED = re.compile(r"\bUntitled-?\d*\b(?:\.\w+)?")
EDITORS = {"code": "VS Code", "visual studio code": "VS Code", "cursor": "Cursor", "pycharm": "PyCharm", "xcode": "Xcode",
           "sublime text": "Sublime Text", "zed": "Zed", "textedit": "TextEdit", "idle": "IDLE", "jupyterlab": "JupyterLab"}


def step_file(step: dict, last: dict | None = None) -> str:
    """The file this step is about: the diagnosis's diff, the step's target, a file check, else a
    file name mentioned in the step's own instructions/title ("Save it as calculator.py")."""
    if (last or {}).get("diff", {}).get("file"):
        return last["diff"]["file"]
    for t in step.get("targets") or []:
        if t.get("file"):
            return t["file"]
    for c in step.get("checks") or []:
        if c.get("file"):
            return c["file"]
    m = FILE_NAME.search(f"{step.get('instructions', '')} {step.get('title', '')}")
    return m.group(1) if m else ""


CREATE_WORDS = re.compile(r"\b(create|make|new file|save (?:it )?as|add a file)\b", re.IGNORECASE)


def lesson_mode(step: dict) -> bool:
    """A "Just teach me" text lesson step: it carries the exact `code` / `run_command`, no video."""
    lesson = (get_lesson() or {}).get("lesson") or {}
    return lesson.get("mode") == "lesson" or (("code" in step or "run_command" in step) and not step.get("video"))


def first_code_line(step: dict, max_chars: int = 40) -> str:
    line = next((ln.strip() for ln in (step.get("code") or "").splitlines() if ln.strip() and not ln.strip().startswith("#")), "")
    line = line.split(";")[0].strip()
    return line if len(line) <= max_chars else line[: max_chars - 1].rstrip() + "…"


def code_question(step: dict) -> str | None:
    """A question about the step's code, never a quoted check label ("Which line of calculator.py defines add?")."""
    f = (step.get("file") or step_file(step) or "").rsplit("/", 1)[-1]
    m = re.search(r"\b(?:def|class|function|const|let|var)\s+(\w+)", step.get("code") or "")
    if f and m:
        return f"Which line of {f} defines {m.group(1)}, and is it there yet?"
    if cmd := (step.get("run_command") or "").strip():
        return f"What does `{cmd}` print right now?"
    return None


def creates_file(step: dict, name: str) -> bool:
    """Does this step ask the learner to create `name` (vs. edit an existing file)?"""
    if any(c.get("type") == "file_exists" and (c.get("file") or "").endswith(name) for c in step.get("checks") or []):
        return True
    text = f"{step.get('title', '')}. {step.get('instructions', '')}"
    return bool(name) and name in text and bool(CREATE_WORDS.search(text))


def start_instruction(step: dict, screen: Any = None) -> str:
    """ONE short action to START this step (S9: <=12 words, the file + VS Code, never the raw instructions).
    Lesson mode: built from the step's own `code` / `run_command`:
      "In VS Code, type `def add(a, b):` in calculator.py."  /  "Run `python3 calculator.py` in the VS Code terminal."
    Video lessons: "Create calculator.py in the lesson folder, then print a welcome message…" (Michael)."""
    ed = editor_state(screen)
    name = (step.get("file") or step_file(step) or "").rsplit("/", 1)[-1]
    if lesson_mode(step):
        if ed and name and (ed.get("untitled") or (ed.get("unsaved") and ed.get("file") == name)):
            return where_hint(step, None, screen) + "."
        if line := first_code_line(step):
            return f"In VS Code, type `{line}` in {name}." if name and name != "(terminal)" else f"In VS Code, type `{line}`."
        if cmd := (step.get("run_command") or "").strip():
            return f"Run `{cmd}` in the VS Code terminal."
    instr = re.sub(r"\s+", " ", step.get("instructions") or step.get("title") or "").strip()
    sentences = [x for x in re.split(r"(?<=[.!?])\s+", instr) if x]
    if not (name and creates_file(step, name)):
        return " ".join(sentences[:1]) or "Start this step"
    first = where_hint(step, None, screen).rstrip(".")
    rest = ""
    for sent in sentences:
        if name in sent:  # the creation sentence: keep only what comes after "and"/"then"
            m = re.search(r"\b(?:and|then)\b\s*(.+)$", sent)
            rest = m.group(1) if m else ""
        else:
            rest = rest or sent
        if rest:
            break
    rest = rest.rstrip(".")
    return f"{first}, then {rest[:1].lower() + rest[1:]}." if rest else f"{first}."


def step_command(step: dict) -> str:
    return next((c.get("command", "") for c in step.get("checks") or [] if c.get("command")), "")


def editor_state(screen: Any) -> dict:
    """What the screen says about the editor: {app, file, unsaved, untitled} (empty dict if no editor).

    Reads window titles (E6 `windows[].title`), title boxes and the first lines of each app's text:
    VS Code shows `Untitled-1 — Visual Studio Code`, `● calc.py — project` (● = unsaved changes)."""
    if screen is None:
        return {}
    rows: list[tuple[str, str]] = []  # (app, text)
    for w in getattr(screen, "windows", None) or []:
        rows.append((getattr(w, "app", "") or "", getattr(w, "title", "") or ""))
    if hasattr(screen, "boxes"):
        rows += [(b.app, b.text) for b in screen.boxes if b.role in ("AXTitle", "AXWindow") or UNTITLED.search(b.text)]
        rows += [(b.app, b.text) for b in screen.boxes[:40]]
    elif hasattr(screen, "lines_by_app"):
        rows += [(a, ln) for a, ls in screen.lines_by_app().items() for ln in ls[:5]]
    elif isinstance(screen, dict):
        rows += [(str(a), str(ln)) for a, ls in screen.items() if isinstance(ls, list) for ln in ls[:5]]
    focused = (getattr(screen, "app", "") or "").lower()
    editors = [(a, t) for a, t in rows if a.lower() in EDITORS]
    if not editors:
        return {}
    editors.sort(key=lambda r: r[0].lower() != focused)  # the focused editor first
    app = editors[0][0]
    texts = [t for a, t in editors if a == app]
    untitled = next((m.group(0) for t in texts if (m := UNTITLED.search(t))), "")
    file = next((m.group(1) for t in texts if (m := FILE_NAME.search(t))), "")
    return {"app": EDITORS[app.lower()], "file": "" if untitled else file, "untitled": untitled,
            "unsaved": bool(untitled) or any(t.lstrip().startswith("●") for t in texts)}


def where_hint(step: dict, last: dict | None = None, screen: Any = None) -> str:
    """Where to go when the place is not on screen. Reads the screen when given: names the actual
    editor and what it shows (Michael: VS Code on Untitled-1 got "open the lesson file in your editor")."""
    f = step_file(step, last)
    name = f.rsplit("/", 1)[-1] if f else ""
    ed = editor_state(screen)
    if ed and name:
        if ed["untitled"]:
            return f"You're in {ed['app']} on an unsaved file. Save it as {name} in the lesson folder"
        if ed["file"] and ed["file"] != name:
            return f"You're in {ed['app']} on {ed['file']}. Open {name} from the lesson folder"
        if ed["file"] == name and ed["unsaved"]:
            return f"{name} is open in {ed['app']} with unsaved changes. Save it"
    if name and lesson_mode(step) and name != "(terminal)":  # lesson mode created the file already (S9)
        return f"Open {name} in VS Code"
    if name and creates_file(step, name):
        return f"Create {name} in the lesson folder" + (f" ({ed['app']} is open)" if ed and not ed["file"] else "")
    if f.endswith(".ipynb"):
        return f"Open {f} in Jupyter or Colab"
    if f:
        return f"Open {f} in {ed['app']}" if ed else f"Open {f} in your editor"
    if cmd := step_command(step):
        return f"Switch to your terminal and run `{cmd}`"
    return "Open the code for this step"


def deterministic_targets(step: dict, screen: ScreenContext, last: dict | None = None) -> list[dict]:
    """Exact matches only: the diagnosed line, then the step's target patterns."""
    boxes = screen.boxes
    want: list[tuple[str, str]] = []  # (kind, needle)
    if line := _first_line(((last or {}).get("diff") or {}).get("yours", "")):
        want.append(("text", line))
    for t in step.get("targets") or []:
        if t.get("match"):
            want.append(("re", t["match"]))
    for kind, needle in want:
        if kind == "text":
            n = _norm(needle)
            hits = [b for b in boxes if n and (n in _norm(b.text) or (len(_norm(b.text)) > 8 and _norm(b.text) in n))]
        else:
            try:
                rx = re.compile(needle)
                # whole-word first: "def loss" must find `def loss(`, not `def lossPDE(`
                strict = re.compile(needle + r"(?!\w)") if re.search(r"\w$", needle) else rx
                hits = [b for b in boxes if strict.search(b.text)] or [b for b in boxes if rx.search(b.text)]
            except re.error:
                hits = [b for b in boxes if _norm(needle) in _norm(b.text)]
        if hits:
            hits.sort(key=lambda b: (b.app.lower() not in ("code", "cursor", "pycharm"), len(b.text)))
            label = ((last or {}).get("title") or "") if kind == "text" else next((t.get("caption", "") for t in step.get("targets") or [] if t.get("match") == needle), "")
            return screen.resolve_targets([{"box_id": hits[0].id, "label": _short(label) or "here"}])
    return []


def code_visible(step: dict, screen: ScreenContext, code_excerpt: str = "", last: dict | None = None) -> bool:
    """Is the learner's code for this step on screen at all? (file name in a title, or a few code lines)."""
    f = step_file(step, last)
    name = f.rsplit("/", 1)[-1].lower() if f else ""
    # a terminal line like `$ python train.py` mentions the file but is not the code
    texts = [_norm(b.text) for b in screen.boxes if b.app.lower() not in TERMINALS]
    if name and any(name in t for t in texts):
        return True
    lines = [_norm(ln) for ln in (code_excerpt or "").splitlines() if len(ln.strip()) > 12]
    return sum(1 for ln in lines[:200] if ln in texts) >= 2


TERMINALS = {"terminal", "iterm2", "iterm", "warp", "alacritty", "kitty", "ghostty", "hyper"}


def _short(label: str, n: int = 3) -> str:
    return " ".join((label or "").replace(".", "").split()[:n])


async def point(
    step: dict,
    screen: ScreenContext | None,
    *,
    about: str,
    last: dict | None = None,
    use_model: bool = True,
    timeout: float = 3.0,
) -> dict:
    """Targets for `about` (what the coach is saying), or a `where` instruction. Never raises."""
    if screen is None or not screen.boxes:
        return {"targets": [], "where": where_hint(step, last, screen), "via": "no-screen"}
    if t := deterministic_targets(step, screen, last):
        return {"targets": t, "where": None, "via": "exact"}
    if not use_model:
        return {"targets": [], "where": where_hint(step, last, screen), "via": "none"}
    user = (
        f"STEP: {step.get('title', '')}: {step.get('instructions', '')}\n"
        f"FILE: {step_file(step, last) or 'unknown'}\n"
        f"POINT AT: {about}\n\n{screen.cursor_line()}\nBOXES (id source app @(x,y,w x h) text):\n{screen.box_list()}"
    )
    try:
        res = await asyncio.wait_for(
            llm.structured_call(
                purpose="point", model=llm.model_for("point"), system=llm.cached_system(POINT_SYSTEM),
                user_text=user, schema=POINT_SCHEMA, effort="low", max_tokens=1000, timeout=timeout,
                thinking={"type": "disabled"},
            ),
            timeout,
        )
    except (llm.CoachLLMError, TimeoutError) as e:
        log.info("point: model unavailable (%s); where-only", e)
        return {"targets": [], "where": where_hint(step, last, screen), "via": "fallback"}
    targets = screen.resolve_targets([{"box_id": i, "label": _short(about)} for i in res.data.get("box_ids", [])[:3]])
    if targets:
        where = None
    else:  # the screen-derived instruction (names the real editor + file) beats Haiku's generic one
        det = where_hint(step, last, screen)
        where = det if editor_state(screen) and step_file(step, last) else ((res.data.get("where") or "").strip() or det)
    return {"targets": targets, "where": where, "via": "haiku"}


async def show_me(step: dict, screen: ScreenContext | None = None, last_offtrack: dict | None = None) -> dict:
    """"Where do I work now?" → {"targets", "caption", "where"} (first target in ~0 ms when exact, ~1 s via Haiku)."""
    from .diagnose import LAST  # late import: diagnose imports this module's users

    last = last_offtrack or LAST.get(step.get("id", "")) or {}
    about = (last.get("title") and f"the code to change: {last['title']}") or f"where to work on this step: {step.get('instructions', '')}"
    p = await point(step, screen, about=about, last=last)
    caption = next((t.get("caption") for t in step.get("targets") or [] if t.get("caption")), "") or (_short(last.get("title", ""), 6) if last else "") or _short(step.get("title", ""), 6)
    return {"stepId": step.get("id"), "targets": p["targets"], "caption": caption or "Work here", "where": p["where"], "_meta": {"via": p["via"]}}

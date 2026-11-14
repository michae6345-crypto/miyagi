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

from . import llm
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


def step_file(step: dict, last: dict | None = None) -> str:
    """The file this step is about: the diagnosis's diff, the step's target, or a file check."""
    if (last or {}).get("diff", {}).get("file"):
        return last["diff"]["file"]
    for t in step.get("targets") or []:
        if t.get("file"):
            return t["file"]
    for c in step.get("checks") or []:
        if c.get("file"):
            return c["file"]
    return ""


def step_command(step: dict) -> str:
    return next((c.get("command", "") for c in step.get("checks") or [] if c.get("command")), "")


def where_hint(step: dict, last: dict | None = None) -> str:
    """Where to go when the place is not on screen. Honest and specific, no model."""
    f = step_file(step, last)
    if f.endswith(".ipynb"):
        return f"Open {f} in Jupyter or Colab"
    if f:
        return f"Open {f} in your editor"
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
        return {"targets": [], "where": where_hint(step, last), "via": "no-screen"}
    if t := deterministic_targets(step, screen, last):
        return {"targets": t, "where": None, "via": "exact"}
    if not use_model:
        return {"targets": [], "where": where_hint(step, last), "via": "none"}
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
        return {"targets": [], "where": where_hint(step, last), "via": "fallback"}
    targets = screen.resolve_targets([{"box_id": i, "label": _short(about)} for i in res.data.get("box_ids", [])[:3]])
    where = None if targets else ((res.data.get("where") or "").strip() or where_hint(step, last))
    return {"targets": targets, "where": where, "via": "haiku"}


async def show_me(step: dict, screen: ScreenContext | None = None, last_offtrack: dict | None = None) -> dict:
    """"Where do I work now?" → {"targets", "caption", "where"} (first target in ~0 ms when exact, ~1 s via Haiku)."""
    from .diagnose import LAST  # late import: diagnose imports this module's users

    last = last_offtrack or LAST.get(step.get("id", "")) or {}
    about = (last.get("title") and f"the code to change: {last['title']}") or f"where to work on this step: {step.get('instructions', '')}"
    p = await point(step, screen, about=about, last=last)
    caption = next((t.get("caption") for t in step.get("targets") or [] if t.get("caption")), "") or (_short(last.get("title", ""), 6) if last else "") or _short(step.get("title", ""), 6)
    return {"stepId": step.get("id"), "targets": p["targets"], "caption": caption or "Work here", "where": p["where"], "_meta": {"via": p["via"]}}

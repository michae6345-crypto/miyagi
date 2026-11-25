"""How do I (AMBIENT-HELP.md section 3): 1 to HELP_STEPS_MAX short steps for "how do I X" in the frontmost app, each
with a place for bon to point at when the app's accessibility tree has it.

    controls = read_controls("Blender")                     # local: AX labels + rects, never a screenshot
    plan = await plan_steps(question, "Blender", controls)  # ONE Haiku call (coach client, guarded, via miyagi-cloud)
    steps = resolve(plan, controls)                         # targets found on this Mac (via "ax")
    advanced = progress(steps, current, before, after)      # watching: no model call

What leaves the Mac: the question, the app's name, the window title and the labels of its controls (menu paths,
button titles), redacted (server.redact via the coach client, home folder shortened). Never a screenshot, a value
typed into a field, or a document's text.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from server.untrusted import EXTRACT_RULE, flag_injection, wrap

from .controls import Control, Controls

log = logging.getLogger("server.ambient")

try:
    from shared.contracts.events import HELP_STEPS_MAX
except Exception:  # noqa: BLE001
    HELP_STEPS_MAX = 5

PURPOSE = "ambient_help"  # server/models.py "coach.ambient_help": Haiku
TEXT_WORDS = 12
DETAIL_WORDS = 25
GOAL_WORDS = 8
LABEL_WORDS = 4
MAX_TOKENS = 1200
TIMEOUT_S = 25.0

SCHEMA = {
    "type": "object",
    "properties": {
        "goal": {"type": "string"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "detail": {"type": "string"},
                    "control": {"type": "string"},
                    "advance": {"type": "string", "enum": ["click", "screen", "next"]},
                },
                "required": ["text", "detail", "control", "advance"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["goal", "steps"],
    "additionalProperties": False,
}

SYSTEM = f"""You help someone do one thing in a Mac app they have open, outside any lesson. Answer with 1 to {HELP_STEPS_MAX}
short steps, in order, that get them there from where they are now.

- goal: the question as a short title, at most {GOAL_WORDS} words ("Export as STL").
- Each step: text = ONE action, at most {TEXT_WORDS} words, plain and calm ("Click File in the top bar").
  detail = an optional hint, at most {DETAIL_WORDS} words, or "".
- control: the exact label of the control the step uses, copied from the list of controls you are given (a menu
  item's own label, not its whole path). "" when the step uses no listed control (typing, a keyboard shortcut, a control
  the list does not show).
- advance: "click" when the step is done by clicking that control, "screen" when it opens a menu, sheet or window,
  "next" when only the person can tell it is done (typing a name, choosing a folder).
- Use the app's real menus and buttons. Prefer the listed labels. Never invent a control that is not there when the
  list shows the app's menus. If the app cannot do it, one step that says so kindly.
- No dashes in the text. No greetings. Never ask for passwords or keys.

{EXTRACT_RULE}"""


def _words(text: Any, n: int) -> str:
    w = re.sub(r"\s+", " ", str(text or "")).strip().split(" ")
    out = " ".join(w[:n]).strip()
    return out.replace(" — ", ", ").replace("—", ", ")


def _home(text: str) -> str:
    from pathlib import Path

    home = str(Path.home())
    return text.replace(home, "~") if home and home != "/" else text


def controls_text(c: Controls | None, limit: int = 220) -> str:
    """The controls as prompt lines: "menu: File > Export > Stl (.stl)" / "button: Export STL (on screen)"."""
    if c is None or not c.items:
        return "(the app's controls could not be read)"
    lines = []
    for item in c.items[:limit]:
        role = item.role.removeprefix("AX").lower()
        name = item.path or item.label
        lines.append(f"{role}: {name}{' (on screen)' if item.rect else ''}")
    return _home("\n".join(lines))


def prompt(question: str, app: str, c: Controls | None) -> str:
    window = _home(c.window) if c and c.window else ""
    return (f"App: {app}\n" + (f"Window: {window}\n" if window else "")
            + "Controls (from the app's accessibility tree):\n"
            + wrap("screen", controls_text(c), cap=12_000) + "\n\n"
            + "Question:\n" + wrap("learner", question, cap=600))


async def plan_steps(question: str, app: str, c: Controls | None, *, call=None) -> dict:
    """The model's {goal, steps: [{text, detail, control, advance}]}. `call`: structured_call (tests mock it).
    Raises llm.CoachLLMError."""
    from server.coach import llm

    call = call or llm.structured_call_retrying
    user = prompt(question, app, c)
    res = await call(purpose=PURPOSE, model=llm.model_for(PURPOSE), system=llm.cached_system(SYSTEM), user_text=user,
                     schema=SCHEMA, effort="low", max_tokens=MAX_TOKENS, timeout=TIMEOUT_S,
                     thinking={"type": "disabled"})
    return res.data if isinstance(res.data, dict) else {}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def find_control(label: str, c: Controls | None) -> Control | None:
    """The control a step names: an exact label (case and punctuation aside), else one whose label starts with it or
    holds it as words. On-screen controls first. None when nothing fits (no guessing from a single letter)."""
    want = _norm(label)
    if not want or c is None or len(want) < 2:
        return None
    ranked = sorted(c.items, key=lambda it: it.rect is None)
    for test in (lambda n: n == want, lambda n: n.startswith(want + " "), lambda n: f" {want} " in f" {n} "):
        for it in ranked:
            if test(_norm(it.label)):
                return it
    return None


def target_of(ctrl: Control | None, app: str, label: str = "") -> dict | None:
    if ctrl is None or ctrl.rect is None:
        return None
    x, y, w, h = ctrl.rect
    return {"x": round(x, 1), "y": round(y, 1), "w": round(w, 1), "h": round(h, 1),
            "label": _words(label or ctrl.label, LABEL_WORDS), "app": app, "via": "ax"}


def resolve(plan: dict, c: Controls | None, app: str) -> tuple[str, list[dict]]:
    """(goal, steps) in the contract's HelpStep shape plus `_control` (the label to find again while watching)."""
    goal = _words(plan.get("goal"), GOAL_WORDS)
    if flag_injection(goal):
        goal = ""
    steps: list[dict] = []
    for i, raw in enumerate((plan.get("steps") or [])[:HELP_STEPS_MAX]):
        if not isinstance(raw, dict):
            continue
        text = _words(raw.get("text"), TEXT_WORDS)
        if not text or flag_injection(text):
            continue
        detail = _words(raw.get("detail"), DETAIL_WORDS)
        control = str(raw.get("control") or "")[:80]
        advance = raw.get("advance") if raw.get("advance") in ("click", "screen", "next") else "next"
        if not control:
            advance = "next" if advance == "click" else advance
        step = {"id": f"h{i + 1}", "text": text, "advance": advance, "_control": control}
        if detail and not flag_injection(detail):
            step["detail"] = detail
        if t := target_of(find_control(control, c), app, control):
            step["target"] = t
        steps.append(step)
    return goal, steps


def retarget(steps: list[dict], c: Controls | None, app: str) -> bool:
    """Fill in / move each step's target from a fresh read (a menu opened, the window moved). True when one changed."""
    changed = False
    for st in steps:
        t = target_of(find_control(st.get("_control") or "", c), app, st.get("_control") or "")
        if t is None and st.get("target") is not None and c is not None and st.get("_control"):
            # its control is gone from the screen (a menu closed): no stale box for bon
            st.pop("target", None)
            changed = True
        elif t is not None and t != st.get("target"):
            st["target"] = t
            changed = True
    return changed


def visible(label: str, c: Controls | None) -> bool:
    ctrl = find_control(label, c)
    return ctrl is not None and ctrl.rect is not None


def progress(steps: list[dict], current: int, before: Controls | None, after: Controls | None) -> int:
    """The step to do now after the screen went from `before` to `after` (no model call). A "click" / "screen" step is
    done when the screen changed and either the next step's control is now on screen or this step's control is gone
    (the menu it opened closed, the dialog it confirmed went away). "next" steps wait for the learner's Next.
    One step per change. Returns len(steps) when the last one is done."""
    if before is None or after is None or before.signature() == after.signature() or current >= len(steps):
        return current
    st = steps[current]
    if st.get("advance") == "next":
        return current
    nxt = steps[current + 1] if current + 1 < len(steps) else None
    now_here = bool(nxt and nxt.get("_control")) and visible(nxt["_control"], after) \
        and not visible(nxt["_control"], before)
    gone = bool(st.get("_control")) and visible(st["_control"], before) and not visible(st["_control"], after)
    return current + 1 if now_here or gone else current


def public(steps: list[dict]) -> list[dict]:
    """The contract's HelpStep dicts (internal keys dropped)."""
    return [{k: v for k, v in st.items() if not k.startswith("_")} for st in steps]

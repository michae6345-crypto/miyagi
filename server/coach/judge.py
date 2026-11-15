"""Claude step judge: when deterministic checks can't tell, look at the screen and say whether the
learner already did the step (Michael: the calculator lesson sat on "0 of 1 pass" for minutes while
he was clearly past it).

    judge = coach.StepJudge()                                # one per session
    if judge.should_judge(step, check_results, idle_s=idle, video_playing=playing,
                          screen=obs_or_text, files=files):
        j = await judge.judge(step, check_results, screen=obs_or_text, files=files, focused_app=app)
        for ev in j["events"]: emit(ev["type"], ev["payload"])   # check.updated status "pass"
        if j["card"]: emit("card", j["card"])                     # "Looks done?" / "Not yet" / "Already ahead?"
        if j["card"] and <it was shown>: judge.card_shown(step["id"], j["card"])

Gate: some check not passed, the learner idle >= 8 s, the video not playing, at most one judgment per
20 s per step, and only when the screen text or the files changed since the last one.
Cards are step-status cards (`source: "judge"`, kind "step"), never answers. "Looks done?" only when Claude
sees the WHOLE step done (`verdict: "done"`); a check-level disagreement on an unfinished step is "Not yet"
(`verdict: "not_done"`, Hint / Show me). A card the learner already saw is not offered again for that step
until the files change.
Haiku only (`llm.model_for("judge")`); never raises (None on any failure).
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from typing import Any

from . import llm, scene
from .common import clamp_words, get_lesson
from .diagnose import notebook_code
from .gate import PeriodicGate, files_signature
from .pointing import deterministic_targets, editor_state, step_file, where_hint

log = logging.getLogger("coach.judge")

PASS_CONFIDENCE = 0.8  # Claude may pass a check the machine can't evaluate
LOOKS_DONE_CONFIDENCE = 0.6  # Claude thinks it's done but a deterministic check disagrees → ask
MAX_SCREEN_CHARS = 6000
MAX_FILE_CHARS = 3000

JUDGE_SYSTEM = """You judge whether a learner has completed a step of a tutorial, from what is on their screen right now (OCR / accessibility text, grouped by app) and their workspace files. You answer per check.
- verdict "done" only with direct evidence on screen or in the files (the code is written, the command ran with the expected output, the window/tool is open); "not_done" when the evidence shows it is missing or wrong; "cant_tell" when the screen doesn't show the relevant place.
- Setup / install steps (install Python, VS Code, a package, create a folder or file) are done when the tool is visibly open or installed (e.g. a VS Code window, `python --version` / `pip show` output, the folder in a file tree).
- confidence: 0..1, how sure you are of the verdict. evidence: the exact on-screen text or file line you relied on (short). reason: one line.
- on_step_id: if the screen clearly shows the learner working on ANOTHER step of this lesson (e.g. already writing functions while the lesson is still on setup), that step's id; else "".
- summary: at most 12 words, what you saw that matters ("calc.py defines add() and subtract(); tests pass").
- missing: at most 12 words, what is still left to do for this step, using the real app and file names from the screen (e.g. "Save the Untitled-1 tab as calculator.py"); "" if nothing. The learner reads it word for word: never mention OCR, the screen text, how anything is read or checked; never ask to add or type code that WORKSPACE FILES already contain (a run step whose code is in the file: say what to run); if the terminal output can't be read, say "Make the terminal panel taller, then run it again"."""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "checks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "check_id": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["done", "not_done", "cant_tell"]},
                    "confidence": {"type": "number"},
                    "reason": {"type": "string"},
                    "evidence": {"type": "string"},
                },
                "required": ["check_id", "verdict", "confidence", "reason", "evidence"],
                "additionalProperties": False,
            },
        },
        "on_step_id": {"type": "string"},
        "summary": {"type": "string"},
        "missing": {"type": "string"},
    },
    "required": ["checks", "on_step_id", "summary", "missing"],
    "additionalProperties": False,
}


# ---------- inputs ----------------------------------------------------------------------------------

def screen_text(screen: Any, focused_app: str = "") -> str:
    """E6 observation / ScreenContext / {app: [lines]} / plain text → 'APP: <name>' blocks, focused app first."""
    if screen is None:
        return ""
    if isinstance(screen, str):
        return screen[-MAX_SCREEN_CHARS:]
    by_app: dict[str, list[str]] = {}
    if isinstance(screen, dict) and all(isinstance(v, list) for v in screen.values()):
        by_app = {str(k): [str(x) for x in v] for k, v in screen.items()}
    elif hasattr(screen, "lines_by_app"):
        by_app = screen.lines_by_app()
    elif hasattr(screen, "boxes"):  # ScreenContext
        for b in sorted(screen.boxes, key=lambda b: (b.y, b.x)):
            by_app.setdefault(b.app or "screen", []).append(b.text)
    focused = focused_app or getattr(screen, "app", "") or ""
    order = sorted(by_app, key=lambda a: (a.lower() != focused.lower(), a))
    text = "\n\n".join(f"APP: {a}{' (focused)' if a.lower() == focused.lower() else ''}\n" + "\n".join(by_app[a]) for a in order)
    return text[:MAX_SCREEN_CHARS]


def files_text(files: dict[str, str] | None) -> str:
    parts = []
    for path, text in list((files or {}).items())[:3]:
        body = notebook_code(text or "")
        parts.append(f"FILE {path}:\n{body[:MAX_FILE_CHARS]}" + ("\n…(truncated)" if len(body) > MAX_FILE_CHARS else ""))
    return "\n\n".join(parts)


# ---------- the judge -----------------------------------------------------------------------------------

EXACT_FILES = ("VS Code's exact editor text, unsaved edits included: judge the code from these only, never from "
               "SCREEN NOW, whose OCR misreads code (e.g. numpy as numey)")


async def _ask(step: dict, check_results: list[dict] | None, screen: Any, files: dict[str, str] | None,
               focused_app: str, lesson: dict | None, active_file: dict | None = None, exact_files: bool = False):
    """One Haiku judgment → (data, result, checks, status_by_id, steps), or None when unavailable. exact_files: the
    files are the editor's own text (the VS Code companion's buffer), so OCR never decides whether code is right."""
    sid = step.get("id", "")
    scr, fil = screen_text(screen, focused_app), files_text(files)
    lesson = lesson if lesson is not None else get_lesson()
    status = {r.get("checkId"): r for r in check_results or []}
    checks = [c for c in step.get("checks") or [] if c.get("id")]
    steps = [s for s in (lesson or {}).get("steps") or [] if s.get("id")]
    ed, expected = editor_state(screen, active_file), step_file(step)
    editor = (f"{ed['app']} showing " + (f"an unsaved {ed['untitled']}" if ed["untitled"] else (ed["file"] or "an unknown file"))
              + (" (unsaved changes)" if ed["unsaved"] and not ed["untitled"] else "")) if ed else ""
    user = "\n\n".join(x for x in [
        f"CURRENT STEP ({sid}): {step.get('title', '')}\n{step.get('instructions', '')}",
        "CHECKS (id: label [machine status]):\n" + "\n".join(
            f"- {c['id']}: {c.get('label', '')} [{status.get(c['id'], {}).get('status', 'pending')}]" for c in checks),
        f"EXPECTED FILE: {expected}" if expected else "",
        f"EDITOR (from the editor window, not OCR): {editor}" if editor else "EDITOR: unknown; don't claim which file is open",
        "OTHER STEPS OF THIS LESSON:\n" + "\n".join(f"- {s['id']}: {s.get('title', '')}" for s in steps if s["id"] != sid) if len(steps) > 1 else "",
        f"SCREEN NOW:\n{scr}" if scr else "SCREEN NOW: (not available)",
        scene.prompt_line(sid),  # a Haiku glance < 8 s old (orchestrator/scene_watch.py): context, never evidence
        (f"WORKSPACE FILES ({EXACT_FILES}):\n{fil}" if exact_files else f"WORKSPACE FILES:\n{fil}") if fil else "",
        "Judge each check.",
    ] if x)
    try:
        res = await llm.structured_call(
            purpose="judge", model=llm.model_for("judge"), system=llm.cached_system(JUDGE_SYSTEM),
            user_text=user, schema=JUDGE_SCHEMA, effort="low", max_tokens=2000, timeout=15.0,
        )
    except llm.CoachLLMError as e:
        log.info("judge: unavailable (%s)", e)
        return None
    log.info("judge %s %s %.2fs usage=%s", sid, res.model, res.latency_s, res.usage)
    return res.data, res, checks, status, steps


def _file_blocker(step: dict, check: dict, files: dict[str, str] | None, screen: Any) -> str | None:
    """Why Claude may NOT pass a check about a file: "unsaved" | "not seen" | "empty", or None.
    Michael: step 1 showed as passed while calculator.py was unsaved (and in another folder)."""
    name = (check.get("file") or "").rsplit("/", 1)[-1]
    if not name:
        expected = (step_file(step) or "").rsplit("/", 1)[-1]
        name = expected if expected and expected in (check.get("label") or "") else ""
    if not name:
        return None
    ed = editor_state(screen) if screen is not None else {}
    if ed and ed.get("unsaved") and (ed.get("untitled") or ed.get("file") == name):
        return "unsaved"
    text = next((t for p, t in (files or {}).items() if p == name or p.rsplit("/", 1)[-1] == name), None)
    if text is None:
        return "not seen"
    return "empty" if not text.strip() else None


SAVE_FIRST = "Save with ⌘S so I can check it"


def _meta(res: llm.CallResult) -> dict:
    return {"model": res.model, "latency_s": round(res.latency_s, 2), "usage": res.usage}


def _box_for(screen: Any, text: str) -> dict | None:
    """The on-screen box showing `text` (evidence), as {text, rect}, when the screen has boxes."""
    n = re.sub(r"\s+", " ", text or "").strip().lower()
    if not n or not hasattr(screen, "boxes"):
        return None
    for b in screen.boxes:
        t = re.sub(r"\s+", " ", b.text).strip().lower()
        if n in t or (len(t) > 8 and t in n):
            return {"text": b.text, "rect": b.rect()}
    return None


async def judge_step(step: dict, screen: Any = None, files: dict[str, str] | None = None, *,
                     check_results: list[dict] | None = None, focused_app: str = "", lesson: dict | None = None,
                     active_file: dict | None = None, exact_files: bool = False) -> dict | None:
    """The "Check" button (action check_step): judge now, no idle/rate gates (the learner asked).

    → {"checks": {id: {"verdict": "done"|"not_done"|"unsure", "reason", "evidence"}}, "done": bool,
       "missing": "<=12 words", "where": str | None, "target": {"text", "rect"} | None, "_meta"}
    `done` = every check passed by the machine or judged done by Claude (confidence >= 0.6).
    None only when the model is unavailable.
    """
    if llm.offline_mode():
        return _offline_judgment(step, check_results, screen)
    asked = await _ask(step, check_results, screen, files, focused_app, lesson, active_file, exact_files)
    if asked is None:
        return None
    data, res, checks, status, _steps = asked
    by_id = {c["id"] for c in checks}
    check_by_id = {c["id"]: c for c in checks}
    out: dict[str, dict] = {}
    blocked: set[str] = set()
    for v in data.get("checks") or []:
        if v.get("check_id") in by_id:
            verdict = {"done": "done", "not_done": "not_done"}.get(v.get("verdict"), "unsure")
            reason = v.get("reason", "")
            if verdict == "done" and float(v.get("confidence") or 0) < LOOKS_DONE_CONFIDENCE:
                verdict = "unsure"
            if verdict == "done" and status.get(v["check_id"], {}).get("status") != "pass" and (
                    why := _file_blocker(step, check_by_id[v["check_id"]], files, screen)):
                verdict, reason = "unsure", f"the file is {why}, so I can't confirm it"
                blocked.add(why)
            out[v["check_id"]] = {"verdict": verdict, "reason": reason, "evidence": v.get("evidence", "")}
    for cid in by_id - out.keys():
        out[cid] = {"verdict": "unsure", "reason": "not judged", "evidence": ""}
    done = bool(checks) and all(status.get(c["id"], {}).get("status") == "pass" or out[c["id"]]["verdict"] == "done" for c in checks)
    missing = "" if done else clamp_words(data.get("missing") or next((o["reason"] for o in out.values() if o["verdict"] != "done"), ""), 12).rstrip(".")
    where = None
    if not done and (editor_state(screen) or step_file(step)):
        where = where_hint(step, None, screen)
    if "unsaved" in blocked:
        missing = where = SAVE_FIRST
    target = None
    if hasattr(screen, "boxes"):
        ev = next((o["evidence"] for o in out.values() if o["evidence"] and (o["verdict"] == "done") == done), "")
        target = _box_for(screen, ev)
        if target is None and not done and (t := deterministic_targets(step, screen)):
            target = {"text": t[0]["text"], "rect": t[0]["rect"]}
    return {"checks": out, "done": done, "missing": missing, "where": where, "target": target, "_meta": _meta(res)}



def _offline_judgment(step: dict, check_results: list[dict] | None, screen: Any) -> dict:
    """The Check button in DEMO / stubbed mode: no model; machine-passed checks are done, the rest
    'unsure'. `done` only if every check already passed."""
    status = {r.get("checkId"): r.get("status") for r in check_results or []}
    checks = [c for c in step.get("checks") or [] if c.get("id")]
    out = {c["id"]: ({"verdict": "done", "reason": "the check passed", "evidence": ""} if status.get(c["id"]) == "pass"
                     else {"verdict": "unsure", "reason": "offline: Claude didn't look", "evidence": ""}) for c in checks}
    done = bool(checks) and all(v["verdict"] == "done" for v in out.values())
    where = None if done or not (editor_state(screen) or step_file(step)) else where_hint(step, None, screen)
    return {"checks": out, "done": done, "missing": "", "where": where, "target": None, "offline": True, "_meta": {"model": None}}


class StepJudge:
    """Periodic judge with the cost gate (gate.PeriodicGate): changed screen/files only, never while
    the reader is down or the display sleeps, 20 s → 5 min backoff on repeat verdicts, stop after 3."""

    def __init__(self, *, min_interval_s: float = 20.0, idle_s: float = 8.0, cap_s: float = 300.0, stop_after: int = 3,
                 clock: Callable[[], float] = time.monotonic):
        self.idle_s, self.clock = idle_s, clock
        self.gate = PeriodicGate(base_s=min_interval_s, cap_s=cap_s, stop_after=stop_after, clock=clock)
        self._files: dict[str, str] = {}  # step id -> files signature at its last judgment
        self._shown: dict[str, tuple] = {}  # step id -> (card key, files signature) of the last card the learner saw

    def should_judge(self, step: dict, check_results: list[dict], *, idle_s: float, video_playing: bool,
                     screen: Any = None, files: dict[str, str] | None = None, focused_app: str = "",
                     screen_ok: bool = True, display_asleep: bool = False, file_mtimes: dict[str, Any] | None = None) -> bool:
        """`file_mtimes` ({path: mtime}) is preferred over `files` for change detection. The screen is compared
        without the "(focused)" marker: switching apps over the same text is not a change."""
        if llm.offline_mode() or screen is None or video_playing or idle_s < self.idle_s:
            return False  # offline (DEMO): never; no screen = the reader is down
        if check_results and all(r.get("status") == "pass" for r in check_results):
            return False
        return self.gate.allow(step.get("id", ""), screen=screen_text(screen), files=file_mtimes or files,
                               screen_ok=screen_ok, asleep=display_asleep)

    async def judge(self, step: dict, check_results: list[dict], *, screen: Any = None, files: dict[str, str] | None = None,
                    focused_app: str = "", lesson: dict | None = None, file_mtimes: dict[str, Any] | None = None,
                    exact_files: bool = False) -> dict | None:
        """{"checks": [...], "events": [check.updated...], "card": {...} | None, "done", "summary", "_meta"}, or None.
        `done`: Claude sees the whole step done. `card` is None when it repeats the card the learner already saw
        for this step (card_shown) and no file changed since."""
        sid = step.get("id", "")
        fsig = files_signature(file_mtimes or files)
        self.gate.started(sid, screen=screen_text(screen), files=file_mtimes or files)
        asked = await _ask(step, check_results, screen, files, focused_app, lesson, exact_files=exact_files)
        if asked is None:
            return None
        data, res, checks, status, steps = asked
        out = self._decide(step, checks, status, steps, data, files, screen)
        # the backoff follows what Claude saw, never the card it led to: a card going up must not reset it to 20 s
        verdict = (tuple(sorted((v["check_id"], v["verdict"]) for v in out["checks"])), data.get("on_step_id", ""))
        self.gate.record(sid, verdict)
        self._files[sid] = fsig
        if out["card"] and self._shown.get(sid) == (_card_key(out["card"]), fsig):
            out = out | {"card": None}  # already shown for this step, nothing saved since: don't repeat it
        return out | {"_meta": _meta(res) | {"gate": self.gate.state(sid)}}

    def card_shown(self, step_id: str, card: dict) -> None:
        """The session showed `card`: the same card is not offered again for this step until the files change."""
        self._shown[step_id] = (_card_key(card), self._files.get(step_id, ""))

    def _decide(self, step: dict, checks: list[dict], status: dict, steps: list[dict], data: dict,
                files: dict[str, str] | None = None, screen: Any = None) -> dict:
        sid = step.get("id", "")
        by_id = {c["id"]: c for c in checks}
        verdicts = [v for v in data.get("checks") or [] if v.get("check_id") in by_id]  # unknown ids dropped
        summary = clamp_words(data.get("summary", ""), 12).rstrip(".")
        events, disagree, blocked, seen = [], [], set(), set()
        for v in verdicts:
            c, st = by_id[v["check_id"]], status.get(v["check_id"], {}).get("status", "pending")
            conf = float(v.get("confidence") or 0)
            if v["verdict"] != "done" or st == "pass":
                continue
            if why := _file_blocker(step, c, files, screen):  # never pass a file nobody has saved/seen
                blocked.add(why)
                continue
            if conf >= LOOKS_DONE_CONFIDENCE:
                seen.add(c["id"])
            if st == "fail":  # a deterministic check disagrees: ask, don't overrule it
                if conf >= LOOKS_DONE_CONFIDENCE:
                    disagree.append(v)
            elif conf >= PASS_CONFIDENCE:  # pending: the machine can't tell, Claude can
                saw = (v.get("evidence") or v.get("reason") or "").strip()
                events.append({"type": "check.updated", "payload": {
                    "stepId": sid, "checkId": c["id"], "label": c.get("label", ""), "status": "pass",
                    "detail": clamp_words(f"Claude saw it on screen: {saw}", 24)}})
        # the step's overall verdict: every check passed by the machine or seen done by Claude (as judge_step)
        done = bool(checks) and all(status.get(c["id"], {}).get("status") == "pass" or c["id"] in seen for c in checks)
        card = None
        other = next((s for s in steps if s["id"] == data.get("on_step_id") and s["id"] != sid), None)
        idx = {s["id"]: i for i, s in enumerate(steps)}
        # judge cards are step-status cards (source "judge", kind "step"), never answers: they don't take the answer slot.
        # No skip_step on them: the bar owns Skip (E9).
        if other is not None and idx.get(other["id"], -1) > idx.get(sid, -1):  # ahead of the lesson; behind → no card
            card = {"stepId": sid, "kind": "step", "source": "judge", "title": "Already ahead?",
                    "body": clamp_words(f"You look to be on “{other.get('title', other['id'])}” already", 12),
                    "actions": [], "targetStepId": other["id"]}
        elif "unsaved" in blocked:
            card = {"stepId": sid, "kind": "step", "source": "judge", "title": "Save so I can check",
                    "body": f"{SAVE_FIRST}.", "actions": []}
        elif disagree and done:  # "Looks done?" only when Claude sees the WHOLE step done; Yes vouches for these checks
            card = {"stepId": sid, "kind": "step", "source": "judge", "verdict": "done", "title": "Looks done?",
                    "body": summary or clamp_words(disagree[0].get("evidence") or disagree[0].get("reason", ""), 12),
                    "actions": ["confirm"], "checkIds": [c["id"] for c in checks if c["id"] in seen]}
        elif disagree:  # Claude sees part of it but the step isn't done: say what's left, never "Looks done?"
            left = [c["id"] for c in checks if c["id"] not in seen and status.get(c["id"], {}).get("status") != "pass"]
            why = (data.get("missing") or next((v.get("reason", "") for v in verdicts
                                                if v["check_id"] in left and v["verdict"] == "not_done"), "")
                   or f"Still missing: {by_id[left[0]].get('label') or left[0]}")
            card = {"stepId": sid, "kind": "step", "source": "judge", "verdict": "not_done", "title": "Not yet",
                    "body": clamp_words(why, 12).rstrip("."), "actions": ["hint", "show_me"], "checkIds": left}
        return {"checks": verdicts, "events": events, "card": card, "done": done, "summary": summary}


def _card_key(card: dict) -> tuple:
    """What makes two judge cards "the same card" for the learner: title + the checks it is about."""
    return card.get("title"), tuple(sorted(card.get("checkIds") or []))

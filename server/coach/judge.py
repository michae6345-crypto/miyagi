"""Claude step judge: when deterministic checks can't tell, look at the screen and say whether the
learner already did the step (Michael: the calculator lesson sat on "0 of 1 pass" for minutes while
he was clearly past it).

    judge = coach.StepJudge()                                # one per session
    if judge.should_judge(step, check_results, idle_s=idle, video_playing=playing,
                          screen=obs_or_text, files=files):
        j = await judge.judge(step, check_results, screen=obs_or_text, files=files, focused_app=app)
        for ev in j["events"]: emit(ev["type"], ev["payload"])   # check.updated status "pass"
        if j["card"]: emit("card", j["card"])                     # "Looks done?" / "Already ahead?"

Gate: some check not passed, the learner idle >= 8 s, the video not playing, at most one judgment per
20 s per step, and only when the screen text or the files changed since the last one.
Haiku only (`llm.model_for("judge")`); never raises (None on any failure).
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from typing import Any

from . import llm
from .common import clamp_words, get_lesson
from .diagnose import notebook_code

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
- summary: at most 12 words, what you saw that matters ("calc.py defines add() and subtract(); tests pass")."""

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
    },
    "required": ["checks", "on_step_id", "summary"],
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


def _sig(*parts: str) -> str:
    return hashlib.sha256("\x00".join(parts).encode()).hexdigest()[:16]


# ---------- the judge -----------------------------------------------------------------------------------

class StepJudge:
    def __init__(self, *, min_interval_s: float = 20.0, idle_s: float = 8.0, clock: Callable[[], float] = time.monotonic):
        self.min_interval_s, self.idle_s, self.clock = min_interval_s, idle_s, clock
        self._last_t: dict[str, float] = {}
        self._last_sig: dict[str, str] = {}

    def should_judge(self, step: dict, check_results: list[dict], *, idle_s: float, video_playing: bool,
                     screen: Any = None, files: dict[str, str] | None = None, focused_app: str = "") -> bool:
        sid = step.get("id", "")
        if video_playing or idle_s < self.idle_s:
            return False
        if check_results and all(r.get("status") == "pass" for r in check_results):
            return False
        last = self._last_t.get(sid)
        if last is not None and self.clock() - last < self.min_interval_s:
            return False
        sig = _sig(screen_text(screen, focused_app), files_text(files))
        return sig != self._last_sig.get(sid)

    async def judge(self, step: dict, check_results: list[dict], *, screen: Any = None, files: dict[str, str] | None = None,
                    focused_app: str = "", lesson: dict | None = None) -> dict | None:
        """{"checks": [...], "events": [check.updated...], "card": {...} | None, "summary", "_meta"}, or None."""
        sid = step.get("id", "")
        scr, fil = screen_text(screen, focused_app), files_text(files)
        self._last_t[sid] = self.clock()
        self._last_sig[sid] = _sig(scr, fil)
        lesson = lesson if lesson is not None else get_lesson()
        status = {r.get("checkId"): r for r in check_results or []}
        checks = [c for c in step.get("checks") or [] if c.get("id")]
        steps = [s for s in (lesson or {}).get("steps") or [] if s.get("id")]
        user = "\n\n".join(x for x in [
            f"CURRENT STEP ({sid}): {step.get('title', '')}\n{step.get('instructions', '')}",
            "CHECKS (id: label [machine status]):\n" + "\n".join(
                f"- {c['id']}: {c.get('label', '')} [{status.get(c['id'], {}).get('status', 'pending')}]" for c in checks),
            "OTHER STEPS OF THIS LESSON:\n" + "\n".join(f"- {s['id']}: {s.get('title', '')}" for s in steps if s["id"] != sid) if len(steps) > 1 else "",
            f"SCREEN NOW:\n{scr}" if scr else "SCREEN NOW: (not available)",
            f"WORKSPACE FILES:\n{fil}" if fil else "",
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
        return self._decide(step, checks, status, steps, res.data) | {"_meta": {"model": res.model, "latency_s": round(res.latency_s, 2), "usage": res.usage}}

    def _decide(self, step: dict, checks: list[dict], status: dict, steps: list[dict], data: dict) -> dict:
        sid = step.get("id", "")
        by_id = {c["id"]: c for c in checks}
        verdicts = [v for v in data.get("checks") or [] if v.get("check_id") in by_id]  # unknown ids dropped
        summary = clamp_words(data.get("summary", ""), 12).rstrip(".")
        events, disagree = [], []
        for v in verdicts:
            c, st = by_id[v["check_id"]], status.get(v["check_id"], {}).get("status", "pending")
            conf = float(v.get("confidence") or 0)
            if v["verdict"] != "done" or st == "pass":
                continue
            if st == "fail":  # a deterministic check disagrees: ask, don't overrule it
                if conf >= LOOKS_DONE_CONFIDENCE:
                    disagree.append(v)
            elif conf >= PASS_CONFIDENCE:  # pending: the machine can't tell, Claude can
                saw = (v.get("evidence") or v.get("reason") or "").strip()
                events.append({"type": "check.updated", "payload": {
                    "stepId": sid, "checkId": c["id"], "label": c.get("label", ""), "status": "pass",
                    "detail": clamp_words(f"Claude saw it on screen: {saw}", 24)}})
        card = None
        other = next((s for s in steps if s["id"] == data.get("on_step_id") and s["id"] != sid), None)
        idx = {s["id"]: i for i, s in enumerate(steps)}
        if other is not None and idx.get(other["id"], -1) > idx.get(sid, -1):  # ahead of the lesson; behind → no card
            card = {"stepId": sid, "kind": "answer", "title": "Already ahead?",
                    "body": clamp_words(f"You look to be on “{other.get('title', other['id'])}” already", 12),
                    "actions": ["skip_step"], "targetStepId": other["id"]}
        elif disagree:
            card = {"stepId": sid, "kind": "answer", "title": "Looks done?",
                    "body": summary or clamp_words(disagree[0].get("evidence") or disagree[0].get("reason", ""), 12),
                    "actions": ["confirm", "skip_step"], "checkIds": [v["check_id"] for v in disagree]}
        return {"checks": verdicts, "events": events, "card": card, "summary": summary}

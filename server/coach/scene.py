"""A Haiku "look" at the whole screen every few seconds during a lesson step, so Miyagi notices what's on screen
instead of only reacting (Michael, Nov 15).

    sc = await scene.look(image, step, step_file="calc.py", run=None, spot="the line in calc.py where …",
                          front_app="Code", mask=private_rects, scale=2.0, origin=(0, 0), frame=412)
    -> Scene(app, window_title, active_file, step_file_open, step_code_visible, typed_fraction, error_visible,
             dialog_visible, learner_doing, spotlight_target_visible, …)          raises llm.CoachLLMError
    scene.publish(sc)                  # the orchestrator's SceneWatch (server/orchestrator/scene_watch.py)
    scene.fresh(step_id)               # judge / explain / hint: the latest look if < FRESH_S old, else None
    scene.prompt_line(step_id)         # that look as one context line for a prompt ("" when there is none)
    scene.with_error(step_id, text)    # diagnose: + the error a fresh look saw after a run (no extra call)

One request: claude-haiku-5-5, thinking off, effort low, strict JSON (output_config.format). The image is the
reader's latest frame (Miyagi's overlay and other folders' VS Code windows already blacked out by
reader.latest_frame(); private apps such as 1Password / Messages blacked out here), downscaled so neither side
is over 1280 px, plus the current step as text (title, file, code to type, run command, check labels, what the
spotlight points at). ~2.1-2.6K input tokens, 50-160 output: about $0.0003 a look (Haiku 5.5, $0.10 / $0.50 per
MTok). One INFO line per look (latency, tokens, $, running total).

A look is CONTEXT, never a verdict: nothing in here passes or fails a check.
FakeLook: the same call signature as look(), canned answers, no API (tests, rehearsals).
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import math
import os
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from . import llm

log = logging.getLogger("coach.scene")

MODEL = os.environ.get("MIYAGI_SCENE_MODEL") or llm.HAIKU
MAX_W = 1280
MAX_TOKENS = 400  # the answer is ~50-160 tokens; room so strict JSON never hits max_tokens
FRESH_S = 8.0  # judge / explain / hint use a look at most this old
ERROR_FRESH_S = 15.0  # diagnose: an error a look saw at most this long ago
CODE_CHARS = 700

SYSTEM = """You glance at a learner's Mac screen for Miyagi, a coding tutor. The learner is on one step of a lesson (described below). Report only what the screenshot shows; never guess. Black rectangles are Miyagi's own overlay or private windows: ignore them.
Fields:
- app: the frontmost app as its window shows it ("Code", "Terminal", "Google Chrome"); "" if unclear.
- window_title: the front window's title if readable, else "".
- active_file: the file name of the code editor's ACTIVE tab (the highlighted tab / the title bar), e.g. "calc.py"; "" when no editor is in front or it is unreadable. A file listed in the Explorer side bar is NOT the active file.
- step_file_open: true only when the step's file is the editor's active tab on screen.
- step_code_visible: true when the step's code, or the place it goes in that file, is visible in the editor.
- typed_fraction: 0 to 1, how much of the step's code is already typed in that file (0 when none of it, or the file is not visible).
- error_visible: an error that is visible (traceback, red error line, Problems entry, failed command), one line of at most 160 characters copied from the screen; "" when there is none.
- dialog_visible: the title of a dialog, popup or permission prompt covering the work (e.g. "Save changes?"); "" when there is none.
- learner_doing: at most 8 words on what the learner seems to be doing ("typing add() in calc.py", "reading docs in Chrome").
- spotlight_target_visible: true when the SPOTLIGHT TARGET named below is visible on screen right now."""

FIELDS = ("app", "window_title", "active_file", "step_file_open", "step_code_visible", "typed_fraction",
          "error_visible", "dialog_visible", "learner_doing", "spotlight_target_visible")

SCHEMA = {
    "type": "object",
    "properties": {
        "app": {"type": "string"},
        "window_title": {"type": "string"},
        "active_file": {"type": "string"},
        "step_file_open": {"type": "boolean"},
        "step_code_visible": {"type": "boolean"},
        "typed_fraction": {"type": "number"},
        "error_visible": {"type": "string"},
        "dialog_visible": {"type": "string"},
        "learner_doing": {"type": "string"},
        "spotlight_target_visible": {"type": "boolean"},
    },
    "required": list(FIELDS),
    "additionalProperties": False,
}


# ---------------------------------------------------------------------- the answer

@dataclass
class Scene:
    app: str = ""
    window_title: str = ""
    active_file: str | None = None
    step_file_open: bool = False
    step_code_visible: bool = False
    typed_fraction: float = 0.0
    error_visible: str | None = None
    dialog_visible: str | None = None
    learner_doing: str = ""
    spotlight_target_visible: bool = False
    step_id: str | None = None
    frame: int | None = None  # the reader's frame number the look was taken on
    after_run: bool = False  # the step had run something when the look was taken (SceneWatch sets it)
    t: float = field(default_factory=time.monotonic)
    wall_t: float = field(default_factory=time.time)
    ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    source: str = "live"  # live | fake

    def age(self) -> float:
        return time.monotonic() - self.t

    def signature(self) -> tuple:
        """What the look saw, for PeriodicGate's "same answer" count (free text and the exact fraction left out)."""
        return (self.app.lower(), (self.active_file or "").lower(), self.step_file_open, self.step_code_visible,
                round(self.typed_fraction, 1), bool(self.error_visible), bool(self.dialog_visible),
                self.spotlight_target_visible)

    def brief(self, files: bool = True) -> str:
        """One line: 'front app Code; active file calc.py (the step's file); its code visible, about 40% typed; …'."""
        parts = [f"front app {self.app or 'unknown'}"]
        if files:
            if self.active_file:
                parts.append(f"active file {self.active_file}" + (" (the step's file)" if self.step_file_open else ""))
            elif self.step_file_open:
                parts.append("the step's file is the active tab")
        if self.step_code_visible:
            parts.append(f"the step's code is visible, about {round(self.typed_fraction * 100)}% typed")
        else:
            parts.append("the step's code is not visible")
        if self.error_visible:
            parts.append(f'error on screen: "{self.error_visible}"')
        if self.dialog_visible:
            parts.append(f'dialog: "{self.dialog_visible}"')
        if self.learner_doing:
            parts.append(f"learner: {self.learner_doing}")
        return "; ".join(parts)

    def to_dict(self) -> dict:
        """camelCase, JSON-safe (session.state()["scene"]["latest"])."""
        return {"app": self.app, "windowTitle": self.window_title, "activeFile": self.active_file,
                "stepFileOpen": self.step_file_open, "stepCodeVisible": self.step_code_visible,
                "typedFraction": round(self.typed_fraction, 2), "errorVisible": self.error_visible,
                "dialogVisible": self.dialog_visible, "learnerDoing": self.learner_doing,
                "spotlightTargetVisible": self.spotlight_target_visible, "stepId": self.step_id, "frame": self.frame,
                "afterRun": self.after_run, "ageS": round(self.age(), 1), "ms": self.ms,
                "inputTokens": self.input_tokens, "outputTokens": self.output_tokens,
                "costUsd": round(self.cost_usd, 6), "source": self.source}


_NONE = {"", "none", "null", "n/a", "na", "no", "-", "nothing"}


def _text(v: Any, n: int) -> str:
    s = " ".join(str(v if v is not None else "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _opt(v: Any, n: int) -> str | None:
    s = _text(v, n)
    return None if s.lower().strip(" .") in _NONE else s


def _flag(v: Any) -> bool:
    return v is True or str(v).strip().lower() in ("true", "yes", "1")


def _frac(v: Any) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(f):
        return 0.0
    if 1.0 < f <= 100.0:  # "40" meant 40%
        f /= 100.0
    return min(1.0, max(0.0, f))


def parse(data: dict) -> dict:
    """The model's JSON -> Scene fields (missing keys default, "" / "none" -> None, paths -> file names)."""
    d = data if isinstance(data, dict) else {}
    active = _opt(d.get("active_file"), 120)
    if active:
        active = re.split(r"[\\/]", active.lstrip("●•⚫ ").strip())[-1] or None
    return {"app": _text(d.get("app"), 60), "window_title": _text(d.get("window_title"), 160), "active_file": active,
            "step_file_open": _flag(d.get("step_file_open")), "step_code_visible": _flag(d.get("step_code_visible")),
            "typed_fraction": _frac(d.get("typed_fraction")), "error_visible": _opt(d.get("error_visible"), 200),
            "dialog_visible": _opt(d.get("dialog_visible"), 120), "learner_doing": _text(d.get("learner_doing"), 80),
            "spotlight_target_visible": _flag(d.get("spotlight_target_visible"))}


def parse_text(text: str) -> dict | None:
    """Strict JSON from structured outputs; a fenced / prose-wrapped object is tolerated. None when unreadable."""
    try:
        d = json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        m = re.search(r"\{.*\}", text or "", re.DOTALL)
        if not m:
            return None
        try:
            d = json.loads(m.group(0))
        except (json.JSONDecodeError, ValueError):
            return None
    return d if isinstance(d, dict) else None


# ---------------------------------------------------------------------- the request

def step_brief(step: dict, *, step_file: str | None = None, run: str | None = None, spot: str | None = None,
               front_app: str = "") -> str:
    """The step as the model needs it: title, what to do, the file, the code to type, the run command, the check
    labels, and what Miyagi's spotlight points at."""
    out = [f"LESSON STEP: {_text(step.get('title'), 120)}"]
    if instr := _text(step.get("instructions"), 300):
        out.append(f"INSTRUCTIONS: {instr}")
    if step_file:
        out.append(f"STEP FILE: {step_file}")
    code = (step.get("code") or "").strip("\n")
    if code.strip() and not run:
        out.append("CODE TO TYPE:\n" + (code if len(code) <= CODE_CHARS else code[:CODE_CHARS] + "\n…"))
    if run:
        out.append(f"COMMAND TO RUN: {run.splitlines()[0][:160]}")
    labels = [_text(c.get("label"), 100) for c in (step.get("checks") or []) if c.get("label")][:6]
    if labels:
        out.append("CHECKS:\n" + "\n".join(f"- {x}" for x in labels))
    out.append(f"SPOTLIGHT TARGET: {spot or 'none (answer false)'}")
    if front_app:  # E5: the OS knows; the picture alone read "Code" while the Claude app was in front
        out.append(f"FRONTMOST APP (from macOS; use it for `app`, and describe learner_doing in this app): {front_app}")
    out.append("Reply with the JSON.")
    return "\n".join(out)


def _code_lines(text: str) -> list[str]:
    return [" ".join(ln.split()) for ln in (text or "").splitlines() if ln.strip() and not ln.strip().startswith("#")]


def typed_fraction(code: str, file_text: str) -> float | None:
    """How much of the step's code is in the file: the share of its code lines (whitespace-normalized, comments left
    out) found in the file's lines, in order. None when the step has no code. Deterministic (E5: the look guessed 0-40%
    from the picture and swung between them with no edit)."""
    want = _code_lines(code)
    if not want:
        return None
    have = _code_lines(file_text)
    i = hits = 0
    for ln in want:
        j = next((k for k in range(i, len(have)) if have[k] == ln), None)
        if j is not None:
            hits, i = hits + 1, j + 1
    return round(hits / len(want), 2)


def _xywh(r: Any) -> tuple[float, float, float, float]:
    if isinstance(r, dict):
        return float(r["x"]), float(r["y"]), float(r["w"]), float(r["h"])
    if isinstance(r, (list, tuple)) and len(r) == 4:
        return tuple(float(v) for v in r)  # type: ignore[return-value]
    return float(r.x), float(r.y), float(r.w), float(r.h)


def encode(image: Any, mask: Sequence = (), scale: float = 1.0, origin: tuple[float, float] = (0.0, 0.0),
           max_w: int = MAX_W, quality: int = 80) -> tuple[bytes, tuple[int, int]]:
    """PIL image of the screen -> JPEG, `mask` rects (screen points; image px = (pt - origin) * scale) blacked out,
    downscaled so neither side is over `max_w` px."""
    from PIL import Image, ImageDraw

    img = image.convert("RGB")
    if img is image:
        img = img.copy()  # never draw on the reader's frame
    if mask:
        d = ImageDraw.Draw(img)
        ox, oy = origin
        for r in mask:
            x, y, w, h = _xywh(r)
            d.rectangle([(x - ox) * scale, (y - oy) * scale, (x + w - ox) * scale, (y + h - oy) * scale], fill=(0, 0, 0))
    k = min(1.0, max_w / img.width, max_w / img.height)
    if k < 1.0:
        img = img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return buf.getvalue(), img.size


_STATS: dict[str, Any] = {}


def reset_stats() -> None:
    _STATS.clear()
    _STATS.update(looks=0, errors=0, input_tokens=0, output_tokens=0, cost_usd=0.0)


reset_stats()


def stats() -> dict:
    return {**_STATS, "cost_usd": round(_STATS["cost_usd"], 6)}


def _cost(resp: Any, usage: Any) -> float:
    """Dollars of one look from the shared price table (server.lesson.cost), also recorded in the lesson's
    session tally (source "coach"). A refused or unusable look is billed too, so it counts."""
    m = getattr(resp, "model", None)
    m = m if isinstance(m, str) and m else MODEL
    if usage is None:
        return 0.0
    if llm._cost_mod() is None:
        return llm.usd(m, int(getattr(usage, "input_tokens", 0) or 0), int(getattr(usage, "output_tokens", 0) or 0))
    return llm.record_cost(m, usage, source="coach", label="coach scene")


async def look(image: Any, step: dict, *, step_file: str | None = None, run: str | None = None,
               spot: str | None = None, front_app: str = "", mask: Sequence = (), scale: float = 1.0,
               origin: tuple[float, float] = (0.0, 0.0), frame: int | None = None, timeout: float | None = None,
               client: Any = None, file_text: str | None = None) -> Scene:
    """One Haiku look at `image` (PIL, the reader's latest frame, overlay already masked) for `step` -> Scene.
    front_app (macOS's frontmost app) and file_text (the step file's text) are facts: they replace the look's own
    `app` and `typed_fraction`.
    Raises llm.CoachLLMError: kind "offline" (DEMO / ORCH_STUBS), "no_key", "connection" (incl. timeout), "api",
    "refusal", "bad_output". `client`: an AsyncAnthropic-like stub (tests); default the coach's BYOK client."""
    if client is None and llm.offline_mode():
        raise llm.CoachLLMError("scene: offline mode (DEMO / ORCH_STUBS), no live call", "offline")
    if client is None and not llm.has_credentials():
        raise llm.CoachLLMError("scene: no ANTHROPIC_API_KEY", "no_key")
    jpeg, size = await asyncio.to_thread(encode, image, mask, scale, origin)
    text = step_brief(step, step_file=step_file, run=run, spot=spot, front_app=front_app)
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                            "data": base64.standard_b64encode(jpeg).decode("ascii")}},
               {"type": "text", "text": text}]
    t = timeout if timeout is not None else float(os.environ.get("MIYAGI_SCENE_TIMEOUT_S", "8") or 8)
    c = client or llm.get_client()
    if hasattr(c, "with_options"):
        c = c.with_options(timeout=t, max_retries=0)  # a slow look is skipped, never retried: the next one is 5 s away
    api, kwargs = llm._request(c, MODEL, [{"type": "text", "text": SYSTEM}], content, SCHEMA, "low", MAX_TOKENS,
                               {"type": "disabled"})
    t0 = time.perf_counter()
    try:
        resp = await asyncio.wait_for(api.create(**kwargs), t)
    except TimeoutError as e:
        _STATS["errors"] += 1
        raise llm.CoachLLMError(f"scene: timeout after {t:.0f} s", "connection") from e
    except Exception as e:
        _STATS["errors"] += 1
        try:
            import anthropic
        except ImportError:  # pragma: no cover
            raise llm.CoachLLMError(f"scene: {type(e).__name__}", "api") from e
        if isinstance(e, anthropic.APIStatusError):
            raise llm.CoachLLMError(f"scene: API {e.status_code}", "api") from e
        if isinstance(e, anthropic.APIConnectionError):
            raise llm.CoachLLMError("scene: connection error", "connection") from e
        raise llm.CoachLLMError(f"scene: {type(e).__name__}: {str(e)[:120]}", "api") from e
    ms = (time.perf_counter() - t0) * 1000
    usage = getattr(resp, "usage", None)
    inp, out = int(getattr(usage, "input_tokens", 0) or 0), int(getattr(usage, "output_tokens", 0) or 0)
    cost = _cost(resp, usage)
    _STATS["looks"] += 1
    _STATS["input_tokens"] += inp
    _STATS["output_tokens"] += out
    _STATS["cost_usd"] += cost
    stop = getattr(resp, "stop_reason", None)
    answer = "".join(getattr(b, "text", "") for b in getattr(resp, "content", None) or []
                     if getattr(b, "type", None) == "text")
    data = parse_text(answer) if stop not in ("refusal", "max_tokens") else None
    if data is None:
        _STATS["errors"] += 1
        log.info("scene look %s: no usable answer (stop=%s) %.0fms in=%d out=%d $%.5f", step.get("id"), stop, ms, inp,
                 out, cost)
        raise llm.CoachLLMError(f"scene: stop_reason={stop}", "refusal" if stop == "refusal" else "bad_output")
    sc = Scene(**parse(data), step_id=step.get("id"), frame=frame, ms=round(ms), input_tokens=inp, output_tokens=out,
               cost_usd=cost)
    if front_app:
        sc.app = _text(front_app, 60)
    if file_text is not None and not run and (frac := typed_fraction(step.get("code") or "", file_text)) is not None:
        sc.typed_fraction = frac
    log.info("scene look %s %.0fms img %dx%d in=%d out=%d $%.5f (total $%.4f, %d looks) | %s",
             step.get("id"), ms, size[0], size[1], inp, out, cost, _STATS["cost_usd"], _STATS["looks"], sc.brief())
    return sc


# ---------------------------------------------------------------------- the latest look (one learner per engine)

_LATEST: Scene | None = None


def publish(sc: Scene | None) -> None:
    global _LATEST
    _LATEST = sc


def clear() -> None:
    publish(None)


def latest() -> Scene | None:
    return _LATEST


def fresh(step_id: str | None = None, max_age: float = FRESH_S) -> Scene | None:
    """The latest look when it is at most `max_age` s old (and about `step_id`, when given), else None."""
    sc = _LATEST
    if sc is None or sc.age() > max_age:
        return None
    if step_id is not None and sc.step_id not in (None, step_id):
        return None
    return sc


def prompt_line(step_id: str | None = None, *, files: bool = True, max_age: float = FRESH_S) -> str:
    """A fresh look as one prompt line, labelled as context (never evidence that a check passed); "" without one.
    files=False leaves the active file out (prompts that must never name which file is open)."""
    sc = fresh(step_id, max_age)
    if sc is None:
        return ""
    return (f"A GLANCE AT THE SCREEN ({sc.age():.0f} s ago, from a downscaled screenshot; context only, not evidence "
            f"that anything is done): {sc.brief(files)}")


def _squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def with_error(step_id: str | None, error_text: str, max_age: float = ERROR_FRESH_S) -> str:
    """Diagnose's error text + the error a fresh look saw on screen after this step ran something, unless the text
    already has it. Unchanged otherwise. No model call."""
    sc = fresh(step_id, max_age)
    if sc is None or not sc.error_visible or not sc.after_run:
        return error_text
    err = _squash(sc.error_visible)
    if not err or err in _squash(error_text):
        return error_text
    line = f"(seen on screen {sc.age():.0f} s ago) {sc.error_visible}"
    return f"{error_text.rstrip()}\n{line}" if (error_text or "").strip() else line


# ---------------------------------------------------------------------- test double

DEFAULTS = {"app": "Code", "window_title": "", "active_file": "", "step_file_open": True, "step_code_visible": True,
            "typed_fraction": 0.0, "error_visible": "", "dialog_visible": "", "learner_doing": "",
            "spotlight_target_visible": True}


class FakeLook:
    """look() without the API. `answers`: scene dicts (model field names; missing keys from DEFAULTS), returned in
    order with the last one repeated; an item may be a callable(step) -> dict, or an exception to raise.

        fake = FakeLook([{"step_file_open": False, "active_file": "README.md"}])
        watch = scene_watch.attach(session, look=fake, frame=lambda: (image, obs))
        fake.calls  # [{"step_id", "step_file", "run", "spot", "front_app", "frame"}, ...]
    """

    def __init__(self, answers: Sequence[dict | Callable[[dict], dict] | BaseException] | None = None, *,
                 delay: float = 0.0):
        self.answers = list(answers or [{}])
        self.delay = delay
        self.calls: list[dict] = []

    async def __call__(self, image: Any, step: dict, **kw: Any) -> Scene:
        self.calls.append({"step_id": step.get("id"), **{k: kw.get(k) for k in ("step_file", "run", "spot",
                                                                                 "front_app", "frame")}})
        if self.delay:
            await asyncio.sleep(self.delay)
        a = self.answers[min(len(self.calls), len(self.answers)) - 1]
        if isinstance(a, BaseException):
            raise a
        data = a(step) if callable(a) else a
        return Scene(**parse({**DEFAULTS, **(data or {})}), step_id=step.get("id"), frame=kw.get("frame"),
                     source="fake")


__all__ = [
    "DEFAULTS",
    "FRESH_S",
    "MODEL",
    "SCHEMA",
    "FakeLook",
    "Scene",
    "clear",
    "encode",
    "fresh",
    "latest",
    "look",
    "parse",
    "parse_text",
    "prompt_line",
    "publish",
    "reset_stats",
    "stats",
    "step_brief",
    "typed_fraction",
    "with_error",
]

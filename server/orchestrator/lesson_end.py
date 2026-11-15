"""The lesson's ending (desktop test 5, 02:21: the last step passed and nothing marked it; End sent nothing).

    finished(session)          the lesson ran to its end: phase done, its last step passed, nothing more coming
    end_reason(session, why)   End on a finished lesson ("stopped" from the bar / launcher, action end_lesson from a
                               card) ends it as "completed": the save was cleared at its last step, so no
                               "Lesson saved · Undo" and no "Continue where you left off?" for it
    card(session)              ONE completion card in the existing card format: a plain title (t7: the skill count,
                               "Neural networks · 8 skills mastered", else the lesson's own title; never "You built..."
                               or "Lesson complete"), a body of plain facts: what they built plus the real evidence
                               from their own runs ("Loss 0.819 → 0.0009 in your last run."), actions [end_lesson]
                               (labelled "End lesson"), card.skillMap (node details and cross notes: the app shows
                               them on click)
    send_later(session, gen)   that card, a moment after the last step's own result card (the run's output) went out

No model call: everything comes from the lesson graph and the runs the engine already holds.
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
from typing import Any

from server.lesson.skillmap import attach_skill_map

from .card_copy import ran

log = logging.getLogger("orchestrator.lesson_end")

CARD_DELAY_S = 2.5  # the last step's "Ran python3 main.py" card (its output) stays up this long first
END_LABEL = "End lesson"  # the card's button (the app's default label for end_lesson is "Start a new lesson")

# ------------------------------------------------------------------------------------------------ finished / reason


def finished(s: Any) -> bool:
    """The lesson ran to its end (its last step passed, nothing more is being built)."""
    return (getattr(s, "phase", None) == "done" and getattr(s, "graph", None) is not None
            and bool(getattr(s, "passed", False)) and not getattr(s, "waiting_more", False))


def end_reason(s: Any, reason: str) -> str:
    """The learner's End on a finished lesson is a completion, not a pause ("stopped" keeps a save to come back to)."""
    return "completed" if reason in ("stopped", "end_lesson") and finished(s) else reason


# ------------------------------------------------------------------------------------------------ title
# t7 (Michael, test 7): "You built a neural net" read as AI slop, and nothing says "Lesson complete". The title is
# the skill count the app's complete panel leads with ("Neural networks · 8 skills mastered"), else the lesson's own
# title ("A neural net from scratch").

MAX_TITLE_WORDS = 8


def title(lesson: dict) -> str:
    """The lesson's own title as written ("A neural net from scratch"), else its goal with a capital first letter;
    "All steps done" when it has neither (or they run longer than MAX_TITLE_WORDS)."""
    for text in (lesson.get("title"), lesson.get("goal")):
        t = " ".join(str(text or "").split()).rstrip(".!?")
        if t and len(t.split()) <= MAX_TITLE_WORDS:
            return t[:1].upper() + t[1:]
    return "All steps done"


def mastery_title(skill_map: Any) -> str | None:
    """"Neural networks · 8 skills mastered" from the card's skillMap (the app's complete panel header), None when
    nothing was mastered."""
    if not isinstance(skill_map, dict):
        return None
    n = sum(1 for x in skill_map.get("nodes") or [] if isinstance(x, dict) and x.get("state") == "mastered")
    track = " ".join(str(skill_map.get("track") or "").split())
    if not n or not track:
        return None
    return f"{track} · {n} skill{'' if n == 1 else 's'} mastered"


# ------------------------------------------------------------------------------------------------ evidence

_NUM = r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?"
_METRIC = re.compile(rf"\b(?P<name>val(?:idation)?[ _]loss|loss|cost|mse|error|accuracy|acc)\b\s*[:=]?\s*(?P<value>{_NUM})",
                     re.I)
_LABEL = {"loss": "Loss", "val_loss": "Validation loss", "cost": "Cost", "mse": "MSE", "error": "Error",
          "accuracy": "Accuracy"}


def _norm(name: str) -> str:
    n = re.sub(r"[\s_]+", "_", name.strip().lower())
    return {"acc": "accuracy", "validation_loss": "val_loss"}.get(n, n)


def _lower_is_better(name: str) -> bool | None:
    n = name.lower()
    if any(k in n for k in ("loss", "cost", "error", "mse", "perplexity")):
        return True
    if any(k in n for k in ("acc", "score", "reward", "f1", "r2")):
        return False
    return None


def _fmt(v: float) -> str:
    a = abs(v)
    if a >= 100:
        return f"{v:,.0f}"
    if a >= 1:
        return f"{v:.2f}".rstrip("0").rstrip(".")
    return f"{v:.3g}"


def _patterns(s: Any) -> list[tuple[str, re.Pattern]]:
    """The lesson's own metric patterns (its metric checks), e.g. loss <- r"epoch (?P<step>\\d+) loss: (?P<value>…)"."""
    out: list[tuple[str, re.Pattern]] = []
    for st in getattr(s, "steps", None) or []:
        for c in (st.get("checks") or []) + (st.get("precision_checks") or []):
            if c.get("metric") and c.get("metric_pattern"):
                try:
                    out.append((_norm(str(c["metric"])), re.compile(str(c["metric_pattern"]))))
                except re.error:
                    continue
    return out


def _series(run: Any, patterns: list[tuple[str, re.Pattern]]) -> dict[str, list[float]]:
    """name -> readings in order, from the run's own metric feed, else its printed output."""
    out: dict[str, list[float]] = {}
    for name, pts in (getattr(run, "metrics", None) or {}).items():
        vals = [float(v) for _, v in pts if v is not None and math.isfinite(v)]
        if len(vals) >= 2:
            out[_norm(name)] = vals
    if out:
        return out
    lines = [str(x) for x in getattr(run, "output_tail", None) or []]
    for name, rx in patterns:
        vals = []
        for line in lines:
            m = rx.search(line)
            if not m:
                continue
            raw = m.groupdict().get("value") if "value" in m.groupdict() else (m.group(m.lastindex) if m.lastindex else None)
            try:
                v = float(raw)
            except (TypeError, ValueError):
                continue
            if math.isfinite(v):
                vals.append(v)
        if len(vals) >= 2:
            out.setdefault(name, vals)
    loose: dict[str, list[float]] = {}  # common names ("loss: 0.25", "accuracy = 0.9") for what no pattern covered
    for line in lines:
        for m in _METRIC.finditer(line):
            try:
                v = float(m.group("value"))
            except ValueError:
                continue
            if math.isfinite(v):
                loose.setdefault(_norm(m.group("name")), []).append(v)
    for name, vals in loose.items():
        if name not in out:
            out[name] = vals
    return {k: v for k, v in out.items() if len(v) >= 2}


def _ok_runs(s: Any) -> list[Any]:
    """The lesson's finished, successful runs, newest first (not the OCR-read "screen-" ones: their numbers can be
    misread)."""
    runs = list((getattr(s, "runs", None) or {}).values())
    return [r for r in reversed(runs) if r.exit_code == 0 and not str(r.run_id).startswith("screen-")]


def metric_line(s: Any) -> str | None:
    """"Loss 0.247 → 0.001 in your last run." from the newest run whose metric moved the right way."""
    patterns = _patterns(s)
    for i, run in enumerate(_ok_runs(s)):
        for name, vals in _series(run, patterns).items():
            lower = _lower_is_better(name)
            first, last = vals[0], vals[-1]
            if lower is None or _fmt(first) == _fmt(last) or (last < first) != lower:
                continue
            label = _LABEL.get(name) or name.replace("_", " ").capitalize()
            when = "in your last run" if i == 0 else "when you ran it"
            return f"{label} {_fmt(first)} → {_fmt(last)} {when}."
    return None


def evidence(s: Any) -> str | None:
    """The real proof it works: a metric that moved the right way, else the last command that ran cleanly."""
    if line := metric_line(s):
        return line
    for run in _ok_runs(s):
        if (run.command or "").strip():
            return f"{ran(run.command)} without errors."  # "Ran nn.py without errors."
    return None


def _what(lesson: dict) -> str | None:
    """What they built, in the lesson's own words ("A 1-4-4-1 neural network in NumPy that learns y = sin(x).")."""
    build = lesson.get("build") if isinstance(lesson.get("build"), dict) else {}
    text = " ".join(str(build.get("summary") or "").split())
    if not text and isinstance(lesson.get("overview"), str):
        first = re.split(r"(?<=[.!?])\s+", " ".join(lesson["overview"].split()), maxsplit=1)[0]
        text = first if len(first.split()) <= 25 else ""
    if not text:
        return None
    return text if text[-1] in ".!?" else text + "."


# ------------------------------------------------------------------------------------------------ the card


def card(s: Any) -> dict:
    lesson = (getattr(s, "graph", None) or {}).get("lesson") or {}
    steps = getattr(s, "steps", None) or []
    skipped = [x for x in getattr(s, "skipped_steps", None) or []]
    proof = evidence(s)
    lines = [_what(lesson), proof]
    if skipped:  # honest: a skipped step is not a pass
        lines.append(f"You did {len(steps) - len(skipped)} of {len(steps)} steps and skipped {len(skipped)}.")
    body = " ".join(x for x in lines if x) or f"All {len(steps)} steps done."
    step = getattr(s, "step", None)
    out = {**({"stepId": step["id"]} if step else {}), "kind": "step", "title": title(lesson), "body": body,
           "actions": ["end_lesson"],
           # setup.actionLabels is how a card names its own buttons (cards/index.tsx actionLabel); no items, so the
           # app draws no setup rows: only the label of end_lesson changes ("End lesson", not "Start a new lesson")
           "setup": {"editorNeeded": False, "items": [], "actionLabels": {"end_lesson": END_LABEL}}}
    # mockup 10 "Your skills": card.skillMap (all three senders: send_later, Check / Skip after the end, the reconnect
    # replay); its headline carries the same real proof as the body. Never raises: no map rather than no card.
    out = attach_skill_map(out, s, evidence=proof)
    if head := mastery_title(out.get("skillMap")):  # the header the app's complete panel draws from the same map
        out["title"] = head
    return out


async def send_later(s: Any, gen: int, delay_s: float | None = None) -> None:
    """The completion card, once the last step's own result card has been seen. Nothing if the learner went Back,
    a new lesson started or End came first (end_lesson cancels this timer; the lesson epoch drops a late emit)."""
    await asyncio.sleep(CARD_DELAY_S if delay_s is None else delay_s)
    if gen != s.step_gen or not finished(s):
        return
    c = card(s)
    log.info("lesson complete: %r | %s", c["title"], c["body"])
    await s._emit_card(c, window_s=0.0)

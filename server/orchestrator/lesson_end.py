"""The lesson's ending (desktop test 5, 02:21: the last step passed and nothing marked it; End sent nothing).

    finished(session)          the lesson ran to its end: phase done, its last step passed, nothing more coming
    end_reason(session, why)   End on a finished lesson ("stopped" from the bar / launcher, action end_lesson from a
                               card) ends it as "completed": the save was cleared at its last step, so no
                               "Lesson saved · Undo" and no "Continue where you left off?" for it
    card(session)              ONE completion card in the existing card format: the title from the goal ("You built a
                               neural network"), what they built plus the real evidence from their own runs ("Loss fell
                               from 0.247 to 0.001 in your last run."), actions [end_lesson] (labelled "End lesson")
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

log = logging.getLogger("orchestrator.lesson_end")

CARD_DELAY_S = 2.5  # the last step's "Ran python3 main.py" card (its output) stays up this long first
END_LABEL = "End lesson"  # the card's button (the app's default label for end_lesson is "Start a new lesson")
MAX_TITLE_WORDS = 8

# ------------------------------------------------------------------------------------------------ finished / reason


def finished(s: Any) -> bool:
    """The lesson ran to its end (its last step passed, nothing more is being built)."""
    return (getattr(s, "phase", None) == "done" and getattr(s, "graph", None) is not None
            and bool(getattr(s, "passed", False)) and not getattr(s, "waiting_more", False))


def end_reason(s: Any, reason: str) -> str:
    """The learner's End on a finished lesson is a completion, not a pause ("stopped" keeps a save to come back to)."""
    return "completed" if reason in ("stopped", "end_lesson") and finished(s) else reason


# ------------------------------------------------------------------------------------------------ title

_IRREGULAR = {"build": "built", "make": "made", "write": "wrote", "draw": "drew", "teach": "taught", "run": "ran",
              "do": "did", "get": "got", "set": "set", "put": "put", "read": "read", "find": "found", "spin": "spun",
              "understand": "understood", "begin": "began", "bring": "brought", "fit": "fitted", "plot": "plotted",
              "plan": "planned", "ship": "shipped", "map": "mapped", "program": "programmed", "debug": "debugged",
              "log": "logged", "chat": "chatted", "stop": "stopped", "drop": "dropped", "grow": "grew",
              "fine-tune": "fine-tuned", "finetune": "fine-tuned"}
_REGULAR = {"create", "train", "code", "implement", "design", "learn", "deploy", "solve", "render", "animate", "model",
            "simulate", "analyze", "analyse", "visualize", "visualise", "compose", "cook", "bake", "paint", "sketch",
            "edit", "record", "mix", "play", "master", "explore", "use", "add", "automate", "scrape", "test", "host",
            "launch", "publish", "configure", "install", "connect", "compute", "calculate", "measure", "predict",
            "classify", "detect", "generate", "translate", "convert", "sort", "search", "parse", "craft", "develop",
            "construct", "assemble", "finish", "complete", "optimize", "optimise", "tune", "style", "format", "clean",
            "fix", "prototype", "start", "practice", "practise", "try", "wire", "script", "query"}
_LEAD = re.compile(r"^(?:how\s+(?:do\s+i\s+|to\s+)|let'?s\s+|(?:i\s+(?:want|would\s+like|'d\s+like)\s+to\s+)|"
                   r"(?:teach\s+me\s+(?:how\s+)?to\s+)|(?:show\s+me\s+how\s+to\s+)|(?:help\s+me\s+)|(?:learn\s+(?:how\s+)?to\s+))",
                   re.I)
# trailing "in Python" / "with NumPy" / "using React" / "from scratch": the title says what, the drawer says how
_TAIL = re.compile(r"\s+(?:from\s+scratch|(?:in|with|using)\s+(?:pure\s+|plain\s+)?[\w.+#-]+)\s*$", re.I)


def _past(verb: str) -> str | None:
    v = verb.lower()
    if v in _IRREGULAR:
        return _IRREGULAR[v]
    if v not in _REGULAR:
        return None
    if v.endswith("e"):
        return v + "d"
    if v.endswith("y") and len(v) > 1 and v[-2] not in "aeiou":
        return v[:-1] + "ied"
    return v + "ed"


def title(lesson: dict) -> str:
    """"Build a neural network in Python" -> "You built a neural network"; no leading verb -> "Lesson complete"."""
    for text in (lesson.get("title"), lesson.get("goal")):
        t = _LEAD.sub("", " ".join(str(text or "").split())).strip().rstrip(".!?")
        words = t.split(" ")
        if len(words) < 2 or not (past := _past(words[0].strip(",:"))):
            continue
        rest = " ".join(words[1:])
        while (m := _TAIL.search(rest)) and len(rest[:m.start()].split()) >= 2:
            rest = rest[:m.start()]
        if len(rest.split()) + 2 <= MAX_TITLE_WORDS:
            return f"You {past} {rest}"
    return "Lesson complete"


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
    """"Loss fell from 0.247 to 0.001 in your last run." from the newest run whose metric moved the right way."""
    patterns = _patterns(s)
    for i, run in enumerate(_ok_runs(s)):
        for name, vals in _series(run, patterns).items():
            lower = _lower_is_better(name)
            first, last = vals[0], vals[-1]
            if lower is None or _fmt(first) == _fmt(last) or (last < first) != lower:
                continue
            label = _LABEL.get(name) or name.replace("_", " ").capitalize()
            when = "in your last run" if i == 0 else "when you ran it"
            return f"{label} {'fell' if lower else 'rose'} from {_fmt(first)} to {_fmt(last)} {when}."
    return None


def evidence(s: Any) -> str | None:
    """The real proof it works: a metric that moved the right way, else the last command that ran cleanly."""
    if line := metric_line(s):
        return line
    for run in _ok_runs(s):
        cmd = (run.command or "").strip().splitlines()[0][:48] if (run.command or "").strip() else ""
        if cmd:
            return f"{cmd} ran without errors."
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
    out = {**({"stepId": step["id"]} if step else {}), "kind": "step",
           "title": "Lesson finished" if skipped else title(lesson), "body": body,
           "actions": ["end_lesson"],
           # setup.actionLabels is how a card names its own buttons (cards/index.tsx actionLabel); no items, so the
           # app draws no setup rows: only the label of end_lesson changes ("End lesson", not "Start a new lesson")
           "setup": {"editorNeeded": False, "items": [], "actionLabels": {"end_lesson": END_LABEL}}}
    # mockup 10 "Your skills": card.skillMap (all three senders: send_later, Check / Skip after the end, the reconnect
    # replay); its headline carries the same real proof as the body. Never raises: no map rather than no card.
    return attach_skill_map(out, s, evidence=proof)


async def send_later(s: Any, gen: int, delay_s: float | None = None) -> None:
    """The completion card, once the last step's own result card has been seen. Nothing if the learner went Back,
    a new lesson started or End came first (end_lesson cancels this timer; the lesson epoch drops a late emit)."""
    await asyncio.sleep(CARD_DELAY_S if delay_s is None else delay_s)
    if gen != s.step_gen or not finished(s):
        return
    c = card(s)
    log.info("lesson complete: %r | %s", c["title"], c["body"])
    await s._emit_card(c, window_s=0.0)

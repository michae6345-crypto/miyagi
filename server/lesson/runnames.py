"""Run steps named for what the learner sees (QA test 5: s5, s7, s9 and s10 all read "Run your program and see what
it prints", s7 and s9 were both "Run main.py").

A run step whose title is generic ("Run main.py", "Run it", "Run your program", "Test it") or repeats another step's,
or whose plan line (`what`) is the generic one or a repeat, is renamed after what THIS run shows:
"Run it: see the untrained guesses" / "Run your program and see the untrained guesses". The phrase comes from the step
writer's `shows` (one more field in the same step call, no extra model call), else from the step's own checks: a falling
metric ("watch the loss fall"), else its terminal check ("Gradient shapes printed" -> "see the gradient shapes").
Specific, unique names are never touched; textlesson.distinct_steps stays the last resort ("again", "(2)").
"""

from __future__ import annotations

import re

_FILES = r"[\w./-]+\.(?:py|js|mjs|cjs|ts|rb|go|rs|sh|java)"
GENERIC_TITLE = re.compile(
    rf"^\s*(?:run|execute|launch|try|test|start|check|see)\b(?:\s+(?:it|the|your|this|my|python3?|node))*"
    rf"(?:\s+(?:program|code|script|file|app|application|output|{_FILES}))?(?:\s+again)?(?:\s*\(\d+\))?\s*[.!]?\s*$", re.I)
GENERIC_WHAT = re.compile(r"^\s*run (?:your|the) [\w. -]+? (?:again )?and see what (?:it prints|changed)(?: again)?"
                          r"(?: \(\d+\))?\s*\.?\s*$", re.I)
_VERB = re.compile(r"^(?:see|watch|check|spot|compare|notice|read|find|count|get|meet|test|try|hear|look)\b", re.I)
_DONE = re.compile(r"\s+(?:printed|shown|shows|appears?|appear|visible|displayed|on screen|in (?:the|VS Code's) terminal)$", re.I)
_SAYS = re.compile(r"^(?:prints|shows|the terminal shows|terminal shows|output shows)\s+", re.I)
_DET = re.compile(r"^(?:(?:the|a|an|its|your|all|every|each|four|three|two|one)\b|\d)", re.I)
TERMINALS = ("Terminal", "iTerm2")


def _clip(text: str, n: int) -> str:
    from .textlesson import _short_title  # textlesson imports this module

    return _short_title(" ".join((text or "").split()), n)


def _lower_first(text: str) -> str:
    w = text.split(" ", 1)[0]
    code = "`" in w or re.search(r"[._\d]|[a-z][A-Z]|^[A-Z]{2,}", w)  # sigmoid_slope, W1, NumPy, XOR stay as written
    return text if code else text[:1].lower() + text[1:]


def clean_phrase(text: str, max_words: int = 4) -> str:
    """"See the untrained guesses." / "the untrained guesses" -> "see the untrained guesses" (<= max_words words,
    a verb first). "" when nothing usable is left (or it's code / the generic "see the output")."""
    t = " ".join(str(text or "").replace("`", "").split()).strip(" .!:;,")
    if not t or re.search(r"[{}()\[\]=]", t):
        return ""
    t = _lower_first(t)
    if not _VERB.match(t):
        t = "see " + t
    if len(t.split()) > max_words:
        return ""  # cut short it would read "see four predictions near": the checks name it instead
    if len(t.split()) < 2 or re.fullmatch(r"see (?:the |what it )?(?:output|prints|result|it)", t, re.I):
        return ""
    return t


def _check_phrase(st: dict) -> str:
    """What a run step's own checks look for, as a phrase: a falling / rising metric, else a terminal line."""
    for c in st.get("checks") or []:
        t, m = c.get("type"), str(c.get("metric") or "").replace("_", " ").strip()
        if not m:
            continue
        down = c.get("op") in ("<", "<=") if t == "metric_threshold" else \
            str(c.get("trend") or "").lower() in ("down", "decreasing", "decrease", "falling") if t == "metric_trend" else None
        if down is not None:
            way = "fall" if down else "rise"
            if phrase := clean_phrase(f"watch the {m} {way}") or clean_phrase(f"watch {m} {way}"):
                return phrase
    for c in st.get("checks") or []:
        if c.get("type") != "screen_contains" or c.get("app") not in TERMINALS:
            continue
        lbl = " ".join(str(c.get("label") or "").split())
        if not lbl or "`" in lbl or re.search(r"[(){}\[\]=:]", lbl):
            continue  # "Prints `dW2 shape: (3, 1)`": an exact line, not a name for the step
        body = _DONE.sub("", _SAYS.sub("", lbl)).strip()
        if not body or body.lower() == lbl.lower():
            continue  # not "X printed" / "Prints X": a claim ("Final loss is small"), not what the run shows
        body = _lower_first(body)
        for cand in ([body] if _DET.match(body) else ["the " + body, body]):  # "the" only while it fits in 4 words
            if phrase := clean_phrase(cand):
                return phrase
    return ""


def phrase_for(st: dict, shows: str = "") -> str:
    return clean_phrase(shows) or _check_phrase(st)


def is_run(st: dict) -> bool:
    from .textlesson import step_kind

    return (st.get("kind") or step_kind(st)) == "run"


def name_run(st: dict, shows: str = "", before=(), after=()) -> dict:
    """Rename one run step's generic / repeated title and plan line after what it shows (see module docstring).
    before / after: the steps before and after it (or their plan rows). A title or plan line repeats when a step
    BEFORE it has it (the first one keeps its name); a new name is never one any other step has."""
    from .textlesson import _noun, _words

    phrase = phrase_for(st, shows)
    if not phrase:
        return st

    def norm(v) -> str:
        return " ".join(str(v or "").split())

    for key, generic in (("title", GENERIC_TITLE), ("what", GENERIC_WHAT)):
        earlier = {norm(o.get(key)).lower() for o in before}
        others = earlier | {norm(o.get(key)).lower() for o in after}
        cur = norm(st.get(key))
        if cur and not generic.match(cur) and cur.lower() not in earlier:
            continue  # specific and the first of its name: kept word for word
        cand = (_clip(f"Run it: {phrase}", 6) if key == "title"
                else _words(f"Run your {_noun(st.get('file') or '')} and {phrase}", 12).rstrip("."))
        if cand.lower() not in others:
            st[key] = cand
    return st


def name_runs(steps: list[dict]) -> None:
    """The post-build pass over a whole lesson: every run step with a generic or repeated title / plan line gets one
    from what it shows, never one another step already has. Run before textlesson.distinct_steps."""
    for k, st in enumerate(steps):
        if is_run(st):
            name_run(st, "", steps[:k], steps[k + 1:])

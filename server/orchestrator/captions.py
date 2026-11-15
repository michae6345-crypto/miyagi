"""Spotlight captions are short pointers on the box (E5): at most ~8 words. The whole instruction stays in the drawer.

    short_caption("Type it here")  -> "Type it here"                 (short: unchanged)
    short_caption("Click at the end of the file, just below sigmoid_slope. Leave a blank line or two, then type the "
                  "X inputs and y answers here.")                    -> "Type below sigmoid_slope"
    short_caption("Run the script in the terminal and watch the loss go down each epoch")  -> "Run it here"
"""

from __future__ import annotations

import re

MAX_WORDS = 8

_TYPE = re.compile(r"\b(type|write|add|paste|insert|define)\b", re.I)
_RUN = re.compile(r"\b(run|rerun|execute)\b", re.I)
_LOOK = re.compile(r"\b(look|see|notice|read|watch|check|compare)\b", re.I)
_CLICK = re.compile(r"\b(click|press|select|open|choose)\b", re.I)
_ANCHOR = re.compile(r"\b(below|under|after|above|before)\s+(?:the\s+)?(?:(?:line|function|def|class)\s+)?"
                     r"([`'\"“]?)([A-Za-z_][\w.]*(?:\(\))?)", re.I)


def _code_name(name: str, quoted: bool) -> bool:
    """`sigmoid_slope`, `main()`, `np.array`, `trainModel`, or anything in quotes: a name worth pointing at."""
    return quoted or "_" in name or "(" in name or "." in name or any(ch.isdigit() for ch in name) or (
        name[:1].islower() and any(ch.isupper() for ch in name[1:]))


def short_caption(text: str, max_words: int = MAX_WORDS) -> str:
    """The caption to put on a spotlight box: `text` when it has at most `max_words` words, else a short pointer for
    what it asks: "Type below <name>" / "Type above <name>" (it names where, by a code name), "Type it here",
    "Run it here", "Look here", "Click here"."""
    if len((text or "").split()) <= max_words:
        return text
    typ, run = _TYPE.search(text), _RUN.search(text)
    if run and (typ is None or run.start() < typ.start()):
        return "Run it here"
    if typ:
        for m in _ANCHOR.finditer(text):
            name = m.group(3).rstrip(".")
            if name and _code_name(name, bool(m.group(2))):
                where = "above" if m.group(1).lower() in ("above", "before") else "below"
                return f"Type {where} {name[:32]}"
        return "Type it here"
    look, click = _LOOK.search(text), _CLICK.search(text)
    if click and (look is None or click.start() < look.start()):
        return "Click here"
    return "Look here"


# ------------------------------------------------------------------ V9: a caption never turns the boxed code into a to-do
# Desktop test 9 (video lesson, s3): the coach boxed `fig, axes = plt.subplots(1, 10, figsize=(10, 10))` as "Assign fig,
# axes here": the model paraphrased the line already on screen into an instruction. A caption says what to do AT that
# spot; when it only restates code the box already sits on, the box is a read-only pointer: "Look here".

LOOK_CAPTION = "Look here"
_WRITE_VERBS = {"assign", "add", "type", "write", "define", "create", "call", "import", "set", "declare", "initialize",
                "initialise", "insert", "enter", "put", "make", "build", "load", "plot", "print", "compute", "calculate",
                "store", "save", "return", "use", "instantiate", "append", "implement", "code", "paste", "show",
                "display", "fit", "train", "compile", "evaluate", "predict", "reshape", "normalize", "normalise",
                "split", "draw", "loop", "iterate", "unpack", "construct", "configure"}
_CHANGE_VERBS = {"change", "replace", "rename", "update", "edit", "fix", "switch", "turn"}
# a caption that says WHERE relative to the line ("Type below sigmoid_slope", "Paste the network under this line")
# points at a place, it doesn't restate the line: always kept
_PLACE_WORDS = {"below", "above", "under", "after", "before", "beneath", "next", "between", "inside", "end", "start",
                "top", "bottom", "following", "previous", "instead"}
_FILLER = {"here", "the", "a", "an", "to", "this", "that", "these", "those", "line", "lines", "it", "them", "in", "on",
           "of", "and", "or", "with", "for", "at", "into", "your", "my", "its", "variable", "variables", "function",
           "value", "values", "from", "as", "by", "statement", "code", "now", "again", "cell", "s", "be", "is", "are",
           "so", "then", "both", "each", "all", "result", "results"}
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+(?:\.\d+)?")


def _squash(text: str) -> str:
    return re.sub(r"[\s`'\"“”‘’]+", "", text or "").lower()


def restates_line(caption: str | None, line: str | None) -> bool:
    """Does `caption` only tell the learner to write what `line` (the boxed line's text) already holds? "Assign fig, axes
    here" on `fig, axes = plt.subplots(...)`, "Import numpy here" on `import numpy as np`, "Change to x = 1" on `x = 1`.
    False for a real action ("Add a comma here", "Lower the learning rate", "Set lr to 0.1" on `lr = 0.5`), a place
    ("Type below sigmoid_slope"), a bare pointer ("Type it here", "Look here") or no line text."""
    cap, text = (caption or "").strip(), (line or "").strip()
    if not cap or not text:
        return False
    words = [w.lower() for w in _WORD.findall(cap)]
    if not words or any(w in _PLACE_WORDS for w in words):
        return False
    if words[0] in _CHANGE_VERBS:  # "Change to <code>": done when the line already is that code
        m = re.search(r"\b(?:to|with|into)\s+(.+?)\s*(?:\bhere)?\s*$", cap, re.I)
        return bool(m) and len(_squash(m.group(1))) >= 2 and _squash(m.group(1)) in _squash(text)
    if words[0] not in _WRITE_VERBS:
        return False
    have = {w.lower() for w in _WORD.findall(text)}
    content = [w for w in words[1:] if w not in _FILLER and w not in _WRITE_VERBS]
    return bool(content) and all(w in have for w in content)


def for_line(caption: str | None, line: str | None) -> str | None:
    """The caption to show on a box over `line`: `caption`, or "Look here" when it restates that line's code (V9)."""
    return LOOK_CAPTION if restates_line(caption, line) else caption

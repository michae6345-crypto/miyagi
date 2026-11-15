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

"""What a card says to the learner (Miyagi desktop test 5, "Build a neural network in Python", 02:11-02:21).

Hooks in LessonSession (kept tiny for merges):
- `emit()`: `card_copy.learner_text(self, type_, payload)` for every `card` and `offtrack` (in place, so the voice line
  `_say` reads afterwards is the same text):
  1. No internals: a card never mentions OCR, screen reading, screenshots, model names, check ids / patterns or "the
     judge". t5 02:21:36 step 10: "Epoch 0 line is garbled in OCR; confirm it reads 'epoch 0…'". Unreadable output
     becomes "I can't read the terminal yet. Make the terminal panel taller, or press Run it for me."; other internal
     clauses are dropped.
  2. A "Not yet" never says code is missing when the file has it. t5 02:20:57 step 9: "Add the training loop to
     main.py, then rerun python3 main.py…" while main.py had the loop. The step's file (VS Code's buffer, else the
     disk) is read before the wording goes out.
  It also remembers the last "Not yet" of the step (`_last_not_yet`), which Hint starts from.
- `_action("hint")`: `await card_copy.diagnosed_hint(self, step)` first (lesson mode). t5 02:16:34: Check had just said
  "change np.exp(x) to np.exp(-x)", and Hint asked "Which line of main.py defines sigmoid, and is it there yet?". Hint
  now starts from what is known: the last diagnosis's diff, else the last "Not yet"'s "change A to B", else the line
  of the file that differs from the step's code. The first press names the line and the thing to look at ("Look at
  the sign inside np.exp on line 20 of main.py."), the next gives the fix ("On line 20, change np.exp(x) to
  np.exp(-x), then save main.py."), with a box on that line.
"""
from __future__ import annotations

import difflib
import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger("orchestrator.card_copy")

TEXT_FIELDS = ("title", "body", "guidingQuestion", "where")

# How Miyagi reads / grades, never shown. A reading failure replaces the whole text with the "can't read" line; any
# other internal clause is dropped. Kept narrow: "model", "regex", "LLM" are real lesson words (an NN lesson's model).
READ_FAIL = re.compile(r"\b(?:OCR(?:'?d|'?s)?|garbled|misread(?:s|ing)?|mis-read|illegible|unreadable)\b", re.I)
INTERNAL = re.compile(
    r"\b(?:screen[- ]?(?:reader|reading|text|capture|scrape)s?|on-screen text|screenshots?|accessibility (?:text|tree)"
    r"|AX tree|set-of-mark|bounding box(?:es)?|vision model|claude[- ](?:haiku|sonnet|opus)[\w.-]*"
    r"|(?:the|my) (?:judge|grader)|check (?:ids?|patterns?|regex(?:es)?|labels?)|checkIds?|pattern[- ]match\w*"
    r"|(?:the )?checks? (?:looks?|search(?:es)?|scans?) for|s\d+[cp]\d+)\b", re.I)
TERMINAL_WORDS = re.compile(r"\b(?:terminal|output|print(?:s|ed)?|console|traceback|epoch)\b", re.I)

# "Add the training loop to main.py", "type it into main.py", "X isn't typed yet", "missing from main.py"
_FILE = r"[\w./-]+\.(?:py|ipynb|js|jsx|ts|tsx|html|css|json|md|txt|sh|rb|go|rs|java|c|cpp)\b"
CODE_CLAIM = re.compile(
    rf"\b(?:add|type|write|insert|paste|put|copy)\b[^.;]{{0,60}}?\b(?:to|in|into|at the (?:end|bottom) of)\s+(?:your\s+)?{_FILE}"
    rf"|\b(?:not|isn't|is not|aren't|are not|hasn't been|haven't been)\s+(?:yet\s+)?(?:typed|written|added|defined)\b"
    rf"|\b(?:not|isn't|is not|aren't|are not)\s+(?:yet\s+)?in\s+{_FILE}|\bmissing (?:from|in)\s+{_FILE}", re.I)
# "In sigmoid(), change np.exp(x) to np.exp(-x) and save main.py" -> (np.exp(x), np.exp(-x))
CHANGE = re.compile(r"\b(?:change|replace|turn)\s+(?P<a>\S.*?)\s+(?:to|with|into)\s+(?P<b>\S.*?)"
                    r"(?=\s+(?:and|then|so|on line|in)\b|[,;]|\.(?:\s|$)|$)", re.I)
QUOTES = "`'\"“”‘’"


def _sq(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _nocomment(line: str) -> str:
    """`x = 1  # note` -> `x = 1` (a learner may skip the step's comments; quotes before the # keep the line as is)."""
    m = re.search(r"\s#[^'\"]*$", line)
    return line[:m.start()] if m and not line.lstrip().startswith("#") else line


def _code_lines(code: str) -> list[str]:
    return [ln for ln in (code or "").splitlines() if ln.strip() and not ln.strip().startswith("#")]


def code_in(code: str, text: str) -> bool:
    """Every meaningful line of `code` is a line of `text` (spacing and trailing comments ignored)."""
    want = [_sq(_nocomment(ln)) for ln in _code_lines(code)]
    have = {_sq(_nocomment(ln)) for ln in (text or "").splitlines() if ln.strip()}
    return bool(want) and all(w in have for w in want)


def step_file_text(s: Any, step: dict) -> tuple[str, str]:
    """(file name, text) of the step's file: VS Code's buffer (unsaved edits included), else the disk."""
    from . import workspace as wsmod

    name = s._step_file(step) or ""
    p = wsmod.resolve_file(s.workdir, name) if name and getattr(s, "workdir", None) else None
    if p is None:
        return Path(name).name, ""
    try:
        text = s._buffers.text(p)
        return p.name, p.read_text(errors="replace") if text is None else text
    except OSError:
        return p.name, ""


# ------------------------------------------------------------------ 1. no internals
def cant_read(terminal: bool, run_it: bool, file: str = "") -> str:
    if terminal:
        return ("I can't read the terminal yet. Make the terminal panel taller, or press Run it for me." if run_it
                else "I can't read the terminal yet. Make the terminal panel taller.")
    return f"I can't read that part of {file or 'your file'} yet. Save it, then press Check again."


def clean(text: Any, *, terminal: bool, run_it: bool, file: str = "") -> Any:
    """`text` without internals (see READ_FAIL / INTERNAL). Non-strings pass through."""
    if not isinstance(text, str) or not text:
        return text
    if READ_FAIL.search(text):
        return cant_read(terminal or bool(TERMINAL_WORDS.search(text)), run_it, file)
    if not INTERNAL.search(text):
        return text
    keep = [p for p in re.split(r"(?<=[.!?;])\s+|\s+[—–]\s+", text) if p.strip() and not INTERNAL.search(p)]
    out = " ".join(keep).strip().rstrip(";").strip()
    return out[:1].upper() + out[1:]


def _clean_fields(s: Any, step: dict | None, payload: dict) -> None:
    if not any(isinstance(v := payload.get(k), str) and (READ_FAIL.search(v) or INTERNAL.search(v)) for k in TEXT_FIELDS):
        return  # the usual case: nothing to clean
    run_step = bool(step is not None and s._run_command(step))
    actions = payload.get("actions") or []
    run_it = "run_command" in actions or (run_step and bool(getattr(s, "lesson_mode", False)))
    file = Path(s._step_file(step) or "").name if step is not None else ""
    for k in TEXT_FIELDS:
        v = payload.get(k)
        if k != "body" and isinstance(v, str) and READ_FAIL.search(v):  # the body says it; a title stays short
            new = ("Can't read the terminal" if run_step or TERMINAL_WORDS.search(v) else "Can't read it yet") \
                if k == "title" else ""
        else:
            new = clean(v, terminal=run_step, run_it=run_it, file=file)
        if new == v:
            continue
        log.info("card text: %s %r -> %r (no internals on a card)", k, v, new)
        if new:
            payload[k] = new
        elif k != "title":
            payload.pop(k, None)


# ------------------------------------------------------------------ 2. a true "Not yet"
def is_not_yet(card: dict) -> bool:
    return card.get("title") == "Not yet" or card.get("verdict") == "not_done"


def true_not_yet(s: Any, step: dict, card: dict) -> str | None:
    """The body to send instead when this "Not yet" says code is missing but the step's file has it; else None."""
    body = card.get("body") or ""
    if not CODE_CLAIM.search(body):
        return None
    name, text = step_file_text(s, step)
    if not text.strip():
        return None
    if cmd := s._run_command(step):  # a run step: the code it runs is the earlier steps' code in this file
        earlier = [st for st in s.steps[:s.idx] if (st.get("code") or "").strip() and not s._run_command(st)
                   and Path(s._step_file(st) or "").name == name]
        if not earlier or not all(code_in(st["code"], text) for st in earlier):
            return None
        tail = ", or press Run it for me." if "run_command" in (card.get("actions") or []) else "."
        return f"Your code is already in {name}. Run {cmd} again{tail}"
    if not code_in(step.get("code") or "", text):
        return None
    if dirty := s._dirty_step_file(step):
        return f"Your code is in {dirty}. Save it with ⌘S so I can check it."
    return f"Your code is in {name}. Press Check again."


def learner_text(s: Any, type_: str, payload: dict) -> dict:
    """The card / off-track as the learner may read it (in place). Never raises: a failure sends the card as is."""
    if not isinstance(payload, dict):
        return payload
    try:
        step = s.step
        mine = step is not None and payload.get("stepId") in (None, step.get("id"))
        if type_ == "card" and mine and is_not_yet(payload):
            if (body := true_not_yet(s, step, payload)) is not None:
                log.info("not yet: %r says code is missing but %s has it; sending %r", payload.get("body"),
                         s._step_file(step), body)
                payload["body"] = body
        _clean_fields(s, step if mine else None, payload)
        if type_ == "card" and mine and is_not_yet(payload):
            s._last_not_yet = {"stepId": step["id"], "gen": s.step_gen, "body": payload.get("body") or ""}
    except Exception:  # noqa: BLE001 - wording is a refinement: the card goes out as it was
        log.exception("card_copy failed; card sent as is")
    return payload


# ------------------------------------------------------------------ 3. Hint from what is known
def _find_line(lines: list[str], target: str, near: Any = None) -> int | None:
    """1-based line of `target` in `lines` (spacing ignored, else >= 0.85 alike), the one nearest `near`."""
    t = _sq(target)
    if not t:
        return None
    hits = [i for i, ln in enumerate(lines) if _sq(ln) == t]
    if not hits:
        scored = [(difflib.SequenceMatcher(None, t, _sq(ln), autojunk=False).ratio(), i) for i, ln in enumerate(lines)
                  if ln.strip()]
        best = max(scored, default=(0.0, -1))
        hits = [best[1]] if best[0] >= 0.85 else []
    if not hits:
        return None
    if isinstance(near, int) and near > 0:
        hits.sort(key=lambda i: abs(i + 1 - near))
    return hits[0] + 1


def _first_change(yours: str, expected: str) -> tuple[str, str] | None:
    """The first changed line pair of a diagnosis diff (yours line, expected line); None for a pure add / delete."""
    ys, es = (yours or "").splitlines(), (expected or "").splitlines()
    ops = difflib.SequenceMatcher(a=[x.strip() for x in ys], b=[x.strip() for x in es], autojunk=False).get_opcodes()
    for tag, i1, i2, j1, j2 in ops:
        if tag == "replace":
            pairs = [(difflib.SequenceMatcher(None, ys[i].strip(), es[j].strip()).ratio(), i, j)
                     for i in range(i1, i2) for j in range(j1, j2)]
            _, i, j = max(pairs)
            return ys[i], es[j]
        if tag != "equal":
            return None
    return None


def _step_mismatch(s: Any, step: dict, lines: list[str]) -> tuple[int, str, str] | None:
    """Lesson mode: the first line of the step's code that isn't in the file, and the file line that is almost it
    (a line no step of the lesson has: the learner's version). None when the step isn't started or nothing is close."""
    want = _code_lines(step.get("code") or "")
    have = [_sq(_nocomment(ln)) for ln in lines]
    have_set = set(have)
    if not any(_sq(_nocomment(w)) in have_set for w in want):
        return None  # not started: the coach's "Type this" hint
    known = {_sq(_nocomment(ln)) for st in s.steps for ln in _code_lines(st.get("code") or "")}
    for w in want:
        ws = _sq(_nocomment(w))
        if ws in have_set:
            continue
        best = max(((difflib.SequenceMatcher(None, ws, h, autojunk=False).ratio(), i) for i, h in enumerate(have)
                    if h and h not in known), default=(0.0, -1))
        if best[0] >= 0.75:
            return best[1] + 1, lines[best[1]], w
    return None


def focus(s: Any, step: dict, lines: list[str]) -> tuple[int, str, str, str] | None:
    """(line number, the learner's line, the line it should be, source) for Hint, best known first."""
    known = {_sq(_nocomment(ln)) for ln in _code_lines(step.get("code") or "")}
    d = (s.last_offtrack or {}).get("diff") or {}
    if (pair := _first_change(d.get("yours") or "", d.get("expected") or "")) is not None:
        if n := _find_line(lines, pair[0], d.get("line")):
            return n, lines[n - 1], pair[1], "diagnosis"
    nyt = getattr(s, "_last_not_yet", None) or {}
    if nyt.get("stepId") == step.get("id") and nyt.get("gen") == s.step_gen and (m := CHANGE.search(nyt.get("body") or "")):
        a, b = m.group("a").strip(QUOTES + " "), m.group("b").strip(QUOTES + " ")
        n = next((i + 1 for i, ln in enumerate(lines) if a and a in ln and _sq(_nocomment(ln)) not in known), None)
        if n and a != b:
            return n, lines[n - 1], lines[n - 1].replace(a, b, 1), "not yet"
    if not s.passed and (mm := _step_mismatch(s, step, lines)) is not None:
        return (*mm, "step code")
    return None


def _term(text: str, i: int, j: int) -> tuple[int, int]:
    """[i, j) widened to the innermost `name(...)` / `(...)` around it, else to the whitespace-free run."""
    best: tuple[int, int] | None = None
    for m in re.finditer(r"[\w.]*\(", text):
        depth, end = 0, None
        for k in range(m.end() - 1, len(text)):
            if text[k] == "(":
                depth += 1
            elif text[k] == ")":
                depth -= 1
                if depth == 0:
                    end = k + 1
                    break
        if end is None:
            continue
        inside = (m.start() < i < end) if i == j else (m.start() <= i and j <= end)
        if inside and (best is None or end - m.start() < best[1] - best[0]):
            best = (m.start(), end)
    if best:
        return best
    a, b = i, max(j, i)
    while a > 0 and not text[a - 1].isspace():
        a -= 1
    while b < len(text) and not text[b].isspace():
        b += 1
    return a, b


def words(yours: str, expected: str) -> tuple[str, str, str]:
    """(what to look at, the fix, the box caption) for one line: ("the sign inside np.exp", "change np.exp(x) to
    np.exp(-x)", "Change to np.exp(-x)")."""
    y, e = yours.strip(), expected.strip()
    ops = [op for op in difflib.SequenceMatcher(None, y, e, autojunk=False).get_opcodes() if op[0] != "equal"]
    if not ops or _sq(y) == _sq(e):
        return "the spacing", f"match the spacing of the step's code: {e}", "Fix the spacing"
    i1, i2 = min(op[1] for op in ops), max(op[2] for op in ops)
    j1, j2 = min(op[3] for op in ops), max(op[4] for op in ops)
    ya, yb = _term(y, i1, i2)
    ea, eb = _term(e, j1, j2)
    yt, et = y[ya:yb].strip(), e[ea:eb].strip()
    if not yt or not et or len(yt) > 40 or len(et) > 48:
        return "", f"make it read {e}" if len(e) <= 70 else "copy it from the step's code", "Change this line"
    changed = "".join(y[a:b] for _, a, b, _, _ in ops) + "".join(e[c:d] for _, _, _, c, d in ops)
    if _sq(changed) and set(_sq(changed)) <= set("+-"):
        call = re.match(r"([\w.]+)\(", yt)
        look = f"the sign inside {call.group(1)}" if call else f"the sign in {yt}"
    else:
        look = yt
    cap = f"Change to {et}"
    return look, f"change {yt} to {et}", cap if len(cap) <= 40 else "Change this line"


async def diagnosed_hint(s: Any, step: dict) -> bool:
    """Lesson mode Hint from what is already known (see the module doc). True = answered (card + box)."""
    try:
        if not getattr(s, "lesson_mode", False) or s._run_command(step):
            return False
        name, text = step_file_text(s, step)
        lines = text.splitlines()
        f = focus(s, step, lines) if lines else None
        if f is None:
            return False
        n, yours, expected, src = f
        key = (step["id"], yours.strip(), expected.strip())
        prev = getattr(s, "_hint_focus", None)
        presses = prev[1] + 1 if prev and prev[0] == key else 0
        s._hint_focus = (key, presses)
        look, fix, cap = words(yours, expected)
        if presses == 0:  # first press: the line and the thing to look at, not the answer
            body = f"Look at {look} on line {n} of {name}." if look else f"Look closely at line {n} of {name}."
            card = {"stepId": step["id"], "kind": "hint", "title": f"Look at line {n}", "body": body,
                    "level": 0, "levelName": "question"}
            cap = "Look here"
        else:  # next press: the fix
            card = {"stepId": step["id"], "kind": "hint", "title": f"Fix line {n}",
                    "body": f"On line {n}, {fix}, then save {name}.", "level": 3, "levelName": "diff"}
    except Exception:  # noqa: BLE001 - the coach's own hint answers instead
        log.exception("diagnosed hint failed")
        return False
    log.info("hint from the %s: line %d of %s (%s)", src, n, name, "look" if presses == 0 else "fix")
    await s._emit_card(card)
    spot = s._locate(re.escape(yours.strip()), None, cap)
    if spot:
        s._action_spot = True
        s.spot_track = (re.escape(yours.strip()), None, cap)
        await s._show_spot(spot)
    return True

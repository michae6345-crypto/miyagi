"""Hint ladder and apply_fix. Nothing here ever writes to the learner's files.

Levels (gentlest first): 0 guiding question → 1 video timestamp → 2 paper → 3 diff.
"""

from __future__ import annotations

import difflib
import json
import re
import textwrap

from .common import fmt_t, get_lesson
from .diagnose import LAST
from .explain import match_explanation
from .playbook import BY_ID, CITATIONS, GUIDING_QUESTIONS
from .pointing import code_visible, deterministic_targets, where_hint
from .screen import ScreenContext

LEVELS = ("question", "video", "paper", "diff")



PAPER_NOTES: dict[str, str] = {
    "pinn_missing_ic_bc": "Raissi et al. train PINNs on the sum of two terms: the misfit to the initial/boundary data and the PDE residual. The data term is what fixes which solution the network learns.",
    "pinn_convection_large_beta": "Krishnapriyan et al. show PINNs fail on convection once β is large, and fix it with curriculum regularization: solve small β first, then raise it step by step.",
    "pinn_loss_imbalance": "Wang, Teng & Perdikaris show the residual's gradients can swamp the boundary terms, and rebalance the loss weights during training.",
    "lr_too_high": "Smith's LR range test: sweep the learning rate upward for a few hundred steps and pick one just below where the loss starts to rise.",
}


def _card(step: dict, level: int, title: str, body: str, **extra) -> dict:
    return {"stepId": step.get("id"), "kind": "hint", "title": title, "body": body, "level": level, "levelName": LEVELS[level], **extra}


def _pid_from_citation(card: dict) -> str | None:
    """Recover the playbook entry from a public card (no `_meta`) via its citation URL."""
    url = (card.get("citation") or {}).get("url")
    return next((m.id for m in BY_ID.values() if url and CITATIONS[m.citation_id]["url"] == url), None)


def hint(step: dict, level: int, last_offtrack: dict | None = None, screen: ScreenContext | None = None) -> dict:
    """Return a `card` (kind "hint") for `level` (clamped to 0..3).

    Level 3 carries `diff` and offers "apply_fix"; the fix is applied only after the
    learner accepts it (see `apply_fix`). Extra fields (`level`, `diff`, `citation`,
    `actions`) are additive to the contract's `card` payload.

    With `screen`, the card also carries `targets` (the line it is about, exact match, no model) or
    `where` (where to go first); levels 0/1 lead with `where` when the code isn't on screen.
    """
    card = _hint(step, level, last_offtrack)
    if screen is None:
        return card
    last = last_offtrack or LAST.get(step.get("id", "")) or {}
    targets = deterministic_targets(step, screen, last)
    if targets:
        card["targets"] = targets
        return card
    card["where"] = where_hint(step, last, screen)
    if card["level"] <= 1 and not code_visible(step, screen, "", last):
        card["title"] = "Open your code first"
        card["body"] = f"{card['where']}. Then: {card['body']}"
    return card


def _hint(step: dict, level: int, last_offtrack: dict | None = None) -> dict:
    level = max(0, min(int(level), 3))
    last = last_offtrack or LAST.get(step.get("id", "")) or {}
    pid = (last.get("_meta") or {}).get("playbook_id") or _pid_from_citation(last)
    mode = BY_ID.get(pid) if pid else None
    hints = step.get("hints") or []

    if level == 0:
        # about THE issue just diagnosed: the card's own question, else the playbook's, else the step's
        q = last.get("guidingQuestion") or (GUIDING_QUESTIONS.get(pid) if pid else None)
        if not q and last.get("title"):  # an older or cached card without a question: still about THIS issue
            q = f"{last['title'].rstrip('.')}: what in your code makes that happen, and which value or line would change it?"
        return _card(step, 0, "A question first", q or (hints[0] if hints else f"What does this step need that your code doesn't do yet? ({step.get('instructions', '')})"))

    if level == 1:
        # the moment in the video about THIS issue; else the step's own segment
        exps = step.get("explanations") or []
        about = " ".join(str(last.get(k, "")) for k in ("title", "body", "guidingQuestion"))
        idx = match_explanation(step, about, min_overlap=2) if last else (0 if exps else -1)
        if idx >= 0 and exps[idx].get("t") is not None:
            e = exps[idx]
            return _card(step, 1, "Rewatch this part", f"The tutorial covers {e.get('topic', 'this')} here.", videoJump={"t": float(e["t"]), "label": f"Explained at {fmt_t(e['t'])}"})
        v = step.get("video") or {}
        if v.get("start") is not None:
            return _card(step, 1, "Rewatch this step", "Watch how the tutorial runs this step and compare its settings with yours.", videoJump={"t": float(v["start"]), "label": f"Step starts at {fmt_t(v['start'])}"})
        return _hint(step, 2, last)

    if level == 2:
        cit = last.get("citation") or (CITATIONS[mode.citation_id] if mode else None)
        if not cit:
            paper = next((s for s in (get_lesson() or {}).get("sources", []) if s.get("kind") == "paper"), None)
            cit = {"label": paper["title"], "url": paper["url"]} if paper else None
        if not cit:
            return _hint(step, 3, last)
        body = PAPER_NOTES.get(mode.id, mode.fix) if mode else "The linked source explains this in more depth."
        return _card(step, 2, "What the source says", body, citation={"label": cit["label"], "url": cit["url"]})

    diff = last.get("diff")
    if not diff and mode and mode.diff_expected:
        diff = {"expected": mode.diff_expected, "yours": ""}
    if not diff:
        return _card(step, 3, "Compare with the tutorial", hints[-1] if hints else step.get("instructions", ""))
    return _card(step, 3, "Here's the change", "Review it first; nothing changes until you accept.", diff=diff, actions=["apply_fix"])


def _indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def _locate(lines: list[str], yours: list[str], hint_line: int | None) -> int | None:
    """Index where every non-empty `yours` line matches consecutive file lines (ignoring indentation)."""
    want = [y.strip() for y in yours]

    def ok(i: int) -> bool:
        return i + len(want) <= len(lines) and all(lines[i + k].strip() == w for k, w in enumerate(want))

    if hint_line and ok(hint_line - 1):
        return hint_line - 1
    return next((i for i in range(len(lines)) if ok(i)), None)


def _splice(lines: list[str], idx: int, n_old: int, expected: str) -> list[str]:
    """Replace lines[idx:idx+n_old] with `expected`, re-indented, re-nesting the old block body if needed."""
    base = _indent(lines[idx])
    exp = textwrap.dedent(expected).strip("\n").splitlines()
    repl = [(base + e if e.strip() else "") + "\n" for e in exp]
    rest = lines[idx + n_old :]

    old_last = lines[idx + n_old - 1]
    new_last = repl[-1] if repl else "\n"
    if old_last.rstrip().endswith(":") and new_last.rstrip().endswith(":"):
        # the old header's body follows; move it under the new (possibly deeper) header
        shift = len(_indent(new_last)) - len(_indent(old_last))
        old_ind = len(_indent(old_last))
        body_end = 0
        for k, l in enumerate(rest):
            if l.strip() and len(_indent(l)) <= old_ind:
                break
            body_end = k + 1
        if shift > 0:
            rest = [(" " * shift + l if l.strip() else l) for l in rest[:body_end]] + rest[body_end:]
        elif shift < 0:
            rest = [(l[-shift:] if l.strip() and l.startswith(" " * -shift) else l) for l in rest[:body_end]] + rest[body_end:]
    return lines[:idx] + repl + rest


GUTTER = re.compile(r"^\s*\d{1,5}\s{1,4}(?=\S)")
GUTTER_ONLY = re.compile(r"^\s*\d{1,5}\s*$")  # an OCR'd empty line: just its line number
FUZZY_MIN = 0.8


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _ratio(a: str, b: str) -> float:
    a, b = _squash(GUTTER.sub("", a)), _squash(b)
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() if a and b else 0.0


MARKER_ONLY = re.compile(r"^\s*(<{5,}|={5,}|>{5,})[^\n]*$")
GUTTER_NUM = re.compile(r"^\s*(\d{1,5})(?:\s|$)")


def _span_from_gutter(lines: list[str], yours: list[str]) -> tuple[int, int] | None:
    """OCR'd editor lines carry the editor's own line numbers ("12 app.post(..."): use them as file
    line numbers when the text there agrees (S9 G3: OCR dropped the `=======` row entirely)."""
    nums = [int(m.group(1)) for y in yours if (m := GUTTER_NUM.match(y))]
    if len(nums) < 2 or nums != sorted(nums) or len(nums) < 0.6 * len(yours):
        return None
    start, end = nums[0] - 1, nums[-1]
    if not (0 <= start < end <= len(lines)):
        return None
    pairs = []
    for y in yours:
        m = GUTTER_NUM.match(y)
        text = GUTTER.sub("", y)
        if m and text.strip() and not GUTTER_ONLY.match(y):
            pairs.append((text, lines[int(m.group(1)) - 1]))
    if not pairs:
        return None
    score = sum(_ratio(a, b) for a, b in pairs) / len(pairs)
    return (start, end) if score >= 0.7 else None


def _locate_span(lines: list[str], yours: list[str], hint_line: int | None) -> tuple[int, int] | None:
    """File span [start, end) holding `yours`: exact (indent-insensitive), then without OCR gutter
    numbers, then the editor's own gutter numbers, then line-by-line fuzzy (OCR errors like `<<<<<`
    for `<<<<<<<`, `=` for `=>`), skipping up to 2 blank / marker-only rows OCR dropped."""
    if (g := _span_from_gutter(lines, yours)) is not None and _locate(lines, yours, hint_line) is None:
        exact_stripped = _locate(lines, [GUTTER.sub("", y) for y in yours if not GUTTER_ONLY.match(y)], hint_line)
        if exact_stripped is None:
            return g
    yours = [y for y in yours if not GUTTER_ONLY.match(y)]
    if not yours:
        return None
    for v in (yours, [GUTTER.sub("", y) for y in yours]):
        if (i := _locate(lines, v, hint_line)) is not None:
            return i, i + len(v)
    best, best_score = None, 0.0
    for s0 in range(len(lines)):
        if _ratio(yours[0], lines[s0]) < FUZZY_MIN:
            continue
        j, total, skipped = s0, 0.0, 0
        for y in yours:
            while j < len(lines) and (not lines[j].strip() or MARKER_ONLY.match(lines[j])) and skipped < 2 and _ratio(y, lines[j]) < FUZZY_MIN:
                j += 1  # a blank / conflict-marker row the OCR dropped
                skipped += 1
            if j >= len(lines) or (r := _ratio(y, lines[j])) < FUZZY_MIN:
                break
            total += r
            j += 1
        else:
            if total > best_score:
                best, best_score = (s0, j), total
    return best


def _widen(lines: list[str], start: int, end: int, expected: str) -> tuple[int, int]:
    """If `expected` rewrites more lines than `yours` covered and its extra lines already sit right
    next to the span, include them (S9 G1: 1 todo line replaced by 4 → three duplicated picks)."""
    exp = [ln.strip() for ln in expected.splitlines() if ln.strip()]
    if len(exp) <= end - start:
        return start, end

    def related(line: str) -> bool:  # an expected line rewrites it (`pick abc Cleanup` → `squash abc Cleanup`)
        t = line.strip()
        return bool(t) and any(t == e or _ratio(t, e) >= 0.7 for e in exp)

    while start > 0 and related(lines[start - 1]) and end - start < len(exp):
        start -= 1
    while end < len(lines) and related(lines[end]) and end - start < len(exp):
        end += 1
    return start, end


def _duplicates_neighbours(lines: list[str], start: int, end: int, expected: str) -> list[str]:
    """Lines the patch would repeat: a contiguous run of >= 2 lines where expected's first lines equal
    the lines right above the span, or its last lines equal the lines right below. Single repeated
    lines (`});`, `return x;`, `res.json(...)`) are normal code (S9: false positive on G3)."""
    exp = [ln.strip() for ln in expected.splitlines() if ln.strip()]
    above = [ln.strip() for ln in lines[:start] if ln.strip()]
    below = [ln.strip() for ln in lines[end:] if ln.strip()]
    for k in range(len(exp), 1, -1):
        if len(above) >= k and exp[:k] == above[-k:]:
            return exp[:k]
        if len(below) >= k and exp[-k:] == below[:k]:
            return exp[-k:]
    return []


def _rebase_todo_error(old: str, new: str) -> str | None:
    """git-rebase-todo: every commit must still appear exactly once."""
    def hashes(t: str) -> list[str]:
        return [p[1] for ln in t.splitlines() if (p := ln.split()) and len(p) > 1 and not ln.lstrip().startswith("#") and p[0] not in ("exec", "x", "break", "label", "reset")]

    a, b = hashes(old), hashes(new)
    if sorted(a) != sorted(b) or len(set(b)) != len(b):
        return "the rebase todo would lose or repeat a commit"
    return None


def _python_ok(src: str, name: str) -> str | None:
    """None if `src` compiles; IPython magics/shell lines (%, !) are blanked first."""
    body = "\n".join("" if ln.lstrip().startswith(("%", "!")) else ln for ln in src.splitlines())
    try:
        compile(body, name, "exec")
    except SyntaxError as e:
        return f"patched file would not compile: {e.msg} (line {e.lineno})"
    return None


def _patch(text: str, yours: str, expected: str, line: int | None, name: str, python: bool) -> tuple[str | None, str, str | None]:
    """(new_text, unified_diff, error) for one text buffer."""
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    y = [ln for ln in yours.strip("\n").splitlines() if ln.strip()]
    span = _locate_span(lines, y, line)
    if span is None:
        return None, "", "learner's lines not found in file"
    start, end = _widen(lines, *span, expected)
    todo = name.rsplit("/", 1)[-1] == "git-rebase-todo"  # judged by the stricter commit check below
    if not todo and (dup := _duplicates_neighbours(lines, start, end, expected)):
        return None, "", f"the patch would duplicate lines already next to it: {dup[0][:60]}"
    new_lines = _splice(lines, start, end - start, expected)
    if new_lines == lines:
        return None, "", "the patch changes nothing"
    candidate = "".join(new_lines)
    unified = "".join(difflib.unified_diff(lines, new_lines, fromfile=f"a/{name}", tofile=f"b/{name}"))
    if todo and (err := _rebase_todo_error(text, candidate)):
        return None, unified, err
    if python and (err := _python_ok(candidate, name)):
        return None, unified, err
    return candidate, unified, None


def _patch_notebook(nb_text: str, yours: str, expected: str, name: str) -> tuple[str | None, str, str | None]:
    """Apply the edit inside the code cell that holds `yours`; re-dump the notebook (indent=1)."""
    try:
        nb = json.loads(nb_text)
    except json.JSONDecodeError:
        return None, "", "notebook is not valid JSON"
    for i, cell in enumerate(nb.get("cells") or []):
        if cell.get("cell_type") != "code":
            continue
        src = cell.get("source") or ""
        text = "".join(src) if isinstance(src, list) else src
        new, unified, err = _patch(text, yours, expected, None, f"{name} [cell {i}]", python=True)
        if err == "learner's lines not found in file":
            continue
        if err:
            return None, unified, err
        new = new.rstrip("\n") if not text.endswith("\n") else new
        cell["source"] = new.splitlines(keepends=True)
        return json.dumps(nb, indent=1, ensure_ascii=False) + "\n", unified, None
    return None, "", "learner's lines not found in any notebook cell"


def apply_fix(diff: dict, file_text: str | None = None) -> dict:
    """Build a proposed patch for the learner to accept. Never writes to disk.

    Returns {"file", "expected", "yours", "unified_diff", "new_text", "error", "requires_confirmation": True}.
    `new_text` is the full file after the change. It is None (and `error` says why) when no
    file text was given, the learner's lines could not be found, the patch changes nothing, or,
    for Python, the result does not compile; the app should then show a "fix it by hand" card.
    Tolerates OCR'd anchors (gutter line numbers, spacing) and edits notebooks cell by cell.
    """
    expected, yours, file = diff.get("expected", ""), diff.get("yours", ""), diff.get("file", "")
    name = f"{file or 'file'}"
    new_text, error, unified = None, None, ""
    if file_text is None:
        error = "no file text"
    elif not yours.strip():
        error = "no anchor line to replace"
    elif name.endswith(".ipynb") or (file_text.lstrip().startswith("{") and '"cells"' in file_text[:20000]):
        new_text, unified, error = _patch_notebook(file_text, yours, expected, name)
    else:
        new_text, unified, error = _patch(file_text, yours, expected, diff.get("line"), name, python=not file or file.endswith(".py"))
    if not unified:
        unified = "".join(
            difflib.unified_diff(
                [l + "\n" for l in yours.splitlines()], [l + "\n" for l in expected.splitlines()], fromfile=f"a/{name}", tofile=f"b/{name}"
            )
        )
    return {
        "file": file,
        "expected": expected,
        "yours": yours,
        "unified_diff": unified,
        "new_text": new_text,
        "error": error,
        "requires_confirmation": True,
    }

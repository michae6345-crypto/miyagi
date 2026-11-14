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
    card["where"] = where_hint(step, last)
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


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _locate_fuzzy(lines: list[str], yours: list[str], hint_line: int | None) -> tuple[int | None, list[str]]:
    """Find `yours` in `lines`: exact (indent-insensitive), then without OCR gutter numbers,
    then whitespace-insensitive (OCR spacing). Returns (index, the yours-lines that matched)."""
    variants = [yours]
    stripped = [GUTTER.sub("", y) for y in yours]
    if stripped != yours:
        variants.append(stripped)
    for v in variants:
        if (i := _locate(lines, v, hint_line)) is not None:
            return i, v
    for v in variants:
        want = [_squash(y) for y in v]
        for i in range(len(lines) - len(want) + 1):
            if all(_squash(lines[i + k]) == w for k, w in enumerate(want)):
                return i, v
    return None, yours


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
    idx, matched = _locate_fuzzy(lines, y, line)
    if idx is None:
        return None, "", "learner's lines not found in file"
    new_lines = _splice(lines, idx, len(matched), expected)
    if new_lines == lines:
        return None, "", "the patch changes nothing"
    candidate = "".join(new_lines)
    unified = "".join(difflib.unified_diff(lines, new_lines, fromfile=f"a/{name}", tofile=f"b/{name}"))
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

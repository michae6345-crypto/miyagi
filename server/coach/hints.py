"""Hint ladder and apply_fix. Nothing here ever writes to the learner's files.

Levels (gentlest first): 0 guiding question → 1 video timestamp → 2 paper → 3 diff.
"""

from __future__ import annotations

import difflib
import textwrap

from .common import fmt_t, get_lesson
from .diagnose import LAST
from .playbook import BY_ID, CITATIONS

LEVELS = ("question", "video", "paper", "diff")

QUESTIONS: dict[str, str] = {
    "pinn_missing_ic_bc": "Many functions satisfy the PDE. What information tells the network which one you want?",
    "pinn_convection_large_beta": "β=30 is the hard version of this PDE. Could the network learn an easier β first and carry those weights forward?",
    "pinn_loss_imbalance": "Look at each loss term separately. Is one of them barely moving?",
    "missing_zero_grad": "What happens to .grad between two calls to loss.backward()?",
    "cuda_on_mac": "Which GPU does this laptop actually have, and what does PyTorch call it?",
    "lr_too_high": "If each step overshoots, what single number controls how far it steps?",
    "pinn_inputs_no_grad": "How does autograd know it should track derivatives with respect to x and t?",
}


PAPER_NOTES: dict[str, str] = {
    "pinn_missing_ic_bc": "Raissi et al. train PINNs on the sum of two terms: the misfit to the initial/boundary data and the PDE residual. The data term is what fixes which solution the network learns.",
    "pinn_convection_large_beta": "Krishnapriyan et al. show PINNs fail on convection once β is large, and fix it with curriculum regularization: solve small β first, then raise it step by step.",
    "pinn_loss_imbalance": "Wang, Teng & Perdikaris show the residual's gradients can swamp the boundary terms, and rebalance the loss weights during training.",
    "lr_too_high": "Smith's LR range test: sweep the learning rate upward for a few hundred steps and pick one just below where the loss starts to rise.",
}


def _card(step: dict, level: int, title: str, body: str, **extra) -> dict:
    return {"stepId": step.get("id"), "kind": "hint", "title": title, "body": body, "level": level, "levelName": LEVELS[level], **extra}


def hint(step: dict, level: int, last_offtrack: dict | None = None) -> dict:
    """Return a `card` (kind "hint") for `level` (clamped to 0..3).

    Level 3 carries `diff` and offers "apply_fix"; the fix is applied only after the
    learner accepts it (see `apply_fix`). Extra fields (`level`, `diff`, `citation`,
    `actions`) are additive to the contract's `card` payload.
    """
    level = max(0, min(int(level), 3))
    last = last_offtrack or LAST.get(step.get("id", "")) or {}
    pid = (last.get("_meta") or {}).get("playbook_id")
    mode = BY_ID.get(pid) if pid else None
    hints = step.get("hints") or []

    if level == 0:
        q = QUESTIONS.get(pid) if pid else None
        return _card(step, 0, "A question first", q or (hints[0] if hints else f"What does this step need that your code doesn't do yet? ({step.get('instructions', '')})"))

    if level == 1:
        exps = [e for e in step.get("explanations") or [] if e.get("t") is not None]
        if exps:
            e = exps[0]
            return _card(step, 1, "Rewatch this part", f"The tutorial covers {e.get('topic', 'this')} here.", videoJump={"t": float(e["t"]), "label": f"Explained at {fmt_t(e['t'])}"})
        v = step.get("video") or {}
        if v.get("start") is not None:
            return _card(step, 1, "Rewatch this step", hints[1] if len(hints) > 1 else "Watch how the tutorial does this step.", videoJump={"t": float(v["start"]), "label": f"Step starts at {fmt_t(v['start'])}"})
        return hint(step, 2, last)

    if level == 2:
        cit = last.get("citation") or (CITATIONS[mode.citation_id] if mode else None)
        if not cit:
            paper = next((s for s in (get_lesson() or {}).get("sources", []) if s.get("kind") == "paper"), None)
            cit = {"label": paper["title"], "url": paper["url"]} if paper else None
        if not cit:
            return hint(step, 3, last)
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


def apply_fix(diff: dict, file_text: str | None = None) -> dict:
    """Build a proposed patch for the learner to accept. Never writes to disk.

    Returns {"file", "expected", "yours", "unified_diff", "new_text", "error", "requires_confirmation": True}.
    `new_text` is the full file after the change. It is None (and `error` says why) when no
    file text was given, the learner's lines could not be found, or, for Python, the result
    does not compile; the app should then show the diff as a "fix it by hand" card.
    """
    expected, yours, file = diff.get("expected", ""), diff.get("yours", ""), diff.get("file", "")
    name = f"{file or 'file'}"
    new_text, error, unified = None, None, ""
    if file_text is None:
        error = "no file text"
    elif not yours.strip():
        error = "no anchor line to replace"
    else:
        lines = file_text.splitlines(keepends=True)
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        y = [l for l in yours.strip("\n").splitlines() if l.strip()]
        idx = _locate(lines, y, diff.get("line"))
        if idx is None:
            error = "learner's lines not found in file"
        else:
            new_lines = _splice(lines, idx, len(y), expected)
            candidate = "".join(new_lines)
            unified = "".join(difflib.unified_diff(lines, new_lines, fromfile=f"a/{name}", tofile=f"b/{name}"))
            if not file or file.endswith(".py"):
                try:
                    compile(candidate, name, "exec")
                except SyntaxError as e:
                    error = f"patched file would not compile: {e.msg} (line {e.lineno})"
            if error is None:
                new_text = candidate
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

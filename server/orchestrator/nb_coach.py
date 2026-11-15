"""Desktop test 10 (Nov 15, video lesson in a Jupyter notebook in VS Code): the coach contradicted its own checks.

- s5: "model.compile called" / "model.fit called" Passed (typed in mnist.ipynb), yet Not yet said "Add history =
  model.fit(...)", twice, mid-training and after it. s6: "view_classify defined" / "model.predict called" Passed, yet
  the off-track said "view_classify cell not written yet · The notebook ends at the model.compile cell": the step's file
  is the video's Untitled.ipynb (not in the folder), so the coach read the screen (the editor scrolled to the top).

Here: the learner's notebook as the coach's source of truth (cells: sources + short output tails, read with
server.checks.notebook's finder), a deterministic guard that drops a "this code is missing" diagnosis whose code's check
passed (rebuilt from the failing rows: "Training is still running", "Run the cell and wait for …"), a "the cell is still
running" read (Check my work mid-training waits instead of diagnosing), and instant cards for deterministic Python
tracebacks (AttributeError with a near-match, NameError, SyntaxError with a line; s2's "load_dat is missing the a" took
~13 s through Claude). Pure helpers + small session reads; nothing here calls a model.
"""

from __future__ import annotations

import difflib
import json
import re
import time
from pathlib import Path
from typing import Any

OUT_TAIL_LINES = 3  # per cell: the last printed lines (the accuracy line, the error) are what a diagnosis needs
OUT_TAIL_CHARS = 240
RUNNING_FRESH_S = 45.0  # a notebook not written for this long is not running (a killed kernel's half-printed epoch)

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")
_MISSING = re.compile(r"\b(add|type|write|insert|paste|create)\b|\bnot (?:yet )?(?:written|defined|typed|there|added|"
                      r"called|in the notebook|in your code)\b|\bmissing\b|\bha(?:s|ve)n'?t (?:been )?(?:written|defined|"
                      r"typed|added|called)|\bha(?:s|ve) not been (?:written|defined|typed|added|called)|\bends at\b|"
                      r"\bno \S+ (?:cell|call|line)\b|\bisn'?t there\b|\bnot written yet\b", re.I)
_OUTPUT_LABEL = re.compile(r"\b(printed|shown|show|output|accuracy|loss|reaches|at least|title|plot|summary|result|"
                           r"error|errors|progress)\b", re.I)
_CODE_LABEL = re.compile(r"\b(called|defined|typed|imported|import|written|created|saved in|assigned|compiled?)\b", re.I)
_OUTPUT_TYPES = {"output_contains", "metric_threshold", "metric_trend", "command_exit_ok", "screen_absent",
                 "output_absent"}


def _text(v: object) -> str:
    return "".join(str(x) for x in v) if isinstance(v, list) else str(v or "")


def _clean(s: str) -> str:
    """Keras progress output: ANSI colours, \\r-overwritten bars, \\b backspaces -> the lines a person sees."""
    s = _ANSI.sub("", s).replace("\b", "")
    return "\n".join(line.rsplit("\r", 1)[-1] for line in s.split("\n"))


# ------------------------------------------------------------------ the notebook
def notebook_step(session: Any, step: dict | None) -> bool:
    if step is None:
        return False
    if getattr(session, "notebook_lesson", False):
        return True
    try:
        f = session._step_file(step) or ""
    except Exception:  # noqa: BLE001
        f = ""
    return any(str(x).lower().endswith(".ipynb") for x in (f, step.get("file") or ""))


def notebook_path(session: Any, step: dict | None) -> Path | None:
    """The learner's notebook for this step: the step's .ipynb in the lesson folder, else the newest .ipynb there
    (test 10: the video's Untitled.ipynb is the learner's mnist.ipynb)."""
    if not notebook_step(session, step):
        return None
    from server.checks.notebook import find_notebook

    names = []
    try:
        names.append(session._step_file(step) or "")
    except Exception:  # noqa: BLE001
        pass
    names.append((step or {}).get("file") or "")
    try:
        return find_notebook(getattr(session, "workdir", None), [n for n in names if n])
    except Exception:  # noqa: BLE001
        return None


def cells(path: Path | str | None) -> list[dict]:
    """[{i, type, source, out (cleaned printed text), error ("Name: value"), count}] for each cell; [] unreadable."""
    if not path:
        return []
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return []
    out: list[dict] = []
    for i, c in enumerate(data.get("cells") or [] if isinstance(data, dict) else []):
        if not isinstance(c, dict):
            continue
        cell = {"i": i, "type": c.get("cell_type"), "source": _text(c.get("source")), "out": "", "error": "",
                "traceback": "", "count": c.get("execution_count")}
        printed = []
        for o in c.get("outputs") or []:
            if not isinstance(o, dict):
                continue
            kind = o.get("output_type")
            if kind == "stream":
                printed.append(_text(o.get("text")))
            elif kind in ("execute_result", "display_data"):
                d = o.get("data") or {}
                if "text/plain" in d:
                    printed.append(_text(d["text/plain"]))
                elif "image/png" in d:
                    printed.append("[image]")
            elif kind == "error":
                cell["error"] = f"{o.get('ename') or 'Error'}: {o.get('evalue') or ''}".strip()
                cell["traceback"] = _clean("\n".join(str(x) for x in o.get("traceback") or []))
        cell["out"] = _clean("".join(printed))
        out.append(cell)
    return out


def _tail(s: str) -> str:
    lines = [ln.rstrip() for ln in s.split("\n") if ln.strip()]
    t = "\n".join(lines[-OUT_TAIL_LINES:])
    return t[-OUT_TAIL_CHARS:]


def render(cs: list[dict], limit: int = 6000) -> str:
    """The cells for the coach: `# %% [cell N]` + source, then its output's last lines as `# [output] …` comments (an
    error as `# [error] …`). Too long: earlier cells lose their outputs, then the START is cut (the step's cell is
    usually the last one; a cut end was how s6 "ended at model.compile")."""
    def one(c: dict, with_out: bool) -> str:
        if c.get("type") != "code":
            return ""
        parts = [f"# %% [cell {c['i']}]", c["source"].rstrip("\n")]
        if with_out and c.get("error"):
            parts.append(f"# [error] {c['error']}"[:OUT_TAIL_CHARS])
        elif with_out and c.get("out"):
            parts += [f"# [output] {ln}" for ln in _tail(c["out"]).split("\n")]
        return "\n".join(parts)

    code = [c for c in cs if c.get("type") == "code"]
    if not code:
        return "# (notebook: no code cells)"
    text = "\n".join(one(c, True) for c in code)
    if len(text) > limit:
        text = "\n".join(one(c, k >= len(code) - 3) for k, c in enumerate(code))
    return text[-limit:] if len(text) > limit else text


def excerpt(session: Any, step: dict | None, limit: int = 6000) -> tuple[str, str] | None:
    """(the notebook's cells for the coach, its file name), or None (not a notebook step / no notebook yet)."""
    p = notebook_path(session, step)
    cs = cells(p) if p is not None else []
    if not cs:
        return None
    return render(cs, limit), p.name


# ------------------------------------------------------------------ is a cell still running?
_EPOCH = re.compile(r"Epoch\s+(\d+)\s*/\s*(\d+)")
_BAR = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s+[━=\.>\-\[]")


def running_in(cs: list[dict]) -> bool:
    """A code cell's output is mid-run: an epoch k/N with k < N, or its last progress bar short of its total (Keras:
    "  12/1875 ━━━…"). Any cell: Run All re-runs training while the cells below still hold their old outputs."""
    for c in cs:
        if c.get("type") != "code" or c.get("error") or not c.get("out"):
            continue
        out = c["out"]
        epochs = _EPOCH.findall(out)
        if epochs and int(epochs[-1][0]) < int(epochs[-1][1]):
            return True
        lines = [ln for ln in out.split("\n") if ln.strip()]
        if lines and (m := _BAR.match(lines[-1])) and int(m.group(1)) < int(m.group(2)):
            return True
    return False


def running(session: Any, step: dict | None, now: float | None = None) -> bool:
    """Is the step's notebook cell still running (training mid-epoch)? Only from a notebook written in the last
    RUNNING_FRESH_S seconds (autosave writes a running cell's output about every second)."""
    p = notebook_path(session, step)
    if p is None:
        return False
    try:
        if (now if now is not None else time.time()) - p.stat().st_mtime > RUNNING_FRESH_S:
            return False
    except OSError:
        return False
    return running_in(cells(p))


def last_metric(cs: list[dict], name: str = "accuracy") -> str | None:
    """The last `accuracy: 0.9861` the cells printed (ANSI stripped), or None."""
    vals = re.findall(rf"\b{re.escape(name)}\s*[:=]\s*([0-9]*\.?[0-9]+)", "\n".join(c.get("out") or "" for c in cs))
    return vals[-1] if vals else None


# ------------------------------------------------------------------ the guard
def _idents(s: str) -> set[str]:
    """Code-looking names in prose or a check's regex: `model.fit`, `view_classify` (dotted / underscored only)."""
    s = re.sub(r"\\[sSdDwWbB][+*?]?", " ", s or "").replace("\\", "")
    return {m.rstrip(".") for m in _IDENT.findall(s) if "_" in m or "." in m}


def _checks_by_id(step: dict) -> dict[str, dict]:
    return {c.get("id"): c for c in (step.get("checks") or []) + (step.get("precision_checks") or []) if c.get("id")}


def _is_output_check(check: dict, row: dict) -> bool:
    t = (check.get("type") or row.get("type") or "").lower()
    if t in _OUTPUT_TYPES or t.startswith("metric"):
        return True
    label = check.get("label") or row.get("label") or ""
    return bool(_OUTPUT_LABEL.search(label)) and not _CODE_LABEL.search(label)


def contradicts(text: str, step: dict, results: list[dict]) -> list[str]:
    """The passed code checks a "this code is missing" diagnosis talks about ([] = no contradiction): the text says
    something is missing / to add it, and names code (model.fit, view_classify) whose own check is Passed."""
    if not text or not _MISSING.search(text):
        return []
    said = _idents(text)
    if not said:
        return []
    by_id = _checks_by_id(step)
    hits = []
    for r in results or []:
        if r.get("status") != "pass":
            continue
        c = {**by_id.get(r.get("checkId"), {}), **r}
        if _is_output_check(c, r):
            continue
        names = _idents(c.get("pattern") or "") | _idents(c.get("label") or "")
        if names & said or any(n.split(".")[-1] in {s.split(".")[-1] for s in said} for n in names if "_" in n):
            hits.append(c.get("label") or c.get("checkId") or "")
    return hits


def rebuilt(session: Any, step: dict, results: list[dict]) -> dict:
    """{title, body} from the failing rows, never asking for code that is there: "Training is still running", "Run the
    cell and wait for the accuracy line", else "Still to do: <labels>"."""
    by_id = _checks_by_id(step)
    failing = [{**by_id.get(r.get("checkId"), {}), **r} for r in results or []
               if r.get("status") != "pass" and not str(r.get("checkId") or "").endswith("-ran")]
    labels = [c.get("label") or "" for c in failing if c.get("label")]
    outputs_only = bool(failing) and all(_is_output_check(c, c) for c in failing)
    if outputs_only:
        if running(session, step):
            return still_running(step)
        what = _wait_for(failing)
        p = notebook_path(session, step)
        cs = cells(p) if p is not None else []
        acc = last_metric(step_cells(cs, step) or cs)
        acc_rows = [c for c in failing if re.search(r"accura", c.get("label") or "", re.I)]
        if acc and acc_rows:
            want = re.findall(r"\d*\.?\d+", acc_rows[0].get("label") or "")
            thr = float(want[-1]) if want else None
            thr = thr / 100 if thr is not None and thr > 1 else thr
            if thr is not None and float(acc) < thr:
                return {"title": "Not yet", "body": f"The run printed accuracy {acc}; this step needs {want[-1]}. "
                                                    f"Compare your cell with the step's code, then run it again."}
            return {"title": "Your code is in",
                    "body": f"The run printed accuracy {acc}. Give me a moment to read it, then press Check my work again."}
        return {"title": "Your code is in", "body": f"Run the cell (Shift+Enter) and wait for {what}."}
    if labels:
        return {"title": "Not yet", "body": "Still to do: " + "; ".join(labels) + "."}
    return {"title": "Not yet", "body": "Run the cell (Shift+Enter) and wait for its output."}


_ERRORISH = re.compile(r"error|traceback|exception", re.I)


def waiting_card(session: Any, step: dict, results: list[dict]) -> dict | None:
    """Check my work in a notebook step whose code rows all pass and whose only failing rows are output / metric rows
    ("Training accuracy reaches 0.95 · waiting for the run's accuracy"): the card at once, from the rows (rebuilt), no
    judge. None: not a notebook step, a code row still fails, an error row fails, or nothing passes yet."""
    if not notebook_step(session, step):
        return None
    by_id = _checks_by_id(step)
    rows = [{**by_id.get(r.get("checkId"), {}), **r} for r in results or []
            if not str(r.get("checkId") or "").endswith("-ran")]
    failing = [c for c in rows if c.get("status") != "pass"]
    code_pass = [c for c in rows if c.get("status") == "pass" and not _is_output_check(c, c)]
    if not failing or not code_pass or not all(_is_output_check(c, c) for c in failing):
        return None
    if any(_ERRORISH.search(f"{c.get('label') or ''} {c.get('detail') or ''}") or c.get("type") == "screen_absent"
           for c in failing):
        return None  # an error is showing: the traceback card / the judge say what it is
    return rebuilt(session, step, results)


def step_cells(cs: list[dict], step: dict) -> list[dict]:
    """The code cells holding this step's code: a source one of its code checks' patterns matches (s5: the
    compile + fit cell, not the evaluate cell's test accuracy below it)."""
    pats = []
    for c in (step.get("checks") or []) + (step.get("precision_checks") or []):
        if c.get("pattern") and not _is_output_check(c, c):
            try:
                pats.append(re.compile(c["pattern"]))
            except re.error:
                continue
    return [c for c in cs if c.get("type") == "code" and any(p.search(c.get("source") or "") for p in pats)]


def _wait_for(failing: list[dict]) -> str:
    label = " ".join(c.get("label") or "" for c in failing).lower()
    if "accura" in label:
        return "the accuracy line"
    if "loss" in label:
        return "the loss line"
    if re.search(r"plot|title|image|figure", label):
        return "the plot"
    return "its output"


def still_running(step: dict) -> dict:
    text = " ".join([step.get("title") or "", step.get("code") or ""]).lower()
    what = "Training is" if re.search(r"\.fit\(|train", text) else "The cell is"
    return {"title": "Still running",
            "body": f"{what} still running. Wait for it to finish (the last epoch's accuracy line), then press Check my "
                    f"work." if what == "Training is" else
                    f"{what} still running. Wait for its output, then press Check my work."}


# ------------------------------------------------------------------ instant traceback cards
_ATTR = re.compile(r"AttributeError: (?:module '([\w.]+)'|'(\w+)' object|type object '(\w+)') has no attribute '(\w+)'")
_NAME = re.compile(r"NameError: name '(\w+)' is not defined")
_SYNTAX = re.compile(r"(SyntaxError|IndentationError): ([^\n]+)")
_LINE = re.compile(r"(?:line|Line) (\d+)")


def notebook_error(session: Any, step: dict | None) -> str:
    """The notebook's last error output (name: value + traceback), '' when none."""
    p = notebook_path(session, step)
    for c in reversed(cells(p) if p is not None else []):
        if c.get("error"):
            return f"{c['traceback']}\n{c['error']}".strip()
    return ""


def _names(code: str) -> list[str]:
    out: list[str] = []
    for m in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", code or ""):
        if m not in out:
            out.append(m)
    return out


def _near(word: str, cands: list[str]) -> str | None:
    cands = [c for c in cands if c != word and len(c) > 2]
    hit = difflib.get_close_matches(word, cands, n=1, cutoff=0.8)
    return hit[0] if hit else None


def _typo_title(wrong: str, right: str) -> str:
    if right.startswith(wrong) and 0 < len(right) - len(wrong) <= 2:
        return f"{wrong} is missing the {right[len(wrong):]}"
    if wrong.startswith(right) and 0 < len(wrong) - len(right) <= 2:
        return f"{wrong} has an extra {wrong[len(right):]}"
    return f"{wrong} should be {right}"


def _line_with(code: str, word: str) -> str:
    return next((ln.strip() for ln in (code or "").split("\n")
                 if re.search(rf"\b{re.escape(word)}\b", ln) and not ln.lstrip().startswith("#")), "")


def traceback_card(step: dict, error_text: str, code: str, *, notebook: bool = False) -> dict | None:
    """The off-track card for a deterministic Python traceback, or None (Claude diagnoses it). Same shape as the
    coach's: title, body (2 sentences), severity, actions; a typo carries diff {yours, expected} so its line is boxed."""
    if not error_text:
        return None
    unit = "cell" if notebook else "code"
    expected = step.get("code") or ""
    last_lines = [ln for ln in error_text.strip().split("\n") if ln.strip()]
    tail = "\n".join(last_lines[-6:])
    card: dict | None = None
    if (m := list(_ATTR.finditer(tail))):
        m = m[-1]
        owner, attr = m.group(1) or m.group(2) or m.group(3), m.group(4)
        cands = re.findall(r"\.([A-Za-z_]\w*)", expected) + _names(expected)
        right = _near(attr, cands)
        if right is None or (code and not re.search(rf"\b{re.escape(attr)}\b", code)):
            return None  # no near-match, or the name is gone from the code (fixed, not rerun): Claude / nothing
        yours = _line_with(code, attr)
        call = "()" if re.search(rf"\b{re.escape(attr)}\s*\(", code or expected) else ""
        what = f"{owner} has no attribute {attr}" if m.group(1) else f"a {owner} has no attribute {attr}"
        card = {"title": _typo_title(attr, right),
                "body": f"The error says {what}, so the name is misspelled and the {unit} crashes. "
                        f"Change it to {right}{call} and run the {unit} again.",
                **({"diff": {"yours": yours, "expected": re.sub(rf"\b{re.escape(attr)}\b", right, yours)}}
                   if yours else {})}
    elif (m := list(_NAME.finditer(tail))):
        name = m[-1].group(1)
        if code and not re.search(rf"\b{re.escape(name)}\b", code):
            return None  # the name is gone from the code (fixed, not rerun)
        right = _near(name, _names(expected) + _names(code))
        yours = _line_with(code, name)
        if right is not None and not re.search(rf"\b{re.escape(name)}\b", expected):
            card = {"title": _typo_title(name, right),
                    "body": f"Python doesn't know the name {name}, so the {unit} stops there. Change it to {right} "
                            f"and run the {unit} again.",
                    **({"diff": {"yours": yours, "expected": re.sub(rf"\b{re.escape(name)}\b", right, yours)}}
                       if yours else {})}
        else:
            defn = next((ln.strip() for ln in expected.split("\n")
                         if re.search(rf"^\s*(def|class)\s+{re.escape(name)}\b|^\s*{re.escape(name)}\s*(,[^=]*)?=|"
                                      rf"\bimport\b.*\b{re.escape(name)}\b", ln)), "")
            defined_in_code = re.search(rf"^\s*(def|class)\s+{re.escape(name)}\b|^\s*{re.escape(name)}\s*(,[^=]*)?=|"
                                        rf"\bimport\b.*\b{re.escape(name)}\b|^\s*\(?[^=\n]*\b{re.escape(name)}\b[^=\n]*\)?\s*=",
                                        code or "", re.M)
            if notebook and defined_in_code:
                card = {"title": f"{name} isn't defined in this kernel yet",
                        "body": f"Your notebook defines {name}, but that cell hasn't run since the kernel started. "
                                f"Run the cells above first (Run All), then this one."}
            elif defn:
                card = {"title": f"{name} isn't defined yet",
                        "body": f"Python doesn't know {name} at this line, so the {unit} stops. Add {defn} above it, "
                                f"then run the {unit} again."}
            else:
                card = {"title": f"{name} isn't defined yet",
                        "body": f"Python doesn't know {name} at this line, so the {unit} stops. Define or import it "
                                f"before it is used, then run the {unit} again."}
    elif (m := list(_SYNTAX.finditer(error_text))):
        kind, msg = m[-1].group(1), m[-1].group(2).strip()
        before = error_text[: m[-1].start()]
        lines = _LINE.findall(before)
        if not lines:
            return None
        n = lines[-1]
        msg = re.sub(r"\s*\(.*line \d+\)\s*$", "", msg)
        what = "indentation" if kind == "IndentationError" else "brackets, quotes and commas"
        card = {"title": f"Syntax error on line {n}",
                "body": f"Python can't read line {n} of the {unit} ({msg}). Compare its {what} with the step's code, "
                        f"then run the {unit} again."}
    if card is None:
        return None
    return {"stepId": step.get("id", ""), "severity": "fail", **card, "actions": ["explain", "show_me", "hint"],
            "_meta": {"route": "traceback"}}

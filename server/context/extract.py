"""Rule-based summaries: no model, no I/O. Each returns (summary, facts) for server.context.store.

    file_outline("nn.py", text)        -> ("nn.py: 42 lines; imports numpy, torch; defs train, loss", {"imports": [...], ...})
    error_lines(text)                  -> ["ModuleNotFoundError: No module named 'torch'"]
    screen_summary("Code", "nn.py - lesson", lines) -> ("Code: nn.py - lesson", {"app": "Code", "errors": [...]})
    checks_summary("s2", results)      -> ("s2 checks: 1 passed, 1 not yet (Run nn.py)", {...})
    card_summary("explain", card)      -> ("coach explain: Why the loss stalls: the rate is too high.", {...})

The text is the learner's (files, screen, terminal): the summaries only quote it, and every prompt that carries them
wraps them as untrusted data (server.untrusted.wrap). Redaction happens in the store, before anything is saved.
"""

from __future__ import annotations

import ast
import json
import re
from typing import Any

SUMMARY_CHARS = 240  # one entry's summary: 1-3 short lines
LIST_MAX = 8  # names kept per fact list (imports, defs, errors)

ERROR_RE = re.compile(
    r"Traceback \(most recent call last\)|^\s*[\w.]*(?:Error|Exception)\b:|(?:^|\s)(?:error|fatal):\s"
    r"|\bERR!|Failed to compile|\bCONFLICT\b|command not found|No such file or directory|Permission denied"
    r"|No module named|is not defined|Segmentation fault|\bFAILED\b",
    re.MULTILINE,
)
_JS_IMPORT = re.compile(r"""^\s*import\s.*?from\s+['"]([^'"]+)['"]|^\s*(?:const|let|var)\s+\w+\s*=\s*require\(\s*['"]([^'"]+)['"]\s*\)""", re.MULTILINE)
_JS_DEF = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function\s*\*?\s*(\w+)|class\s+(\w+)|(?:const|let)\s+(\w+)\s*=\s*(?:async\s*)?\(?[\w,\s]*\)?\s*=>)", re.MULTILINE)
_PY_IMPORT = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.MULTILINE)
_PY_DEF = re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+(\w+)", re.MULTILINE)


def short(text: Any, n: int = SUMMARY_CHARS) -> str:
    """One line (or up to 3), whitespace squashed, at most n characters."""
    lines = [" ".join(str(x).split()) for x in str(text or "").splitlines()]
    s = "\n".join(x for x in lines if x)[: n + 1]
    s = "\n".join(s.splitlines()[:3])
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _uniq(xs: list[str], n: int = LIST_MAX) -> list[str]:
    out: list[str] = []
    for x in xs:
        x = (x or "").strip()
        if x and x not in out:
            out.append(x)
        if len(out) >= n:
            break
    return out


def first_sentence(text: Any, n: int = 160) -> str:
    s = " ".join(str(text or "").split())
    m = re.match(r"(.+?[.!?])(\s|$)", s)
    return short(m.group(1) if m else s, n)


def error_lines(text: Any, n: int = 3) -> list[str]:
    """The lines that read as an error (a traceback's last line rather than its header), newest last, at most n."""
    lines = [ln.rstrip() for ln in str(text or "").splitlines() if ln.strip()]
    hits = [ln.strip() for ln in lines if ERROR_RE.search(ln) and not ln.strip().startswith("Traceback")]
    if not hits and any(ln.strip().startswith("Traceback") for ln in lines):
        hits = [lines[-1].strip()]
    return _uniq([short(h, 160) for h in hits[-n * 2:]], n)[-n:]


# ---------------------------------------------------------------- files
def _py_outline(text: str) -> dict:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError) as e:
        line = getattr(e, "lineno", None)
        return {"imports": _uniq([a or b for a, b in _PY_IMPORT.findall(text)]),
                "defs": _uniq(_PY_DEF.findall(text)),
                "syntax_error": f"line {line}: {getattr(e, 'msg', str(e))}" if line else str(e)[:80]}
    imports: list[str] = []
    defs: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defs.append(node.name)
    main = any(isinstance(n, ast.If) and "__main__" in ast.dump(n.test) for n in tree.body)
    out = {"imports": _uniq(imports), "defs": _uniq(defs)}
    if main:
        out["entry"] = "__main__"
    return out


def _js_outline(text: str) -> dict:
    return {"imports": _uniq([a or b for a, b in _JS_IMPORT.findall(text)]),
            "defs": _uniq([a or b or c for a, b, c in _JS_DEF.findall(text)])}


def _cell_text(cell: dict) -> str:
    src = cell.get("source") or ""
    return "".join(src) if isinstance(src, list) else str(src)


def notebook_outline(text: str) -> dict:
    """A notebook by cell: how many code / markdown cells, each code cell's imports + defs, cells with an error output."""
    try:
        nb = json.loads(text)
    except ValueError:
        return {"unreadable": "not valid notebook JSON"}
    cells = [c for c in (nb.get("cells") or []) if isinstance(c, dict)]
    code = [c for c in cells if c.get("cell_type") == "code"]
    imports: list[str] = []
    defs: list[str] = []
    errors: list[str] = []
    ran = 0
    for i, c in enumerate(cells, 1):
        if c.get("cell_type") != "code":
            continue
        o = _py_outline(_cell_text(c).replace("%", "#").replace("!", "#"))  # magics and shell lines read as comments
        imports += o.get("imports") or []
        defs += o.get("defs") or []
        if c.get("execution_count"):
            ran += 1
        for out in c.get("outputs") or []:
            if isinstance(out, dict) and out.get("output_type") == "error":
                errors.append(f"cell {i}: {out.get('ename', 'Error')}: {short(out.get('evalue', ''), 100)}")
    return {"cells": f"{len(code)} code, {len(cells) - len(code)} markdown, {ran} run", "imports": _uniq(imports),
            "defs": _uniq(defs), "errors": _uniq(errors, 3)}


def file_outline(name: str, text: str) -> tuple[str, dict]:
    """(summary, facts) for one file. Python by its syntax tree, a notebook by cell, JS/TS by imports and functions,
    anything else by its size and first line."""
    lower = name.lower()
    n_lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    if lower.endswith(".ipynb"):
        facts = notebook_outline(text)
    elif lower.endswith((".py", ".pyw")):
        facts = _py_outline(text)
    elif lower.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")):
        facts = _js_outline(text)
    else:
        first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
        facts = {"first_line": short(first, 80)} if first else {}
    if not text.strip():
        facts = {"empty": "yes"}
    facts = {k: v for k, v in facts.items() if v}
    parts = [f"{name}: {n_lines} lines" if not lower.endswith(".ipynb") else f"{name}: {facts.get('cells', 'notebook')}"]
    if facts.get("empty"):
        parts = [f"{name}: empty"]
    if facts.get("imports"):
        parts.append("imports " + ", ".join(facts["imports"][:5]))
    if facts.get("defs"):
        parts.append("defines " + ", ".join(facts["defs"][:5]))
    if facts.get("syntax_error"):
        parts.append("syntax error at " + facts["syntax_error"])
    if facts.get("errors"):
        parts.append("error output: " + facts["errors"][-1])
    return short("; ".join(parts)), facts


# ---------------------------------------------------------------- screen, checks, cards, setup, actions
def screen_summary(app: str, title: str = "", lines: list[str] | None = None) -> tuple[str, dict]:
    errs = error_lines("\n".join(lines or []))
    facts: dict[str, Any] = {"app": app}
    if title:
        facts["window"] = short(title, 100)
    if errs:
        facts["errors"] = errs
    s = f"{app}" + (f": {short(title, 100)}" if title else "") + (f"\nerror on screen: {errs[-1]}" if errs else "")
    return short(s), facts


def checks_summary(step_id: str, results: list[dict]) -> tuple[str, dict]:
    passed = [r for r in results if r.get("status") == "pass"]
    failing = [r for r in results if r.get("status") == "fail"]
    pending = [r for r in results if r.get("status") not in ("pass", "fail")]
    bits = [f"{len(passed)} passed"]
    if failing:
        bits.append(f"{len(failing)} not yet (" + "; ".join(short(r.get("label") or r.get("checkId") or "", 60)
                                                           for r in failing[:3]) + ")")
    if pending:
        bits.append(f"{len(pending)} waiting")
    facts = {"passed": _uniq([str(r.get("label") or r.get("checkId") or "") for r in passed]),
             "failing": _uniq([str(r.get("label") or r.get("checkId") or "") for r in failing])}
    details = _uniq([short(r.get("detail"), 100) for r in failing if r.get("detail")], 2)
    if details:
        facts["details"] = details
    return short(f"{step_id} checks: " + ", ".join(bits)), {k: v for k, v in facts.items() if v}


def card_summary(kind: str, card: dict) -> tuple[str, dict]:
    """A card the coach (a model call that already ran) or the engine showed: its title and first sentence."""
    title = short(card.get("title"), 80)
    body = first_sentence(card.get("body") or card.get("why") or "")
    facts: dict[str, Any] = {"kind": kind}
    if card.get("verdict"):
        facts["verdict"] = str(card["verdict"])
    if card.get("level") is not None:
        facts["level"] = str(card["level"])
    return short(f"{'coach ' + kind if kind != 'offtrack' else 'off-track'}: {title}" + (f": {body}" if body else "")), facts


def setup_summary(p: dict) -> tuple[str, dict] | None:
    tool = short(p.get("tool"), 60)
    if not tool or not p.get("done"):
        return None
    if p.get("ok"):
        return short(f"setup: {tool} is ready" + (f" ({short(p.get('version'), 30)})" if p.get("version") else "")), {"tool": tool, "ok": "yes"}
    return short(f"setup: {tool} failed" + (f": {short(p.get('error'), 120)}" if p.get("error") else "")), {"tool": tool, "ok": "no"}


ACTION_WORDS = {
    "skip_setup": "skipped setup", "have_it": "said they already have {t}", "get_it": "opened the download page for {t}",
    "alternative": "chose a free alternative to {t}", "skip_step": "skipped the step", "install": "asked to install {t}",
    "install_all": "asked to install everything missing", "run_command": "pressed Run it for me", "apply_fix": "applied the fix",
    "undo": "undid the last fix", "use_this_folder": "chose their own folder", "download": "downloaded the tutorial files",
    "show_me": "asked where to work", "check_step": "asked Can I move on?",
}


def action_summary(kind: str, text: str | None = None) -> tuple[str, dict] | None:
    words = ACTION_WORDS.get(kind)
    if words is None:
        return None
    t = short(text, 60) or "it"
    return f"learner {words.format(t=t)}", {"action": kind, **({"tool": t} if text else {})}

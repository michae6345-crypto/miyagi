"""Terminal-command typos on a lesson's run step, caught deterministically (no model call), Nov 15 live test.

Michael typed `python 3 nn.py` on the curated NN lesson's run step; the coach caught it from OCR ~4 s later ("Retype as
python3 nn.py"). This module compares the command VS Code's terminal reports (the companion's command_end: commandLine,
exitCode, outputTail) with the step's command and names the exact fix at once. Edit distance on tokens + the shell's
own error lines. Anything it doesn't recognise -> None (the live coach stays the fallback).

    diagnose(typed, expected, output=..., exit_code=..., lesson_dir=..., cwd=..., file_lines=..., has_python=...)
        -> {"kind", "fix", "title", "body", "caption", "line"?} | None

kinds: split (`python 3 nn.py`), interp (`pyhton3 nn.py`), no_python (`python nn.py`: zsh has no `python`),
bare_file (`nn.py` alone), file (`python3 nn`, `nn,py`, `NN.py`, `nn.py.`, `n.py`), wrong_folder (No such file),
venv (`python3 nn.py` has no NumPy; the lesson's .venv does), pip (`pip intsall numpy`, `pip` not found),
in_file (the run command typed into nn.py instead of the terminal).
"""
from __future__ import annotations

import os
import re
import shlex

PY_INTERP = re.compile(r"^(?:\S*/)?python(?:3(?:\.\d+)?)?$")
NOT_FOUND = re.compile(r"command not found:\s*(\S+)")  # zsh: `zsh: command not found: python`
NOT_FOUND_SH = re.compile(r"(\S+): (?:command )?not found")  # bash / sh: `bash: python: command not found`
NO_FILE = re.compile(r"can't open file|No such file or directory|Errno 2")
NO_NUMPY = re.compile(r"No module named '?(numpy|\w+)'?")
PACKAGES = ("numpy", "matplotlib", "pandas", "requests", "scipy", "torch", "flask", "scikit-learn", "jupyter",
            "pytest", "pillow", "seaborn", "tensorflow", "opencv-python", "streamlit", "fastapi", "uvicorn")


def edits(a: str, b: str) -> int:
    """Damerau-Levenshtein distance (one swap = one edit: `pyhton` -> `python` is 1)."""
    if a == b:
        return 0
    d = [[i + j if i * j == 0 else 0 for j in range(len(b) + 1)] for i in range(len(a) + 1)]
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[-1][-1]


def _tokens(cmd: str) -> list[str]:
    try:
        return shlex.split(cmd)
    except ValueError:  # an unclosed quote: plain split
        return cmd.split()


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _not_found(output: list[str]) -> str | None:
    for ln in output:
        if m := NOT_FOUND.search(ln) or NOT_FOUND_SH.search(ln.split(": ", 1)[-1]):
            return m.group(1)
    return None


def _verdict(kind: str, fix: str, title: str, body: str, caption: str | None = None, **kw) -> dict:
    return {"kind": kind, "fix": fix, "title": title, "body": body, "caption": caption or f"Retype as {fix}", **kw}


def _retype(kind: str, fix: str, what: str) -> dict:
    return _verdict(kind, fix, f"Retype it as {fix}", f"{what} In VS Code's terminal, type {fix} and press Return.")


def _file_close(tok: str, file: str) -> bool:
    """`nn`, `nn,py`, `NN.py`, `nn.py.`, `n.py`, `nn.yp`, `./nn.py` against nn.py."""
    t = tok.removeprefix("./")
    if t == file:
        return False
    stem = file.rsplit(".", 1)[0]
    return (t.lower() == file.lower() or t.rstrip(".,;:") == file or t == stem
            or edits(t.lower(), file.lower()) <= 2 and len(t) >= 2)


def _in_file(file_lines: list[str] | None, expected: str, file: str) -> dict | None:
    """The run command typed into the .py file: a line that reads (about) `python3 nn.py` / `nn.py` / `$ python3 ...`."""
    want = _squash(expected)
    for i, ln in enumerate(file_lines or [], start=1):
        s = ln.strip().lstrip("$%> ").strip()
        if not s or s.startswith("#"):
            continue
        toks = _tokens(s)
        runs = len(toks) == 2 and edits(toks[0].lower(), "python3") <= 2 and toks[1].endswith((".py", file))
        if edits(_squash(s), want) <= 2 or runs or s == file:
            return _verdict("in_file", expected, "That's a terminal command, not Python",
                            f"Line {i} of {file} reads `{ln.strip()}`. Delete that line, save, and type {expected} in "
                            "VS Code's terminal (⌃` opens it).", caption="Delete this line", line=i, anchor=ln.strip())
    return None


def _pip(toks: list[str], output: list[str]) -> dict | None:
    """`pip intsall numpy`, `pip3 isntall numpi`, `pipinstall numpy`, `pip install` when zsh has no `pip`."""
    if not toks:
        return None
    head = toks[0].lower()
    rest = toks[1:]
    if head.startswith("pip") and head not in ("pip", "pip3") and edits(head[3:].lstrip("3"), "install") <= 2:
        rest, head = [head[3:].lstrip("3") or "install", *rest], ("pip3" if head.startswith("pip3") else "pip")
    if PY_INTERP.match(head) and rest[:2] == ["-m", "pip"]:
        pre, rest = f"{toks[0]} -m pip", rest[2:]
    elif head in ("pip", "pip3") or (len(head) >= 3 and edits(head, "pip3") <= 1 and head[0] == "p"):
        pre = "pip3" if head not in ("pip", "pip3") else head
    else:
        return None
    if not rest or edits(rest[0].lower(), "install") > 2:
        return None
    pkgs, fixed = rest[1:], []
    for p in pkgs:
        if p.startswith("-"):
            fixed.append(p)
            continue
        best = min(PACKAGES, key=lambda k: edits(p.lower(), k))
        fixed.append(best if edits(p.lower(), best) <= 2 else p)
    missing = _not_found(output)
    if missing and missing.startswith("pip"):
        pre = "python3 -m pip"  # this Mac has no `pip` on PATH
    fix = " ".join([pre, "install", *fixed]).strip()
    if fix == " ".join(toks):
        return None  # typed right (it failed for another reason: not a typo)
    return _retype("pip", fix, f"`{' '.join(toks)}` has a typo." if not missing else f"zsh has no `{missing}` here.")


def diagnose(typed: str, expected: str, *, output: list[str] | tuple = (), exit_code: int | None = None,
             lesson_dir: str | None = None, cwd: str | None = None, file_lines: list[str] | None = None,
             has_python: bool | None = None) -> dict | None:
    """The fix for a terminal command on a run step, or None (right command that worked, a real error in the code,
    or a command that isn't an attempt at the step's: `ls`, `clear`, `cat nn.py`)."""
    typed = " ".join((typed or "").split())
    expected = " ".join((expected or "").split())
    out = [str(x) for x in output or []]
    if not expected:
        return None
    etoks = _tokens(expected)
    file = next((t for t in reversed(etoks) if t.endswith(".py")), "")
    interp = etoks[0] if etoks else ""
    if not typed:
        return _in_file(file_lines, expected, file) if file else None
    toks = _tokens(typed)
    failed = exit_code not in (0, None) or any(NO_FILE.search(x) or _not_found([x]) for x in out)
    if (v := _pip(toks, out)) is not None:
        return v
    if not file:  # not a `python <file>` step: only an outright typo of the whole command
        if typed != expected and edits(_squash(typed), _squash(expected)) <= max(1, len(_squash(expected)) // 6):
            return _retype("typo", expected, f"`{typed}` has a typo.")
        return None
    missing = _not_found(out)
    # `nn.py` / `./nn.py` alone: zsh can't run a .py file by its name
    if len(toks) == 1 and (toks[0].lstrip("./") == file or _file_close(toks[0], file)):
        return _retype("bare_file", expected, f"{file} is a Python file: start the command with {interp}.")
    # the interpreter split in two (`python 3 nn.py`, `python 3.12 nn.py`)
    if len(toks) >= 2 and toks[0].lower() == "python" and re.fullmatch(r"3(?:\.\d+)?", toks[1]):
        return _retype("split", expected, "There's a space inside python3, so zsh looked for `python`.")
    head = toks[0]
    py_like = PY_INTERP.match(head) is not None
    if not py_like and (edits(head.lower(), "python3") <= 2 or edits(head.lower(), "python") <= 2) and len(head) >= 4:
        return _retype("interp", expected, f"`{head}` is a typo for python3.")
    if not py_like:
        if failed and missing and missing == head and len(toks) >= 2 and toks[-1] == file:
            return _retype("interp", expected, f"zsh has no `{head}` command.")
        return None  # `ls`, `cd ..`, `cat nn.py`: not an attempt at the run
    # `python nn.py` where zsh has no `python` (or the step asks for python3 and it failed)
    if head == "python" and interp != "python" and (missing == "python" or has_python is False):
        return _retype("no_python", expected, "This Mac has no `python` command, only python3.")
    script = next((t for t in toks[1:] if not t.startswith("-")), "")
    if script and script.lstrip("./") != file and (script.endswith((".py", ".py.", ",py")) or _file_close(script, file)):
        if _file_close(script, file):
            return _retype("file", expected, f"`{script}` isn't the file: it's {file}.")
        return None  # another .py file on purpose (`python3 test.py`): not this step's typo
    if not script:
        return None  # `python3` alone: the REPL, not a typo
    # the right command: wrong folder / the lesson's .venv / a real error in the code
    if any(NO_FILE.search(x) and file in x for x in out) or (exit_code == 2 and any(NO_FILE.search(x) for x in out)):
        if lesson_dir:
            folder = lesson_dir if " " not in lesson_dir else f'"{lesson_dir}"'
            return _verdict("wrong_folder", f"cd {folder}", "The terminal isn't in the lesson's folder",
                            f"{file} is in {os.path.basename(lesson_dir.rstrip('/'))}. Type cd {folder} and press "
                            f"Return, then {expected}.", caption="Run cd to the lesson folder first")
        return None
    if cwd and lesson_dir and failed and os.path.realpath(cwd) != os.path.realpath(lesson_dir) \
            and not os.path.exists(os.path.join(cwd, file)):
        folder = lesson_dir if " " not in lesson_dir else f'"{lesson_dir}"'
        return _verdict("wrong_folder", f"cd {folder}", "The terminal isn't in the lesson's folder",
                        f"Type cd {folder} and press Return, then {expected}.",
                        caption="Run cd to the lesson folder first")
    if any((m := NO_NUMPY.search(x)) and m.group(1) == "numpy" for x in out) and interp != head \
            and ".venv" in interp:
        return _retype("venv", expected, "NumPy is installed in the lesson's .venv, not in this python3.")
    if failed and any("SyntaxError" in x for x in out) and (v := _in_file(file_lines, expected, file)) is not None:
        return v
    return None


# The offline table: (typed, expected, kw, expected kind or None). scripts/check_cmd_typos.py prints the verdicts.
CASES: list[tuple[str, str, dict, str | None]] = [
    ("python 3 nn.py", "python3 nn.py", {"output": ["zsh: command not found: python"], "exit_code": 127}, "split"),
    ("pyhton3 nn.py", "python3 nn.py", {"output": ["zsh: command not found: pyhton3"], "exit_code": 127}, "interp"),
    ("pytohn3 nn.py", "python3 nn.py", {"exit_code": 127}, "interp"),
    ("python3 nn", "python3 nn.py", {"output": ["python3: can't open file '/l/nn': [Errno 2] No such file or directory"],
                                     "exit_code": 2}, "file"),
    ("python3 nn,py", "python3 nn.py", {"exit_code": 2}, "file"),
    ("python3 NN.py", "python3 nn.py", {"exit_code": 0}, "file"),
    ("python3 nn.py.", "python3 nn.py", {"exit_code": 2}, "file"),
    ("python3 n.py", "python3 nn.py", {"exit_code": 2}, "file"),
    ("python3 nn.yp", "python3 nn.py", {"exit_code": 2}, "file"),
    ("python3 nn.py", "python3 nn.py", {"output": [("python3: can't open file '/Users/me/nn.py': [Errno 2] No such "
                                                    "file or directory")], "exit_code": 2,
                                        "lesson_dir": "/Users/me/miyagi/lessons/nn-1"}, "wrong_folder"),
    ("python nn.py", "python3 nn.py", {"output": ["zsh: command not found: python"], "exit_code": 127}, "no_python"),
    ("pip intsall numpy", "python3 nn.py", {"exit_code": 1}, "pip"),
    ("pip3 isntall numpi", "python3 nn.py", {"exit_code": 1}, "pip"),
    ("pipinstall numpy", "python3 nn.py", {"exit_code": 127}, "pip"),
    ("pip install numpy", "python3 nn.py", {"output": ["zsh: command not found: pip"], "exit_code": 127}, "pip"),
    ("nn.py", "python3 nn.py", {"output": ["zsh: command not found: nn.py"], "exit_code": 127}, "bare_file"),
    ("./nn.py", "python3 nn.py", {"output": ["zsh: permission denied: ./nn.py"], "exit_code": 126}, "bare_file"),
    ("python3 nn.py", "python3 nn.py", {"output": ["  File \"nn.py\", line 40", "    python3 nn.py",
                                                   "SyntaxError: invalid syntax"], "exit_code": 1,
                                        "file_lines": ["import numpy as np", "x = 1", "python3 nn.py"]}, "in_file"),
    ("", "python3 nn.py", {"file_lines": ["import numpy as np", "python3 nn.py"]}, "in_file"),
    ("python3 nn.py", ".venv/bin/python nn.py", {"output": ["ModuleNotFoundError: No module named 'numpy'"],
                                                 "exit_code": 1}, "venv"),
    # not typos: no card, the coach (or nothing) handles them
    ("python3 nn.py", "python3 nn.py", {"exit_code": 0}, None),
    ("python3 nn.py", "python3 nn.py", {"output": ["NameError: name 'W4' is not defined"], "exit_code": 1}, None),
    (".venv/bin/python nn.py", ".venv/bin/python nn.py", {"exit_code": 0}, None),
    ("ls", "python3 nn.py", {"exit_code": 0}, None),
    ("cat nn.py", "python3 nn.py", {"exit_code": 0}, None),
    ("clear", "python3 nn.py", {"exit_code": 0}, None),
    ("python3 test.py", "python3 nn.py", {"exit_code": 0}, None),
    ("python3", "python3 nn.py", {"exit_code": 0}, None),
    ("pip install numpy", "python3 nn.py", {"exit_code": 0}, None),
]

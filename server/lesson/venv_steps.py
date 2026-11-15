"""A video's "make a venv and pip install" step, in the lesson's own .venv (desktop test 9, Nov 15, V6).

Kie Codes' TensorFlow lesson (demo/cache/lessons/5c0ea8a49f419487.json) told the learner, in step 1, to run
`python3 -m venv venv && source venv/bin/activate && pip3 install jupyter tensorflow numpy matplotlib && jupyter notebook`
while Miyagi had already made the lesson's `.venv` and its setup card installs those packages into it. That sends the
learner to make a second venv (the VS Code terminal and the notebook kernel use `.venv`) and to install everything again.

use_lesson_venv(graph) runs on every lesson load (a cached lesson too: the demo replays that cache) and before a new
build is cached. For each step whose shell `run_command` makes a venv, activates one or pip-installs the lesson's own
libraries:
- the command: no `python -m venv X` / `virtualenv X` / `uv venv X`; `source X/bin/activate` -> `source .venv/bin/activate`;
  `pip install` drops the lesson's libraries (others stay); `X/bin/...` -> `.venv/bin/...`;
- its instructions say so, and keep the rest of what the step asks;
- hints and common mistakes about making the venv / installing go (an activation hint names .venv), plus one hint that
  says the command;
- checks: a screen check that waits for pip's own output ("Successfully installed") can never pass any more and goes;
  file checks on `X/...` look in `.venv/...`; a prompt check `\\(venv\\)` also accepts `(.venv)`;
- a target that pointed at a dropped command points at the command left.
Idempotent: a second pass changes nothing. Returns the ids of the steps it changed."""

from __future__ import annotations

import re

VENV = ".venv"
_SPLIT = re.compile(r"\s*(?:&&|;|\n)\s*")
_MAKE = re.compile(r"^(?:python(?:3(?:\.\d+)?)?\s+-m\s+venv|virtualenv|uv\s+venv)\s+(?:-\S+\s+)*(?P<dir>[\w.~/-]+?)/?$")
_ACTIVATE = re.compile(r"^(?:source|\.)\s+(?P<dir>[\w.~/-]+?)/bin/activate(?:\.\w+)?$")
_PIP = re.compile(r"^(?:(?:python(?:3(?:\.\d+)?)?|py)\s+-m\s+)?pip3?\s+install\s+(?P<args>.+)$")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_ABOUT_VENV = re.compile(r"\bvenv\b|virtual\s*env|virtualenv|-m\s+venv", re.I)
_ABOUT_INSTALL = re.compile(r"\bpip3?\b|\binstall", re.I)
_MAKE_TITLE = re.compile(r"\b(?:create|make|set\s*up)\s+(?:(?:a|the|your)\s+)?(?:venv|virtual\s*env\w*)\b", re.I)
_LEAD = re.compile(r"^(?:launch|start|run|open)\s+(?P<what>.+?)\s+and\s+(?P<rest>.+)$", re.I)
# what pip prints: a screen check waiting for it can only pass if the learner runs pip
_PIP_OUTPUT = ("Successfully installed numpy-1.26.4", "Requirement already satisfied: numpy in ./.venv/lib")


def _norm(pkg: str) -> str:
    return re.split(r"[\[<>=!~;@ ]", pkg.strip(), maxsplit=1)[0].lower().replace("_", "-")


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _shell(cmd: str) -> bool:
    """A command to type (not a notebook action like "Run the cell (Shift+Enter)")."""
    return bool(cmd) and not re.search(r"shift\s*\+\s*enter|^\s*(?:run|execute|press|click)\s+(?:the|a|all|each|this)\b", cmd, re.I)


def rewrite_command(cmd: str, libs: set[str]) -> tuple[str, dict] | None:
    """-> (the command in the lesson's .venv, what changed) or None when it has nothing to change."""
    parts = [p for p in _SPLIT.split(cmd.strip()) if p]
    out: list[str] = []
    dirs: set[str] = set()
    made = activated = False
    dropped_pkgs: list[str] = []
    for p in parts:
        if m := _MAKE.match(p):
            made = True
            dirs.add(m.group("dir").rstrip("/"))
            continue
        if m := _ACTIVATE.match(p):
            activated = True
            dirs.add(m.group("dir").rstrip("/"))
            if f"source {VENV}/bin/activate" not in out:
                out.append(f"source {VENV}/bin/activate")
            continue
        if (m := _PIP.match(p)) and libs:
            toks = m.group("args").split()
            if any(t in ("-r", "--requirement", "-e", "--editable") for t in toks):
                out.append(p)
                continue
            pkgs = [t for t in toks if not t.startswith("-")]
            keep = [t for t in pkgs if _norm(t) not in libs]
            dropped_pkgs += [_norm(t) for t in pkgs if _norm(t) in libs]
            if keep:
                out.append("pip install " + " ".join(keep))
            continue
        out.append(p)
    dirs.discard(VENV)
    for d in dirs:  # venv/bin/python main.py -> .venv/bin/python main.py
        out = [re.sub(rf"(?<![\w.]){re.escape(d)}/bin/", f"{VENV}/bin/", p) for p in out]
    new = " && ".join(out)
    if not (made or dropped_pkgs) and new == " && ".join(parts):
        return None
    return new, {"made": made, "activated": activated, "dirs": dirs, "dropped": dropped_pkgs}


def _rewrite_text(text: str, dirs: set[str]) -> str:
    for d in dirs:
        text = re.sub(rf"(?<![\w.]){re.escape(d)}/bin/activate", f"{VENV}/bin/activate", text)
        text = re.sub(rf"\({re.escape(d)}\)", f"({VENV})", text)
    return text


def _instructions(old: str, cmd: str, ch: dict) -> str:
    kept: list[str] = []
    for s in (x.strip() for x in _SENTENCE.split(old or "") if x.strip()):
        if (ch["made"] or ch["activated"]) and _ABOUT_VENV.search(s) or ch["dropped"] and _ABOUT_INSTALL.search(s):
            continue
        m = _LEAD.match(s)
        if cmd and m and all(w.lower() in cmd.lower() for w in re.findall(r"[A-Za-z]+", m.group("what"))):
            s = "Then " + m.group("rest")  # "Launch Jupyter Notebook and create…": the command launches it
        kept.append(s)
    if ch["dropped"]:
        lead = f"Miyagi already made this lesson's {VENV} and installs {_join(ch['dropped'])} into it from the setup card."
    else:
        lead = f"Miyagi already made this lesson's {VENV}: use it, not a new venv."
    run = f"In the VS Code terminal, run `{cmd}`." if cmd else ""
    return " ".join(x for x in [lead, run, *kept] if x)


def _pip_check(c: dict) -> bool:
    if c.get("type") != "screen_contains" or not c.get("pattern"):
        return False
    try:
        return any(re.search(c["pattern"], s) for s in _PIP_OUTPUT)
    except re.error:
        return False


def _fix_file(path: str, dirs: set[str]) -> str:
    for d in dirs:
        if path == d or path.startswith(d + "/"):
            return VENV + path[len(d):]
    return path


def _fix_pattern(p: str, dirs: set[str]) -> str:
    for d in dirs:
        esc = re.escape(d)
        new = r"\.?venv" if d == "venv" else re.escape(VENV)
        p = p.replace(rf"\({esc}\)", rf"\({new}\)").replace(rf"{esc}/bin", rf"{new}/bin")
    return p


def use_lesson_venv(graph: dict) -> list[str]:
    """Rewrite `graph` in place (see the module doc). -> ids of the steps it changed."""
    lesson = graph.get("lesson") or {}
    libs = {_norm(k) for k in (lesson.get("libraries") or {}) if isinstance(k, str) and k.strip()}
    changed: list[str] = []
    if not libs:  # no packages for Miyagi's setup card to put in a .venv: it may never be made
        return changed
    for step in graph.get("steps") or []:
        if not isinstance(step, dict):
            continue
        cmd = (step.get("run_command") or "").strip()
        if not _shell(cmd):
            continue
        res = rewrite_command(cmd, libs)
        if res is None:
            continue
        new, ch = res
        if new:
            step["run_command"] = new
        else:
            step.pop("run_command", None)
        dirs = ch["dirs"]
        if ch["made"] and step.get("title"):  # "Create venv and start Jupyter" -> "Activate .venv and start Jupyter"
            step["title"] = _MAKE_TITLE.sub(f"Activate {VENV}", step["title"], count=1)
        step["instructions"] = _instructions(step.get("instructions") or "", new, ch)
        hints = []
        for h in step.get("hints") or []:
            if ch["dropped"] and _ABOUT_INSTALL.search(h) or re.search(r"-m\s+venv|virtualenv|create\s+(?:a|the|your)\s+(?:venv|virtual)", h, re.I):
                continue
            hints.append(_rewrite_text(h, dirs))
        if new and not any(new in h for h in hints):
            hints.append(f"Run `{new}` in the VS Code terminal.")
        step["hints"] = hints
        step["common_mistakes"] = [m for m in step.get("common_mistakes") or []
                                   if not (ch["dropped"] and _ABOUT_INSTALL.search(m) or _ABOUT_VENV.search(m) and ch["made"])]
        for key in ("checks", "precision_checks"):
            kept = []
            for c in step.get(key) or []:
                if ch["dropped"] and _pip_check(c):
                    continue
                c = dict(c)
                if c.get("file") and (f := _fix_file(c["file"], dirs)) != c["file"]:
                    c["file"] = f
                    if _ABOUT_VENV.search(c.get("label") or ""):  # "Venv folder created": Miyagi made it
                        c["label"] = f"Lesson {VENV} ready"
                if c.get("pattern") and c.get("type", "").startswith("screen_"):
                    c["pattern"] = _fix_pattern(c["pattern"], dirs)
                kept.append(c)
            if key in step:
                step[key] = kept
        left = [p for p in _SPLIT.split(new) if p] if new else []
        targets = []
        for t in step.get("targets") or []:
            m = str(t.get("match") or "")
            if m and m not in new and (_PIP.match(m) or _MAKE.match(m) or _ACTIVATE.match(m) or m in cmd):
                if not left:
                    continue
                t = {**t, "match": left[-1], "caption": "Run this in the VS Code terminal"}
            targets.append(t)
        step["targets"] = targets
        changed.append(step.get("id") or "?")
    return changed

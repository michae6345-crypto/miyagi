"""Which lesson commands the engine may run for the learner (OWASP LLM06: excessive agency).

A run step's command comes from a model watching a video, from a lesson graph that may be cached or stored, or from a
step's code that looks like a shell line. None of it is trusted. parse_run_command() turns it into an argv the engine
runs WITHOUT a shell, or says why the learner should run it themselves:

  Allowed(argv)   python | python3 | .venv/bin/python <relative .py in the lesson folder> [plain args]
                  python -m pytest | pytest [relative paths in the lesson folder] [-q -v -vv -x -s]
                  node <relative .js / .mjs / .cjs in the lesson folder> [plain args]
                  npm run <a script in the lesson's package.json> | npm start (its start script) | npm test
                  pip | pip3 | python -m pip install -r <relative requirements*.txt in the lesson folder>
                  pip install <names on the curated package list (server/safety/packages.py)>
  Manual(reason)  everything else: several commands, pipes, redirects, substitutions, globs, `~`, URLs, shells and
                  other programs (curl, wget, bash, sudo, rm, open, osascript, npx ...), and paths that leave the
                  lesson folder (symlinks followed)

Manual commands are shown on a card ("From the tutorial: check it before running") and never run by the engine.
"""
from __future__ import annotations

import json
import os
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from . import packages
from .paths import safe_lesson_path

_META = set(";|&`<>*~$\x00(){}!?[]")  # the shell syntax a learner's own command never needs here
_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://|\bwww\.", re.I)
ARG = re.compile(r"^[A-Za-z0-9_./=:,+@-]+$")
PYTHONS = frozenset({"python", "python3", ".venv/bin/python", ".venv/bin/python3", "./.venv/bin/python",
                     "./.venv/bin/python3"})
PIPS = frozenset({"pip", "pip3", ".venv/bin/pip", ".venv/bin/pip3"})
PYTEST_FLAGS = frozenset({"-q", "-v", "-vv", "-x", "-s", "-rA"})
NEVER = frozenset({"curl", "wget", "bash", "sh", "zsh", "fish", "dash", "ksh", "csh", "tcsh", "eval", "exec", "sudo",
                   "su", "doas", "rm", "rmdir", "mv", "dd", "chmod", "chown", "chflags", "osascript", "open", "source",
                   ".", "npx", "pnpx", "bunx", "nc", "ncat", "ssh", "scp", "sftp", "rsync", "ftp", "telnet",
                   "launchctl", "defaults", "security", "crontab", "kill", "killall", "pkill", "xattr", "spctl",
                   "csrutil", "diskutil", "env", "xargs", "nohup", "time", "watch", "brew", "git", "uv", "pipx",
                   "yarn", "pnpm", "bun", "deno", "perl", "ruby", "php", "lua", "tclsh", "awk", "sed", "find",
                   "powershell", "pwsh", "cmd"})


@dataclass(frozen=True)
class Allowed:
    """Run `argv` with create_subprocess_exec (no shell) in the lesson folder."""
    argv: tuple[str, ...]
    details: str = ""  # what else the confirm card should show (an npm script's text, a requirements file's names)

    @property
    def command(self) -> str:
        return shlex.join(self.argv)


@dataclass(frozen=True)
class Manual:
    """Never run by the engine: the learner reads it and runs it themselves."""
    reason: str
    structural: bool = True  # False: refused only because of the lesson folder's contents (a file not there yet)
    command: str = field(default="", compare=False)


def parse_run_command(cmd: str | None, workdir: str | os.PathLike | None) -> Allowed | Manual:
    """Allowed(argv) when the engine may run `cmd` for the learner in `workdir`, else Manual(reason)."""
    raw = (cmd or "").strip()
    if raw.startswith("$ "):  # a prompt copied with the command
        raw = raw[2:].strip()
    if not raw:
        return Manual("no command", command=raw)
    if "\n" in raw or "\r" in raw:
        return Manual("more than one command", command=raw)
    if bad := sorted(set(raw) & _META):
        return Manual(f"shell syntax ({' '.join(bad)}) the engine never runs", command=raw)
    if _URL.search(raw):
        return Manual("it names a web address", command=raw)
    try:
        argv = shlex.split(raw)
    except ValueError:
        return Manual("it doesn't parse as one command", command=raw)
    if not argv:
        return Manual("no command", command=raw)
    if not workdir:
        return Manual("no lesson folder", structural=False, command=raw)
    res = _classify(argv, str(workdir))
    if isinstance(res, Manual):
        return Manual(res.reason, res.structural, command=raw)
    return res


def _classify(argv: list[str], workdir: str) -> Allowed | Manual:
    prog = argv[0]
    base = PurePosixPath(prog).name
    if base in NEVER or prog in NEVER:
        return Manual(f"{base} is never run for you")
    if prog in PYTHONS:
        return _python(argv, workdir)
    if prog in PIPS:
        return _pip(argv, 1, workdir)
    if prog == "pytest":
        return _pytest(argv, 1, workdir)
    if prog == "node":
        return _node(argv, workdir)
    if prog == "npm":
        return _npm(argv, workdir)
    return Manual(f"{base} isn't one of the commands miyagi runs for you")


def _python(argv: list[str], workdir: str) -> Allowed | Manual:
    if len(argv) < 2:
        return Manual("an interactive Python")
    if argv[1] == "-m":
        mod = argv[2] if len(argv) > 2 else ""
        if mod == "pytest":
            return _pytest(argv, 3, workdir)
        if mod == "pip":
            return _pip(argv, 3, workdir)
        return Manual(f"python -m {mod or '?'} isn't run for you")
    return _script(argv, 1, workdir, (".py",))


def _node(argv: list[str], workdir: str) -> Allowed | Manual:
    if len(argv) < 2:
        return Manual("an interactive node")
    return _script(argv, 1, workdir, (".js", ".mjs", ".cjs"))


def _script(argv: list[str], i: int, workdir: str, suffixes: tuple[str, ...]) -> Allowed | Manual:
    script = argv[i]
    if script.startswith("-"):
        return Manual(f"{argv[0]} {script} runs code that isn't a lesson file")
    if not script.endswith(suffixes):
        return Manual(f"{script} isn't a {'/'.join(suffixes)} file")
    if (why := _inside(script, workdir)) is not None:
        return why
    if (why := _args(argv[i + 1:], workdir)) is not None:
        return why
    return Allowed(tuple(argv))


def _args(args: list[str], workdir: str) -> Manual | None:
    for a in args:
        if not ARG.match(a):
            return Manual(f"the argument {a[:40]!r} isn't a plain value")
        if a.startswith("/") or ".." in PurePosixPath(a.split("=", 1)[-1]).parts:
            return Manual(f"the argument {a[:40]!r} points outside the lesson folder")
    return None


def _inside(rel: str, workdir: str) -> Manual | None:
    if rel.startswith("/") or ".." in PurePosixPath(rel).parts:
        return Manual(f"{rel} is outside the lesson folder")
    if safe_lesson_path(workdir, rel) is None:
        return Manual(f"{rel} is outside the lesson folder")
    return None


def _pytest(argv: list[str], i: int, workdir: str) -> Allowed | Manual:
    for a in argv[i:]:
        if a in PYTEST_FLAGS:
            continue
        if a.startswith("-") or not ARG.match(a):
            return Manual(f"pytest {a[:40]} isn't run for you")
        if (why := _inside(a.split("::", 1)[0], workdir)) is not None:
            return why
    return Allowed(tuple(argv))


def _pip(argv: list[str], i: int, workdir: str) -> Allowed | Manual:
    rest = argv[i:]
    if not rest or rest[0] != "install":
        return Manual(f"pip {rest[0] if rest else ''} isn't run for you".strip())
    rest = rest[1:]
    if not rest:
        return Manual("pip install of nothing")
    if rest[0] == "-r":
        if len(rest) != 2:
            return Manual("pip install -r takes one requirements file here")
        req = rest[1]
        name = PurePosixPath(req).name
        if not (name.startswith("requirements") and name.endswith(".txt")):
            return Manual(f"{req} isn't a requirements*.txt file")
        if (why := _inside(req, workdir)) is not None:
            return why
        path = safe_lesson_path(workdir, req)
        try:
            text = path.read_text(encoding="utf-8", errors="replace") if path is not None and path.is_file() else None
        except OSError:
            text = None
        if text is None:
            return Manual(f"{req} isn't in the lesson folder yet", structural=False)
        if probs := packages.requirements_problems(text):
            return Manual(f"{req}: {probs[0]}", structural=False)
        names = packages.requirement_names(text)
        return Allowed(tuple(argv), details="Installs: " + (", ".join(names[:12]) + (" …" if len(names) > 12 else "")
                                             if names else "nothing listed"))
    for a in rest:
        if a.startswith("-"):
            return Manual(f"pip install {a[:40]} isn't run for you")
        v = packages.verdict(a)
        if v.kind != packages.ALLOW:
            extra = f" ({v.url})" if v.name else ""
            return Manual(f"{v.reason}{extra}")
    return Allowed(tuple(argv))


def npm_scripts(workdir: str | os.PathLike) -> dict[str, str]:
    """The lesson folder's package.json scripts ({} when there is none or it doesn't parse)."""
    p = safe_lesson_path(workdir, "package.json")
    try:
        data = json.loads(p.read_text(encoding="utf-8")) if p is not None and p.is_file() else {}
    except (OSError, ValueError):
        return {}
    scripts = data.get("scripts") if isinstance(data, dict) else None
    return {str(k): str(v) for k, v in scripts.items()} if isinstance(scripts, dict) else {}


def _npm(argv: list[str], workdir: str) -> Allowed | Manual:
    rest = argv[1:]
    if rest in (["test"], ["start"]):
        name = rest[0]
    elif len(rest) == 2 and rest[0] in ("run", "run-script") and re.fullmatch(r"[A-Za-z0-9:_.-]+", rest[1]):
        name = rest[1]
    else:
        return Manual(f"npm {' '.join(rest)[:40]} isn't run for you")
    scripts = npm_scripts(workdir)
    if name not in scripts:
        return Manual(f"package.json has no {name!r} script", structural=False)
    return Allowed(tuple(argv), details=f"{name}: {scripts[name][:200]}")


def is_structural_manual(cmd: str | None) -> Manual | None:
    """parse_run_command's verdict on `cmd` alone (no lesson folder needed): Manual when no lesson folder could make it
    runnable (shell syntax, a URL, a program never run, a path out of the folder), else None. For lesson validation,
    which runs before the folder's files exist."""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="miyagi-cmd-") as tmp:
        res = parse_run_command(cmd, tmp)
    return res if isinstance(res, Manual) and res.structural else None

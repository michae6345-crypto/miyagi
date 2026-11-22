"""Which lesson commands the engine may run for the learner (OWASP LLM06: excessive agency).

A run step's command comes from a model watching a video, from a lesson graph that may be cached or stored, or from a
step's code that looks like a shell line. None of it is trusted. parse_run_command() turns it into an argv the engine
runs WITHOUT a shell, or says why the learner should run it themselves:

  Allowed(argv)   python | python3 | .venv/bin/python <relative .py in the lesson folder> [plain args]
                  python -m pytest | pytest [relative paths in the lesson folder] [-q -v -vv -x -s], never while
                    the folder has its own pytest.py, _pytest/ ... (SHADOWS) that would run instead
                  node <relative .js / .mjs / .cjs in the lesson folder> [plain args]
                  npm run <a script in the lesson's package.json> | npm start (its start script) | npm test,
                    run with --ignore-scripts, and only when the script has no pre<name> / post<name> hook (npm would
                    run those too, and the card would not show them)
                  pip | pip3 | python -m pip install -r <relative requirements*.txt in the lesson folder> whose every
                    line is a name on the curated package list, run as `pip install <those specs>` (pip never reads
                    the file; a file pip would decode differently, by a BOM or a coding line, is refused)
                  pip install <names on the curated package list (server/safety/packages.py)>
                  (`python -m pip` always runs as `python -I -m pip`: a pip.py in the lesson folder never runs)
  Manual(reason)  everything else: several commands, pipes, redirects, substitutions, globs, `~`, URLs, shells and
                  other programs (curl, wget, bash, sudo, rm, open, osascript, npx ...), and paths that leave the
                  lesson folder (symlinks followed)

Manual commands are shown on a card ("From the tutorial: check it before running") and never run by the engine.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import unicodedata
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from . import packages
from .paths import safe_lesson_path

_META = set(";|&`<>*~$\x00(){}!?[]")  # the shell syntax a learner's own command never needs here
_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://|\bwww\.", re.I)
ARG = re.compile(r"^[A-Za-z0-9_./=:,+@-]+$")
# a lesson file the engine runs (a script, a pytest path, a requirements file): plain ASCII path characters only, so
# the card shows exactly the file that runs (no look-alike, zero-width or bidi characters: main​.py)
PATH_ARG = re.compile(r"^[A-Za-z0-9_./-]+$")
# Unicode categories never in a command the engine runs: controls (^U kills the line in zsh's editor, ^O accepts it,
# so typed into VS Code's terminal they would run something else), format characters (zero-width, bidi overrides),
# line / paragraph separators, private use, surrogates and unassigned code points
_INVISIBLE = frozenset({"Cc", "Cf", "Zl", "Zp", "Co", "Cs", "Cn"})


def invisible_char(text: str) -> str | None:
    """The first character of `text` a confirm card can't show truthfully (a control, format, separator, private-use,
    unassigned character or any space but ' '), as U+XXXX; None when there is none."""
    for ch in text:
        cat = unicodedata.category(ch)
        if cat in _INVISIBLE or (cat == "Zs" and ch != " "):
            return f"U+{ord(ch):04X}"
    return None


def visible(text: str) -> str:
    """`text` with every character invisible_char() objects to written out as <U+XXXX>: what a card shows (and its
    Copy copies) for a command the engine refused, so nothing hidden reaches the learner's terminal. Line breaks and
    tabs stay: a card shows them as they are."""
    return "".join(f"<U+{ord(ch):04X}>" if ch not in "\n\t" and invisible_char(ch) else ch for ch in text)
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
    # what the command runs besides its own words (the npm script's text, the requirements file's content), hashed:
    # a run is confirmed per (folder, command, fingerprint), so an edited script or requirements file asks again
    fingerprint: str = ""

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
    raw = (cmd or "").strip(" \t\r\n")  # (str.strip() would also eat \x1c-\x1f and \x0b: never silently)
    if raw.startswith("$ "):  # a prompt copied with the command
        raw = raw[2:].strip(" \t\r\n")
    if not raw:
        return Manual("no command", command=raw)
    if "\n" in raw or "\r" in raw:
        return Manual("more than one command", command=raw)
    if (bad := invisible_char(raw)) is not None:  # checked on the raw text, before shlex reads it
        return Manual(f"it holds an invisible or control character ({bad})", command=raw)
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
    if argv[1] == "-I" and argv[2:4] == ["-m", "pip"]:  # `python -I -m pip ...`: what _pip_argv itself writes
        return _pip([argv[0], *argv[2:]], 3, workdir)
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
    if not PATH_ARG.match(script):
        return Manual(f"the file name {script[:40]!r} has characters miyagi doesn't run (letters, digits, _ . / - only)")
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
        value = a.split("=", 1)[-1]  # --out=/etc/x: the value after '=' is a path too
        if a.startswith(("/", "~")) or value.startswith(("/", "~")) or ".." in PurePosixPath(value).parts:
            return Manual(f"the argument {a[:40]!r} points outside the lesson folder")
    return None


def _inside(rel: str, workdir: str) -> Manual | None:
    if rel.startswith("/") or ".." in PurePosixPath(rel).parts:
        return Manual(f"{rel} is outside the lesson folder")
    if safe_lesson_path(workdir, rel) is None:
        return Manual(f"{rel} is outside the lesson folder")
    return None


# top-level lesson files that would run in place of pytest (`python -m pytest` puts the lesson folder first on
# sys.path, and pytest inserts it for the tests too, so it can't run isolated like pip)
SHADOWS = frozenset({"pytest", "pytest.py", "_pytest", "_pytest.py", "py.py", "pluggy", "pluggy.py"})


def shadowing(workdir: str) -> str | None:
    """The first top-level entry of the lesson folder named like pytest or a module of it (pytest.py, _pytest/ ...),
    compared case-insensitively (APFS), else None."""
    try:
        names = os.listdir(workdir)
    except OSError:
        return None
    return next((n for n in sorted(names) if n.casefold() in SHADOWS), None)


def _pytest(argv: list[str], i: int, workdir: str) -> Allowed | Manual:
    if (shadow := shadowing(workdir)) is not None:
        return Manual(f"the lesson folder has its own {shadow}, which would run instead of pytest", structural=False)
    for a in argv[i:]:
        if a in PYTEST_FLAGS:
            continue
        if a.startswith("-") or not ARG.match(a) or not PATH_ARG.match(a.split("::", 1)[0]):
            return Manual(f"pytest {a[:40]} isn't run for you")
        if (why := _inside(a.split("::", 1)[0], workdir)) is not None:
            return why
    return Allowed(tuple(argv))


def _pip_argv(argv: list[str], i: int, tail: list[str]) -> tuple[str, ...]:
    """What runs for `argv[:i] install <tail>`: `python -m pip` as `python -I -m pip` (isolated mode: the lesson
    folder is never on sys.path, so a pip.py, pip/ or a stdlib-named module there can't run in place of pip). The
    `pip` console script never has the folder on its path."""
    head = list(argv[:i])
    if head[0] in PYTHONS and "-I" not in head:
        head.insert(1, "-I")
    return (*head, "install", *tail)


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
        if not PATH_ARG.match(req):
            return Manual(f"the file name {req[:40]!r} has characters miyagi doesn't run (letters, digits, _ . / - only)")
        name = PurePosixPath(req).name
        if not (name.startswith("requirements") and name.endswith(".txt")):
            return Manual(f"{req} isn't a requirements*.txt file")
        if (why := _inside(req, workdir)) is not None:
            return why
        path = safe_lesson_path(workdir, req)
        try:
            data = path.read_bytes() if path is not None and path.is_file() else None
        except OSError:
            data = None
        if data is None:
            return Manual(f"{req} isn't in the lesson folder yet", structural=False)
        # A08: read the bytes the way pip would or not at all (a `# coding: utf-7` line or a BOM made pip see a URL
        # line the card never showed)
        text, why = packages.decode_requirements(data)
        if text is None:
            return Manual(f"{req}: {why}", structural=False)
        if probs := packages.requirements_problems(text):
            return Manual(f"{req}: {probs[0]}", structural=False)
        if unlisted := packages.requirements_to_confirm(text):
            # names off the curated list need their own confirm (setup's Install with its pypi.org page), never a
            # bulk install: the learner checks each one and runs it themselves
            return Manual(f"{req} lists packages that aren't on miyagi's list of common tutorial packages, so check "
                          "each one first: " + "; ".join(f"{v.name} ({v.url})" for v in unlisted[:8])
                          + (" …" if len(unlisted) > 8 else ""), structural=False)
        specs = packages.requirement_specs(text)
        if not specs:
            return Manual(f"{req} lists no packages, so there's nothing to install", structural=False)
        names = packages.requirement_names(text)
        # pip gets the verified specs themselves, never the file: what it installs is exactly what the card shows,
        # whatever the file says by the time pip would have read it
        return Allowed(_pip_argv(argv, i, specs),
                       details=f"Installs (from {req}): " + ", ".join(names[:12]) + (" …" if len(names) > 12 else ""),
                       fingerprint=_digest(req, text))
    for a in rest:
        if a.startswith("-"):
            return Manual(f"pip install {a[:40]} isn't run for you")
        v = packages.verdict(a)
        if v.kind != packages.ALLOW:
            extra = f" ({v.url})" if v.name else ""
            return Manual(f"{v.reason}{extra}")
    return Allowed(_pip_argv(argv, i, rest))


def npm_scripts(workdir: str | os.PathLike) -> dict[str, str]:
    """The lesson folder's package.json scripts ({} when there is none or it doesn't parse)."""
    p = safe_lesson_path(workdir, "package.json")
    try:
        data = json.loads(p.read_text(encoding="utf-8")) if p is not None and p.is_file() else {}
    except (OSError, ValueError):
        return {}
    scripts = data.get("scripts") if isinstance(data, dict) else None
    return {str(k): str(v) for k, v in scripts.items()} if isinstance(scripts, dict) else {}


NPM_SCRIPT_MAX = 200  # a longer npm script is never run for the learner: the confirm card shows the script in full


def _npm(argv: list[str], workdir: str) -> Allowed | Manual:
    rest = [a for a in argv[1:] if a != "--ignore-scripts"]
    if rest in (["test"], ["start"]):
        name = rest[0]
    elif len(rest) == 2 and rest[0] in ("run", "run-script") and re.fullmatch(r"[A-Za-z0-9:_.-]+", rest[1]):
        name = rest[1]
    else:
        return Manual(f"npm {' '.join(rest)[:40]} isn't run for you")
    scripts = npm_scripts(workdir)
    if name not in scripts:
        return Manual(f"package.json has no {name!r} script", structural=False)
    if hooks := [h for h in (f"pre{name}", f"post{name}") if h in scripts]:
        # npm runs pre<name> / post<name> around it: code the card wouldn't show. The learner reads them and runs it.
        return Manual(f"package.json also runs {' and '.join(f'{h}: {scripts[h][:80]}' for h in hooks)} around "
                      f"{name!r}", structural=False)
    script = scripts[name]
    if len(script) > NPM_SCRIPT_MAX or not script.isprintable():
        # the card shows the WHOLE script or the engine doesn't run it: a harmless start, 200 spaces, then
        # `&& curl … | sh` must never hide past what a card shows (nor a control character inside it)
        return Manual(f"package.json's {name!r} script is too long (or has characters) to check on a card: read it "
                      "in package.json", structural=False)
    # --ignore-scripts: npm still runs the named script, never a pre / post hook added after this check
    return Allowed((argv[0], *rest, "--ignore-scripts"), details=f"{name}: {script}",
                   fingerprint=_digest(name, script))


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x00".join(parts).encode("utf-8", "replace")).hexdigest()[:16]


def is_structural_manual(cmd: str | None) -> Manual | None:
    """parse_run_command's verdict on `cmd` alone (no lesson folder needed): Manual when no lesson folder could make it
    runnable (shell syntax, a URL, a program never run, a path out of the folder), else None. For lesson validation,
    which runs before the folder's files exist."""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="miyagi-cmd-") as tmp:
        res = parse_run_command(cmd, tmp)
    return res if isinstance(res, Manual) and res.structural else None

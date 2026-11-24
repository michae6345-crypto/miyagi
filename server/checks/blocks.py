"""A terminal's history (or a command-line app's: AutoCAD's ``Command:`` rows) as blocks: one command row and the
output under it, up to the next command row. A check reads the screen through them, so it can tell

* a command's own echo from its result (``git add learning.py`` above ``fatal: not a git repository``);
* a failed command from a good one (``fatal:``, ``error:``, ``! [rejected]``, ``nothing added to commit``,
  ``1 failed, 2 passed``, ``error TS2305:``, AutoCAD's ``*Cancel*``), and a failure the command got past
  (pip's resolver ``ERROR:`` notice, then ``Successfully installed``);
* an older run from the newest one of the same command (``✓ built in 812ms`` above a newer ``npm run build`` that
  failed);
* a harmless repeat (``git rebase --continue`` once more after ``Successfully rebased``: ``fatal: No rebase in
  progress?``);
* whether the step's own command ran at all (``git branch update-name`` is not ``git checkout -b update-name``;
  ``touch`` / ``ls`` rows are not ``git add``).

Pure functions on OCR rows; nothing here runs a command.
"""
from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass

SHELL_JOIN = {"&&", "||", ";", "|"}
PROMPT_MARKS = ("%", "$", "#", "❯")  # zsh %, bash $, root #, starship's arrow

# What an error looks like in a terminal: a traceback, `XError:` / `XException:`, `Error:` / `error:` starting a line
# (or a tool's `gcc: error:`), npm's `ERR!`, the shell's "command not found", a test run's `1 failed` / `FAILED`, a
# compiler's `error TS2305:` / `Found 2 errors`. The bare word anywhere else ("Relative L2 Error: 3.1e-02",
# "error rate", "no errors", "0 failed") is a number the program prints, not a crash.
ERROR_FORM = re.compile(r"Traceback \(most recent call last\)|\b[A-Za-z_]\w*(?:Error|Exception)\s*:"
                        r"|:\s*[A-Z]\w*(?:Error|Exception)\s*$"
                        r"|(?:^|:\s)\s*(?:Error|ERROR|error|Fatal|FATAL|fatal)\b\s*[:!]|\bnpm ERR!|command not found"
                        r"|\b[1-9]\d*\s+failed\b|^\s*FAILED\b|\berror\s+[A-Z]{1,5}\d+\s*:|^\s*Found\s+[1-9]\d*\s+errors?\b",
                        re.M)
# ...and what else says a command did not do its job: the shell can't find the folder, git refused the push or made no
# commit, a command-line app's command was cancelled or unknown
FAILURE_ROW = re.compile(ERROR_FORM.pattern + r"|[Nn]o such file or directory|^\s*!\s*\[(?:remote )?rejected\]"
                         r"|\bnothing added to commit\b|\bno changes added to commit\b|\*Cancel\*"
                         r"|^\s*Unknown command\b", re.M)
# a later row that says the command got there anyway (pip's resolver notice, then the install)
SUCCESS_ROW = re.compile(r"^\s*(?:Successfully\b|✓\s)")
_AUTOCAD_COMMAND = re.compile(r"^\s*Command:\s*(.*)$")


def words(text: str) -> list[str]:
    try:
        return shlex.split(text)
    except ValueError:
        return text.split()


def after_prompt(prev: str) -> bool:
    """Is ``prev`` (the word before a program) the end of a shell prompt (``tripi@mac nn %``, ``me@box:~/lesson1$``,
    starship's arrow, fish's ``~/nn>``) or a shell join (``cd nn && python3 x.py``)? Not ``100%`` (a progress bar in
    the output): only a glued ``%`` after a digit is refused; a bash folder ending in a digit is still a prompt."""
    if prev in SHELL_JOIN or prev in PROMPT_MARKS:
        return True
    if len(prev) < 2:
        return False
    if prev.endswith("%"):
        return not prev[-2].isdigit()
    if prev.endswith(">"):  # fish: user@host ~/nn>  (a path glued to >, never an arrow like ->)
        return prev[0] in "~/"
    return prev.endswith(PROMPT_MARKS)


def _looks_like_prompt_start(prefix: list[str]) -> bool:
    """The words before a prompt mark: a user@host, a path, a (venv) tag. Not output that happens to hold a lone %."""
    return any("@" in p or p.startswith(("~", "/", "(")) or p.endswith("~") for p in prefix)


def prompt_command(row: str) -> str | None:
    """The command on a command row ("" for an empty prompt), else None: a shell prompt (zsh / bash / fish /
    starship / oh-my-zsh's arrow) or a command-line app's ``Command: STLOUT`` row."""
    if m := _AUTOCAD_COMMAND.match(row):
        return m.group(1).strip()
    ws = row.split()
    if not ws:
        return None
    if ws[0] == "➜":  # oh-my-zsh: arrow, <dir>, [git:(branch)], [dirty mark], <command> (never Vite's "➜  Local:")
        if len(ws) < 2 or ws[1].endswith(":"):
            return None
        rest = ws[2:]
        if rest and rest[0].startswith("git:("):
            rest = rest[1:]
        if rest and rest[0] == "✗":
            rest = rest[1:]
        return " ".join(rest)
    for j, w in enumerate(ws):
        if w in SHELL_JOIN or not after_prompt(w):
            continue
        if j == 0:
            if w in ("$", "❯") or (len(w) > 1 and ("@" in w or ":" in w or w[0] in "~/")):
                return " ".join(ws[1:])
            continue
        if _looks_like_prompt_start(ws[:j]) or w in ("$", "❯"):
            return " ".join(ws[j + 1:])
    return None


@dataclass
class Block:
    command: str | None  # the command typed at the prompt ("" an empty prompt); None: rows above the first prompt
    rows: list[str]  # the command row first (when there is one), then its output

    @property
    def output(self) -> list[str]:
        return self.rows[1:] if self.command is not None else self.rows

    @property
    def text(self) -> str:
        return "\n".join(self.rows)

    def failure(self) -> str | None:
        """The output row that says the command failed, unless a later row says it got there anyway; else None."""
        bad = None
        for row in self.output:
            if FAILURE_ROW.search(row):
                bad = row
            elif bad is not None and SUCCESS_ROW.match(row):
                bad = None
        return bad

    def recovered(self) -> bool:
        """It printed a failure row and then said it got there anyway (pip: ``ERROR: pip's dependency resolver ...``,
        then ``Successfully installed``)."""
        return self.failure() is None and any(FAILURE_ROW.search(r) for r in self.output)


def parse(rows: list[str]) -> list[Block]:
    """Rows top to bottom as blocks."""
    out: list[Block] = []
    for row in rows:
        cmd = prompt_command(row)
        if cmd is not None or not out:
            out.append(Block(cmd, [row]))
        else:
            out[-1].rows.append(row)
    return out


def has_commands(blocks: list[Block]) -> bool:
    return any(b.command for b in blocks)


def segments(command: str) -> list[str]:
    """``cd x; git init && git status`` -> ``["cd x", "git init", "git status"]``."""
    return [s.strip() for s in re.split(r"&&|\|\||;|\|", command or "") if s.strip()]


def _program(token: str) -> str:
    name = os.path.basename(token)
    if re.fullmatch(r"python[\d.]*t?", name):
        return "python"
    if re.fullmatch(r"pip[\d.]*", name):
        return "pip"
    return name


def norm(command: str) -> str:
    """A command as words, programs by name (``python3`` -> ``python``): two runs of the same command compare equal."""
    ws = words(command)
    return " ".join([_program(ws[0]), *ws[1:]]) if ws else ""


def _command_words(segment: str) -> list[str]:
    """A segment's words without env assignments and ``sudo``."""
    ws = words(segment)
    while ws and ("=" in ws[0] and not ws[0].startswith(("/", ".")) or ws[0] == "sudo"):
        ws = ws[1:]
    return ws


# python's own options that take the next word as their value (``-W ignore``, ``-X dev``)
_PY_VALUE_OPTS = frozenset({"-W", "-X", "-Q"})
# modules run with ``python -m`` that take a subcommand of their own (``python -m pip install``, ``python -m django
# startproject``); any other module's words are its arguments (``python -m venv .venv``, ``python -m http.server 8000``)
_PY_MODULES_WITH_SUBCOMMANDS = frozenset("""pip pipx uv poetry pdm hatch conda mamba django flask jupyter twine
spacy alembic celery""".split())


def _python_module_at(ws: list[str]) -> int | None:
    """The index of the module in ``python [options] -m <module> ...``: ``-m`` among python's own options only, before
    the first word that is not a flag (``python train.py -m resnet``: ``-m`` is train.py's argument), never after
    ``-c`` / ``-`` / ``--``. ``-qm pytest`` (short flags run together, ``m`` last) counts too."""
    i = 1
    while i < len(ws) - 1:
        w = ws[i]
        if w == "-m" or re.fullmatch(r"-[bBdEiIOPqRsSuvx]+m", w):
            return i + 1
        if not w.startswith("-") or w in ("-", "--", "-c"):
            return None
        i += 2 if w in _PY_VALUE_OPTS else 1
    return None


def program_and_sub(segment: str) -> tuple[str, str]:
    """(program, its first word that is not a flag): ``git checkout -b x`` -> (git, checkout); env assignments and
    ``sudo`` skipped. ``python3 -m pytest -q`` runs the module: (pytest, ""), as ``pytest -q`` is; a module's
    arguments are not a subcommand (``python -m venv .venv`` -> (venv, "")) unless the module has subcommands
    (``python -m pip install x`` -> (pip, install))."""
    ws = _command_words(segment)
    if not ws:
        return "", ""
    if _program(ws[0]) == "python" and (at := _python_module_at(ws)) is not None:
        ws = ws[at:]
        if ws[0].split(".")[0] not in _PY_MODULES_WITH_SUBCOMMANDS:
            return _program(ws[0]), ""
    sub = next((w for w in ws[1:] if not w.startswith("-")), "")
    return _program(ws[0]), sub


# the same action under another name (git 2.23+: switch / restore split out of checkout)
_SAME = {("checkout", "switch"), ("switch", "checkout"), ("checkout", "restore"), ("restore", "checkout")}

# JavaScript runners: a package script (npm run dev, yarn dev, pnpm dev, bun run dev, npm start) or a package's binary
# (npx vite, bunx vite, pnpm exec / dlx vite). A script's name says nothing of the binary it runs ("dev" is "vite"
# in package.json), so a binary run counts for a project's dev / start / build / test script (the scripts a binary
# stands in for), two scripts count when they have the same name, and two binary runs when they run the same binary.
_JS_SCRIPT_RUNNERS = frozenset({"npm", "yarn", "pnpm", "bun"})
_JS_BIN_RUNNERS = frozenset({"npx", "bunx"})
_NPM_LIFECYCLE = frozenset({"start", "test", "t", "tst", "stop", "restart"})
# package-manager commands that are not "run a script" (yarn / pnpm / bun run a script by its bare name)
_PM_OWN = frozenset("""add audit bin cache ci config create dedupe dlx exec global help i import info init install
link list login logout ls outdated pack patch prune publish rebuild remove rm store uninstall unlink up update
upgrade upgrade-interactive version why x""".split())
# the scripts a binary run stands in for, and the binary subcommands that name one (``npx vite build`` is the build
# script, never the dev one)
_SCRIPT_ROLES = frozenset("dev start build test serve preview watch".split())
# a binary subcommand that sets a project up or adds to it: no script's run
_BIN_SETUP = frozenset("init install add create new generate g".split())
# binaries that format, lint or scaffold: never a project's dev / start / build / test script
_TOOL_BINS = frozenset("prettier eslint stylelint biome husky lint-staged degit ncu npm-check-updates".split())


def _js_run(segment: str) -> tuple[str, str, list[str]] | None:
    ws = _command_words(segment)
    if not ws:
        return None
    p = _program(ws[0])
    rest = [w for w in ws[1:] if not w.startswith("-")]
    if p in _JS_BIN_RUNNERS:
        return ("bin", _bin_name(rest[0]), rest[1:]) if rest else None
    if p not in _JS_SCRIPT_RUNNERS or not rest:
        return None
    first = rest[0]
    if first in ("run", "run-script") and len(rest) > 1:
        return "script", rest[1], []
    if p == "npm":
        return ("script", {"t": "test", "tst": "test"}.get(first, first), []) if first in _NPM_LIFECYCLE else None
    if p in ("pnpm", "yarn") and first in ("exec", "dlx") and len(rest) > 1:
        return "bin", _bin_name(rest[1]), rest[2:]
    if p == "bun" and first == "x" and len(rest) > 1:
        return "bin", _bin_name(rest[1]), rest[2:]
    return None if first in _PM_OWN or first == "run" else ("script", first, [])


def _bin_name(word: str) -> str:
    """``vite@5`` -> ``vite``, ``@angular/cli@17`` -> ``@angular/cli``: a binary by name, whatever its version."""
    return re.sub(r"(?<=.)@[^/@]*$", "", word)


def js_run(segment: str) -> tuple[str, str] | None:
    """("script", name) for a package script run, ("bin", name) for a package binary run, else None (``npm install``,
    ``node app.js``)."""
    r = _js_run(segment)
    return (r[0], r[1]) if r else None


def _bin_runs_script(name: str, args: list[str], script: str) -> bool:
    """Does ``npx <name> <args>`` stand in for the package script ``script``? Only for a dev / start / build / test
    script, never for a formatter, linter or scaffolder, and a binary's own subcommand that names a script (``vite
    build``, ``vite preview``) must name this one."""
    if script not in _SCRIPT_ROLES or name in _TOOL_BINS or name.split("/")[-1].startswith("create-"):
        return False
    sub = args[0] if args else ""
    if sub in _BIN_SETUP:
        return False
    return sub == script if sub in _SCRIPT_ROLES else True


def _same_js_run(a: tuple[str, str, list[str]], b: tuple[str, str, list[str]]) -> bool:
    if a[0] == b[0]:
        return a[1] == b[1]
    binary, script = (a, b) if a[0] == "bin" else (b, a)
    return _bin_runs_script(binary[1], binary[2], script[1])


def runs(segment: str, target: str) -> bool:
    """Does a command ``segment`` run the step's ``target`` command: same program, same subcommand (a prefix either
    way: an alias ``git i`` for ``git init``; or git's switch for checkout)? ``python3 -m pytest`` runs ``pytest``,
    and a JavaScript runner runs another's script (``yarn dev`` / ``npx vite`` for ``npm run dev``)."""
    if (js := _js_run(segment)) and (tjs := _js_run(target)):
        return _same_js_run(js, tjs)
    p, s = program_and_sub(segment)
    tp, ts = program_and_sub(target)
    if not p or p != tp:
        return False
    if not ts:
        return True
    return bool(s) and (s.startswith(ts) or ts.startswith(s) or (s, ts) in _SAME)


# command-line programs a lesson's Terminal target names (a target is also what to point at in the output: "epoch 3900")
PROGRAMS = frozenset("""git gh npm npx yarn pnpm bun node deno pip pipx python uv poetry conda mamba jupyter pytest
ipython cargo rustc go java javac mvn gradle dotnet ruby gem bundle rails php composer docker kubectl helm terraform
make cmake gcc clang brew apt apt-get curl wget ssh scp cd ls mkdir touch rm cp mv cat echo source export chmod tar unzip
code open vite tsc ng flutter dart swift xcodebuild psql mysql sqlite3 redis-cli heroku vercel firebase aws gcloud
az""".split())


def is_command(text: str, extra: frozenset[str] | set[str] = frozenset()) -> bool:
    """A target's text that is a command to run (a known program first, or one of ``extra``: the programs of the
    step's run_command), not an output line to point at."""
    p, _ = program_and_sub(text)
    ws = _command_words(text)
    raw = _program(ws[0]) if ws else ""
    return bool(p) and (p in PROGRAMS or p in extra or raw in PROGRAMS or raw in extra)


def programs_of(command: str) -> set[str]:
    return {program_and_sub(s)[0] for s in segments(command)} - {""}


def superseded(blocks: list[Block], i: int) -> bool:
    """A later block runs the same command again: block ``i``'s output is no longer the latest."""
    me = norm(blocks[i].command or "")
    return bool(me) and any(norm(b.command or "") == me for b in blocks[i + 1:] if b.command)


# a command's "there was nothing left to do" refusal (git: no rebase in progress, nothing to commit, already exists)
_NOTHING_TO_DO = re.compile(r"\bno\s+\w+(?:\s+\w+)?\s+in\s+progress\b|\bnothing\s+to\s+(?:commit|do)\b"
                            r"|\balready\s+(?:exists|up[\s-]to[\s-]date|initiali[sz]ed|a\s+git\s+repository)\b", re.I)


def redundant(blocks: list[Block], i: int) -> bool:
    """Block ``i`` repeats (part of) an earlier command that already succeeded, and its output is one short "nothing to
    do" complaint (``fatal: No rebase in progress?``): nothing was left to do, nothing was undone. Never a rebuild
    that fails on new code."""
    b = blocks[i]
    me = norm(b.command or "")
    out = [r for r in b.output if r.strip()]
    if not me or not out or len(out) > 2 or not any(_NOTHING_TO_DO.search(r) for r in out):
        return False
    return any(b2.command and b2.failure() is None and me in {norm(s) for s in segments(b2.command)}
               for b2 in blocks[:i])

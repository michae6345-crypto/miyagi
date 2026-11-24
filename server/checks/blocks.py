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
                         r"|^\s*Unknown command\b|\bis not a [\w-]+ command\b", re.M)
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


def _path_base(path: str) -> str | None:
    path = path.strip().rstrip("/")
    if not path:
        return "/" if path == "" else None
    return path if path == "~" else path.rsplit("/", 1)[-1] or None


def prompt_dir(row: str) -> str | None:
    """The folder a shell prompt row shows (its last part: ``tripi@mac shop %`` -> ``shop``, ``me@box:~/a/b$`` ->
    ``b``, ``~`` for home), else None (not a prompt row, or the prompt shows no folder)."""
    ws = row.split()
    if not ws or _AUTOCAD_COMMAND.match(row):
        return None
    if ws[0] == "➜":
        return _path_base(ws[1]) if len(ws) > 1 and not ws[1].endswith(":") else None
    for j, w in enumerate(ws):
        if w in SHELL_JOIN or not after_prompt(w):
            continue
        glued = w.rstrip("%$#❯>") if len(w) > 1 else ""
        if j == 0:
            if not glued or not (len(w) > 1 and ("@" in w or ":" in w or w[0] in "~/")):
                continue
            body = glued.split(":", 1)[1] if ":" in glued else ("" if "@" in glued else glued)
            return _path_base(body) if body else None
        if not (_looks_like_prompt_start(ws[:j]) or w in ("$", "❯")):
            continue
        if glued:
            body = glued.split(":", 1)[1] if ":" in glued else ("" if "@" in glued else glued)
            return _path_base(body) if body else None
        prev = ws[j - 1]
        if "@" in prev:
            return _path_base(prev.split(":", 1)[1]) if ":" in prev else None
        return _path_base(prev)
    return None


def prompt_user(row: str) -> str | None:
    """The user name a ``user@host`` prompt shows, else None."""
    m = re.match(r"^\s*(?:\([^)]*\)\s*)?([\w.-]+)@[\w.-]+", row)
    return m.group(1) if m and prompt_command(row) is not None else None


# ---------------------------------------------------------------- AutoCAD's UNDO

_UNDO_ALL = re.compile(r"\beverything has been undone\b", re.I)
_UNDO_NAMES = re.compile(r"^\s*(?:[A-Z][A-Z0-9_]{1,20})(?:\s+[A-Z][A-Z0-9_]{1,20})*\s*$")


def _app_command(b: "Block") -> str:
    return (b.command or "").strip().lstrip("_.'").split(" ")[0].upper()


def is_undo(b: "Block") -> bool:
    """A command-line app's UNDO / U (AutoCAD): its output names what it took back."""
    return bool(b.rows) and bool(_AUTOCAD_COMMAND.match(b.rows[0])) and _app_command(b) in ("UNDO", "U")


def undone(blocks: list["Block"]) -> set[int]:
    """Indices of the blocks a later UNDO took back: all of them before an UNDO that says "Everything has been
    undone" (UNDO > Back), else, for each command name the UNDO lists (``ARC LINE``), the newest earlier block of
    that command."""
    out: set[int] = set()
    for j, b in enumerate(blocks):
        if not is_undo(b):
            continue
        before = [i for i in range(j) if blocks[i].command and i not in out and not is_undo(blocks[i])]
        if any(_UNDO_ALL.search(r) for r in b.output):
            out |= set(before)
            continue
        for row in b.output:
            if not _UNDO_NAMES.match(row):
                continue
            for name in row.split():
                hit = next((i for i in reversed(before) if i not in out and _app_command(blocks[i]) == name), None)
                if hit is not None:
                    out.add(hit)
    return out


# ---------------------------------------------------------------- a test run of part of the suite

_SELECT_FLAGS = frozenset({"-k", "--lf", "--last-failed", "--deselect", "-t", "--testNamePattern", "-run", "--grep",
                           "-g", "--only", "--testPathPattern"})


def narrows(segment: str, target: str) -> bool:
    """Does a test run ``segment`` select only some tests (``pytest x.py::test_add``, ``-k add``, ``--lf``, jest's
    ``-t``) where the step's ``target`` runs them all?"""
    tw = set(words(target))
    for w in words(segment):
        if w in tw:
            continue
        flag = w.split("=", 1)[0]
        if "::" in w or flag in _SELECT_FLAGS:
            return True
    return False


# ---------------------------------------------------------------- git status sections

_GIT_SECTION = re.compile(r"^\s*(Changes to be committed|Changes not staged for commit|Untracked files|Unmerged paths)"
                          r"\s*:\s*$")


def git_section(rows: list[str], k: int) -> str | None:
    """The ``git status`` section row ``k`` of a block's ``rows`` is listed under ("Untracked files", "Changes to be
    committed" ...), else None."""
    for r in reversed(rows[:k]):
        if m := _GIT_SECTION.match(r):
            return m.group(1)
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
        """The output row that says the command failed, unless a later row says it got there anyway; else None. Also
        a command that never ran (the shell is still waiting for its closing quote: zsh's ``dquote>``, see
        waiting_row), and a ``git config <key>`` with no value that printed nothing (a read of an unset key: git exits
        1, nothing was set)."""
        if self.command is not None and (cont := waiting_row(self.command, self.output)):
            return f"{cont.strip().split('>')[0]}> (the shell is waiting for the rest of the command: it never ran)"
        if self.command and not any(r.strip() for r in self.output) and any(
                config_read(s) for s in segments(self.command)):
            return "git config printed nothing: that key has no value (put the value after the key to set it)"
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


# the shell's continuation prompts (zsh: dquote> quote> bquote> cmdsubst> pipe> heredoc>; bash: a bare "> "): the
# command above is not finished yet (zsh stacks them: "cmdsubst dquote>")
_CONTINUATION = re.compile(r"^\s*(?:(?:d|b)?quote|cmdsubst|pipe|heredoc|cmdand|cmdor)"
                           r"(?:\s+(?:(?:d|b)?quote|cmdsubst|pipe|heredoc|cmdand|cmdor))*>\s?")
_CANCELLED = re.compile(r"\^C\s*$")
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_]\w*)\1")


def continuation(row: str) -> bool:
    """Is a terminal row one of the shell's continuation prompts (``dquote> to the menu"``, ``heredoc> EOF``)?"""
    return bool(_CONTINUATION.match(row))


def _unfinished(text: str) -> bool:
    """Is a command (its continuation rows joined with newlines) still open: a quote, a backtick or a ``$(`` not
    closed yet, or a last line ending in ``|`` / ``&&`` / ``\\``?"""
    quote, depth, k = "", 0, 0
    while k < len(text):
        ch = text[k]
        if ch == "\\" and quote != "'":
            k += 2
            continue
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "'\"`":
            quote = ch
        elif text.startswith("$(", k):
            depth, k = depth + 1, k + 1
        elif ch == ")" and depth:
            depth -= 1
        k += 1
    return bool(quote) or depth > 0 or text.rstrip().endswith(("|", "&&", "\\"))


def waiting_row(command: str, output: list[str]) -> str | None:
    """The continuation row (zsh's ``dquote>`` / ``heredoc>`` ...) that says the command above never ran, else None:
    the shell is still waiting at it (it is the last row printed, and the command typed so far with every continuation
    row is still open: a quote not closed, a heredoc without its end word), or the learner cancelled it there
    (``dquote> ^C``, or a ``^C`` row under it). A quote closed on a later row (``dquote> to the menu"``), a heredoc
    ended by its word (``heredoc> EOF``), and a command that printed something after its last continuation row ran."""
    rows = [r for r in output if r.strip()]
    conts = [k for k, r in enumerate(rows) if _CONTINUATION.match(r)]
    if not conts:
        return None
    for k in conts:
        if _CANCELLED.search(rows[k]) or (k + 1 < len(rows) and rows[k + 1].strip() == "^C"):
            return rows[k]
    last = conts[-1]
    if last != len(rows) - 1:
        return None
    bodies = [_CONTINUATION.sub("", r, count=1) for r in rows[conts[0]:]]
    if ends := [m.group(2) for m in _HEREDOC.finditer(command)]:
        lines, at = [b.strip() for b in bodies], 0
        for word in ends:
            if word not in lines[at:]:
                return rows[last]
            at = lines.index(word, at) + 1
        return None
    return rows[last] if _unfinished("\n".join([command, *bodies])) else None
# git config options that are not a key or a value
_GIT_CONFIG_SCOPE = frozenset({"--global", "--local", "--system", "--worktree", "--type", "--bool", "--int", "--path"})


def dry_run(segment: str) -> bool:
    """A command that only shows what it would do (``git push --dry-run``, ``git push -n``, ``npm publish --dry-run``,
    ``rsync -n``): it changes nothing."""
    ws = _command_words(segment)
    if any(w.split("=", 1)[0] in ("--dry-run", "--dryrun", "--what-if") for w in ws[1:]):
        return True
    p, sub = program_and_sub(segment)
    return p == "git" and sub in ("push", "add", "clean", "rm", "mv") and "-n" in ws[2:]


_SKIPPED = re.compile(r"\b(\d+)\s+(?:skipped|pending|todo|deselected)\b", re.I)
_TEST_SUMMARY = re.compile(r"^\s*Tests?:|\bpassed\b|\bpassing\b|^\s*=+.*\b(?:passed|failed)\b", re.I)


def skipped_tests(output: list[str], in_files: bool = False) -> int:
    """How many tests a test run's summary says it skipped (Jest's ``Tests: 2 skipped, 1 passed, 3 total``, pytest's
    ``1 passed, 2 skipped``, mocha's ``2 pending``), else 0. ``in_files``: only the ones a test file skipped
    (skipped / pending), not the ones the command line left out (pytest's ``deselected``) or ``todo`` tests."""
    n = 0
    for row in output:
        if _TEST_SUMMARY.search(row):
            n = max(n, sum(int(m.group(1)) for m in _SKIPPED.finditer(row)
                           if not in_files or m.group(0).split()[-1].lower() in ("skipped", "pending")))
    return n


def new_branch(segment: str) -> str | None:
    """The branch a command makes and moves to: ``git switch -c x`` / ``git checkout -b x`` -> x."""
    ws = _command_words(segment)
    if len(ws) < 4 or _program(ws[0]) != "git" or ws[1] not in ("switch", "checkout"):
        return None
    for k, w in enumerate(ws[2:-1], start=2):
        if w in ("-c", "-C", "--create", "-b", "-B"):
            return ws[k + 1]
    return None


def config_read(segment: str) -> bool:
    """``git config [--global] user.name``: a key and no value, which reads the key instead of setting it."""
    ws = _command_words(segment)
    if len(ws) < 3 or _program(ws[0]) != "git" or ws[1] != "config":
        return False
    rest = ws[2:]
    if any(w.startswith("-") and w.split("=", 1)[0] not in _GIT_CONFIG_SCOPE for w in rest):
        return False  # --list, --get, --unset, -e, --file x ...
    args = [w for w in rest if not w.startswith("-")]
    return len(args) == 1 and "." in args[0]


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
    if p == "gh" and tp == "git" and ts in gh_git_steps(segment):
        return True
    if not p or p != tp:
        return False
    if not ts:
        return True
    if not (bool(s) and (s.startswith(ts) or ts.startswith(s) or (s, ts) in _SAME)):
        return False
    return not _other_ref(segment, target)


def gh_git_steps(segment: str) -> set[str]:
    """The git subcommands a GitHub CLI command runs for the learner: ``gh repo create x --source=. --remote=origin
    --push`` adds the remote and pushes (``remote``, ``push``); ``gh repo clone`` clones."""
    ws = _command_words(segment)
    if len(ws) < 3 or _program(ws[0]) != "gh" or ws[1] != "repo":
        return set()
    if ws[2] == "clone":
        return {"clone"}
    if ws[2] != "create":
        return set()
    flags = {w.split("=", 1)[0] for w in ws[3:] if w.startswith("-")}
    out = set()
    if flags & {"--source", "-s", "--remote", "-r"}:
        out.add("remote")
    if "--push" in flags:
        out.add("push")
    return out


# git commands whose first argument says which way the work goes: ``git merge main`` on the branch is the other way
# round from ``git merge add-waffles`` on main
_REF_DIRECTED = frozenset({"merge", "rebase", "cherry-pick", "revert"})


def _ref_arg(segment: str) -> str | None:
    ws = _command_words(segment)
    if len(ws) < 3 or _program(ws[0]) != "git" or ws[1] not in _REF_DIRECTED:
        return None
    return next((w for w in ws[2:] if not w.startswith("-")), None)


def _other_ref(segment: str, target: str) -> bool:
    """Does ``segment`` name another branch / commit than the step's ``target`` for a git command whose argument sets
    its direction (merge, rebase)? A remote's copy of the branch (``origin/add-waffles``) is the same one; a target
    with a placeholder (``<branch>``) takes any."""
    a, t = _ref_arg(segment), _ref_arg(target)
    if not a or not t or re.search(r"[<>{}\[\]~^@]|\.\.\.", t) or re.fullmatch(r"[0-9a-f]{7,40}", t):
        return False  # a placeholder, or a commit counted back from HEAD / named by its hash: how far is the learner's
    a, t = a.lower(), t.lower()
    return a != t and not a.endswith("/" + t) and not t.endswith("/" + a)


def retried(blocks: list[Block], i: int) -> bool:
    """Block ``i`` is a git command that failed, and a later run of the same git subcommand succeeded (``git commit
    -m x pancakes.md`` -> ``error: pathspec``, then ``git add`` and ``git commit -m x``): the learner got past it."""
    b = blocks[i]
    if not b.command or b.failure() is None:
        return False
    mine = {program_and_sub(s) for s in segments(b.command)}
    mine = {m for m in mine if m[0] == "git" and m[1]}
    return bool(mine) and any(
        n.command and n.failure() is None and mine & {program_and_sub(s) for s in segments(n.command)}
        for n in blocks[i + 1:])


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


# a command that failed only because the repository wasn't set up yet, and the later commands that set it up
_CURED_BY = ((re.compile(r"\bdoes not have any commits yet\b|\bbad default revision 'HEAD'", re.I),
              {("git", "commit")}),
             (re.compile(r"\bnot a git repository\b", re.I), {("git", "init"), ("git", "clone")}))


# the same result printed another way: a pull that brought commits in prints "Fast-forward" and a diffstat when it
# fast-forwards, but "Successfully rebased and updated refs/heads/main." with pull.rebase set, and "Merge made by the
# 'ort' strategy." when it merges
_SAME_OUTCOME = ((("Fast-forward", " 1 file changed, 1 insertion(+)"), {("git", "pull"), ("git", "merge"), ("git", "rebase")},
                  re.compile(r"^\s*Successfully rebased and updated refs/heads/|^\s*Merge made by the\b")),)


_HEAD_PUSH = re.compile(r"(\s)HEAD\s*->\s*([\w./-]+)")
_TRACKS = re.compile(r"\bbranch '([\w./-]+)' set up to track\b")


def same_outcome(matches, b: "Block") -> bool:
    """Does block ``b`` print, in another form, what a check (``matches``: does the check's pattern find a text?) looks
    for in a command's usual output: a rebasing ``git pull`` for "Fast-forward"?"""
    if not b.command or b.failure() is not None:
        return False
    if any(program_and_sub(s) == ("git", "push") or "push" in gh_git_steps(s) for s in segments(b.command)):
        # a push of the checked-out branch prints "HEAD -> main" (gh pushes HEAD); git's next row says HEAD was main
        tracked = {m.group(1) for r in b.output if (m := _TRACKS.search(r))}
        text = _HEAD_PUSH.sub(lambda m: f"{m.group(1)}{m.group(2)} -> {m.group(2)}" if m.group(2) in tracked
                              else m.group(0), b.text)
        if text != b.text and matches(text):
            return True
    for samples, cmds, alt in _SAME_OUTCOME:
        if any(program_and_sub(s) in cmds for s in segments(b.command)) and any(matches(x) for x in samples) \
                and any(alt.search(r) for r in b.output):
            return True
    return False


def cured(blocks: list[Block], i: int) -> bool:
    """Block ``i`` failed only because something wasn't set up yet (``git log`` before the first commit: "your current
    branch 'main' does not have any commits yet"; ``git status`` before ``git init``), and a later command set it up
    and succeeded: the failure changed nothing and is history."""
    bad = blocks[i].failure()
    if not bad:
        return False
    for rx, fixes in _CURED_BY:
        if not rx.search(bad):
            continue
        for b in blocks[i + 1:]:
            if b.command and b.failure() is None and any(program_and_sub(s) in fixes for s in segments(b.command)):
                return True
    return False


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

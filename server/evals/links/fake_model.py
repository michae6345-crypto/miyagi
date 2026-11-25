"""A deterministic stand-in for the models of a link lesson: free, offline, the same answer every run.

Two calls, as in the contract (shared/contracts/ANY-LINK.md, "Models"):

- `verdict(page)` stands in for the small Haiku call on the page outline: is it teachable (steps to follow, code to
  type or run), and one line on why;
- `generate_json(system, prompt, schema, ...)` stands in for `server.lesson.claude._generate_json` during the build
  (the plan call and one call per step). It is a FAITHFUL, DUMB model: one plan step per code block of the page (a
  shell block is one run step with its commands, a block of code is typed into the file the page names), every block
  copied verbatim, 3-8 steps (blocks for the same file merged, then the page cut at a section boundary, as the contract
  says a long page is), a check on the most distinctive line of each code step.

So the eval measures the deterministic parts of a link lesson (reading the page, the teachable gate, and the engine's
own shaping of the steps: order_plan, plan_runs, strip_injection's command allowlist, sanitize_step, coverage, repair,
the lesson schema), never a model's judgement. A block that a faithful model put in a step and the lesson does not
carry was lost by the engine.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from server.lesson import builder, textlesson

from .reader import Page

SHELL_LANGS = frozenset({"bash", "sh", "shell", "console", "zsh", "shell-session", "shellsession", "powershell", "ps",
                         "cmd", "terminal", "sh-session"})
OUTPUT_LANGS = frozenset({"text", "output", "none", "plaintext", "txt", "log"})
_CMD_HEAD = re.compile(r"^(?:python3?|pip3?|uv|npm|npx|node|yarn|pnpm|git|cd|ls|mkdir|touch|source|export|brew|curl|"
                       r"wget|flask|pytest|blender|cargo|go|make|docker|cat|echo|code|open|deactivate|\.)(?:\s|$)")
_PROMPT = re.compile(r"^\s*(?:\([\w.-]+\)\s*)?[$%]\s+")  # "$ ", "% ", "(tutorial-env) $ "
_REPL = re.compile(r"^\s*(>>>|\.\.\.)(\s|$)")
_FILE_NAME = re.compile(r"\b([\w-]+(?:/[\w.-]+)*\.(py|js|mjs|jsx|ts|tsx|html|css|json|toml|ya?ml|md|txt))\b")
_FILE_COMMENT = re.compile(r"^\s*(?:#|//|<!--|/\*)\s*(?:file(?:name)?:\s*)?([\w./-]+\.\w+)\s*(?:-->|\*/)?\s*$", re.IGNORECASE)
_DEF = re.compile(r"^(?:async\s+)?(?:def|class|function)\s+([A-Za-z_]\w*)|^(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=|"
                  r"^([A-Za-z_]\w*)\s*=(?!=)")
_EXT = {"python": "py", "py": "py", "python3": "py", "pycon": "py", "javascript": "js", "js": "js", "node": "js",
        "jsx": "jsx", "typescript": "ts", "ts": "ts", "html": "html", "css": "css", "json": "json", "toml": "toml",
        "yaml": "yml", "yml": "yml"}
_PRODUCTS = frozenset({"node", "vue", "next", "nuxt", "three", "express", "react", "d3", "chart", "p5", "socket", "ember",
                       "backbone", "angular", "alpine", "solid", "deno", "bun"})  # "Node.js" is not a file
_EXTS = {"py": ("py",), "js": ("js", "mjs", "cjs"), "yml": ("yml", "yaml")}
_DEFAULT_FILE = {"py": "main.py", "js": "app.js", "jsx": "App.jsx", "ts": "main.ts", "html": "index.html", "css": "style.css",
                 "json": "data.json", "toml": "pyproject.toml", "yml": "config.yml"}
_IMPERATIVE = re.compile(r"^(open|click|press|select|choose|run|install|create|add|type|go|set|enter|save|drag|move|scale|"
                         r"rotate|extrude|switch|hold|use|make|right-click|double-click|pick|start|close|navigate|change|"
                         r"turn|toggle|apply|tab|hover|delete|duplicate|render|export|import|copy|paste|edit|write)\b", re.IGNORECASE)
MAX_PLAN = 8
MIN_PLAN = 3


@dataclass
class Unit:
    kind: str  # "code" | "run" | "app"
    section: int
    heading: str
    file: str = ""
    code: str = ""
    commands: list[str] = field(default_factory=list)
    output: str = ""
    lang: str = ""


# --------------------------------------------------------------------------- the teachable verdict (Haiku's stand-in)

def _is_output(code: str, lang: str) -> bool:
    if lang in OUTPUT_LANGS:
        return True
    if lang:
        return False
    lines = [ln for ln in code.splitlines() if ln.strip()]
    return bool(lines) and not any(_PROMPT.match(ln) or _REPL.match(ln) or _CMD_HEAD.match(ln.strip()) or
                                   re.search(r"[(){}=:;\[\]]", ln) for ln in lines)


def verdict(page: Page) -> dict:
    """{teachable, teach: {steps, code}, why}: what link.preview's Haiku call answers, decided on the outline."""
    real = [c for c in page.code if not _is_output(c.text, c.lang)]
    code = len(real) >= 2 or any(len([ln for ln in c.text.splitlines() if ln.strip()]) >= 3 for c in real)
    steps = any(len(s.ordered) >= 3 and sum(bool(_IMPERATIVE.match(x)) for x in s.ordered) * 3 >= len(s.ordered) * 2
                for s in page.sections)
    if code and steps:
        why = "Walks through code to type and steps to follow."
    elif code:
        why = "Has code you type and run, one piece at a time."
    elif steps:
        why = "Walks through steps you follow in the app."
    elif page.code:
        why = "Shows a little code, but nothing to build or follow along."
    else:
        why = "It's reading, with nothing to do or type."
    return {"teachable": code or steps, "teach": {"steps": steps, "code": code}, "why": why}


# --------------------------------------------------------------------------- the plan (Sonnet's stand-in)

def _file_for(code: str, lang: str, page: Page, section: int, last: dict[str, str]) -> str:
    first = next((ln for ln in code.splitlines() if ln.strip()), "")
    if m := _FILE_COMMENT.match(first):
        return m.group(1)
    ext = _EXT.get(lang, "")
    if not ext:
        ext = "py" if re.search(r"^\s*(def |import |from \w+ import|print\()", code, re.MULTILINE) else (
            "js" if re.search(r"\b(const|let|function|=>|console\.log)\b", code) else (
                "html" if re.search(r"<\w+[^>]*>", code) else "py"))
    exts = _EXTS.get(ext, (ext,))

    def named(texts) -> str | None:
        for text in texts:
            for m in _FILE_NAME.finditer(text):
                if m.group(2) in exts and m.group(1).rsplit(".", 1)[0].lower() not in _PRODUCTS:
                    return m.group(1)
        return None

    sec = page.sections[section]
    return (named([sec.heading] + sec.text) or last.get(ext)
            or named(t for s in page.sections for t in [s.heading] + s.text)  # the page names it elsewhere
            or _DEFAULT_FILE.get(ext, f"main.{ext}"))


def units(page: Page) -> list[Unit]:
    """The page's code blocks, in order, as plan units (an output block rides on the run before it)."""
    out: list[Unit] = []
    last_file: dict[str, str] = {}
    for c in page.code:
        lines = c.text.splitlines()
        heading = page.sections[c.section].heading
        if any(_PROMPT.match(ln) for ln in lines):  # a console session: the prompted lines are commands
            cmds = [_PROMPT.sub("", ln).strip() for ln in lines if _PROMPT.match(ln)]
            outp = "\n".join(ln for ln in lines if not _PROMPT.match(ln) and ln.strip())
            out.append(Unit("run", c.section, heading, commands=cmds, output=outp, lang=c.lang))
            continue
        if any(_REPL.match(ln) for ln in lines):  # a REPL session: the prompted lines are code
            code = "\n".join(_REPL.sub("", ln, count=1) for ln in lines if _REPL.match(ln))
            f = _file_for(code, "python", page, c.section, last_file)
            last_file["py"] = f
            out.append(Unit("code", c.section, heading, file=f, code=code.strip("\n"), lang="python"))
            continue
        body = [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]
        if c.lang in SHELL_LANGS or (not c.lang and body and all(_CMD_HEAD.match(ln) for ln in body)):
            out.append(Unit("run", c.section, heading, commands=body, lang=c.lang or "bash"))
            continue
        if _is_output(c.text, c.lang):
            if out and out[-1].kind == "run" and not out[-1].output:
                out[-1].output = c.text
            continue
        f = _file_for(c.text, c.lang, page, c.section, last_file)
        last_file[f.rsplit(".", 1)[-1]] = f
        out.append(Unit("code", c.section, heading, file=f, code=c.text, lang=c.lang))
    if not out:  # an app page: its numbered steps, one unit per section
        for i, s in enumerate(page.sections):
            if len(s.ordered) >= 2:
                out.append(Unit("app", i, s.heading, code="\n".join(s.ordered)))
    return out


def _one_command_each(us: list[Unit]) -> list[Unit]:
    """A run unit per command, block by block, while the lesson stays within MAX_PLAN steps (a model follows the page's
    commands one at a time when it can); the output stays with the block's last command."""
    out = list(us)
    k = 0
    while k < len(out):
        u = out[k]
        if u.kind == "run" and len(u.commands) > 1 and len(out) + len(u.commands) - 1 <= MAX_PLAN:
            parts = [Unit(**{**u.__dict__, "commands": [c], "output": u.output if j == len(u.commands) - 1 else ""})
                     for j, c in enumerate(u.commands)]
            out[k:k + 1] = parts
            k += len(parts)
        else:
            k += 1
    return out


def _merge(us: list[Unit], *, same_section: bool) -> list[Unit]:
    merged: list[Unit] = []
    for u in us:
        p = merged[-1] if merged else None
        if p and p.kind == u.kind == "code" and p.file == u.file and (not same_section or p.section == u.section):
            p.code = p.code.rstrip("\n") + "\n\n" + u.code
            continue
        merged.append(Unit(**{**u.__dict__, "commands": list(u.commands)}))
    return merged


def plan_units(page: Page) -> tuple[list[Unit], bool]:
    """3-8 units; True when the page was cut (the lesson covers its first part)."""
    us = _merge(units(page), same_section=True)
    if len(us) > MAX_PLAN:
        us = _merge(us, same_section=False)
    cut = False
    if len(us) > MAX_PLAN:  # cut at a section boundary
        keep = MAX_PLAN
        while keep > MIN_PLAN and us[keep].section == us[keep - 1].section:
            keep -= 1
        us, cut = us[:keep], True
    us = _one_command_each(us)
    while 0 < len(us) < MIN_PLAN:  # split the biggest code block at a top-level blank line
        big = max((u for u in us if u.kind == "code"), key=lambda u: len(u.code), default=None)
        parts = re.split(r"\n\s*\n(?=\S)", big.code) if big else []
        if len(parts) < 2:
            break
        k = us.index(big)
        half = len(parts) // 2
        a = Unit(**{**big.__dict__, "code": "\n\n".join(parts[:half])})
        b = Unit(**{**big.__dict__, "code": "\n\n".join(parts[half:])})
        us[k:k + 1] = [a, b]
    return us, cut


def _names(code: str) -> list[str]:
    out = []
    for ln in code.splitlines():
        if m := _DEF.match(ln):
            n = next(g for g in m.groups() if g)
            if n not in out:
                out.append(n)
    return out[:8]


def _distinctive(code: str) -> str:
    lines = [ln.strip() for ln in code.splitlines() if re.search(r"[A-Za-z]{2}", ln) and not ln.strip().startswith(("#", "//"))]
    lines = [ln for ln in lines if len(ln) <= 60] or [ln[:60] for ln in lines]
    return max(lines, key=len) if lines else ""


def _title(u: Unit, used: set[str]) -> str:
    if u.kind == "run":
        words = " ".join(u.commands[0].split()[:3]) if u.commands else "the command"
        t = f"Run {words}"
    elif u.kind == "app":
        t = u.heading or "Follow the steps"
    else:
        names = _names(u.code)
        t = f"Write {names[0]}" if names else (u.heading or f"Add code to {u.file}")
    t = " ".join(t.replace('"', "").replace("'", "").split()[:6])
    base, n = t, 2
    while t.lower() in used:
        t = f"{' '.join(base.split()[:5])} ({n})"
        n += 1
    used.add(t.lower())
    return t


def _libraries(page: Page, us: list[Unit]) -> list[dict]:
    libs: dict[str, str] = {}
    for u in us:
        for cmd in u.commands:
            toks = cmd.split()
            if "install" in toks:
                for t in toks[toks.index("install") + 1:]:
                    if not t.startswith("-") and re.match(r"^[A-Za-z0-9@][\w.@/-]*$", t):
                        libs.setdefault(re.split(r"[<>=@]", t)[0] or t, "latest")
        if u.lang in ("python", "py") or u.file.endswith(".py"):
            libs.setdefault("python", "3.12")
        if u.file.endswith((".js", ".jsx")):
            libs.setdefault("node", "22")
    return [{"name": k, "version": v} for k, v in libs.items()]


class FakeModel:
    """One per build: answers the plan call and each step call from the page."""

    def __init__(self, page: Page):
        self.page = page
        self.units, self.cut = plan_units(page)
        used: set[str] = set()
        self.titles = [_title(u, used) for u in self.units]
        self.calls: list[str] = []

    # the plan
    def plan(self) -> dict:
        steps = []
        for u, t in zip(self.units, self.titles):
            if u.kind == "run":
                instr = f"Run {u.commands[0].split()[0] if u.commands else 'it'} in the terminal."
            elif u.kind == "app":
                instr = "Follow these steps in the app."
            else:
                instr = f"Add this code to {u.file}."
            steps.append({"title": t, "instructions": instr, "file": u.file if u.kind == "code" else "",
                          "what": " ".join((u.heading or t).split()[:12]), "why": "The page does this here.", "concepts": [],
                          "estMinutes": 2 if u.kind == "run" else 4, "adds": _names(u.code) if u.kind == "code" else []})
        title = self.page.title or "Lesson from a page"
        return {"title": " ".join(title.split()[:6]), "libraries": _libraries(self.page, self.units),
                "overview": ("We follow the page step by step" + (", its first part" if self.cut else "") + "."),
                "primer": [], "steps": steps, "build": {"summary": title[:80], "outcome": "What the page builds."},
                "flow": [], "prerequisites": [], "learnFirst": []}

    # one step
    def step(self, title: str) -> dict:
        k = next((i for i, t in enumerate(self.titles) if t == title), None)
        if k is None:  # the run step textlesson.plan_runs adds ("Run app.py")
            f = title.split(" ", 1)[1] if " " in title else ""
            cmd = f"{'node' if f.endswith(('.js', '.mjs')) else 'python3'} {f}"
            return {"file": "", "code": "", "run_command": cmd, "hints": ["Run it in the terminal."],
                    "checks": [{"type": "screen_absent", "label": "No errors", "app": "Terminal",
                                "pattern": r"Traceback|Error:"}],
                    "targets": [{"file": f, "match": cmd, "caption": "Run it here"}]}
        u = self.units[k]
        if u.kind == "run":
            cmd = "\n".join(u.commands)
            outl = [ln.strip() for ln in u.output.splitlines() if ln.strip()]
            checks = ([{"type": "screen_contains", "label": "Prints the result", "app": "Terminal",
                        "pattern": builder.literal_pattern(outl[-1][:60])}] if outl else
                      [{"type": "screen_absent", "label": "No errors in the terminal", "app": "Terminal",
                        "pattern": r"command not found|Error:|fatal:"}])
            return {"file": "", "code": "", "run_command": cmd, "expected_output": u.output, "checks": checks,
                    "targets": [{"file": "", "match": u.commands[0][:40] if u.commands else "run", "caption": "Run it here"}],
                    "hints": ["Type the command exactly as the page shows it."], "common_mistakes": []}
        if u.kind == "app":
            return {"file": "", "code": "", "checks": [{"type": "screen_contains", "label": "Done in the app", "app": "",
                                                       "pattern": builder.literal_pattern(u.heading or "done")}],
                    "targets": [], "hints": u.code.splitlines()[:3]}
        frag = _distinctive(u.code)
        first = next((ln.strip() for ln in u.code.splitlines() if ln.strip()), "")
        return {"file": u.file, "code": u.code,
                "checks": [{"type": "screen_contains", "label": "The code is typed", "app": "Code",
                            "pattern": builder.literal_pattern(frag)}] if frag else [],
                "precision_checks": [{"type": "file_contains", "label": "In the file", "file": u.file,
                                      "pattern": builder.literal_pattern(frag)}] if frag else [],
                "targets": [{"file": u.file, "match": first[:40], "caption": "Type it here"}],
                "hints": ["Copy it exactly as the page shows it."], "common_mistakes": []}

    async def generate_json(self, system, prompt, schema, *, role=None, check=None, prefix="", **kw):
        """claude._generate_json's signature. A `check` that fails is a RuntimeError, as after the real escalation."""
        if schema is textlesson.PLAN_SCHEMA:
            self.calls.append("plan")
            out = self.plan()
        else:
            m = re.search(r'Write step (\d+): "(.*?)"\.', (prefix or "") + "\n" + prompt)
            if not m:
                raise RuntimeError("fake model: no step in the prompt")
            self.calls.append(f"step:{m.group(2)}")
            out = self.step(m.group(2))
        if check is not None and (problem := check(out)):
            raise RuntimeError(f"fake model: {problem}")
        return out

    async def research(self, goal: str) -> dict:
        """The page stands in for the research notes (the contract: the page text in place of the transcript)."""
        return {"notes": self.page.text[:4000], "sources": [{"url": self.page.url, "title": self.page.title or self.page.site}]}

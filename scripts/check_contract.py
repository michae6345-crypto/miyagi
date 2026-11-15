#!/usr/bin/env python3
"""Contract conformance check: does the app handle everything the contract declares?

Static only (no network, no engine, no API calls, standard library only). It parses
shared/contracts/events.ts and looks for evidence in the app source (app/src) that each
declared item is handled:

  event           every key of EngineEvents (+ config.status): listed in wire.ts KNOWN (else the
                  parser silently drops it) AND has an onMessage('<type>', ...) handler
  card.kind       every card.kind: a key of the cards KIND map
  card.action     every card.actions value: a key of the cards ACTION map, or a cardAct('<kind>') call
  offtrack.action every offtrack.actions value: a button that tests actions.includes('<kind>')
  action.kind     every action.kind (app -> engine): something sends it
                  (cmd('action', {kind}), sendAction/triggerShortcut/cardAct/act('<kind>'), kind: '<kind>', ACTION key)
  command         every AppCommands key: cmd('<type>', ...) or {type: '<type>'}
                  (top-level end_lesson also counts as sent when the end_lesson action is, the engine treats both alike)
  diagram.kind    every diagram.kind: a view branch under features/diagrams

Usage:
  python3 scripts/check_contract.py                       # working tree: app/src
  python3 scripts/check_contract.py --ref origin/adrian/shell   # read app/src from a git ref
  python3 scripts/check_contract.py --all                 # also list what is handled, and allowed items
  python3 scripts/check_contract.py --json

Exit code: 0 = everything handled, 1 = something is missing, 2 = the check itself could not run
(no contract / no app sources). If a structure it relies on is absent (the wire.ts KNOWN set, the
cards KIND or ACTION map) that is reported as a `structure` finding and everything that depends on
it counts as missing, so the check never passes silently.

Deliberate gaps go in scripts/contract_check_allow.txt, one `category:name  # reason` per line.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONTRACT = "shared/contracts/events.ts"
DEFAULT_APP = "app/src"
DEFAULT_ALLOW = "scripts/contract_check_allow.txt"
SKIP_PATH = re.compile(r"(^|/)(node_modules|dev|mock|mocks|__tests__)/|\.(test|spec|stories)\.tsx?$|\.d\.ts$")


class CheckError(Exception):
    """The check could not run (exit 2)."""


# --------------------------------------------------------------------------- TypeScript scanning
def strip_comments(src: str) -> str:
    """Remove // and /* */ comments, leaving string literals alone."""
    out: List[str] = []
    i, n, quote = 0, len(src), None
    while i < n:
        c = src[i]
        if quote:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(src[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in "\"'`":
            quote = c
            out.append(c)
            i += 1
            continue
        if c == "/" and src[i + 1:i + 2] == "/":
            while i < n and src[i] != "\n":
                i += 1
            continue
        if c == "/" and src[i + 1:i + 2] == "*":
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
            out.append(" ")
            continue
        out.append(c)
        i += 1
    return "".join(out)


def strip_app_comments(src: str) -> str:
    """Lighter, JSX-safe stripping for app files: block comments and whole-line // comments."""
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", src)


def match_close(s: str, open_idx: int) -> int:
    """Index of the bracket closing the one at open_idx ({ [ or ( ), skipping string literals."""
    pairs = {"{": "}", "[": "]", "(": ")"}
    open_ch = s[open_idx]
    close_ch = pairs[open_ch]
    depth, i, quote = 0, open_idx, None
    while i < len(s):
        c = s[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "\"'`":
            quote = c
        elif c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise CheckError("unbalanced %r starting at offset %d" % (open_ch, open_idx))


def split_entries(body: str) -> List[str]:
    """Split a member list at depth-0 ',' and ';' (brackets and string literals respected)."""
    entries: List[str] = []
    depth, start, i, quote = 0, 0, 0, None
    while i < len(body):
        c = body[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "\"'`":
            quote = c
        elif c in "{[(":
            depth += 1
        elif c in "}])":
            depth -= 1
        elif c in ",;" and depth == 0:
            entries.append(body[start:i])
            start = i + 1
        i += 1
    entries.append(body[start:])
    return [e.strip() for e in entries if e.strip()]


KEY = re.compile(r"""^(?:"([^"]+)"|'([^']+)'|([A-Za-z_$][\w$]*))\s*\??\s*:""")


def parse_members(body: str) -> Dict[str, str]:
    """{key: raw value text} for the depth-0 members of an object type / object literal body."""
    members: Dict[str, str] = {}
    for entry in split_entries(body):
        m = KEY.match(entry)
        if m:
            members[m.group(1) or m.group(2) or m.group(3)] = entry[m.end():].strip()
    return members


def block_after(text: str, pattern: str, flags: int = 0) -> Optional[str]:
    """Body (between the braces) of the first `{` that follows the regex `pattern`."""
    m = re.search(pattern, text, flags)
    if not m:
        return None
    open_idx = m.end() - 1  # the pattern ends with the opening brace
    return text[open_idx + 1:match_close(text, open_idx)]


def literals(text: str) -> List[str]:
    return re.findall(r"""["']([^"']+)["']""", text)


def object_body(value: str) -> str:
    value = value.strip()
    if not value.startswith("{"):
        raise CheckError("expected an object type, got: %s" % value[:60])
    return value[1:match_close(value, 0)]


# --------------------------------------------------------------------------- the contract
class Contract:
    def __init__(self, src: str):
        src = strip_comments(src)
        events = block_after(src, r"export\s+interface\s+EngineEvents\s*\{")
        commands = block_after(src, r"export\s+interface\s+AppCommands\s*\{")
        keystatus = block_after(src, r"export\s+interface\s+KeyStatusEvent\s*\{")
        if events is None or commands is None:
            raise CheckError("could not find `interface EngineEvents` / `interface AppCommands` in the contract")
        ev = parse_members(events)
        cm = parse_members(commands)
        self.events: List[str] = list(ev) + [k for k in parse_members(keystatus or "") if k not in ev]
        self.commands: List[str] = list(cm)
        card = parse_members(object_body(ev["card"]))
        offtrack = parse_members(object_body(ev["offtrack"]))
        diagram = parse_members(object_body(ev["diagram"]))
        action = parse_members(object_body(cm["action"]))
        self.card_kinds = literals(card["kind"])
        self.card_actions = literals(card["actions"])
        self.offtrack_actions = literals(offtrack["actions"])
        self.diagram_kinds = literals(diagram["kind"])
        self.action_kinds = literals(action["kind"])
        for name, vals in (("card.kind", self.card_kinds), ("card.actions", self.card_actions),
                           ("action.kind", self.action_kinds), ("diagram.kind", self.diagram_kinds)):
            if not vals:
                raise CheckError("contract: found no values for %s (did the shape change?)" % name)


# --------------------------------------------------------------------------- the app
class App:
    def __init__(self, files: Dict[str, str], label: str):
        self.files = {p: strip_app_comments(t) for p, t in files.items() if not SKIP_PATH.search(p)}
        self.label = label

    # -- collectors
    def known(self) -> Tuple[Set[str], str]:
        """(KNOWN set, file); raises CheckError when the allow-list isn't in the app."""
        pat = re.compile(r"\bKNOWN\b[^=\n]*=\s*new Set(?:<[^>]*>)?\(\s*\[")
        for path, text in sorted(self.files.items()):
            m = pat.search(text)
            if m:
                close = match_close(text, m.end() - 1)
                return set(literals(text[m.end():close])), path
        raise CheckError("no `KNOWN = new Set([...])` found in the app (the wire.ts parser's allow-list)")

    def handlers(self) -> Dict[str, List[str]]:
        found: Dict[str, List[str]] = {}
        direct = re.compile(r"""\bonMessage\(\s*['"]([^'"]+)['"]""")
        loop = re.compile(r"""for\s*\(\s*const\s+(\w+)\s+of\s*\[([^\]]*)\][^)]*\)\s*onMessage\(\s*\1\b""")
        for path, text in self.files.items():
            for m in direct.finditer(text):
                found.setdefault(m.group(1), []).append(path)
            for m in loop.finditer(text):
                for t in literals(m.group(2)):
                    found.setdefault(t, []).append(path)
        return found

    def map_keys(self, names: Iterable[str], hint: str) -> Tuple[Set[str], str]:
        order = sorted(self.files, key=lambda p: (hint not in "/" + p, p))
        for name in names:
            decl = re.compile(r"\bconst\s+%s\b" % re.escape(name))
            assign = re.compile(r"(?<![=!<>])=(?!=)\s*\{")
            for path in order:
                text = self.files[path]
                m = decl.search(text)
                if not m:
                    continue
                a = assign.search(text, m.end())
                if a:
                    open_idx = a.end() - 1
                    return set(parse_members(text[open_idx + 1:match_close(text, open_idx)])), path
        raise CheckError("no `const %s = {...}` map found in the app (looked under %r first)" % ("/".join(names), hint))

    def pattern_hits(self, regex: str, flags: int = 0, group: int = 1) -> Set[str]:
        pat = re.compile(regex, flags)
        return {m.group(group) for text in self.files.values() for m in pat.finditer(text)}

    def sent_action_kinds(self, action_map_keys: Set[str]) -> Set[str]:
        sent = set(action_map_keys)  # cardAct(a) sends every key of the ACTION map
        sent |= self.pattern_hits(r"""\b(?:sendAction|triggerShortcut|cardAct|act)\(\s*['"](\w+)['"]""")
        sent |= self.pattern_hits(r"""\bcmd\(\s*['"]action['"]\s*,\s*\{[^}]*?\bkind:\s*['"](\w+)['"]""", re.S)
        sent |= self.pattern_hits(r"""\bkind:\s*['"](\w+)['"]\s*[,}]""")  # shortcut-bar style items
        return sent

    def sent_commands(self) -> Set[str]:
        return self.pattern_hits(r"""(?:\bcmd\(\s*|\btype:\s*)['"]([\w.]+)['"]""")

    def diagram_kinds_shown(self, kinds: List[str]) -> Set[str]:
        shown: Set[str] = set()
        for path, text in self.files.items():
            if "/diagrams/" not in "/" + path:
                continue
            for k in kinds:
                if re.search(r"""(?:kind\s*===?\s*|case\s+)['"]%s['"]|\b%s\s*:\s*[\w(<\[]""" % (re.escape(k), re.escape(k)), text):
                    shown.add(k)
        return shown

    def offtrack_buttons(self) -> Set[str]:
        return self.pattern_hits(r"""\.includes\(\s*['"](\w+)['"]\s*\)""")


# --------------------------------------------------------------------------- loading
def git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True)
    if r.returncode != 0:
        raise CheckError("git %s failed: %s" % (" ".join(args), r.stderr.strip()))
    return r.stdout


def load_app(app_dir: str, ref: Optional[str]) -> App:
    files: Dict[str, str] = {}
    if ref:
        for path in git("ls-tree", "-r", "--name-only", ref, "--", app_dir).splitlines():
            if path.endswith((".ts", ".tsx")):
                files[path] = git("show", "%s:%s" % (ref, path))
        label = "%s (%s)" % (ref, git("rev-parse", "--short", ref).strip())
    else:
        base = Path(app_dir) if Path(app_dir).is_absolute() else ROOT / app_dir
        if not base.is_dir():
            raise CheckError("app directory not found: %s" % base)
        for p in base.rglob("*"):
            if p.suffix in (".ts", ".tsx") and p.is_file():
                files[p.relative_to(base).as_posix()] = p.read_text(encoding="utf-8", errors="replace")
        label = "working tree: %s" % app_dir
    if not files:
        raise CheckError("no .ts/.tsx files found under %s" % app_dir)
    return App(files, label)


def load_contract(path: str, ref: Optional[str]) -> Contract:
    if ref:
        return Contract(git("show", "%s:%s" % (ref, path)))
    p = Path(path) if Path(path).is_absolute() else ROOT / path
    if not p.is_file():
        raise CheckError("contract not found: %s" % p)
    return Contract(p.read_text(encoding="utf-8"))


def load_allow(path: str) -> Dict[str, str]:
    p = Path(path) if Path(path).is_absolute() else ROOT / path
    allowed: Dict[str, str] = {}
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            body, _, why = line.partition("#")
            if body.strip():
                allowed[body.strip()] = why.strip() or "no reason given"
    return allowed


# --------------------------------------------------------------------------- the check
Finding = Dict[str, str]  # category, name, status (ok|missing|allowed), detail


def run_check(contract: Contract, app: App, allow: Dict[str, str]) -> List[Finding]:
    out: List[Finding] = []

    def structure(label: str, getter):  # -> (set, file); absent structure = empty set + a finding
        try:
            return getter()
        except CheckError as e:
            out.append({"category": "structure", "name": label, "status": "missing", "detail": str(e)})
            return set(), "(not found)"

    known, known_file = structure("wire.ts KNOWN", app.known)
    handlers = app.handlers()
    kind_keys, _ = structure("cards KIND map", lambda: app.map_keys(["KIND", "CARD_KIND", "KINDS"], "/cards/"))
    action_keys, _ = structure("cards ACTION map", lambda: app.map_keys(["ACTION", "ACTIONS", "CARD_ACTION"], "/cards/"))
    card_calls = app.pattern_hits(r"""\bcardAct\(\s*['"](\w+)['"]""")
    sent = app.sent_action_kinds(action_keys)
    sent_cmds = app.sent_commands()
    shown = app.diagram_kinds_shown(contract.diagram_kinds)
    offtrack_btn = app.offtrack_buttons()

    def add(category: str, name: str, problems: List[str]) -> None:
        key = "%s:%s" % (category, name)
        if not problems:
            out.append({"category": category, "name": name, "status": "ok", "detail": ""})
        elif key in allow:
            out.append({"category": category, "name": name, "status": "allowed", "detail": allow[key]})
        else:
            out.append({"category": category, "name": name, "status": "missing", "detail": "; ".join(problems)})

    for e in contract.events:
        probs = []
        if e not in known:
            probs.append("not in %s KNOWN (the parser drops it)" % known_file.split("/")[-1])
        if e not in handlers:
            probs.append("no onMessage('%s') handler" % e)
        add("event", e, probs)
    for k in contract.card_kinds:
        add("card.kind", k, [] if k in kind_keys else ["no entry in the cards KIND map (falls back to the generic header)"])
    for a in contract.card_actions:
        add("card.action", a, [] if (a in action_keys or a in card_calls)
            else ["no ACTION-map entry and no cardAct('%s') call (the card shows no button)" % a])
    for a in contract.offtrack_actions:
        add("offtrack.action", a, [] if a in offtrack_btn else ["no button (nothing tests actions.includes('%s'))" % a])
    for a in contract.action_kinds:
        add("action.kind", a, [] if a in sent else ["nothing sends action {kind: '%s'}" % a])
    for c in contract.commands:
        ok = c in sent_cmds or (c == "end_lesson" and "end_lesson" in sent)  # same effect in the engine
        add("command", c, [] if ok else ["never sent (no cmd('%s', ...))" % c])
    for d in contract.diagram_kinds:
        add("diagram.kind", d, [] if d in shown else ["no view for it under features/diagrams"])
    return out


CATEGORIES = ["structure", "event", "card.kind", "card.action", "offtrack.action", "action.kind", "command", "diagram.kind"]


def report(findings: List[Finding], label: str, show_all: bool, allow: Dict[str, str]) -> str:
    lines = ["contract check: %s vs %s" % (DEFAULT_CONTRACT, label)]
    missing = [f for f in findings if f["status"] == "missing"]
    for cat in CATEGORIES:
        fs = [f for f in findings if f["category"] == cat]
        if cat == "structure":
            for f in fs:
                lines += ["", "STRUCTURE  %s: %s" % (f["name"], f["detail"])]
            continue
        ok = sum(1 for f in fs if f["status"] != "missing")
        lines.append("")
        lines.append("%-16s %d/%d handled" % (cat, ok, len(fs)))
        for f in fs:
            if f["status"] == "missing":
                lines.append("  MISSING  %-18s %s" % (f["name"], f["detail"]))
            elif show_all:
                note = "allowed: " + f["detail"] if f["status"] == "allowed" else "ok"
                lines.append("  ok       %-18s %s" % (f["name"], note if f["status"] == "allowed" else ""))
    used = {"%s:%s" % (f["category"], f["name"]) for f in findings if f["status"] == "allowed"}
    stale = sorted(set(allow) - used)
    if stale:
        lines += ["", "note: allow-list entries that no longer match a gap (remove them): " + ", ".join(stale)]
    lines += ["", "%d missing, %d allowed, %d handled" % (
        len(missing), sum(1 for f in findings if f["status"] == "allowed"), sum(1 for f in findings if f["status"] == "ok"))]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--contract", default=DEFAULT_CONTRACT)
    ap.add_argument("--contract-ref", help="read the contract from this git ref instead of the working tree")
    ap.add_argument("--app", default=DEFAULT_APP, help="app source dir (default app/src)")
    ap.add_argument("--ref", help="read the app source from this git ref (e.g. origin/adrian/shell)")
    ap.add_argument("--allow", default=DEFAULT_ALLOW)
    ap.add_argument("--all", action="store_true", help="also list what is handled")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        contract = load_contract(args.contract, args.contract_ref)
        app = load_app(args.app, args.ref)
        allow = load_allow(args.allow)
        findings = run_check(contract, app, allow)
    except CheckError as e:
        print("contract check could not run: %s" % e, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"app": app.label, "findings": findings}, indent=2))
    else:
        print(report(findings, app.label, args.all, allow))
    return 1 if any(f["status"] == "missing" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())

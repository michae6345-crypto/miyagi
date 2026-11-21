"""Ask Claude for the starter file set of a lesson, then make sure it is safe and gives nothing away.

Claude sees the step graph and returns JSON (SCAFFOLD_SCHEMA): small text files, an optional
scripted git history (for lessons that start from an existing repo, e.g. rebase), and setup
commands that go in the README (never run). Then, deterministically:

- paths must be relative, inside the folder, text, small (MAX_FILES / MAX_FILE_BYTES / MAX_TOTAL_BYTES);
- no file a check expects the learner to create (`file_exists`), except small data files;
- no content that already satisfies a check (`file_contains` on that file, or an editor
  `screen_contains`): that would pass a step before the learner did it, i.e. leak the solution.
  Leaks go back to Claude once as feedback; whatever still leaks is dropped.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from jsonschema import Draft202012Validator

log = logging.getLogger("server.workspace")

DEFAULT_MODEL = "claude-sonnet-5-5"
MAX_FILES = 12
MAX_FILE_BYTES = 20_000
MAX_TOTAL_BYTES = 100_000
DATA_EXT = {".csv", ".tsv", ".jsonl"}
# A step that creates one of these makes the whole folder around it: nothing may be pre-created there.
PROJECT_MARKERS = {"package.json", "Cargo.toml", "pyproject.toml", "go.mod", "manage.py", "Gemfile", "pom.xml", ".git"}
TEXT_EXT = {
    ".py", ".ipynb", ".txt", ".toml", ".cfg", ".ini", ".yaml", ".yml", ".md", ".sh", ".json", ".jsonl",
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".html", ".css", ".scss", ".vue", ".svelte",
    ".go", ".rs", ".java", ".kt", ".rb", ".php", ".c", ".h", ".cpp", ".hpp", ".swift", ".sql",
    ".csv", ".tsv", ".r", ".jl", ".lua", ".env.example", ".gitignore", ".xml", ".svg", ".mod", ".lock",
}
TEXT_NAMES = {"Makefile", "Dockerfile", "Cargo.toml", "Gemfile", ".gitignore", ".gitattributes", ".editorconfig", ".nvmrc", ".python-version"}
FORBIDDEN_PARTS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".miyagi-state"}
# Screen checks in these apps read terminal/browser output, not files: starter files can't satisfy them.
NON_EDITOR_APPS = {"terminal", "iterm", "iterm2", "warp", "ghostty", "kitty", "alacritty", "hyper",
                   "safari", "google chrome", "chrome", "firefox", "arc", "microsoft edge", "brave browser"}

_FILE = {
    "type": "object",
    "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
    "required": ["path", "content"],
    "additionalProperties": False,
}
SCAFFOLD_SCHEMA = {
    "type": "object",
    "properties": {
        "lesson_kind": {"type": "string", "enum": ["code", "no_code", "conceptual"],
                        "description": "code: the learner writes code/text files; no_code: the work happens in web apps or "
                                       "desktop apps (Botpress, Zapier, Figma, Blender, Excel); conceptual: watching/explaining only"},
        "stack": {"type": "string", "description": "e.g. python, node/react, git, rust, sql"},
        "summary": {"type": "string", "description": "one sentence: what the starter folder contains and why"},
        "setup": {"type": "array", "items": {"type": "string"},
                  "description": "shell commands the learner runs once before step 1 (shown in README.md, never run for them)"},
        "open_file": {"type": "string", "description": "relative path to open in the editor first, or \"\""},
        "files": {"type": "array", "items": _FILE},
        "git": {
            "type": "object",
            "properties": {
                "init": {"type": "boolean"},
                "default_branch": {"type": "string"},
                "ops": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "op": {"type": "string", "enum": ["commit", "branch", "checkout"]},
                            "name": {"type": "string", "description": "branch name for branch/checkout, \"\" for commit"},
                            "message": {"type": "string", "description": "commit message, \"\" otherwise"},
                            "files": {"type": "array", "items": _FILE, "description": "files written before a commit, [] otherwise"},
                        },
                        "required": ["op", "name", "message", "files"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["init", "default_branch", "ops"],
            "additionalProperties": False,
        },
    },
    "required": ["lesson_kind", "stack", "summary", "setup", "open_file", "files", "git"],
    "additionalProperties": False,
}

SYSTEM = """You prepare the empty project folder a learner starts a coding tutorial in. A tutor
app then walks them through the tutorial's steps and checks their work. Your job is ONLY the
starting point: what has to be on disk before step 1 so the learner can follow along. You never
write the lesson's solution."""

PROMPT = """Lesson (step graph built from the tutorial video, JSON):
{lesson_json}

Return the starter folder for this lesson as JSON.

Rules:
- Go only by the video's steps above. What the learner typed when searching is not part of the lesson.
- lesson_kind: "code" only if the steps have the learner write code or text files. If the work happens in
  web apps or other desktop apps (no-code builders, Zapier, Botpress, Figma, Blender, spreadsheets), it is
  "no_code"; if it only explains ideas, "conceptual". For no_code and conceptual: no files, no git, no setup.
- Derive the language and tooling from the steps, targets, checks and libraries (any topic: Python,
  pandas, React, git, Rust, SQL, ...). Never assume a topic the lesson doesn't show.
- Only what step 1 needs to begin, plus files later steps edit but never create. Use the exact
  relative paths the steps, targets and checks name (the folder IS the learner's working directory).
- If a step creates the project itself (npm create vite, cargo new, django-admin startproject,
  rails new, mkdir + git init, ...), do NOT pre-create it: return no files for it.
- Never write code that a step asks the learner to write. Starter code files get only what the
  tutorial's starting point plausibly has: a module docstring/comment saying what the file is for,
  or the boilerplate the tutorial starts from. No function bodies, imports, components or commands
  a step tells the learner to add. No step-numbered placeholder comments (`# Step 1: ...`): no step
  uses or removes them, so they end up below the learner's code.
- Dependency files (requirements.txt, package.json, Cargo.toml, ...) list what the tutorial
  installs. Pin an old major version (lesson.libraries) only if the tutorial's code breaks without
  it; otherwise use lower bounds that install on a current toolchain (Python 3.12, Node 20+).
  Put install commands in "setup"; nothing is run for the learner.
- Data: if the tutorial loads a named data file the learner can't create (e.g. data/sales.csv),
  add a small sample (<= 60 rows) with the columns and value types the tutorial uses. Do not add
  data files nobody loads.
- git: only when the lesson starts from an existing repository/history (e.g. a rebase, merge,
  bisect or revert lesson): set init=true and script the history with ops (commit / branch /
  checkout; commits write their files first). Leave init=false when a step runs git init itself.
- Small text files only: at most {max_files} files, each under {max_kb} KB. No binaries, no
  lockfiles, no node_modules, no .git internals, no README.md (the app writes it).
- It is fine, and often right, to return no files at all.
- open_file: the file the learner edits first ("" if none).
{forbidden}"""


@dataclass
class Scaffold:
    lesson_kind: str = "code"  # code | no_code | conceptual
    stack: str = ""
    summary: str = ""
    setup: list[str] = field(default_factory=list)
    open_file: str = ""
    files: dict[str, str] = field(default_factory=dict)  # rel path -> content
    git_init: bool = False
    git_default_branch: str = "main"
    git_ops: list[dict] = field(default_factory=list)
    model: str = ""
    dropped: list[str] = field(default_factory=list)  # "path: reason"
    error: str = ""  # set when Claude couldn't be used (no key, API error): folder gets README only


# --------------------------------------------------------------------------- checks -> guards

def _all_checks(graph: dict) -> list[dict]:
    out = []
    for s in graph.get("steps") or []:
        for c in (s.get("checks") or []) + (s.get("precision_checks") or []):
            out.append({**c, "_step": s.get("index", s.get("id"))})
    return out


def _norm(p: str) -> str:
    p = (p or "").replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return PurePosixPath(p).as_posix() if p else ""


def learner_creates(graph: dict) -> set[str]:
    """Files some step's `file_exists` check expects the learner to create."""
    return {_norm(c["file"]) for c in _all_checks(graph) if c.get("type") == "file_exists" and c.get("file")}


def learner_projects(graph: dict) -> set[str]:
    """Folders a step creates as a whole project (npm create vite my-app, git init project1, ...)."""
    out = set()
    for f in learner_creates(graph):
        pp = PurePosixPath(f)
        if pp.name in PROJECT_MARKERS and len(pp.parts) > 1:
            out.add(pp.parent.as_posix())
    return out


def _compile(pattern: str) -> re.Pattern | None:
    try:
        rx = re.compile(pattern, re.MULTILINE)
    except (re.error, TypeError):
        return None
    return None if rx.search("") else rx  # a pattern matching "" passes anyway: not a leak signal


def leaks(path: str, text: str, graph: dict) -> list[str]:
    """Checks this file content would already satisfy: '<checkId> (<pattern>)'."""
    path = _norm(path)
    hits = []
    for c in _all_checks(graph):
        t = c.get("type")
        in_file = t == "file_contains" and c.get("file") and _norm(c["file"]) == path
        in_editor = t == "screen_contains" and (c.get("app") or "").strip().lower() not in NON_EDITOR_APPS
        if not (in_file or in_editor):
            continue
        rx = _compile(c.get("pattern") or "")
        if rx is not None and rx.search(text):
            hits.append(f"{c.get('id')} ({c.get('pattern')})")
    return hits


def _safe_rel(path: str) -> str | None:
    p = _norm(path)
    if not p or path.startswith(("/", "~")) or re.match(r"^[A-Za-z]:", path):
        return None
    parts = PurePosixPath(p).parts
    if ".." in parts or any(x in FORBIDDEN_PARTS for x in parts):
        return None
    return p


def _is_text_name(p: str) -> bool:
    name = PurePosixPath(p).name
    return name in TEXT_NAMES or any(name.endswith(ext) for ext in TEXT_EXT)


# E26: "# Step 1: start building the weather CLI here" stayed on line 10, under the learner's step-2 code: no step uses
# or removes a step-numbered placeholder. One whole comment line ("# Step 2 - ...", "// step 3", "<!-- Step 1 -->").
# `--` starts a comment only in SQL, Lua and Haskell; elsewhere it is a CLI flag line (`  --step 1000 \`) and stays.
_MARKER_RE = (r"^[ \t]*(?:(?:{lead})[ \t]*|/\*[ \t]*(?=[^\n]*\*/)|<!--[ \t]*(?=[^\n]*-->))"
              r"(?:TODO:?[ \t]*)?\(?step[ \t]*\d+\b[^\n]*(?:\n|\Z)")
_STEP_MARKER = re.compile(_MARKER_RE.replace("{lead}", "#|//|;"), re.I | re.M)
_STEP_MARKER_DASH = re.compile(_MARKER_RE.replace("{lead}", "#|//|--|;"), re.I | re.M)
_DASH_COMMENT_EXT = {".sql", ".lua", ".hs"}


def strip_step_markers(text: str, path: str = "") -> str:
    """A starter code file without step-numbered placeholder comment lines (the docstring and the rest kept). Prose and
    data files (`# Step 1` is a Markdown heading there) are left as they are."""
    ext = PurePosixPath(path or "").suffix.lower()
    if ext in {".md", ".txt", ".csv", ".tsv", ".json", ".jsonl"}:
        return text or ""
    out = (_STEP_MARKER_DASH if ext in _DASH_COMMENT_EXT else _STEP_MARKER).sub("", text or "")
    if out == (text or ""):
        return out
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.rstrip("\n") + "\n" if out.strip() else ""


def vet(raw: dict, graph: dict) -> tuple[Scaffold, list[str]]:
    """Apply the safety and no-solution rules. Returns the cleaned scaffold and the leak
    messages (for one corrective round trip)."""
    kind = raw.get("lesson_kind") if raw.get("lesson_kind") in ("code", "no_code", "conceptual") else "code"
    sc = Scaffold(
        lesson_kind=kind,
        stack=str(raw.get("stack") or ""),
        summary=str(raw.get("summary") or ""),
        setup=[str(x) for x in raw.get("setup") or [] if str(x).strip()][:8],
    )
    if kind != "code":  # no-code / conceptual lessons never get files, git history or setup commands
        n = len(raw.get("files") or []) + len((raw.get("git") or {}).get("ops") or [])
        if n:
            sc.dropped.append(f"{n} file(s)/git op(s): a {kind.replace('_', '-')} lesson gets no starter files")
        sc.setup = []
        return sc, []
    creates = learner_creates(graph)
    projects = learner_projects(graph)
    leak_msgs: list[str] = []
    total = 0

    def admit(path: str, content: str, where: str) -> str | None:
        nonlocal total
        p = _safe_rel(path)
        if p is None:
            sc.dropped.append(f"{path}: unsafe path")
            return None
        if PurePosixPath(p).name.lower() == "readme.md" and "/" not in p:
            sc.dropped.append(f"{p}: README.md is written by the app")
            return None
        if not _is_text_name(p):
            sc.dropped.append(f"{p}: not a text file type")
            return None
        size = len(content.encode())
        if size > MAX_FILE_BYTES or total + size > MAX_TOTAL_BYTES:
            sc.dropped.append(f"{p}: too large ({size} bytes)")
            return None
        if p in creates and PurePosixPath(p).suffix not in DATA_EXT:
            sc.dropped.append(f"{p}: a step has the learner create it")
            return None
        if any(p == d or p.startswith(d + "/") for d in projects):
            sc.dropped.append(f"{p}: inside a project folder a step creates")
            return None
        if hits := leaks(p, content, graph):
            leak_msgs.append(f"{where}{p} already satisfies " + ", ".join(hits))
            sc.dropped.append(f"{p}: gives away " + ", ".join(hits))
            return None
        total += size
        return p

    for f in raw.get("files") or []:
        if len(sc.files) >= MAX_FILES:
            sc.dropped.append(f"{f.get('path')}: over {MAX_FILES} files")
            continue
        content = strip_step_markers(str(f.get("content") or ""), str(f.get("path") or ""))
        if (p := admit(str(f.get("path") or ""), content, "")) is not None:
            sc.files[p] = content

    git = raw.get("git") or {}
    if git.get("init"):
        if any(PurePosixPath(c).name == ".git" or c == ".git" for c in creates):
            sc.dropped.append("git history: a step runs git init itself")
        else:
            sc.git_init = True
            sc.git_default_branch = _branch(git.get("default_branch")) or "main"
            for op in (git.get("ops") or [])[:20]:
                kind = op.get("op")
                if kind in ("branch", "checkout"):
                    if (name := _branch(op.get("name"))):
                        sc.git_ops.append({"op": kind, "name": name})
                elif kind == "commit":
                    files = {}
                    for f in op.get("files") or []:
                        content = strip_step_markers(str(f.get("content") or ""), str(f.get("path") or ""))
                        if (p := admit(str(f.get("path") or ""), content, "commit: ")) is not None:
                            files[p] = content
                    sc.git_ops.append({"op": "commit", "message": (op.get("message") or "update")[:200], "files": files})

    of = _safe_rel(str(raw.get("open_file") or ""))
    committed = {p for op in sc.git_ops for p in op.get("files", {})}
    sc.open_file = of if of and (of in sc.files or of in committed) else next(iter(sc.files), "")
    return sc, leak_msgs


def _branch(name) -> str:
    name = str(name or "").strip()
    return name if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,60}", name) and ".." not in name else ""


# --------------------------------------------------------------------------- Claude

def model() -> str:
    """WORKSPACE_CLAUDE_MODEL, through the shared Opus guard (Opus only with MIYAGI_ALLOW_OPUS=1)."""
    m = os.environ.get("WORKSPACE_CLAUDE_MODEL", DEFAULT_MODEL)
    try:
        from server.config import guard_model
    except Exception:  # pragma: no cover
        return m
    return guard_model(m)


def make_client():
    """A sync Anthropic client with the app's key, the miyagi cloud's install token (through the proxy) or the env,
    else None (server.config.anthropic_kwargs)."""
    try:
        from server.config import anthropic_kwargs
        kw = anthropic_kwargs("workspace")
    except Exception:  # pragma: no cover - server.config always importable in the engine
        key = os.environ.get("ANTHROPIC_API_KEY")
        kw = {"api_key": key} if key else {}
    if not kw.get("api_key"):
        return None
    import anthropic

    return anthropic.Anthropic(timeout=90.0, max_retries=1, **kw)


def _lesson_for_prompt(graph: dict) -> str:
    keep_step = ("index", "title", "instructions", "targets", "checks", "precision_checks", "common_mistakes")
    slim = {
        "lesson": {k: v for k, v in (graph.get("lesson") or {}).items() if k in ("title", "libraries")},
        "sources": [{k: s.get(k) for k in ("kind", "title", "url")} for s in graph.get("sources") or []],
        "steps": [{k: s[k] for k in keep_step if k in s} for s in graph.get("steps") or []],
    }
    return json.dumps(slim, indent=1)[:60_000]


def _forbidden_text(graph: dict) -> str:
    creates = sorted(learner_creates(graph))
    out = []
    if creates:
        out.append("- The learner creates these during the lesson, so do not create them (sample data files the "
                   "tutorial downloads are the only exception): " + ", ".join(creates))
    if projects := sorted(learner_projects(graph)):
        out.append("- A step creates these project folders itself; put nothing inside them: " + ", ".join(projects))
    return "\n".join(out)


def _reply_text(msg) -> str:
    for b in getattr(msg, "content", None) or []:
        if getattr(b, "type", "") == "text":
            return b.text
    return ""


def _extract_json(text: str) -> dict:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    start = t.find("{")
    if start < 0:
        raise ValueError("no JSON object in the reply")
    obj, _ = json.JSONDecoder().raw_decode(t, start)
    return obj


def _ask(client, messages: list[dict]) -> dict:
    """One Claude call with structured output; falls back to schema-in-prompt if the API rejects it."""
    kw = dict(model=model(), max_tokens=16000, system=SYSTEM, messages=messages)
    try:
        msg = client.messages.create(**kw, output_config={"format": {"type": "json_schema", "schema": SCAFFOLD_SCHEMA}})
    except Exception as e:  # BadRequest on schema support -> prompt-described JSON
        if "schema" not in str(e).lower() and "output_config" not in str(e).lower():
            raise
        log.info("structured output unavailable (%s); asking for JSON in the prompt", str(e)[:120])
        msgs = [*messages[:-1], {"role": "user", "content": messages[-1]["content"]
                + "\n\nReply with ONE JSON object (no prose) matching this JSON Schema:\n" + json.dumps(SCAFFOLD_SCHEMA)}]
        msg = client.messages.create(**{**kw, "messages": msgs})
    if getattr(msg, "stop_reason", None) == "max_tokens":
        raise RuntimeError("Claude's starter-file reply was cut off (max_tokens)")
    if getattr(msg, "stop_reason", None) == "refusal":
        raise RuntimeError("Claude declined to produce starter files")
    obj = _extract_json(_reply_text(msg))
    errors = [e.message for e in Draft202012Validator(SCAFFOLD_SCHEMA).iter_errors(obj)]
    if errors:
        raise ValueError("starter-file JSON invalid: " + "; ".join(errors[:5]))
    return obj


def generate(graph: dict, goal: str, client=None) -> Scaffold:
    """Claude -> vetted Scaffold. Never raises: on any failure, Scaffold(error=...) with no files."""
    client = client if client is not None else make_client()
    if client is None:
        return Scaffold(error="no Anthropic key (config.keys.anthropic / ANTHROPIC_API_KEY): README only")
    prompt = PROMPT.format(  # the learner's goal text is deliberately left out: the video decides
        lesson_json=_lesson_for_prompt(graph),
        max_files=MAX_FILES,
        max_kb=MAX_FILE_BYTES // 1000,
        forbidden=_forbidden_text(graph),
    )
    messages = [{"role": "user", "content": prompt}]
    try:
        raw = _ask(client, messages)
        sc, leak_msgs = vet(raw, graph)
        if leak_msgs:
            log.info("starter files leak %d check(s); asking Claude once more", len(leak_msgs))
            messages += [
                {"role": "assistant", "content": json.dumps(raw)},
                {"role": "user", "content": "These starter files already contain what a step asks the learner to write, "
                 "so the step would pass before the learner did it. Remove that content (keep placeholders) and "
                 "return the full JSON again:\n- " + "\n- ".join(leak_msgs[:20])},
            ]
            raw = _ask(client, messages)
            sc, _ = vet(raw, graph)  # whatever still leaks is dropped by vet
    except Exception as e:
        log.warning("starter files: Claude failed: %s", str(e)[:300])
        return Scaffold(error=f"Claude failed: {str(e)[:200]}")
    sc.model = model()
    return sc

"""Contract validation for step graphs, plus the JSON schemas we hand to Gemini.

The contract schemas live in shared/contracts/ and are the boundary with the
orchestrator and the checks module; never edit them from here.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = REPO_ROOT / "shared" / "contracts"

# Screen-first (contract change, Sat 1 PM): a step's `checks` are graded from what is on
# the learner's screen (Apple Vision OCR), so they use screen_* and metric_* (+ metric_pattern).
# file_*/command_* need a known workdir or `tut run`; they go in the optional per-step
# `precision_checks` list (extra field, allowed by the contract) so they never block a step
# in screen mode. `visual` is not machine-checkable, so the builder never emits it.
SCREEN_TYPES = ["screen_contains", "screen_absent", "metric_threshold", "metric_trend"]
PRECISION_TYPES = ["file_exists", "file_contains", "command_exit_ok", "output_contains", "metric_threshold", "metric_trend"]
CHECK_TYPES = sorted(set(SCREEN_TYPES) | set(PRECISION_TYPES))
SCREEN_APPS = ["Code", "Terminal", "iTerm2", "Google Chrome", "Safari", "Jupyter", "PyCharm", "Cursor"]
MAX_SCREEN_PATTERN = 80  # long regexes break on OCR noise


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    graph = json.loads((CONTRACTS / "step-graph.schema.json").read_text())
    check = json.loads((CONTRACTS / "check.schema.json").read_text())
    registry = Registry().with_resource("check.schema.json", Resource.from_contents(check))
    return Draft202012Validator(graph, registry=registry)


def schema_errors(graph: dict) -> list[str]:
    """Contract violations, as short human-readable strings (empty = valid)."""
    out = []
    for err in sorted(_validator().iter_errors(graph), key=lambda e: list(e.absolute_path)):
        path = "/".join(str(p) for p in err.absolute_path) or "<root>"
        out.append(f"{path}: {err.message}")
    return out


def lint(graph: dict, known_metrics: set[str] | None = None, known_files: set[str] | None = None) -> list[str]:
    """Semantic problems the JSON schema can't catch: a check must be *runnable*.

    known_files / known_metrics come from scanning the learner's workdir; when they
    are empty (fresh or unknown workdir) the corresponding checks are not enforced.
    """
    problems: list[str] = []
    seen_ids: set[str] = set()
    for step in graph.get("steps", []):
        sid = step.get("id", "?")
        if len(step.get("title", "").split()) > 6:
            problems.append(f"{sid}: title longer than 6 words")
        checks = step.get("checks", [])
        if not checks:
            problems.append(f"{sid}: no screen checks (every step needs at least one screen_* or metric_* check)")
        v = step.get("video")
        if v and not (0 <= v.get("start", 0) < v.get("end", 0)):
            problems.append(f"{sid}: video.start must be < video.end")
        for key, allowed in (("checks", SCREEN_TYPES), ("precision_checks", PRECISION_TYPES)):
            for c in step.get(key, []):
                cid = c.get("id", "?")
                if cid in seen_ids:
                    problems.append(f"{sid}/{cid}: duplicate check id")
                seen_ids.add(cid)
                problems += [f"{sid}/{cid}: {p}" for p in check_problems(c, allowed, key, known_metrics, known_files)]
    return problems


def check_problems(c: dict, allowed: list[str], where: str, known_metrics=None, known_files=None) -> list[str]:
    out: list[str] = []
    t = c.get("type")
    if t not in allowed:
        return [f"type {t!r} not allowed in `{where}` (use one of {allowed})"]
    need = {
        "screen_contains": ("pattern",), "screen_absent": ("pattern",),
        "file_exists": ("file",), "file_contains": ("file", "pattern"), "command_exit_ok": ("command",),
        "output_contains": ("pattern",), "metric_threshold": ("metric", "op", "value"), "metric_trend": ("metric", "trend"),
    }[t]
    out += [f"{t} needs `{k}`" for k in need if c.get(k) in (None, "")]
    if c.get("pattern"):
        if err := _regex_error(c["pattern"]):
            out.append(f"pattern does not compile ({err})")
        elif t.startswith("screen_") and len(c["pattern"]) > MAX_SCREEN_PATTERN:
            out.append(f"screen pattern longer than {MAX_SCREEN_PATTERN} chars; OCR text is noisy, match a short distinctive fragment")
    if t in ("metric_threshold", "metric_trend"):
        mp = c.get("metric_pattern")
        if where == "checks" and not mp:
            out.append("screen metric check needs `metric_pattern` (regex with (?P<step>...) and (?P<value>...)) to read it off the terminal")
        if mp:
            if err := _regex_error(mp):
                out.append(f"metric_pattern does not compile ({err})")
            elif not {"step", "value"} <= set(re.compile(mp).groupindex):
                out.append("metric_pattern must have named groups `step` and `value`")
        if where == "precision_checks" and known_metrics and c.get("metric") and not _metric_known(c["metric"], known_metrics):
            out.append(f"metric {c['metric']!r} is never printed by the workdir code (known: {sorted(known_metrics)})")
    if t in ("file_exists", "file_contains") and known_files and c.get("file"):
        if c["file"] not in known_files and not _creatable(c["file"]):
            out.append(f"file {c['file']!r} is not in the workdir (files: {sorted(known_files)[:20]})")
    return out


def _regex_error(p: str) -> str | None:
    try:
        re.compile(p)
    except re.error as e:
        return str(e)
    return None


def _metric_known(name: str, known: set[str]) -> bool:
    if name in known:
        return True
    # f-string metric names are recorded as prefixes, e.g. "grad_norm/*"
    return any(k.endswith("*") and name.startswith(k[:-1]) for k in known)


def _creatable(path: str) -> bool:
    # Steps may legitimately ask the learner to create new files; allow simple
    # source-file names, flag anything that looks like a typo'd existing path.
    return "/" not in path and path.endswith((".py", ".ipynb", ".txt", ".png"))


# --------------------------------------------------------------------------- #
# Schemas for Gemini structured output. Gemini supports a subset of JSON Schema
# (no $ref across files, no additionalProperties maps), so these are inlined
# and flatter than the contract; builder.py converts them to the contract shape.
# --------------------------------------------------------------------------- #

_CHECK_DRAFT = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": CHECK_TYPES},
        "label": {"type": "string", "description": "<= 6 words, shown in a checklist"},
        "app": {"type": "string", "description": "screen_*: app whose window must show the text, e.g. Code, Terminal"},
        "metric_pattern": {"type": "string", "description": "regex with named groups step and value that reads the metric off a terminal line"},
        "file": {"type": "string"},
        "pattern": {"type": "string", "description": "Python regex"},
        "command": {"type": "string"},
        "metric": {"type": "string"},
        "op": {"type": "string", "enum": ["<", "<=", ">", ">="]},
        "value": {"type": "number"},
        "by_step": {"type": "integer"},
        "trend": {"type": "string", "enum": ["decreasing", "not_flat"]},
        "window": {"type": "integer"},
    },
    "required": ["type", "label"],
}

VIDEO_DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "lesson title"},
        "summary": {"type": "string"},
        "libraries": {
            "type": "array",
            "description": "libraries the tutorial uses, with the version if shown or inferable (pip output, imports, API style)",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "version": {"type": "string"}},
                "required": ["name", "version"],
            },
        },
        "files": {"type": "array", "items": {"type": "string"}, "description": "file names the tutorial creates/edits"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "description": "MM:SS where the step's explanation/coding starts"},
                    "end": {"type": "string", "description": "MM:SS where the step is complete (code written / run finished)"},
                    "title": {"type": "string", "description": "imperative, <= 6 words"},
                    "instructions": {"type": "string", "description": "<= 2 sentences telling the learner what to do"},
                    "file": {"type": "string", "description": "file edited in this step, if any"},
                    "code": {"type": "string", "description": "the key code written in this step, as seen on screen"},
                    "run_command": {"type": "string", "description": "command run at the end of the step, if any"},
                    "expected_output": {"type": "string", "description": "terminal lines printed by the run, verbatim as on screen (format matters: checks parse it)"},
                    "checks": {"type": "array", "items": _CHECK_DRAFT},
                    "targets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"app": {"type": "string"}, "file": {"type": "string"}, "match": {"type": "string"}, "caption": {"type": "string"}},
                            "required": ["match", "caption"],
                        },
                    },
                    "explanations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"topic": {"type": "string"}, "t": {"type": "string", "description": "MM:SS"}},
                            "required": ["topic", "t"],
                        },
                    },
                    "hints": {"type": "array", "items": {"type": "string"}},
                    "common_mistakes": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["start", "end", "title", "instructions", "checks", "hints"],
            },
        },
    },
    "required": ["title", "libraries", "steps"],
}

DETAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "file": {"type": "string", "description": "file name visible in the editor tab, if any"},
        "code": {"type": "string", "description": "the code on screen at the end of this clip, transcribed exactly"},
        "run_command": {"type": "string"},
        "terminal_output": {"type": "string", "description": "training/progress lines visible in the terminal or notebook output, verbatim"},
        "printed_metrics": {"type": "array", "items": {"type": "string"}, "description": "names of values printed during training (loss, etc.)"},
        "library_versions": {
            "type": "array",
            "items": {"type": "object", "properties": {"name": {"type": "string"}, "version": {"type": "string"}}, "required": ["name", "version"]},
        },
    },
    "required": ["code"],
}

ADAPTED_SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "instructions": {"type": "string"},
                    "checks": {"type": "array", "items": _CHECK_DRAFT, "description": "screen-first: screen_contains / screen_absent / metric_* with metric_pattern"},
                    "precision_checks": {"type": "array", "items": _CHECK_DRAFT, "description": "backup when the workdir is known: file_* / command_exit_ok / metric_* by ::metric:: name"},
                    "targets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"app": {"type": "string"}, "file": {"type": "string"}, "match": {"type": "string"}, "caption": {"type": "string"}},
                            "required": ["match", "caption"],
                        },
                    },
                },
                "required": ["index", "checks", "targets"],
            },
        }
    },
    "required": ["steps"],
}

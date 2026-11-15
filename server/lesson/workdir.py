"""Scan the learner's project folder so checks can name real files and metrics."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

SKIP_DIRS = {".git", ".venv", "dist", "build", ".next", "target", "coverage", "venv", "env", "node_modules", "__pycache__", ".ipynb_checkpoints", "data", "runs", "wandb", ".mypy_cache", ".pytest_cache"}
TEXT_EXT = {
    ".py", ".ipynb", ".txt", ".toml", ".cfg", ".yaml", ".yml", ".md", ".sh", ".json",
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".html", ".css", ".vue", ".svelte",
    ".go", ".rs", ".java", ".kt", ".rb", ".php", ".c", ".h", ".cpp", ".swift", ".sql",
}
SKIP_FILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "uv.lock", "Cargo.lock"}
MAX_FILES = 40
MAX_CHARS_PER_FILE = 12_000
MAX_CHARS_TOTAL = 60_000

# log_metric(step, "loss", value)  /  log_metric(step, f"grad_norm/{i}", g)
_LOG_METRIC = re.compile(r"""log_metric\(\s*[^,]+,\s*(f?)(["'])(.+?)\2""")
# print(f'::metric:: {{"step": {s}, "name": "loss", ...}}')  (also with escaped quotes)
_RAW_METRIC = re.compile(r"""::metric::.*?\\?["']name\\?["']\s*:\s*\\?["']([^"'\\]+)""")
_ARGPARSE = re.compile(r"""add_argument\(\s*["'](--[\w-]+)""")
_DEF = re.compile(r"^\s*(?:def|class)\s+(\w+)", re.M)


@dataclass
class WorkdirInfo:
    root: str
    exists: bool
    files: list[str] = field(default_factory=list)  # relative paths
    metrics: set[str] = field(default_factory=set)  # names; f-string names as "prefix*"
    cli_flags: dict[str, list[str]] = field(default_factory=dict)  # file -> ["--epochs", ...]
    symbols: dict[str, list[str]] = field(default_factory=dict)  # file -> def/class names
    contents: dict[str, str] = field(default_factory=dict)  # truncated text for the prompt

    def summary_for_prompt(self) -> str:
        if not self.exists or not self.files:
            return (f"The learner's workdir ({self.root}) is empty or does not exist yet: they start from scratch, so "
                    "step 1 must create anything the tutorial assumes (files, data, repo state) and later checks must not "
                    "depend on files or names the learner was never told to create.")
        parts = [f"Workdir: {self.root}", "Files: " + ", ".join(self.files)]
        if self.metrics:
            parts.append("Metric names printed via ::metric:: lines: " + ", ".join(sorted(self.metrics)))
        else:
            parts.append("No ::metric:: lines found yet; metric checks must use names the instructions tell the learner to log.")
        for f, flags in self.cli_flags.items():
            parts.append(f"CLI flags in {f}: {' '.join(flags)}")
        for f, text in self.contents.items():
            parts.append(f"\n----- {f} -----\n{text}")
        return "\n".join(parts)


def scan(workdir: str) -> WorkdirInfo:
    root = Path(workdir).expanduser()
    info = WorkdirInfo(root=str(root), exists=root.is_dir())
    if not info.exists:
        return info
    budget = MAX_CHARS_TOTAL
    for p in sorted(_walk(root)):
        rel = p.relative_to(root).as_posix()
        info.files.append(rel)
        if len(info.files) >= MAX_FILES:
            break
        if p.suffix not in TEXT_EXT:
            continue
        text = _read(p)
        if text is None:
            continue
        if p.suffix in (".py", ".ipynb"):
            info.metrics |= _metrics(text)
            if flags := _ARGPARSE.findall(text):
                info.cli_flags[rel] = flags
            if syms := _DEF.findall(text):
                info.symbols[rel] = syms
        if budget > 0:
            chunk = text[: min(MAX_CHARS_PER_FILE, budget)]
            info.contents[rel] = chunk
            budget -= len(chunk)
    return info


def _walk(root: Path):
    for p in root.iterdir():
        if p.name.startswith(".") and p.name not in (".env.example",):
            continue
        if p.is_dir():
            if p.name not in SKIP_DIRS:
                yield from _walk(p)
        elif p.is_file() and p.name not in SKIP_FILES:
            yield p


def _read(p: Path) -> str | None:
    try:
        raw = p.read_text(errors="replace")
    except OSError:
        return None
    if p.suffix == ".ipynb":
        try:
            nb = json.loads(raw)
            return "\n\n".join("".join(c.get("source", [])) for c in nb.get("cells", []) if c.get("cell_type") == "code")
        except (json.JSONDecodeError, AttributeError):
            return None
    return raw


def _metrics(text: str) -> set[str]:
    out: set[str] = set()
    for is_f, _q, name in _LOG_METRIC.findall(text):
        if is_f and "{" in name:
            out.add(name.split("{", 1)[0] + "*")
        else:
            out.add(name)
    out |= set(_RAW_METRIC.findall(text))
    out.discard("{name}")
    return {m for m in out if m and "{" not in m}

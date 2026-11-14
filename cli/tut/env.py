"""Tiny .env loader (no python-dotenv dependency). Real env vars always win."""
from __future__ import annotations

import os
from pathlib import Path


def find_upwards(name: str, starts: list[Path]) -> Path | None:
    for start in starts:
        for d in [start, *start.parents]:
            p = d / name
            if p.exists():
                return p
    return None


def repo_root() -> Path | None:
    """The sandhacks-tutor checkout (holds shared/contracts), from cwd or this package."""
    p = find_upwards("shared/contracts/tiger-schema.sql", [Path.cwd().resolve(), Path(__file__).resolve().parent])
    return p.parents[2] if p else None


def load_dotenv() -> Path | None:
    starts = [Path.cwd().resolve()]
    root = repo_root()
    if root:
        starts.append(root)
        # worktrees live in <main>/.claude/worktrees/<name>; fall back to the main checkout's .env
        if root.parent.name == "worktrees" and root.parent.parent.name == ".claude":
            starts.append(root.parent.parent.parent)
    path = find_upwards(".env", starts)
    if not path:
        return None
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            v = v[1:-1]
        os.environ.setdefault(k, v)
    return path

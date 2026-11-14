"""Resolve a step's semantic `targets` ({file, match, caption}) to concrete line ranges."""

from __future__ import annotations

import re
from pathlib import Path

MAX_BLOCK = 25


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def find_block(text: str, match: str) -> tuple[int, int] | None:
    """1-based (start, end) of the first line matching `match` (regex, else substring)
    and the indented block under it."""
    lines = text.splitlines()
    try:
        rx = re.compile(match)
        hit = lambda s: rx.search(s) is not None
    except re.error:
        hit = lambda s: match in s
    for i, line in enumerate(lines):
        if not hit(line):
            continue
        base = _indent(line)
        end = i
        for j in range(i + 1, min(len(lines), i + MAX_BLOCK)):
            if not lines[j].strip():
                continue
            if _indent(lines[j]) <= base:
                break
            end = j
        return i + 1, end + 1
    return None


def resolve(workdir: str | Path, target: dict) -> dict | None:
    """-> spotlight payload {file, startLine, endLine, caption} or None."""
    file = target.get("file")
    if not file:
        return None
    path = Path(workdir) / file
    caption = target.get("caption", "")
    if not path.exists():
        return None
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return None
    match = target.get("match")
    span = find_block(text, match) if match else None
    if span is None:
        n = max(1, len(text.splitlines()))
        span = (1, min(n, 1))
    return {"file": str(path), "startLine": span[0], "endLine": span[1], "caption": caption}


def resolve_line(workdir: str | Path, file: str, line: int, caption: str) -> dict:
    path = Path(file)
    if not path.is_absolute():
        path = Path(workdir) / file
    return {"file": str(path), "startLine": int(line), "endLine": int(line), "caption": caption}

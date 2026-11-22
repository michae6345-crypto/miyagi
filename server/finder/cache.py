"""Per-query cache of REAL results in demo/cache/search/ (so the demo never waits on the network)."""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

from .env import CACHE_DIR


def normalize(query: str) -> str:
    return " ".join(query.lower().split())


def path_for(query: str, root: Path | None = None) -> Path:
    q = normalize(query)
    slug = re.sub(r"[^a-z0-9]+", "-", q).strip("-")[:48] or "query"
    h = hashlib.sha1(q.encode()).hexdigest()[:8]
    return (root or CACHE_DIR) / f"{slug}-{h}.json"


def load(query: str, *, max_age_s: float | None = None, root: Path | None = None) -> dict | None:
    p = path_for(query, root)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if normalize(data.get("query", "")) != normalize(query) or not data.get("results"):
        return None
    if max_age_s is not None and time.time() - data.get("created", 0) > max_age_s:
        return None
    return data


def save(query: str, results: list[dict], info: dict, *, root: Path | None = None) -> Path:
    p = path_for(query, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"query": query, "created": int(time.time()), **info, "results": results}
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)
    return p

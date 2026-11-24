"""The plans catalog: Adrian's 40 lesson plans (docs/ui-next/catalog on adrian/ui-next), shipped with the engine.

data/catalog.json is `node catalog/build.mjs`'s output, copied as is (format: catalog/SCHEMA.md there). data/playlists.json
is the 50 YouTube playlists picked for 25 of those plans (two each), fetched and checked by hand on Nov 22 2026.
Both are read once and kept (the files never change while the engine runs). Nothing here touches the network.

MIYAGI_PLANS_CATALOG / MIYAGI_PLANS_PLAYLISTS point at other files (tests, a newer catalog dropped in by hand).
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any

log = logging.getLogger("plans.catalog")

DATA_DIR = Path(__file__).parent / "data"
PLAN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
GROUPS = ("language", "environment", "topic")
TOPICS = ("code", "data", "ai", "3d", "cad", "design", "tools")
CHECKS = ("run", "code", "scene", "file", "screen")

_lock = threading.Lock()
_cache: dict[str, Any] = {}


def _path(env: str, name: str) -> Path:
    return Path(os.environ.get(env) or DATA_DIR / name)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        log.warning("no plans file at %s", path)
    except (OSError, ValueError) as e:
        log.warning("ignoring unreadable plans file %s: %s", path, e)
    return None


def _str(v: Any, limit: int = 400) -> str:
    return " ".join(v.split())[:limit] if isinstance(v, str) else ""


def _strs(v: Any, limit: int = 120) -> list[str]:
    return [s for s in (_str(x, limit) for x in v) if s] if isinstance(v, list) else []


def _clean_lesson(raw: Any) -> dict | None:
    if not isinstance(raw, dict) or not _str(raw.get("title")) or not _str(raw.get("goal")):
        return None
    out = {"title": _str(raw["title"], 120), "goal": _str(raw["goal"], 400), "grows": _strs(raw.get("grows"), 60)}
    for k in ("minutes", "steps"):
        v = raw.get(k)
        out[k] = v if isinstance(v, int) and not isinstance(v, bool) and 0 < v <= 600 else None
    out["check"] = raw.get("check") if raw.get("check") in CHECKS else "screen"
    out["passes"] = _str(raw.get("passes"), 200)
    return out


def _clean_plan(raw: Any) -> dict | None:
    """One plan, kept to the fields SCHEMA.md names. A plan with no id, title or lessons is dropped (logged)."""
    if not isinstance(raw, dict):
        return None
    pid = raw.get("id")
    if not isinstance(pid, str) or not PLAN_ID_RE.fullmatch(pid) or not _str(raw.get("title")):
        log.warning("catalog: dropping a plan with no usable id or title (%r)", pid)
        return None
    lessons = [le for le in (_clean_lesson(x) for x in raw.get("lessons") or []) if le]
    if not lessons:
        log.warning("catalog: dropping %s (no lessons)", pid)
        return None
    tool = raw.get("tool") if isinstance(raw.get("tool"), dict) else {}
    proj = raw.get("project") if isinstance(raw.get("project"), dict) else {}
    skills = []
    for s in raw.get("skills") or []:
        if isinstance(s, dict) and _str(s.get("id")) and _str(s.get("label")):
            skills.append({"id": _str(s["id"], 60), "label": _str(s["label"], 40), "needs": _strs(s.get("needs"), 60)})
    return {
        "id": pid,
        "title": _str(raw["title"], 80),
        "group": raw.get("group") if raw.get("group") in GROUPS else "topic",
        "topic": raw.get("topic") if raw.get("topic") in TOPICS else "tools",
        "track": _str(raw.get("track"), 40).lower(),
        "tool": {"id": _str(tool.get("id"), 40), "label": _str(tool.get("label"), 40)},
        "also": _strs(raw.get("also"), 60),
        "level": "next" if raw.get("level") == "next" else "start",
        "needs": [n for n in _strs(raw.get("needs"), 64) if PLAN_ID_RE.fullmatch(n)],
        "line": _str(raw.get("line"), 140),
        "project": {"title": _str(proj.get("title"), 120), "brief": _str(proj.get("brief"), 300),
                    "checks": _strs(proj.get("checks"), 200)},
        "skills": skills,
        "lessons": lessons,
    }


def _clean_playlist(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    plid = raw.get("playlistId")
    if not isinstance(plid, str) or not PLAYLIST_ID_RE.fullmatch(plid):
        return None
    videos = []
    for v in raw.get("videos") or []:
        if isinstance(v, dict) and isinstance(v.get("id"), str) and VIDEO_ID_RE.fullmatch(v["id"]):
            secs = v.get("seconds")
            videos.append({"id": v["id"], "title": _str(v.get("title"), 200) or "Video",
                           "seconds": secs if isinstance(secs, int) and not isinstance(secs, bool) and secs >= 0 else None})
    if not videos:
        return None
    return {"planId": _str(raw.get("planId"), 64) or None, "playlistId": plid, "title": _str(raw.get("title"), 200),
            "channel": _str(raw.get("channel"), 120), "url": f"https://www.youtube.com/playlist?list={plid}",
            "videos": videos}


PLAYLIST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,64}$")
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def _load() -> dict:
    with _lock:
        if "plans" not in _cache:
            data = _read_json(_path("MIYAGI_PLANS_CATALOG", "catalog.json"))
            raw = data.get("plans") if isinstance(data, dict) else data
            plans: dict[str, dict] = {}
            for p in (_clean_plan(x) for x in raw or []):
                if p and p["id"] not in plans:
                    plans[p["id"]] = p
            _cache["plans"] = plans
            _cache["version"] = data.get("version") if isinstance(data, dict) else None
            pls = _read_json(_path("MIYAGI_PLANS_PLAYLISTS", "playlists.json"))
            _cache["playlists"] = [p for p in (_clean_playlist(x) for x in pls or []) if p] if isinstance(pls, list) else []
            log.info("plans catalog: %d plans, %d playlists", len(plans), len(_cache["playlists"]))
        return _cache


def reload() -> None:
    """Forget the cached files (tests; a catalog swapped on disk)."""
    with _lock:
        _cache.clear()


def plans() -> list[dict]:
    """Every plan, in the catalog's order."""
    return list(_load()["plans"].values())


def get(plan_id: str) -> dict | None:
    return _load()["plans"].get(plan_id) if isinstance(plan_id, str) else None


def playlists(plan_id: str | None = None) -> list[dict]:
    pls = _load()["playlists"]
    return [p for p in pls if p["planId"] == plan_id] if plan_id else list(pls)


def shipped_playlist(playlist_id: str) -> dict | None:
    """A playlist from playlists.json (no fetch needed)."""
    return next((p for p in _load()["playlists"] if p["playlistId"] == playlist_id), None)


def total_minutes(plan: dict) -> int:
    return sum(le.get("minutes") or 0 for le in plan.get("lessons") or [])


def summary(plan: dict) -> dict:
    """A plan as a row on the Plans page: everything but the lessons and skills themselves."""
    return {
        "id": plan["id"], "title": plan["title"], "group": plan["group"], "topic": plan["topic"],
        "track": plan["track"], "tool": dict(plan["tool"]), "also": list(plan["also"]), "level": plan["level"],
        "needs": list(plan["needs"]), "line": plan["line"], "project": {"title": plan["project"]["title"]},
        "lessonCount": len(plan["lessons"]), "skillCount": len(plan["skills"]), "minutes": total_minutes(plan),
        "playlists": len(playlists(plan["id"])),
    }


def detail(plan: dict) -> dict:
    """A plan with its lessons (each with its index) and skills: the plan page."""
    out = summary(plan)
    out["project"] = {k: (list(v) if isinstance(v, list) else v) for k, v in plan["project"].items()}
    out["skills"] = [dict(s, needs=list(s["needs"])) for s in plan["skills"]]
    out["lessons"] = [dict(le, index=i, grows=list(le["grows"])) for i, le in enumerate(plan["lessons"])]
    return out

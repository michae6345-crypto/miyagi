"""Tracks and skills from the plans catalog (catalog.json, a compact copy of Adrian's docs/ui-next/catalog/catalog.json).

A plan belongs to one track ("python", "blender", "cad", ...) and lists 6-10 skills ({id, label, needs}) and its lessons
in order (each lesson `grows` 1 or 2 skill ids). A track is every plan with that track name, in catalog order: its skills
are the union of the plans' skills (ids are unique across the catalog). Skill `needs` may point into another plan of the
same track or a plan the plan `needs` (e.g. TypeScript builds on JavaScript).

    catalog.tracks()            -> [Track]               (catalog order)
    catalog.skill(skill_id)     -> Skill | None
    catalog.match_lesson(meta)  -> (plan, lesson) | None (a lesson whose goal / title is this one's)

Loaded once and cached; MIYAGI_SKILL_CATALOG points at another file (tests). Never raises: a missing or broken file
reads as an empty catalog (the keyword fallback in tagging.py still works on nothing, so nothing is tagged).
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

log = logging.getLogger("skilltree")

CATALOG_PATH = Path(__file__).parent / "catalog.json"


@dataclass(frozen=True)
class Skill:
    id: str
    label: str
    track: str
    plan_id: str
    needs: tuple[str, ...]
    order: int  # position in the track (catalog order)
    lessons: tuple[str, ...] = ()  # titles of the catalog lessons that grow it, in order


@dataclass
class Plan:
    id: str
    title: str
    track: str
    topic: str
    tool: dict
    level: str
    needs: list[str]
    project: dict
    skills: list[Skill]
    lessons: list[dict]


@dataclass
class Track:
    id: str  # the track name, lowercase ("blender", "cad", "c#")
    label: str  # display name ("Blender", "CAD", "C#")
    topic: str
    plans: list[Plan] = field(default_factory=list)

    @property
    def skills(self) -> list[Skill]:
        return [s for p in self.plans for s in p.skills]


LABELS = {"cad": "CAD", "c#": "C#", "c++": "C++", "sql": "SQL", "vs code": "VS Code", "numpy": "NumPy", "pytorch": "PyTorch",
          "javascript": "JavaScript", "typescript": "TypeScript", "web": "HTML and CSS", "r": "R", "go": "Go", "c": "C",
          "scikit-learn": "scikit-learn", "git": "Git", "jupyter": "Jupyter", "figma": "Figma", "fusion": "Fusion",
          "onshape": "Onshape", "excel": "Excel", "sheets": "Google Sheets"}


def norm(text: Any) -> str:
    """Lowercase words only: the key two goals / titles are compared by."""
    return " ".join(re.findall(r"[a-z0-9#+]+", str(text or "").lower()))


def track_label(track_id: str) -> str:
    return LABELS.get(track_id) or track_id[:1].upper() + track_id[1:]


class Catalog:
    def __init__(self, data: Any) -> None:
        self.plans: list[Plan] = []
        self.tracks_by_id: dict[str, Track] = {}
        self.skills_by_id: dict[str, Skill] = {}
        self._by_goal: dict[str, tuple[Plan, dict]] = {}
        self._by_title: dict[str, tuple[Plan, dict]] = {}
        plans = data.get("plans") if isinstance(data, dict) else None
        for raw in plans if isinstance(plans, list) else []:
            try:
                self._add(raw)
            except (KeyError, TypeError, AttributeError) as e:
                log.warning("skill catalog: skipping a bad plan %r: %s", (raw or {}).get("id") if isinstance(raw, dict) else raw, e)

    def _add(self, raw: dict) -> None:
        track_id = str(raw["track"]).strip().lower()
        track = self.tracks_by_id.get(track_id)
        if track is None:
            track = self.tracks_by_id[track_id] = Track(track_id, track_label(track_id), str(raw.get("topic") or ""))
        lessons = [dict(lesson) for lesson in raw.get("lessons") or [] if isinstance(lesson, dict)]
        grown: dict[str, list[str]] = {}
        for lesson in lessons:
            for sid in lesson.get("grows") or []:
                grown.setdefault(sid, []).append(str(lesson.get("title") or ""))
        skills = []
        for s in raw.get("skills") or []:
            sid = str(s["id"])
            if sid in self.skills_by_id:
                continue  # ids are unique in the catalog; a repeat keeps the first
            sk = Skill(sid, str(s.get("label") or sid), track_id, str(raw["id"]), tuple(str(n) for n in s.get("needs") or []),
                       len(track.skills) + len(skills), tuple(grown.get(sid, ())))
            skills.append(sk)
            self.skills_by_id[sid] = sk
        plan = Plan(str(raw["id"]), str(raw.get("title") or raw["id"]), track_id, str(raw.get("topic") or ""),
                    dict(raw.get("tool") or {}), str(raw.get("level") or ""), list(raw.get("needs") or []),
                    dict(raw.get("project") or {}), skills, lessons)
        self.plans.append(plan)
        track.plans.append(plan)
        for lesson in lessons:
            if g := norm(lesson.get("goal")):
                self._by_goal.setdefault(g, (plan, lesson))
            if t := norm(lesson.get("title")):
                self._by_title.setdefault(t, (plan, lesson))

    def match_lesson(self, meta: dict | None) -> tuple[Plan, dict] | None:
        """The catalog lesson a built lesson came from: its goal (the learn query a plan's lesson sends), else its
        title, compared as plain words. None when the lesson is not from the catalog."""
        meta = meta or {}
        for key in ("goal", "asked", "query"):
            if hit := self._by_goal.get(norm(meta.get(key))):
                return hit
        return self._by_title.get(norm(meta.get("title"))) if meta.get("title") else None

    def plan(self, plan_id: str) -> Plan | None:
        return next((p for p in self.plans if p.id == plan_id), None)


@lru_cache(maxsize=4)
def _load(path: str) -> Catalog:
    try:
        return Catalog(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError) as e:
        log.warning("skill catalog unreadable (%s): no tracks", e)
        return Catalog({})


def get() -> Catalog:
    return _load(os.environ.get("MIYAGI_SKILL_CATALOG") or str(CATALOG_PATH))


def tracks() -> list[Track]:
    return list(get().tracks_by_id.values())


def skill(skill_id: str) -> Skill | None:
    return get().skills_by_id.get(skill_id)


def match_lesson(meta: dict | None) -> tuple[Plan, dict] | None:
    return get().match_lesson(meta)

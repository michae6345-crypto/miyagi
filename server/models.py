"""One table: purpose -> Claude model. Every Claude call in the engine looks its model up here.

Policy (cost): Haiku for small calls (hints, checks, judge, triage, scene / target / where picks, requirements,
finder search and scoring, preflight classification); Sonnet for lesson builds (segment), escalation, scaffolding,
diagrams and the coach's diagnosis / selection explanations. Never Opus: every lookup goes through
`server.config.guard_model`, which turns Opus / Fable / Mythos into Sonnet unless MIYAGI_ALLOW_OPUS=1 (and never
through the miyagi cloud).

Each purpose lists the env vars that override it, first set wins, so every override that existed before the table
still works:
  lesson.*       LESSON_CLAUDE_MODEL (forces one model for all lesson roles), LESSON_CLAUDE_MODEL_<ROLE>
  coach.*        COACH_MODEL_<PURPOSE>   (an unlisted coach purpose is Haiku)
  diagrams       DIAGRAMS_MODEL
  workspace.*    WORKSPACE_CLAUDE_MODEL (scaffold), WORKSPACE_REQ_MODEL (requirements)
  finder         FINDER_CLAUDE_MODEL
  screen.*       TUT_SCREEN_COACH_MODEL, TUT_SCREEN_QUICK_MODEL, MIYAGI_VISION_MODEL (target picks)
  scene          MIYAGI_SCENE_MODEL
  preflight      PREFLIGHT_MODEL

Changed defaults: none. (lesson.detail / adapt / judge, requirements, finder, preflight, screen quick / target and
scene were already Haiku; segment, escalate, scaffold, diagrams, screen coach and coach diagnose were already Sonnet.)
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from server import config

SONNET = "claude-sonnet-5-5"
HAIKU = "claude-haiku-5-5"


@dataclass(frozen=True)
class Route:
    default: str
    env: tuple[str, ...] = ()  # override env vars, highest priority first


def _coach(name: str, default: str = HAIKU) -> Route:
    return Route(default, (f"COACH_MODEL_{name.upper()}",))


def _lesson(role: str, default: str) -> Route:
    return Route(default, ("LESSON_CLAUDE_MODEL", f"LESSON_CLAUDE_MODEL_{role.upper()}"))


ROUTES: dict[str, Route] = {
    # lesson builds (server/lesson/claude.py roles)
    "lesson.segment": _lesson("segment", SONNET),      # one big call over the whole transcript: needs reasoning
    "lesson.detail": _lesson("detail", HAIKU),         # per-step fill-in on a transcript slice
    "lesson.adapt": _lesson("adapt", HAIKU),
    "lesson.judge": _lesson("judge", HAIKU),           # goal-fit score
    "lesson.escalate": _lesson("escalate", SONNET),    # retry after a failed quality check (Opus only if opted in)
    # coach
    "coach.diagnose": _coach("diagnose", SONNET),
    "coach.explain": _coach("explain"),
    "coach.explain_selection": _coach("explain_selection", SONNET),
    "coach.circle_ask": _coach("circle_ask"),  # circle to ask (Nov 22): Haiku reads the circled crop
    "coach.hint": _coach("hint"),
    "coach.judge": _coach("judge"),
    "coach.triage": _coach("triage"),
    "coach.point": _coach("point"),
    "coach.locate": _coach("locate"),
    "coach.do_it_for_me": _coach("do_it_for_me"),
    "coach.fix_outdated": _coach("fix_outdated"),
    "coach.scene": Route(HAIKU, ("MIYAGI_SCENE_MODEL",)),
    # screen
    "screen.coach": Route(SONNET, ("TUT_SCREEN_COACH_MODEL",)),   # "what is on my screen?" answers
    "screen.quick": Route(HAIKU, ("TUT_SCREEN_QUICK_MODEL",)),    # where-is-it picks
    "screen.target": Route(HAIKU, ("MIYAGI_VISION_MODEL",)),
    # builders
    "diagrams": Route(SONNET, ("DIAGRAMS_MODEL",)),               # steadier than Haiku for the drawing JSON
    "workspace.scaffold": Route(SONNET, ("WORKSPACE_CLAUDE_MODEL",)),
    "workspace.requirements": Route(HAIKU, ("WORKSPACE_REQ_MODEL",)),
    "finder": Route(HAIKU, ("FINDER_CLAUDE_MODEL",)),
    "preflight": Route(HAIKU, ("PREFLIGHT_MODEL",)),
}
FALLBACK = Route(HAIKU)  # a purpose not in the table (a new coach purpose): the cheap model

# Cache the stable part of the USER message (a transcript, a lesson outline) at this call site? System prompts and
# schemas are always cached (the same bytes on every call, and every install shares the cloud's account). A user
# prefix is cached only where the same build reads it again within the 5-minute TTL; a write that nothing reads costs
# 1.25x for nothing. Flip one from measured cache_read vs cache_write tokens (the per-call `cost` log line and the
# session_cost event, by source) with MIYAGI_CACHE_PREFIX_<SITE>=1|0, e.g. MIYAGI_CACHE_PREFIX_LESSON_DETAIL=1.
PREFIX_CACHE: dict[str, bool] = {
    "lesson.segment": False,    # one call per build over the transcript; repeat builds hit the lesson cache instead
    "lesson.detail": False,     # per-step calls start together (up to DETAIL_CONCURRENCY=8), so none reads another's write
    "lesson.text_step": False,  # "Just teach me" step drafts also run in parallel
}


def cache_prefix(site: str) -> bool:
    """Whether `site` caches its user-message prefix: MIYAGI_CACHE_PREFIX_<SITE> (1/0), else for lesson sites the older
    LESSON_PROMPT_CACHE_USER (1/0), else PREFIX_CACHE (unknown sites: off)."""
    for name in (f"MIYAGI_CACHE_PREFIX_{site.replace('.', '_').upper()}",
                 *(("LESSON_PROMPT_CACHE_USER",) if site.startswith("lesson.") else ())):
        v = (os.environ.get(name) or "").strip()
        if v in ("0", "1"):
            return v == "1"
    return PREFIX_CACHE.get(site, False)


def default_for(purpose: str) -> str:
    return ROUTES.get(purpose, FALLBACK).default


def env_override(purpose: str) -> str | None:
    """The first override env var that is set for `purpose`, else None. A purpose "coach.<name>" that is not
    listed still honors COACH_MODEL_<NAME>."""
    r = ROUTES.get(purpose)
    names = r.env if r else ((f"COACH_MODEL_{purpose.split('.', 1)[1].upper()}",) if purpose.startswith("coach.") else ())
    for n in names:
        v = (os.environ.get(n) or "").strip()
        if v:
            return v
    return None


def model_for(purpose: str, *, allow: bool | None = None) -> str:
    """The model for `purpose`: its env override, else the table default; through the Opus guard (an Opus / Fable /
    Mythos choice becomes Sonnet unless allowed). `allow` replaces the MIYAGI_ALLOW_OPUS check (the lesson passes
    its own LESSON_ALLOW_OPUS)."""
    return config.guard_model(env_override(purpose) or default_for(purpose), SONNET, allow=allow)


def configured(purpose: str) -> str:
    """env override else table default, without the Opus guard. For module constants that callers guard later
    (describe.COACH_MODEL, diagrams.MODEL, target.MODEL): read once at import, as those constants always were."""
    return env_override(purpose) or default_for(purpose)

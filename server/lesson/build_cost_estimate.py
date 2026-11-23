"""What one lesson build costs, before and after prompt caching, from token counts in a profile (no model call).

Prices come from server.lesson.cost.PRICES (cache reads 0.1x input, cache writes 1.25x input). A cached prefix is
written by the first call that carries it and read by later ones inside the 5-minute TTL; a prefix under the model's
minimum cacheable length (about 1024 tokens Sonnet, 2048 Haiku) is never cached. Concurrent calls of a first wave do
not read each other's writes (the entry exists only once the first response starts).

Scenarios:
  cold build         one build, nothing cached yet: caching only costs the 1.25x writes
  build + rebuild    the same video built twice inside the TTL (a prebuild, then the learner's own build; or a
                     segment retry): the second build reads the first one's prefixes
  coach session      the calls a learner makes after the build, all sharing the lesson context
"""

from __future__ import annotations

import json
from pathlib import Path

from . import cost

PROFILE = Path(__file__).parent / "tests" / "fixtures" / "build_cost_profile.json"
STAGES = ("segment", "detail", "adapt", "judge")


def load(path: Path | str = PROFILE) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _min_cache(profile: dict, model: str) -> int:
    mins = profile.get("min_cacheable") or {"sonnet": 1024, "haiku": 2048}
    return mins["haiku"] if "haiku" in model else mins["sonnet"]


def stage_cost(profile: dict, stage: dict, *, caching: bool, warm_system: bool = False, warm_shared: bool = False,
               cache_shared: bool = True) -> float:
    """Dollars for all calls of one stage. `warm_system` / `warm_shared`: the system prompt / the shared prefix is
    already in the cache when the stage starts (an earlier build wrote it). `cache_shared=False`: the shared part of the
    user message is sent uncached (lesson calls with LESSON_PROMPT_CACHE_USER off, the default)."""
    model = stage["after"] if caching else stage["before"]
    n, sysn, shared, own, out = stage["calls"], stage["system"], stage.get("shared", 0), stage["own"], stage["output"]
    if not caching:
        return n * cost.usd(model, sysn + shared + own, out)
    floor = _min_cache(profile, model)
    sys_ok = sysn >= floor
    pre_ok = cache_shared and (sysn + shared) >= floor and shared > 0  # the shared block is cached together with the system before it
    wave = n if stage.get("concurrent_first_wave") else 1  # calls that start before any entry exists
    total = 0.0
    for i in range(n):
        cold = i < wave
        sys_hit = sys_ok and (warm_system or not cold)
        pre_hit = pre_ok and (warm_shared or not cold)
        cr = cw = 0
        plain = own
        if pre_ok:
            if pre_hit:
                cr, plain = sysn + shared, own
            else:
                cw, plain = sysn + shared, own
        elif sys_ok:
            if sys_hit:
                cr, plain = sysn, own + shared
            else:
                cw, plain = sysn, own + shared
        else:
            plain = sysn + shared + own
        total += cost.usd(model, plain, out, cr, cw)
    return total


def build_cost(profile: dict, *, caching: bool, warm: bool = False, cache_user: bool = False) -> float:
    """One build's dollars. warm: an earlier build of the same video ran within the TTL (its system prompts, schema
    and the video's own prefix are in the cache; the lesson outline of the detail calls is the same too).
    cache_user: LESSON_PROMPT_CACHE_USER=1 (the transcript / step-head prefix is cached too); off by default."""
    return sum(stage_cost(profile, profile[s], caching=caching, warm_system=warm, warm_shared=warm, cache_shared=cache_user)
               for s in STAGES)


def coach_session_cost(profile: dict, *, caching: bool) -> float:
    return stage_cost(profile, profile["coach_session"], caching=caching)


def scenarios(profile: dict | None = None) -> dict[str, dict[str, float]]:
    p = profile or load()
    out = {}
    for label, cu in (("", False), (" [transcript cache on]", True)):
        out["cold build" + label] = {"before": build_cost(p, caching=False), "after": build_cost(p, caching=True, cache_user=cu)}
        out["build + rebuild (same video, in TTL)" + label] = {
            "before": 2 * build_cost(p, caching=False),
            "after": build_cost(p, caching=True, cache_user=cu) + build_cost(p, caching=True, warm=True, cache_user=cu)}
    out["coach session (after the build)"] = {"before": coach_session_cost(p, caching=False),
                                              "after": coach_session_cost(p, caching=True)}
    return out


def report(profile: dict | None = None) -> str:
    p = profile or load()
    rows = scenarios(p)
    seg = p["segment"]
    det, ada, jud, coa = p["detail"], p["adapt"], p["judge"], p["coach_session"]
    lines = [
        "Lesson build cost, USD (prices: server/lesson/cost.py PRICES; reads 0.1x, writes 1.25x input)",
        f"  segment: {seg['calls']} call, {seg['after']}, {seg['system']}+{seg['shared']}+{seg['own']} in / {seg['output']} out",
        f"  detail:  {det['calls']} calls, {det['after']}, {det['system']}+{det['shared']}+{det['own']} in / {det['output']} out",
        f"  adapt {ada['calls']} call, judge {jud['calls']} call; coach session {coa['calls']} calls ({coa['system']}+{coa['shared']}+{coa['own']} in)",
        "",
        f"{'scenario':62} {'before':>9} {'after':>9} {'saved':>8}",
    ]
    for name, r in rows.items():
        b, a = r["before"], r["after"]
        lines.append(f"{name:62} ${b:8.4f} ${a:8.4f} {100 * (b - a) / b:7.1f}%")
    return "\n".join(lines)

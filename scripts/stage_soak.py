#!/usr/bin/env python3
"""Soak test: many topics back to back on one LIVE engine (default :8790), each one
search -> build -> setup card -> end_lesson, timing every stage and flagging crashes, hangs (> 120 s
without a new event), wrong-topic lessons and PINN leaks.

  .venv/bin/python scripts/stage_soak.py                  # the default 10 topics
  .venv/bin/python scripts/stage_soak.py --only "css flexbox layout"

A topic may pin a video: "build an LLM from scratch=https://www.youtube.com/watch?v=kCc8FmEb1nY"
(the search still runs, for timing; the pinned URL is built through learn_url).
Writes demo/runs/stage-soak.jsonl (one record per topic) and prints a summary table.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage  # noqa: E402
from stage_lifecycle import Client  # noqa: E402

C = stage.C
TOPICS = [
    "build an LLM from scratch=https://www.youtube.com/watch?v=kCc8FmEb1nY",
    "react useEffect cleanup",
    "pandas groupby",
    "git rebase interactive",
    "fastapi crud api",
    "rust cli with clap",
    "docker compose for a node app",
    "make an AI agent with no code",
    "linear regression in numpy",
    "css flexbox layout",
]
HANG_S = 120.0
STOP = {"a", "an", "the", "in", "for", "with", "of", "to", "and", "from", "make", "build", "tutorial", "app", "no",
        "code", "how", "using", "layout"}


def _mmss(s) -> str:
    try:
        s = int(s)
    except (TypeError, ValueError):
        return "?"
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def topic_terms(q: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9+#]+", q.lower()) if w not in STOP and len(w) > 1}


async def wait_progress(c: Client, i: int, done_pred, *, total_s: float, hang_s: float = HANG_S):
    """Wait for done_pred; fail on `total_s`, or when no event at all arrived for `hang_s` (a hang)."""
    t_start = time.monotonic()
    while True:
        hit = next((e for e in c.events[i:] if done_pred(e)), None)
        if hit:
            return hit, None
        last = c.events[-1][0] if len(c.events) > i else (t_start - c.t0)
        now = time.monotonic() - c.t0
        if now - max(last, t_start - c.t0) > hang_s:
            return None, f"hang: no event for {hang_s:.0f} s"
        if time.monotonic() - t_start > total_s:
            return None, f"timeout after {total_s:.0f} s"
        await asyncio.sleep(0.1)


async def soak_topic(engine: stage.Engine, spec: str) -> dict:
    query, _, pinned = spec.partition("=")
    rec: dict = {"topic": query, "pinned": pinned or None, "bugs": []}
    print(f"\n{C['bold']}=== {query}{C['x']}" + (f"  (pinned {pinned})" if pinned else ""))
    async with Client(engine, "soak") as c:
        await asyncio.sleep(0.3)
        # ---- search
        i = c.mark()
        t0 = time.monotonic() - c.t0
        await c.send("learn", {"query": query})
        done, err = await wait_progress(c, i, lambda e: e[1] == "search.done", total_s=90)
        rows = [p for _, ty, p in c.since(i) if ty == "search.result"]
        first = next((t for t, ty, _ in c.since(i) if ty == "search.result"), None)
        rec["search_first_s"] = round(first - t0, 1) if first else None
        rec["search_done_s"] = round(done[0] - t0, 1) if done else None
        rec["n_results"] = len(rows)
        rec["n_videos"] = sum(1 for r in rows if r.get("kind") == "video")
        if err:
            rec["bugs"].append(f"E7 finder: search {err}")
        final, _notes, _tim = stage._finder_final(query, since=0)
        sent = {r["id"]: r for r in rows}
        pick = None
        if pinned:
            vid = pinned.rsplit("=", 1)[-1]
            pick = next((r for r in rows if vid in (r.get("url") or "")), None) or {"url": pinned, "title": "(pinned)", "kind": "video"}
        else:
            pick = next((sent[r["id"]] | {k: r.get(k) for k in ("score", "reason")} for r in final if r["id"] in sent), None) \
                or next((r for r in rows if r.get("kind") == "video"), None)
        if not pick:
            rec["bugs"].append("E7 finder: no result to build from")
            rec["result"] = "no pick"
            return rec
        rec["pick"] = {k: pick.get(k) for k in ("title", "kind", "url", "durationS", "channel", "score")}
        print(f"  search {rec['search_first_s']} s first · {rec['search_done_s']} s done · {rec['n_results']} rows "
              f"({rec['n_videos']} videos) · pick [{pick.get('kind')}] {pick.get('title', '')[:60]!r} {_mmss(pick.get('durationS'))}")
        if pick.get("kind") != "video":
            rec["bugs"].append(f"E7 finder: best pick is a {pick.get('kind')}, not a video")
        # ---- build
        j = c.mark()
        tb = time.monotonic() - c.t0
        if pinned or "id" not in pick:
            await c.send("learn_url", {"url": pick["url"]})
        else:
            await c.send("build_lesson", {"resultIds": [pick["id"]]})
        hit, err = await wait_progress(c, j, lambda e: e[1] == "lesson.ready" or (e[1] == "lesson.building" and e[2].get("failed")),
                                       total_s=330)
        stages, last = [], None
        for t, ty, p in c.since(j):
            if ty == "lesson.building":
                txt = re.sub(r"\s*·\s*\d+:\d\d$", "", p.get("message", ""))
                if txt != last:
                    stages.append((round(t - tb, 1), txt))
                    last = txt
            elif ty == "card" and p.get("kind") not in ("setup", "resume", None) and t < (hit[0] if hit else 1e9):
                stages.append((round(t - tb, 1), f"card {p.get('kind')}: {p.get('title')}"))
        rec["stages"] = stages
        steps_ready = next((t for t, s in stages if s.startswith("Steps ready")), None)
        rec["first_steps_s"] = steps_ready
        rec["preflight"] = [s for _, s in stages if s.startswith("card ")] or None
        errors = [p.get("message") for _, ty, p in c.since(j) if ty == "error"]
        rec["errors"] = errors
        if not hit or hit[1] != "lesson.ready":
            rec["result"] = "FAILED"
            rec["build_s"] = round((hit[0] if hit else time.monotonic() - c.t0) - tb, 1)
            rec["bugs"].append(f"build failed: {errors[-1] if errors else err}")
            if err and err.startswith("hang"):
                rec["bugs"][-1] = f"E4/E2 HANG during build ({err})"
            print(f"  {C['r']}build FAILED after {rec['build_s']} s: {errors[-1] if errors else err}{C['x']}")
            print(f"  stages: {stages}")
        else:
            rec["result"] = "OK"
            rec["build_s"] = round(hit[0] - tb, 1)
            ready = hit[2]
            rec["n_steps"] = len(ready.get("steps", []))
            # setup card (S2) arrives in the background after lesson.ready
            setup, _ = await wait_progress(c, j, lambda e: e[1] == "card" and e[2].get("kind") == "setup", total_s=45, hang_s=45)
            if setup:
                su = setup[2].get("setup") or {}
                items = su.get("items") or []
                rec["setup"] = {"t_after_ready": round(setup[0] - hit[0], 1), "editorNeeded": su.get("editorNeeded"),
                                "title": setup[2].get("title"), "actions": setup[2].get("actions"),
                                "items": [f"{it.get('tool')}{'' if it.get('installed') else ' (missing)'}" for it in items if it.get("needed")]}
            else:
                rec["setup"] = None
            st = engine.state()
            graph, how = stage._full_graph(engine, ready["lesson"]["id"], rec["n_steps"])
            lesson = (graph or {}).get("lesson", {})
            rec["builtBy"] = lesson.get("builtBy")
            rec["model"] = (graph or {}).get("build", {}).get("model")
            rec["title"] = lesson.get("title")
            rec["workdir"] = st.get("workdir")
            rec["step_titles"] = [s.get("title") for s in (graph or {}).get("steps", [])]
            blob = json.dumps(graph or {}, ensure_ascii=False)
            leak = stage.leaks_in(blob, topic=query)
            if re.search(r"pinn", st.get("workdir") or "", re.I):
                leak.insert(0, f"workdir {st.get('workdir')}")
            rec["leaks"] = leak
            if leak:
                rec["bugs"].append(f"PINN leak: {leak}")
            terms = topic_terms(query)
            text = (rec["title"] or "") + " " + " ".join(rec["step_titles"]) + " " + " ".join(
                s.get("instructions", "") for s in (graph or {}).get("steps", []))
            hits = {t for t in terms if t in text.lower()}
            rec["topic_terms_hit"] = f"{len(hits)}/{len(terms)}"
            if terms and not hits:
                rec["bugs"].append(f"wrong topic? none of {sorted(terms)} in the lesson")
            print(f"  {C['g']}lesson.ready {rec['build_s']} s{C['x']} ({how}) · {rec['n_steps']} steps · builtBy {rec['builtBy']} "
                  f"· model {rec['model']} · {rec['title']!r}")
            print(f"  stages: {stages}")
            print(f"  setup: {rec['setup']}")
            print(f"  steps: {rec['step_titles']}")
            print(f"  topic terms {rec['topic_terms_hit']} · leaks {leak or 'none'} · workdir {rec['workdir']}")
        # ---- end
        k = c.mark()
        await c.send("end_lesson", {})
        ended, err = await wait_progress(c, k, lambda e: e[1] == "lesson.ended", total_s=10, hang_s=10)
        idle = await c.wait_for(lambda e: e[1] == "status" and e[2].get("state") == "idle", k, 5)
        await asyncio.sleep(2)
        leftover = [ty for t, ty, _ in c.since(k) if ended and t > ended[0] and ty in ("card", "diagram", "offtrack", "step.started", "video.play")]
        st = engine.state()
        rec["ended_clean"] = bool(ended and idle and not leftover and st.get("phase") == "idle" and not st.get("lesson"))
        if not rec["ended_clean"]:
            rec["bugs"].append(f"E4: end_lesson not clean (ended={bool(ended)} idle={bool(idle)} leftover={leftover} phase={st.get('phase')})")
        print(f"  end_lesson: {'clean' if rec['ended_clean'] else 'NOT clean'}")
    if not engine.health():
        rec["bugs"].append("E4: ENGINE CRASHED (no /health)")
    return rec


engine_open_ws = False


async def run(engine: stage.Engine, topics: list[str]) -> list[dict]:
    out = []
    for spec in topics:
        try:
            rec = await soak_topic(engine, spec)
        except Exception as e:  # noqa: BLE001 - one topic's failure must not stop the soak
            rec = {"topic": spec.partition("=")[0], "result": "RUNNER ERROR", "bugs": [f"runner: {type(e).__name__}: {e}"]}
        rec["at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        out.append(rec)
        with (stage.RUNS / "stage-soak.jsonl").open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if not engine.health():
            print(f"{C['r']}engine is down after {rec['topic']!r}; restarting for the next topic{C['x']}")
            engine.ensure(screen=False, open_ws=engine_open_ws, workdir=None)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--only", action="append", default=[], help="run just these topics (repeatable, same syntax)")
    ap.add_argument("--open", action="store_true",
                    help="ORCH_OPEN_WORKSPACE=1: the engine sends S2's setup card (VS Code still opens only on open_editor)")
    ap.add_argument("--fresh", action="store_true", help="restart the engine first")
    args = ap.parse_args()
    engine = stage.Engine(args.port)
    engine.ensure(screen=False, open_ws=args.open, workdir=None, fresh=args.fresh)
    stage.RUNS.mkdir(parents=True, exist_ok=True)
    global engine_open_ws
    engine_open_ws = args.open
    recs = asyncio.run(run(engine, args.only or TOPICS))
    print(f"\n{C['bold']}topic | search first/done | pick (kind, length) | build | first steps | builtBy | steps | setup | end | bugs{C['x']}")
    for r in recs:
        p = r.get("pick") or {}
        su = r.get("setup")
        print(f"{r['topic']} | {r.get('search_first_s')}/{r.get('search_done_s')} s | {str(p.get('title'))[:40]} ({p.get('kind')}, "
              f"{_mmss(p.get('durationS'))}) | {r.get('result')} {r.get('build_s')} s | {r.get('first_steps_s')} s | {r.get('builtBy')} | "
              f"{r.get('n_steps')} | {'editor' if su and su.get('editorNeeded') else ('no editor' if su else '—')} | "
              f"{'clean' if r.get('ended_clean') else 'NOT clean'} | {'; '.join(r['bugs']) or '—'}")


if __name__ == "__main__":
    main()

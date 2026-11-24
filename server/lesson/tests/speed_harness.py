"""Build-speed harness: the REAL video builder (builder.build_lesson, Claude transcript path) on a virtual clock, with
every model call, the watch page, the captions and the shared lesson cache faked at fixed latencies. Offline: no key,
no network, no paid call; a 40 s build runs in well under a second of real time.

    python -m server.lesson.tests.speed_harness          # the critical-path timeline, before vs after

"Before" is the same code with LESSON_FAST_FIRST_STEP=0 (no step-1-first path, no prefetch: the old serial build).

Latencies (PROFILE_10MIN) come from the one recorded real build on disk (~/miyagi/engine/logs/engine.log, Nov 22
15:14:02, "AutoCAD - Toy Car Creation for 3D Printer", 17.6 min, 386 caption lines, 7 steps, built in 39.6 s):
watch page 0.24 s + timedtext 0.57 s; goal match (Haiku) 1.3 s; segment (Sonnet, effort medium, 7.4k tokens in)
9.3 s; per-step detail (Haiku) 3.6 / 5.8 / 6.0 / 7.7 / 6.3 / 6.7 / 6.5 s, at most 4 in flight (claude.CONCURRENCY);
adapt (Haiku) 2.6 s for a 1-step batch, 6.8-7.0 s for 3 steps; adapt retry with lint feedback (Sonnet) 4.9-7.0 s per
batch; 5 of 7 steps failed lint on round 1. Scaled to a typical 10-minute video (ASSUMED, not recorded): 6 steps,
segment 8.0 s (fewer caption lines in), the shared lesson cache's lookup + claim 0.3 s each (not in that log).
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import json
import os
import re
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

VID = "SPEEDtest01"
URL = f"https://www.youtube.com/watch?v={VID}"
GOAL = "build a todo app in python"
TITLE = "Todo app in Python"

PROFILE_10MIN = {
    "name": "typical 10-min video (6 steps)",
    "length_s": 600, "steps": 6,
    "watch_page_s": 0.25, "captions_s": 0.55, "shared_lookup_s": 0.3, "shared_claim_s": 0.3,
    "goal_s": 1.3, "segment_s": 8.0,
    "detail_s": [3.6, 5.8, 6.0, 7.7, 6.3, 6.7],
    "adapt_s": (2.6, 2.2),  # Haiku: first step in the batch, then each more step
    "escalate_s": (5.0, 2.45),  # Sonnet retry with the lint feedback
    "lint_fail": {3, 5},  # steps whose round-1 adapt output lint rejects (step 1 passes)
}
# the same video when step 1's own round-1 checks fail lint too (5 of 7 steps did in the recorded build)
PROFILE_10MIN_S1_RETRY = {**PROFILE_10MIN, "name": "same, step 1 needs an adapt retry", "lint_fail": {1, 3, 5}}
# the recorded build itself (Nov 22, 17.6 min, 7 steps): its own segment and detail latencies; 5 of 7 steps failed
# lint in round 1, in 2 of its batches (which 5 is not in the log: steps 1-5 is one set that fits)
PROFILE_RECORDED = {**PROFILE_10MIN, "name": "recorded Nov 22 build (17.6 min, 7 steps)", "length_s": 1056, "steps": 7,
                    "watch_page_s": 0.24, "captions_s": 0.57, "segment_s": 9.3,
                    "detail_s": [3.6, 5.8, 6.0, 7.7, 6.3, 6.7, 6.5], "lint_fail": {1, 2, 3, 4, 5}}


def scaled(profile: dict, k: float) -> dict:
    """The profile with every latency times k (a real-clock test: 0.01 turns seconds into tens of milliseconds)."""
    q = dict(profile)
    for key in ("watch_page_s", "captions_s", "shared_lookup_s", "shared_claim_s", "goal_s", "segment_s"):
        q[key] = profile[key] * k
    q["detail_s"] = [x * k for x in profile["detail_s"]]
    q["adapt_s"] = tuple(x * k for x in profile["adapt_s"])
    q["escalate_s"] = tuple(x * k for x in profile["escalate_s"])
    return q


# --------------------------------------------------------------------------- virtual clock
class _VirtualSelector:
    """asyncio's selector, but a wait with nothing ready jumps the clock to the next timer instead of sleeping."""

    def __init__(self, real, clock: list[float]) -> None:
        self._real, self._clock = real, clock

    def select(self, timeout=None):
        ready = self._real.select(0)
        if ready or timeout == 0:
            return ready
        if timeout is None:
            return self._real.select(None)  # nothing scheduled: only real I/O (a thread) can wake the loop
        self._clock[0] += timeout
        return []

    def __getattr__(self, name):
        return getattr(self._real, name)


def run_virtual(coro):
    loop = asyncio.new_event_loop()
    clock = [0.0]
    loop.time = lambda: clock[0]  # type: ignore[method-assign]
    loop._selector = _VirtualSelector(loop._selector, clock)  # type: ignore[attr-defined]
    try:
        return loop.run_until_complete(coro)
    finally:
        for t in asyncio.all_tasks(loop):
            t.cancel()
        loop.run_until_complete(asyncio.sleep(0))
        loop.close()


def now() -> float:
    return asyncio.get_running_loop().time()


# --------------------------------------------------------------------------- fakes
def _mmss(t: float) -> str:
    return f"{int(t) // 60}:{int(t) % 60:02d}"


def _spans(p: dict) -> list[tuple[float, float]]:
    n, L = p["steps"], p["length_s"]
    return [((k * L) / n + 5, ((k + 1) * L) / n) for k in range(n)]


def _text(x) -> str:
    if isinstance(x, str):
        return x
    if isinstance(x, (list, tuple)):
        return "\n".join(_text(b) for b in x)
    if isinstance(x, dict):
        return str(x.get("text") or "")
    return ""


class Fakes:
    def __init__(self, profile: dict) -> None:
        self.p = profile
        self.events: list[dict] = []
        self.updates: list[dict] = []
        self._meta: asyncio.Future | None = None

    def log(self, kind: str, t0: float, **kw) -> None:
        self.events.append({"kind": kind, "start": round(t0, 3), "end": round(now(), 3), **kw})

    async def call_once(self, mid, system, prompt, *, effort, schema):
        p, sys_t, txt = self.p, _text(system), _text(prompt)
        t0 = now()
        if "judge whether a tutorial fits" in sys_t:
            await asyncio.sleep(p["goal_s"])
            self.log("goal", t0)
            return SimpleNamespace(model=mid), json.dumps({"score": 0.9, "note": "fits"})
        if "Break this tutorial into" in txt:
            await asyncio.sleep(p["segment_s"])
            self.log("segment", t0)
            steps = [{"start": _mmss(a), "end": _mmss(b), "title": f"Write part {k} of the app",
                      "instructions": f"Write part {k} of todo.py."} for k, (a, b) in enumerate(_spans(p), 1)]
            return SimpleNamespace(model=mid), json.dumps({"title": p.get("title", TITLE), "libraries": [], "steps": steps})
        m = re.search(r"Fill in step (\d+)", txt)
        if m:
            i = int(m.group(1))
            await asyncio.sleep(p["detail_s"][(i - 1) % len(p["detail_s"])])
            self.log("detail", t0, steps=[i])
            a, _b = _spans(p)[i - 1]
            out = {
                "file": p.get("work_file", "todo.py"), "code": f"def part_{i}():\n    return {i}",
                "checks": [{"type": "screen_contains", "label": f"part_{i} typed", "app": "Code", "pattern": f"def part_{i}"}],
                "targets": [{"app": "Code", "match": f"def part_{i}", "caption": "Type it here"}],
                "explanations": [{"topic": f"idea {i}", "t": _mmss(a + 20)}],
                "hints": [f"Start with def part_{i}", "Return the number"], "common_mistakes": [f"Naming it part{i}"]}
            out.update(copy.deepcopy((p.get("detail_extra") or {}).get(i) or {}))  # a test's own fields for step i
            return SimpleNamespace(model=mid), json.dumps(out)
        if "previous answer had these problems" in txt or '"index"' in txt:
            idx = [int(x) for x in re.findall(r'"index":\s*(\d+)', txt)]
            retry = "previous answer had these problems" in txt
            base, per = p["escalate_s"] if retry else p["adapt_s"]
            await asyncio.sleep(base + per * (len(idx) - 1))
            self.log("adapt_retry" if retry else "adapt", t0, steps=idx)
            out = []
            for i in idx:
                # lint rejects a screen pattern over 60 chars (OCR is noisy): round 1's for the lint_fail steps
                bad = i in p["lint_fail"] and (not retry or i in p.get("lint_fail_always", ()))  # "always": no retry fixes it
                pat = (rf"def\s+part_{i}\b" + r"\s*\(\s*\)\s*:" * 6) if bad else rf"def\s+part_{i}\b"
                wf = p.get("work_file", "todo.py")
                out.append({"index": i, "checks": [{"type": "screen_contains", "label": f"part_{i} typed", "app": "Code", "pattern": pat}],
                            "precision_checks": [{"type": "file_contains", "label": f"part_{i} in {wf}", "file": wf,
                                                  "pattern": f"def part_{i}"}],
                            "targets": [{"app": "Code", "file": wf, "match": f"def part_{i}", "caption": "Type it here"}],
                            **copy.deepcopy((p.get("adapt_extra") or {}).get(i) or {})})
            return SimpleNamespace(model=mid), json.dumps({"steps": out})
        raise AssertionError(f"unexpected model call: {txt[:120]!r}")

    async def fetch_metadata(self, vid):
        """Like transcript.fetch_metadata: the watch page is fetched once per video per process."""
        if self._meta is None:
            self._meta = asyncio.ensure_future(self._watch_page(vid))
        return dict(await asyncio.shield(self._meta))

    async def _watch_page(self, vid):
        t0 = now()
        await asyncio.sleep(self.p["watch_page_s"])
        self.log("watch_page", t0)
        return {"video_id": vid, "title": self.p.get("title", TITLE), "description": "Building a todo app.",
                "length_s": self.p["length_s"], "chapters": []}

    async def fetch_video_info(self, vid):
        meta = await self.fetch_metadata(vid)
        t0 = now()
        await asyncio.sleep(self.p["captions_s"])
        self.log("captions", t0)
        lines = [{"t": float(t), "text": f"now we write line {t}"} for t in range(0, self.p["length_s"], 3)]
        return {**meta, "transcript": lines, "sources": {"transcript": "youtube.com timedtext"}, "errors": []}

    async def lookup(self, vid, **kw) -> None:  # a shared-cache miss
        t0 = now()
        await asyncio.sleep(self.p["shared_lookup_s"])
        self.log("shared_lookup", t0)

    async def claim_build(self, vid, poll) -> None:  # claimed: build here
        t0 = now()
        await asyncio.sleep(self.p["shared_claim_s"])
        self.log("shared_claim", t0)


class _Blocked:
    def __init__(self, *a, **k):
        raise AssertionError("the speed harness never creates a real API client")


@contextlib.contextmanager
def patched(fakes: Fakes, *, fast: bool, root: Path, batched: bool = True):
    import anthropic
    import httpx

    from server.lesson import builder, claude, cloud_cache, materials, transcript

    async def no_net(self, request, *a, **k):
        raise AssertionError(f"the speed harness never reaches the network: {request.url}")

    async def no_materials(url, **k):
        raise RuntimeError("offline")

    env = {"LESSON_NO_DOTENV": "1", "LESSON_FAST_FIRST_STEP": "1" if fast else "0", "MIYAGI_STATE_DIR": str(root / "state"),
           "LESSON_BATCHED_ADAPT": "1" if batched else "0"}
    keys = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "GEMINI_API_KEY", "GOOGLE_API_KEY", "LESSON_ENGINE",
            "LESSON_CLAUDE_MODEL", "LESSON_QUICK_START_S", "ORCH_PREBUILD")
    with contextlib.ExitStack() as st:
        st.enter_context(mock.patch.dict(os.environ, env))
        for k in keys:
            if k in os.environ:
                st.enter_context(mock.patch.dict(os.environ, {k: ""}))
                del os.environ[k]
        for obj, name, val in [
            (anthropic, "AsyncAnthropic", _Blocked), (anthropic, "Anthropic", _Blocked), (httpx.AsyncClient, "send", no_net),
            (claude, "_call_once", fakes.call_once), (claude, "_client", None), (claude, "_schema_too_complex", set()),
            (transcript, "fetch_metadata", fakes.fetch_metadata), (transcript, "fetch_video_info", fakes.fetch_video_info),
            (materials, "_http_get", no_materials), (materials, "_tasks", {}),
            (cloud_cache, "enabled", lambda: True), (cloud_cache, "lookup", fakes.lookup),
            (cloud_cache, "claim_build", fakes.claim_build), (cloud_cache, "share_later", lambda *a, **k: None),
            (builder, "CACHE_DIR", root / "lessons"), (builder, "RAW_DIR", root / "lessons" / "raw"),
        ]:
            st.enter_context(mock.patch.object(obj, name, val))
        yield


def build_once(profile: dict, *, fast: bool, root: Path | None = None, fakes: Fakes | None = None, batched: bool = True,
               **build_kw) -> dict:
    """One build of the profile's video on the virtual clock -> {graph, events, updates, done_s}. `root`: a folder to
    keep the lesson caches in across builds (default: a fresh temporary one)."""
    from server.lesson import builder

    fakes = fakes or Fakes(profile)
    with contextlib.ExitStack() as st:
        if root is None:
            root = Path(st.enter_context(tempfile.TemporaryDirectory()))
        (root / "work").mkdir(exist_ok=True)
        st.enter_context(patched(fakes, fast=fast, root=root, batched=batched))

        async def go():
            def on_update(graph, complete):
                fakes.updates.append({"t": round(now(), 3), "complete": complete,
                                      "provisional": bool((graph.get("lesson") or {}).get("provisional")),
                                      "steps": [s["id"] for s in graph.get("steps") or []],
                                      "graph": copy.deepcopy(graph)})

            g = await builder.build_lesson(URL, GOAL, str(root / "work"), on_update=on_update,
                                           video_meta={"title": profile.get("title", TITLE), "length_s": profile["length_s"]},
                                           **build_kw)
            return g, round(now(), 3)

        graph, done_s = run_virtual(go())
    return {"graph": graph, "events": fakes.events, "updates": fakes.updates, "done_s": done_s}


def first_step_s(run: dict) -> float | None:
    """When the learner's REAL step 1 arrives: the first non-placeholder update, else the finished build."""
    real = [u["t"] for u in run["updates"] if not u["provisional"]]
    return min(real) if real else run["done_s"]


def comparable(graph: dict) -> dict:
    """A finished graph without what differs from run to run by design (wall-clock seconds, the step-1 record)."""
    g = copy.deepcopy(graph)
    b = g.get("build") or {}
    for k in ("seconds", "firstStep", "cost"):
        b.pop(k, None)
    (b.get("model") or {}).pop("adapt", None)  # the model of the LAST adapt call: step 1's own is in build.firstStep
    (g.get("lesson") or {}).pop("workdir", None)  # each run's own temporary folder
    return g


# --------------------------------------------------------------------------- report
def _span(run: dict, kind: str, step: int | None = None) -> tuple[float, float] | None:
    ev = [e for e in run["events"] if e["kind"] == kind and (step is None or step in e.get("steps", []))]
    return (min(e["start"] for e in ev), max(e["end"] for e in ev)) if ev else None


def timeline_rows(run: dict) -> list[tuple[str, str]]:
    def fmt(sp):
        return f"{sp[0]:5.1f} -> {sp[1]:5.1f}" if sp else "      -       "

    rows = [("shared lesson cache (lookup + claim)", fmt(_span(run, "shared_lookup") and (
                _span(run, "shared_lookup")[0], (_span(run, "shared_claim") or _span(run, "shared_lookup"))[1]))),
            ("watch page + captions", fmt(_span(run, "watch_page") and (_span(run, "watch_page")[0], _span(run, "captions")[1]))),
            ("segment call (step list)", fmt(_span(run, "segment"))),
            ("step 1 detail call", fmt(_span(run, "detail", 1))),
            ("all detail calls", fmt(_span(run, "detail"))),
            ("step 1 adapt (round 1)", fmt(_span(run, "adapt", 1))),
            ("step 1 adapt retry (lint feedback)", fmt(_span(run, "adapt_retry", 1))),
            ("all adapt calls", fmt((min(e["start"] for e in run["events"] if e["kind"].startswith("adapt")),
                                    max(e["end"] for e in run["events"] if e["kind"].startswith("adapt"))))),
            ("quick-start placeholder (no checks)", next((f"{u['t']:5.1f}" for u in run["updates"] if u["provisional"]), "-")),
            ("REAL STEP 1 READY", f"{first_step_s(run):5.1f}"),
            ("full lesson ready", f"{run['done_s']:5.1f}")]
    return rows


def calls(run: dict) -> dict:
    """Model calls a build made, by kind (adapt round 1 is Haiku, an adapt retry with lint feedback is Sonnet)."""
    out: dict = {}
    for e in run["events"]:
        out[e["kind"]] = out.get(e["kind"], 0) + 1
    return out


MODES = (("serial", {"fast": False}), ("step 1 first", {"fast": True, "batched": False}), ("batched", {"fast": True}))


def report(profiles=(PROFILE_10MIN, PROFILE_10MIN_S1_RETRY, PROFILE_RECORDED)) -> str:
    """The critical-path timeline of each profile in each mode: serial (LESSON_FAST_FIRST_STEP=0), step 1 first
    (LESSON_BATCHED_ADAPT=0) and batched (both on, the default)."""
    out = []
    for p in profiles:
        runs = [(name, build_once(p, **kw)) for name, kw in MODES]
        ref = comparable(runs[0][1]["graph"])
        out.append(f"\n{p['name']}  (seconds from the Build press; virtual clock)")
        out.append(f"{'stage':40s}" + "".join(f" {name:>16s}" for name, _r in runs))
        rows = [timeline_rows(r) for _n, r in runs]
        for k, (label, _v) in enumerate(rows[0]):
            out.append(f"{label:40s}" + "".join(f" {r[k][1]:>16s}" for r in rows))
        for kind, label in (("adapt", "adapt calls, round 1 (Haiku)"), ("adapt_retry", "adapt retries (Sonnet)")):
            out.append(f"{label:40s}" + "".join(f" {calls(r).get(kind, 0):>16d}" for _n, r in runs))
        same = all(comparable(r["graph"]) == ref for _n, r in runs)
        out.append(f"finished lesson, same steps in every mode on this deterministic fake: {same}")
    return "\n".join(out)


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.WARNING)
    print(report())

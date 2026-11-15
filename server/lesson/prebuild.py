"""Speculative pre-builds: start building a lesson before the learner clicks Build.

Opt-in: only active with ORCH_PREBUILD=1 (it spends model calls on videos that may never be picked).
The orchestrator calls prebuild() for the top 1-2 video results as soon as search.done lands (and
for the picked video when preflight starts). When the learner clicks Build, build_lesson() attaches
to the in-flight or finished job instead of starting over: it replays the progress stages and the
latest partial graph, then forwards later updates. At most MAX_CONCURRENT jobs run; the ones not
picked are cancelled once a lesson starts. Every job logs what it cost (model calls), used or not.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

from . import cost

log = logging.getLogger("server.lesson")

MAX_CONCURRENT = int(os.environ.get("LESSON_PREBUILD_MAX", "2"))
_jobs: dict[str, "Job"] = {}


class Job:
    def __init__(self, vid: str, url: str, goal: str, workdir: str, video_meta: dict | None):
        self.vid, self.url, self.goal, self.workdir, self.video_meta = vid, url, goal, workdir, video_meta
        self.started = time.time()
        self.latest: dict | None = None
        self.stages: list[tuple[str, str]] = []
        self.update_listeners: list = []
        self.progress_listeners: list = []
        self.cost: dict = {}
        self.used = False
        self.workdir_fp: str | None = None
        self.task: asyncio.Task | None = None

    async def run(self) -> dict:
        from . import builder
        from .workdir import scan

        self.cost = cost.start()
        self.workdir_fp = builder.workdir_fingerprint(self.workdir, scan(self.workdir))
        try:
            g = await builder.build_lesson(self.url, self.goal, self.workdir, on_update=self._on_update,
                                           on_progress=self._on_progress, video_meta=self.video_meta, _prebuild=True)
            log.info("prebuild %s done in %.1fs (%s)%s", self.vid, time.time() - self.started, self.cost,
                     "" if self.used else ", not (yet) used")
            return g
        except asyncio.CancelledError:
            log.info("prebuild %s cancelled after %.1fs; spent %s", self.vid, time.time() - self.started, self.cost)
            raise

    async def _on_update(self, graph: dict, complete: bool) -> None:
        self.latest = graph
        for cb in list(self.update_listeners):
            await _call(cb, graph, complete)

    def _on_progress(self, stage: str, message: str) -> None:
        self.stages.append((stage, message))
        for cb in list(self.progress_listeners):
            r = cb(stage, message)
            if asyncio.iscoroutine(r):
                asyncio.ensure_future(r)


async def _call(cb, *args) -> None:
    try:
        r = cb(*args)
        if asyncio.iscoroutine(r):
            await r
    except Exception as e:  # noqa: BLE001  a UI callback must never break a build
        log.warning("prebuild listener failed: %s", e)


def prebuild(url: str, goal: str, workdir: str, *, video_meta: dict | None = None) -> bool:
    """Start building `url` in the background (call from the running event loop). Returns True if a job
    for this video is running or finished, False if it was skipped (cap reached or not a YouTube URL)."""
    from .gemini import youtube_id

    if os.environ.get("ORCH_PREBUILD", "0") != "1":  # opt-in: speculative builds cost money even when unused
        return False
    vid = youtube_id(url)
    if not vid:
        return False
    old = _jobs.get(vid)
    if old and old.task and not (old.task.cancelled() or (old.task.done() and old.task.exception())):
        return True
    running = [j for j in _jobs.values() if j.task and not j.task.done()]
    if len(running) >= MAX_CONCURRENT:
        log.info("prebuild %s skipped: %d already running", vid, len(running))
        return False
    job = Job(vid, url, goal, workdir, video_meta)
    job.task = asyncio.ensure_future(job.run())
    job.task.add_done_callback(lambda t: t.cancelled() or t.exception())  # never "exception was never retrieved"
    _jobs[vid] = job
    log.info("prebuild %s started (%d running)", vid, len(running) + 1)
    return True


async def attach(vid: str, workdir: str, on_update=None, on_progress=None) -> dict | None:
    """The finished or in-flight prebuild for this video and workdir, or None (build normally)."""
    from . import builder
    from .workdir import scan

    job = _jobs.get(vid)
    if not job or not job.task or job.task.cancelled():
        return None
    if job.task.done() and job.task.exception() is not None:
        return None  # it failed: let a fresh build try (quota may be back)
    if job.workdir_fp != builder.workdir_fingerprint(workdir, scan(workdir)):
        return None  # adapted to a different project
    job.used = True
    t = time.time()
    for stage, msg in job.stages:  # replay what already happened
        if on_progress:
            await _call(on_progress, stage, msg)
    if job.latest is not None and on_update and not job.task.done():
        await _call(on_update, job.latest, False)
    if on_update:
        job.update_listeners.append(on_update)
    if on_progress:
        job.progress_listeners.append(on_progress)
    try:
        g = await asyncio.shield(job.task)
    except asyncio.CancelledError:
        return None
    except Exception:  # noqa: BLE001
        return None
    log.info("prebuild %s used: %.1fs after the click (started %.1fs before it)", vid, time.time() - t, t - job.started)
    return dict(g, lesson=dict(g["lesson"], workdir=workdir))


def cancel(except_vid: str | None = None) -> int:
    """Cancel running prebuilds other than `except_vid` (call when a lesson starts). Returns how many."""
    n = 0
    for vid, job in list(_jobs.items()):
        if vid != except_vid and job.task and not job.task.done():
            job.task.cancel()
            n += 1
    return n


def status() -> list[dict]:
    return [{"videoId": v, "running": bool(j.task and not j.task.done()), "seconds": round(time.time() - j.started, 1),
             "used": j.used, "cost": dict(j.cost)} for v, j in _jobs.items()]

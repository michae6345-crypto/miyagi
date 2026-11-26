"""Step 1 first: a video lesson's first step reaches the learner as soon as it is built, the rest streams in after.

The Claude transcript path (builder._watch's claude_draft) is: one segment call (the step list), then one detail call
per step in parallel, then the adapt pass (fit the checks to the learner's folder, lint, retry what lint rejects). The
learner used to wait for ALL of it (recorded Nov 22: 39.6 s on a 7-step video, step 1's own work was ~16 s of that).

FirstStep watches that build through claude.DETAIL_HOOKS:

* segment(seg): which segment steps make up the lesson's step 1 after normalize_draft (usually just the first one;
  more when a micro step is merged into it). Those detail calls get claude.PRIORITY (they go before the rest of the
  fan-out) and one Claude lane is reserved for step 1 until it is built.
* detail(i, step): once every piece of step 1 is filled, step 1 is built in its own task, with the SAME functions the
  full build uses: normalize_draft + timing.pin_starts + rehome_explanations over the whole step list (start/end come
  from the segment, so step 1's timing is the full build's), the link check, builder._adapt on step 1 alone (same
  adapt prompt and models, same lint, same retry-with-feedback, same repair), the link strip, community mistakes,
  use_lesson_venv / use_lesson_notebook, and the step-graph contract. Lesson-wide decisions (is this an app lesson or
  a code lesson, a notebook lesson and its notebook's name) see the whole step list known so far.
* The graph {lesson (complete: false), sources, steps: [s1]} goes to on_update(graph, False): the orchestrator's
  existing progressive path (E2 long videos, the quick-start placeholder) starts the lesson on it, and the full build
  later appends s2..sN (lesson.updated; ids never change, earlier steps are never edited).

The full build then LOCKS step 1 (builder._adapt(locked=...)): step 1's adapt result is reused instead of adapting it
again, its lint problems are not retried (it is final), and the finished graph's step 1 is the one the learner got,
byte for byte, so the cached / shared lesson is what the learner saw. If step 1 can't be built early (its adapt pass
failed, the contract rejected it, anything raised), nothing is sent and the full build adapts step 1 as before.

Lesson-wide choices the full build would make from every step are pinned to what step 1 shipped with: for a video
whose title names an app (AutoCAD, Excel) step 1 waits for every step's detail before "app lesson or code lesson" is
decided, and the full build keeps that choice and step 1's notebook choice (builder._adapt / _lock_first_step). The
session's first graph carries the other steps as known so far in build.upcomingSteps (server.workspace.paths.
lesson_steps), so the starter files never hold what a later step has the learner write; no event to the app carries it.
Once the build ends (close(): returned, failed or cancelled) step 1 is never sent, and a build that fails before step
1's on_update started fails the normal way.

Off with LESSON_FAST_FIRST_STEP=0 (also turns off builder's transcript prefetch): the build is then the old serial one.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import os
import time

from . import claude

log = logging.getLogger("server.lesson")


def enabled() -> bool:
    return os.environ.get("LESSON_FAST_FIRST_STEP", "1") != "0"


class FirstStep:
    def __init__(self, *, url: str, vid: str, goal: str, workdir: str, info, key: str, on_update,
                 transcript_only: bool = False, t0: float | None = None) -> None:
        self.url, self.vid, self.goal, self.workdir, self.info, self.key = url, vid, goal, workdir, info, key
        self.on_update = on_update
        self.transcript_only = transcript_only
        self.t0 = t0 if t0 is not None else time.time()
        self.goal_task: asyncio.Future | None = None  # builder sets it once the goal-match call is running
        self.checked: dict = {}  # link checks already done (shared with the full build's)
        self.video_info: dict | None = None  # the transcript info the draft is built from (claude_draft sets it)
        self.seg: dict | None = None
        self.need: set[int] = set()
        self.filled: dict[int, dict] = {}
        self.task: asyncio.Task | None = None
        self.result: dict | None = None  # the lock: {"adapted": {1: ...}, "step": s1, "notebook": ..., "seconds": ...}
        self.sent_at: float | None = None
        self._lock: asyncio.Future = asyncio.get_running_loop().create_future()
        self._reserve = None
        self._hooked = False  # segment() ran: the draft this build uses is the one we watch
        self.stale = False  # a second watch_transcript attempt started: its details are not the steps we watch
        self.closed = False  # the build ended (or was cancelled): nothing is sent any more
        self.sending = False  # on_update(step 1) has started: the learner has step 1, or is getting it
        self.app_wait = False  # an app-titled video: is it an app lesson or a code lesson? wait for every step's detail

    # ------------------------------------------------------------------ claude.watch_transcript hooks
    def segment(self, seg: dict) -> set[int]:
        """The segment call's (stripped) step list. -> the segment step numbers that form the lesson's step 1."""
        from .builder import normalize_draft

        if self._hooked:  # a second watch_transcript in the same build (an unusable step list was asked again)
            self.stale = True
            self.seg_latest, self.filled_latest = seg, {}  # what the lesson's other steps now are (upcoming())
            if self.task is None:
                self._settle(None)
                self._unreserve()
            return set()
        self._hooked = True
        steps = seg.get("steps") or []
        stubs = [{**copy.deepcopy(s), f"_o{i}": True} for i, s in enumerate(steps, 1)]
        try:  # merges keep every key of both steps, so step 1's _o<i> keys name the segment steps it is made of
            first = normalize_draft({"steps": stubs})["steps"][0]
        except (ValueError, KeyError, IndexError) as e:
            log.info("first step early: skipped (%s)", e)
            self._settle(None)
            return set()
        self.seg = seg
        self.need = {int(k[2:]) for k in first if isinstance(k, str) and k.startswith("_o") and k[2:].isdigit()}
        # app lesson or code lesson is decided on the whole lesson: for a video whose title names an app (AutoCAD,
        # Excel), step 1 waits until every step's detail is in, unless a step already shows code
        from . import app_lesson

        titles = {"lesson": {"title": seg.get("title") or ""}, "sources": [{"title": (self.video_info or {}).get("title") or ""}]}
        self.app_wait = app_lesson.work_app(titles) is not None
        if not self.app_wait:  # step 1's adapt call follows its detail at once: keep it a lane from now
            self._take_reserve()  # (an app-titled video waits for every detail: the lane is kept only once step 1 starts)
        return set(self.need)

    def _take_reserve(self) -> None:
        if self._reserve is not None or self.closed:
            return
        try:
            self._reserve = claude._sem().reserve()
            self._reserve.__enter__()
        except RuntimeError:  # no running loop (never in a build)
            self._reserve = None

    def detail(self, i: int, step: dict) -> None:
        """Segment step i is filled (the per-step call returned). Step 1 starts building once all its pieces are in."""
        if self.stale and not self.closed:
            getattr(self, "filled_latest", {})[i] = step
            return
        if self.seg is None or self.closed:
            return
        self.filled[i] = step  # also after step 1 started: the workspace's view of the other steps (upcoming())
        if self.task is not None or self._lock.done() or not self.need or not self.need <= set(self.filled):
            return
        if self.app_wait and len(self.filled) < len(self.seg.get("steps") or []):
            from . import app_lesson

            if not app_lesson.has_code({"steps": list(self.filled.values())}):
                return  # not known yet whether this is an app lesson: wait for the other steps
        self._take_reserve()
        self.task = asyncio.ensure_future(self._from_details())
        self.task.add_done_callback(_retrieve)

    # ------------------------------------------------------------------ the raw-draft path
    def start_from_draft(self, draft: dict) -> None:
        """A cached video draft (no model call to watch): build step 1 from it while the rest is adapted."""
        if self.task is not None or self._lock.done() or not draft.get("steps"):
            return
        self._draft_rest = copy.deepcopy(draft["steps"][1:])
        self.task = asyncio.ensure_future(self._run(copy.deepcopy(draft)))
        self.task.add_done_callback(_retrieve)

    # ------------------------------------------------------------------ what the full build waits for
    def lock_state(self) -> str:
        """"locked" (step 1 is built and final), "none" (it won't be built early) or "pending"."""
        if self._lock.done():
            return "locked" if self._lock.result() is not None else "none"
        return "pending"

    def building(self) -> bool:
        """Step 1 is being built early, or was: the full build should wait for its lock instead of adapting it."""
        return self.task is not None and (not self._lock.done() or self._lock.result() is not None)

    async def lock(self) -> dict | None:
        """Step 1's lock once it is built (None: it was not built early; the full build adapts it as before)."""
        if self.task is None and not self._lock.done():
            return None
        return await asyncio.shield(self._lock)

    async def delivered(self) -> None:
        """Wait until step 1's on_update has returned, so the full lesson never reaches the app before it."""
        if self.task is not None and not self.task.done():
            try:
                await asyncio.shield(self.task)
            except Exception as e:  # noqa: BLE001  the task logged it
                log.debug("first step task ended with %s", type(e).__name__)

    def close(self) -> None:
        """The build ended (returned, failed or was cancelled): step 1 is never sent after this."""
        self.closed = True
        if self.task is not None and not self.task.done():
            self.task.cancel()
        self._settle(None)
        self._unreserve()

    def upcoming(self, sent_steps: list[dict] | None = None) -> list[dict]:
        """The lesson's other steps as known right now (segment fields, plus file / checks / targets for those whose
        detail is in), for the workspace's starter files: they must not hold what a later step has the learner write.
        Rides in graph["build"]["upcomingSteps"], which no event to the app carries."""
        keep = ("title", "instructions", "file", "checks", "precision_checks", "targets", "common_mistakes")
        latest = getattr(self, "seg_latest", None)
        if latest is not None:  # a second step list replaced the first: its steps after the first
            filled = getattr(self, "filled_latest", {})
            rows = [(i, filled.get(i) or s) for i, s in enumerate(latest.get("steps") or [], 1) if i > 1]
        elif self.seg is not None:
            rows = [(i, self.filled.get(i) or s) for i, s in enumerate(self.seg.get("steps") or [], 1) if i not in self.need]
        else:
            rows = [(k, s) for k, s in enumerate(sent_steps or [], 2)]
        return [{"index": n, **{k: copy.deepcopy(st[k]) for k in keep if st.get(k)}} for n, (_i, st) in enumerate(rows, 2)]

    # ------------------------------------------------------------------ building step 1
    def _settle(self, value: dict | None) -> None:
        if not self._lock.done():
            self._lock.set_result(value)

    def _unreserve(self) -> None:
        r, self._reserve = self._reserve, None
        if r is not None:
            r.__exit__(None, None, None)

    async def _from_details(self) -> None:
        from . import builder, timing

        seg = self.seg or {}
        try:
            steps = [copy.deepcopy(self.filled.get(i) or s) for i, s in enumerate(seg.get("steps") or [], 1)]
            draft = builder.normalize_draft({"title": seg.get("title", ""), "libraries": seg.get("libraries", []), "steps": steps})
            info = self.video_info or {}
            timing.pin_starts(draft["steps"], info.get("transcript"), info.get("chapters"))  # as claude_draft does
            builder.rehome_explanations(draft["steps"])
        except Exception as e:  # noqa: BLE001  never leave the full build waiting for a lock
            log.warning("first step early failed (%s: %s); step 1 waits for the full build", type(e).__name__, str(e)[:200])
            self._settle(None)
            self._unreserve()
            return
        await self._run(draft)

    async def _run(self, draft: dict) -> None:
        """Build, validate and send step 1 of `draft` (every step; only step 1 is built, the rest is context)."""
        from . import builder, links
        from .notebook_steps import use_lesson_notebook
        from .schema import schema_errors
        from .venv_steps import use_lesson_venv

        claude.PRIORITY.set(True)  # this task's model calls: step 1's adapt pass and its retry
        try:
            s1, context = draft["steps"][0], draft["steps"][1:]
            draft1 = {"title": draft.get("title"), "libraries": draft.get("libraries") or [], "steps": [s1]}
            known_text = await builder._known_text(self.vid)
            bad = await builder._bad_urls([s1], known_text, self.checked)
            adapted: dict[int, dict] = {}
            graph, warnings, ok, adapt_model = await builder._adapt(draft1, self.goal, self.info, bad, partial=True,
                                                                    context=context, keep=adapted)
            if not ok or 1 not in adapted:
                log.info("first step early: adapt pass failed; step 1 waits for the full build")
                self._settle(None)
                return
            warnings = warnings + links.strip_bad_urls(graph["steps"], await builder._bad_urls(graph["steps"], known_text, self.checked))
            await builder.add_community_mistakes(graph, self.url)
            lesson = graph["lesson"]
            lesson["id"] = f"lesson-{self.key[:8]}"
            lesson["builtBy"] = "claude"
            lesson["workdir"] = self.workdir
            lesson["complete"] = False
            if self.transcript_only:
                lesson["transcriptOnly"] = True
            gt = self.goal_task
            if gt is not None and gt.done() and not gt.cancelled() and gt.exception() is None:
                lesson["goalMatch"] = gt.result()
            graph["sources"] = [{"id": "src1", "kind": "video", "title": draft.get("title") or "Tutorial", "url": self.url,
                                 "videoId": self.vid}]
            seconds = round(time.time() - self.t0, 1)
            graph["build"] = {"adapted": True, "firstStep": True, "model": {"video": "claude", "adapt": adapt_model},
                              "seconds": seconds, "workdir_metrics": sorted(self.info.metrics),
                              "workdir_fp": builder.workdir_fingerprint(self.workdir, self.info), "warnings": warnings}
            use_lesson_venv(graph)
            # a notebook lesson (and its notebook's name) is decided on every step known so far, not on step 1 alone
            use_lesson_notebook({"lesson": lesson, "sources": graph["sources"], "steps": graph["steps"] + copy.deepcopy(context)})
            errs = schema_errors(graph)
            if errs:
                log.warning("first step early: contract rejected step 1 (%s); it waits for the full build", "; ".join(errs[:3]))
                self._settle(None)
                return
        except asyncio.CancelledError:
            self._settle(None)
            raise
        except Exception as e:  # noqa: BLE001  a speed-up: the full build still builds step 1 the old way
            log.warning("first step early failed (%s: %s); step 1 waits for the full build", type(e).__name__, str(e)[:200])
            self._settle(None)
            return
        finally:
            self._unreserve()
        # lesson-wide choices step 1 was built with: the full build makes the same ones (builder._lock_first_step)
        self.result = {"adapted": {1: adapted[1]}, "step": copy.deepcopy(graph["steps"][0]),
                       "notebook": lesson.get("notebook"), "app": copy.deepcopy(lesson.get("app")),
                       "seconds": seconds, "adapt_model": adapt_model}
        self._settle(self.result)
        if self.closed:  # the build ended while step 1 was being built: it is never sent
            return
        log.info("first step ready in %.1fs (%s; %d more step(s) building)", seconds, graph["steps"][0].get("title"), len(context))
        builder._emit("first_steps", "1 step")
        if self.on_update is None:
            return
        graph["build"]["upcomingSteps"] = self.upcoming(getattr(self, "_draft_rest", None))  # for the starter files
        self.sending = True
        try:
            r = self.on_update(graph, False)
            if asyncio.iscoroutine(r):
                await r
            self.sent_at = time.time()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001  a UI callback must never break a build
            log.warning("on_update (first step) failed: %s", e)


def _retrieve(t: asyncio.Task) -> None:
    if not t.cancelled():
        t.exception()

"""Batched adapt (lane eng-build-speed-2): the adapt pass starts batch by batch as the step details land, instead of
after every detail call has returned, and each batch retries its own lint problems right away.

The Claude transcript path's adapt pass (builder._adapt) adapts the steps in batches of ADAPT_BATCH (3) in parallel,
lints the whole lesson and retries what lint rejects. Its first round used to wait for the whole draft; the last
batch's details land seconds after the first ones (recorded Nov 22: 7 detail calls over 12.5 s on 4 lanes), and the
retry round waited for every batch. BatchedAdapt watches the per-step detail calls (claude.DETAIL_HOOKS, next to
first_step) and, per batch:

1. Round 1 starts as soon as the batch's steps are final for the adapt prompt. A batch's steps are the lesson's
   steps after builder.normalize_draft; their structure (order, merged micro steps) comes from the segment call alone,
   and a step's adapt input (gemini.ADAPT_STEP_KEYS: title, instructions, file, code, run command, expected output,
   checks, targets) only from its own segment piece(s) and their details. Timing pins and explanations are not in the
   adapt prompt, so a neighbouring step's detail (which can move an explanation across a batch boundary:
   builder.rehome_explanations) never changes a batch's input; explanations are rehomed over the whole draft and
   attached afterwards (builder.assemble), exactly as before.
2. When the lesson-wide choice lint depends on is already fixed (no app in the titles, or step 1 went out with its
   app-or-code choice), the batch is linted at once (only problems its own results decide: "repeats the previous
   step's checks" only once that step's result is known; lesson-wide problems are left to the full build) and the
   steps lint rejects get one retry with their own problems as feedback, the same prompt and model (Sonnet, the
   escalation model) the full build's retry would use. A step keeps its round-1 result when the retry is no better.

The full build (builder._adapt_call, round 1) takes a batch's result over only when the batch's input is identical to
the one it would send (goal, folder summary, every ADAPT_STEP_KEYS field of the final draft's steps); any other batch
is sent as before. Then it lints the whole lesson and retries what is still wrong (problems across batches, lesson-wide
ones) exactly as before, and repair, link checks, venv / notebook, step 1's lock and the contract run unchanged. The
batches are the ones the full build would make (steps 2..N in threes when step 1 is built first, else 1..N), so round
1's Haiku calls are the same; a retry is per batch, so failing steps in two batches take two Sonnet calls instead of one.

Nothing streams to the app early: a batch is not final until the whole-lesson lint has run (and the session never edits
a step it has), so the full lesson just arrives sooner. Calls run without priority (step 1 and its reserved lane go
first) inside the 4-lane cap. A build that ends (returned, failed, cancelled) cancels every call nobody took over
(close()). Off with LESSON_BATCHED_ADAPT=0 (and with LESSON_FAST_FIRST_STEP=0, which restores the old serial build).
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import os

from . import claude, gemini

log = logging.getLogger("server.lesson")


def enabled() -> bool:
    return os.environ.get("LESSON_BATCHED_ADAPT", "1") != "0"


class BatchedAdapt:
    def __init__(self, *, goal: str, info, first=None, batch: int = 3, vid: str = "") -> None:
        self.goal, self.info, self.first, self.batch, self.vid = goal, info, first, max(1, batch), vid
        self.video_info: dict | None = None  # the transcript info (claude_draft sets it): the video's title
        self.adapted: dict[int, dict] = {}  # step index -> its adapt result so far (the "repeats step k-1" lint)
        self.checked: dict = {}  # link checks done for the early lint
        self.summary = info.summary_for_prompt()
        self.seg: dict | None = None
        self.origins: list[set[int]] = []  # normalized step k (0-based) -> the segment steps it is made of
        self.filled: dict[int, dict] = {}
        self.plan: list[list[int]] | None = None  # normalized step indices (1-based) per batch
        self.started: dict[str, asyncio.Task] = {}  # adapt input (key()) -> its round-1 call
        self.taken: set[str] = set()
        self.closed = False

    # ------------------------------------------------------------------ claude.watch_transcript hooks
    def segment(self, seg: dict) -> set[int]:
        from .builder import normalize_draft

        self._cancel()  # a second step list (an unusable first one was asked again): start over
        self.seg, self.filled, self.plan, self.origins = None, {}, None, []
        steps = seg.get("steps") or []
        stubs = [{**copy.deepcopy(s), f"_o{i}": True} for i, s in enumerate(steps, 1)]
        try:  # merges keep every key of both steps: each normalized step's _o<i> keys name its segment steps
            norm = normalize_draft({"steps": stubs})["steps"]
        except (ValueError, KeyError) as e:
            log.info("batched adapt: skipped (%s)", e)
            return set()
        self.seg = seg
        self.origins = [{int(k[2:]) for k in st if isinstance(k, str) and k.startswith("_o") and k[2:].isdigit()} for st in norm]
        return set()

    def detail(self, i: int, step: dict) -> None:
        if self.seg is None or self.closed:
            return
        self.filled[i] = step
        try:
            self._start_ready()
        except Exception as e:  # noqa: BLE001  a speed-up: the full build sends every batch itself
            log.warning("batched adapt: %s: %s", type(e).__name__, str(e)[:200])
            self._cancel()
            self.seg = None

    # ------------------------------------------------------------------ the full build's round 1
    def layout(self, steps: list[dict]) -> list[list[dict]] | None:
        """How builder._adapt_call should batch `steps` (round 1): the batches already started, then the rest in
        threes, in order. None: nothing started (the default batching)."""
        if not self.started or self.plan is None:
            return None
        by = {st.get("index"): st for st in steps}
        out, used = [], set()
        for grp in self.plan:
            if all(k in by for k in grp) and any(self._key(grp, steps) == p for p in self.started):
                out.append([by[k] for k in grp])
                used.update(grp)
        rest = [st for st in steps if st.get("index") not in used]
        out += [rest[j:j + self.batch] for j in range(0, len(rest), self.batch)]
        return sorted(out, key=lambda b: b[0].get("index", 0)) if out else None

    def take(self, prompt: str) -> asyncio.Task | None:
        """The started round-1 call whose input is exactly `prompt` (key()), once."""
        if prompt in self.taken:
            return None
        t = self.started.get(prompt)
        if t is not None:
            self.taken.add(prompt)
        return t

    def close(self) -> None:
        self.closed = True
        self._cancel()

    # ------------------------------------------------------------------ internals
    def _key(self, grp: list[int], steps: list[dict]) -> str:
        by = {st.get("index"): st for st in steps}
        return key(self.goal, [by[k] for k in grp], self.summary)

    def _cancel(self) -> None:
        for p, t in self.started.items():
            if p not in self.taken and not t.done():
                t.cancel()
        self.started, self.taken = {}, set()

    def _decide_plan(self) -> None:
        n = len(self.origins)
        everything = list(range(1, n + 1))
        if self.first is None:
            order = everything
        else:
            state = self.first.lock_state()
            if state == "none":
                order = everything
            else:  # locked, or still building: step 1 is its own (the full build adds it alone if the lock fails)
                order = everything[1:]
                if state == "pending" and not self._ready(order[:self.batch]):
                    return  # undecided until step 1's fate or the first batch is known
        self.plan = [order[j:j + self.batch] for j in range(0, len(order), self.batch)]

    def _ready(self, grp: list[int]) -> bool:
        return bool(grp) and all(o in self.filled for k in grp for o in self.origins[k - 1])

    def _start_ready(self) -> None:
        if self.plan is None:
            self._decide_plan()
            if self.plan is None:
                return
        ready = [g for g in self.plan if self._ready(g)]
        if not ready:
            return
        from .builder import normalize_draft

        seg = self.seg or {}
        steps = [copy.deepcopy(self.filled.get(i) or s) for i, s in enumerate(seg.get("steps") or [], 1)]
        draft = normalize_draft({"title": seg.get("title", ""), "libraries": seg.get("libraries", []), "steps": steps})
        for grp in ready:
            batch = [draft["steps"][k - 1] for k in grp]
            prompt = key(self.goal, batch, self.summary)
            if prompt in self.started:
                continue
            log.info("batched adapt: steps %s start (their details are in)", grp)
            t = asyncio.ensure_future(self._pipeline(list(grp), copy.deepcopy(draft)))
            t.add_done_callback(_retrieve)
            self.started[prompt] = t


    # ------------------------------------------------------------------ one batch: round 1, then its own retry
    def _app_choice(self):
        """The lesson's app-or-code choice when it is already fixed (lint depends on it), else ... (not yet)."""
        from . import app_lesson

        titles = {"lesson": {"title": (self.seg or {}).get("title") or ""},
                  "sources": [{"title": (self.video_info or {}).get("title") or ""}]}
        if app_lesson.work_app(titles) is None:
            return None  # no app in the titles: never an app lesson
        if self.first is not None and self.first.lock_state() == "locked":
            return (self.first.result or {}).get("app")  # step 1 went out with it
        return ...

    async def _pipeline(self, grp: list[int], draft: dict) -> dict:
        """Round 1 for steps `grp` of `draft` (the lesson's steps, the ones whose detail is not in yet as segment
        stubs), then, when the lesson-wide choices lint depends on are already fixed, one retry of the steps lint
        rejects, with only their own problems as feedback (exactly what the full build's retry would send them); a
        step keeps its round-1 result when the retry is no better. The full build lints the whole lesson again
        afterwards (problems across batches, lesson-wide ones) and retries as before."""
        from . import builder

        claude.PRIORITY.set(False)  # the rest of the lesson: never ahead of step 1
        batch = [draft["steps"][k - 1] for k in grp]
        r1 = await claude.adapt_checks(self.goal, copy.deepcopy(batch), self.summary, None)
        out = {st["index"]: st for st in (r1.get("steps") or []) if isinstance(st.get("index"), int) and st["index"] in grp}
        self._note(out)
        app = self._app_choice()
        if app is ... or not out:
            return r1
        try:
            known_text = await builder._known_text(self.vid)
            bad = await builder._bad_urls(batch, known_text, self.checked)
            problems = self._problems(draft, grp, out, app, bad)
            if not problems:
                return r1
            targets = [st for st in batch if st["index"] in problems]
            feedback = [p for k in sorted(problems) for p in problems[k]]
            log.info("batched adapt: steps %s: %d problems in %d step(s), retrying those", grp, len(feedback), len(targets))
            r2, _model = await builder._adapt_call(self.goal, {"steps": copy.deepcopy(targets)}, self.summary, feedback)
            new = {st["index"]: st for st in (r2.get("steps") or []) if isinstance(st.get("index"), int) and st["index"] in problems}
            after = self._problems(draft, grp, {**out, **new}, app, bad)
            for k, st in new.items():
                if len(after.get(k, [])) < len(problems[k]):
                    out[k] = st  # better: keep the retry's (else the round-1 result stays, as the full build does)
        except RuntimeError as e:  # the retry failed: round 1 stands; the full build retries what is still wrong
            log.warning("batched adapt: retry of steps %s failed: %s", grp, str(e)[:200])
        self._note(out)
        return {"steps": [out[k] for k in grp if k in out], "_early_retry": True}

    def _note(self, out: dict) -> None:
        self.adapted.update(copy.deepcopy(out))

    def _problems(self, draft: dict, grp: list[int], out: dict, app, bad: set[str]) -> dict[int, list[str]]:
        """Lint problems of steps `grp` that only their own results decide, by step. "Repeats the previous step's
        checks" counts only when the previous step's result is known; lesson-wide problems are the full build's."""
        from . import builder, links
        from .schema import lint

        known = {**self.adapted, **out}
        if self.first is not None and self.first.lock_state() == "locked":
            known.update((self.first.result or {}).get("adapted") or {})
        upto = max(grp)
        sub = {**draft, "steps": [st for st in draft["steps"] if st["index"] <= upto]}
        graph = builder.normalize_checks(builder.assemble(sub, self.goal, {"steps": [v for k, v in known.items() if k <= upto]}),
                                         self.info.metrics, app=app)
        found = lint(graph, self.info.metrics, set(self.info.files)) + links.url_problems(
            [st for st in graph["steps"] if st["index"] in grp], bad)
        by: dict[int, list[str]] = {}
        for p in found:
            m = builder._STEP_PROBLEM.match(p)
            if not m or int(m.group(1)) not in grp:
                continue
            k = int(m.group(1))
            if "repeat the previous step" in p and (k - 1) not in known:
                continue
            by.setdefault(k, []).append(p)
        return by


def key(goal: str, steps: list[dict], summary: str) -> str:
    """A round-1 adapt call's whole input (gemini.adapt_prompt without its random block ids)."""
    return json.dumps([goal, summary, [{k: s.get(k) for k in gemini.ADAPT_STEP_KEYS} for s in steps]], sort_keys=True)


def _retrieve(t: asyncio.Task) -> None:
    if not t.cancelled():
        t.exception()

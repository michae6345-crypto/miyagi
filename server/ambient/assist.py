"""Ambient help, engine side: "Set up this project" and "How do I" (AMBIENT-HELP.md sections 2 and 3). Payloads arrive
parsed by the contract (main.parse_command); replies go to the app that asked.

  setup.scan {path?, reqId?}        -> setup.report {scanning: true} at once, then the full report (no model call)
  setup.fix {tool, root?, reqId?}   -> setup.progress {tool, line} ..., {tool, done, ok, ...}, then a fresh setup.report
  help.ask {text, app?, reqId?}     -> help.steps {pending}, then the steps; re-sent as `current` / targets move
  help.nav {reqId?, to}             -> help.steps (next / back); close: no reply

Cost: help.ask is the only model call here: one Haiku call (coach client, guarded, via miyagi-cloud) on a sent ask,
inside the shared AMBIENT_CALLS_PER_HOUR budget (budget.BUDGET, with Explain). Watching the steps makes no model call.
Setup reads the project's own files on this Mac. setup.fix installs only a row of the project's own report, and only
because the learner pressed its Install (the row's press is the consent).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from server.workspace import project

from . import controls as _controls
from . import howto
from .budget import BUDGET, CallBudget

log = logging.getLogger("server.ambient")

COMMANDS = ("setup.scan", "setup.fix", "help.ask", "help.nav")
POLL_S = 1.0           # how often the help card's app is looked at while a card is open (AX only; each read walks
                       # the app's menus and window, up to controls.MAX_NODES elements)
IDLE_S = 300.0         # a help card with no progress for this long stops watching
CONFIRM_S = 180.0      # an off-list pip package: the same row's second Install within this long installs it
BUSY_RETRY_S = 30
LINE_MAX = 300

Reply = Callable[[str, dict], Awaitable[None]]


def _rid(p: Any) -> dict:
    rid = getattr(p, "reqId", None)
    return {"reqId": rid} if isinstance(rid, str) and rid else {}


def _public(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if not k.startswith("_")}


def fail_kind(e: BaseException) -> tuple[str, int | None]:
    """A coach error -> (AmbientFail, retryInS)."""
    kind = getattr(e, "kind", "")
    msg = str(e).lower()
    if kind in ("connection", "no_key", "offline"):
        return "offline", None
    if "529" in msg or "overloaded" in msg or " 503" in msg:
        return "busy", BUSY_RETRY_S
    return "failed", None


class Assist:
    def __init__(self, *, lesson_running: Callable[[], bool] = lambda: False,
                 read_controls: Callable[[str], Any] = _controls.read,
                 frontmost: Callable[[], str | None] = _controls.frontmost_app,
                 call: Any = None, budget: CallBudget = BUDGET,
                 scan: Callable[..., dict] = project.scan, fix: Callable[..., dict] = project.fix,
                 poll_s: float = POLL_S, idle_s: float = IDLE_S, clock: Callable[[], float] = time.monotonic):
        self.lesson_running, self.read_controls, self.frontmost = lesson_running, read_controls, frontmost
        self.call, self.budget, self.scan, self.fix = call, budget, scan, fix
        self.poll_s, self.idle_s, self.clock = poll_s, idle_s, clock
        self.last_root: str | None = None
        self.installing: set[str] = set()
        self.confirm: dict[str, tuple[str, float]] = {}  # tool -> (package, when the confirm was asked)
        self.help: dict | None = None
        self._watch: asyncio.Task | None = None
        self._asks = 0  # bumped by every help.ask: an older ask still waiting on the model never answers after a newer one

    async def handle(self, type_: str, p: Any, reply: Reply) -> None:
        if type_ == "setup.scan":
            await self.setup_scan(getattr(p, "path", None), reply, _rid(p))
        elif type_ == "setup.fix":
            await self.setup_fix(p.tool, getattr(p, "root", None), reply, _rid(p))
        elif type_ == "help.ask":
            await self.help_ask(p.text, getattr(p, "app", None), reply, _rid(p))
        elif type_ == "help.nav":
            await self.help_nav(p.to, getattr(p, "reqId", None), reply)

    # ------------------------------------------------------------------ setup
    async def _report(self, path: str | None, req: dict, *, quick: bool = False) -> dict:
        rep = await asyncio.to_thread(self.scan, path, req_id=req.get("reqId"), quick=quick)
        if rep.get("_path") and not rep.get("error"):
            self.last_root = rep["_path"]  # setup.fix without root installs here
        return rep

    async def setup_scan(self, path: str | None, reply: Reply, req: dict) -> None:
        quick = await self._report(path, req, quick=True)
        await reply("setup.report", _public(quick))
        if quick.get("error"):
            return
        await reply("setup.report", _public(await self._report(path, req)))

    async def setup_fix(self, tool: str, root: str | None, reply: Reply, req: dict) -> None:
        root = root or self.last_root
        if not root:
            await reply("setup.progress", {"tool": tool, "done": True, "ok": False,
                                           "error": "Check the project first, then press Install."})
            return
        if tool in self.installing:
            log.info("setup.fix %s already running; ignoring the repeat", tool)
            return
        confirmed = None
        if (asked := self.confirm.pop(tool, None)) and self.clock() - asked[1] <= CONFIRM_S:
            confirmed = asked[0]  # the row's second press: the learner checked the package
        self.installing.add(tool)
        loop = asyncio.get_running_loop()
        sends: list[asyncio.Future] = []

        def on_line(line: str) -> None:  # installer thread -> loop
            text = str(line).strip()[:LINE_MAX]
            if text:
                loop.call_soon_threadsafe(lambda: sends.append(asyncio.ensure_future(
                    self._safe(reply, "setup.progress", {"tool": tool, "line": text}))))
        try:
            await reply("setup.progress", {"tool": tool, "line": "Installing…"})
            res = await asyncio.to_thread(self.fix, tool, root, on_line=on_line, confirmed=confirmed)
        except Exception:  # noqa: BLE001 - the row always ends
            log.exception("setup.fix %s failed", tool)
            res = {"ok": False, "error": "Couldn't install that just now. Try again."}
        finally:
            self.installing.discard(tool)
        await asyncio.sleep(0)  # the last lines' callbacks have run: their sends go out before done
        await asyncio.gather(*sends, return_exceptions=True)
        if res.get("needs_confirm") and res.get("package"):
            self.confirm[tool] = (str(res["package"]), self.clock())
        done = {"tool": tool, "done": True, "ok": bool(res.get("ok"))}
        for k in ("error", "url", "version"):
            if res.get(k):
                done[k] = str(res[k])
        await reply("setup.progress", done)
        await reply("setup.report", _public(await self._report(root, req)))

    @staticmethod
    async def _safe(reply: Reply, type_: str, payload: dict) -> None:
        with contextlib.suppress(Exception):  # the app went away: nothing to tell
            await reply(type_, payload)

    # ------------------------------------------------------------------ how do I
    def _stop_help(self) -> None:
        if self._watch is not None and not self._watch.done():
            self._watch.cancel()
        self._watch = None
        self.help = None

    def _steps_payload(self, h: dict, **extra: Any) -> dict:
        return {**({"reqId": h["reqId"]} if h.get("reqId") else {}), "app": h["app"], "goal": h["goal"],
                "steps": howto.public(h["steps"]), "current": min(h["current"], max(0, len(h["steps"]) - 1)), **extra}

    async def help_ask(self, text: str, app: str | None, reply: Reply, req: dict) -> None:
        self._stop_help()  # a new ask replaces the one before
        self._asks += 1
        mine = self._asks
        app = (app or "").strip() or await asyncio.to_thread(self.frontmost) or ""
        base = {**req, "app": app, "goal": "", "steps": [], "current": 0}
        await reply("help.steps", {**base, "pending": True})
        if not app:
            await reply("help.steps", {**base, "error": "no_app"})
            return
        if (wait := self.budget.take()) is not None:
            await reply("help.steps", {**base, "error": "cap", "retryInS": wait})
            return
        ctrls = await asyncio.to_thread(self.read_controls, app)
        if ctrls is not None and getattr(ctrls, "app", ""):
            base["app"] = app = ctrls.app
        try:
            plan = await howto.plan_steps(text, app, ctrls, call=self.call)
        except Exception as e:  # noqa: BLE001 - CoachLLMError and anything else: a calm error, never a crash
            if mine != self._asks:
                return
            kind, retry = fail_kind(e)
            log.info("help.ask: no steps (%s: %s)", type(e).__name__, getattr(e, "kind", ""))
            await reply("help.steps", {**base, "error": kind, **({"retryInS": retry} if retry else {})})
            return
        if mine != self._asks:  # a newer ask replaced this one while the model answered
            return
        goal, steps = howto.resolve(plan, ctrls, app)
        if not steps:
            await reply("help.steps", {**base, "error": "failed"})
            return
        h = {"reqId": req.get("reqId"), "app": app, "goal": goal, "steps": steps, "current": 0, "controls": ctrls,
             "reply": reply, "moved_at": self.clock()}
        self.help = h
        await reply("help.steps", self._steps_payload(h))
        self._watch = asyncio.ensure_future(self._watch_loop(h))

    async def help_nav(self, to: str, rid: str | None, reply: Reply) -> None:
        h = self.help
        if to == "close":
            if h is not None and (not rid or rid == h.get("reqId")):
                self._stop_help()
            return
        if h is None or (rid and rid != h.get("reqId")):
            await reply("help.steps", {**({"reqId": rid} if rid else {}), "app": "", "goal": "", "steps": [], "current": 0,
                                       "error": "gone"})
            return
        h["moved_at"] = self.clock()
        if to == "back":
            h["current"] = max(0, h["current"] - 1)
            await reply("help.steps", self._steps_payload(h))
            return
        h["current"] += 1
        if h["current"] >= len(h["steps"]):
            await reply("help.steps", self._steps_payload(h, done=True))
            self._stop_help()
            return
        await reply("help.steps", self._steps_payload(h))

    async def _watch_loop(self, h: dict) -> None:
        """Watch the app while the card is open: move `current` and the targets as the screen changes. AX reads only;
        no model call. Ends on done, close, a new ask, a lesson starting, or IDLE_S without progress."""
        before = h.get("controls")
        try:
            while self.help is h:
                await asyncio.sleep(self.poll_s)
                if self.help is not h:
                    return
                if self.lesson_running() or self.clock() - h["moved_at"] > self.idle_s:
                    log.info("help card stops watching (%s)", "lesson" if self.lesson_running() else "idle")
                    self._stop_help()
                    return
                after = await asyncio.to_thread(self.read_controls, h["app"])
                if after is None or self.help is not h:
                    continue
                moved = howto.progress(h["steps"], h["current"], before, after)
                changed = howto.retarget(h["steps"], after, h["app"])
                before = after
                if moved != h["current"]:
                    h["current"], h["moved_at"] = moved, self.clock()
                    if moved >= len(h["steps"]):
                        await self._safe(h["reply"], "help.steps", self._steps_payload(h, done=True))
                        self.help, self._watch = None, None
                        return
                    changed = True
                if changed:
                    await self._safe(h["reply"], "help.steps", self._steps_payload(h))
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - watching is a nicety; the card's Next still works
            log.exception("help card watch failed")

    def stop(self) -> None:
        """A lesson started (or the engine stops): no help card is watched any more."""
        self._stop_help()

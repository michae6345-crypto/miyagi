"""The orchestrator's view of the other engine modules, behind one small interface.

LIVE (default): only the real `server.<module>` functions run. A module that is missing or
raises becomes a ModuleUnavailable, which the session turns into an `error` event; no
canned data ever reaches the learner.
DEMO=1: demo/cache/ files first, then the canned PINN stubs (checks stay real: the demo run is real).
ORCH_STUBS=all|lesson,coach,...: developer/test flag that forces stubs for those modules.

"""

from __future__ import annotations

import asyncio
import dataclasses
import importlib
import inspect
import json
import logging
import os
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from . import stubs
from .config import DEMO_CACHE, demo_mode
from .context import RunContext

log = logging.getLogger("orchestrator.modules")

MODULES = ("lesson", "checks", "coach", "finder", "diagrams")


async def _call(fn: Callable, *args, **kwargs) -> Any:
    out = fn(*args, **kwargs)
    if inspect.isawaitable(out):
        out = await out
    return out


def _to_dict(obj: Any) -> Any:
    if isinstance(obj, dict):
        return obj
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if hasattr(obj, "model_dump"):
        return obj.model_dump(exclude_none=True)
    return obj


def _accepts(fn: Callable, name: str) -> bool:
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False
    return name in params or any(p.kind is p.VAR_KEYWORD for p in params.values())


def _video_id(url: str) -> str | None:
    import re

    m = re.search(r"(?:v=|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{6,})", url or "")
    return m.group(1) if m else None


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


class ModuleUnavailable(RuntimeError):
    """A real module is missing or failed and stubs aren't allowed (live mode)."""


class Modules:
    def __init__(self, *, demo: bool | None = None, force_stubs: str | None = None):
        self.demo = demo_mode() if demo is None else demo
        forced = os.environ.get("ORCH_STUBS", "") if force_stubs is None else force_stubs
        forced_set = {m.strip() for m in forced.split(",") if m.strip()}
        if "all" in forced_set:
            forced_set = set(MODULES)
        self.forced = forced_set
        self.real: dict[str, Any] = {}
        self.import_errors: dict[str, str] = {}
        for name in MODULES:
            if name in forced_set:
                continue
            try:
                self.real[name] = importlib.import_module(f"server.{name}")
            except Exception as e:  # noqa: BLE001 - surfaced through describe() / errors
                self.import_errors[name] = f"{type(e).__name__}: {e}"
                log.warning("server.%s failed to import (%s)", name, e)

    # -- helpers
    def stubs_allowed(self, module: str) -> bool:
        return self.demo or module in self.forced

    # modules that run for real even with DEMO=1: checks (the demo run is real) and coach (E5 handles DEMO=1
    # itself: offline playbook cards instead of failing, e.g. the hero's lr_too_high card)
    DEMO_REAL = ("checks", "coach")

    def _real_fn(self, module: str, attr: str) -> Callable | None:
        if module in self.forced or (self.demo and module not in self.DEMO_REAL):
            return None
        mod = self.real.get(module)
        fn = getattr(mod, attr, None) if mod else None
        return fn if callable(fn) else None

    def describe(self) -> dict[str, str]:
        out = {}
        probes = {"lesson": "build_lesson", "checks": "evaluate_gate", "coach": "diagnose",
                  "finder": "search", "diagrams": "build"}
        for m, attr in probes.items():
            if self._real_fn(m, attr):
                out[m] = "real"
            elif self.demo:
                out[m] = "demo"
            elif m in self.forced:
                out[m] = "stub (ORCH_STUBS)"
            else:
                out[m] = "missing"
        return out

    def _missing(self, module: str, attr: str) -> ModuleUnavailable:
        why = self.import_errors.get(module)
        if why:
            return ModuleUnavailable(f"server.{module} failed to import ({why})")
        return ModuleUnavailable(f"server.{module}.{attr} isn't available yet")

    async def _run(self, module: str, attr: str, stub: Callable[[], Any], *args, **kwargs) -> Any:
        """Real function, else (only if allowed) the stub, else ModuleUnavailable."""
        fn = self._real_fn(module, attr)
        if fn is not None:
            try:
                return _to_dict(await _call(fn, *args, **kwargs))
            except Exception as e:
                if not self.stubs_allowed(module):
                    raise ModuleUnavailable(f"{module}.{attr} failed: {type(e).__name__}: {e}") from e
                log.exception("server.%s.%s failed; DEMO stub instead", module, attr)
        elif not self.stubs_allowed(module):
            raise self._missing(module, attr)
        return await _call(stub)

    def _cache(self, *parts: str) -> Any | None:
        if not self.demo:
            return None
        return _read_json(DEMO_CACHE.joinpath(*parts))

    # -- finder
    async def search(self, query: str) -> AsyncIterator[dict]:
        """Yields search.result payloads (each with "url") as they arrive."""
        if self.demo:
            cached = self._cache("search.json")
            if cached is None and (DEMO_CACHE / "search").is_dir():
                files = sorted((DEMO_CACHE / "search").glob("*.json"))
                cached = _read_json(files[0]) if files else None
            items = (cached.get("results", cached) if isinstance(cached, dict) else cached) if cached else None
            for r in items or await stubs.search(query):
                yield r
            return
        fn = self._real_fn("finder", "search")
        if fn is None:
            if self.stubs_allowed("finder"):
                for r in await stubs.search(query):
                    yield r
                return
            raise self._missing("finder", "search")
        if _accepts(fn, "on_result"):  # E7: rows arrive through on_result while the search runs
            from server.config import KEY_ENV, get_key

            queue: asyncio.Queue = asyncio.Queue()
            kwargs = {"api_keys": {k: get_key(k) for k in KEY_ENV}} if _accepts(fn, "api_keys") else {}

            async def on_result(row: Any) -> None:
                await queue.put(_to_dict(row))

            task = asyncio.ensure_future(_call(fn, query, on_result=on_result, **kwargs))
            seen: set = set()
            try:
                while True:
                    getter = asyncio.ensure_future(queue.get())
                    done, _ = await asyncio.wait({getter, task}, return_when=asyncio.FIRST_COMPLETED)
                    if getter in done:
                        row = getter.result()
                        if row.get("id") not in seen:
                            seen.add(row.get("id"))
                            yield row
                        continue
                    getter.cancel()
                    final = task.result()  # raises if the search failed
                    while not queue.empty():
                        row = queue.get_nowait()
                        if row.get("id") not in seen:
                            seen.add(row.get("id"))
                            yield row
                    for row in final or []:  # anything that only came back in the final list
                        row = _to_dict(row)
                        if row.get("id") not in seen:
                            seen.add(row.get("id"))
                            yield row
                    return
            except Exception as e:
                task.cancel()
                raise ModuleUnavailable(f"finder.search failed: {type(e).__name__}: {e}") from e
        try:
            out = fn(query)
            if hasattr(out, "__aiter__"):  # streaming finder
                async for r in out:
                    yield _to_dict(r)
                return
            if inspect.isawaitable(out):
                out = await out
            for r in out or []:
                yield _to_dict(r)
        except ModuleUnavailable:
            raise
        except Exception as e:
            raise ModuleUnavailable(f"finder.search failed: {type(e).__name__}: {e}") from e

    # -- lesson
    def _lesson_file(self) -> dict | None:
        """ORCH_LESSON (DEMO only)."""
        from .config import lesson_file

        p = lesson_file()
        if p is None:
            return None
        g = _read_json(p)
        if g is None:
            log.warning("ORCH_LESSON=%s could not be read", p)
        return g

    async def build_lesson(self, source_url: str, goal: str, workdir: str, on_progress: Any = None,
                           on_update: Any = None, video_meta: dict | None = None) -> dict:
        if self.demo:
            # ORCH_LESSON > a cached lesson for the PICKED video > lesson.json > the newest cache > stub
            if (g := self._lesson_file()) is not None:
                return g
            files = sorted((DEMO_CACHE / "lessons").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True) \
                if (DEMO_CACHE / "lessons").is_dir() else []
            vid = _video_id(source_url)
            if vid:
                for f in files:
                    g = _read_json(f)
                    if g and any(s.get("videoId") == vid or vid in (s.get("url") or "") for s in g.get("sources", [])):
                        return g
            cached = self._cache("lesson.json")
            if cached is None and files:
                cached = _read_json(files[0])
            if cached is not None:
                return cached
            return await stubs.build_lesson(source_url, goal, workdir)
        fn = self._real_fn("lesson", "build_lesson")
        kwargs = {}
        if fn is not None and _accepts(fn, "api_key"):
            from server.config import get_key

            kwargs["api_key"] = get_key("gemini")
        if fn is not None and on_progress is not None and _accepts(fn, "on_progress"):
            kwargs["on_progress"] = on_progress  # E2: stage ids for the launcher's progress line
        if fn is not None and video_meta and _accepts(fn, "video_meta"):
            kwargs["video_meta"] = video_meta  # S8's preflight (duration, chapters, firstHandsOn): part 1 skips the intro
        first_part = asyncio.Event()
        if fn is not None and on_update is not None and _accepts(fn, "on_update"):
            async def on_update_marked(graph: Any, complete: bool) -> None:  # E2: long videos build progressively
                first_part.set()
                await _call(on_update, graph, complete)

            kwargs["on_update"] = on_update_marked
        # The timeout only covers the wait for the FIRST steps: once part 1 of a long video has arrived the
        # learner is working, and later parts may take minutes (Karpathy: complete at ~400 s).
        timeout = float(os.environ.get("ORCH_BUILD_TIMEOUT_S", "300"))
        task = asyncio.ensure_future(self._run("lesson", "build_lesson",
                                               lambda: stubs.build_lesson(source_url, goal, workdir),
                                               source_url, goal, workdir, **kwargs))
        waiter = asyncio.ensure_future(first_part.wait())
        try:
            done, _ = await asyncio.wait({task, waiter}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
            if not done:
                task.cancel()
                raise ModuleUnavailable(f"building the lesson took over {timeout:.0f}s")
            return await task  # finished, or part 1 is in: no hard cut for the rest
        except asyncio.CancelledError:
            task.cancel()
            raise
        finally:
            waiter.cancel()

    # -- checks (always real unless forced: the demo run is a real run)
    def make_context(self, ctx: RunContext) -> Any:
        mod = self.real.get("checks")
        cls = getattr(mod, "RunContext", None) if mod else None
        if cls is None or cls is RunContext:
            return ctx
        params = inspect.signature(cls).parameters
        candidates = {"workdir": ctx.workdir, "last_run": ctx.last_run, "metrics": ctx.metrics,
                      "exit_code": ctx.exit_code, "output_tail": ctx.output_tail,
                      "command": ctx.command, "runs": ctx.runs, "running": ctx.running,
                      "screen": ctx.screen}
        return cls(**{k: v for k, v in candidates.items() if k in params})

    def evaluate_gate(self, step: dict, ctx: RunContext, screen: Any = None, precision_mode: bool = False) -> dict:
        """-> {passed, via: "checks"|"precision"|None, checks: [...], precision: [...]}"""
        ctx.screen = screen
        fn = self._real_fn("checks", "evaluate_gate")
        if fn is not None:
            try:
                gate = _to_dict(fn(step, self.make_context(ctx), screen=screen, precision_mode=precision_mode))
                gate["checks"] = [_to_dict(r) for r in gate.get("checks", [])]
                gate["precision"] = [_to_dict(r) for r in gate.get("precision", [])]
                return gate
            except Exception as e:
                if not self.stubs_allowed("checks"):
                    raise ModuleUnavailable(f"checks.evaluate_gate failed: {type(e).__name__}: {e}") from e
                log.exception("server.checks.evaluate_gate failed; DEMO stub evaluator instead")
        elif not self.stubs_allowed("checks"):
            raise self._missing("checks", "evaluate_gate")
        return stubs.evaluate_gate(step, ctx, screen=screen, precision_mode=precision_mode)

    def evaluate_step(self, step: dict, ctx: RunContext) -> list[dict]:
        return self.evaluate_gate(step, ctx, ctx.screen)["checks"]

    # -- coach
    def _public(self, card: Any) -> dict:
        card = _to_dict(card)
        pub = getattr(self.real.get("coach"), "public", None) if "coach" not in self.forced else None
        if callable(pub):
            try:
                return pub(card)
            except Exception:
                log.exception("coach.public failed")
        return {k: v for k, v in card.items() if not str(k).startswith("_")}

    def set_lesson(self, graph: dict) -> None:
        fn = self._real_fn("coach", "set_lesson")
        if fn is not None:
            try:
                fn(graph)
            except Exception:
                log.exception("coach.set_lesson failed")

    # -- coach: screen context, streaming targets, cancel, warm-up (E5's screen API)
    def screen_context(self, obs: Any, image: Any, cursor: tuple[float, float], **extra: Any) -> Any:
        """coach.ScreenContext from E6's observation + a screenshot, or None if the coach can't take one."""
        cls = getattr(self.real.get("coach"), "ScreenContext", None) if self._real_fn("coach", "diagnose") else None
        if cls is None or obs is None or image is None:
            return None
        try:
            names = {f.name for f in dataclasses.fields(cls)} if dataclasses.is_dataclass(cls) else set()
            return cls.from_observation(obs, image, cursor=cursor,
                                        **{k: v for k, v in extra.items() if k in names and v not in (None, "")})
        except Exception:
            log.exception("coach.ScreenContext failed; diagnosing without the screen")
            return None

    def cancel_coach(self) -> int:
        fn = self._real_fn("coach", "cancel")
        try:
            return int(fn() or 0) if fn else 0
        except Exception:
            log.exception("coach.cancel failed")
            return 0

    async def warm(self) -> None:
        fn = self._real_fn("coach", "warm")
        if fn is not None:
            try:
                await _call(fn)
            except Exception as e:  # warming is best-effort
                log.warning("coach.warm failed: %s", e)

    async def diagnose(self, step: dict, failed_checks: list[dict], metrics: dict, code_excerpt: str,
                       error_text: str = "", cursor: dict | None = None, screen: Any = None,
                       on_targets: Callable[[list[dict]], Any] | None = None) -> dict:
        """`metrics` is the raw series dict {name: [(step, value)]} (what coach.diagnose expects).
        Runs as the coach's cancellable "diagnose" task when the coach supports it."""
        cached = self._cache("coach", f"{step['id']}.json")
        if cached:
            return cached
        fn = self._real_fn("coach", "diagnose")
        kwargs: dict[str, Any] = {}
        if fn is not None:
            for name, val in (("error_text", error_text), ("cursor", cursor), ("screen", screen),
                              ("on_targets", on_targets)):
                if val and _accepts(fn, name):
                    kwargs[name] = val
        inflight = getattr(self.real.get("coach"), "inflight", None) if fn is not None else None
        if fn is not None and inflight is not None and hasattr(inflight, "start"):
            try:
                out = await inflight.start("diagnose", fn(step, failed_checks, metrics, code_excerpt, **kwargs))
            except asyncio.CancelledError:
                raise ModuleUnavailable("cancelled: the learner acted") from None
            except Exception as e:
                if not self.stubs_allowed("coach"):
                    raise ModuleUnavailable(f"coach.diagnose failed: {type(e).__name__}: {e}") from e
                out = await stubs.diagnose(step, failed_checks, metrics, code_excerpt)
            out = _to_dict(out)
            meta = out.get("_meta") if isinstance(out, dict) else None
            if meta:  # where the coach's time went (E5): latency_s, usage.first_text_s, cache reads, triage
                usage = meta.get("usage") or {}
                log.info("coach meta: latency_s=%s first_text_s=%s cache_read=%s triage=%s model=%s web=%s",
                         meta.get("latency_s"), usage.get("first_text_s"), usage.get("cache_read_input_tokens"),
                         (meta.get("triage") or {}).get("by"), meta.get("model"), len(meta.get("web_sources") or []))
            return self._public(out)
        out = await self._run("coach", "diagnose", lambda: stubs.diagnose(step, failed_checks, metrics, code_excerpt),
                              step, failed_checks, metrics, code_excerpt, **kwargs)
        return self._public(out)

    # -- preflight (S8): what the picked video is, how well it fits, what it needs, before building
    def _preflight_mod(self) -> Any:
        if self.demo or "lesson" in self.forced:
            return None
        try:
            return importlib.import_module("server.preflight")
        except Exception:  # noqa: BLE001
            return None

    def has_preflight(self) -> bool:
        return self._preflight_mod() is not None

    def prefetch_preflight(self, rows: list[dict], goal: str) -> None:
        mod = self._preflight_mod()
        if mod is not None:
            try:
                from server.config import KEY_ENV, get_key

                mod.prefetch(rows, goal, api_keys={k: get_key(k) for k in KEY_ENV})
            except Exception:  # noqa: BLE001 - a prefetch must never surface
                log.exception("preflight prefetch failed")

    async def preflight(self, url: str, goal: str, row: dict | None, on_late: Any) -> dict:
        from server.config import KEY_ENV, get_key

        mod = self._preflight_mod()
        return _to_dict(await mod.preflight(url, goal, row=row, on_late=on_late,
                                            api_keys={k: get_key(k) for k in KEY_ENV}))

    def preflight_card(self, res: dict) -> dict:
        return _to_dict(self._preflight_mod().preflight_card(res))

    # -- learning events -> Tiger (E3's server.checks.tiger: non-blocking queue + offline spool)
    def record(self, kind: str, lesson_id: str | None, step_id: str | None, video_t: float | None = None,
               payload: dict | None = None, source_id: str | None = None) -> None:
        if "checks" in self.forced:
            return
        try:
            tiger = importlib.import_module("server.checks.tiger")
        except Exception:  # noqa: BLE001 - no Tiger module: nothing to record
            return
        fn = getattr(tiger, "record_event", None)
        if fn is not None:
            fn(kind, lesson_id, step_id, video_t, payload, source_id=source_id)

    # -- voice (E5: ElevenLabs behind server.coach.voice; fills the existing `speak` event)
    def _voice(self) -> Any:
        if self.demo or "coach" in self.forced:
            return None
        return getattr(self.real.get("coach"), "voice", None)

    async def speak_event(self, kind: str, payload: dict) -> dict | None:
        """-> {audioUrl, text} or None (no key, failure: logged once by the coach)."""
        v = self._voice()
        fn = getattr(v, "speak_event", None) if v is not None else None
        if fn is None:
            return None
        try:
            return _to_dict(await _call(fn, kind, payload)) or None
        except Exception as e:  # voice must never break the lesson
            log.warning("voice.speak_event failed: %s", e)
            return None

    def voice_line(self, kind: str, payload: dict) -> str | None:
        v = self._voice()
        fn = getattr(v, "line_for", None) if v is not None else None
        try:
            return fn(kind, payload) if fn else None
        except Exception:  # noqa: BLE001
            return None

    async def prefetch_voice(self, lines: list[str]) -> None:
        v = self._voice()
        fn = getattr(v, "prefetch", None) if v is not None else None
        if fn is not None:
            try:
                await _call(fn, lines)
            except Exception as e:
                log.warning("voice.prefetch failed: %s", e)

    def has_do_it_for_me(self) -> bool:
        return self._real_fn("coach", "do_it_for_me") is not None

    async def do_it_for_me(self, step: dict, file: str, file_text: str, last_offtrack: dict | None) -> dict:
        """-> {file, unified_diff, summary, line, new_text, requires_confirmation}; ModuleUnavailable if no safe patch."""
        fn = self._real_fn("coach", "do_it_for_me")
        if fn is None:
            raise self._missing("coach", "do_it_for_me")
        try:
            return _to_dict(await _call(fn, step, file, file_text, last_offtrack))
        except Exception as e:
            raise ModuleUnavailable(f"{getattr(e, 'reason', None) or e}") from e

    async def explain(self, step: dict, question: str | None, context: dict) -> dict:
        kind = "answer" if question else "explain"
        cached = self._cache("cards", f"{step['id']}-{kind}.json")
        if cached:
            return cached
        out = await self._run("coach", "explain", lambda: stubs.explain(step, question, context),
                              step, question, context)
        return self._public(out)

    async def hint(self, step: dict, level: int, last_offtrack: dict | None = None) -> dict:
        cached = self._cache("cards", f"{step['id']}-hint{level}.json")
        if cached:
            return cached
        fn = self._real_fn("coach", "hint")
        kwargs = {"last_offtrack": last_offtrack} if fn is not None and _accepts(fn, "last_offtrack") else {}
        out = await self._run("coach", "hint", lambda: stubs.hint(step, level), step, level, **kwargs)
        return self._public(out)

    def propose_fix(self, diff: dict, file_text: str) -> str | None:
        """-> the full new file text for an offtrack diff, or None (then the learner fixes it by hand)."""
        fn = self._real_fn("coach", "apply_fix")
        if fn is not None:
            try:
                return _to_dict(fn(diff, file_text)).get("new_text")
            except Exception:
                log.exception("coach.apply_fix failed")
                return None
        return stubs.apply_fix(diff, file_text) if self.stubs_allowed("coach") else None

    # -- diagrams
    def has_diagrams(self) -> bool:
        return self._real_fn("diagrams", "build") is not None

    def clear_diagrams(self) -> None:
        fn = self._real_fn("diagrams", "clear_cache")
        if fn is not None:
            try:
                fn()
            except Exception:  # noqa: BLE001
                log.exception("diagrams.clear_cache failed")

    async def diagram(self, kind: str | None, step: dict | None, ctx: RunContext | None,
                      context: dict | None = None) -> dict:
        """S4: server.diagrams.build(step, context) -> {kind, caption, data, stepId}. `kind` is only a
        preference ("network" | "graph"); DEMO stubs draw network/gradients/heatmap."""
        stub_kind = kind or "network"
        cached = self._cache("diagrams", f"{stub_kind}.json")
        if cached:
            return cached
        ctx_in = dict(context or {})
        if kind in ("network", "graph"):
            ctx_in["kind"] = kind
        return await self._run("diagrams", "build", lambda: stubs.diagrams_build(stub_kind, step, ctx),
                               step, ctx_in)

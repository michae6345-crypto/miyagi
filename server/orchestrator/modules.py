"""The orchestrator's view of the other engine modules, behind one small interface.

Resolution per module (lesson, checks, coach, finder, diagrams):
  1. DEMO=1            -> demo/cache/ files first, then stubs (never a live API)
  2. ORCH_STUBS=all|lesson,coach,...  -> force the stub for those modules
  3. otherwise         -> the real function if `server.<module>` exports it, else the stub
A real function that raises is logged and falls back to the stub, so a flaky API
never kills the demo.
"""

from __future__ import annotations

import asyncio
import dataclasses
import importlib
import inspect
import json
import logging
import os
from collections.abc import Callable
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


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


class Modules:
    def __init__(self, *, demo: bool | None = None, force_stubs: str | None = None):
        self.demo = demo_mode() if demo is None else demo
        forced = os.environ.get("ORCH_STUBS", "") if force_stubs is None else force_stubs
        forced_set = {m.strip() for m in forced.split(",") if m.strip()}
        if "all" in forced_set:
            forced_set = set(MODULES)
        self.real: dict[str, Any] = {}
        for name in MODULES:
            if name in forced_set:
                continue
            try:
                self.real[name] = importlib.import_module(f"server.{name}")
            except Exception as e:  # pragma: no cover - import errors in sibling modules
                log.warning("server.%s failed to import (%s); using stub", name, e)

    # -- helpers
    def _real_fn(self, module: str, attr: str) -> Callable | None:
        if self.demo and module != "checks":
            return None
        mod = self.real.get(module)
        fn = getattr(mod, attr, None) if mod else None
        return fn if callable(fn) else None

    def describe(self) -> dict[str, str]:
        out = {}
        probes = {"lesson": "build_lesson", "checks": "evaluate_gate", "coach": "diagnose",
                  "finder": "search", "diagrams": "build"}
        for m, attr in probes.items():
            if self.demo and m != "checks":
                out[m] = "demo-cache"
            else:
                out[m] = "real" if self._real_fn(m, attr) else "stub"
        return out

    def _cache(self, *parts: str) -> Any | None:
        if not self.demo:
            return None
        return _read_json(DEMO_CACHE.joinpath(*parts))

    async def _try_real(self, module: str, attr: str, *args, **kwargs) -> tuple[bool, Any]:
        fn = self._real_fn(module, attr)
        if fn is None:
            return False, None
        try:
            return True, await _call(fn, *args, **kwargs)
        except Exception:
            log.exception("server.%s.%s failed; falling back to stub", module, attr)
            return False, None

    # -- finder
    async def search(self, query: str) -> list[dict]:
        cached = self._cache("search.json")
        if cached is None and self.demo and (DEMO_CACHE / "search").is_dir():
            files = sorted((DEMO_CACHE / "search").glob("*.json"))
            cached = _read_json(files[0]) if files else None
        if cached is not None:
            return list(cached.get("results", cached) if isinstance(cached, dict) else cached)
        ok, out = await self._try_real("finder", "search", query)
        if ok and out is not None:
            return [_to_dict(r) for r in out]
        lesson = self._lesson_file()
        if lesson:  # offer the ORCH_LESSON tutorial so the launcher matches the lesson that gets built
            kinds = {"video": "YouTube", "paper": "Paper", "notebook": "Notebook", "repo": "Code", "blog": "Article"}
            return [{"id": f"r{i + 1}", "kind": src.get("kind", "video"), "title": src.get("title", "Tutorial"),
                     "meta": kinds.get(src.get("kind", ""), "Source"), "score": round(0.95 - 0.1 * i, 2),
                     "reason": "Best match for your goal" if i == 0 else "Supporting source",
                     "url": src.get("url", "")}
                    for i, src in enumerate(lesson.get("sources", [])[:5])]
        return await stubs.search(query)

    # -- lesson
    def _lesson_file(self) -> dict | None:
        from .config import lesson_file

        p = lesson_file()
        if p is None:
            return None
        g = _read_json(p)
        if g is None:
            log.warning("ORCH_LESSON=%s could not be read", p)
        return g

    async def build_lesson(self, source_url: str, goal: str, workdir: str) -> dict:
        if self.demo:
            cached = self._cache("lesson.json")
            if cached is None and (DEMO_CACHE / "lessons").is_dir():
                files = sorted((DEMO_CACHE / "lessons").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
                cached = _read_json(files[0]) if files else None
            if cached is not None:
                return cached
            if (g := self._lesson_file()) is not None:
                return g
        fn = self._real_fn("lesson", "build_lesson")
        kwargs = {}
        if fn is not None and _accepts(fn, "api_key"):
            from server.config import get_key

            kwargs["api_key"] = get_key("gemini")
        timeout = float(os.environ.get("ORCH_BUILD_TIMEOUT_S", "90"))
        try:
            ok, out = await asyncio.wait_for(
                self._try_real("lesson", "build_lesson", source_url, goal, workdir, **kwargs), timeout)
        except asyncio.TimeoutError:
            log.warning("build_lesson took over %.0fs; using the fallback lesson", timeout)
            ok, out = False, None
        if ok and out:
            return _to_dict(out)
        if (g := self._lesson_file()) is not None:
            return g
        return await stubs.build_lesson(source_url, goal, workdir)

    # -- checks (always local: the demo is a real run)
    def make_context(self, ctx: RunContext) -> Any:
        mod = self.real.get("checks")
        cls = getattr(mod, "RunContext", None) if mod else None
        if cls is None or cls is RunContext:
            return ctx
        try:
            params = inspect.signature(cls).parameters
            candidates = {"workdir": ctx.workdir, "last_run": ctx.last_run, "metrics": ctx.metrics,
                          "exit_code": ctx.exit_code, "output_tail": ctx.output_tail,
                          "command": ctx.command, "runs": ctx.runs, "running": ctx.running,
                          "screen": ctx.screen}
            return cls(**{k: v for k, v in candidates.items() if k in params})
        except Exception:
            log.exception("could not build server.checks.RunContext; passing ours")
            return ctx

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
            except Exception:
                log.exception("server.checks.evaluate_gate failed; using stub evaluator")
        return stubs.evaluate_gate(step, ctx, screen=screen, precision_mode=precision_mode)

    def evaluate_step(self, step: dict, ctx: RunContext) -> list[dict]:
        return self.evaluate_gate(step, ctx, ctx.screen)["checks"]

    # -- coach
    def _public(self, card: Any) -> dict:
        card = _to_dict(card)
        pub = getattr(self.real.get("coach"), "public", None) if not self.demo else None
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

    async def diagnose(self, step: dict, failed_checks: list[dict], metrics: dict, code_excerpt: str,
                       error_text: str = "") -> dict:
        """`metrics` is the raw series dict {name: [(step, value)]} (what coach.diagnose expects)."""
        cached = self._cache("coach", f"{step['id']}.json")
        if cached:
            return cached
        fn = self._real_fn("coach", "diagnose")
        kwargs = {"error_text": error_text} if fn is not None and error_text and _accepts(fn, "error_text") else {}
        ok, out = await self._try_real("coach", "diagnose", step, failed_checks, metrics, code_excerpt, **kwargs)
        if ok and out:
            return self._public(out)
        return await stubs.diagnose(step, failed_checks, metrics, code_excerpt)

    async def explain(self, step: dict, question: str | None, context: dict) -> dict:
        kind = "answer" if question else "explain"
        cached = self._cache("cards", f"{step['id']}-{kind}.json")
        if cached:
            return cached
        ok, out = await self._try_real("coach", "explain", step, question, context)
        if ok and out:
            return self._public(out)
        return await stubs.explain(step, question, context)

    async def hint(self, step: dict, level: int, last_offtrack: dict | None = None) -> dict:
        cached = self._cache("cards", f"{step['id']}-hint{level}.json")
        if cached:
            return cached
        fn = self._real_fn("coach", "hint")
        kwargs = {"last_offtrack": last_offtrack} if fn is not None and _accepts(fn, "last_offtrack") else {}
        ok, out = await self._try_real("coach", "hint", step, level, **kwargs)
        if ok and out:
            return self._public(out)
        return stubs.hint(step, level)

    def propose_fix(self, diff: dict, file_text: str) -> str | None:
        """-> the full new file text for an offtrack diff, or None if it can't be placed."""
        fn = self._real_fn("coach", "apply_fix")
        if fn is not None:
            try:
                patch = _to_dict(fn(diff, file_text))
                return patch.get("new_text")
            except Exception:
                log.exception("coach.apply_fix failed; using the local fallback")
        return stubs.apply_fix(diff, file_text)

    # -- diagrams
    async def diagram(self, kind: str, step: dict | None, ctx: RunContext | None) -> dict:
        cached = self._cache("diagrams", f"{kind}.json")
        if cached:
            return cached
        ok, out = await self._try_real("diagrams", "build", kind, step=step, ctx=ctx)
        if ok and out:
            return _to_dict(out)
        return await stubs.diagrams_build(kind, step, ctx)

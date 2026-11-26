"""Drive the REAL coach (server.coach, live Opus/Haiku) on each case, exactly as the orchestrator calls it.

Per case:
  1. build the learner's folder + screen, OCR it with the engine's Vision path (screens.ocr)
  2. gate = server.checks.evaluate_gate(step, ctx, screen=obs.lines_by_app(), precision_mode=True)
     -> "fires" iff the gate fails (else the step would turn green and the coach never speaks)
  3. inputs built with the orchestrator's own code: LessonSession._code_excerpt (file on disk, else the
     screen's Code lines), target_location -> ScreenContext(file, line), cursor_context -> {x, y, under}
  4. coach.warm(), then coach.diagnose(..., screen=ScreenContext, cursor=..., on_targets=cb), timed
  5. level 3: coach.hint(step, 3, card) and coach.do_it_for_me(step, file, text, card) (what "Do it for me" calls)
  6. apply the patch (+ diff.command) the way the learner would and re-run the real check
     (react_check.mjs / nbclient / git), then re-render + OCR the after-screen and re-run the lesson gate

usage: REACT_ENV=<dir with react 18 + esbuild> .venv/bin/python -m evals.coach.run_coach [R1 P2 ...]
Writes evals/coach/results/<id>.json and evals/coach/cases/<id>/{screen.png,screen.json,obs.json}.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("DEMO", "0")  # never the canned playbook card

from server import coach  # noqa: E402
from server.checks import RunContext, evaluate_gate  # noqa: E402

from . import cases as C  # noqa: E402
from .screens import ocr  # noqa: E402

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
SHOTS = HERE / "cases"
log = logging.getLogger("evals.coach")


class ObsScreen:
    """The orchestrator's screen bridge surface the session needs, over one OCR'd observation."""

    active = True

    def __init__(self, obs):
        self.obs = obs

    def latest(self):
        return self.obs

    def lines(self, obs=None):
        return (obs or self.obs).lines_by_app()


def orchestrator_inputs(step: dict, workdir: Path, obs, cursor: tuple[float, float]) -> dict:
    """What session._coach would pass: code excerpt (+ which file), target_location, cursor context."""
    from server.orchestrator.inputs import text_under
    from server.orchestrator.modules import Modules
    from server.orchestrator.session import LessonSession
    from server.orchestrator.workspace import target_location

    async def _emit(*_a, **_k):
        return None

    s = LessonSession(_emit, Modules(demo=False, force_stubs="all"), screen=ObsScreen(obs))
    s.workdir = str(workdir)
    s.last_obs = obs
    code, file = s._code_excerpt(step)
    loc = target_location(workdir, step)
    cur = {"x": round(cursor[0], 1), "y": round(cursor[1], 1)}
    if (u := text_under(obs, *cursor)):
        cur["under"] = u
    return {"code": code, "code_from": file or "screen OCR (Code)", "loc": loc, "cursor": cur}


def gate_for(step: dict, workdir: Path, obs) -> dict:
    ctx = RunContext(workdir=str(workdir), screen=obs.lines_by_app())
    g = evaluate_gate(step, ctx, screen=obs.lines_by_app(), precision_mode=True)
    screen_failed = [r for r in g["checks"] if r["status"] == "fail"]
    failed = list(screen_failed)
    if not g["passed"]:  # session.evaluate: shown checks first, then the other list's failures
        seen = {r["checkId"] for r in failed}
        failed += [r for r in g["precision"] if r["status"] == "fail" and r["checkId"] not in seen]
    return {"passed": g["passed"], "via": g["via"], "checks": g["checks"], "precision": g["precision"], "failed": failed,
            "screen_failed": screen_failed, "passed_screen_only": not screen_failed and bool(g["checks"])}


def changed_lines(unified: str) -> int:
    return sum(1 for ln in (unified or "").splitlines() if ln[:1] in "+-" and not ln.startswith(("+++", "---")))


def expected_rects(built, rx: str) -> list[tuple]:
    """Where the right line(s) were drawn (editor / terminal / notebook rows matching the case's target)."""
    return [d.rect for d in built.screen.drawn if d.kind in ("editor", "terminal", "output", "browser") and re.search(rx, d.text, re.M)]


def _on_line(r: dict, e: tuple) -> bool:
    cy = r["y"] + r["h"] / 2
    ex, ey, ew, eh = e
    return ey - 3 <= cy <= ey + eh + 3 and r["x"] < ex + ew + 40 and r["x"] + r["w"] > ex - 40


def target_hits(card: dict, rects: list[tuple]) -> dict:
    """A target is right when its box sits on the offending line (OCR may split a line into several boxes)."""
    ts = card.get("targets") or []
    hits = [i for i, t in enumerate(ts) if any(_on_line(t["rect"], e) for e in rects)]
    return {"n": len(ts), "any": bool(hits), "first": bool(hits and hits[0] == 0), "texts": [t.get("text", "")[:80] for t in ts],
            "labels": [t.get("label") for t in ts]}


async def run_case(case: C.Case, work: Path) -> dict:
    from PIL import Image

    out: dict = {"id": case.id, "topic": case.topic, "step": case.step, "mistake": case.mistake, "truth": case.truth}
    built = C.build(case, work / case.id)
    shot = SHOTS / case.id / "screen.png"
    built.screen.save(shot)
    obs = ocr(shot)
    (shot.parent / "obs.json").write_text(json.dumps(obs.to_dict(), indent=1, ensure_ascii=False))
    out["ocr"] = {"blocks": len(obs.blocks), "ms": round(obs.ocr_ms), "lines_by_app": {k: len(v) for k, v in obs.lines_by_app().items()}}
    out["cursor"] = {"xy": built.cursor, "on": built.cursor_text}
    if built.extra:
        out["before_check"] = built.extra.get("react_check") or built.extra.get("cells")

    graph = case.graph()
    step = case.step_dict()
    gate = gate_for(step, built.workdir, obs)
    out["gate_before"] = {"passed": gate["passed"], "via": gate["via"], "passed_screen_only": gate["passed_screen_only"],
                          "checks": [f"{r['checkId']} {r['status']}: {r.get('detail', '')}" for r in gate["checks"]],
                          "precision": [f"{r['checkId']} {r['status']}: {r.get('detail', '')}" for r in gate["precision"]]}
    out["fires"] = not gate["passed"]  # what the orchestrator does (precision mode: the lesson folder exists)
    out["fires_screen_only"] = not gate["passed_screen_only"]
    failed = gate["failed"]
    if gate["passed"]:  # the step would turn green and the coach never speaks: diagnose anyway (forced) with
        failed = gate["screen_failed"] or [r for r in gate["precision"] if r["status"] == "fail"]  # what does catch it
        out["forced"] = True

    inp = orchestrator_inputs(step, built.workdir, obs, built.cursor)
    out["inputs"] = {"code_from": inp["code_from"], "code_chars": len(inp["code"]), "target_location": [str(inp["loc"][0]), inp["loc"][1]] if inp["loc"] else None,
                     "cursor_under": (inp["cursor"].get("under") or {}).get("text")}
    by_id = {c["id"]: c for c in (step.get("checks") or []) + (step.get("precision_checks") or [])}
    failed_checks = [{**by_id.get(r.get("checkId"), {}), **r} for r in failed]

    image = Image.open(shot).convert("RGB")
    extra = {"file": str(inp["loc"][0]), "line": inp["loc"][1]} if inp["loc"] else {}
    screen = coach.ScreenContext.from_observation(obs, image, cursor=built.cursor, **extra)

    coach.set_lesson(graph)
    t_w = time.perf_counter()
    try:
        await coach.warm()
    except Exception as e:  # noqa: BLE001
        log.warning("warm failed: %s", e)
    out["warm_s"] = round(time.perf_counter() - t_w, 2)

    marks: dict = {}
    t0 = time.perf_counter()

    def on_targets(t):
        marks.setdefault("targets_s", round(time.perf_counter() - t0, 2))

    try:
        card = await coach.diagnose(step, failed_checks, {}, inp["code"], error_text="", cursor=inp["cursor"],
                                    screen=screen, on_targets=on_targets)
        out["card_s"] = round(time.perf_counter() - t0, 2)
        out["targets_s"] = marks.get("targets_s")
    except coach.CoachUnavailable as e:
        out["card_s"] = round(time.perf_counter() - t0, 2)
        out["error"] = f"CoachUnavailable: {e.reason}"
        return out
    meta = card.get("_meta", {})
    out["card"] = coach.public(card)
    out["meta"] = {"route": meta.get("route"), "triage": meta.get("triage"), "model": meta.get("model"), "latency_s": meta.get("latency_s"),
                   "playbook_id": meta.get("playbook_id"), "web_sources": [s.get("url") for s in meta.get("web_sources") or []],
                   "usage": meta.get("usage")}
    text = f"{card.get('title', '')}. {card.get('body', '')}"
    out["diagnosis_auto"] = all(re.search(rx, text, re.I) for rx in case.cause_rx)
    out["targets"] = target_hits(card, expected_rects(built, case.target_rx))

    # ---- level 3: the exact fix + "Do it for me"
    l3 = coach.hint(step, 3, card)
    out["hint3"] = {"title": l3.get("title"), "diff": l3.get("diff")}
    diff = card.get("diff") or {}
    real_file = built.file
    out["orchestrator_resolves_file"] = bool(diff.get("file")) and (built.workdir / diff["file"]).is_file()
    patch, new_text = None, None
    if diff.get("expected") or not diff.get("command"):
        t1 = time.perf_counter()
        try:
            p = await coach.do_it_for_me(step, Path(real_file).name, built.file_text, card)
            patch = {k: v for k, v in p.items() if k != "new_text"}
            patch["s"] = round(time.perf_counter() - t1, 2)
            patch["changed_lines"] = changed_lines(p.get("unified_diff", ""))
            new_text = p.get("new_text")
        except coach.CoachUnavailable as e:
            patch = {"error": e.reason, "s": round(time.perf_counter() - t1, 2)}
    out["patch"] = patch
    command = diff.get("command") or (patch or {}).get("command")  # do_it_for_me may return a command fix

    # ---- apply + re-run the real check
    if case.topic == "react":
        check = C.react_check(new_text, built.workdir, case.step) if new_text else {"ok": False, "error": "no patch"}
    elif case.topic == "pandas":
        check = C.pandas_check(case, new_text, built.workdir) if new_text else {"ok": False, "error": "no patch"}
    else:
        with tempfile.TemporaryDirectory() as td:
            check = C.git_check(case, built, new_text, command, Path(td))
    out["check_after"] = {k: v for k, v in check.items() if k not in ("cells",)}

    after = C.after_screen(case, built, new_text, check)
    ashot = work / case.id / "after.png"
    after.save(ashot)
    aobs = ocr(ashot)
    ag = gate_for(step, built.workdir, aobs)
    out["gate_after"] = {"passed": ag["passed"], "via": ag["via"], "failed": [f"{r['checkId']} {r['label']}: {r.get('detail', '')}" for r in ag["failed"]]}
    return out


async def main(ids: list[str]) -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    RESULTS.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="coach-eval-"))
    for case in [C.BY_ID[i] for i in ids] if ids else C.CASES:
        print(f"=== {case.id} ({case.topic} {case.step}): {case.mistake}", flush=True)
        try:
            res = await run_case(case, work)
        except Exception as e:  # noqa: BLE001
            log.exception("case %s crashed", case.id)
            res = {"id": case.id, "crash": f"{type(e).__name__}: {e}"}
        (RESULTS / f"{case.id}.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str))
        c = res.get("card") or {}
        print(f"  fires={res.get('fires')} forced={res.get('forced', False)} route={((res.get('meta') or {}).get('triage') or {}).get('route')} "
              f"card={res.get('card_s')}s targets={res.get('targets_s')}s | {c.get('title')!r}\n  body: {c.get('body')!r}\n"
              f"  diff: {c.get('diff')}\n  targets: {res.get('targets')}\n  patch: {(res.get('patch') or {}).get('summary') or (res.get('patch') or {}).get('error')} "
              f"({(res.get('patch') or {}).get('changed_lines')} lines)\n  check_after: ok={(res.get('check_after') or {}).get('ok')} "
              f"{(res.get('check_after') or {}).get('why') or (res.get('check_after') or {}).get('error') or ''}\n"
              f"  gate_after: {res.get('gate_after')}\n  {res.get('error') or res.get('crash') or ''}", flush=True)
    print(f"work dir: {work}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))

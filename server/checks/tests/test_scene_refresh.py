"""Blender scene dumps kept fresh before a check reads them (server/checks/scene_refresh.py, Nov 24). Everything
Blender-side is a fake: no Blender, no bridge, no network."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from server.checks import evaluator, scene_refresh
from server.checks.evaluator import RunContext

DUMP = {"dump": "dump_scene.py 1", "blender": "5.3.0", "file": "mug.blend", "is_dirty": False,
        "scene": {"name": "Scene", "unit_system": "METRIC", "frame_start": 1, "frame_end": 250, "fps": 24},
        "objects": [{"name": "Müg", "type": "MESH", "location": [0.0, 0.0, 0.0],
                     "modifiers": [{"name": "Subdivision", "type": "SUBSURF", "levels": 2, "render_levels": 2}]}]}


class Clock:
    def __init__(self, t: float = 100.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


class Recorder:
    """A live or headless stand-in that records its calls and returns `result`."""

    def __init__(self, result=None, write: str | None = None):
        self.calls: list[tuple] = []
        self.result = result
        self.write = write

    def __call__(self, *args):
        self.calls.append(args)
        if self.write is not None:  # a headless dump writes the json, as dump_blend does
            Path(args[1]).write_text(self.write, encoding="utf-8")
        return self.result


@pytest.fixture(autouse=True)
def clean_state():
    scene_refresh.enable(False)
    scene_refresh.reset()
    yield
    scene_refresh.enable(False)
    scene_refresh.reset()


def _age(path: Path, seconds_ago: float) -> None:
    t = path.stat().st_mtime - seconds_ago
    os.utime(path, (t, t))


def test_disabled_by_default_and_calls_nothing(tmp_path):
    assert scene_refresh.enabled() is False
    live, headless = Recorder(DUMP), Recorder({})
    (tmp_path / "mug.blend").write_text("blend")
    assert scene_refresh.refresh(str(tmp_path / "mug.scene.json"), live=live, headless=headless) == "off"
    assert live.calls == [] and headless.calls == []
    assert not (tmp_path / "mug.scene.json").exists()


def test_blend_for():
    assert scene_refresh.blend_for("/x/mug.scene.json") == Path("/x/mug.blend")
    assert scene_refresh.blend_for("/x/My Donut.Scene.JSON") == Path("/x/My Donut.blend")


def test_live_writes_the_dump_skips_unchanged_text_and_asks_once_a_second(tmp_path):
    scene_refresh.enable()
    js = tmp_path / "mug.scene.json"
    clock, live, headless = Clock(), Recorder(DUMP), Recorder({})
    assert scene_refresh.refresh(str(js), live=live, headless=headless, clock=clock) == "live"
    want = json.dumps(DUMP, indent=1, ensure_ascii=False) + "\n"
    assert js.read_text(encoding="utf-8") == want and "Müg" in want  # non-ASCII kept, key order kept
    assert live.calls == [(str(tmp_path / "mug.blend"),)]
    # within the second: the bridge is not asked again, the last answer stands
    clock.t += 0.5
    assert scene_refresh.refresh(str(js), live=live, headless=headless, clock=clock) == "live"
    assert len(live.calls) == 1
    # a second on, the same scene: asked again, the file is not rewritten
    _age(js, 30)
    before = js.stat().st_mtime
    clock.t += 0.6
    assert scene_refresh.refresh(str(js), live=live, headless=headless, clock=clock) == "live"
    assert len(live.calls) == 2 and js.stat().st_mtime == before
    # the scene changed: written
    live.result = {**DUMP, "is_dirty": True}
    clock.t += 1.0
    assert scene_refresh.refresh(str(js), live=live, headless=headless, clock=clock) == "live"
    assert '"is_dirty": true' in js.read_text(encoding="utf-8")
    assert headless.calls == []
    assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]  # no temp file left behind


def test_live_throttle_is_per_file(tmp_path):
    scene_refresh.enable()
    clock, live = Clock(), Recorder(DUMP)
    for name in ("mug.scene.json", "donut.scene.json"):
        assert scene_refresh.refresh(str(tmp_path / name), live=live, headless=Recorder(), clock=clock) == "live"
    assert [c[0] for c in live.calls] == [str(tmp_path / "mug.blend"), str(tmp_path / "donut.blend")]


def test_a_dump_with_the_wrong_tag_is_not_written(tmp_path):
    scene_refresh.enable()
    js = tmp_path / "mug.scene.json"
    assert scene_refresh.refresh(str(js), live=Recorder({"dump": "other 2"}), headless=Recorder(), clock=Clock()) == "fresh"
    assert not js.exists()


def test_headless_runs_when_the_blend_is_newer_at_most_every_10s(tmp_path):
    scene_refresh.enable()
    blend, js = tmp_path / "mug.blend", tmp_path / "mug.scene.json"
    blend.write_text("blend")
    js.write_text("{}\n")
    _age(js, 60)  # saved after the last dump
    clock, live = Clock(), Recorder(None)
    headless = Recorder(DUMP)
    assert scene_refresh.refresh(str(js), live=live, headless=headless, clock=clock) == "headless"
    assert headless.calls == [(str(blend), str(js))]
    # still stale (the stand-in wrote nothing) but within 10 s: no second background Blender
    clock.t += 5
    assert scene_refresh.refresh(str(js), live=live, headless=headless, clock=clock) == "fresh"
    assert len(headless.calls) == 1
    clock.t += 5
    assert scene_refresh.refresh(str(js), live=live, headless=headless, clock=clock) == "headless"
    assert len(headless.calls) == 2


def test_headless_when_there_is_no_dump_yet_and_none_when_it_fails(tmp_path):
    scene_refresh.enable()
    (tmp_path / "mug.blend").write_text("blend")
    js = tmp_path / "mug.scene.json"
    headless = Recorder(None)
    assert scene_refresh.refresh(str(js), live=Recorder(None), headless=headless, clock=Clock()) == "none"
    assert headless.calls == [(str(tmp_path / "mug.blend"), str(js))]


def test_a_fresh_dump_or_no_blend_needs_nothing(tmp_path):
    scene_refresh.enable()
    blend, js = tmp_path / "mug.blend", tmp_path / "mug.scene.json"
    js.write_text(scene_refresh.to_text(DUMP), encoding="utf-8")
    headless = Recorder(DUMP)
    assert scene_refresh.refresh(str(js), live=Recorder(None), headless=headless, clock=Clock()) == "fresh"  # no .blend
    blend.write_text("blend")
    _age(blend, 60)  # the dump is newer than the save
    assert scene_refresh.refresh(str(js), live=Recorder(None), headless=headless, clock=Clock(200)) == "fresh"
    assert headless.calls == []


def test_an_empty_dump_newer_than_the_blend_is_still_dumped(tmp_path):
    """Lesson mode makes the step's file (mug.scene.json) empty with touch before the step starts, after mug.blend was
    saved: that file is newer than the .blend but holds no scene, so the background dump still runs, once."""
    scene_refresh.enable()
    blend, js = tmp_path / "mug.blend", tmp_path / "mug.scene.json"
    blend.write_text("blend")
    _age(blend, 60)
    js.touch()
    clock, live = Clock(), Recorder(None)
    headless = Recorder(DUMP, write=scene_refresh.to_text(DUMP))
    assert scene_refresh.refresh(str(js), live=live, headless=headless, clock=clock) == "headless"
    assert headless.calls == [(str(blend), str(js))]
    # the dump is on disk now and newer than the .blend: not stuck, and no second background Blender
    clock.t += 30
    assert scene_refresh.refresh(str(js), live=live, headless=headless, clock=clock) == "fresh"
    assert len(headless.calls) == 1


def test_an_empty_blend_is_no_blend(tmp_path):
    """Lesson mode makes a step's file with touch before the step starts: a 0-byte donut.blend is no saved scene, so no
    background Blender is started for it."""
    scene_refresh.enable()
    blend, js = tmp_path / "mug.blend", tmp_path / "mug.scene.json"
    blend.touch()
    headless = Recorder(DUMP)
    assert scene_refresh.refresh(str(js), live=Recorder(None), headless=headless, clock=Clock()) == "fresh"
    assert headless.calls == []


def test_a_failed_dump_waits_for_the_next_save(tmp_path):
    """A broken .blend that stays newer than the dump is dumped once, not again every 10 s; saving it again (a new
    mtime) makes it run again."""
    scene_refresh.enable()
    blend, js = tmp_path / "mug.blend", tmp_path / "mug.scene.json"
    blend.write_text("broken")
    clock, live, headless = Clock(), Recorder(None), Recorder(None)
    assert scene_refresh.refresh(str(js), live=live, headless=headless, clock=clock) == "none"
    assert len(headless.calls) == 1
    clock.t += 60  # long past the 10 s throttle, same file: no second background Blender
    assert scene_refresh.refresh(str(js), live=live, headless=headless, clock=clock) == "fresh"
    assert len(headless.calls) == 1
    t = blend.stat().st_mtime + 5  # the learner saves again
    os.utime(blend, (t, t))
    assert scene_refresh.refresh(str(js), live=live, headless=headless, clock=clock) == "none"
    assert len(headless.calls) == 2
    # a new save within 10 s of the last try still waits for the throttle
    t += 5
    os.utime(blend, (t, t))
    clock.t += 3
    assert scene_refresh.refresh(str(js), live=live, headless=headless, clock=clock) == "fresh"
    assert len(headless.calls) == 2
    clock.t += 10
    headless.result = DUMP
    assert scene_refresh.refresh(str(js), live=live, headless=headless, clock=clock) == "headless"
    assert len(headless.calls) == 3


@pytest.mark.parametrize("text", ["", "{}\n", '{"dump": "other 2"}\n', "not json"])
def test_a_file_that_is_not_a_dump_counts_as_missing(tmp_path, text):
    scene_refresh.enable()
    blend, js = tmp_path / "mug.blend", tmp_path / "mug.scene.json"
    blend.write_text("blend")
    _age(blend, 60)
    js.write_text(text, encoding="utf-8")
    assert not scene_refresh.is_dump(str(js))
    headless = Recorder(None)
    assert scene_refresh.refresh(str(js), live=Recorder(None), headless=headless, clock=Clock()) == "none"
    assert headless.calls == [(str(blend), str(js))]


def test_is_dump(tmp_path):
    js = tmp_path / "mug.scene.json"
    js.write_text(scene_refresh.to_text(DUMP), encoding="utf-8")
    assert scene_refresh.is_dump(str(js)) is True
    assert scene_refresh.is_dump(str(tmp_path / "gone.scene.json")) is False


def test_never_raises(tmp_path):
    scene_refresh.enable()
    (tmp_path / "mug.blend").write_text("blend")

    def boom(*_a):
        raise RuntimeError("bridge down")

    assert scene_refresh.refresh(str(tmp_path / "mug.scene.json"), live=boom, headless=boom, clock=Clock()) == "none"
    # a folder that does not exist: nothing to write, nothing raised
    assert scene_refresh.refresh(str(tmp_path / "gone" / "mug.scene.json"), live=Recorder(DUMP),
                                 headless=boom, clock=Clock()) == "none"


def test_default_sources_are_lazy_and_optional(tmp_path, monkeypatch):
    """Before the bridge and dumper lanes merge (or with them stubbed out), refresh finds nothing and says so."""
    scene_refresh.enable()
    monkeypatch.setattr(scene_refresh, "_default_live", lambda: None)
    monkeypatch.setattr(scene_refresh, "_default_headless", lambda: None)
    js = tmp_path / "mug.scene.json"
    assert scene_refresh.refresh(str(js), clock=Clock()) == "fresh"
    (tmp_path / "mug.blend").write_text("blend")
    assert scene_refresh.refresh(str(js), clock=Clock()) == "none"


# ------------------------------------------------------------------ the evaluator hook

def _calls(monkeypatch, content: str | None = None) -> list[str]:
    seen: list[str] = []

    def fake(path, **_kw):
        seen.append(path)
        if content is not None:  # the refresh writes the dump: the check must read it afterwards
            Path(path).write_text(content, encoding="utf-8")
        return "live"

    monkeypatch.setattr(scene_refresh, "refresh", fake)
    return seen


def test_file_contains_refreshes_a_scene_dump_once_before_reading(tmp_path, monkeypatch):
    seen = _calls(monkeypatch, json.dumps(DUMP, indent=1) + "\n")
    check = {"id": "c1", "type": "file_contains", "label": "Subsurf", "file": "mug.scene.json",
             "pattern": r'"type":\s*"SUBSURF"'}
    res = evaluator.evaluate_check(check, RunContext(workdir=str(tmp_path)))
    assert seen == [str(tmp_path / "mug.scene.json")]
    assert os.path.isabs(seen[0])
    assert res["status"] == "pass"  # it read the file the refresh had just written


def test_file_exists_refreshes_a_scene_dump(tmp_path, monkeypatch):
    seen = _calls(monkeypatch, "{}\n")
    res = evaluator.evaluate_check({"id": "c1", "type": "file_exists", "label": "Dump", "file": "mug.scene.json"},
                                   RunContext(workdir=str(tmp_path)))
    assert seen == [str(tmp_path / "mug.scene.json")] and res["status"] == "pass"


def test_other_files_never_refresh(tmp_path, monkeypatch):
    seen = _calls(monkeypatch)
    (tmp_path / "app.py").write_text("print('hi')\n")
    (tmp_path / "settings.json").write_text('{"a": 1}\n')
    ctx = RunContext(workdir=str(tmp_path))
    for f, pat in (("app.py", "print"), ("settings.json", '"a"')):
        evaluator.evaluate_check({"id": "c", "type": "file_contains", "label": "x", "file": f, "pattern": pat}, ctx)
        evaluator.evaluate_check({"id": "e", "type": "file_exists", "label": "x", "file": f}, ctx)
    assert seen == []


def test_eval_runner_never_touches_blender(monkeypatch):
    """The eval runner grades the stored dump as it is: refresh stays off, neither source is asked."""
    from server.evals.checks import runner

    asked: list[str] = []
    monkeypatch.setattr(scene_refresh, "_default_live", lambda: lambda *a: asked.append("live"))
    monkeypatch.setattr(scene_refresh, "_default_headless", lambda: lambda *a: asked.append("headless"))
    case = next(c for c in runner.load_cases() if c["id"] == "blender-mug-subsurf-smooth-done")
    out = runner.run_case(case)
    assert asked == [] and out.got == "pass" and out.error is None

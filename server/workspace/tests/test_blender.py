"""server.workspace.blender and the blender-addon dump scripts, with fakes only.

No Blender runs here: the runner is a fake that writes (or fails to write) the JSON Blender would, and the bpy
module is a stub so scene_dump.py's pure helpers load. The real headless run is test_blender_dump_live.py."""

from __future__ import annotations

import importlib.util
import json
import stat
import subprocess
import sys
import types
from pathlib import Path

import pytest

from server.workspace import blender

REPO = Path(__file__).resolve().parents[3]
ADDON = REPO / "blender-addon"
GOOD = {"dump": "dump_scene.py 1", "blender": "5.3.0", "file": "mug.blend", "is_dirty": False}
OLD = '{"dump": "dump_scene.py 1", "file": "old"}\n'


def _exe(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------ find_blender
@pytest.fixture
def nowhere(tmp_path, monkeypatch):
    """Every place find_blender looks is empty: fake home, empty PATH, no /Applications app, no Spotlight hit."""
    home, bin_dir = tmp_path / "home", tmp_path / "bin"
    home.mkdir()
    bin_dir.mkdir()
    monkeypatch.delenv(blender.BLENDER_ENV, raising=False)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setattr(blender, "SYSTEM_APP", tmp_path / "Applications" / "Blender.app")
    from server.workspace import setup

    monkeypatch.setattr(setup, "find_app", lambda bundle_id, name, *a, **k: None)
    return tmp_path


def test_find_blender_none_when_every_place_is_empty(nowhere):
    assert blender.find_blender() is None


def test_find_blender_honours_env_first(nowhere, monkeypatch):
    exe = _exe(nowhere / "custom" / "blender-5")
    _exe(nowhere / "bin" / "blender")
    monkeypatch.setenv(blender.BLENDER_ENV, str(exe))
    assert blender.find_blender() == str(exe)


def test_find_blender_skips_env_that_is_not_executable(nowhere, monkeypatch):
    (nowhere / "notexe").write_text("x")
    monkeypatch.setenv(blender.BLENDER_ENV, str(nowhere / "notexe"))
    assert blender.find_blender() is None
    monkeypatch.setenv(blender.BLENDER_ENV, str(nowhere / "missing"))
    assert blender.find_blender() is None


def test_find_blender_order_after_env(nowhere, monkeypatch):
    on_path = _exe(nowhere / "bin" / "blender")
    assert blender.find_blender() == str(on_path)
    from server.workspace import setup

    spot = nowhere / "Volumes" / "Blender.app"
    _exe(spot / "Contents" / "MacOS" / "Blender")
    monkeypatch.setattr(setup, "find_app", lambda bundle_id, name, *a, **k: str(spot))
    assert blender.find_blender() == str(spot / "Contents" / "MacOS" / "Blender")
    user = _exe(nowhere / "home" / "Applications" / "Blender.app" / "Contents" / "MacOS" / "Blender")
    assert blender.find_blender() == str(user)
    system = _exe(nowhere / "Applications" / "Blender.app" / "Contents" / "MacOS" / "Blender")
    assert blender.find_blender() == str(system)


def test_find_blender_survives_a_broken_spotlight(nowhere, monkeypatch):
    from server.workspace import setup

    def boom(*a, **k):
        raise RuntimeError("mdfind gone")

    monkeypatch.setattr(setup, "find_app", boom)
    assert blender.find_blender() is None


# ------------------------------------------------------------------ paths and argv
def test_scene_json_path_sits_next_to_the_blend(tmp_path):
    assert blender.scene_json_path(tmp_path / "mug.blend") == tmp_path / "mug.scene.json"
    assert blender.scene_json_path("a/b/shapes.v2.blend") == Path("a/b/shapes.v2.scene.json")


def test_dump_argv_is_headless_and_exact():
    argv = blender.dump_argv("/l/mug.blend", "/l/.out.tmp", blender="/bin/blender")
    assert argv == ["/bin/blender", "--background", "--factory-startup", "--disable-autoexec", "/l/mug.blend",
                    "--python-exit-code", "1", "--python", str(blender.DUMP_SCRIPT), "--", "/l/.out.tmp"]
    assert blender.DUMP_SCRIPT == REPO / "blender-addon" / "dump_scene.py"
    assert blender.DUMP_SCRIPT.is_file()


# ------------------------------------------------------------------ dump_blend with a fake Blender
class FakeBlender:
    """Stands in for the subprocess: records argv and writes `text` to the path after "--"."""

    def __init__(self, text: str | None = None, code: int = 0):
        self.text, self.code, self.calls = text, code, []

    def __call__(self, argv: list[str], timeout: float) -> int:
        self.calls.append((argv, timeout))
        if self.text is not None:
            Path(argv[argv.index("--") + 1]).write_text(self.text, encoding="utf-8")
        return self.code


@pytest.fixture
def lesson(tmp_path):
    blend = tmp_path / "mug.blend"
    blend.write_bytes(b"BLENDER-v405 fake")
    return blend


def test_dump_blend_writes_scene_json_and_returns_the_dict(lesson):
    fake = FakeBlender(json.dumps(GOOD))
    doc = blender.dump_blend(lesson, runner=fake, blender="/bin/blender", timeout=12.0)
    assert doc == GOOD
    out = lesson.with_name("mug.scene.json")
    assert json.loads(out.read_text()) == GOOD
    (argv, timeout), = fake.calls
    tmp = argv[-1]
    assert argv == blender.dump_argv(lesson.resolve(), tmp, blender="/bin/blender")
    assert argv[1:4] == ["--background", "--factory-startup", "--disable-autoexec"]
    assert Path(tmp).parent == out.parent.resolve() and tmp != str(out)
    assert timeout == 12.0
    assert sorted(p.name for p in lesson.parent.iterdir()) == ["mug.blend", "mug.scene.json"]


def test_dump_blend_honours_out_path(lesson, tmp_path):
    out = tmp_path / "elsewhere.json"
    assert blender.dump_blend(lesson, out, runner=FakeBlender(json.dumps(GOOD)), blender="/bin/b") == GOOD
    assert out.is_file() and not lesson.with_name("mug.scene.json").exists()


def test_dump_blend_finds_blender_when_not_given(lesson, monkeypatch):
    monkeypatch.setattr(blender, "find_blender", lambda: "/found/Blender")
    fake = FakeBlender(json.dumps(GOOD))
    assert blender.dump_blend(lesson, runner=fake) == GOOD
    assert fake.calls[0][0][0] == "/found/Blender"


@pytest.mark.parametrize("case", ["exit_1", "timeout", "bad_json", "wrong_tag", "not_a_dict", "no_output",
                                  "runner_raises"])
def test_dump_blend_failure_keeps_the_old_dump(lesson, case):
    out = lesson.with_name("mug.scene.json")
    out.write_text(OLD)
    before = out.read_bytes()
    fake = {
        "exit_1": FakeBlender(json.dumps(GOOD), code=1),
        "timeout": FakeBlender(None, code=-1),
        "bad_json": FakeBlender('{"dump": "dump_scene.py 1",'),
        "wrong_tag": FakeBlender(json.dumps({**GOOD, "dump": "dump_scene.py 2"})),
        "not_a_dict": FakeBlender("[1, 2]"),
        "no_output": FakeBlender(None),
    }.get(case)
    if case == "runner_raises":
        def fake(argv, timeout):
            raise RuntimeError("boom")
    assert blender.dump_blend(lesson, runner=fake, blender="/bin/blender") is None
    assert out.read_bytes() == before
    assert sorted(p.name for p in lesson.parent.iterdir()) == ["mug.blend", "mug.scene.json"]


def test_dump_blend_missing_blend_or_blender_or_script(lesson, monkeypatch):
    out = lesson.with_name("mug.scene.json")
    out.write_text(OLD)
    before = out.read_bytes()
    fake = FakeBlender(json.dumps(GOOD))
    assert blender.dump_blend(lesson.with_name("gone.blend"), out, runner=fake, blender="/bin/b") is None
    monkeypatch.setattr(blender, "find_blender", lambda: None)
    assert blender.dump_blend(lesson, runner=fake) is None
    monkeypatch.setattr(blender, "DUMP_SCRIPT", lesson.with_name("no_script.py"))
    assert blender.dump_blend(lesson, runner=fake, blender="/bin/b") is None
    assert fake.calls == []
    assert out.read_bytes() == before


def test_dump_blend_never_raises_on_odd_input(tmp_path):
    assert blender.dump_blend(tmp_path, runner=FakeBlender(json.dumps(GOOD)), blender="/bin/b") is None
    assert blender.dump_blend("\0bad", runner=FakeBlender(json.dumps(GOOD)), blender="/bin/b") is None


# ------------------------------------------------------------------ the default runner
def test_run_blender_drops_paid_keys_and_maps_timeout(monkeypatch):
    seen = {}

    def fake_run(argv, **kw):
        seen.update(kw, argv=argv)
        return subprocess.CompletedProcess(argv, 3, b"", b"")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("GEMINI_API_KEY", "y")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert blender.run_blender(["/bin/blender", "--background"], 5.0) == 3
    assert "ANTHROPIC_API_KEY" not in seen["env"] and "GEMINI_API_KEY" not in seen["env"]
    assert seen["timeout"] == 5.0 and seen["capture_output"] is True

    def slow(argv, **kw):
        raise subprocess.TimeoutExpired(argv, kw["timeout"])

    monkeypatch.setattr(subprocess, "run", slow)
    assert blender.run_blender(["/bin/blender"], 0.1) == -1


def test_run_blender_missing_binary_is_minus_one(tmp_path):
    assert blender.run_blender([str(tmp_path / "no-blender")], 1.0) == -1


# ------------------------------------------------------------------ dump_scene.py CLI helpers (no bpy needed)
def test_cli_splits_args_and_writes_atomically(tmp_path):
    cli = _load("miyagi_dump_cli_test", ADDON / "dump_scene.py")
    assert cli.script_args(["blender", "-b", "x.blend", "--", "out.json"]) == (["blender", "-b", "x.blend"],
                                                                               ["out.json"])
    assert cli.script_args(["blender"]) == (["blender"], [])
    out = tmp_path / "x.scene.json"
    out.write_text("old")
    cli.write_atomic(str(out), "new\n")
    assert out.read_text() == "new\n"
    assert [p.name for p in tmp_path.iterdir()] == ["x.scene.json"]
    assert Path(cli.SCENE_DUMP) == ADDON / "miyagi_bridge" / "scene_dump.py"


def test_cli_never_imports_the_bridge_package():
    text = (ADDON / "dump_scene.py").read_text()
    assert "spec_from_file_location" in text
    assert "import miyagi_bridge" not in text and "from miyagi_bridge" not in text


# ------------------------------------------------------------------ scene_dump.py pure helpers (stub bpy)
@pytest.fixture
def scene_dump(monkeypatch):
    monkeypatch.setitem(sys.modules, "bpy", types.ModuleType("bpy"))
    return _load("miyagi_scene_dump_test", ADDON / "miyagi_bridge" / "scene_dump.py")


def test_scene_dump_has_no_relative_imports_and_no_ops():
    text = (ADDON / "miyagi_bridge" / "scene_dump.py").read_text()
    assert "from ." not in text
    assert "bpy.ops" not in text.replace("no bpy.ops", "")


def test_scene_dump_format_and_json(scene_dump):
    assert scene_dump.FORMAT == "dump_scene.py 1"
    text = scene_dump.to_json({"dump": scene_dump.FORMAT, "name": "Tasse é", "v": [1.0, 2]})
    assert text == '{\n "dump": "dump_scene.py 1",\n "name": "Tasse é",\n "v": [\n  1.0,\n  2\n ]\n}\n'


def test_scene_dump_rounds_to_six_places(scene_dump):
    assert scene_dump._f(1.5199999809265137) == 1.52
    assert scene_dump._f(90.00000250447816) == 90.000003
    assert scene_dump._deg([1.5707963705062866, 0.0]) == [90.000003, 0.0]
    assert json.dumps(scene_dump._vec([-0.0, -1e-9, -0.5])) == "[0.0, 0.0, -0.5]"


def test_scene_dump_islands(scene_dump):
    assert scene_dump._islands(0, []) == 0
    assert scene_dump._islands(4, [0, 1, 1, 2]) == 2  # 0-1-2 and a loose 3
    assert scene_dump._islands(6, [0, 1, 2, 3, 4, 5, 1, 2]) == 2


def test_scene_dump_overlapping_boxes(scene_dump):
    assert scene_dump._overlapping([]) == 0
    assert scene_dump._overlapping([(0, 0, 1, 1), (1, 0, 2, 1)]) == 0  # touching edges only
    assert scene_dump._overlapping([(0, 0, 1, 1), (0.5, 0.5, 1.5, 1.5), (3, 3, 4, 4)]) == 2
    assert scene_dump._overlapping([(0, 0, 1, 1)] * 3) == 3


def test_scene_dump_socket_values(scene_dump):
    assert scene_dump._socket_value(True) is True
    assert scene_dump._socket_value(3) == 3
    assert scene_dump._socket_value(0.30000001192092896) == 0.3
    assert scene_dump._socket_value((0.8, 0.8, 0.8, 1.0)) == [0.8, 0.8, 0.8, 1.0]
    assert scene_dump._socket_value("text") is None
    assert scene_dump._socket_value(object()) is None


# ------------------------------------------------------------------ create_blend (Open in Blender, Nov 24)
BLEND_BYTES = b"BLENDER-v405" + b"\0" * 64


class NewBlend:
    """A fake headless Blender for new_blend_argv: records argv, writes `data` to the temp path, returns `code`."""

    def __init__(self, code: int = 0, data: bytes | None = BLEND_BYTES):
        self.code, self.data, self.calls = code, data, []

    def __call__(self, argv: list[str], timeout: float) -> int:
        self.calls.append(list(argv))
        if self.data is not None:
            Path(argv[-1]).write_bytes(self.data)
        return self.code


def test_new_blend_argv_is_headless_factory_and_no_autoexec(tmp_path):
    out = tmp_path / "x.blend"
    assert blender.new_blend_argv(out, blender="/B") == [
        "/B", "--background", "--factory-startup", "--disable-autoexec", "--python-exit-code", "1",
        "--python-expr", "import bpy,sys; bpy.ops.wm.save_as_mainfile(filepath=sys.argv[-1])", "--", str(out)]


def test_create_blend_writes_a_temp_then_replaces(tmp_path):
    run = NewBlend()
    target = tmp_path / "donut.blend"
    assert blender.create_blend(target, runner=run, blender="/B") is True
    assert len(run.calls) == 1
    tmp = Path(run.calls[0][-1])
    assert tmp.parent == tmp_path and tmp != target and tmp.name.startswith(".donut.")
    assert target.read_bytes() == BLEND_BYTES
    assert sorted(p.name for p in tmp_path.iterdir()) == ["donut.blend"]  # no temp left


def test_create_blend_fills_a_zero_byte_file(tmp_path):
    target = tmp_path / "donut.blend"
    target.touch()  # lesson mode touches step files
    run = NewBlend()
    assert blender.create_blend(target, runner=run, blender="/B") is True
    assert len(run.calls) == 1 and target.read_bytes() == BLEND_BYTES


def test_create_blend_never_rewrites_a_saved_scene(tmp_path):
    target = tmp_path / "donut.blend"
    target.write_bytes(b"BLENDER learner's own")
    run = NewBlend()
    assert blender.create_blend(target, runner=run, blender="/B") is True
    assert run.calls == [] and target.read_bytes() == b"BLENDER learner's own"


def test_create_blend_keeps_a_scene_saved_while_blender_ran(tmp_path):
    target = tmp_path / "donut.blend"

    def run(argv, timeout):
        Path(argv[-1]).write_bytes(BLEND_BYTES)
        target.write_bytes(b"BLENDER saved meanwhile")
        return 0

    assert blender.create_blend(target, runner=run, blender="/B") is True
    assert target.read_bytes() == b"BLENDER saved meanwhile"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["donut.blend"]


@pytest.mark.parametrize("run", [NewBlend(code=1), NewBlend(data=None), NewBlend(data=b""),
                                 NewBlend(data=b"not a blend")],
                         ids=["rc1", "no-output", "empty-output", "not-a-blend"])
def test_create_blend_failures_leave_nothing(tmp_path, run):
    target = tmp_path / "donut.blend"
    assert blender.create_blend(target, runner=run, blender="/B") is False
    assert list(tmp_path.iterdir()) == []


def test_create_blend_failure_keeps_the_zero_byte_file(tmp_path):
    target = tmp_path / "donut.blend"
    target.touch()
    assert blender.create_blend(target, runner=NewBlend(code=1), blender="/B") is False
    assert [p.name for p in tmp_path.iterdir()] == ["donut.blend"] and target.stat().st_size == 0


def test_create_blend_without_blender_or_folder(nowhere):
    run = NewBlend()
    lesson_dir = nowhere / "lesson"
    lesson_dir.mkdir()
    assert blender.create_blend(lesson_dir / "donut.blend", runner=run) is False  # no Blender anywhere
    assert blender.create_blend(lesson_dir / "missing" / "donut.blend", runner=run, blender="/B") is False
    assert run.calls == [] and list(lesson_dir.iterdir()) == []


def test_create_blend_never_raises(tmp_path):
    def boom(argv, timeout):
        raise RuntimeError("runner broke")

    assert blender.create_blend(tmp_path / "donut.blend", runner=boom, blender="/B") is False
    assert list(tmp_path.iterdir()) == []


def test_create_blend_default_runner_is_the_clean_env_one(tmp_path, monkeypatch):
    seen = {}

    def fake_run(argv, **kw):
        seen.update(kw)
        Path(argv[-1]).write_bytes(BLEND_BYTES)
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert blender.create_blend(tmp_path / "donut.blend", blender="/B") is True
    assert "ANTHROPIC_API_KEY" not in seen["env"]


@pytest.mark.skipif(blender.find_blender() is None, reason="Blender is not installed")
def test_create_blend_with_real_headless_blender(tmp_path, monkeypatch):
    """The real thing, headless only (--background --factory-startup, no window): Blender's factory scene saved,
    then read back by dump_blend."""
    for k in blender.PAID_KEYS:
        monkeypatch.delenv(k, raising=False)
    target = tmp_path / "donut.blend"
    assert blender.create_blend(target, timeout=120) is True
    assert target.stat().st_size > 0 and [p.name for p in tmp_path.iterdir()] == ["donut.blend"]
    doc = blender.dump_blend(target, timeout=120)
    assert doc is not None and "Cube" in [o["name"] for o in doc["objects"]]

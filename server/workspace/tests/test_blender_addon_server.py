"""blender-addon/miyagi_bridge: the in-Blender bridge server, tested without Blender.

The add-on package is loaded by file path with a fake `bpy` and a fake `scene_dump` module; servers bind port 0.
One smoke test runs the real Blender headless (--background --factory-startup) when it is installed."""

from __future__ import annotations

import http.client
import importlib
import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[3]
ADDON_DIR = REPO / "blender-addon"
PKG_DIR = ADDON_DIR / "miyagi_bridge"
PKG = "miyagi_bridge"
LOCAL = {"Host": "127.0.0.1:8801"}


# ------------------------------------------------------------------ fakes


class FakeObjects(list):
    def __init__(self, objs, active=None):
        super().__init__(objs)
        self.active = active


class FakeObject:
    def __init__(self, name, selected=False):
        self.name, self.selected = name, selected

    def select_get(self, view_layer=None):
        return self.selected


class FakeTimers:
    def __init__(self):
        self.fns = []

    def register(self, fn, first_interval=0.0, persistent=False):
        self.fns.append(fn)

    def unregister(self, fn):
        self.fns.remove(fn)

    def is_registered(self, fn):
        return fn in self.fns


class FakeProps:
    def __init__(self, **values):
        self.__dict__.update(values)
        names = ["rna_type", *values]
        self.bl_rna = SimpleNamespace(properties=[SimpleNamespace(identifier=n) for n in names])
        self.rna_type = object()


class FakeOp:
    _next = 1000

    def __init__(self, bl_idname="MESH_OT_primitive_torus_add", name="Add Torus", **props):
        FakeOp._next += 8
        self.ptr, self.bl_idname, self.name, self.properties = FakeOp._next, bl_idname, name, FakeProps(**props)

    def as_pointer(self):
        return self.ptr


def rect(x, y, w, h, **kw):
    return SimpleNamespace(x=x, y=y, width=w, height=h, **kw)


def make_bpy():
    cube, light = FakeObject("Cube", selected=True), FakeObject("Light")
    view3d = rect(0, 0, 800, 600, type="VIEW_3D", ui_type="VIEW_3D",
                  regions=[rect(0, 0, 800, 26, type="HEADER"), rect(0, 26, 800, 574, type="WINDOW")])
    props = rect(800, 0, 300, 600, type="PROPERTIES", ui_type="PROPERTIES", regions=[rect(800, 0, 300, 600,
                                                                                         type="WINDOW")])
    window = rect(10, 20, 1100, 600, screen=SimpleNamespace(name="Layout", areas=[view3d, props]),
                  workspace=SimpleNamespace(name="Layout"))
    ctx = SimpleNamespace(
        mode="OBJECT",
        scene=SimpleNamespace(frame_current=7),
        view_layer=SimpleNamespace(objects=FakeObjects([cube, light], active=cube)),
        window_manager=SimpleNamespace(operators=[], windows=[window]),
        preferences=SimpleNamespace(system=SimpleNamespace(pixel_size=2.0, ui_scale=1.25)),
    )
    bpy = types.ModuleType("bpy")
    bpy.app = SimpleNamespace(version_string="5.3.0", timers=FakeTimers())
    bpy.data = SimpleNamespace(filepath="/tmp/lesson/scene.blend", is_dirty=True)
    bpy.context = ctx
    return bpy


@pytest.fixture
def bpy(monkeypatch):
    fake = make_bpy()
    monkeypatch.setitem(sys.modules, "bpy", fake)
    return fake


@pytest.fixture
def dumps(monkeypatch):
    """A fake miyagi_bridge.scene_dump: records each context it was given."""
    calls = []
    mod = types.ModuleType(f"{PKG}.scene_dump")
    mod.FORMAT = "dump_scene.py 1"

    def dump(context=None):
        calls.append(context)
        return {"dump": "dump_scene.py 1", "objects": [{"name": "Cube"}]}

    mod.dump = dump
    monkeypatch.setitem(sys.modules, f"{PKG}.scene_dump", mod)
    return calls


def load_addon():
    """A fresh copy of the add-on package (and its server module), loaded by file path."""
    for name in [n for n in sys.modules if n == PKG or n.startswith(PKG + ".")]:
        if not name.endswith(".scene_dump"):
            del sys.modules[name]
    spec = importlib.util.spec_from_file_location(PKG, PKG_DIR / "__init__.py", submodule_search_locations=[str(PKG_DIR)])
    pkg = importlib.util.module_from_spec(spec)
    sys.modules[PKG] = pkg
    spec.loader.exec_module(pkg)
    return pkg, importlib.import_module(f"{PKG}.server")


@pytest.fixture
def addon(monkeypatch, tmp_path):
    monkeypatch.setenv("MIYAGI_ENGINE_TOKEN_DIR", str(tmp_path / "tokens"))
    pkg, srv = load_addon()
    srv.reset_tokens()
    srv.reset_ops()
    yield SimpleNamespace(pkg=pkg, server=srv)
    srv.stop()
    for name in [n for n in sys.modules if n == PKG or (n.startswith(PKG + ".") and not n.endswith(".scene_dump"))]:
        del sys.modules[name]


@pytest.fixture
def server(addon):
    return addon.server


def live_token(tmp_path, token="tok-abc"):
    d = tmp_path / "tokens"
    d.mkdir(exist_ok=True)
    (d / "8787.json").write_text(json.dumps({"token": token, "pid": os.getpid(), "port": 8787}))
    return token


def handle_with_pump(server, path, headers=LOCAL, limit=3.0):
    """Ask in a handler thread while this thread plays Blender's timer, as bpy.app.timers would."""
    out = {}
    t = threading.Thread(target=lambda: out.update(r=server.handle("GET", path, headers)))
    t.start()
    end = time.monotonic() + limit
    while t.is_alive() and time.monotonic() < end:
        server.pump()
        time.sleep(0.01)
    t.join(1.0)
    return out["r"]


# ------------------------------------------------------------------ acceptance 4: health and token


def test_health_without_token(server, bpy, tmp_path):
    live_token(tmp_path)
    server.pump()  # caches blender version and file
    code, body = server.handle("GET", "/health", LOCAL)
    assert code == 200
    assert body == {"ok": True, "app": "blender", "name": "miyagi_bridge", "version": "0.1.0", "blender": "5.3.0",
                    "port": 0, "pid": os.getpid(), "file": "/tmp/lesson/scene.blend"}


@pytest.mark.parametrize("path", ["/state", "/ops", "/ui"])
def test_routes_need_the_token_while_an_engine_is_live(server, bpy, dumps, tmp_path, path):
    tok = live_token(tmp_path)
    code, body = server.handle("GET", path, LOCAL)
    assert (code, body) == (401, {"ok": False, "error": "token_required"})
    code, body = server.handle("GET", path, {**LOCAL, "X-Miyagi-Token": "wrong"})
    assert code == 401
    code, body = handle_with_pump(server, path, {**LOCAL, "x-miyagi-token": tok})
    assert code == 200 and body["ok"] is True


def test_dead_engine_token_is_ignored(server, bpy, tmp_path):
    d = tmp_path / "tokens"
    d.mkdir()
    (d / "8787.json").write_text(json.dumps({"token": "t", "pid": 999_999_999, "port": 8787}))
    (d / "notes.json").write_text(json.dumps({"token": "t2", "pid": os.getpid(), "port": 1}))
    assert server.live_tokens() == []
    assert server.handle("GET", "/ops", LOCAL)[0] == 200


def test_open_to_loopback_without_a_token(server, bpy):
    assert server.handle("GET", "/ops", LOCAL)[0] == 200


# ------------------------------------------------------------------ acceptance 5: guards


@pytest.mark.parametrize("headers,remote,code,error", [
    ({**LOCAL, "Origin": "https://evil.example"}, "127.0.0.1", 403, "origin_not_allowed"),
    ({**LOCAL, "Sec-Fetch-Site": "cross-site"}, "127.0.0.1", 403, "browser_not_allowed"),
    ({**LOCAL, "Sec-Fetch-Site": "same-origin"}, "127.0.0.1", 403, "browser_not_allowed"),
    ({"Host": "evil.example"}, "127.0.0.1", 403, "host_not_allowed"),
    ({"Host": "evil.example:8801"}, "127.0.0.1", 403, "host_not_allowed"),
    ({}, "127.0.0.1", 403, "host_not_allowed"),
    (LOCAL, "192.168.1.9", 403, "not_loopback"),
])
def test_guards(server, headers, remote, code, error):
    assert server.handle("GET", "/health", headers, remote) == (code, {"ok": False, "error": error})


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost:8801", "[::1]:8802", "LOCALHOST"])
def test_loopback_hosts_pass(server, host):
    assert server.handle("GET", "/health", {"Host": host}, "::1")[0] == 200


def test_sec_fetch_site_none_passes(server):
    assert server.handle("GET", "/health", {**LOCAL, "Sec-Fetch-Site": "none"})[0] == 200


def test_unknown_route(server):
    code, body = server.handle("GET", "/nope", LOCAL)
    assert code == 404 and body["error"] == "no_route"
    assert server.handle("POST", "/health", LOCAL)[0] == 404


# ------------------------------------------------------------------ acceptance 6: /state on the main thread


def test_state_runs_on_the_main_thread(server, bpy, dumps):
    code, body = handle_with_pump(server, "/state")
    assert code == 200
    assert body == {"ok": True, "app": "blender", "port": 0, "file": "/tmp/lesson/scene.blend", "dirty": True,
                    "mode": "OBJECT", "active": "Cube", "selected": ["Cube"], "frame_current": 7,
                    "dump": {"dump": "dump_scene.py 1", "objects": [{"name": "Cube"}]}}
    assert dumps == [bpy.context]


def test_state_without_pump_is_busy(server, bpy, dumps, monkeypatch):
    monkeypatch.setattr(server, "MAIN_WAIT_S", 0.2)
    t0 = time.monotonic()
    assert server.handle("GET", "/state", LOCAL) == (503, {"ok": False, "error": "busy"})
    assert 0.15 < time.monotonic() - t0 < 1.0
    server.pump()  # the abandoned job is dropped, not run
    assert dumps == []


def test_main_thread_wait_is_one_and_a_half_seconds(server):
    assert server.MAIN_WAIT_S == 1.5


def test_a_failing_job_answers_500_and_pump_survives(server, bpy, monkeypatch):
    def broken(context=None):
        raise ValueError("bad scene")

    mod = types.ModuleType(f"{PKG}.scene_dump")
    mod.dump = broken
    monkeypatch.setitem(sys.modules, f"{PKG}.scene_dump", mod)
    code, body = handle_with_pump(server, "/state")
    assert code == 500 and body["error"] == "internal" and "bad scene" in body["detail"]
    assert server.pump() == server.PUMP_INTERVAL_S


def test_state_without_active_object(server, bpy, dumps):
    bpy.context.view_layer.objects.active = None
    code, body = handle_with_pump(server, "/state")
    assert code == 200 and body["active"] is None


# ------------------------------------------------------------------ acceptance 7: /ops


def test_ops_seen_once_with_increasing_seq(server, bpy, monkeypatch):
    monkeypatch.setattr(server, "OPS_POLL_S", 0.0)
    wm = bpy.context.window_manager
    torus = FakeOp(major_radius=1.0, location=(0.0, 1.5, 2.0), align="WORLD", flags={"B", "A"})
    wm.operators = [torus]
    server.pump()
    move = FakeOp("TRANSFORM_OT_translate", "Move", value=(1.0, 0.0, 0.0))
    wm.operators = [torus, move]
    server.pump()
    server.pump()
    code, body = server.handle("GET", "/ops", LOCAL)
    assert code == 200
    assert body["last_seq"] == 2
    assert [(o["seq"], o["idname"], o["name"]) for o in body["ops"]] == [
        (1, "mesh.primitive_torus_add", "Add Torus"), (2, "transform.translate", "Move")]
    assert body["ops"][0]["props"] == {"major_radius": 1.0, "location": [0.0, 1.5, 2.0], "align": "WORLD",
                                       "flags": ["A", "B"]}
    assert isinstance(body["ops"][0]["t"], float)
    code, body = server.handle("GET", "/ops?since=1", LOCAL)
    assert [o["seq"] for o in body["ops"]] == [2] and body["last_seq"] == 2
    assert server.handle("GET", "/ops?since=2", LOCAL)[1]["ops"] == []
    assert server.handle("GET", "/ops?since=x", LOCAL)[1]["last_seq"] == 2


def test_ops_poll_is_throttled(server, bpy):
    wm = bpy.context.window_manager
    wm.operators = [FakeOp()]
    server.pump()
    wm.operators = [*wm.operators, FakeOp()]
    server.pump()  # within OPS_POLL_S of the last poll: not read yet
    assert server.handle("GET", "/ops", LOCAL)[1]["last_seq"] == 1


def test_ops_capped_at_200(server):
    for _ in range(5):
        server.poll_ops([FakeOp() for _ in range(50)])
    body = server.handle("GET", "/ops", LOCAL)[1]
    assert body["last_seq"] == 250
    assert len(body["ops"]) == 200
    assert body["ops"][0]["seq"] == 51


def test_ops_reused_pointer_in_one_poll_is_reported(server):
    """Blender frees the oldest registered op when a new one comes in; a new op can land on that address."""
    full = [FakeOp() for _ in range(32)]
    server.poll_ops(full)
    reused = FakeOp()
    reused.ptr = full[0].ptr  # same address and same idname as the op that was just freed
    assert server.poll_ops([*full[1:], reused]) == 1
    body = server.handle("GET", "/ops?since=32", LOCAL)[1]
    assert [o["seq"] for o in body["ops"]] == [33] and body["last_seq"] == 33
    assert server.poll_ops([*full[1:], reused]) == 0


def test_ops_two_new_in_one_poll_with_a_full_list(server):
    full = [FakeOp() for _ in range(32)]
    server.poll_ops(full)
    a, b = FakeOp("OBJECT_OT_delete", "Delete"), FakeOp("TRANSFORM_OT_resize", "Resize")
    b.ptr = full[0].ptr
    assert server.poll_ops([*full[2:], a, b]) == 2
    body = server.handle("GET", "/ops?since=32", LOCAL)[1]
    assert [(o["seq"], o["idname"]) for o in body["ops"]] == [(33, "object.delete"), (34, "transform.resize")]


def test_ops_cleared_list_reports_everything_new(server):
    server.poll_ops([FakeOp(), FakeOp()])
    assert server.poll_ops([FakeOp()]) == 1
    assert server.handle("GET", "/ops", LOCAL)[1]["last_seq"] == 3


class BrokenProps(FakeOp):
    @property
    def properties(self):
        raise ReferenceError("StructRNA of type Operator has been removed")

    @properties.setter
    def properties(self, value):
        pass


class BrokenIdname(FakeOp):
    @property
    def bl_idname(self):
        raise ReferenceError("StructRNA of type Operator has been removed")

    @bl_idname.setter
    def bl_idname(self, value):
        pass


@pytest.mark.parametrize("broken", [BrokenProps, BrokenIdname])
def test_an_unreadable_op_is_skipped_and_nothing_repeats(server, broken):
    good1, bad, good2 = FakeOp(), broken("OBJECT_OT_delete", "Delete"), FakeOp("TRANSFORM_OT_translate", "Move")
    assert server.poll_ops([good1, bad, good2]) == 2
    assert server.poll_ops([good1, bad, good2]) == 0
    good3 = FakeOp("OBJECT_OT_shade_smooth", "Shade Smooth")
    assert server.poll_ops([good1, bad, good2, good3]) == 1
    body = server.handle("GET", "/ops", LOCAL)[1]
    assert [(o["seq"], o["idname"]) for o in body["ops"]] == [
        (1, "mesh.primitive_torus_add"), (2, "transform.translate"), (3, "object.shade_smooth")]


def test_an_unlistable_operators_value_keeps_the_snapshot(server):
    class Unlistable:
        def __iter__(self):
            raise ReferenceError("window manager freed")

    ops = [FakeOp(), FakeOp()]
    server.poll_ops(ops)
    assert server.poll_ops(Unlistable()) == 0
    assert server.poll_ops(ops) == 0
    assert server.handle("GET", "/ops", LOCAL)[1]["last_seq"] == 2


def test_py_idname():
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location("bridge_server_plain", PKG_DIR / "server.py")
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.py_idname("MESH_OT_primitive_torus_add") == "mesh.primitive_torus_add"
    assert mod.py_idname("OBJECT_OT_modifier_add") == "object.modifier_add"
    assert mod.py_idname("mesh.subdivide") == "mesh.subdivide"


# ------------------------------------------------------------------ acceptance 8: /ui


def test_ui_rects(server, bpy):
    code, body = handle_with_pump(server, "/ui")
    assert code == 200
    assert body["pixel_size"] == 2.0 and body["ui_scale"] == 1.25 and body["origin"] == "bottom-left"
    (win,) = body["windows"]
    assert {k: win[k] for k in ("x", "y", "width", "height", "screen", "workspace")} == {
        "x": 10, "y": 20, "width": 1100, "height": 600, "screen": "Layout", "workspace": "Layout"}
    assert [a["type"] for a in win["areas"]] == ["VIEW_3D", "PROPERTIES"]
    area = win["areas"][0]
    assert area == {"type": "VIEW_3D", "ui_type": "VIEW_3D", "x": 0, "y": 0, "width": 800, "height": 600,
                    "regions": [{"type": "HEADER", "x": 0, "y": 0, "width": 800, "height": 26},
                                {"type": "WINDOW", "x": 0, "y": 26, "width": 800, "height": 574}]}


# ------------------------------------------------------------------ real HTTP, register / unregister


def get(port, path, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        conn.request("GET", path, headers=headers or {})
        resp = conn.getresponse()
        return resp.status, {k.lower(): v for k, v in resp.getheaders()}, json.loads(resp.read())
    finally:
        conn.close()


def test_http_server_on_port_zero(server, bpy):
    port = server.start(0)
    assert port > 0 and server.port() == port
    assert server.start(0) == port  # a second start keeps the running server
    status, headers, body = get(port, "/health")
    assert status == 200 and body["app"] == "blender" and body["port"] == port
    assert headers["cache-control"] == "no-store"
    assert headers["content-type"].startswith("application/json")
    status, _, body = get(port, "/health", {"Origin": "https://evil.example"})
    assert (status, body["error"]) == (403, "origin_not_allowed")
    status, _, body = get(port, "/nope")
    assert (status, body["error"]) == (404, "no_route")
    server.stop()
    assert server.port() == 0
    with pytest.raises(OSError):
        get(port, "/health")


def test_start_takes_the_first_free_port(server, monkeypatch):
    with socket.socket() as busy, socket.socket() as probe:
        busy.bind(("127.0.0.1", 0))
        busy.listen(1)
        probe.bind(("127.0.0.1", 0))
        free = probe.getsockname()[1]
        probe.close()
        monkeypatch.setenv("MIYAGI_BLENDER_PORTS", f"{busy.getsockname()[1]},{free}")
        assert server.ports() == [busy.getsockname()[1], free]
        assert server.start() == free


def test_start_returns_zero_when_no_port_is_free(server, monkeypatch):
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen(1)
        monkeypatch.setenv("MIYAGI_BLENDER_PORTS", str(busy.getsockname()[1]))
        assert server.start() == 0


def test_default_ports(server, monkeypatch):
    monkeypatch.delenv("MIYAGI_BLENDER_PORTS", raising=False)
    assert server.ports() == list(range(8801, 8810))


def test_register_and_unregister(addon, bpy, monkeypatch):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        free = probe.getsockname()[1]
    monkeypatch.setenv("MIYAGI_BLENDER_PORTS", str(free))
    addon.pkg.register()
    assert addon.server.port() == free
    assert bpy.app.timers.is_registered(addon.server.pump)
    addon.pkg.register()  # twice: still one timer
    assert bpy.app.timers.fns.count(addon.server.pump) == 1
    addon.pkg.unregister()
    assert addon.server.port() == 0
    assert not bpy.app.timers.is_registered(addon.server.pump)


def test_bl_info_and_manifest(addon):
    info = addon.pkg.bl_info
    assert info["name"] == "miyagi bridge" and info["blender"] == (4, 2, 0) and info["category"] == "System"
    text = (PKG_DIR / "blender_manifest.toml").read_text()
    for line in ('schema_version = "1.0.0"', 'id = "miyagi_bridge"', 'version = "0.1.0"', 'type = "add-on"',
                 'blender_version_min = "4.2.0"', "[permissions]", "network = ", "files = "):
        assert line in text
    try:
        import tomllib
    except ImportError:
        return
    data = tomllib.loads(text)
    assert set(data["permissions"]) == {"network", "files"}
    # Blender's extension check: each permission reason and the tagline are at most 64 characters and end in a
    # letter or digit, else the add-on cannot be built or installed as an extension.
    for value in [*data["permissions"].values(), data["tagline"]]:
        assert len(value) <= 64, value
        assert value[-1].isalnum(), value


# ------------------------------------------------------------------ acceptance 10: no bpy at import, no UI


def test_imports_without_bpy():
    code = (
        "import sys, importlib.util\n"
        "assert 'bpy' not in sys.modules\n"
        f"spec = importlib.util.spec_from_file_location('miyagi_bridge', {str(PKG_DIR / '__init__.py')!r},"
        f" submodule_search_locations=[{str(PKG_DIR)!r}])\n"
        "pkg = importlib.util.module_from_spec(spec); sys.modules['miyagi_bridge'] = pkg\n"
        "spec.loader.exec_module(pkg)\n"
        "import miyagi_bridge.server as s\n"
        "assert 'bpy' not in sys.modules, 'bpy imported'\n"
        "assert s.handle('GET', '/health', {'Host': '127.0.0.1'})[0] == 200\n"
        "print('ok')\n"
    )
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY")}
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30, env=env, check=False)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "ok"


def test_addon_draws_nothing():
    for path in [*PKG_DIR.glob("*.py"), ADDON_DIR / "start_bridge.py"]:
        if path.name == "scene_dump.py":
            continue
        src = path.read_text()
        assert not re.search(r"bpy\.types\.(Panel|Menu|Header|UIList|Operator)|register_class|def draw\b|"
                             r"\.draw_handler_add|report\(", src), path


def test_start_bridge_registers(monkeypatch, bpy, tmp_path):
    """start_bridge.py puts its folder on sys.path, imports miyagi_bridge and registers it."""
    monkeypatch.setenv("MIYAGI_ENGINE_TOKEN_DIR", str(tmp_path / "tokens"))
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        free = probe.getsockname()[1]
    monkeypatch.setenv("MIYAGI_BLENDER_PORTS", str(free))
    monkeypatch.setattr(sys, "path", list(sys.path))
    for name in [n for n in sys.modules if n == PKG or (n.startswith(PKG + ".") and not n.endswith(".scene_dump"))]:
        monkeypatch.delitem(sys.modules, name)
    spec = importlib.util.spec_from_file_location("start_bridge_t", ADDON_DIR / "start_bridge.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    srv = sys.modules[f"{PKG}.server"]
    try:
        assert str(ADDON_DIR) in sys.path
        assert srv.port() == free
        assert bpy.app.timers.is_registered(srv.pump)
    finally:
        sys.modules[PKG].unregister()
        for name in [n for n in sys.modules if n == PKG or (n.startswith(PKG + ".") and not n.endswith(".scene_dump"))]:
            del sys.modules[name]


# ------------------------------------------------------------------ real Blender, headless (skipped when missing)


def _blender() -> str | None:
    for cand in (os.environ.get("MIYAGI_BLENDER"), "/Applications/Blender.app/Contents/MacOS/Blender"):
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return None


SMOKE = r'''
import http.client, json, sys, threading, types
addon_dir, out = sys.argv[sys.argv.index("--") + 1:]
sys.path.insert(0, addon_dir)
stub = types.ModuleType("miyagi_bridge.scene_dump")
stub.dump = lambda context=None: {"dump": "dump_scene.py 1", "objects": [o.name for o in context.scene.objects]}
sys.modules["miyagi_bridge.scene_dump"] = stub
import miyagi_bridge
from miyagi_bridge import server
miyagi_bridge.register()
port = server.port()
res = {"port": port}

def get(path, key):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request("GET", path)
    r = c.getresponse()
    res[key] = [r.status, json.loads(r.read())]

for path, key in (("/health", "health"), ("/state", "state"), ("/ui", "ui")):
    t = threading.Thread(target=get, args=(path, key))
    t.start()
    for _ in range(200):
        if not t.is_alive():
            break
        server.pump()
        t.join(0.02)
miyagi_bridge.unregister()
res["after"] = server.port()
with open(out, "w") as f:
    json.dump(res, f)
'''


@pytest.mark.skipif(_blender() is None, reason="Blender is not installed")
def test_real_blender_smoke(tmp_path):
    script = tmp_path / "smoke.py"
    script.write_text(SMOKE)
    out = tmp_path / "out.json"
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        free = probe.getsockname()[1]
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY")}
    env["MIYAGI_BLENDER_PORTS"] = str(free)
    env["MIYAGI_ENGINE_TOKEN_DIR"] = str(tmp_path / "tokens")
    argv = [_blender(), "--background", "--factory-startup", "--python", str(script), "--", str(ADDON_DIR), str(out)]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=90, env=env, check=False)
    assert out.exists(), proc.stdout[-2000:] + proc.stderr[-2000:]
    res = json.loads(out.read_text())
    assert res["port"] == free and res["after"] == 0
    status, health = res["health"]
    assert status == 200 and health["app"] == "blender" and health["name"] == "miyagi_bridge"
    assert re.match(r"\d+\.\d+", health["blender"])
    status, st = res["state"]
    assert status == 200 and st["mode"] == "OBJECT" and st["file"] == ""
    assert st["dump"]["dump"] == "dump_scene.py 1" and "Cube" in st["dump"]["objects"]
    assert st["active"] == "Cube" and st["frame_current"] == 1
    status, ui = res["ui"]
    assert status == 200 and ui["origin"] == "bottom-left" and isinstance(ui["windows"], list)


def _blender_ext_cli() -> Path | None:
    """Blender's bundled extension tool (bl_pkg/cli/blender_ext.py); it runs on plain Python, no Blender."""
    exe = _blender()
    if exe is None:
        return None
    hits = sorted(Path(exe).resolve().parents[1].glob("Resources/*/scripts/addons_core/bl_pkg/cli/blender_ext.py"))
    return hits[-1] if hits else None


@pytest.mark.skipif(_blender_ext_cli() is None or sys.version_info < (3, 11), reason="Blender is not installed")
def test_manifest_passes_blenders_own_check():
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY")}
    out = subprocess.run([sys.executable, "-I", str(_blender_ext_cli()), "validate", str(PKG_DIR)],
                         capture_output=True, text=True, timeout=60, env=env, check=False)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "Success" in out.stdout

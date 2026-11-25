"""The miyagi bridge's loopback HTTP server: the tutor reads the open Blender scene through it.

    from miyagi_bridge import server
    port = server.start()          # first free port of MIYAGI_BLENDER_PORTS (default 8801-8809); 0 when none is free
    bpy.app.timers.register(server.pump, first_interval=0.05, persistent=True)
    server.handle("GET", "/health", {"Host": "127.0.0.1"})   # the pure router, (status, body)
    server.stop()

Routes (GET only, JSON, cache-control: no-store):
    /health          who is here: blender version, port, pid, open file. Never needs the token.
    /state           the open file, mode, active / selected objects and a "dump_scene.py 1" scene dump.
    /ops?since=<n>   operators the learner ran (window_manager.operators), each once, with an increasing seq.
    /ui              window, area and region rectangles in raw Blender pixels (origin bottom-left), the mode and
                     active object, each 3D Viewport's visible object boxes and each Properties editor's tabs.

Blender's data may only be read on its main thread. /state and /ui are queued as jobs that pump() (a bpy.app.timers
callback every 0.05 s) runs; the HTTP thread waits at most MAIN_WAIT_S for them, else answers 503 busy. /health and
/ops are served from values pump() cached, so they never touch bpy from the HTTP thread.

Guards (the same as the VS Code companion's refuse() in vscode-ext/extension.js): loopback peers only, no Origin
header, no Sec-Fetch-Site other than "none", a loopback Host (against DNS rebinding). While a live miyagi engine has
written its token (~/.miyagi/engine-tokens/<port>.json, or MIYAGI_ENGINE_TOKEN_DIR), every route but /health needs
X-Miyagi-Token equal to one of them; with no live engine token the routes are open to loopback.

This module imports without bpy: bpy is imported inside the functions that need it (tests pass a fake one).
"""

from __future__ import annotations

import contextlib
import hmac
import json
import os
import queue
import re
import threading
import time
import urllib.parse
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

NAME = "miyagi_bridge"
VERSION = "0.1.0"
HOST = "127.0.0.1"
DEFAULT_PORTS = "8801-8809"
PORTS_ENV = "MIYAGI_BLENDER_PORTS"
TOKEN_DIR_ENV = "MIYAGI_ENGINE_TOKEN_DIR"
TOKEN_HEADER = "x-miyagi-token"
TOKEN_TTL_S = 2.0
MAIN_WAIT_S = 1.5
PUMP_INTERVAL_S = 0.05
OPS_POLL_S = 0.25
OPS_MAX = 200

LOCAL_HOST = re.compile(r"^(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$", re.IGNORECASE)
LOOPBACK_ADDR = re.compile(r"^(127\.\d+\.\d+\.\d+|::1|::ffff:127\.\d+\.\d+\.\d+)$")
OPEN_ROUTES = {"GET /health"}

_lock = threading.Lock()
_httpd: ThreadingHTTPServer | None = None
_thread: threading.Thread | None = None
_port = 0
_jobs: queue.Queue = queue.Queue()
_cache: dict = {"blender": "", "file": ""}
_ops: deque = deque(maxlen=OPS_MAX)
_op_seq = 0
_op_seen: list[tuple[int, str]] = []  # the previous poll's (as_pointer, bl_idname), oldest first
_last_ops_poll = 0.0
_tokens: tuple[float, str, list[str]] = (0.0, "", [])


# ------------------------------------------------------------------ ports

def ports() -> list[int]:
    """MIYAGI_BLENDER_PORTS: "8801-8809" or "8801,8802" (default 8801-8809)."""
    spec = os.environ.get(PORTS_ENV, "").strip() or DEFAULT_PORTS
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        try:
            if "-" in part:
                a, b = (int(x) for x in part.split("-", 1))
                out.extend(range(a, b + 1))
            elif part:
                out.append(int(part))
        except ValueError:
            continue
    return list(dict.fromkeys(p for p in out if 0 < p < 65536))


def port() -> int:
    """The port this bridge listens on, 0 when it is not running."""
    return _port


# ------------------------------------------------------------------ engine token

def token_dir() -> Path:
    return Path(os.environ.get(TOKEN_DIR_ENV) or Path.home() / ".miyagi" / "engine-tokens").expanduser()


def _pid_alive(pid: object) -> bool:
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _read_tokens(folder: Path) -> list[str]:
    """Every live engine's token: <port>.json files whose pid is still running."""
    out: list[str] = []
    try:
        files = sorted(p for p in folder.iterdir() if re.fullmatch(r"\d+\.json", p.name))
    except OSError:
        return out
    for p in files:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue  # half-written or unreadable: skip
        live = isinstance(d, dict) and isinstance(d.get("token"), str) and d["token"] and _pid_alive(d.get("pid"))
        if live and d["token"] not in out:
            out.append(d["token"])
    return out


def live_tokens() -> list[str]:
    """The live engine tokens, re-read at most every TOKEN_TTL_S (and at once when the folder changes)."""
    global _tokens
    folder = token_dir()
    now = time.monotonic()
    at, where, toks = _tokens
    if where != str(folder) or now - at >= TOKEN_TTL_S:
        toks = _read_tokens(folder)
        _tokens = (now, str(folder), toks)
    return toks


def reset_tokens() -> None:
    """Forget the cached tokens (tests, or right after an engine starts)."""
    global _tokens
    _tokens = (0.0, "", [])


def _same_token(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


# ------------------------------------------------------------------ guards

def _lower(headers: dict | None) -> dict[str, str]:
    return {str(k).lower(): str(v) for k, v in (headers or {}).items()}


def refuse(method: str, route: str, headers: dict, remote: str = "127.0.0.1") -> tuple[int, str] | None:
    """Why this request is refused, as (status, error), or None when it may go on."""
    h = _lower(headers)
    if remote and not LOOPBACK_ADDR.match(remote):
        return 403, "not_loopback"
    if h.get("origin"):
        return 403, "origin_not_allowed"
    site = h.get("sec-fetch-site")
    if site and site != "none":
        return 403, "browser_not_allowed"
    if not LOCAL_HOST.match(h.get("host", "")):
        return 403, "host_not_allowed"
    if route not in OPEN_ROUTES:
        live = live_tokens()
        given = h.get(TOKEN_HEADER, "").strip()
        if live and not (given and any(_same_token(t, given) for t in live)):
            return 401, "token_required"
    return None


# ------------------------------------------------------------------ main-thread jobs

class _Job:
    def __init__(self, fn):
        self.fn = fn
        self.done = threading.Event()
        self.cancelled = False
        self.result: dict | None = None
        self.error: str | None = None


def _on_main(fn, wait: float | None = None) -> tuple[int, dict]:
    """Run fn() on Blender's main thread (the next pump()) and return its reply, or 503 busy after `wait`."""
    job = _Job(fn)
    _jobs.put(job)
    if not job.done.wait(MAIN_WAIT_S if wait is None else wait):
        job.cancelled = True
        return 503, {"ok": False, "error": "busy"}
    if job.error is not None:
        return 500, {"ok": False, "error": "internal", "detail": job.error}
    return 200, job.result or {"ok": True}


def _run_jobs() -> None:
    while True:
        try:
            job = _jobs.get_nowait()
        except queue.Empty:
            return
        if job.cancelled:
            continue
        try:
            job.result = job.fn()
        except Exception as err:  # noqa: BLE001 - a broken job answers 500, it never stops the timer
            job.error = f"{type(err).__name__}: {err}"
        job.done.set()


# ------------------------------------------------------------------ bpy readers (main thread only)

def _scene_dump():
    """The scene dumper next to this file (miyagi_bridge.scene_dump), imported only when /state asks."""
    if __package__:
        from . import scene_dump

        return scene_dump
    import importlib

    return importlib.import_module("scene_dump")


def _refresh_cache() -> None:
    import bpy

    _cache["blender"] = str(getattr(bpy.app, "version_string", "") or "")
    _cache["file"] = str(getattr(bpy.data, "filepath", "") or "")


def _selected_names(view_layer) -> list[str]:
    out = []
    for ob in getattr(view_layer, "objects", None) or []:
        try:
            if ob.select_get(view_layer=view_layer):
                out.append(ob.name)
        except Exception:  # noqa: BLE001, S112 - an object outside this view layer
            continue
    return out


def state_payload() -> dict:
    """The /state reply. Main thread only."""
    import bpy

    ctx = bpy.context
    view_layer = getattr(ctx, "view_layer", None)
    active = getattr(getattr(view_layer, "objects", None), "active", None)
    scene = getattr(ctx, "scene", None)
    return {
        "ok": True,
        "app": "blender",
        "port": _port,
        "file": str(getattr(bpy.data, "filepath", "") or ""),
        "dirty": bool(getattr(bpy.data, "is_dirty", False)),
        "mode": str(getattr(ctx, "mode", "") or "OBJECT"),
        "active": active.name if active is not None else None,
        "selected": _selected_names(view_layer),
        "frame_current": int(getattr(scene, "frame_current", 0) or 0),
        "dump": _scene_dump().dump(ctx),
    }


def _rect(x) -> dict:
    return {"x": int(x.x), "y": int(x.y), "width": int(x.width), "height": int(x.height)}


def _ui_geom():
    """The pure projection helpers next to this file (miyagi_bridge.ui_geom)."""
    if __package__:
        from . import ui_geom

        return ui_geom
    import importlib

    return importlib.import_module("ui_geom")


MAX_UI_OBJECTS = 200        # object boxes per 3D Viewport
MAX_UI_SCAN = 5000          # objects looked at per 3D Viewport (a huge scene must not stall the main thread)
POINT_TYPES = frozenset({"LIGHT", "CAMERA", "EMPTY", "SPEAKER", "LIGHT_PROBE", "LIGHTPROBE"})
_CONTEXTS = re.compile(r"not found in \(([^)]*)\)")


def _space(area):
    return getattr(getattr(area, "spaces", None), "active", None)


def _visible(ob, space, view_layer=None) -> bool:
    """Visible in this viewport (local view, viewport-hidden collections) of this window's view layer."""
    try:
        if view_layer is not None:
            return bool(ob.visible_get(view_layer=view_layer, viewport=space))
        return bool(ob.visible_get(viewport=space))
    except TypeError:
        return bool(ob.visible_get())


def _view3d_objects(ctx, area, view_layer=None) -> list[dict] | None:
    """The boxes of the visible objects in one single-view 3D Viewport, in window pixels (bottom-left, like the area):
    [{name, type, x, y, width, height}], at most MAX_UI_OBJECTS. view_layer: the area's window's own (a second main
    window may show another scene or view layer); None: the context's. None: no space / region_3d / WINDOW region, or
    a quad view (four regions: a box could be on any of them). A broken object is skipped; this never raises."""
    try:
        geom = _ui_geom()
        space = _space(area)
        rv3d = getattr(space, "region_3d", None)
        if space is None or rv3d is None or list(getattr(space, "region_quadviews", None) or []):
            return None
        region = next((r for r in area.regions if str(r.type) == "WINDOW"), None)
        if region is None or int(region.width) <= 0 or int(region.height) <= 0:
            return None
        persmat = geom.matrix(rv3d.perspective_matrix)
        rw, rh = float(region.width), float(region.height)
        view_layer = view_layer if view_layer is not None else getattr(ctx, "view_layer", None)
        objects = getattr(view_layer, "objects", None) or []
    except Exception:  # noqa: BLE001 - no boxes rather than a 500
        return None
    out: list[dict] = []
    for i, ob in enumerate(objects):
        if i >= MAX_UI_SCAN or len(out) >= MAX_UI_OBJECTS:
            break
        try:
            if not _visible(ob, space, view_layer):
                continue
            kind = str(ob.type)
            mw = geom.matrix(ob.matrix_world)
            if kind in POINT_TYPES:
                box = geom.point_box(geom.apply(mw, (0.0, 0.0, 0.0)), persmat, rw, rh)
            else:
                box = geom.object_box([geom.apply(mw, c) for c in ob.bound_box], persmat, rw, rh)
            if box is None:
                continue
            x, y, w, h = box
            out.append({"name": str(ob.name), "type": kind, "x": round(float(region.x) + x, 1),
                        "y": round(float(region.y) + y, 1), "width": round(w, 1), "height": round(h, 1)})
        except Exception:  # noqa: BLE001, S112 - a broken object is left out
            continue
    return out


def _contexts(space) -> list[str] | None:
    """The Properties editor's tabs available now, in order. Blender has no API for its dynamic context enum, but an
    invalid value is refused before anything is set and the refusal lists them: read that, change nothing."""
    try:
        old = space.context
        try:
            space.context = "__miyagi_probe__"
        except TypeError as err:
            m = _CONTEXTS.search(str(err))
            got = re.findall(r"'([A-Z_]+)'", m.group(1)) if m else []
            return got or None
        space.context = old  # not real Blender (a fake took the value): put it back
        return None
    except Exception:  # noqa: BLE001 - no list rather than a 500
        return None


def _properties(area) -> dict | None:
    """A Properties editor: {context: the tab shown, tabs: its NAVIGATION_BAR (the tab column) rect or None,
    contexts: the tabs available now, in order (left out when unreadable)}."""
    space = _space(area)
    if space is None or not isinstance(getattr(space, "context", None), str):
        return None
    nav = next((r for r in area.regions if str(r.type) == "NAVIGATION_BAR"), None)
    out: dict = {"context": str(space.context), "tabs": _rect(nav) if nav is not None else None}
    if (ctxs := _contexts(space)) is not None:
        out["contexts"] = ctxs
    return out


def _area_payload(ctx, area, view_layer=None) -> dict:
    regions = [{"type": str(r.type), **_rect(r)} for r in area.regions]
    out = {"type": str(area.type), "ui_type": str(getattr(area, "ui_type", area.type)), **_rect(area),
           "regions": regions}
    if out["type"] == "VIEW_3D" and (objs := _view3d_objects(ctx, area, view_layer)) is not None:
        out["objects"] = objs
    elif out["type"] == "PROPERTIES":
        with contextlib.suppress(Exception):
            if (props := _properties(area)) is not None:
                out["properties"] = props
    return out


def _active_name(ctx) -> str | None:
    try:
        active = getattr(getattr(getattr(ctx, "view_layer", None), "objects", None), "active", None)
        return str(active.name) if active is not None else None
    except Exception:  # noqa: BLE001
        return None


def ui_payload() -> dict:
    """The /ui reply: every window's areas and regions in raw Blender pixels, the mode and active object, each
    single-view 3D Viewport's object boxes and each Properties editor's tab column. Main thread only."""
    import bpy

    ctx = bpy.context
    system = getattr(getattr(ctx, "preferences", None), "system", None)
    windows = []
    for win in getattr(ctx.window_manager, "windows", None) or []:
        screen = getattr(win, "screen", None)
        try:  # each window shows its own scene / view layer: its objects, never the context window's
            view_layer = getattr(win, "view_layer", None)
        except Exception:  # noqa: BLE001
            view_layer = None
        areas = [_area_payload(ctx, area, view_layer) for area in getattr(screen, "areas", None) or []]
        windows.append({**_rect(win), "screen": str(getattr(screen, "name", "")),
                        "workspace": str(getattr(getattr(win, "workspace", None), "name", "")), "areas": areas})
    return {
        "ok": True,
        "pixel_size": float(getattr(system, "pixel_size", 1.0) or 1.0),
        "ui_scale": float(getattr(system, "ui_scale", 1.0) or 1.0),
        "origin": "bottom-left",
        "mode": str(getattr(ctx, "mode", "") or "OBJECT"),
        "active": _active_name(ctx),
        "windows": windows,
    }


# ------------------------------------------------------------------ operators

def py_idname(bl_idname: str) -> str:
    """MESH_OT_primitive_torus_add -> mesh.primitive_torus_add (already dotted names pass through)."""
    if "_OT_" in bl_idname:
        mod, rest = bl_idname.split("_OT_", 1)
        return f"{mod.lower()}.{rest}"
    return bl_idname


def _json_value(v):
    """A JSON scalar or list for one operator property, or None when it has no plain value."""
    if isinstance(v, bool) or v is None or isinstance(v, (int, str)):
        return v
    if isinstance(v, float):
        return round(v, 6)
    if isinstance(v, (set, frozenset)):
        return sorted(str(x) for x in v)
    try:
        items = list(v)
    except TypeError:
        name = getattr(v, "name", None)
        return name if isinstance(name, str) else None
    if all(isinstance(x, (bool, int, float, str)) for x in items):
        return [_json_value(x) for x in items]
    return None


def _op_props(op) -> dict:
    props = getattr(op, "properties", None)
    out: dict = {}
    rna = getattr(props, "bl_rna", None)
    for p in getattr(rna, "properties", None) or []:
        ident = getattr(p, "identifier", "")
        if not ident or ident == "rna_type":
            continue
        try:
            out[ident] = _json_value(getattr(props, ident))
        except Exception:  # noqa: BLE001, S112 - an unreadable property is left out
            continue
    return out


def _new_tail(prev: list, cur: list) -> list:
    """The entries of `cur` that came after `prev`. Blender keeps window_manager.operators as an append-only list
    that drops its oldest entries (about 32 are kept), so `cur` is a tail of `prev` plus new ones: the new ones are
    what follows the longest start of `cur` that matches the end of `prev`, or all of `cur` when nothing matches
    (the list was cleared, or more ops ran than it holds). Matching the order, not a set of pointers, keeps an op
    whose memory reuses a just-freed op's address."""
    for m in range(min(len(prev), len(cur)), 0, -1):
        if cur[:m] == prev[-m:]:
            return cur[m:]
    return cur


def _op_entry(op) -> dict:
    return {"idname": py_idname(str(op.bl_idname)), "name": str(getattr(op, "name", "")), "props": _op_props(op),
            "t": time.time()}


def poll_ops(operators) -> int:
    """Append the operators registered since the previous poll to the ops deque. Returns how many were added.
    An unreadable op (for example a freed RNA struct raising ReferenceError) is skipped, never reported twice."""
    global _op_seq, _op_seen
    try:
        listed = list(operators or [])
    except Exception:  # noqa: BLE001 - keep the previous snapshot; try again next poll
        return 0
    ops, snap = [], []
    for op in listed:
        try:
            key = (int(op.as_pointer()), str(op.bl_idname))
        except Exception:  # noqa: BLE001, S112 - not an operator, or already freed
            continue
        ops.append(op)
        snap.append(key)
    added = 0
    try:
        fresh = len(_new_tail(_op_seen, snap))
        for op in ops[len(ops) - fresh:] if fresh else []:
            try:
                entry = _op_entry(op)
            except Exception:  # noqa: BLE001, S112 - freed while we read it: left out
                continue
            with _lock:
                _op_seq += 1
                _ops.append({"seq": _op_seq, **entry})
            added += 1
    finally:
        _op_seen = snap
    return added


def ops_since(since: int) -> dict:
    with _lock:
        return {"ok": True, "last_seq": _op_seq, "ops": [dict(o) for o in _ops if o["seq"] > since]}


def reset_ops() -> None:
    """Tests only."""
    global _op_seq, _op_seen, _last_ops_poll
    with _lock:
        _ops.clear()
        _op_seq = 0
        _op_seen = []
        _last_ops_poll = 0.0


# ------------------------------------------------------------------ timer

def pump() -> float | None:
    """The bpy.app.timers callback: run queued main-thread jobs, refresh the cached file and version, and read new
    operators every OPS_POLL_S. Never raises (a raising timer is dropped by Blender). Returns the next interval."""
    global _last_ops_poll
    _run_jobs()
    with contextlib.suppress(Exception):
        _refresh_cache()
    now = time.monotonic()
    if now - _last_ops_poll >= OPS_POLL_S:
        _last_ops_poll = now
        with contextlib.suppress(Exception):
            import bpy

            poll_ops(getattr(bpy.context.window_manager, "operators", None))
    return PUMP_INTERVAL_S


# ------------------------------------------------------------------ router

def health_payload() -> dict:
    return {"ok": True, "app": "blender", "name": NAME, "version": VERSION, "blender": _cache["blender"],
            "port": _port, "pid": os.getpid(), "file": _cache["file"]}


def _since(query: str) -> int:
    try:
        return int((urllib.parse.parse_qs(query).get("since") or ["0"])[0])
    except ValueError:
        return 0


def handle(method: str, path: str, headers: dict, remote: str = "127.0.0.1") -> tuple[int, dict]:
    """Route one request: (status, JSON body). Pure apart from the main-thread wait for /state and /ui."""
    url = urllib.parse.urlsplit(path or "/")
    route = f"{method.upper()} {url.path}"
    no = refuse(method, route, headers, remote)
    if no:
        return no[0], {"ok": False, "error": no[1]}
    if route == "GET /health":
        return 200, health_payload()
    if route == "GET /ops":
        return 200, ops_since(_since(url.query))
    if route == "GET /state":
        return _on_main(state_payload)
    if route == "GET /ui":
        return _on_main(ui_payload)
    return 404, {"ok": False, "error": "no_route", "route": route}


# ------------------------------------------------------------------ HTTP

class _Handler(BaseHTTPRequestHandler):
    server_version = "miyagi-bridge"

    def log_message(self, *args):  # quiet: Blender's console is the learner's
        pass

    def _serve(self):
        status, body = handle(self.command, self.path, dict(self.headers.items()), self.client_address[0])
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(data)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    do_GET = _serve
    do_POST = _serve
    do_PUT = _serve
    do_DELETE = _serve


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False  # two Blenders must never share a port


def _bind(p: int) -> _Server | None:
    try:
        return _Server((HOST, p), _Handler)
    except OSError:
        return None


def start(port: int | None = None) -> int:
    """Start serving on 127.0.0.1: `port` when given (0 = any free one), else the first free port of
    MIYAGI_BLENDER_PORTS. Returns the port, or 0 when none could be bound. A second call keeps the running server."""
    global _httpd, _thread, _port
    if _httpd is not None:
        return _port
    with contextlib.suppress(Exception):  # no bpy (tests): the cache stays empty until pump()
        _refresh_cache()
    for p in ([port] if port is not None else ports()):
        srv = _bind(p)
        if srv is not None:
            _httpd, _port = srv, int(srv.server_address[1])
            _thread = threading.Thread(target=srv.serve_forever, name="miyagi-bridge", daemon=True)
            _thread.start()
            return _port
    return 0


def stop() -> None:
    """Stop serving and answer every waiting job busy."""
    global _httpd, _thread, _port
    srv, _httpd, _thread, _port = _httpd, None, None, 0
    if srv is not None:
        srv.shutdown()
        srv.server_close()
    while True:
        try:
            job = _jobs.get_nowait()
        except queue.Empty:
            break
        job.cancelled = True

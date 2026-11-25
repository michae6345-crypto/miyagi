"""Client for the miyagi bridge Blender add-on (blender-addon/miyagi_bridge): the open scene, read exactly, no OCR.

    from server.workspace import blender_ext as bx
    bx.health()                       # the first Blender with the bridge: {app, name, version, blender, port, pid, file}
    bx.instances()                    # every one, in port order
    st = bx.state(blend_path)         # the /state of the Blender that has blend_path open (None: no such Blender)
    doc = bx.live_state(blend_path)   # just its "dump_scene.py 1" scene dump, the format of X.scene.json
    bx.recent_ops(since=seq)          # operators the learner ran: [{seq, idname, name, props, t}]
    bx.ui_rects()                     # window / area / region rectangles in raw Blender pixels (origin bottom-left)
    bx.launch_argv(blend_path)        # [blender, blend, "--python", start_bridge.py]: argv only, nothing runs it

Every call is synchronous and returns None ([] for instances()) when no Blender answers: the add-on not running,
Blender closed, a timeout, a non-2xx reply or bad JSON. Nothing raises. /health, /ops and /ui are capped at TIMEOUT_S
(0.3 s); /state at STATE_TIMEOUT_S (2 s), since the bridge computes it on Blender's main thread. From async code:
`await asyncio.to_thread(bx.live_state, path)`.

Each Blender runs its own bridge on the next free port from 8801 (MIYAGI_BLENDER_PORTS, default "8801-8809"). Every
call carries X-Miyagi-Token when the engine has a token (vscode_ext.link_token()): the bridge requires it on every
route but /health while a live engine has written one.
"""

from __future__ import annotations

import http.client
import json
import logging
import os
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, wait
from concurrent.futures import TimeoutError as FutureTimeout
from pathlib import Path

from server.workspace import vscode_ext

log = logging.getLogger("server.workspace.blender_ext")

REPO_ROOT = Path(__file__).resolve().parents[2]
BRIDGE_START = REPO_ROOT / "blender-addon" / "start_bridge.py"
HOST = "127.0.0.1"
DEFAULT_PORTS = "8801-8809"
PORTS_ENV = "MIYAGI_BLENDER_PORTS"
TIMEOUT_S = 0.3
STATE_TIMEOUT_S = 2.0
DUMP_FORMAT = "dump_scene.py 1"
MAX_RESPONSE = 32 * 1024 * 1024

_POOL = ThreadPoolExecutor(max_workers=12, thread_name_prefix="blender-ext")


# ------------------------------------------------------------------ transport

def ports() -> list[int]:
    """MIYAGI_BLENDER_PORTS: "8801-8809" or "8801,8802" (default 8801-8809)."""
    spec = os.environ.get(PORTS_ENV, "").strip() or DEFAULT_PORTS
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part:
                a, b = (int(x) for x in part.split("-", 1))
                out.extend(range(a, b + 1))
            else:
                out.append(int(part))
        except ValueError:
            log.warning("ignoring bad %s entry %r", PORTS_ENV, part)
    return list(dict.fromkeys(p for p in out if 0 < p < 65536))


def _headers() -> dict[str, str]:
    tok = vscode_ext.link_token()
    return {"X-Miyagi-Token": tok} if tok else {}


def _get(port: int, path: str, timeout: float) -> dict | None:
    """GET one route on one port: the JSON object of a 2xx reply, else None."""
    conn = http.client.HTTPConnection(HOST, port, timeout=timeout)
    try:
        conn.request("GET", path, headers=_headers())
        resp = conn.getresponse()
        raw = resp.read(MAX_RESPONSE)
        if not 200 <= resp.status < 300:
            return None
        out = json.loads(raw) if raw else None
        return out if isinstance(out, dict) else None
    except (OSError, http.client.HTTPException, ValueError):
        return None
    finally:
        conn.close()


def _call(port: int, path: str, timeout: float = TIMEOUT_S) -> dict | None:
    """One GET, hard-capped at `timeout` for the caller (the worker thread may finish a little later)."""
    fut = _POOL.submit(_get, port, path, timeout)
    try:
        return fut.result(timeout=timeout)
    except FutureTimeout:
        return None
    except Exception:
        log.exception("blender-ext GET %s failed", path)
        return None


# ------------------------------------------------------------------ instances

def instances(timeout: float = TIMEOUT_S) -> list[dict]:
    """Every Blender with the bridge: its /health, scanned on all ports at once, in port order. [] when none."""
    futs = [(p, _POOL.submit(_get, p, "/health", timeout)) for p in ports()]
    done, _ = wait([f for _, f in futs], timeout=timeout)
    out = []
    for _, f in futs:
        if f in done and f.exception() is None:
            h = f.result()
            if isinstance(h, dict) and h.get("app") == "blender" and h.get("port"):
                out.append(h)
    return out


def health(timeout: float = TIMEOUT_S) -> dict | None:
    """The first Blender with the bridge, or None."""
    found = instances(timeout)
    return found[0] if found else None


def same_file(a: str | Path | None, b: str | Path | None) -> bool:
    """True when both name the same file (after ~ and symlinks); never for an empty path."""
    if not a or not b:
        return False
    try:
        return Path(a).expanduser().resolve() == Path(b).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return False


def pick(found: list[dict], blend_path: str | Path | None = None) -> dict | None:
    """The instance with blend_path open, or the first one when blend_path is None."""
    if blend_path is None:
        return found[0] if found else None
    return next((h for h in found if same_file(h.get("file"), blend_path)), None)


# ------------------------------------------------------------------ routes

def state(blend_path: str | Path | None = None, timeout: float = STATE_TIMEOUT_S) -> dict | None:
    """The full /state of the Blender that has blend_path open (any Blender when None), or None."""
    h = pick(instances(), blend_path)
    if h is None:
        return None
    st = _call(int(h["port"]), "/state", timeout)
    if not st or st.get("app") != "blender":
        return None
    if blend_path is not None and not same_file(st.get("file"), blend_path):
        return None  # it opened another file between /health and /state
    return st


def live_state(blend_path: str | Path | None = None, timeout: float = STATE_TIMEOUT_S) -> dict | None:
    """Just the scene dump of state(): a "dump_scene.py 1" dict, the format X.scene.json holds. None otherwise."""
    doc = (state(blend_path, timeout) or {}).get("dump")
    return doc if isinstance(doc, dict) and doc.get("dump") == DUMP_FORMAT else None


def recent_ops(since: int = 0, timeout: float = TIMEOUT_S) -> list[dict] | None:
    """Operators the learner ran in the first Blender with the bridge, those with seq > since. None: no Blender."""
    h = health(timeout)
    if h is None:
        return None
    reply = _call(int(h["port"]), "/ops?" + urllib.parse.urlencode({"since": int(since)}), timeout)
    ops = (reply or {}).get("ops")
    return ops if isinstance(ops, list) else None


def ui_rects(timeout: float = TIMEOUT_S) -> dict | None:
    """The first Blender's /ui in raw Blender pixels (origin bottom-left, x / y relative to the window), or None:

        {pixel_size, ui_scale, origin, mode, active,
         windows: [{x, y, width, height, screen, workspace, areas: [{type, ui_type, x, y, width, height,
             regions: [{type, x, y, width, height}],
             objects?: [{name, type, x, y, width, height}],          # a single-view 3D Viewport: visible boxes
             properties?: {context, tabs: {x, y, width, height} | None, contexts?: [str]}}]}]}  # a Properties editor

    None also for a reply whose windows is not a list of objects (server.screen.app_target checks the rest)."""
    h = health(timeout)
    if h is None:
        return None
    reply = _call(int(h["port"]), "/ui", timeout)
    wins = (reply or {}).get("windows")
    if not isinstance(wins, list) or not all(isinstance(w, dict) for w in wins):
        return None
    return reply


# ------------------------------------------------------------------ launch

def _find_blender() -> str | None:
    try:
        from server.workspace.blender import find_blender

        return find_blender()
    except Exception:  # noqa: BLE001 - the dump lane's finder is not here yet, or it failed
        return None


def launch_argv(blend_path: str | Path, *, blender: str | None = None) -> list[str] | None:
    """The argv that opens blend_path in the learner's own Blender with the bridge started, or None when no Blender
    is found. No --background, no --factory-startup. Argv only: nothing here runs it."""
    exe = blender or _find_blender()
    if not exe:
        return None
    return [str(exe), os.path.abspath(os.path.expanduser(str(blend_path))), "--python", str(BRIDGE_START)]

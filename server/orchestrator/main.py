"""Engine hub: FastAPI app on :8787.

  WS   /                 events.ts protocol ({type, payload} JSON both ways)
  POST /ingest           `tut run` events (one object, a list, or {"events": [...]})
  POST /end              end the current lesson (curl -X POST localhost:8787/end)
  GET  /state            session state (debugging, the CLI client's simulator)
  GET  /health           liveness; ?checks=1 adds the setup checklist {items, ready, total} (health.py, never prompts)
  GET  /library          lessons cached on this Mac {items, continue} (lesson/library.py)
  GET  /library/{id}     one lesson's preview {item, steps, overview}; 404 for a bad or unknown id
  GET  /progress         skills, finished and in-progress lessons (sessions/progress.py); null = nothing yet
  GET  /events?since=N   the hub's recent history, every session event (dev only)
  POST /debug/pass       force-pass the active step            (dev only: MIYAGI_DEBUG_ROUTES=1 or DEMO=1, else 404)
  POST /debug/goto/{i}   jump to step i                       (dev only)
  POST /debug/lesson     DEMO only: load the cached/canned lesson without searching (dev only)
  GET  /demo/runs, POST /demo/replay   recorded `tut run` replays (dev only)
  GET  /stage            is a Demo lesson running (launcher → Demo, or MIYAGI_STAGE=1; stage.py)
  POST /stage/{cmd}      presenter, Demo lessons only: next | back | restart

Run:  python -m server.orchestrator.main      (or uvicorn server.orchestrator.main:app --port 8787)

v2 (BUILD-PLAN E2): every WebSocket connect starts with `engine.hello {version, contract, capabilities, restored?}`;
the app sends a v2 command only when `capabilities` lists it. Security (BUILD-PLAN section 6):
  - Host: every HTTP request and WebSocket must name this Mac (localhost, 127.0.0.1, [::1]; when bound off loopback,
    also that host, <hostname>.local and MIYAGI_ALLOWED_HOSTS), else 403 / close 1008. Closes DNS rebinding.
  - Bind: 127.0.0.1 unless ENGINE_HOST / --host says otherwise (an empty ENGINE_HOST is loopback too).
  - MIYAGI_ENGINE_TOKEN (the app's per-launch token): when set, a WebSocket must carry it in X-Miyagi-Token, or it is
    refused before the handshake; so must every POST/PUT/PATCH/DELETE (/ingest, /vscode/event, /end, /stage/*, ...),
    from this Mac too, and any HTTP request from another machine (ENGINE_HOST=0.0.0.0). Loopback GETs (/health,
    /state, /library) need none. It is read once and removed from os.environ, so no learner subprocess inherits it.
    run() writes the token (or, with none set, a fresh random one) to ~/.miyagi/engine-tokens/<port>.json (0600,
    server/engine_token.py) for the VS Code companion, `tut run` and the dev CLI, and removes it on exit.
  - Dev routes (/debug/*, /demo/*, /events) answer 404 unless MIYAGI_DEBUG_ROUTES=1 or DEMO=1: the app's engine (localEngine.ts)
    sets neither, so a release build never serves them.
  - Origin: a request that carries an Origin header (a browser page) must come from this Mac (http(s)://localhost,
    127.0.0.1, [::1]) or MIYAGI_ALLOWED_ORIGINS; a POST/PUT/PATCH/DELETE carrying one only from MIYAGI_ALLOWED_ORIGINS.
    Native clients (the app's main process, the VS Code companion, `tut run`, curl) send none.
  - POST bodies are JSON only (415 otherwise); a POST with no body (curl -X POST .../end) still works.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import hmac
import ipaddress
import logging
import math
import os
import re
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit

from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from shared.contracts import events as contract
from shared.contracts.events import parse_app_message

from server import config as server_config

from . import config, recorder, stage
from .hub import Hub, log_received
from .modules import Modules
from .screen_bridge import ScreenBridge
from .session import LessonSession
from .watcher import Watcher
from .inputs import Inputs
from .workspace import Workspace

log = logging.getLogger("orchestrator")

# E1's modules (pure reads, no model calls). Each is optional: an engine without one doesn't list its commands.
try:
    from . import health as health_mod
except Exception as _e:  # noqa: BLE001
    log.warning("health checks unavailable: %s", _e)
    health_mod = None  # type: ignore[assignment]
try:
    from . import system_status as status_mod
except Exception as _e:  # noqa: BLE001
    log.warning("system status unavailable: %s", _e)
    status_mod = None  # type: ignore[assignment]
try:
    from server.lesson import library as library_mod
except Exception as _e:  # noqa: BLE001
    log.warning("lesson library unavailable: %s", _e)
    library_mod = None  # type: ignore[assignment]
try:
    from server.sessions import progress as progress_mod
except Exception as _e:  # noqa: BLE001
    log.warning("progress unavailable: %s", _e)
    progress_mod = None  # type: ignore[assignment]
try:
    from server.sessions import review as review_mod
except Exception as _e:  # noqa: BLE001
    log.warning("spaced review unavailable: %s", _e)
    review_mod = None  # type: ignore[assignment]


# ============================================================================ v2 wire (BUILD-PLAN E2)
def _engine_version() -> str:
    try:
        text = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
        m = re.search(r'^version\s*=\s*"([^"]{1,32})"', text, re.M)
        return m.group(1) if m else "dev"
    except OSError:
        return "dev"


ENGINE_VERSION = _engine_version()
CONTRACT_VERSION = getattr(contract, "CONTRACT_VERSION", None) or "2026-11-20"  # W0-1: the shapes this engine sends
V2_COMMANDS = ("health.get", "permission.open", "library.list", "library.get", "library.start", "progress.get",
               "panel.state", "review.start", "data.delete")
# answered at once, beside the command queue (reads, a layout note); library.start / review.start change the lesson, so
# they queue
V2_INSTANT = frozenset(V2_COMMANDS) - {"library.start", "review.start"}
INSTANT = frozenset({"video.state", "overlay.bounds", "end_lesson", "card.shown", "card.closed"})
LESSON_STARTS = frozenset({"learn", "learn_url", "build_lesson", "library.start", "review.start"})  # each replaces a running build
# Nov 21 (launch-quiet): what counts as the learner asking for a lesson on this connection (session.learner_asked)
LEARNER_ASKS = LESSON_STARTS
LEARNER_ASK_ACTIONS = frozenset({"start", "resume", "build"})  # Start, Continue, the preflight card's Build (a pick)
SECRET_COMMANDS = frozenset({"config.keys", "config.validate"})  # payloads hold keys: never logged, never echoed
PERMISSION_KINDS = ("screen", "accessibility", "automation")
LIBRARY_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
TOKEN_HEADER = "x-miyagi-token"
TOKEN_ENV = "MIYAGI_ENGINE_TOKEN"
_CONTRACT_COMMANDS: dict = getattr(contract, "APP_COMMANDS", {})

# fixed copy: no input echoed back, no em dashes
KEYS_FAILED = "Couldn't read those keys. Check them and try again."
V2_FAILED = "Couldn't answer that just now. Try again."
LIBRARY_GONE = "That lesson isn't on this Mac any more."
REVIEW_GONE = "That review isn't ready. Try again after your next lesson."
LIBRARY_FAILED = "Couldn't start this lesson. Try again."


def _take_token() -> str | None:
    """The app's per-launch engine token (main/localEngine.ts passes it in the environment). Read once, then removed
    from os.environ: kernels, "Run it for me", pip and VS Code terminals start from os.environ and never see it."""
    tok = os.environ.pop(TOKEN_ENV, "").strip()
    return tok or None


ENGINE_TOKEN = _take_token()


def token_ok(given: str | None) -> bool:
    """No token configured (an engine started by hand, tests): any local client may connect. Otherwise the header
    must match exactly (constant-time compare; the token is never logged)."""
    if ENGINE_TOKEN is None:
        return True
    return bool(given) and hmac.compare_digest(given.strip().encode(), ENGINE_TOKEN.encode())


_LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1"})
MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})
REFUSED_PAGE = "This page may not call the miyagi engine."
REFUSED_HOST = "This address may not call the miyagi engine."
REFUSED_TOKEN = "Send the engine token (X-Miyagi-Token)."
DEV_PREFIXES = ("/debug/", "/demo/")
# /events hands out the hub's whole history (cards, selections, run and terminal output) to a loopback GET, which needs
# no token: a local program the WebSocket refuses could read the session there. Development only.
DEV_PATHS = frozenset({"/events", "/events/"})
DEBUG_ENV = "MIYAGI_DEBUG_ROUTES"
_bind_host: str | None = None  # run() sets it from --host; else ENGINE_HOST (uvicorn ... --host has no say)


def is_dev_route(path: str) -> bool:
    return path.startswith(DEV_PREFIXES) or path in DEV_PATHS


def debug_routes_on() -> bool:
    """/debug/* and /demo/* (force-pass a step, jump, load a canned lesson, replay a recording) are for development:
    MIYAGI_DEBUG_ROUTES=1, or a DEMO=1 engine. The app's own engine (main/localEngine.ts) sets neither."""
    return os.environ.get(DEBUG_ENV, "").strip() == "1" or config.demo_mode()


def needs_token(method: str, scope: dict) -> bool:
    """With MIYAGI_ENGINE_TOKEN set: every write (from this Mac too: another local program or a learner's script could
    otherwise end the lesson, fake runs into /ingest or fake editor events) and anything from another machine."""
    return ENGINE_TOKEN is not None and (method in MUTATING or not client_is_loopback(scope))


def _csv_env(name: str) -> set[str]:
    return {v.strip().lower().rstrip("/") for v in os.environ.get(name, "").split(",") if v.strip()}


def _extra_origins() -> set[str]:
    return _csv_env("MIYAGI_ALLOWED_ORIGINS")


def _host_name(value: str | None) -> str:
    """The host part of a Host header, lowercased, port and IPv6 brackets dropped ("[::1]:8787" -> "::1")."""
    h = (value or "").strip().lower()
    if h.startswith("["):
        h = h[1:].split("]", 1)[0]
    elif h.count(":") == 1:
        h = h.split(":", 1)[0]
    return h.rstrip(".")


@functools.lru_cache(maxsize=1)
def _mac_names() -> frozenset[str]:
    name = _host_name(socket.gethostname())
    if not name:
        return frozenset()
    base = name[: -len(".local")] if name.endswith(".local") else name
    return frozenset({name, base + ".local"})


def allowed_hosts() -> set[str]:
    """Loopback always. Bound to the LAN (ENGINE_HOST / --host not on loopback): also that host, <this Mac>.local and
    MIYAGI_ALLOWED_HOSTS (comma-separated, e.g. the Mac's LAN IP)."""
    hosts = set(_LOOPBACK)
    bind = _host_name(_bind_host if _bind_host is not None else os.environ.get("ENGINE_HOST", ""))
    if bind and bind not in _LOOPBACK:
        hosts.add(bind)
        hosts |= _mac_names()
        hosts |= {_host_name(h) for h in _csv_env("MIYAGI_ALLOWED_HOSTS")}
    return hosts


def host_allowed(host: str | None) -> bool:
    """DNS rebinding: after a rebind the attacker's page is same-origin and sends no Origin on a GET, but its Host
    header still names the attacker's domain. Only this Mac's own names pass. No Host at all (HTTP/1.0, a raw
    socket) is never a browser, so it passes."""
    if host is None or not host.strip():
        return True
    return _host_name(host) in allowed_hosts()


def client_is_loopback(scope: dict) -> bool:
    client = scope.get("client")
    if not client:
        return False
    try:
        ip = ipaddress.ip_address(str(client[0]).split("%", 1)[0])
    except ValueError:
        return False
    mapped = getattr(ip, "ipv4_mapped", None)
    return (mapped or ip).is_loopback


def origin_allowed(origin: str | None) -> bool:
    """A browser always sends Origin on a WebSocket and on a cross-site request; native clients send none. Only pages
    served from this Mac (the app's own renderer, the dev stage) or MIYAGI_ALLOWED_ORIGINS may read from the engine,
    so a web page elsewhere can't drive it (cross-site WebSocket hijacking). DNS rebinding is host_allowed's job."""
    if origin is None:
        return True
    o = origin.strip().lower().rstrip("/")
    if o in _extra_origins():
        return True
    try:
        u = urlsplit(o)
        host = u.hostname or ""
    except ValueError:
        return False
    return u.scheme in ("http", "https") and host in _LOOPBACK


def write_origin_allowed(origin: str | None) -> bool:
    """POST/PUT/PATCH/DELETE: a bodyless cross-origin POST is a CORS simple request (no preflight), so any page on
    localhost:<any port> (a dev server, Jupyter, a lesson's web project) could end a lesson. Native clients never
    send Origin; a browser page may write only when MIYAGI_ALLOWED_ORIGINS lists it."""
    if origin is None:
        return True
    return origin.strip().lower().rstrip("/") in _extra_origins()


def _shown(origin: str | None) -> str:
    return repr(str(origin)[:80])


def _is_json(content_type: str | None) -> bool:
    media = (content_type or "").split(";", 1)[0].strip().lower()
    return media == "application/json" or (media.startswith("application/") and media.endswith("+json"))


def _refuse(error: str, status: int) -> JSONResponse:
    return JSONResponse({"ok": False, "error": error}, status_code=status)


class RequestGuard:
    """HTTP only (the WebSocket runs the same checks before its handshake), in this order:
      - Host must name this Mac (host_allowed): 403. Closes DNS rebinding.
      - Dev routes (/debug/*, /demo/*) without MIYAGI_DEBUG_ROUTES=1 / DEMO=1: 404, as if they did not exist.
      - With MIYAGI_ENGINE_TOKEN set, every POST/PUT/PATCH/DELETE and every request from another machine
        (ENGINE_HOST=0.0.0.0) must send a matching X-Miyagi-Token: 403 (needs_token). The companion (0.0.7+),
        `tut run` and the dev CLI read it from ~/.miyagi/engine-tokens/<port>.json; loopback GETs need none.
      - Origin: any request carrying one must come from a page on this Mac (origin_allowed); a POST/PUT/PATCH/DELETE
        carrying one must be listed in MIYAGI_ALLOWED_ORIGINS (write_origin_allowed): 403.
      - A write's body must be JSON: 415 (a browser can't send JSON cross-site without a CORS preflight, which this
        engine never answers). A native POST with no body (curl -X POST localhost:8787/end) passes."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}
        method, path = scope.get("method", "GET"), scope.get("path", "")
        origin = headers.get("origin")
        refused: JSONResponse | None = None
        if not host_allowed(headers.get("host")):
            log.warning("refused %s %s for host %s", method, path, _shown(headers.get("host")))
            refused = _refuse(REFUSED_HOST, 403)
        elif is_dev_route(path) and not debug_routes_on():
            log.info("refused %s %s: dev route (set %s=1 to serve it)", method, path, DEBUG_ENV)
            refused = _refuse("Not found.", 404)
        elif needs_token(method, scope) and not token_ok(headers.get(TOKEN_HEADER)):
            _log_token_refusal(method, path, scope, headers)
            refused = _refuse(REFUSED_TOKEN, 403)
        elif not origin_allowed(origin) or (method in MUTATING and not write_origin_allowed(origin)):
            log.warning("refused %s %s from origin %s", method, path, _shown(origin))
            refused = _refuse(REFUSED_PAGE, 403)
        elif method in MUTATING:
            length = headers.get("content-length", "").strip()
            has_body = "transfer-encoding" in headers or length not in ("", "0")
            if has_body and not _is_json(headers.get("content-type")):
                log.warning("refused %s %s: the body is not JSON", method, path)
                refused = _refuse("Send JSON (Content-Type: application/json).", 415)
        if refused is not None:
            await refused(scope, receive, send)
            return
        await self.app(scope, receive, send)


_warned_companion = False


def _log_token_refusal(method: str, path: str, scope: dict, headers: dict) -> None:
    """One line, never the token. A token-less /vscode/event is a VS Code companion older than 0.0.7: said once."""
    global _warned_companion
    why = "wrong token" if headers.get(TOKEN_HEADER) else "no token"
    where = "this Mac" if client_is_loopback(scope) else "another machine"
    if path == "/vscode/event" and not headers.get(TOKEN_HEADER):
        if not _warned_companion:
            _warned_companion = True
            log.warning("refused POST /vscode/event without the engine token: the VS Code companion is older than "
                        "0.0.7 (reinstall it from vscode-ext/); its editor events are ignored until then")
        return
    log.warning("refused %s %s from %s (%s)", method, path, where, why)


def parse_command(raw: dict) -> Any:
    """parse_app_message, plus the v2 commands while this tree's contract (shared/contracts/events.py) predates W0-1.
    Once W0-1 lands, its models parse them (same names, same id pattern) and this fallback is unused."""
    type_ = raw.get("type")
    if type_ in V2_COMMANDS and type_ not in _CONTRACT_COMMANDS:
        return SimpleNamespace(type=type_, payload=_parse_v2(type_, raw.get("payload")))
    return parse_app_message(raw)


def _parse_v2(type_: str, payload: Any) -> SimpleNamespace:
    p = payload if isinstance(payload, dict) else {}
    if type_ == "permission.open":
        if p.get("kind") not in PERMISSION_KINDS:
            raise ValueError("permission.open: unknown kind")
        return SimpleNamespace(kind=p["kind"])
    if type_ in ("library.get", "library.start"):
        lid = p.get("id")
        if not isinstance(lid, str) or not LIBRARY_ID_RE.fullmatch(lid):
            raise ValueError(f"{type_}: not a library id")
        return SimpleNamespace(id=lid)
    if type_ == "review.start":  # {skillId?, label?}: both optional (none = the first review due); bad types read as absent
        def _t(v: Any) -> str:
            return " ".join(v.split())[:80] if isinstance(v, str) else ""

        return SimpleNamespace(skillId=_t(p.get("skillId")), label=_t(p.get("label")))
    if type_ == "panel.state":
        if not isinstance(p.get("open"), bool):
            raise ValueError("panel.state: open must be true or false")
        return SimpleNamespace(open=p["open"], rect=_rect(p.get("rect")))
    return SimpleNamespace()


def _rect(v: Any) -> dict | None:
    if hasattr(v, "model_dump"):
        v = v.model_dump()
    if v is None:
        return None
    if not isinstance(v, dict):
        raise ValueError("panel.state: rect must be {x, y, w, h}")
    out = {}
    for k in ("x", "y", "w", "h"):
        n = v.get(k)
        if isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n):
            raise ValueError("panel.state: rect must be {x, y, w, h}")
        out[k] = float(n)
    return out


# ---- E1 payloads -> the W0-1 contract shapes (app-core-v2 shared/contracts/events.py). E1's own fields stay as
# extras (the contract models allow them); only what the contract requires, or names differently, is added.
HEALTH_LABELS = {"screen": "Screen Recording", "accessibility": "Accessibility", "companion": "VS Code companion",
                 "engine": "miyagi engine", "keys": "AI key", "vscode": "VS Code"}


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def contract_health(h: dict | None) -> dict:
    """health {items: [{id, label, state, detail?, fix?, required, ...}], ready, total}. A `vscode` row is added only
    when E1 knows VS Code is missing (the companion's fix is get_vscode), so the app can offer Get VS Code."""
    h = h if isinstance(h, dict) else {}
    items: list[dict] = []
    for it in h.get("items") or []:
        if not isinstance(it, dict) or not isinstance(it.get("id"), str):
            continue
        row = dict(it)
        row.setdefault("label", HEALTH_LABELS.get(row["id"], row["id"]))
        if isinstance(row.get("version"), str) and "detail" not in row:
            row["detail"] = row["version"]
        items.append(row)
    if (any(r["id"] == "companion" and r.get("fix") == "get_vscode" for r in items)
            and not any(r["id"] == "vscode" for r in items)):
        items.append({"id": "vscode", "label": HEALTH_LABELS["vscode"], "state": "missing", "required": False,
                      "fix": "get_vscode"})
    return {"items": items, "ready": int(_num(h.get("ready")) or 0), "total": int(_num(h.get("total")) or 0)}


def _iso(ts: Any) -> str | None:
    if (t := _num(ts)) is None or t <= 0:
        return None
    try:
        return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    except (OverflowError, OSError, ValueError):
        return None


def _local_date(ts: Any) -> str | None:
    if (t := _num(ts)) is None or t <= 0:
        return None
    try:
        return datetime.fromtimestamp(t).date().isoformat()  # the learner's own calendar day
    except (OverflowError, OSError, ValueError):
        return None


def _progress_of(row: dict) -> dict | None:
    """ContinueItem -> LibraryProgress {stepIndex, stepTitle, total}, only when both numbers are known."""
    i, n = row.get("stepIndex"), row.get("stepCount")
    if not isinstance(i, int) or not isinstance(n, int) or isinstance(i, bool) or isinstance(n, bool):
        return None
    if n <= 0 or not 0 <= i < n:
        return None
    title = row.get("stepTitle")
    return {"stepIndex": i, "stepTitle": title if isinstance(title, str) else "", "total": n}


def contract_library_item(it: dict, progress: dict | None = None) -> dict:
    """LibraryItem {id, title, by?, steps, estMinutes?, tools, ready, progress?, source?, updatedAt? (ISO)}."""
    out = dict(it)
    title = it.get("title") if isinstance(it.get("title"), str) else "Lesson"
    src = it.get("source") if isinstance(it.get("source"), dict) else {}
    if src.get("kind") == "video":
        source: dict[str, Any] = {"kind": "youtube", "title": src.get("title") or title}
        for k, to in (("url", "url"), ("creator", "channel"), ("videoId", "videoId")):
            if isinstance(src.get(k), str):
                source[to] = src[k]
    else:
        source = {"kind": "goal", "title": title}
    out["source"] = source
    if isinstance(src.get("creator"), str) and "by" not in out:
        out["by"] = src["creator"]  # never invented: only when the cache names the channel
    out["ready"] = True  # in the cache: starts with no build
    if (iso := _iso(it.get("updatedAt"))) is not None:
        out["updatedAt"] = iso
    else:
        out.pop("updatedAt", None)
    if progress is not None:
        out["progress"] = progress
    return out


def contract_library(listing: dict | None) -> dict:
    """library {items, continue}: each row in the contract's shape, with its Continue place as `progress`."""
    listing = listing if isinstance(listing, dict) else {}
    cont = [c for c in listing.get("continue") or [] if isinstance(c, dict)]
    by_id = {c["libraryId"]: p for c in cont if isinstance(c.get("libraryId"), str) and (p := _progress_of(c))}
    items = [contract_library_item(it, by_id.get(it["id"])) for it in listing.get("items") or []
             if isinstance(it, dict) and isinstance(it.get("id"), str)]
    return {"items": items, "continue": cont}


def contract_library_detail(found: dict | None) -> dict | None:
    """library.item {item, steps: [OutlineStep {index, title}], overview?}. A step's first check label stays as
    `check` (it is not the step's plan line, so it never poses as `what`)."""
    if not isinstance(found, dict) or not isinstance(found.get("item"), dict):
        return None
    d = dict(found["item"])
    rows = d.pop("stepList", None) or []
    out: dict[str, Any] = {"item": contract_library_item(d)}
    steps = []
    for i, r in enumerate(rows):
        if not isinstance(r, dict) or not isinstance(r.get("title"), str):
            continue
        n = r.get("n")
        step: dict[str, Any] = {"index": n - 1 if isinstance(n, int) and not isinstance(n, bool) and n >= 1 else i,
                                "title": r["title"]}
        if isinstance(r.get("check"), str):
            step["check"] = r["check"]
        steps.append(step)
    out["steps"] = steps
    if isinstance(d.get("overview"), str):
        out["overview"] = d["overview"]
    return out


def contract_progress(p: dict | None) -> dict:
    """progress {skills: [{track, mastered, total, items: [{label, state}]}], completed: [{lessonId, title, at}]}.
    Nothing recorded yet: {} (the app's empty states). No week field: nothing records it. `review` {due, items} is the
    spaced-review schedule (sessions/review.py), present only when a skill has been mastered."""
    if not isinstance(p, dict):
        return {}
    skills = []
    for t in p.get("skills") or []:
        if not isinstance(t, dict):
            continue
        row = {k: v for k, v in t.items() if k != "skills"}
        row["items"] = [dict(s) for s in t.get("skills") or t.get("items") or [] if isinstance(s, dict)]
        skills.append(row)
    completed = []
    for c in p.get("completed") or []:
        if not isinstance(c, dict):
            continue
        row = dict(c)
        row["at"] = _local_date(c.get("finishedAt")) or ""  # "": finished, day unknown (never a made-up date)
        completed.append(row)
    out: dict[str, Any] = {"skills": skills, "completed": completed}
    if isinstance(p.get("inProgress"), list):
        out["inProgress"] = p["inProgress"]
    if isinstance(p.get("review"), dict):  # additive: spaced review {due, items} (sessions/review.py), only once a skill is mastered
        out["review"] = p["review"]
    return out


def _library_folder(graph: dict) -> str:
    """The lesson folder for a library start, made with no model call: S2's folder for this lesson (found without
    writing, as the preflight card finds it), else ~/miyagi/lessons/<slug>. The cached graph's own workdir is a path
    from the Mac that built it and is never used. Blocking: run it in a thread."""
    from . import workspace as wsmod

    lesson = graph.get("lesson") or {}
    if os.environ.get("TUT_WORKDIR"):
        return str(config.default_workdir())
    folder = wsmod.lesson_folder(graph)
    path = Path(folder) if folder else config.lesson_workdir("", str(lesson.get("title") or lesson.get("id") or ""))
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


READ_TTL_S = 1.0  # library.list / progress.get repeats inside this window share one disk read


class Engine:
    def __init__(self) -> None:
        self.hub = Hub()
        self.modules = Modules()
        self.screen = ScreenBridge()
        self.workspace = Workspace()
        self.session = LessonSession(self._emit, self.modules, screen=self.screen, workspace=self.workspace,
                                     inputs=Inputs())
        self.session.has_clients = lambda: bool(self.hub.clients)  # E4: only an app shows "Before you start"
        # Nov 21 (launch-quiet): nothing asked yet: VS Code never opens under "Before you start" until the learner
        # asks on a connection (dispatch: learn / pick / library.start / action start or resume)
        self.session.learner_asked = False
        # Nov 21 (launch-quiet review): the saved-lesson card after library.list goes at most once per connection
        # (the app asks for its library on every launcher / library open) and never again in this engine run once the
        # learner answered it (Continue / Start new) or closed it
        self._offered_to: set[Any] = set()
        self._offer_answered = False
        # E7: the app left: no screen reading / looks / cards (an engine that never had one, e.g. rehearse_boxes, goes on)
        self.session.app_left = lambda: not self.hub.clients and self.last_client_gone is not None
        self.watcher = Watcher(self.session.on_file_change, interval=config.WATCH_INTERVAL_S)
        self.session.on_workdir = self.watcher.set_root
        # E14: no off-track to an app that left (headless runs that never had an app still get them, e.g. /events)
        self.session.has_client = lambda: bool(self.hub.clients) or self.last_client_gone is None
        try:  # S7: progress saved to ~/miyagi/state; "Continue where you left off?" survives an engine restart
            from server.sessions import Resumer

            self.resumer = Resumer(self.session)
        except Exception as e:  # noqa: BLE001
            log.warning("saved-session resume unavailable: %s", e)
            self.resumer = None
        self.recorder = recorder.Recorder()
        self._ticker: asyncio.Task | None = None
        self._avoider: asyncio.Task | None = None  # t9: screen.avoid (quick_pick.py)
        self._replays: set[asyncio.Task] = set()
        self.last_client_gone: float | None = None
        self.seen_lesson: str | None = None  # lesson id an app has already been shown
        # E1's poller (network / AI busy / health, sent on change only). Started by the first v2 command, so an older
        # app (or a test) never makes it probe; its events go out only to a v2 app.
        self.status: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._cloud_off: Any = None  # removes the cloud verdict listener (watch_cloud)
        self._cloud_tasks: set[asyncio.Task] = set()
        self._screen_boot: asyncio.Task | None = None
        self.hub.on_progress_event = self.forget_reads
        self._reads: dict[str, tuple[float, Any]] = {}  # coalesced app reads: key -> (when, result)
        self._reads_inflight: dict[str, asyncio.Future] = {}
        self._reads_gen = 0  # bumped by forget_reads: an older in-flight read must not cache its stale result

    def _lesson_id(self) -> str | None:
        return (self.session.graph or {}).get("lesson", {}).get("id")

    def mark_lesson_seen(self) -> None:
        if self._lesson_id():
            self.seen_lesson = self._lesson_id()

    def app_returning(self) -> bool:
        """The app reconnects after being away (>= ORCH_RESUME_AFTER_S with no client) to a lesson it had
        already shown: offer "Continue / Start new". A first connection (e.g. the demo's autostart) or a
        quick network blip just continues."""
        if not self.app_was_away() or not self._lesson_id():
            return False
        return self.seen_lesson == self._lesson_id()

    def app_was_away(self) -> bool:
        """No app now, and the last one left >= ORCH_RESUME_AFTER_S ago (an app relaunch on an engine that kept
        running, lesson or not). Nov 21: its old preflight card is never sent again."""
        if self.hub.clients or self.last_client_gone is None:
            return False
        return time.monotonic() - self.last_client_gone >= float(os.environ.get("ORCH_RESUME_AFTER_S", "10"))

    async def _emit(self, type_: str, payload: dict | None = None) -> None:
        if type_ == "lesson.ready" and self.hub.clients:
            self.seen_lesson = ((payload or {}).get("lesson") or {}).get("id")
        if (note := getattr(self.screen, "note_ui", None)) is not None:
            note(type_, payload)  # the targeter never boxes Miyagi's own text (cards, captions) seen on screen
        await self.hub.emit(type_, self.session._tagged(type_, payload or {}))  # epoch / gen: which lesson and step

    async def ingest(self, ev: dict) -> None:
        self.recorder.record(ev)
        await self.session.ingest(ev)

    def watch_cloud(self) -> None:
        """Install token self-heal: hear the proxy's verdicts (server_config.cloud_error, from any thread) and tell the
        apps: `cloud.token_invalid` the first time the proxy does not know the token (a 401; the app mints a new one),
        and a fresh `config.status` (cloud: unauthorized / paused / quota) on each new verdict. Call on the loop."""
        self._loop = asyncio.get_running_loop()
        if self._cloud_off is None:
            self._cloud_off = server_config.on_cloud_verdict(self._on_cloud_verdict)

    def _on_cloud_verdict(self, event: dict) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            here = asyncio.get_running_loop() is loop
        except RuntimeError:
            here = False
        if here:
            self._cloud_task(self._announce_cloud(event))
        else:  # a worker thread (sync clients, to_thread): hop onto the engine's loop
            asyncio.run_coroutine_threadsafe(self._announce_cloud(event), loop).add_done_callback(_log_cloud_failure)

    async def _announce_cloud(self, event: dict) -> None:
        if event.get("token_invalid"):
            await self.hub.emit("cloud.token_invalid", {"reason": "unknown_token"})  # never the token or its hash
        await self.hub.emit("config.status", key_status())
        ttl = event.get("ttl")
        if ttl and self._loop is not None:  # paused / quota lapse on their own: say so when they do
            self._loop.call_later(float(ttl) + 0.5, lambda: self._cloud_task(self.hub.emit("config.status", key_status())))

    def _cloud_task(self, coro: Any) -> None:
        task = asyncio.get_running_loop().create_task(coro)
        self._cloud_tasks.add(task)  # keep a reference until it is done
        task.add_done_callback(self._cloud_tasks.discard)
        task.add_done_callback(_log_cloud_failure)

    async def start(self) -> None:
        self.watch_cloud()
        self.watcher.set_root(self.session.workdir)
        self.watcher.start()
        if getattr(self.screen, "enabled", False) and hasattr(self.screen, "down_reason"):
            # The real bridge imports pyobjc / Vision / ScreenCaptureKit and waits up to 2 s for the event tap: all of
            # that ran here, before uvicorn served, so the island's first connect waited ~1.4 s. Start it in a thread
            # while the port opens; reads answer "nothing" until the reader is up (bridge.reader is None).
            self._screen_boot = asyncio.create_task(self._start_screen(asyncio.get_running_loop()))
        else:
            self._screen_up(self.screen.start(self.session.on_screen))
        if config.env_flag("ORCH_AUTOSTART"):  # no launcher needed: the lesson is live from the start
            if self.modules.demo and (graph := self.modules._lesson_file()):
                await self.session.load_graph(graph)
            elif url := os.environ.get("ORCH_LESSON_URL"):  # real builder (E2's cache makes it instant)
                self._autostart = asyncio.create_task(self.session.learn_url(url, skip_preflight=True))
        self._ticker = asyncio.create_task(self._tick_loop())
        self._avoider = asyncio.create_task(self._avoid_loop())
        # screen state is logged by _start_screen: the bridge boots in a thread after this line
        log.info("engine up: demo=%s modules=%s workdir=%s precision=%s", self.modules.demo,
                 self.modules.describe(), self.session.workdir, config.precision_setting())

    def _screen_up(self, ok: bool) -> None:
        if not ok:
            self.session.screen = None  # precision mode only (files + tut run)
        else:  # E6: app switch / Space swipe within ~0.25 s -> clear (or re-place) the spotlight at once
            self.screen.watch_frontmost(self.session.on_front_switch)  # (E5: also books the keys to the old app)

    async def _start_screen(self, loop: asyncio.AbstractEventLoop) -> None:
        t0 = time.monotonic()
        try:
            ok = await asyncio.to_thread(self.screen.start, self.session.on_screen, loop)
        except Exception:  # noqa: BLE001 - never kill the engine
            log.exception("screen start failed")
            ok = False
        self._screen_up(ok)
        log.info("screen up in %.2f s (off the startup path): %s", time.monotonic() - t0, ok)

    async def auto_resume(self) -> bool:
        """The first app connection after an engine restart (or a deploy's POST /end) while a lesson was running: that
        lesson continues at its saved step, as if nothing happened (Michael, Nov 15: restarts sent him back to "begin
        project"). Not a lesson the learner ended (End / Start new: `stopped`, only the library's Continue row now),
        not one finished, not one idle longer than ORCH_AUTO_RESUME_S (default 3 h), never a Demo take (each Demo
        start is a fresh take at step 1: stage.py). True when it restored one (engine.hello.restored).
        Nov 21: OFF by default. Michael: every launch is a fresh start ("it's like continuing a lesson. No, I need it to
        restart"): auto-resume opened VS Code, the steps drawer and the old clip with sound before sign-in. The saved
        lesson stays on disk: the library's Continue row, plus the resume card after library.list when it was not
        ended (never on connect); ORCH_AUTO_RESUME=1 turns the old behaviour back on (dev, deploys)."""
        s = self.session
        if os.environ.get("ORCH_AUTO_RESUME") != "1":
            return False
        if self.resumer is None or self.hub.clients or s.graph is not None or s.phase != "idle":
            return False
        try:
            from server.sessions import store
            from server.sessions.resume import is_demo

            saved = store.load()
            if not saved or saved.get("stopped") or (graph := store.load_graph(saved)) is None or is_demo(graph):
                return False
            idle = time.time() - float(saved.get("lastActiveAt") or saved.get("startedAt") or 0)
            if idle > float(os.environ.get("ORCH_AUTO_RESUME_S", str(3 * 3600))):
                return False
            log.info("auto-resume: %s at step %s (%s) after an engine restart", saved.get("lessonId"),
                     int(saved.get("stepIndex") or 0) + 1, saved.get("stepId"))
            await self.resumer.resume()
            self.seen_lesson = self._lesson_id()  # the app sees it in this connection's snapshot
            return self.session.graph is not None
        except Exception:  # noqa: BLE001 - never blocks the connection: the resume card is still there
            log.exception("auto-resume failed")
            return False

    # ------------------------------------------------------------------ v2 (BUILD-PLAN E2)
    def capabilities(self) -> list[str]:
        """The v2 commands this engine answers (engine.hello.capabilities): only those whose module loaded."""
        caps: list[str] = []
        if health_mod is not None:
            caps += ["health.get", "permission.open"]
        if library_mod is not None:
            caps += ["library.list", "library.get", "library.start"]
        if progress_mod is not None:
            caps.append("progress.get")
        if review_mod is not None and library_mod is not None:  # Start review replays the lesson's own cached steps
            caps.append("review.start")
        if hasattr(self.session, "panel_state"):
            caps.append("panel.state")
        caps.append("data.delete")  # Delete my data, engine part (the lesson notes); app follow-up: settings:delete
        return caps

    def hello(self, restored: bool = False) -> dict:
        out: dict[str, Any] = {"version": ENGINE_VERSION, "contract": CONTRACT_VERSION,
                               "capabilities": self.capabilities()}
        if restored:
            out["restored"] = True
        return out

    def ensure_status(self) -> None:
        """Start E1's system-status poller once a v2 app is here (MIYAGI_SYSTEM_STATUS=0 keeps it off)."""
        if self.status is not None or status_mod is None or os.environ.get("MIYAGI_SYSTEM_STATUS", "1").strip() == "0":
            return
        try:
            self.status = status_mod.SystemStatus(self._emit_status, restore_status=self._restore_status)
            self.session.system_status = self.status  # for E4: mark_busy / clear_busy / note_network
            self.status.start()
            log.info("system status poller on (network, AI busy, setup health; sent on change only)")
        except Exception:  # noqa: BLE001 - the lesson runs without it
            log.exception("system status poller failed to start")
            self.status = None

    def _restore_status(self) -> dict:
        """AI busy is over: the session's own status again (with its detail while thinking)."""
        s = self.session
        state = getattr(s, "status", "") or "idle"
        detail = getattr(s, "status_detail", None)
        return {"state": state, **({"detail": detail} if detail and state == "thinking" else {})}

    async def _emit_status(self, type_: str, payload: dict) -> None:
        if not getattr(self.session, "app_v2", False):
            return  # an older app has no surface for blocker / busy / health
        await self._emit(type_, contract_health(payload) if type_ == "health" else payload)

    def status_replay(self) -> list[tuple[str, dict]]:
        """What a reconnecting v2 app needs from the poller: offline blocker, busy, the last health."""
        if self.status is None or not getattr(self.session, "app_v2", False):
            return []
        return [(t, contract_health(p) if t == "health" else p) for t, p in self.status.replay()]

    async def health_payload(self) -> dict:
        """The setup checklist in the contract's shape, sampled now. Probes never prompt and run in a thread; with the
        poller on, its snapshot moves too, so it doesn't send the same rows again."""
        h = await self.status.refresh_health() if self.status is not None else None
        if h is None and health_mod is not None:
            h = await asyncio.to_thread(health_mod.snapshot)
        return contract_health(h)

    async def _coalesced(self, key: str, make: Any, ttl: float = READ_TTL_S) -> Any:
        """One file read per `ttl` for the app's burst of identical reads (log: library.list x3 and progress.get x3-4 on
        every window open): concurrent askers share one in-flight read, and a repeat within `ttl` gets its result.
        If the leader running make() is cancelled, waiters are not cancelled with it: they retry (one becomes leader)."""
        while True:
            hit = self._reads.get(key)
            if hit is not None and time.monotonic() - hit[0] < ttl:
                return hit[1]
            fut = self._reads_inflight.get(key)
            if fut is None:
                break
            try:
                return await asyncio.shield(fut)
            except asyncio.CancelledError:
                task = asyncio.current_task()
                if task is not None and task.cancelling():
                    raise  # this waiter itself was cancelled
                # the leader was cancelled: loop and retry
        gen = self._reads_gen
        fut = asyncio.get_running_loop().create_future()
        self._reads_inflight[key] = fut
        try:
            res = await make()
            if gen == self._reads_gen:  # a PROGRESS event during the read made this result stale: do not cache it
                self._reads[key] = (time.monotonic(), res)
            fut.set_result(res)
            return res
        except BaseException as e:
            fut.set_exception(e) if not isinstance(e, asyncio.CancelledError) else fut.cancel()
            fut.exception() if not fut.cancelled() else None  # mark retrieved (nobody else may await it)
            raise
        finally:
            if self._reads_inflight.get(key) is fut:
                self._reads_inflight.pop(key, None)

    def forget_reads(self) -> None:
        self._reads_gen += 1
        self._reads.clear()

    async def library_payload(self) -> dict:
        if library_mod is None:
            return {"items": [], "continue": []}
        return await self._coalesced(
            "library", lambda: self._read_library())

    async def _read_library(self) -> dict:
        return contract_library(await asyncio.to_thread(library_mod.listing))

    async def library_detail(self, lid: str) -> dict | None:
        if library_mod is None or not isinstance(lid, str) or not LIBRARY_ID_RE.fullmatch(lid):
            return None
        return contract_library_detail(await asyncio.to_thread(library_mod.item, lid))

    async def progress_payload(self) -> dict | None:
        """None: nothing recorded yet (GET /progress answers null, progress.get answers {})."""
        if progress_mod is None:
            return None
        return await self._coalesced("progress", self._read_progress)

    async def _read_progress(self) -> dict | None:
        p = await asyncio.to_thread(progress_mod.progress)
        return contract_progress(p) if p is not None else None

    async def handle_v2(self, type_: str, p: Any, reply: Any) -> None:
        """health.get, permission.open, library.list, library.get, progress.get, panel.state, data.delete. Every blocking
        call runs in a thread; replies go to the app that asked."""
        s = self.session
        s.note_app_v2(type_)  # E3: lesson.paused / blocker / the complete card go out from now on
        self.ensure_status()
        if type_ == "health.get":
            await reply("health", await self.health_payload())
        elif type_ == "permission.open":
            # The app opens System Settings itself (fixed URLs); nothing prompts here. The learner is fixing a grant:
            # health sampling stays on, so the row flips by itself once the switch is on.
            log.info("permission.open %s: the app opened System Settings; watching for the grant", p.kind)
            if self.status is not None:
                self.status.watch_health(True)
            await reply("health", await self.health_payload())
        elif type_ == "library.list":
            await reply("library", await self.library_payload())
            # Nov 21 (launch-quiet): the saved lesson's card follows (dispatch: _offer_saved_lesson), never on connect
        elif type_ == "library.get":
            found = await self.library_detail(p.id)
            if found is None:  # no reply (contract): the app's ask ends on its own timeout
                log.info("library.get: no lesson %s on this Mac", p.id)
                return
            await reply("library.item", found)
        elif type_ == "progress.get":
            await reply("progress", await self.progress_payload() or {})
        elif type_ == "panel.state":
            await s.panel_state(p.open, _rect(p.rect))
        elif type_ == "data.delete":  # Settings > Privacy > Delete my data: the engine's local lesson notes go too
            await asyncio.to_thread(_wipe_context_memory, s)  # no reply: the app's sheet already says what it erased

    async def library_start(self, lid: str) -> None:
        """library.start: a cached lesson, with no build and no lesson-writing model call. The cached graph's workdir is
        another Mac's path: the lesson gets its own folder here (_library_folder)."""
        s = self.session
        s.note_app_v2("library.start")
        self.ensure_status()
        graph = await asyncio.to_thread(library_mod.load_graph, lid) if library_mod is not None else None
        if not isinstance(graph, dict) or not graph.get("steps"):
            log.info("library.start: no lesson %s on this Mac", lid)
            await self._emit("error", {"message": LIBRARY_GONE})
            return
        lesson = graph.setdefault("lesson", {})
        lesson.pop("workdir", None)
        title = str(lesson.get("title") or lesson.get("goal") or "Lesson")
        if s._same_lesson_running(graph):  # a re-sent start never restarts it
            log.info("library.start: %s is already running: continuing", lid)
            for type_, payload in s.snapshot():
                await s.emit(type_, payload)
            return
        if s.graph is not None or s.phase in ("building", "searching"):
            await s.end_lesson("new lesson")
        s.query = title
        s.results, s.pending_pick = {}, None
        log.info("library.start: %s (lesson %s)", lid, lesson.get("id"))
        await s._run_build("", title, factory=lambda: self._load_library(graph, title))

    async def review_start(self, skill_id: str, label: str) -> None:
        """review.start {skillId?, label?}: a quick spaced review of one mastered skill, with no build and no model call.
        The steps behind the skill are replayed from its lesson's cached graph (sessions/review.py), in that lesson's own
        folder so the checks run on the learner's own code. The result (a pass / a skipped step) goes to the schedule."""
        s = self.session
        s.note_app_v2("review.start")
        self.ensure_status()
        graph = await asyncio.to_thread(self._review_graph, skill_id, label)
        if graph is None:
            log.info("review.start: nothing to review for %r / %r", skill_id, label)
            await self._emit("error", {"message": REVIEW_GONE})
            return
        folder = graph["lesson"].pop("_folder", None)
        title = str(graph["lesson"].get("title") or "Review")
        if s._same_lesson_running(graph):
            log.info("review.start: %s is already running: continuing", graph["lesson"].get("id"))
            for type_, payload in s.snapshot():
                await s.emit(type_, payload)
            return
        if s.graph is not None or s.phase in ("building", "searching"):
            await s.end_lesson("new lesson")
        s.query = title
        s.results, s.pending_pick = {}, None
        log.info("review.start: %s (lesson %s)", (graph["lesson"].get("review") or {}).get("label"), graph["lesson"].get("id"))
        await s._run_build("", title, factory=lambda: self._load_library(graph, title, folder=folder))

    def _review_graph(self, skill_id: str, label: str) -> dict | None:
        """The review lesson for a skill (blocking: reads the schedule and the cached lesson). None: no such skill, or its
        lesson is no longer cached."""
        if review_mod is None or library_mod is None:
            return None
        row = review_mod.find({"skillId": skill_id, "label": label})
        if row is None or not isinstance(row.get("_lessonId"), str):
            return None
        lib_id = library_mod.index_by_lesson_id().get(row["_lessonId"])
        source = library_mod.load_graph(lib_id) if lib_id else None
        if not isinstance(source, dict):
            return None
        graph = review_mod.review_graph(source, row["label"], row["_key"], skill_id=row["skillId"])
        if graph is None:
            return None
        graph["lesson"].pop("workdir", None)
        graph["lesson"]["_folder"] = _library_folder(source)  # the finished lesson's own folder: the learner's code is there
        return graph

    async def _load_library(self, graph: dict, title: str, folder: str | None = None) -> None:
        """Mirrors the curated start (session._load_curated): the folder, the last run's files set aside on a fresh
        start, "Lesson ready", then the lesson."""
        from . import workspace as wsmod

        s = self.session
        s.phase = "building"
        s._build_start(text=True, title=title)
        if isinstance(getattr(s, "_build_v2", None), dict):
            s._build_v2["source"] = {"kind": "library", "title": title[:200]}
        await s._status("thinking", detail="Loading the lesson")
        ok = False
        try:
            s.build_progress = {"message": "Setting up your project folder", "progress": 0.5}
            await s.emit("lesson.building", s.build_progress)
            if folder is None:
                folder = await asyncio.to_thread(_library_folder, graph)
                if not s._continues_save(graph):  # a fresh start: no step passes on the last run's files
                    await asyncio.to_thread(wsmod.set_aside_previous, folder, graph)
            else:  # a review (review_start): the learner's own files are what its checks look at: never set aside
                await asyncio.to_thread(Path(folder).mkdir, parents=True, exist_ok=True)
            graph["lesson"]["workdir"] = folder
            s.build_progress = None
            await s.emit("lesson.building", {"message": "Lesson ready", "progress": 1.0})
            await asyncio.sleep(min(s.ready_hold_s, 0.6))
            await s.load_graph(graph)
            ok = True
        except Exception:
            log.exception("starting the library lesson failed")
            await s._build_failed(LIBRARY_FAILED)
        finally:
            if not ok:
                s.phase = "idle" if s.graph is None else s.phase

    def save_progress(self) -> None:
        if self.resumer is not None and self.session.graph is not None and not self.session.awaiting_resume:
            try:
                self.resumer.save_now()
            except Exception:  # noqa: BLE001
                log.exception("saving lesson progress failed")

    async def stop(self) -> None:
        if self._cloud_off is not None:
            self._cloud_off()
            self._cloud_off = None
        self.save_progress()
        await self.watcher.stop()
        if self._screen_boot is not None:
            with contextlib.suppress(Exception):
                await self._screen_boot
        self.screen.stop()
        if self.status is not None:
            await self.status.stop()
        for task in (self._ticker, self._avoider):
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    async def _tick_loop(self) -> None:
        while True:
            await asyncio.sleep(1.0)
            try:
                await self.session.tick()
            except Exception:
                log.exception("tick failed")

    async def _avoid_loop(self) -> None:
        """t9: every 0.5 s while a lesson runs, VS Code's quick-pick -> screen.avoid when it changed (quick_pick.py)."""
        from . import quick_pick

        while True:
            await asyncio.sleep(quick_pick.POLL_S)
            try:
                await quick_pick.poll(self.session)
            except Exception:
                log.exception("screen.avoid poll failed")

    async def _offer_saved_lesson(self, ws: WebSocket | None, reply: Any) -> None:
        """Nov 21 (launch-quiet): after `library`, the saved lesson's resume card (sessions.Resumer.pending_offer: a
        lesson not ended, nothing in memory). At most once per connection: the app sends library.list on every
        launcher and library open, and the card store keeps a closed decision card closed only until the next one.
        Never again in this engine run once the learner answered (Continue / Start new) or closed it. The library's
        Continue row always carries the saved lesson."""
        if self.resumer is None or self._offer_answered or ws in self._offered_to:
            return
        offer = self.resumer.pending_offer()
        if offer is None:
            return
        self._offered_to.add(ws)
        await reply("card", offer)

    async def dispatch(self, raw: dict, ws: WebSocket | None = None) -> None:
        """One App->Engine command. `ws`: the socket it came on (v2 replies go to that app only; None: to every app)."""
        msg = parse_command(raw)
        p = msg.payload
        s = self.session
        log_received(msg.type, p)
        if msg.type in LEARNER_ASKS or msg.type == "action" and getattr(p, "kind", None) in LEARNER_ASK_ACTIONS:
            s.learner_asked = True  # Nov 21: the learner asked for this lesson: VS Code may open under the sheet
        if (msg.type == "action" and getattr(p, "kind", None) in ("resume", "end_lesson")
                or msg.type == "card.closed" and getattr(p, "kind", None) == "resume"):
            self._offer_answered = True  # Nov 21: answered or closed: the saved-lesson card is not offered again
        if msg.type in V2_INSTANT:
            async def reply(type_: str, payload: dict) -> None:
                if ws is None:
                    await self.hub.emit(type_, payload)
                else:
                    await self.hub.send_to(ws, type_, payload)

            await self.handle_v2(msg.type, p, reply)
            if msg.type == "library.list":
                await self._offer_saved_lesson(ws, reply)
        elif msg.type == "library.start":
            await self.library_start(p.id)
        elif msg.type == "review.start":
            await self.review_start(p.skillId, p.label)
        elif msg.type == "learn":
            await s.learn(p.query, getattr(p, "mode", None))
        elif msg.type == "learn_url":
            await s.learn_url(p.url, transcript_only=getattr(p, "transcriptOnly", None) is True)
        elif msg.type == "build_lesson":
            await s.build_lesson(p.resultIds)
        elif msg.type == "action":
            circle = {}  # circle to ask (Nov 22): only when the app sent them, so older callers are unchanged
            if getattr(p, "region", None) is not None:
                circle["region"] = p.region.model_dump()
            if getattr(p, "askId", None):
                circle["ask_id"] = p.askId
            if getattr(p, "source", None):
                circle["source"] = p.source
            await s.action(p.kind, p.text, **circle)
        elif msg.type == "video.state":
            await s.video_state(p.t, p.playing)
        elif msg.type == "overlay.bounds":
            s.overlay_bounds([r.model_dump() for r in p.rects])
        elif msg.type == "end_lesson":  # the bar's / launcher's End: stop for now, the saved progress stays resumable
            await s.end_lesson("stopped")  # (the resume card's "Start a new lesson", action end_lesson, keeps it too)
        elif msg.type == "config.keys":
            keys = p.model_dump()
            erased = is_delete_my_data(keys)  # read before apply_keys forgets the keys the app held
            await self.hub.emit("config.status", apply_keys(keys))
            if erased:
                await asyncio.to_thread(_wipe_context_memory, s)
            if server_config.token_invalid_pending():  # the same dead token again (e.g. after a reconnect): say it again
                await self.hub.emit("cloud.token_invalid", {"reason": "unknown_token"})
        elif msg.type in ("card.shown", "card.closed"):  # E14: what the learner really has on screen
            await s.card_seen(msg.type == "card.shown", p.stepId, p.title, p.kind, getattr(p, "by", None))


# config.keys -> server.config (get_key) + the env vars modules read. Memory only; never logged.
KEY_ENV = server_config.KEY_ENV
_ENV_AT_START = {name: os.environ.get(var, "") for name, var in KEY_ENV.items()}


def apply_keys(keys: dict) -> dict:
    """Use the app's keys over .env (bring-your-own-key), or the miyagi cloud token; answer with presence only.

    The install token (config.keys.miyagiToken) and the cloud URL stay in server_config's memory: they are
    never exported to os.environ (not as ANTHROPIC_API_KEY / GEMINI_API_KEY / MIYAGI_CLOUD_TOKEN, and no
    ANTHROPIC_BASE_URL), so a learner's subprocess (their code, a kernel, "Run it for me", VS Code terminals)
    cannot inherit a credential that bills miyagi. Every Claude / Gemini client is built from
    server_config.anthropic_kwargs() / gemini_kwargs(), which send the token to the proxy. ANTHROPIC_BASE_URL is
    left alone: the engine's clients pass base_url explicitly (a direct key always goes to api.anthropic.com)."""
    server_config.set_app_keys(keys)
    for name, var in KEY_ENV.items():
        if name == "miyagiToken":
            continue  # memory only (server_config.cloud_token()); never exported
        app_key = server_config._app_keys.get(name)
        if app_key:
            os.environ[var] = app_key
        elif _ENV_AT_START[name]:
            os.environ[var] = _ENV_AT_START[name]
        else:
            os.environ.pop(var, None)
    return key_status()


# The bring-your-own keys the app's Settings holds and sends (app settings/keys.ts KEY_NAMES). Not miyagiToken /
# miyagiCloud: engine.ts folds the install token into every config.keys, and Delete my data keeps it (erase.test.ts).
BYOK_NAMES = ("anthropic", "gemini", "elevenlabs")


def is_delete_my_data(keys: dict) -> bool:
    """Settings > Privacy > Delete my data (the app's settings:delete) as a config.keys: every BYOK key empty while the
    engine still held one of them. The install token and cloud URL riding along (they stay) do not count. A learner
    clearing their only key in Settings reads the same; then only the local lesson notes go, which is harmless.
    A learner with no BYOK key (the cloud only) sends the same all-empty keys on every connect, so that case needs the
    explicit command: data.delete (app follow-up: settings:delete sends it when engine.hello lists it)."""
    held = any(server_config._app_keys.get(name) for name in BYOK_NAMES)
    return held and not any(server_config.usable((keys.get(name) or "").strip()) for name in BYOK_NAMES)


def _wipe_context_memory(session: Any = None) -> None:
    """Delete my data, engine part: every lesson's notes and file-scan cache (server/context), and the running session's
    hold on them. Never raises."""
    try:
        from . import context_memory

        context_memory.wipe_all(session)
    except Exception:  # noqa: BLE001 - the keys already went; a leftover note is logged, never a crash
        log.exception("context memory wipe failed")


def _log_cloud_failure(fut: Any) -> None:
    """Done-callback for the cloud announcements (a task, or a run_coroutine_threadsafe future): log what failed."""
    if fut.cancelled():
        return
    if (exc := fut.exception()) is not None:
        log.error("announcing the miyagi cloud verdict failed: %s", type(exc).__name__, exc_info=exc)


def key_status() -> dict:
    """config.status: where each key comes from (never the key) and what the miyagi cloud said (cloud_status)."""
    status = {name: server_config.key_source(name) for name in KEY_ENV}
    status["cloud"] = server_config.cloud_status()
    return status


def _redact(raw: Any) -> Any:
    """For logs: a command that holds keys (config.keys, config.validate) by name only; anything else as sent, with an
    over-long payload clipped (v2 commands are short: ids, kinds, a rect)."""
    if not isinstance(raw, dict):
        return "<not an object>"
    if raw.get("type") in SECRET_COMMANDS:
        return {"type": raw.get("type"), "payload": "<redacted>"}
    text = repr(raw.get("payload"))
    return raw if len(text) <= 300 else {"type": raw.get("type"), "payload": text[:300] + "…"}


def _failure_text(raw: dict, e: Exception) -> str:
    """The `error` message for a command that failed. Fixed copy for key commands (the exception can quote a key)
    and for v2 commands (no internals on a v2 surface)."""
    type_ = raw.get("type")
    if type_ in SECRET_COMMANDS:
        return KEYS_FAILED
    if type_ in V2_COMMANDS:
        return V2_FAILED
    return f"{type_}: {e}"


def _log_failure(raw: dict, e: Exception) -> None:
    if raw.get("type") in SECRET_COMMANDS:  # no traceback: a validation error prints the input (the keys)
        log.error("command failed: %s (%s)", _redact(raw), type(e).__name__)
    elif raw.get("type") in V2_COMMANDS and isinstance(e, ValueError):  # a malformed v2 command: one line
        log.warning("command refused: %s", e)
    else:
        log.exception("command failed: %s", _redact(raw))


def _searching(running: dict, session: Any) -> bool:
    """The worker is on a search (learn, not "Just teach me") that is still streaming rows."""
    cur, job = running.get("cmd") or {}, running.get("job")
    return job is not None and not job.done() and cur.get("type") == "learn" and session.phase == "searching"


def _brief(raw: dict) -> str:
    """'action hint' / 'learn': the type (+ an action's kind), never a payload (config.keys holds keys)."""
    p = raw.get("payload")
    kind = p.get("kind") if raw.get("type") == "action" and isinstance(p, dict) else None
    return f"{raw.get('type')} {kind}" if kind else str(raw.get("type"))


engine = Engine()


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    await engine.start()
    yield
    await engine.stop()


app = FastAPI(title="sandhacks-tutor engine", lifespan=lifespan)
app.add_middleware(RequestGuard)  # Host, LAN token, Origin, JSON-only bodies on every HTTP route (BUILD-PLAN 6)

try:  # E5 voice: GET /tts/<hash>.mp3 for `speak.audioUrl` (relative: the app prefixes ENGINE_HTTP)
    from server.coach import voice as _voice

    app.include_router(_voice.router)
except Exception as _e:  # noqa: BLE001
    log.warning("voice routes unavailable: %s", _e)

try:  # E3 Tiger stats: GET /stats (HTML, refreshes every 2 s) + /stats/data (JSON); read-only, never blocks long
    from server.checks.stats_web import router as _stats_router

    app.include_router(_stats_router)
except Exception as _e:  # noqa: BLE001
    log.warning("stats routes unavailable: %s", _e)


@app.websocket("/")
async def ws_endpoint(ws: WebSocket) -> None:
    # Before the handshake (a refusal is an HTTP 403): a browser page from elsewhere, or a client without the app's
    # per-launch token when the engine has one, or a Host that isn't this Mac (DNS rebinding). Neither the Origin's
    # page nor the token is ever echoed in full.
    if not host_allowed(ws.headers.get("host")):
        log.warning("refused a WebSocket for host %s", _shown(ws.headers.get("host")))
        await ws.close(code=1008)
        return
    origin = ws.headers.get("origin")
    if not origin_allowed(origin):
        log.warning("refused a WebSocket from origin %s", _shown(origin))
        await ws.close(code=1008)
        return
    if not token_ok(ws.headers.get(TOKEN_HEADER)):
        log.warning("refused a WebSocket without the engine token (%s)",
                    "wrong token" if ws.headers.get(TOKEN_HEADER) else "no X-Miyagi-Token header")
        await ws.close(code=1008)
        return
    await ws.accept()
    if engine.app_was_away():  # Nov 21: a new app run asks again before VS Code opens by itself (a quick blip
        engine.session.learner_asked = False  # mid-build keeps the ask; the first connection is False from __init__)
    engine.hub.begin(ws)  # events emitted while hello + the snapshot go out are held and sent right after
    try:
        restored = await engine.auto_resume()  # off unless ORCH_AUTO_RESUME=1 (Nov 21: every launch starts fresh)
        await engine.hub.send_to(ws, "engine.hello", engine.hello(restored))  # v2: always the first message
        snap = engine.session.snapshot(ask_resume=engine.app_returning(), returning=engine.app_was_away())
        if not any(t == "status" for t, _ in snap):  # every (re)connect resyncs the island, whatever the early return
            snap = [*snap, ("status", {"state": engine.session.status or "idle"})]
        for type_, payload in snap:
            await engine.hub.send_to(ws, type_, engine.session._tagged(type_, payload))
        for type_, payload in engine.status_replay():  # a v2 app coming back: offline / busy / the last health
            await engine.hub.send_to(ws, type_, payload)
        await engine.hub.finish(ws)
    except Exception as e:  # noqa: BLE001  the app went away mid-handshake: nothing to clean up but the hold
        engine.hub.drop(ws, f"handshake failed: {type(e).__name__}", close=True)
        return
    engine.mark_lesson_seen()
    queue: asyncio.Queue[dict] = asyncio.Queue()
    running: dict[str, dict] = {}  # the command the worker is on (a press queued behind it is logged on arrival)
    side: set[asyncio.Task] = set()  # v2 reads answered beside the queue (health.get, library.list, ...)

    async def report(raw: dict, e: Exception) -> None:
        _log_failure(raw, e)
        with contextlib.suppress(Exception):
            await engine.hub.send_to(ws, "error", {"message": _failure_text(raw, e)})

    async def worker() -> None:
        # commands run in order, off the receive loop, so video.state keeps flowing
        while True:
            raw = await queue.get()
            running["cmd"] = raw
            job = running["job"] = asyncio.ensure_future(engine.dispatch(raw, ws))  # cancellable: a new learn ends a search
            try:
                await job
            except asyncio.CancelledError:
                cur = asyncio.current_task()
                if cur is not None and cur.cancelling():
                    raise  # the app left: the worker (and its command) stop
                log.info("%s cancelled: a newer request replaced it", _brief(raw))
            except Exception as e:
                await report(raw, e)
            finally:
                running.pop("cmd", None)
                running.pop("job", None)

    async def answer(raw: dict) -> None:
        try:
            await engine.dispatch(raw, ws)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            await report(raw, e)

    task = asyncio.create_task(worker())
    why = "cancelled"  # how the socket ended (E14: the hub logs every close)
    try:
        while True:
            raw = await ws.receive_json()
            if not isinstance(raw, dict):
                continue
            if raw.get("type") in LESSON_STARTS:  # build metrics count from the command's arrival (queue wait too)
                with contextlib.suppress(Exception):
                    engine.session.build_metrics.command(raw["type"])
            if raw.get("type") in LESSON_STARTS and engine.session.building():
                await engine.session.cancel_build()  # unblock the queue: the new request replaces the build
            elif raw.get("type") in LESSON_STARTS and _searching(running, engine.session):
                running["job"].cancel()  # "Just teach me" / a pick / a new query while the search still runs: it
                # replaces the search (rows so far stay pickable) instead of waiting out its tail (live: 15 s)
            if raw.get("type") in INSTANT:
                try:
                    await engine.dispatch(raw, ws)
                except Exception:
                    log.exception("bad %s: %s", _brief(raw), _redact(raw))
            elif raw.get("type") in V2_INSTANT:  # a read never waits behind a build or an answer being written
                t = asyncio.create_task(answer(raw))
                side.add(t)
                t.add_done_callback(side.discard)
            else:
                if (cur := running.get("cmd")) is not None:  # '<- …' is logged when it runs; this says it waited
                    log.info("<- %s queued behind %s (%d waiting)", _brief(raw), _brief(cur), queue.qsize())
                await queue.put(raw)
    except WebSocketDisconnect as e:
        why = f"closed, code {e.code}"
    except RuntimeError as e:
        why = f"closed ({e})"
    except Exception:
        log.exception("websocket error")
        why = "error"
    finally:
        engine.hub.drop(ws, why)
        engine._offered_to.discard(ws)
        if not engine.hub.clients:
            engine.last_client_gone = time.monotonic()
            engine.save_progress()  # the app left: keep the exact video position (autosave is throttled)
        task.cancel()
        for t in list(side):
            t.cancel()


@app.post("/ingest")
async def ingest(body: Any = Body(...)) -> dict:
    if isinstance(body, dict) and isinstance(body.get("events"), list):
        events = body["events"]
    elif isinstance(body, list):
        events = body
    else:
        events = [body]
    n = 0
    for ev in events:
        if isinstance(ev, dict):
            await engine.ingest(ev)
            n += 1
    st = engine.session.step
    lesson = (engine.session.graph or {}).get("lesson", {})
    # E3's `tut run` tags its Tiger run with these
    return {"ok": True, "accepted": n, "lesson_id": lesson.get("id"), "step_id": st["id"] if st else None}


@app.post("/vscode/event")
async def vscode_event(body: dict = Body(...)) -> dict:
    """The VS Code companion (vscode-ext/) posts editor/save/dirty/focus/command_end events; see server.workspace.vscode_ext."""
    from server.workspace import vscode_ext

    item = vscode_ext.record_event(body)
    from . import quiet_save  # Nov 15: a dirty / save / editor change of the step file re-grades within ~0.2 s

    quiet_save.on_vscode_event(engine.session, item)
    if body.get("type") in ("dirty", "save", "editor") and (getattr(engine.session, "_advice_up", None) is not None
                                                             or getattr(engine.session, "_offtrack_up", None) is not None):
        from . import advice_clear  # t8: the Hint / Not yet whose line was just fixed goes within ~1 s

        engine.session._spawn(advice_clear.follow(engine.session, force=True))
    if body.get("type") == "command_end":  # a curated lesson's run: VS Code's exact output grades it (curated.py)
        from . import curated

        if curated.active(engine.session):
            engine.session._spawn(curated.on_command_end(engine.session, item))  # never holds up the extension
    if body.get("type") in ("command_end", "save"):  # Nov 15: a run step's terminal typo -> instant card (cmd_typos)
        from . import typo_card

        engine.session._spawn(typo_card.on_vscode_event(engine.session, item))
    if body.get("type") == "visible":  # t7: the editor scrolled (companion 0.0.5): the type box follows its row now
        from . import box_follow

        box_follow.on_visible(engine.session, item)
    if body.get("type") in ("dirty", "save", "editor", "visible", "command_end", "focus"):
        engine.session.relayout(f"VS Code {body.get('type')}")  # V9: a cell ran / output / edit: the box re-measures
    if body.get("type") == "explain_selection":  # "Miyagi: Explain this" -> an Explain card in the overlay (selection.py)
        from .selection import explain_from_vscode

        return {"ok": True, "explaining": explain_from_vscode(engine.session, body)}
    return {"ok": True}


@app.post("/end")
async def end_lesson(forget: int = 0) -> dict:
    """End the current lesson from a terminal:  curl -X POST localhost:8787/end
    Nov 15: this runs before every engine deploy, so the learner's place is KEPT on disk. Nov 21: it is no longer
    continued by itself on the next connection (ORCH_AUTO_RESUME=1 only): the app offers it through Continue (the
    library's continue row and the resume card after library.list). A clean start (tests) that drops it:
    curl -X POST 'localhost:8787/end?forget=1'"""
    lesson = (engine.session.graph or {}).get("lesson", {}).get("id")
    demo = stage.on(engine.session)  # a Demo take is never saved (sessions.resume.is_demo): the next Demo is step 1
    if not forget:
        engine.save_progress()  # the exact step + checks, just before the lesson is unloaded
    await engine.session.end_lesson("POST /end" if forget else "interrupted")
    return {"ok": True, "ended": lesson, "kept": bool(lesson) and not forget and not demo}


@app.get("/state")
async def state() -> dict:
    st = engine.session.state()
    if engine.session.graph is None and engine.session.phase == "idle" and engine.resumer is not None:
        try:  # S7: a lesson saved before an engine restart, waiting for the learner's Continue / Start new
            from server.sessions import store

            saved = store.load()
            graph = store.load_graph(saved) if saved else None
            if graph is not None:
                st.update({"phase": "awaiting_resume", "lesson": graph.get("lesson"),
                           "saved": {k: saved.get(k) for k in ("stepIndex", "stepCount", "stepId", "videoT", "lastActiveAt")}})
        except Exception:  # noqa: BLE001
            log.exception("reading saved session failed")
    return st


@app.get("/health")
async def health(checks: int = 0) -> dict:
    """Liveness (scripts poll it every 0.25 s, so it stays instant). ?checks=1 adds the setup checklist
    {items, ready, total}: the same rows as health.get, probed in a thread, never prompting."""
    out: dict[str, Any] = {"ok": True, "clients": len(engine.hub.clients), "demo": engine.modules.demo,
                           "modules": engine.modules.describe()}
    if checks and health_mod is not None:
        out.update(await engine.health_payload())
    return out


@app.get("/library")
async def library_list() -> dict:
    """Lessons cached on this Mac, ready to start with no build: {items, continue}."""
    return await engine.library_payload()


@app.get("/library/{lid}")
async def library_get(lid: str) -> Any:
    found = await engine.library_detail(lid)  # the id is checked (pattern + inside the cache dir) before any read
    if found is None:
        return JSONResponse({"ok": False, "error": "No such lesson on this Mac."}, status_code=404)
    return found


@app.get("/progress")
async def progress_get() -> dict | None:
    """Skills, finished and in-progress lessons. null: nothing recorded yet (the app shows its empty states)."""
    return await engine.progress_payload()


@app.get("/events")
async def events(since: int = 0) -> dict:
    """Dev only (is_dev_route): the hub's recent history, for debugging an engine by hand."""
    items = list(engine.hub.history)
    return {"total": len(items), "events": items[since:]}


@app.post("/debug/pass")
async def debug_pass() -> dict:
    await engine.session.force_pass()
    return {"ok": True}


@app.post("/debug/goto/{idx}")
async def debug_goto(idx: int) -> dict:
    await engine.session.goto_step(idx)
    return {"ok": True}


@app.get("/stage")
async def stage_state() -> dict:
    """Is a Demo lesson running (the app binds the presenter keys while it is)?"""
    return stage.state(engine.session)


@app.post("/stage/{cmd}")
async def stage_cmd(cmd: str) -> dict:
    """Presenter, Demo lessons only: next (pass the step) | back (the step before) | restart (step 1, clean nn.py)."""
    fn = {"next": stage.next_step, "back": stage.back, "restart": stage.restart}.get(cmd)
    if fn is None:
        return {"ok": False, "error": f"unknown: {cmd} (next, back, restart)"}
    if not stage.on(engine.session):
        return {"ok": False, "error": "no Demo lesson is running"}
    if cmd == "restart":  # it ends the lesson it runs in: never inside this request
        task = asyncio.create_task(fn(engine.session))
        engine._replays.add(task)
        task.add_done_callback(engine._replays.discard)
        return {"ok": True}
    return {"ok": await fn(engine.session)}


@app.post("/debug/lesson")
async def debug_lesson() -> dict:
    graph = await engine.modules.build_lesson("", "", str(config.default_workdir()))
    await engine.session.load_graph(graph)
    return {"ok": True, "lesson": graph.get("lesson")}


@app.get("/demo/runs")
async def demo_runs() -> dict:
    return {"runs": [str(p.relative_to(config.REPO_ROOT)) for p in recorder.list_recordings()]}


@app.post("/demo/replay")
async def demo_replay(body: dict | None = Body(None)) -> dict:
    """Replay a recorded `tut run` (default: newest) into the active step. Body: {"name"?, "speed"?}"""
    body = body or {}
    path = recorder.find_recording(body.get("name"))
    if path is None:
        return {"ok": False, "error": "no recording found in demo/cache/runs or demo/runs"}
    speed = float(body.get("speed") or recorder.default_speed())
    task = asyncio.create_task(recorder.replay(path, engine.session.ingest, speed=speed))
    engine._replays.add(task)
    task.add_done_callback(engine._replays.discard)
    return {"ok": True, "replaying": path.name, "speed": speed}


def run() -> None:
    import argparse

    import uvicorn

    ap = argparse.ArgumentParser(description="sandhacks-tutor engine (WS + /ingest)")
    # ENGINE_HOST=0.0.0.0 / --host 0.0.0.0 lets Adrian's app reach this Mac over the LAN (ws://<mac>.local:8787)
    # 5.3: loopback unless asked; an empty ENGINE_HOST (`ENGINE_HOST= ...`) must not become "every interface"
    ap.add_argument("--host", default=os.environ.get("ENGINE_HOST", "").strip() or "127.0.0.1")
    ap.add_argument("--port", type=int, default=config.port())
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    global _bind_host
    args.host = args.host.strip() or "127.0.0.1"
    _bind_host = args.host
    if _host_name(args.host) not in _LOOPBACK:  # BUILD-PLAN section 6: say so when other machines can reach it
        if ENGINE_TOKEN:
            log.warning("listening on %s: other machines on this network reach the engine only with the engine "
                        "token (X-Miyagi-Token), on HTTP and the WebSocket", args.host)
        else:
            log.warning("listening on %s with no MIYAGI_ENGINE_TOKEN: every HTTP route and the WebSocket are open "
                        "to any machine on this network", args.host)
    if debug_routes_on():
        log.info("dev routes on (/debug/*, /demo/*): %s=1 or DEMO=1", DEBUG_ENV)
    link = _publish_token(args.port)
    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    finally:
        from server import engine_token

        engine_token.remove(link, args.port)


def _publish_token(port: int) -> str:
    """The token beside-the-engine clients send (server/engine_token.py): the app's MIYAGI_ENGINE_TOKEN, else a fresh
    random one for this launch (then it only guards the engine -> companion calls). Never logged."""
    import secrets

    from server import engine_token
    from server.workspace import vscode_ext

    link = ENGINE_TOKEN or secrets.token_urlsafe(32)
    vscode_ext.set_link_token(link)
    if engine_token.write(link, port) is None:
        log.warning("could not write the engine token to %s: the VS Code companion and `tut run` go without it",
                    engine_token.token_dir())
    return link


if __name__ == "__main__":
    run()

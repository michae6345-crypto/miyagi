"""Setup health: is this Mac ready for a lesson? The onboarding checklist and Settings > Permissions rows.

    from server.orchestrator import health
    health.snapshot()                 -> {"items": [HealthItem], "ready": n, "total": m}   GET /health, health.get
    health.summarize(items)           -> the same from items (pure)
    health.from_probes(results)       -> [HealthItem] from raw probe answers (pure)
    health.probe_all()                -> {probe: bool | str | None} (reads only; never prompts)
    health.same(a, b)                 -> True when two payloads would draw the same rows (change detection)

Rows (ids are stable; the app owns every label and button):
    screen         Screen Recording granted                         fix "permission.open" kind "screen"
    accessibility  Accessibility granted                            fix "permission.open" kind "accessibility"
    companion      the miyagi VS Code companion is installed        fix "install_companion" (VS Code found)
                   (and `running` when a VS Code window answers)        "get_vscode" (no VS Code)
                   an older companion than MIN_COMPANION reads missing  fix "install_companion", `outdated` True
                   (its token handshake is too old: the engine's calls answer 403)
    engine         this engine answers                              always ok when this code runs
    keys           an Anthropic key is set (app or .env)            fix "keys"; required False (cloud mode needs none)

State: "ok" | "missing" | "unknown". unknown = the probe couldn't tell (not macOS, pyobjc missing, a timeout): the app
shows it gray ("watching"), never as missing. ready / total count the required rows only.

Never prompts (BUILD-PLAN section 6): Screen Recording uses CGPreflightScreenCaptureAccess (never the Request call),
Accessibility uses AXIsProcessTrusted (never the WithOptions prompt), the companion is VS Code's extensions.json (or a
directory listing of its extensions folder) minus its .obsolete list, plus the companion's own 0.3 s /state scan. No
subprocess, no model call, no network beyond 127.0.0.1. A permission probe answers for the process macOS holds
responsible: the app when the engine is its child, Terminal when someone runs the engine by hand, so the app prefers
its own permission probes (main/permissions.ts) and uses these rows for the companion and the engine.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

log = logging.getLogger("orchestrator.health")

OK, MISSING, UNKNOWN = "ok", "missing", "unknown"
STATES = (OK, MISSING, UNKNOWN)
ROWS = ("screen", "accessibility", "companion", "engine", "keys")
REQUIRED = frozenset({"screen", "accessibility", "companion", "engine"})
COMPANION_ID = "miyagi.companion"  # vscode-ext/package.json publisher.name
MIN_COMPANION = (0, 0, 7)  # older companions refuse the engine's calls (403); vscode-ext/package.json ships 0.0.8


def _state(v: Any) -> str:
    if v is True:
        return OK
    if v is False:
        return MISSING
    return UNKNOWN


def item(rid: str, state: str, **extra: Any) -> dict:
    """One HealthItem: {id, state, required, fix?, kind?, running?, version?} (extras with value None are dropped)."""
    out: dict[str, Any] = {"id": rid, "state": state if state in STATES else UNKNOWN, "required": rid in REQUIRED}
    out.update({k: v for k, v in extra.items() if v is not None})
    return out


def from_probes(r: dict[str, Any]) -> list[dict]:
    """Rows from probe answers (pure). r: {screen, accessibility, vscode, companion, companionRunning,
    companionVersion, keys}: True / False / None (unknown); companionVersion a short string or None."""
    screen = _state(r.get("screen"))
    ax = _state(r.get("accessibility"))
    comp = _state(r.get("companion"))
    running = r.get("companionRunning") is True
    if running:
        comp = OK  # a window answered: installed whatever the folder listing said
    vscode = r.get("vscode")
    version = r.get("companionVersion")
    version = version if isinstance(version, str) and 0 < len(version) <= 32 else None
    outdated = comp == OK and companion_outdated(version)
    if outdated:
        comp = MISSING  # installed, but too old to talk to this engine: the same fix as not installed
    comp_fix = None
    if outdated:
        comp_fix = "install_companion"  # VS Code is there: the old companion runs in it
    elif comp != OK:
        comp_fix = "get_vscode" if vscode is False else "install_companion"
    keys = _state(r.get("keys"))
    return [
        item("screen", screen, fix="permission.open" if screen != OK else None, kind="screen"),
        item("accessibility", ax, fix="permission.open" if ax != OK else None, kind="accessibility"),
        item("companion", comp, fix=comp_fix, running=running if comp == OK else None, version=version,
             outdated=True if outdated else None),
        item("engine", OK),
        item("keys", keys, fix="keys" if keys == MISSING else None),
    ]


def summarize(items: list[dict]) -> dict:
    """{"items", "ready", "total"} (pure). ready = required rows that are ok; total = required rows."""
    rows = [dict(i) for i in items if isinstance(i, dict) and i.get("id")]
    req = [i for i in rows if i.get("required")]
    return {"items": rows, "ready": sum(i.get("state") == OK for i in req), "total": len(req)}


def fingerprint(payload: dict | None) -> tuple:
    """What the rows look like (id, state, fix, running): equal fingerprints draw the same checklist."""
    if not isinstance(payload, dict):
        return ()
    return tuple((i.get("id"), i.get("state"), i.get("fix"), i.get("running")) for i in payload.get("items") or []
                 if isinstance(i, dict))


def same(a: dict | None, b: dict | None) -> bool:
    return fingerprint(a) == fingerprint(b)


# ------------------------------------------------------------------------------------------------ probes (read-only)
def screen_granted() -> bool | None:
    """CGPreflightScreenCaptureAccess(): never shows the macOS prompt. None off macOS or without pyobjc."""
    if sys.platform != "darwin":
        return None
    try:
        import Quartz  # type: ignore[import-not-found]

        return bool(Quartz.CGPreflightScreenCaptureAccess())
    except Exception:  # noqa: BLE001 - ImportError, or a macOS without the call
        return None


def accessibility_granted() -> bool | None:
    """AXIsProcessTrusted() via ctypes: never prompts (the WithOptions variant would). None off macOS."""
    if sys.platform != "darwin":
        return None
    try:
        import ctypes

        lib = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
        lib.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(lib.AXIsProcessTrusted())
    except (OSError, AttributeError):
        return None


def _extensions_dir() -> Path:
    env = os.environ.get("VSCODE_EXTENSIONS", "").strip()  # VS Code's own override
    return Path(env).expanduser() if env else Path.home() / ".vscode" / "extensions"


_VERSION_RE = re.compile(r"\d+(?:\.\d+)*")
MAX_INDEX_BYTES = 4 * 1024 * 1024


def _version_key(v: str) -> tuple[int, ...]:
    """"0.10.0" -> (0, 10, 0), so 0.10.0 ranks above 0.9.0 (a text sort gets that backwards). () when unparseable."""
    m = _VERSION_RE.match(v or "")
    return tuple(int(x) for x in m.group(0).split(".")) if m else ()


def companion_outdated(version: str | None) -> bool:
    """True when `version` parses and is older than MIN_COMPANION. An unknown or unparseable version is not outdated
    (the folder listing can miss it; a wrong install prompt is worse than none)."""
    key = _version_key(version or "")
    if not key:
        return False
    pad = max(len(key), len(MIN_COMPANION))
    return key + (0,) * (pad - len(key)) < MIN_COMPANION + (0,) * (pad - len(MIN_COMPANION))


def _read_json(p: Path) -> Any:
    """A small JSON file VS Code keeps in its extensions folder, or None (missing, too big, unreadable)."""
    try:
        if not p.is_file() or p.stat().st_size > MAX_INDEX_BYTES:
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _obsolete(d: Path) -> set[str]:
    """Folder names VS Code marked for removal in <extensions>/.obsolete ({"<folder>": true}): uninstalled, not yet
    pruned."""
    data = _read_json(d / ".obsolete")
    return {k for k, v in data.items() if v is True} if isinstance(data, dict) else set()


def _from_index(d: Path, obsolete: set[str]) -> tuple[bool, str | None] | None:
    """(installed, version) from <extensions>/extensions.json, VS Code's own list. None when there is no usable list
    (older VS Code), so the caller falls back to the folder names."""
    data = _read_json(d / "extensions.json")
    if not isinstance(data, list):
        return None
    versions = []
    for e in data:
        if not isinstance(e, dict):
            continue
        ident = e.get("identifier")
        if not isinstance(ident, dict) or str(ident.get("id") or "").lower() != COMPANION_ID:
            continue
        folder = e.get("relativeLocation")
        if not isinstance(folder, str):
            loc = e.get("location")
            folder = Path(str(loc.get("path") or loc.get("fsPath") or "")).name if isinstance(loc, dict) else ""
        if folder and folder in obsolete:
            continue
        v = e.get("version")
        versions.append(v if isinstance(v, str) else "")
    if not versions:
        return False, None
    newest = max(versions, key=_version_key)
    return True, newest[:32] or None


def companion_installed() -> tuple[bool | None, str | None]:
    """(installed, version) from VS Code's extensions folder (no `code` subprocess): extensions.json when VS Code keeps
    one, else the folder names; either way an uninstall still waiting in .obsolete doesn't count. (None, None) if it
    can't read the folder."""
    d = _extensions_dir()
    try:
        if not d.is_dir():
            return False, None
        obsolete = _obsolete(d)
        indexed = _from_index(d, obsolete)
        if indexed is not None:
            return indexed
        names = [p.name for p in d.iterdir()
                 if p.name.lower().startswith(COMPANION_ID + "-") and p.name not in obsolete and p.is_dir()]
    except OSError:
        return None, None
    if not names:
        return False, None
    versions = [n[len(COMPANION_ID) + 1:] for n in names]
    newest = max(versions, key=_version_key)
    return True, newest[:32] or None


def vscode_installed() -> bool | None:
    """VS Code's app bundle in /Applications or ~/Applications, or `code` on PATH (no Spotlight query)."""
    if sys.platform != "darwin":
        return None
    import shutil

    for base in (Path("/Applications"), Path.home() / "Applications"):
        if (base / "Visual Studio Code.app").exists():
            return True
    return True if shutil.which("code") else False


def companion_running() -> bool | None:
    """A VS Code window's companion answered /state on 127.0.0.1 (the 0.3 s scan). None if the client can't load."""
    try:
        from server.workspace import vscode_ext

        return bool(vscode_ext.windows())
    except Exception as e:  # noqa: BLE001
        log.debug("health: companion scan failed: %s", e)
        return None


def keys_set() -> bool | None:
    try:
        from server.config import key_source

        return key_source("anthropic") != "missing"
    except Exception:  # noqa: BLE001
        return None


PROBES: dict[str, Callable[[], Any]] = {  # + companion / companionVersion from companion_installed()
    "screen": screen_granted,
    "accessibility": accessibility_granted,
    "vscode": vscode_installed,
    "companionRunning": companion_running,
    "keys": keys_set,
}


def probe_all(probes: dict[str, Callable[[], Any]] | None = None) -> dict[str, Any]:
    """Run every probe (each one guarded: a probe that raises reads as unknown). Blocking, well under a second:
    call it from a thread (`await asyncio.to_thread(health.snapshot)`)."""
    out: dict[str, Any] = {}
    for name, fn in (probes or PROBES).items():
        try:
            out[name] = fn()
        except Exception as e:  # noqa: BLE001
            log.debug("health probe %s failed: %s", name, e)
            out[name] = None
    if probes is None:  # the folder listing is one of the defaults; injected probes name their own
        try:
            out["companion"], out["companionVersion"] = companion_installed()
        except Exception:  # noqa: BLE001
            out["companion"], out["companionVersion"] = None, None
    return out


def snapshot(probes: dict[str, Callable[[], Any]] | None = None) -> dict:
    """GET /health and the `health` event: {"items", "ready", "total"}."""
    return summarize(from_probes(probe_all(probes)))

"""Check self-check (Nov 25): can a manual Check (Check my work / Check again) actually see anything?

A real learner pressed Check again six times and got the same "Not yet" each time: every judge call carried exactly
the same evidence (no screen text, the same file), so the verdict could never change and nothing said why. Before a
manual check answers, the engine now asks four free questions and says what it found:

  screen   is capture returning frames?   ok | off (Screen Recording) | error | paused | asleep | stale | none
  ocr      is OCR producing text?         ok | empty | unknown
  vscode   is the companion connected?    connected | not_connected | unknown
  cloud    is miyagi cloud reachable?     ok | unreachable | unauthorized | paused | quota | missing | off | not_used | unknown

No paid call: the cloud check is GET <cloud origin>/healthz (the proxy's free liveness route, the same one
coach/fast_ask.py warms the connection with), cached CLOUD_TTL_S, and only when the judge goes through the cloud.

`issue_for` turns a report into the one thing to tell the learner (contract Card.checkIssue): blocking when the check
had nothing to look at (it answers "Couldn't check" with the fix, never "Not yet"), else a note under the "Not yet".
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

log = logging.getLogger("orchestrator.check_health")

CLOUD_TTL_S = 60.0  # one /healthz per minute at most, however often Check is pressed
CLOUD_TIMEOUT_S = 2.0
# The newest frame is older than this and no fresh capture came in: the screen read is stale. Above the reader's idle
# heartbeat (perf_tier idle_heartbeat_max 10 s x 1.5) plus its max_age (15 s): a still screen is not a stale one.
STALE_S = 30.0
# A Check's capture that missed check_wait_s (1.2 s: the capture lock held by a tick, OCR, the AX wait on a slow Mac)
# is awaited this much longer before the screen counts as stale; one still running after that is slow, never stale.
FRESH_EXTRA_S = 3.0
VSCODE_TIMEOUT_S = 0.3

_cloud_cache: dict[str, Any] = {"t": -1e9, "url": None, "state": None}


# ------------------------------------------------------------------ the four probes

async def settle_fresh(s: Any, fresh: bool | None, extra: float = FRESH_EXTRA_S) -> tuple[bool | None, bool]:
    """(fresh, capture still running). fresh_frame gave up after check_wait_s, but its capture job goes on: wait for that
    same job up to `extra` s more (never a second capture). Its result decides; still running = slow, not stale."""
    if fresh is not False:
        return fresh, False
    job = getattr(getattr(s, "screen", None), "fresh_job", None)
    if job is None or not isinstance(job, asyncio.Future):
        return fresh, False
    if not job.done():
        try:
            await asyncio.wait_for(asyncio.shield(job), extra)
        except Exception:  # noqa: BLE001 - slow or failed: decided below
            pass
    if not job.done():
        return False, True
    return (not job.cancelled() and job.exception() is None), False


def screen_state(s: Any, fresh: bool | None, running: bool = False) -> tuple[str, float | None, str | None]:
    """(state, newest frame age in s or None, down reason). `fresh`: did this check get a frame captured now
    (None: not asked). `running`: this check's capture is still going (slow, so never "stale")."""
    scr = getattr(s, "screen", None)
    if scr is None:
        return "none", None, None  # no screen by design (ORCH_SCREEN=0 / headless / not macOS): nothing broken
    if not getattr(scr, "active", True):
        err = getattr(scr, "start_error", None)  # the reader failed to start (error), or was never meant to (none)
        return ("error" if err else "none"), None, err
    try:
        down = s.screen_down_reason(include_ax=False)
    except Exception:  # noqa: BLE001
        down = None
    if down:
        low = down.lower()
        if "asleep" in low or "locked" in low:
            return "asleep", None, down
        return ("off" if low == "no_permission" else "error"), None, down
    if getattr(scr, "paused", False) and getattr(scr, "reader", None) is not None:
        return "paused", None, None
    age = None
    try:
        obs = scr.latest()
        t = getattr(obs, "t", None)
        if t:
            age = max(0.0, time.time() - float(t))
    except Exception:  # noqa: BLE001
        obs = None
    if fresh is False and not running and (age is None and getattr(scr, "reader", None) is not None or (age or 0) > STALE_S):
        return "stale", age, None
    return "ok", age, None


def ocr_state(s: Any) -> tuple[str, int]:
    """(ok | empty | unknown, how many text lines the latest frame has, every app)."""
    try:
        lines = s._screen_lines()
    except Exception:  # noqa: BLE001
        return "unknown", 0
    if lines is None:
        return "unknown", 0  # no frame to read (screen_state says why), or a reader that keeps no text
    n = sum(len(v or []) for v in lines.values())
    return ("ok" if n else "empty"), n


def vscode_windows() -> list[dict]:
    """The companion extension's windows (localhost 8791-8799, ~0.3 s at most). Tests replace it."""
    from server.workspace import vscode_ext

    return vscode_ext.windows(timeout=VSCODE_TIMEOUT_S)


async def vscode_state(s: Any, exact: bool, has_files: bool = True) -> str:
    """connected: VS Code's exact buffer was read for this check, or a window answers; unknown without the real screen
    reader (tests, the stage) unless vscode_windows was replaced, and unknown when the step has no file in a "Just teach
    me" lesson (a video / app lesson): no port scan for nothing."""
    if exact:
        return "connected"
    if not (getattr(s, "lesson_mode", False) and has_files):
        return "unknown"
    real = getattr(getattr(s, "screen", None), "reader", None) is not None
    if not real and vscode_windows is _REAL_WINDOWS:
        return "unknown"
    try:
        wins = await asyncio.wait_for(asyncio.to_thread(vscode_windows), VSCODE_TIMEOUT_S + 0.5)
    except Exception:  # noqa: BLE001
        return "unknown"
    return "connected" if wins else "not_connected"


_REAL_WINDOWS = vscode_windows


def _cloud_route() -> tuple[str | None, str]:
    """(the proxy URL when the judge goes through it, the state that needs no network)."""
    try:
        from server import config as sc
    except Exception:  # noqa: BLE001
        return None, "unknown"
    try:
        st = sc.cloud_status()  # ok | missing | off | unauthorized | paused | quota
        route = sc.mode("anthropic")  # byok | cloud | env | missing
    except Exception:  # noqa: BLE001
        return None, "unknown"
    if route in ("byok", "env"):
        return None, "not_used"
    if st != "ok":
        return None, st
    return sc.cloud_url(), "ok"


async def cloud_state(probe: bool = True) -> str:
    """The cloud as the judge sees it. A probe is GET <origin>/healthz (free, never a model), at most every CLOUD_TTL_S."""
    url, st = _cloud_route()
    if url is None or not probe:
        return st
    now = time.monotonic()
    if _cloud_cache["url"] == url and now - _cloud_cache["t"] < CLOUD_TTL_S and _cloud_cache["state"]:
        return _cloud_cache["state"]
    u = urlsplit(url)
    state = "unreachable"
    try:
        import httpx

        async with httpx.AsyncClient(timeout=CLOUD_TIMEOUT_S, follow_redirects=False) as c:
            r = await c.get(f"{u.scheme}://{u.netloc}/healthz")
        state = "ok" if r.status_code < 500 else "unreachable"
    except Exception as e:  # noqa: BLE001
        log.info("self-check: cloud /healthz failed (%s)", type(e).__name__)
    _cloud_cache.update(t=now, url=url, state=state)
    return state


def start_cloud_probe() -> asyncio.Future | None:
    """Start the cloud probe now (it runs beside the capture and the checks); None when it needs no network."""
    url, _ = _cloud_route()
    if url is None:
        return None
    job = asyncio.ensure_future(cloud_state(True))
    job.add_done_callback(lambda t: t.cancelled() or t.exception())
    return job


async def self_check(s: Any, *, fresh: bool | None = None, exact: bool = False, has_files: bool = True,
                     cloud_job: asyncio.Future | None = None, probe_cloud: bool = False) -> dict:
    """The report, also kept on the session (last_self_check, GET /health) and logged."""
    fresh, running = await settle_fresh(s, fresh)
    screen, age, down = screen_state(s, fresh, running)
    ocr, n = ocr_state(s) if screen in ("ok", "stale") else ("unknown", 0)
    vscode = await vscode_state(s, exact, has_files)
    cloud = "unknown"
    if cloud_job is not None:
        try:
            cloud = await asyncio.wait_for(asyncio.shield(cloud_job), CLOUD_TIMEOUT_S + 0.5)
        except Exception:  # noqa: BLE001
            cloud = "unreachable"
    else:
        cloud = await cloud_state(probe_cloud)
    rep = {"screen": screen, "ocr": ocr, "vscode": vscode, "cloud": cloud, "frameAgeS": round(age, 1) if age is not None else None,
           "ocrLines": n, "fresh": fresh, "at": int(time.time() * 1000)}
    if down:
        rep["screenWhy"] = str(down)[:120]
    if running:
        rep["captureSlow"] = True  # this check's capture outlived check_wait_s + FRESH_EXTRA_S: slow, not stale
    try:
        s.last_self_check = rep
    except Exception:  # noqa: BLE001
        pass
    log.info("self-check: screen=%s ocr=%s (%d lines) vscode=%s cloud=%s fresh=%s slow=%s age=%s", screen, ocr, n, vscode,
             cloud, fresh, running, rep["frameAgeS"])
    return rep


def brief(rep: dict | None) -> dict | None:
    """The four states only (contract SelfCheck), for the card."""
    if not rep:
        return None
    return {k: rep[k] for k in ("screen", "ocr", "vscode", "cloud") if k in rep}


# ------------------------------------------------------------------ what to tell the learner

_JUDGE_CLOUD = {"cloud", "no_key"}  # the proxy refused (paused / quota / auth), or no token / key at all
_JUDGE_DOWN = {"connection", "api"}  # the network / proxy / an HTTP error


def _issue(kind: str, title: str, body: str, nxt: str, blocking: bool, rep: dict | None) -> dict:
    out = {"kind": kind, "title": title, "body": body, "next": nxt, "blocking": blocking}
    if (b := brief(rep)) is not None:
        out["selfCheck"] = b
    return out


def screen_issue(rep: dict, *, has_files: bool, file: str | None = None) -> dict | None:
    """The screen can't be read for this check. Blocking when no file stands in for it (nothing to judge)."""
    name = Path(file).name if file else "your file"
    only = f" I checked {name} on disk only." if has_files else ""
    st = rep.get("screen")
    if st == "off":
        return _issue("screen_off", "Can't see your screen",
                      "Screen Recording is off for miyagi, so I can't see what you did." + only,
                      "Turn on Screen Recording for miyagi in System Settings, then press Check again.", not has_files, rep)
    if st == "error":
        return _issue("screen_error", "Can't see your screen",
                      "miyagi's screen reader isn't running, so I can't see what you did." + only,
                      "Press Check again. If this keeps happening, quit and reopen miyagi.", not has_files, rep)
    if st in ("stale", "paused") or (st == "ok" and rep.get("ocr") == "empty"):
        what = "read any text on" if st == "ok" else "get a fresh look at"
        # A frame with no text at all is odd but not proof of blindness (a blank desktop): a note, never blocking alone
        return _issue("screen_stale", "Couldn't read your screen", f"I couldn't {what} your screen just now." + only,
                      "Bring the window you're working in to the front, then press Check again.",
                      not has_files and st == "stale", rep)  # blocks only when stale with no capture running
    return None


def explains_blank(issue: dict | None) -> bool:
    """Does this issue explain a "Not yet" with nothing specific in it (no row, no judge words)? Then the answer is
    "Couldn't check" with it. A note (text-less frame, the extension) does not: the plain "Not yet" stays."""
    if not issue:
        return False
    if issue.get("kind") in ("screen_off", "screen_error", "check_failed", "cloud_unreachable", "cloud_auth"):
        return True
    return issue.get("kind") == "screen_stale" and (issue.get("selfCheck") or {}).get("screen") != "ok"


def issue_for(rep: dict | None, *, has_files: bool, file: str | None = None, judge_error: dict | None = None,
              eval_error: str | None = None, exact: bool = False, lesson_mode: bool = False) -> dict | None:
    """The one issue to show with this check's answer, most serious first, or None when the check saw what it needs."""
    rep = rep or {}
    if eval_error:
        return _issue("check_failed", "Couldn't run the checks",
                      "Something went wrong while checking this step, so I can't say yet.",
                      "Press Check again. If this keeps happening, quit and reopen miyagi.", True, rep)
    if (it := screen_issue(rep, has_files=has_files, file=file)) is not None:
        return it
    if judge_error:
        kind = str(judge_error.get("kind") or "")
        if kind in _JUDGE_CLOUD or rep.get("cloud") in ("unauthorized", "paused", "quota", "missing"):
            msg = str(judge_error.get("message") or "")
            why = ("today's free checks are used up" if "quota" in msg or rep.get("cloud") == "quota"
                   else "your miyagi account isn't signed in" if "auth" in msg or rep.get("cloud") in ("unauthorized", "missing")
                   else "miyagi cloud is paused")
            return _issue("cloud_auth", "miyagi cloud said no", f"Only the automatic checks ran: {why}.",
                          "Open miyagi's Settings to sign in, then press Check again.", False, rep)
        if kind in _JUDGE_DOWN or rep.get("cloud") == "unreachable":
            return _issue("cloud_unreachable", "Couldn't reach miyagi cloud",
                          "Only the automatic checks ran, so I can't say exactly what's missing.",
                          "Check your internet connection, then press Check again.", False, rep)
    if lesson_mode and has_files and not exact and rep.get("vscode") == "not_connected":
        name = Path(file).name if file else "your file"
        return _issue("vscode_ext", "VS Code extension not connected",
                      f"I read {name} from disk, so edits you haven't saved don't count yet.",
                      "Save the file, or reinstall the miyagi extension in VS Code, then press Check again.", False, rep)
    return None

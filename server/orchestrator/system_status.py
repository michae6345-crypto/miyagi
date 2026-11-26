"""System status: network, AI busy and setup health, polled in the background and sent ONLY when they change.

    st = SystemStatus(emit)                 # emit(type, payload): sync or async (Session.emit / hub broadcast)
    st.start()                              # background poll (network every POLL_S, health every HEALTH_S)
    st.mark_busy(30)                        # a provider answered 429 / overloaded: status busy + retryInS once
    st.note_network(False)                  # a real request failed to connect: counts as one offline sample
    await st.refresh_health()               # health.get: sample now, return the payload (the caller replies)
    st.replay()                             # what a newly connected app needs: [(type, payload)]
    await st.stop()

What it sends (W0-1 contract names; shapes in app/agents/eng-modules.md):
    blocker {kind: "network"}               offline: OFFLINE_AFTER failed samples in a row (one blip is not offline)
    blocker {kind: "network", clear: true}  back online after that (one good sample)
    status  {state: "busy", retryInS}       mark_busy(); again only if the retry time moves by RETRY_STEP_S or more
    status  <restore_status()>              busy is over: the session's own status (nothing when no callback given)
    health  {items, ready, total}           the checklist rows changed (health.same); the first sample counts

Nothing is sent while nothing changes, so the app's notices never flicker and the socket stays quiet. The pure
pieces (settle_network, changes) take everything as arguments; the class only keeps the last snapshot and the
clock. Health sampling never prompts (health.py) and stops while `watch_health(False)`. The network probe is a
plain TCP connect (no HTTP request, no API call, no cost) to MIYAGI_NET_PROBE (host:port, default
api.anthropic.com:443); MIYAGI_NET_PROBE=0 turns it off (network stays unknown and no blocker is ever sent).
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import math
import os
import socket
import time
from collections.abc import Callable
from typing import Any

from . import health as health_mod

log = logging.getLogger("orchestrator.system_status")

ONLINE, OFFLINE, UNKNOWN = "online", "offline", "unknown"
POLL_S = 5.0
HEALTH_S = 15.0
OFFLINE_AFTER = 2  # failed samples in a row before "offline"
NET_TIMEOUT_S = 2.0
RETRY_STEP_S = 1.0
MAX_RETRY_S = 3600
DEFAULT_NET_PROBE = "api.anthropic.com:443"

Change = tuple[str, dict]


def _consume(fut: asyncio.Future) -> None:
    """Read a finished probe's exception so a late failure after a timeout is never reported as unretrieved."""
    if not fut.cancelled():
        fut.exception()


# ------------------------------------------------------------------------------------------------ pure pieces
def settle_network(samples: list[bool | None], prev: str = UNKNOWN, need: int = OFFLINE_AFTER) -> str:
    """The network state from recent samples (oldest first): online on the newest good sample, offline after `need`
    failed samples in a row, else the previous state (a single failure, or probes that couldn't tell)."""
    known = [s for s in samples if s is not None]
    if not known:
        return prev
    if known[-1] is True:
        return ONLINE
    tail = 0
    for s in reversed(known):
        if s is False:
            tail += 1
        else:
            break
    return OFFLINE if tail >= need else prev


def retry_in(busy_until: float | None, now: float) -> int | None:
    """Whole seconds left before a retry (>= 1), or None when not busy."""
    if busy_until is None or busy_until <= now:
        return None
    return max(1, min(MAX_RETRY_S, math.ceil(busy_until - now)))


def changes(prev: dict, cur: dict, now: float, restore: dict | None = None) -> list[Change]:
    """What to send going from snapshot `prev` to `cur` (pure). Snapshots: {network, busyUntil, health}.
    restore: the status to put back when busy ends (None: send nothing then)."""
    out: list[Change] = []
    pn, cn = prev.get("network", UNKNOWN), cur.get("network", UNKNOWN)
    if cn == OFFLINE and pn != OFFLINE:
        out.append(("blocker", {"kind": "network"}))
    elif pn == OFFLINE and cn == ONLINE:
        out.append(("blocker", {"kind": "network", "clear": True}))

    pb, cb = prev.get("busyUntil"), cur.get("busyUntil")
    left = retry_in(cb, now)
    if left is not None:  # busy now: new, or its retry time moved
        if pb is None or abs(cb - pb) >= RETRY_STEP_S:
            out.append(("status", {"state": "busy", "retryInS": left}))
    elif pb is not None and restore:  # was busy at the last send, not any more
        out.append(("status", dict(restore)))

    ph, ch = prev.get("health"), cur.get("health")
    if isinstance(ch, dict) and not health_mod.same(ph, ch):
        out.append(("health", ch))
    return out


# ------------------------------------------------------------------------------------------------ probes
def _net_target() -> tuple[str, int] | None:
    spec = os.environ.get("MIYAGI_NET_PROBE", "").strip() or DEFAULT_NET_PROBE
    if spec.lower() in ("0", "off", "false", "no"):
        return None
    host, _, port = spec.rpartition(":")
    try:
        return (host or spec, int(port)) if host else (spec, 443)
    except ValueError:
        return (spec, 443)


def net_probe() -> bool | None:
    """True when a TCP connection to the probe host opens within NET_TIMEOUT_S (no bytes sent). None when off."""
    target = _net_target()
    if target is None:
        return None
    try:
        with socket.create_connection(target, timeout=NET_TIMEOUT_S):
            return True
    except OSError:
        return False


# ------------------------------------------------------------------------------------------------ the poller
class SystemStatus:
    def __init__(self, emit: Callable[[str, dict], Any], *,
                 net_probe: Callable[[], bool | None] | None = net_probe,
                 health_probe: Callable[[], dict] | None = health_mod.snapshot,
                 restore_status: Callable[[], dict | None] | None = None,
                 poll_s: float = POLL_S, health_s: float = HEALTH_S,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._emit = emit
        self._net_probe = net_probe
        self._health_probe = health_probe
        self._restore = restore_status
        self.poll_s, self.health_s = poll_s, health_s
        self._clock = clock
        self._samples: list[bool | None] = []
        self._snap: dict[str, Any] = {"network": UNKNOWN, "busyUntil": None, "health": None}
        self._busy_until: float | None = None
        self._health_at: float | None = None
        self._watch_health = True
        self._task: asyncio.Task | None = None
        self._net_inflight: asyncio.Future | None = None  # the probe thread, kept until it really ends
        self._lock = asyncio.Lock()

    # -------- inputs from the rest of the engine
    def mark_busy(self, retry_in_s: float) -> None:
        """A provider said "busy, retry later". Sent on the next tick (or right away by `await flush()`)."""
        try:
            secs = float(retry_in_s)
        except (TypeError, ValueError):
            return
        if not math.isfinite(secs) or secs <= 0:
            return
        self._busy_until = self._clock() + min(secs, MAX_RETRY_S)

    def clear_busy(self) -> None:
        """A call went through: busy is over before its time."""
        self._busy_until = None

    def note_network(self, ok: bool) -> None:
        """A real request connected (True) or couldn't (False): one network sample."""
        self._push(bool(ok))

    def watch_health(self, on: bool) -> None:
        """Health sampling on (default) or off (no permission probe runs while off)."""
        self._watch_health = bool(on)

    # -------- reads
    def current(self) -> dict:
        """{network, busy: retryInS | None, health} as last sent."""
        return {"network": self._snap["network"], "busy": retry_in(self._snap["busyUntil"], self._clock()),
                "health": self._snap["health"]}

    def replay(self) -> list[Change]:
        """What a newly connected app needs to match the engine: the offline blocker, busy, the last health."""
        out: list[Change] = []
        if self._snap["network"] == OFFLINE:
            out.append(("blocker", {"kind": "network"}))
        left = retry_in(self._snap["busyUntil"], self._clock())
        if left is not None:
            out.append(("status", {"state": "busy", "retryInS": left}))
        if isinstance(self._snap["health"], dict):
            out.append(("health", self._snap["health"]))
        return out

    # -------- sampling
    def _push(self, sample: bool | None) -> None:
        self._samples = (self._samples + [sample])[-(OFFLINE_AFTER + 2):]

    async def _sample_health(self) -> dict | None:
        if self._health_probe is None:
            return None
        try:
            h = await asyncio.to_thread(self._health_probe)
        except Exception as e:  # noqa: BLE001
            log.debug("health sample failed: %s", e)
            return None
        self._health_at = self._clock()
        return h if isinstance(h, dict) else None

    async def refresh_health(self) -> dict | None:
        """Sample health now (health.get). The snapshot is updated without sending, so the poller doesn't send the
        same rows again; the caller replies with the returned payload. Holds the lock, so a tick() that is sampling
        health at the same time can't diff its older sample against this newer snapshot."""
        async with self._lock:
            h = await self._sample_health()
            if h is not None:
                self._snap = {**self._snap, "health": h}
            return h

    async def _sample_network(self) -> None:
        if self._net_probe is None:
            return
        prev = self._net_inflight
        if prev is not None and not prev.done():
            # The last probe is still stuck (create_connection's timeout does not bound getaddrinfo, so a hanging DNS
            # holds its thread). Start no other thread: they would pile up in the default executor every
            # asyncio.to_thread in the engine shares. Still hung past its timeout = nothing answered, the same sample
            # a timeout gives (None would push the earlier failure out of the window and never read offline).
            self._push(False)
            return
        fut = self._net_inflight = asyncio.ensure_future(asyncio.to_thread(self._net_probe))
        fut.add_done_callback(_consume)
        try:
            # shield: on timeout the thread keeps running and `fut` stays not done, which is what the check above sees
            ok = await asyncio.wait_for(asyncio.shield(fut), NET_TIMEOUT_S + 1.0)
        except asyncio.TimeoutError:
            ok = False  # DNS or connect hung past the timeout: nothing answered
        except Exception as e:  # noqa: BLE001
            log.debug("network probe failed: %s", e)
            ok = None
        self._push(ok)

    async def flush(self) -> list[Change]:
        """Send what changed since the last send, without sampling (after mark_busy / note_network)."""
        async with self._lock:
            return await self._advance(None)

    async def tick(self) -> list[Change]:
        """One poll: sample the network (and health when due), send what changed. Returns what was sent."""
        async with self._lock:
            await self._sample_network()
            health = self._snap["health"]
            now = self._clock()
            if self._watch_health and (self._health_at is None or now - self._health_at >= self.health_s):
                h = await self._sample_health()
                if h is not None:
                    health = h
            return await self._advance(health)

    async def _advance(self, health: dict | None) -> list[Change]:
        now = self._clock()
        if self._busy_until is not None and self._busy_until <= now:
            self._busy_until = None
        cur = {"network": settle_network(self._samples, self._snap["network"]),
               "busyUntil": self._busy_until,
               "health": health if health is not None else self._snap["health"]}
        restore = None
        if self._snap["busyUntil"] is not None and cur["busyUntil"] is None and self._restore is not None:
            try:
                restore = self._restore()
            except Exception as e:  # noqa: BLE001
                log.debug("restore_status failed: %s", e)
        sent = changes(self._snap, cur, now, restore if isinstance(restore, dict) else None)
        self._snap = cur
        for typ, payload in sent:
            await self._send(typ, payload)
        return sent

    async def _send(self, typ: str, payload: dict) -> None:
        try:
            r = self._emit(typ, payload)
            if inspect.isawaitable(r):
                await r
        except Exception as e:  # noqa: BLE001 - a closed socket must not stop the poller
            log.debug("system status emit %s failed: %s", typ, e)

    # -------- lifecycle
    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.get_running_loop().create_task(self._run(), name="system-status")

    async def _run(self) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("system status tick failed")
            await asyncio.sleep(self.poll_s)

    async def stop(self) -> None:
        self._net_inflight = None  # a stuck probe thread ends on its own; nothing waits for it
        t, self._task = self._task, None
        if t is not None:
            t.cancel()
            try:
                await t
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

"""Engine-side voice for `speak` events (ElevenLabs track). The coach owns what is said.

    from server.coach import voice
    app.include_router(voice.router)                               # GET /tts/<hash>.mp3
    if session.voice and not session.typing():                     # E4's gate: voice on, no keystroke in 2 s
        if s := await voice.speak_event("offtrack", card):         # → {"audioUrl", "text"} | None
            await emit("speak", s)

Only short lines: the step title on `step.started`, the one-line diagnosis (card title) on
`offtrack`, "Nice, step passed." on `step.passed`. Audio comes from ElevenLabs' streaming TTS
(POST /v1/text-to-speech/{voice_id}/stream, `eleven_flash_v2_5`, mp3_44100_128), cached on disk
by a hash of (voice, model, text), so repeats and prefetched step titles are instant.
Never raises: any failure → None and one log line; the coach is never blocked.

Env / keys: ELEVENLABS_API_KEY (via server.config / set_keys), ELEVENLABS_VOICE_ID,
COACH_TTS_MODEL (default eleven_flash_v2_5), COACH_TTS_DIR (default ~/.cache/sandhacks-tutor/tts).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import time
from pathlib import Path

import httpx

from . import llm

log = logging.getLogger("coach.voice")

API = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
DEFAULT_MODEL = "eleven_flash_v2_5"  # docs: ~100 ms model latency, 40k chars, replaces eleven_turbo_v2_5
OUTPUT_FORMAT = "mp3_44100_128"
MAX_CHARS = 200  # we only ever speak one short line
ROUTE = "/tts"

_client: httpx.AsyncClient | None = None
_transport: httpx.AsyncBaseTransport | None = None  # tests inject httpx.MockTransport
_inflight: dict[str, asyncio.Task] = {}
_logged: set[str] = set()
last_timing: dict = {}


def cache_dir() -> Path:
    d = Path(os.environ.get("COACH_TTS_DIR") or Path.home() / ".cache" / "sandhacks-tutor" / "tts")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _log_once(reason: str) -> None:
    if reason not in _logged:
        _logged.add(reason)
        log.warning("voice: %s (no audio; coaching continues)", reason)


def _http() -> httpx.AsyncClient:
    """One keep-alive client so later lines skip the TLS handshake."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0), transport=_transport)
    return _client


# ---------- what gets said ----------------------------------------------------------------------

def spoken(text: str) -> str:
    """Make a line read well aloud: 1e-3 → 0.001, β → beta, code-ish tokens softened, one line."""
    def sci(m: re.Match) -> str:
        mant, exp = float(m.group(1)), int(m.group(2))
        return f"{mant * 10 ** exp:.{max(0, -exp)}f}".rstrip("0").rstrip(".") if -6 <= exp <= 6 else m.group(0)

    t = re.sub(r"(\d+(?:\.\d+)?)[eE]([+-]?\d+)", sci, text or "")
    t = t.replace("β", "beta").replace("λ", "lambda").replace("_", " ")
    t = re.sub(r"\blr\b", "learning rate", t)
    t = re.sub(r"[`*#]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    if t and t[-1] not in ".!?":
        t += "."
    return t[:MAX_CHARS]


def line_for(event: str, payload: dict) -> str | None:
    """The one short line for an engine event, or None if this event is not spoken."""
    if event == "step.started":
        title = (payload.get("title") or "").strip()
        n = payload.get("index")
        return spoken(f"Step {n}: {title}" if isinstance(n, int) and title else title) or None
    if event == "offtrack":
        return spoken(payload.get("title") or "") or None
    if event == "step.passed":
        return "Nice, step passed."
    return None


# ---------- synthesis -------------------------------------------------------------------------------

def _key(text: str, voice_id: str, model: str) -> str:
    return hashlib.sha256(f"{voice_id}\n{model}\n{OUTPUT_FORMAT}\n{text}".encode()).hexdigest()[:20]


def audio_url(h: str) -> str:
    return f"{ROUTE}/{h}.mp3"


def path_for(name: str) -> Path | None:
    """Cached file for a `<hash>.mp3` name (validated: no paths, hex only), or None."""
    m = re.fullmatch(r"([0-9a-f]{20})\.mp3", name or "")
    if not m:
        return None
    p = cache_dir() / name
    return p if p.is_file() else None


async def _synthesize(text: str, voice_id: str, model: str, key: str, out: Path) -> bool:
    t0 = time.monotonic()
    tmp = out.with_suffix(".part")
    try:
        async with _http().stream(
            "POST",
            API.format(voice_id=voice_id),
            params={"output_format": OUTPUT_FORMAT},
            headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
            json={"text": text, "model_id": model},
        ) as r:
            if r.status_code != 200:
                await r.aread()
                _log_once(f"ElevenLabs HTTP {r.status_code}")
                return False
            first = None
            n = 0
            with tmp.open("wb") as f:
                async for chunk in r.aiter_bytes():
                    if first is None:
                        first = time.monotonic() - t0
                    f.write(chunk)
                    n += len(chunk)
        if n == 0:
            _log_once("ElevenLabs returned no audio")
            return False
        tmp.replace(out)
        last_timing.update(first_byte_s=round(first or 0, 3), total_s=round(time.monotonic() - t0, 3), bytes=n, model=model)
        log.info("voice: %d bytes, first byte %.2fs, total %.2fs", n, first or 0, time.monotonic() - t0)
        return True
    except (httpx.HTTPError, OSError) as e:
        _log_once(f"ElevenLabs request failed ({type(e).__name__})")
        return False
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


async def speak(text: str) -> dict | None:
    """`speak` payload {"audioUrl", "text"} for a short line, or None (no key, error, empty line)."""
    text = spoken(text)
    if not text:
        return None
    key = llm.get_key("elevenlabs")
    voice_id = llm.get_key("ELEVENLABS_VOICE_ID")
    if not key or not voice_id:
        _log_once("ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID not set")
        return None
    model = os.environ.get("COACH_TTS_MODEL", DEFAULT_MODEL)
    h = _key(text, voice_id, model)
    out = cache_dir() / f"{h}.mp3"
    if not out.is_file():
        task = _inflight.get(h)  # the same line requested twice at once → one request
        if task is None:
            task = asyncio.create_task(_synthesize(text, voice_id, model, key, out))
            _inflight[h] = task
            task.add_done_callback(lambda _t, h=h: _inflight.pop(h, None))
        try:
            ok = await asyncio.shield(task)
        except Exception as e:  # noqa: BLE001 - voice must never break coaching
            _log_once(f"unexpected {type(e).__name__}")
            return None
        if not ok:
            return None
    return {"audioUrl": audio_url(h), "text": text}


async def speak_event(event: str, payload: dict) -> dict | None:
    """The spoken line for an engine event, synthesized; None when the event isn't spoken or TTS fails."""
    line = line_for(event, payload)
    return await speak(line) if line else None


async def prefetch(lines: list[str]) -> int:
    """Warm the cache (e.g. every step title right after the lesson loads). Returns how many are ready."""
    res = await asyncio.gather(*(speak(t) for t in lines if t), return_exceptions=True)
    return sum(1 for r in res if isinstance(r, dict))


def _make_router():
    try:
        from fastapi import APIRouter, HTTPException
        from fastapi.responses import FileResponse
    except ImportError:  # pragma: no cover - fastapi is a server dependency
        return None
    router = APIRouter()

    @router.get(ROUTE + "/{name}")
    async def tts_file(name: str):
        p = path_for(name)
        if p is None:
            raise HTTPException(status_code=404)
        return FileResponse(p, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=86400"})

    return router


router = _make_router()

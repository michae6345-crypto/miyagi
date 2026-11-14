"""describe(): send a screenshot (or a region of it) to Gemini for a semantic question.

Rate-limited: at most one call every `min_interval` seconds; a repeat of the same
(question, region) inside `cache_ttl` returns the cached answer.
Failures raise `DescribeError`; nothing is ever returned as a fake answer.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import time

log = logging.getLogger("server.screen.describe")

DEFAULT_MODEL = os.environ.get("GEMINI_VISION_MODEL", "gemini-3.8-flash")
# tried in order when the primary is overloaded (503), retired (404) or slow
FALLBACK_MODELS = ["gemini-3.1-flash-lite", "gemini-3.5-flash"]
CALL_TIMEOUT = float(os.environ.get("GEMINI_VISION_TIMEOUT", "12"))
SYSTEM = ("You are looking at a learner's screen while they follow a coding tutorial. "
          "Answer the question about the screenshot concisely (<= 3 sentences). "
          "If the screenshot doesn't show enough to answer, say so.")


class DescribeError(RuntimeError):
    """describe() could not produce an answer. `reason`: missing_key | invalid_key | no_image |
    unavailable (every model failed / timed out)."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


def _is_key_error(e: Exception) -> bool:
    s = str(e).lower()
    return any(k in s for k in ("api key not valid", "api_key_invalid", "permission_denied", "unauthenticated"))


class Describer:
    def __init__(self, min_interval: float = 4.0, cache_ttl: float = 15.0, model: str | None = None):
        self.min_interval = min_interval
        self.cache_ttl = cache_ttl
        self.model = model or DEFAULT_MODEL
        self._last_call = 0.0
        self._cache: dict[tuple, tuple[float, str]] = {}
        self._lock = asyncio.Lock()
        self._client = None
        self._byok: str | None = None     # key handed over by the app (config.keys)
        self._key_invalid = False

    # ------------------------------------------------------------------ keys

    def set_key(self, key: str | None) -> None:
        """BYOK: use this Gemini key instead of GEMINI_API_KEY from .env (None/"" = back to env)."""
        self._byok = key or None
        self._client = None
        self._key_invalid = False
        self._cache.clear()

    def _key(self) -> str:
        return self._byok or os.environ.get("GEMINI_API_KEY", "")

    @property
    def key_status(self) -> str:
        """KeyState from events.ts: ok | missing | invalid | env."""
        if not self._key():
            return "missing"
        if self._key_invalid:
            return "invalid"
        return "ok" if self._byok else "env"

    def _get_client(self):
        if self._client is None:
            key = self._key()
            if not key:
                raise DescribeError("missing_key", "no Gemini key (config.keys.gemini or GEMINI_API_KEY)")
            from google import genai
            self._client = genai.Client(api_key=key)
        return self._client

    # ------------------------------------------------------------------ call

    async def describe(self, jpeg: bytes, question: str, cache_key: tuple) -> str:
        now = time.time()
        hit = self._cache.get(cache_key)
        if hit and now - hit[0] < self.cache_ttl:
            return hit[1]
        client = self._get_client()
        async with self._lock:
            wait = self.min_interval - (time.time() - self._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.time()
            from google.genai import types
            text, errors = None, []
            for model in [self.model] + [m for m in FALLBACK_MODELS if m != self.model]:
                try:
                    resp = await asyncio.wait_for(client.aio.models.generate_content(
                        model=model,
                        contents=[types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"), question],
                        config=types.GenerateContentConfig(system_instruction=SYSTEM, temperature=0.2),
                    ), timeout=CALL_TIMEOUT)
                    text = (resp.text or "").strip()
                    if not text:
                        raise RuntimeError("empty response")
                    if model != self.model:
                        log.warning("describe: %s unavailable, answered by %s", self.model, model)
                    break
                except Exception as e:
                    if _is_key_error(e):
                        self._key_invalid = True
                        raise DescribeError("invalid_key", str(e)[:200]) from e
                    errors.append(f"{model}: {str(e)[:120] or e.__class__.__name__}")
                    log.warning("Gemini describe via %s failed: %s", model, errors[-1])
            if text is None:
                raise DescribeError("unavailable", "; ".join(errors))
        self._key_invalid = False
        self._cache[cache_key] = (time.time(), text)
        return text


def to_jpeg(pil_image, max_w: int = 1600, quality: int = 80) -> bytes:
    img = pil_image
    if img.width > max_w:
        img = img.resize((max_w, round(img.height * max_w / img.width)))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=quality)
    return buf.getvalue()

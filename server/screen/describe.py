"""describe(): send a screenshot (or a region of it) to Gemini for a semantic question.

Rate-limited: at most one call every `min_interval` seconds; a repeat of the same
(question, region) inside `cache_ttl` returns the cached answer.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import time

log = logging.getLogger("server.screen.describe")

DEFAULT_MODEL = os.environ.get("GEMINI_VISION_MODEL", "gemini-2.5-flash")
SYSTEM = ("You are looking at a learner's screen while they follow a coding tutorial. "
          "Answer the question about the screenshot concisely (<= 3 sentences). "
          "If the screenshot doesn't show enough to answer, say so.")


class Describer:
    def __init__(self, min_interval: float = 4.0, cache_ttl: float = 15.0, model: str | None = None):
        self.min_interval = min_interval
        self.cache_ttl = cache_ttl
        self.model = model or DEFAULT_MODEL
        self._last_call = 0.0
        self._cache: dict[tuple, tuple[float, str]] = {}
        self._lock = asyncio.Lock()
        self._client = None

    def _get_client(self):
        if self._client is None:
            key = os.environ.get("GEMINI_API_KEY", "")
            if not key:
                return None
            from google import genai
            self._client = genai.Client(api_key=key)
        return self._client

    async def describe(self, jpeg: bytes, question: str, cache_key: tuple) -> str:
        now = time.time()
        hit = self._cache.get(cache_key)
        if hit and now - hit[0] < self.cache_ttl:
            return hit[1]
        client = self._get_client()
        if client is None:
            return "(describe unavailable: GEMINI_API_KEY is not set)"
        async with self._lock:
            wait = self.min_interval - (time.time() - self._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.time()
            from google.genai import types
            try:
                resp = await client.aio.models.generate_content(
                    model=self.model,
                    contents=[types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"), question],
                    config=types.GenerateContentConfig(system_instruction=SYSTEM, temperature=0.2),
                )
                text = (resp.text or "").strip()
            except Exception as e:  # noqa: BLE001
                log.warning("Gemini describe failed: %s", e)
                return f"(describe failed: {e.__class__.__name__})"
        self._cache[cache_key] = (time.time(), text)
        return text


def to_jpeg(pil_image, max_w: int = 1600, quality: int = 80) -> bytes:
    img = pil_image
    if img.width > max_w:
        img = img.resize((max_w, round(img.height * max_w / img.width)))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=quality)
    return buf.getvalue()

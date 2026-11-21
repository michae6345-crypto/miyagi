"""Screen questions answered by Claude vision (model rule: reading the screen/code = Claude only;
Gemini is only for YouTube in server/lesson).

- `describe(question)`  -> claude-sonnet-5-5: semantic/coaching questions ("is this loss converging?").
  Opus only with MIYAGI_ALLOW_OPUS=1 (server.config.guard_model); the miyagi cloud never takes it.
- `where(target)`       -> claude-haiku-5-5: quick "where is X". Set-of-mark: the OCR lines are
  numbered in the prompt and Claude answers with line numbers, which map back to exact rects.

Every call sends a 1280-wide JPEG with the cursor marked, plus the cursor position and what's under
it. Rate-limited (one call per `min_interval` s; same question within `cache_ttl` is cached).
Failures raise `DescribeError`; nothing is ever returned as a fake answer, and there is no
fallback to another provider.

Never sends secrets (ROADMAP 5.2): the text part goes through server.redact.redact_secrets, and the screenshot has
the rows whose OCR text held a secret blacked out (`to_jpeg(mask=...)`, the reader passes them).
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import re
import time

from server import config as server_config
from server.redact import redact_secrets

log = logging.getLogger("server.screen.describe")

COACH_MODEL = os.environ.get("TUT_SCREEN_COACH_MODEL", "claude-sonnet-5-5")  # cost: never Opus by default
QUICK_MODEL = os.environ.get("TUT_SCREEN_QUICK_MODEL", "claude-haiku-5-5")
COACH_TIMEOUT = float(os.environ.get("TUT_SCREEN_COACH_TIMEOUT", "30"))
QUICK_TIMEOUT = float(os.environ.get("TUT_SCREEN_QUICK_TIMEOUT", "12"))

SYSTEM = ("You are looking at a learner's screen while they follow a coding tutorial. The screenshot "
          "has the mouse cursor marked with a red ring. Answer the question about the screen concisely "
          "(at most 3 sentences). If the screenshot doesn't show enough to answer, say so.")
WHERE_SYSTEM = ("You locate things on a learner's screen. You get a screenshot and a numbered list of the "
                "text lines OCR found on it. Reply with ONLY the number(s) of the line(s) that best match "
                "the request, comma-separated, most relevant first, or `none` if nothing matches.")


class DescribeError(RuntimeError):
    """A screen question could not be answered. `reason`: missing_key | invalid_key | no_image |
    refused | unavailable (rate limit / overload / network / timeout)."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


class Describer:
    def __init__(self, min_interval: float = 2.0, cache_ttl: float = 15.0):
        self.min_interval = min_interval
        self.cache_ttl = cache_ttl
        self._last_call = 0.0
        self._cache: dict[tuple, tuple[float, object]] = {}
        self._lock = asyncio.Lock()
        self._client = None
        self._byok: str | None = None     # key handed over by the app (config.keys.anthropic)
        self._key_invalid = False

    # ------------------------------------------------------------------ keys

    def set_key(self, key: str | None) -> None:
        """BYOK: use this Anthropic key instead of ANTHROPIC_API_KEY from .env (None/"" = back to env)."""
        self._byok = key or None
        self._client = None
        self._key_invalid = False
        self._cache.clear()

    def _key(self) -> str:
        """The key handed over by set_key, else server.config's (Settings key > miyagi cloud token > .env)."""
        return self._byok or server_config.get_key("anthropic") or ""

    @property
    def key_status(self) -> str:
        """KeyState from events.ts: ok | missing | invalid | env | cloud."""
        if not self._key():
            return "missing"
        if self._key_invalid:
            return "invalid"
        return "ok" if self._byok else server_config.key_source("anthropic")

    def _get_client(self):
        key = self._key()
        if self._client is None or getattr(self, "_client_for", None) != key:
            if not key:
                raise DescribeError("missing_key", "no Anthropic key (config.keys.anthropic or ANTHROPIC_API_KEY)")
            import anthropic
            # a cloud token goes to the miyagi cloud, any other key straight to Anthropic
            self._client = anthropic.AsyncAnthropic(max_retries=1, **server_config.anthropic_kwargs("screen", key=key))
            self._client_for = key
        return self._client

    # ------------------------------------------------------------------ calls

    async def _ask(self, model: str, system: str, image_jpeg: bytes, text: str, *, effort: str,
                   max_tokens: int, timeout: float) -> str:
        import anthropic
        client = self._get_client()
        text = redact_secrets(text)
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": base64.standard_b64encode(image_jpeg).decode("ascii")}},
            {"type": "text", "text": text},
        ]
        model = server_config.guard_model(model)
        kwargs = {"model": model, "max_tokens": max_tokens, "system": system,
                      "output_config": {"effort": effort}, "messages": [{"role": "user", "content": content}]}
        async with self._lock:
            wait = self.min_interval - (time.time() - self._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.time()
            try:
                c = client.with_options(timeout=timeout)
                # server-side refusal fallback (re-runs a declined request on a fallback model), never onto Opus
                fb = server_config.fallback_kwargs(model)
                if fb:
                    resp = await c.beta.messages.create(**fb, **kwargs)
                else:
                    resp = await c.messages.create(**kwargs)
            except anthropic.APIStatusError as e:
                code = server_config.cloud_error(e)
                if code:  # the miyagi cloud: paused / over today's limit / token refused
                    raise DescribeError(code, server_config.CLOUD_ERRORS[code]) from e
                if isinstance(e, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
                    self._key_invalid = True
                    raise DescribeError("invalid_key", getattr(e, "message", str(e))[:200]) from e
                if isinstance(e, anthropic.RateLimitError):
                    raise DescribeError("unavailable", f"rate limited: {getattr(e, 'message', e)}"[:200]) from e
                raise DescribeError("unavailable", f"{e.status_code}: {getattr(e, 'message', e)}"[:200]) from e
            except (anthropic.APITimeoutError, anthropic.APIConnectionError) as e:
                raise DescribeError("unavailable", f"{e.__class__.__name__}: {e}"[:200]) from e
        self._key_invalid = False
        if resp.stop_reason == "refusal":
            cat = getattr(getattr(resp, "stop_details", None), "category", None)
            raise DescribeError("refused", f"category={cat}")
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
        if not text:
            raise DescribeError("unavailable", f"empty answer (stop_reason={resp.stop_reason})")
        return text

    async def describe(self, jpeg: bytes, question: str, context: str, cache_key: tuple) -> str:
        hit = self._cache.get(("d",) + cache_key)
        if hit and time.time() - hit[0] < self.cache_ttl:
            return hit[1]
        text = await self._ask(COACH_MODEL, SYSTEM, jpeg, f"{context}\n\nQuestion: {question}",
                               effort="low", max_tokens=2000, timeout=COACH_TIMEOUT)
        self._cache[("d",) + cache_key] = (time.time(), text)
        return text

    async def where(self, jpeg: bytes, target: str, numbered_lines: list[str], context: str,
                    cache_key: tuple) -> list[int]:
        """-> indices into `numbered_lines` (0-based), best first; [] when Claude says none."""
        hit = self._cache.get(("w",) + cache_key)
        if hit and time.time() - hit[0] < self.cache_ttl:
            return hit[1]
        listing = "\n".join(f"{i + 1}: {t}" for i, t in enumerate(numbered_lines))
        text = await self._ask(QUICK_MODEL, WHERE_SYSTEM, jpeg,
                               f"{context}\n\nOCR lines:\n{listing}\n\nFind: {target}",
                               effort="low", max_tokens=1000, timeout=QUICK_TIMEOUT)
        ids = parse_ids(text, len(numbered_lines))
        self._cache[("w",) + cache_key] = (time.time(), ids)
        return ids


def parse_ids(text: str, n: int) -> list[int]:
    """'12, 13' -> [11, 12] (0-based, in range, deduped); 'none' -> []."""
    if re.fullmatch(r"\s*none\.?\s*", text, re.IGNORECASE):
        return []
    out: list[int] = []
    for m in re.findall(r"\d+", text):
        i = int(m) - 1
        if 0 <= i < n and i not in out:
            out.append(i)
    return out


def to_jpeg(pil_image, max_w: int = 1280, quality: int = 80, cursor: tuple[float, float] | None = None,
            scale: float = 1.0, origin: tuple[float, float] = (0.0, 0.0),
            mask: list[tuple[float, float, float, float]] | None = None) -> bytes:
    """Downscale to `max_w` and (optionally) draw a red ring at the cursor (points -> pixels). `mask`: rects in
    points (x, y, w, h) painted solid black first, e.g. the rows whose OCR text held an API key."""
    from PIL import ImageDraw
    img = pil_image.convert("RGB")
    if mask:
        d = ImageDraw.Draw(img)
        for x, y, w, h in mask:
            x0, y0 = (x - origin[0]) * scale - 2, (y - origin[1]) * scale - 2
            d.rectangle([x0, y0, x0 + w * scale + 4, y0 + h * scale + 4], fill=(0, 0, 0))
    if cursor is not None:
        d = ImageDraw.Draw(img)
        cx, cy = (cursor[0] - origin[0]) * scale, (cursor[1] - origin[1]) * scale
        r = max(10, int(img.width / 120))
        if 0 <= cx <= img.width and 0 <= cy <= img.height:
            d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 0, 0), width=max(3, r // 4))
    if img.width > max_w:
        img = img.resize((max_w, round(img.height * max_w / img.width)))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return buf.getvalue()

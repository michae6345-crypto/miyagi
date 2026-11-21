"""Never send secrets (ROADMAP 5.2): key- and token-shaped text out of anything that leaves this Mac.

    from server.redact import redact_secrets, redact_file_text, is_secret_file, scrub_secrets
    redact_secrets("key sk-ant-api03-...")         # "key [secret]"
    redact_file_text(".env", "OPENAI_API_KEY=abc") # "OPENAI_API_KEY=[secret]": names kept, every value hidden
    is_secret_file("~/proj/.env.local")            # True
    scrub_secrets({"a": ["ghp_..."]})              # a copy with every string redacted

Applied at the boundaries where text leaves the engine: screen OCR and Accessibility text (server.screen.privacy),
every coach request (server.coach.llm), the screen describe/where calls (server.screen.describe), and editor text the
companion hands over ("Explain this", via server.workspace.core.text_for_model). Grading reads the learner's real
text; only what is sent out is redacted.

What counts as a secret:
  - known formats: Anthropic / OpenAI `sk-...`, Google `AIza...`, GitHub `ghp_` / `gho_` / `ghu_` / `ghs_` / `ghr_` /
    `github_pat_`, Slack `xox?-` / `xapp-`, Stripe `sk_live_` / `rk_test_` ..., ElevenLabs `sk_<hex>`, AWS `AKIA...`,
    JWTs (`eyJ...`), PEM private key blocks, the password in `scheme://user:password@host`;
  - a long base64-ish value after a name with KEY / TOKEN / SECRET / PASSWORD / CREDENTIAL / AUTH in it
    (`API_KEY=...`, `token: "..."`, `secret = '...'`);
  - the exact keys this engine holds (Settings keys, the miyagi cloud token, provider keys in the environment).
The marker is SECRET_MARK, so a caller can tell a line held one (the screen describe call blacks out those rows).
"""

from __future__ import annotations

import contextlib
import os
import re
import time
from collections.abc import Iterable
from pathlib import PurePath
from typing import Any

SECRET_MARK = "[secret]"

# Known token formats. Each pattern matches only the secret itself (the text around it stays).
_TOKEN_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)", re.DOTALL),
    re.compile(r"(?<![\w-])sk-(?:ant-|proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?<![\w-])AIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"(?<![\w-])gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"(?<![\w-])github_pat_[A-Za-z0-9_]{30,}"),
    re.compile(r"(?<![\w-])xox[abposr]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"(?<![\w-])xapp-[A-Za-z0-9\-]{10,}"),
    re.compile(r"(?<![\w-])(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{16,}"),
    re.compile(r"(?<![\w-])sk_[a-f0-9]{32,}"),
    re.compile(r"(?<![\w-])xi-[A-Za-z0-9]{16,}"),
    re.compile(r"(?<![A-Z0-9])(?:AKIA|ASIA)[0-9A-Z]{16}(?![A-Z0-9])"),
    re.compile(r"(?<![\w-])eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),
)
_BEARER = re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9_\-.=+/]{16,}")
# scheme://user:password@host -> the password only
_URL_PASSWORD = re.compile(r"(\b[a-z][a-z0-9+.\-]*://[^\s:/@]+:)([^\s@/]{3,})(@)", re.IGNORECASE)
# NAME = "value" / NAME: value / NAME=value, where NAME says it holds a secret and the value looks like one
_SECRET_NAME = r"(?:[A-Za-z_][\w.\-]*?)?(?:key|token|secret|passw(?:or)?d|pwd|credential|auth|dsn)[\w.\-]*"
_ASSIGN_QUOTED = re.compile(
    r"(?i)(?P<name>\b" + _SECRET_NAME + r"""["']?[ \t]*[:=][ \t]*)(?P<q>["'])(?P<val>[A-Za-z0-9+/_\-.=~:]{12,})(?P=q)""")
_ASSIGN_BARE = re.compile(
    r"(?im)(?P<name>^[ \t]*(?:export[ \t]+)?" + _SECRET_NAME + r"[ \t]*[:=][ \t]*)"
    r"(?P<val>[A-Za-z0-9+/_\-.=~]{16,})[ \t]*$")
# one KEY=value line of an env file (names kept, the value hidden)
_ENV_LINE = re.compile(r"(?m)^([ \t]*(?:export[ \t]+)?[A-Za-z_][A-Za-z0-9_.\-]*[ \t]*=[ \t]*)(\S.*?)[ \t]*$")
_PLACEHOLDER = re.compile(r"""^["']?(?:|<[^>]*>|\$\{?\w+\}?|your[_\-\w]*|x{4,}|\.{3}|changeme|none|null|true|false|\d{1,6})["']?$""",
                          re.IGNORECASE)

# .env files and friends: their text is never sent as it is
_SECRET_NAMES = frozenset({".env", ".envrc", ".netrc", ".npmrc", ".pypirc", ".pgpass", "credentials",
                           "credentials.json", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"})
_SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".keystore", ".jks")
_ENV_EXAMPLES = frozenset({"example", "sample", "template", "dist", "defaults"})
_ENV_STYLE = frozenset({".env", ".envrc", ".pypirc", ".npmrc", ".netrc", ".pgpass"})


_KNOWN_TTL_S = 2.0
_known_cache: tuple[float, tuple[str, ...]] = (0.0, ())


def _known_values() -> tuple[str, ...]:
    """The exact secrets this engine holds right now: Settings keys, the cloud token, provider keys in os.environ
    (re-read every _KNOWN_TTL_S; OCR calls this per block). Never logged; only used to find and hide them."""
    global _known_cache
    now = time.monotonic()
    if now - _known_cache[0] < _KNOWN_TTL_S:
        return _known_cache[1]
    vals: set[str] = set()
    with contextlib.suppress(Exception):  # redaction never fails a send
        from server import config as cfg

        vals.update(v for v in getattr(cfg, "_app_keys", {}).values() if isinstance(v, str))
        for name in getattr(cfg, "KEY_ENV", {}):
            v = cfg._env_key(name)
            if isinstance(v, str):
                vals.add(v)
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "GEMINI_API_KEY", "GOOGLE_API_KEY", "ELEVENLABS_API_KEY",
                "MIYAGI_CLOUD_TOKEN", "TIGER_DATABASE_URL"):
        if v := os.environ.get(var, "").strip():
            vals.add(v)
    out = tuple(sorted((v.strip() for v in vals if len(v.strip()) >= 12), key=len, reverse=True))
    _known_cache = (now, out)
    return out


def _quick_skip(text: str) -> bool:
    """Most screen lines hold none of the triggers: skip the regexes for them (OCR runs every tick)."""
    if len(text) < 12:
        return True
    low = text.lower()
    return not any(t in low for t in ("sk", "aiza", "gh", "xox", "xapp", "xi-", "akia", "asia", "eyj", "://",
                                      "key", "token", "secret", "pass", "pwd", "credential", "auth", "dsn",
                                      "-----begin", "github_pat", "bearer")) and not _has_known(text)


def _has_known(text: str) -> bool:
    return any(v in text for v in _known_values())


def redact_secrets(text: str, *, known: Iterable[str] | None = None) -> str:
    """`text` with every key- or token-shaped value replaced by SECRET_MARK. Anything not a string comes back as is."""
    if not isinstance(text, str) or not text:
        return text
    values = list(known) if known is not None else None
    if values is None and _quick_skip(text):
        return text
    for v in values if values is not None else _known_values():
        if v and v in text:
            text = text.replace(v, SECRET_MARK)
    for rx in _TOKEN_RES:
        text = rx.sub(SECRET_MARK, text)
    text = _BEARER.sub(lambda m: m.group(1) + SECRET_MARK, text)
    text = _URL_PASSWORD.sub(lambda m: m.group(1) + SECRET_MARK + m.group(3), text)
    text = _ASSIGN_QUOTED.sub(_assign_quoted, text)
    text = _ASSIGN_BARE.sub(_assign_bare, text)
    return text


def _looks_secret(val: str) -> bool:
    """A value after a secret-sounding name: long, one word, and either long enough or mixing digits and letters
    (`tokenizer_name_or_path` is not a token; `a1b2c3d4e5f6a7b8` is)."""
    if SECRET_MARK in val or _PLACEHOLDER.match(val):
        return False
    has_digit = any(c.isdigit() for c in val)
    has_alpha = any(c.isalpha() for c in val)
    return (has_digit and has_alpha) or len(val) >= 32


def _assign_quoted(m: re.Match[str]) -> str:
    if not _looks_secret(m.group("val")):
        return m.group(0)
    return f"{m.group('name')}{m.group('q')}{SECRET_MARK}{m.group('q')}"


def _assign_bare(m: re.Match[str]) -> str:
    if not _looks_secret(m.group("val")):
        return m.group(0)
    return f"{m.group('name')}{SECRET_MARK}"


def is_secret_file(path: str | os.PathLike[str] | None) -> bool:
    """.env, .env.local, .envrc, .netrc, .npmrc, .pypirc, credentials files, SSH / PEM keys. `.env.example` and
    friends hold placeholders, not secrets: False (their text is still run through redact_secrets)."""
    if not path:
        return False
    name = PurePath(os.fspath(path)).name.lower()
    if name in _SECRET_NAMES or name.endswith(_SECRET_SUFFIXES):
        return True
    if name.startswith(".env."):
        return name.split(".", 2)[2] not in _ENV_EXAMPLES
    return name.startswith("service-account") and name.endswith(".json")


def redact_file_text(path: str | os.PathLike[str] | None, text: str) -> str:
    """Text read from `path`, safe to send. An env-style secret file (.env, .envrc, .npmrc, ...) keeps its names and
    comments with every value hidden, so the coach can still help with its shape; any other secret file (a key, a
    credentials JSON) is withheld whole; everything else goes through redact_secrets."""
    if not isinstance(text, str) or not text:
        return text
    if is_secret_file(path):
        name = PurePath(os.fspath(path)).name.lower()  # type: ignore[arg-type]
        if name in _ENV_STYLE or name.startswith(".env."):
            return redact_secrets(_ENV_LINE.sub(_env_value, text))
        return f"{SECRET_MARK} (the contents of {PurePath(os.fspath(path)).name} are not shared)"  # type: ignore[arg-type]
    return redact_secrets(text)


def _env_value(m: re.Match[str]) -> str:
    head = m.group(1)
    if head.lstrip().startswith("#"):
        return m.group(0)
    return head + (m.group(2) if _PLACEHOLDER.match(m.group(2).strip()) else SECRET_MARK)


def scrub_secrets(value: Any) -> Any:
    """A copy of a JSON-like value with every string run through redact_secrets (dict keys are kept)."""
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, dict):
        return {k: scrub_secrets(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub_secrets(v) for v in value]
    if isinstance(value, tuple):
        return tuple(scrub_secrets(v) for v in value)
    return value

"""Never send secrets (ROADMAP 5.2): key- and token-shaped text out of anything that leaves this Mac.

    from server.redact import redact_secrets, redact_file_text, is_secret_file, scrub_secrets
    redact_secrets("key sk-ant-api03-...")         # "key [secret]"
    redact_file_text(".env", "OPENAI_API_KEY=abc") # "OPENAI_API_KEY=[secret]": names kept, every value hidden
    redact_file_text(".netrc", "machine ...")       # withheld whole: no name=value shape to keep
    is_secret_file("~/proj/.env.local")            # True
    scrub_secrets({"a": ["ghp_..."]})              # a copy with every string redacted

Applied at the boundaries where text leaves the engine: screen OCR and Accessibility text (server.screen.privacy),
every coach request (server.coach.llm), the screen describe/where calls (server.screen.describe), editor text the
companion hands over ("Explain this", via server.workspace.core.text_for_model), a secret step file sent to the coach
(session._coach_excerpt, coach.actions.do_it_for_me) and web search words (coach.web.search_safe). Every screenshot
sent out blacks out rows that held a secret. Grading reads the learner's real text; only what is sent out is redacted,
and coach.hints.apply_fix refuses a patch that would write SECRET_MARK into the file.

What counts as a secret:
  - known formats: Anthropic / OpenAI `sk-...`, Google `AIza...`, GitHub `ghp_` / `gho_` / `ghu_` / `ghs_` / `ghr_` /
    `github_pat_`, Slack `xox?-` / `xapp-`, Stripe `sk_live_` / `rk_test_` ..., ElevenLabs `sk_<hex>`, AWS `AKIA...`,
    HuggingFace `hf_...`, npm `npm_...`, GitLab `glpat-...`, PyPI `pypi-AgEIcHlwaS5vcmc...`, JWTs (`eyJ...`),
    PEM private key blocks, the password in `scheme://user:password@host`;
  - a long base64-ish value after a name with KEY / TOKEN / SECRET / PASSWORD / CREDENTIAL / AUTH in it, anywhere in
    a line (`API_KEY=...`, `token: "..."`, `secret = '...'`, `API_KEY=... python app.py`, `?apiKey=...&x=1`,
    `"x-api-key: ..."`), and `Basic <base64 of user:password>`;
  - the exact keys this engine holds (Settings keys, the miyagi cloud token, provider keys in the environment).
The marker is SECRET_MARK, so a caller can tell a line held one (the screen describe call blacks out those rows).

Cost: coach requests redact the learner's whole file, so every pattern stays linear in the text. A name before `=` or
`:` is at most 64 characters and matched possessively (Python 3.11+), so a long run of `a-a-a-...` or `token_token_...`
(minified code, a data line) never backtracks; 100 KB of such text redacts in milliseconds (test_redact.py).
"""

from __future__ import annotations

import base64
import binascii
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
    re.compile(r"(?<![\w-])hf_[A-Za-z0-9]{30,}"),
    re.compile(r"(?<![\w-])npm_[A-Za-z0-9]{36,}"),
    re.compile(r"(?<![\w-])glpat-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?<![\w-])pypi-AgEIcHlwaS5vcmc[A-Za-z0-9_\-]{20,}"),
)
_BEARER = re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9_\-.=+/]{16,}")
# `Authorization: Basic dXNlcjpwYXNz...`: base64 of `user:password` (decoded and checked in _basic, so "basic
# understanding" stays)
_BASIC = re.compile(r"(?i)(\bbasic[ \t]+)(?P<val>[A-Za-z0-9+/]{12,}+={0,2})(?![\w+/=])")
# scheme://user:password@host -> the password only
_URL_PASSWORD = re.compile(r"(\b[a-z][a-z0-9+.\-]{0,30}://[^\s:/@]+:)([^\s@/]{3,})(@)", re.IGNORECASE)
# NAME = "value" / NAME: value / NAME=value, where NAME says it holds a secret and the value looks like one. NAME is
# one identifier of at most 64 characters, taken possessively (`{0,63}+` never gives characters back), and the
# secret-sounding word is looked for in it afterwards (_SECRET_WORD): no nested, unbounded backtracking.
_NAME = r"(?P<n>[A-Za-z_][\w.\-]{0,63}+)"
_SECRET_WORD = re.compile(r"(?i)key|token|secret|passw(?:or)?d|pwd|credential|auth|dsn")
_ASSIGN_QUOTED = re.compile(
    r"(?i)(?P<name>\b" + _NAME + r"""["']?[ \t]*[:=][ \t]*)(?P<q>["'])(?P<val>[A-Za-z0-9+/_\-.=~:]{12,})(?P=q)""")
_ASSIGN_BARE = re.compile(
    r"(?im)(?P<name>^[ \t]*(?:export[ \t]+)?" + _NAME + r"[ \t]*[:=][ \t]*)"
    r"(?P<val>[A-Za-z0-9+/_\-.=~]{16,})[ \t]*$")
# NAME=value anywhere in a line: a command (`API_KEY=... python app.py`, `export TOKEN=...  # mine`, `HF_TOKEN=...;`),
# a URL query (`?apiKey=...&x=1`, `&access_token=...`), a header (`"x-api-key: ..."`), a CLI flag (`--token=...`). NAME
# starts the line or follows ? & ( , - whitespace or a quote; the value ends at whitespace, & ; # ) , a quote or the
# line's end. Both are bounded / possessive, so this stays linear (_SECRET_WORD and _looks_secret decide afterwards).
_ASSIGN_INLINE = re.compile(
    r"""(?m)(?P<name>(?:^|(?<=[?&(,\-\s"']))""" + _NAME + r"[ \t]{0,4}+[:=][ \t]{0,4}+)"
    r"""(?P<val>[A-Za-z0-9+/_\-.=~%]{12,}+)(?=[\s&;#),"']|$)""")
# one line of a secret file whose shape is kept (names and comments stay, the value is hidden). `(\S(?:.*\S)?)` takes
# the value up to its last non-blank character without a lazy scan (a lazy `.*?` before `[ \t]*$` is quadratic).
_VALUE = r"(\S(?:.*\S)?)[ \t]*$"
_ENV_LINE = re.compile(r"(?m)^([ \t]*(?:export[ \t]+)?[A-Za-z_][A-Za-z0-9_.\-]*[ \t]*=[ \t]*)" + _VALUE)
# .pypirc (configparser: `password = ...` or `password: ...`)
_INI_LINE = re.compile(r"(?m)^([ \t]*[A-Za-z_][\w.\-]*[ \t]*[:=][ \t]*)" + _VALUE)
# .npmrc: everything after the first `=` (`//registry.npmjs.org/:_authToken=...` has no plain name)
_NPMRC_LINE = re.compile(r"(?m)^([ \t]*[^\s#;=][^=\n]*=[ \t]*)" + _VALUE)
_PLACEHOLDER = re.compile(r"""^["']?(?:|<[^>]*>|\$\{?\w+\}?|your[_\-\w]*|x{4,}|\.{3}|changeme|none|null|true|false|\d{1,6})["']?$""",
                          re.IGNORECASE)

# .env files and friends: their text is never sent as it is
_SECRET_NAMES = frozenset({".env", ".envrc", ".netrc", ".npmrc", ".pypirc", ".pgpass", "credentials",
                           "credentials.json", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"})
_SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".keystore", ".jks")
_ENV_EXAMPLES = frozenset({"example", "sample", "template", "dist", "defaults"})
# secret files whose names and comments are kept with every value hidden (.netrc and .pgpass have no name=value
# shape, `machine h login u password p` / `host:port:db:user:password`, so they are withheld whole)
_ENV_STYLE = frozenset({".env", ".envrc"})
_LINE_STYLE: dict[str, re.Pattern[str]] = {".npmrc": _NPMRC_LINE, ".pypirc": _INI_LINE}


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
                                      "-----begin", "github_pat", "bearer", "hf_", "npm_", "glpat-",
                                      "pypi-")) and not _has_known(text)


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
    text = _ASSIGN_INLINE.sub(_assign_bare, text)
    text = _BASIC.sub(_basic, text)
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
    if not _SECRET_WORD.search(m.group("n")) or not _looks_secret(m.group("val")):
        return m.group(0)
    return f"{m.group('name')}{m.group('q')}{SECRET_MARK}{m.group('q')}"


def _assign_bare(m: re.Match[str]) -> str:
    if not _SECRET_WORD.search(m.group("n")) or not _looks_secret(m.group("val")):
        return m.group(0)
    return f"{m.group('name')}{SECRET_MARK}"


def _basic(m: re.Match[str]) -> str:
    """`Basic <base64>` whose base64 decodes to `user:password` (or looks like a token): hidden."""
    val = m.group("val")
    try:
        raw = base64.b64decode(val + "=" * (-len(val) % 4), validate=True)
        creds = b":" in raw and all(32 <= c < 127 for c in raw)
    except (ValueError, binascii.Error):
        creds = False
    if not creds and not (len(val) >= 20 and any(c.isdigit() for c in val) and any(c.isalpha() for c in val)):
        return m.group(0)
    return m.group(1) + SECRET_MARK


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
    """Text read from `path`, safe to send. A secret file with name=value lines (.env, .env.local, .envrc, .npmrc,
    .pypirc) keeps its names and comments with every value hidden, so the coach can still help with its shape; any other
    secret file (a key, a credentials JSON, .netrc, .pgpass) is withheld whole; everything else goes through
    redact_secrets."""
    if not isinstance(text, str) or not text:
        return text
    if is_secret_file(path):
        name = PurePath(os.fspath(path)).name.lower()  # type: ignore[arg-type]
        if name in _ENV_STYLE or name.startswith(".env."):
            return redact_secrets(_ENV_LINE.sub(_env_value, text))
        if name in _LINE_STYLE:
            return redact_secrets(_LINE_STYLE[name].sub(_env_value, text))
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

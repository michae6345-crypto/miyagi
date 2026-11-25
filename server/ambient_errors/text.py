"""What an error's text may look like where it goes: on this Mac (error.seen) and to the model (Explain).

  for_app(text)    the home folder shortened to ~ (any /Users/<name> or /home/<name>), secret-looking values masked
                   as •••• (server.redact): error.seen's title, lines and file
  for_model(text)  the same, and every path cut to its file name, or to the path inside the package for a file in
                   site-packages / node_modules ("pandas/core/frame.py"); a relative path (inside the project) stays
"""

from __future__ import annotations

import re

try:
    from server.redact import SECRET_MARK, redact_secrets
except Exception:  # pragma: no cover - the engine always has it
    SECRET_MARK = "[secret]"

    def redact_secrets(text: str, **_k) -> str:  # type: ignore[misc]
        return text

MASK = "••••"  # AMBIENT-HELP.md: secrets masked as ••••
_HOME = re.compile(r"(?:/Users|/home)/[^/\s\"'():,]+")
# an absolute or ~ path, never the "//host/x" of a URL ("https://registry.npmjs.org/x") or a/b inside a word
_PATH = re.compile(r"(?<![\w:/.\-~])(?:file://)?(?:~|/)[^\s\"'(),:;<>]*[^\s\"'(),:;<>.]")
_PKG_ROOTS = ("site-packages/", "dist-packages/", "node_modules/")


def mask(text: str) -> str:
    return redact_secrets(text or "").replace(SECRET_MARK, MASK)


def short_home(text: str) -> str:
    return _HOME.sub("~", text or "")


def for_app(text: str | None) -> str:
    return short_home(mask(text or ""))


def cut_path(path: str) -> str:
    """One path as the model sees it: the file name, or the part inside a package folder."""
    p = path[7:] if path.startswith("file://") else path
    for root in _PKG_ROOTS:
        if root in p:
            return p.rsplit(root, 1)[1]
    if p.startswith(("/", "~")):
        return p.rstrip("/").rsplit("/", 1)[-1] or p
    return p


def for_model(text: str | None) -> str:
    return _PATH.sub(lambda m: cut_path(m.group(0)), for_app(text))

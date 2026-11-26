"""PII and secret scrubbing + private apps. Applied to every OCR block and AX text before it leaves the reader
(observations, coach payloads, Claude vision, Tiger). Secrets (API keys, tokens, .env values on screen) become
server.redact.SECRET_MARK; see server/redact.py."""
from __future__ import annotations

import os
import re

from server.redact import SECRET_MARK, redact_secrets

PRIVATE_APP_NAMES = {"1Password", "1Password 7", "Bitwarden", "Keychain Access", "Passwords", "Messages",
                     "Dashlane", "LastPass"} | {s.strip() for s in os.environ.get("TUT_PRIVATE_APPS", "").split(",")
                                                if s.strip()}

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_PHONE = re.compile(r"(?<![\w.])(?:\+?1[\s.-])?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?![\w.])")
_CARD = re.compile(r"(?<![\w.])(?:\d[ -]?){12,18}\d(?![\w.])")


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def _card(m: re.Match) -> str:
    digits = re.sub(r"\D", "", m.group(0))
    return "[card]" if 13 <= len(digits) <= 19 and _luhn(digits) else m.group(0)


def redact(text: str) -> str:
    if not text:
        return text
    text = redact_secrets(text)  # keys first: a token can hold digit runs the card / phone rules would split
    if not any(c.isdigit() or c == "@" for c in text):
        return text
    text = _EMAIL.sub("[email]", text)
    text = _SSN.sub("[ssn]", text)
    text = _CARD.sub(_card, text)
    return _PHONE.sub("[phone]", text)


def holds_secret(text: str | None) -> bool:
    """A redacted line that had a secret in it (the screen describe call blacks out its row in the screenshot)."""
    return bool(text) and SECRET_MARK in text  # type: ignore[operator]


def is_private_app(app: str | None) -> bool:
    return bool(app) and app in PRIVATE_APP_NAMES

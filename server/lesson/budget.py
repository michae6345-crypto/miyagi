"""Daily spend guard for Gemini video watching.

Every Gemini *video* call (a whole video, or one clip of a long one) takes one unit from a daily
budget (LESSON_GEMINI_DAILY_CAP, default 25), persisted in ~/miyagi/state/gemini_usage.json
(LESSON_GEMINI_USAGE_FILE overrides) so restarts don't reset it. When it's used up, the builder
skips Gemini and builds from the transcript with Claude, and says so in the progress stages.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import threading
from pathlib import Path

log = logging.getLogger("server.lesson")
_lock = threading.Lock()


def _path() -> Path:
    return Path(os.environ.get("LESSON_GEMINI_USAGE_FILE", "~/miyagi/state/gemini_usage.json")).expanduser()


def cap() -> int:
    try:
        return max(0, int(os.environ.get("LESSON_GEMINI_DAILY_CAP", "25")))
    except ValueError:
        return 25


def _today() -> str:
    return _dt.date.today().isoformat()


def _read() -> dict:
    try:
        d = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        d = {}
    if d.get("date") != _today():
        d = {"date": _today(), "video_calls": 0}
    return d


def used() -> int:
    return int(_read().get("video_calls", 0))


def remaining() -> int:
    return max(0, cap() - used())


def try_take(what: str = "") -> bool:
    """Take one Gemini video call from today's budget; False (and nothing taken) when it's used up."""
    with _lock:
        d = _read()
        if d["video_calls"] >= cap():
            return False
        d["video_calls"] += 1
        d.setdefault("log", []).append(what[:80])
        d["log"] = d["log"][-50:]
        p = _path()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps(d, indent=1), encoding="utf-8")
            tmp.replace(p)
        except OSError as e:  # can't persist: still count in memory for this call, but say so
            log.warning("could not write %s: %s", p, e)
        return True


def exhausted_message() -> str:
    return f"today's Gemini budget is used up ({cap()} video calls, LESSON_GEMINI_DAILY_CAP)"

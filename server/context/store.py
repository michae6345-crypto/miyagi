"""Context memory on this Mac: short notes of what the engine saw and did in a lesson, so later answers know it.

    from server.context import store
    st = store.ContextStore("lesson-abc", session="e1f2")
    st.add("check", "s2", "s2 checks: 1 passed, 1 not yet (Run nn.py)", {"failing": ["Run nn.py"]}, step="s2")
    st.entries()          # newest last: [Entry(kind, source, t, summary, facts, step, session, hash)]
    store.wipe_lesson("lesson-abc"); store.wipe_all(); store.prune()

One JSON-lines file per lesson: <state>/context/<lesson>.jsonl (state = $MIYAGI_CONTEXT_DIR, else
server.sessions.store.state_dir()/context, i.e. ~/miyagi/state/context). The folder is 0700 and each file 0600. Nothing
here is uploaded: a few of these lines go into a coach prompt (server.context.recall), wrapped as untrusted data.

Rules:
  - redacted before saving: secrets (server.redact) plus emails, phone and card numbers (server.screen.privacy.redact);
  - a private app (screen/privacy.py PRIVATE_APP_NAMES: password managers, Messages) is never summarized;
  - deduped: an entry equal to the newest one in its slot (kind + source + step) is not written again;
  - capped: MAX_ENTRIES lines and MAX_BYTES per lesson (the oldest go first), MAX_LESSONS lesson files;
  - expires: a lesson file untouched for TTL_DAYS is removed (prune), a completed lesson's file goes with it, and
    "Delete my data" removes every file (wipe_all: the data.delete command, or the config.keys hook, in
    orchestrator/main.py); a lesson that starts fresh rather than resuming forgets its earlier run (wipe_lesson);
  - a wipe bumps generation(), so a scanner holding outlines in memory never writes them back.

Off with MIYAGI_CONTEXT_MEMORY=0. Under pytest it is off unless a test sets MIYAGI_CONTEXT_MEMORY=1, so the coach's
replay fixtures (keyed by the prompt text) never see notes another test left.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from server.context.extract import LIST_MAX, SUMMARY_CHARS, short

log = logging.getLogger("server.context")

MAX_ENTRIES = 400  # per lesson
MAX_BYTES = 256_000  # per lesson file
MAX_LESSONS = 40  # lesson files kept (the least recently touched go first)
TTL_DAYS = 14.0
KINDS = frozenset({"file", "screen", "check", "coach", "setup", "action", "step", "transcript", "note"})
FILES_SUFFIX = ".files.json"  # server.context.scan's per-lesson scan cache, next to the notes

# What Settings > Privacy can list (app follow-up: the privacy panel's facts list shows it). Calm, <= 12 words a line.
PRIVACY_FACT = {
    "id": "lesson_notes",
    "title": "Lesson notes",
    "text": "Short notes of each lesson stay on this Mac.",
    "detail": "They help answers remember what you did. Delete my data removes them.",
}

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
# per lesson file: {"latest": {slot: hash of its newest entry}, "count": lines}; shared by every ContextStore of a file
_index: dict[str, dict] = {}
# Wipe generations: wipe_all bumps the global one, wipe_lesson and prune the lesson's. A FileScanner (and a scan already
# running) compares them, so an outline cached in memory before a wipe is never written back after it.
_gen_all = 0
_gen_lesson: dict[str, int] = {}


def generation(lesson_id: str | None) -> tuple[int, int]:
    """(global, this lesson's) wipe generation: it changes whenever this lesson's notes or scan cache were removed."""
    return _gen_all, _gen_lesson.get(lesson_key(lesson_id), 0)


def _bump(key: str | None = None) -> None:
    global _gen_all
    with _locks_guard:
        if key is None:
            _gen_all += 1
        else:
            _gen_lesson[key] = _gen_lesson.get(key, 0) + 1


def enabled() -> bool:
    v = os.environ.get("MIYAGI_CONTEXT_MEMORY", "").strip().lower()
    if v in ("0", "false", "off", "no"):
        return False
    if "PYTEST_CURRENT_TEST" in os.environ and v not in ("1", "true", "on", "yes"):
        return False
    return True


def root() -> Path:
    env = os.environ.get("MIYAGI_CONTEXT_DIR")
    if env:
        return Path(env).expanduser()
    from server.sessions.store import state_dir

    return state_dir() / "context"


def lesson_key(lesson_id: str | None) -> str:
    """A safe file stem for a lesson id (ids are the builder's own, but never trusted as a path)."""
    raw = str(lesson_id or "lesson")
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", raw)[:80].strip("._") or "lesson"
    if stem != raw:
        stem += "-" + hashlib.sha256(raw.encode("utf-8", "surrogatepass")).hexdigest()[:8]
    return stem


def _lock(path: Path) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(str(path), threading.Lock())


def _ensure_dir() -> Path:
    d = root()
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    return d


def redact(text: Any) -> str:
    from server.screen.privacy import redact as privacy_redact

    return privacy_redact(str(text or ""))


def _clean_facts(facts: dict | None) -> dict:
    out: dict[str, Any] = {}
    for k, v in (facts or {}).items():
        key = re.sub(r"[^a-z0-9_]", "", str(k).lower())[:24]
        if not key:
            continue
        if isinstance(v, (list, tuple)):
            vals = [short(redact(x), 120) for x in v if str(x or "").strip()][:LIST_MAX]
            if vals:
                out[key] = vals
        elif v not in (None, ""):
            out[key] = short(redact(v), 160)
        if len(out) >= 10:
            break
    return out


@dataclass
class Entry:
    kind: str
    source: str
    summary: str
    t: float = field(default_factory=time.time)
    facts: dict = field(default_factory=dict)
    step: str = ""
    session: str = ""
    hash: str = ""

    @property
    def slot(self) -> tuple[str, str, str]:
        return (self.kind, self.source, self.step)

    @classmethod
    def from_json(cls, d: Any) -> Entry | None:
        if not isinstance(d, dict) or not isinstance(d.get("summary"), str) or d.get("kind") not in KINDS:
            return None
        try:
            return cls(kind=d["kind"], source=str(d.get("source") or ""), summary=d["summary"], t=float(d.get("t") or 0),
                       facts=d.get("facts") if isinstance(d.get("facts"), dict) else {}, step=str(d.get("step") or ""),
                       session=str(d.get("session") or ""), hash=str(d.get("hash") or ""))
        except (TypeError, ValueError):
            return None


def _hash(kind: str, source: str, step: str, summary: str, facts: dict) -> str:
    blob = json.dumps([kind, source, step, summary, facts], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8", "surrogatepass")).hexdigest()[:16]


class ContextStore:
    """One lesson's notes. Safe from the event loop and from a scan thread (a lock per file)."""

    def __init__(self, lesson_id: str | None, session: str = "") -> None:
        self.lesson_id = str(lesson_id or "")
        self.session = session
        self.path = root() / f"{lesson_key(lesson_id)}.jsonl"

    # ------------------------------------------------------------ write
    def add(self, kind: str, source: str, summary: str, facts: dict | None = None, *, step: str | None = None,
            app: str | None = None, t: float | None = None) -> Entry | None:
        """Save one note → the Entry, or None (memory off, a private app, nothing to say, or the same as last time)."""
        if not enabled() or kind not in KINDS or not self.lesson_id:
            return None
        from server.screen.privacy import is_private_app

        if is_private_app(app) or is_private_app((facts or {}).get("app")):
            return None
        text = short(redact(summary), SUMMARY_CHARS)
        if not text:
            return None
        clean = _clean_facts(facts)
        src = short(redact(source), 120)
        stp = short(step or "", 40)
        h = _hash(kind, src, stp, text, clean)
        e = Entry(kind=kind, source=src, summary=text, t=time.time() if t is None else t, facts=clean, step=stp,
                  session=self.session, hash=h)
        with _lock(self.path):
            idx = self._index()
            if idx["latest"].get(e.slot) == h:
                return None
            try:
                _ensure_dir()
                line = json.dumps(asdict(e), ensure_ascii=False) + "\n"
                fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                with os.fdopen(fd, "a", encoding="utf-8") as f:
                    f.write(line)
            except OSError as err:
                log.warning("context note not saved: %s", type(err).__name__)
                return None
            idx["latest"][e.slot] = h
            idx["count"] += 1
            self._enforce_caps(idx)
        return e

    def _index(self) -> dict:
        idx = _index.get(str(self.path))
        if idx is None or not self.path.exists():
            es = self._read()
            idx = _index[str(self.path)] = {"latest": {e.slot: e.hash for e in es}, "count": len(es)}
        return idx

    def _enforce_caps(self, idx: dict) -> None:
        try:
            size = self.path.stat().st_size
        except OSError:
            return
        if size <= MAX_BYTES and idx["count"] <= MAX_ENTRIES:
            return
        entries = self._read()
        keep = entries[-int(MAX_ENTRIES * 0.75):]
        while keep and sum(len(json.dumps(asdict(x), ensure_ascii=False)) + 1 for x in keep) > MAX_BYTES * 0.75:
            keep = keep[len(keep) // 4 or 1:]
        self._rewrite(keep)

    def _rewrite(self, entries: list[Entry]) -> None:
        d = _ensure_dir()
        fd, tmp = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=d)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                for x in entries:
                    f.write(json.dumps(asdict(x), ensure_ascii=False) + "\n")
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            return
        _index[str(self.path)] = {"latest": {e.slot: e.hash for e in entries}, "count": len(entries)}

    # ------------------------------------------------------------ read
    def _read(self) -> list[Entry]:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except (FileNotFoundError, NotADirectoryError):
            return []
        except (OSError, UnicodeDecodeError) as e:
            log.warning("context notes unreadable: %s", type(e).__name__)
            return []
        out: list[Entry] = []
        for line in raw.splitlines():
            try:
                e = Entry.from_json(json.loads(line))
            except ValueError:
                continue  # a torn last line (the engine stopped mid-write): skip it
            if e is not None:
                out.append(e)
        return out

    def entries(self) -> list[Entry]:
        """Every note of this lesson, oldest first (empty when memory is off)."""
        if not enabled():
            return []
        with _lock(self.path):
            return self._read()

    def wipe(self) -> None:
        _bump(lesson_key(self.lesson_id))
        with _lock(self.path):
            for p in (self.path, self.path.with_name(self.path.name[: -len(".jsonl")] + FILES_SUFFIX)):
                try:
                    p.unlink()
                except FileNotFoundError:
                    pass
                except OSError as e:
                    log.warning("context notes not removed: %s", type(e).__name__)
            _index.pop(str(self.path), None)


# ---------------------------------------------------------------- retention
def wipe_lesson(lesson_id: str | None) -> None:
    ContextStore(lesson_id).wipe()


def wipe_all() -> int:
    """Delete my data: every lesson's notes and scan cache. → how many files went."""
    _bump()  # first: a scan finishing during the wipe drops what it read instead of saving it
    d = root()
    n = 0
    if not d.is_dir():
        return 0
    for p in list(d.iterdir()):
        if p.is_file() and (p.name.endswith(".jsonl") or p.name.endswith(FILES_SUFFIX) or p.name.startswith(".")):
            with _lock(p):
                try:
                    p.unlink()
                    n += 1
                except OSError as e:
                    log.warning("context file not removed: %s", type(e).__name__)
    _index.clear()
    log.info("context memory wiped (%d files)", n)
    return n


def prune(*, now: float | None = None, ttl_days: float = TTL_DAYS, max_lessons: int = MAX_LESSONS) -> int:
    """Remove lesson files untouched for ttl_days, then all but the max_lessons most recent. → files removed."""
    d = root()
    if not d.is_dir():
        return 0
    now = time.time() if now is None else now
    notes = []
    for p in d.glob("*.jsonl"):
        try:
            notes.append((p.stat().st_mtime, p))
        except OSError:
            continue
    notes.sort(reverse=True)
    gone = 0
    for i, (mtime, p) in enumerate(notes):
        if now - mtime > ttl_days * 86400 or i >= max_lessons:
            _bump(p.name[: -len(".jsonl")])
            for q in (p, p.with_name(p.name[: -len(".jsonl")] + FILES_SUFFIX)):
                try:
                    q.unlink()
                    gone += 1
                except OSError:
                    pass
            _index.pop(str(p), None)
    return gone


def facts() -> dict:
    """For Settings > Privacy: what is kept (PRIVACY_FACT) and how much is on this Mac right now."""
    d = root()
    files = list(d.glob("*.jsonl")) if d.is_dir() else []
    size = 0
    for p in files:
        try:
            size += p.stat().st_size
        except OSError:
            pass
    return {**PRIVACY_FACT, "lessons": len(files), "bytes": size, "enabled": enabled(), "ttlDays": TTL_DAYS}

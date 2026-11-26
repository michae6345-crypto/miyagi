"""Proof of a pass (contract Proof, UI-V4.md section 4): the learner's own work when a step passed.
~/miyagi/state/proofs/<id>.json, on this Mac only, never sent anywhere.

A proof is small: the lines of the learner's file the step asked for (kind "code"), a notebook cell (kind "cell"), or
the command and the tail of its output (kind "command"). text <= PROOF_TEXT_MAX, output <= PROOF_OUTPUT_MAX (cut from
the top, `truncated` set), secrets redacted (server.redact), a secret file (.env, keys) never read. `file` is the path
relative to the lesson folder (a reference, never a copy of the file). No screenshot is ever kept. Every proof can be
deleted: one, a skill's, or all (data.delete).

    build(step, file_text=, file_ref=, run=, cell=) -> body | None            (pure)
    save(body, skill_ids=, lesson=, step=, now=)    -> proof id
    get(id) / for_skill(skill_id) / wire(rec, tz)  -> stored records / the contract Proof
    delete(id) / delete_for_skill(skill_id) / wipe()
"""

from __future__ import annotations

import logging
import re
import secrets
import time
from datetime import datetime, tzinfo
from pathlib import PurePath
from typing import Any

from server.redact import is_secret_file, redact_secrets
from server.sessions import store

from . import ledger

log = logging.getLogger("skilltree")

TEXT_MAX = 2000  # contract PROOF_TEXT_MAX
OUTPUT_MAX = 1000  # contract PROOF_OUTPUT_MAX
MAX_LINES = 40
MAX_PROOFS = 300
FOR_SKILL = 5  # proof.get {skillId}: the newest five
MAX_FILE_BYTES = 200_000  # a bigger file is not scanned for the snippet
ID_RE = re.compile(r"^pf-[A-Za-z0-9_-]{4,72}$")
LANGS = {".py": "python", ".ipynb": "python", ".js": "javascript", ".mjs": "javascript", ".ts": "typescript",
         ".tsx": "typescript", ".jsx": "javascript", ".rs": "rust", ".go": "go", ".swift": "swift", ".sql": "sql",
         ".sh": "shell", ".html": "html", ".css": "css", ".c": "c", ".cpp": "cpp", ".cs": "csharp", ".java": "java",
         ".r": "r", ".gd": "gdscript", ".ino": "cpp", ".rb": "ruby"}


def _dir():
    return store.state_dir() / "proofs"


def iso(t: float, tz: tzinfo | None = None) -> str:
    """ISO 8601 with the learner's UTC offset (the contract's times)."""
    d = datetime.fromtimestamp(t, tz) if tz is not None else datetime.fromtimestamp(t).astimezone()
    return d.isoformat(timespec="seconds")


def _cap(text: str, limit: int) -> tuple[str, bool]:
    """The last MAX_LINES lines and `limit` characters (the end of a run or a block is what matters)."""
    lines = str(text or "").replace("\r\n", "\n").strip("\n").split("\n")
    cut = len(lines) > MAX_LINES
    text = "\n".join(lines[-MAX_LINES:] if cut else lines)
    if len(text) > limit:
        text, cut = text[-limit:], True
    return text, cut


def _meaningful(code: str) -> list[str]:
    return [ln.strip() for ln in str(code or "").splitlines() if ln.strip() and not ln.strip().startswith(("#", "//"))]


def snippet(file_text: str, step_code: str) -> tuple[str, int] | None:
    """The lines of the learner's file that hold the step's code, and the 1-based line they start on: from the line
    matching the step's first meaningful line to the one matching its last (the learner's own spelling in between).
    None when it cannot be found."""
    want = _meaningful(step_code)
    if not file_text or not want:
        return None
    lines = file_text.splitlines()
    norm = [ln.strip() for ln in lines]
    try:
        start = norm.index(want[0])
    except ValueError:
        start = next((i for i, ln in enumerate(norm) if len(ln) > 3 and (want[0] in ln or ln in want[0])), -1)
        if start < 0:
            return None
    window = range(start, min(len(lines), start + len(want) * 3 + 5))
    end = next((i for i in window if norm[i] == want[-1]), min(len(lines), start + len(want)) - 1)
    return "\n".join(lines[start:end + 1]), start + 1


def build(step: dict, *, file_text: str | None = None, file_ref: str | None = None, run: Any = None,
          cell: dict | None = None) -> dict | None:
    """The proof body for a passed step, or None when there is nothing of the learner's own to keep.
    run: anything with .command / .output_tail (orchestrator RunInfo) or a {command, output} dict; used for a run step.
    cell: {source, output} of the notebook cell that passed."""
    step = step if isinstance(step, dict) else {}
    body: dict[str, Any] | None = None
    is_run = step.get("kind") == "run" or bool(str(step.get("run_command") or "").strip()) or not step.get("code")
    if isinstance(cell, dict) and str(cell.get("source") or "").strip():
        body = {"kind": "cell", "text": str(cell["source"]), "output": str(cell.get("output") or "")}
    elif run is not None and is_run:
        cmd = run.get("command") if isinstance(run, dict) else getattr(run, "command", "")
        out = run.get("output") if isinstance(run, dict) else getattr(run, "output_tail", [])
        out = "\n".join(str(x) for x in out) if isinstance(out, list) else str(out or "")
        if str(cmd or "").strip():
            body = {"kind": "command", "text": str(cmd).strip(), "output": out}
    elif file_text and not is_secret_file(file_ref) and len(file_text.encode("utf-8", "ignore")) <= MAX_FILE_BYTES:
        if hit := snippet(file_text, step.get("code") or ""):
            body = {"kind": "code", "text": hit[0], "line": hit[1]}
    if not body:
        return None
    body["text"], cut = _cap(redact_secrets(body["text"]), TEXT_MAX)
    if not body["text"].strip():
        return None
    if body.get("output", "").strip():
        body["output"], cut2 = _cap(redact_secrets(body["output"]), OUTPUT_MAX)
        cut = cut or cut2
    else:
        body.pop("output", None)
    if cut:
        body["truncated"] = True
    ref = file_ref or step.get("file")
    if ref and body["kind"] in ("code", "cell"):
        body["file"] = str(ref)[:200]
    lang = LANGS.get(PurePath(str(ref or "")).suffix.lower()) or ("shell" if body["kind"] == "command" else None)
    if lang:
        body["lang"] = lang
    return body


def check_label(step: dict) -> str:
    """The check that passed, in words (Proof.check.label): the step's first check label, else its title."""
    for c in step.get("checks") or []:
        if isinstance(c, dict) and str(c.get("label") or "").strip():
            return " ".join(str(c["label"]).split())[:120]
    return " ".join(str(step.get("title") or "Step passed").split())[:120]


def _all() -> list[dict]:
    d = _dir()
    out = []
    for f in d.glob("pf-*.json") if d.exists() else []:
        data = store._read(f)
        if isinstance(data, dict) and data.get("id") == f.stem:
            out.append(data)
    return sorted(out, key=lambda p: p.get("at") or 0)


def save(body: dict, *, skill_ids: list[str], lesson: dict | None = None, step: dict | None = None,
         now: float | None = None) -> str:
    """Store a proof; the oldest go past MAX_PROOFS. Returns its id ("pf-<lesson>-<step>-<random>")."""
    now = time.time() if now is None else float(now)
    lesson, step = lesson or {}, step or {}
    lid, sid = str(lesson.get("id") or "lesson")[:80], str(step.get("id") or "step")[:40]
    tag = re.sub(r"[^A-Za-z0-9_-]", "", f"{lid[-8:]}-{sid}")[:56] or "x"
    pid = f"pf-{tag}-{secrets.token_hex(3)}"
    rec = {"id": pid, "at": now, "key": f"{lid}:{sid}", "skillIds": list(skill_ids)[:10], "lessonId": lid,
           "stepId": sid, "stepTitle": str(step.get("title") or sid)[:200], "check": {"label": check_label(step)},
           **{k: body[k] for k in ("kind", "text", "output", "lang", "file", "line", "truncated") if k in body}}
    if lesson.get("title"):
        rec["lessonTitle"] = str(lesson["title"])[:200]
    store._write_atomic(_dir() / f"{pid}.json", rec)
    rows = _all()
    for old in rows[:max(0, len(rows) - MAX_PROOFS)]:
        _unlink(old["id"])
    return pid


def wire(rec: dict, tz: tzinfo | None = None) -> dict:
    """A stored record as the contract's Proof (at as ISO text)."""
    out = {k: v for k, v in rec.items() if k != "at"}
    out["at"] = iso(float(rec.get("at") or 0), tz)
    return out


def _unlink(pid: str) -> bool:
    if not ID_RE.match(pid or ""):
        return False
    try:
        (_dir() / f"{pid}.json").unlink()
        return True
    except FileNotFoundError:
        return False


def get(proof_id: str) -> dict | None:
    if not ID_RE.match(proof_id or ""):
        return None
    data = store._read(_dir() / f"{proof_id}.json")
    return data if isinstance(data, dict) and data.get("id") == proof_id else None


def for_skill(skill_id: str, limit: int = FOR_SKILL) -> list[dict]:
    return [p for p in reversed(_all()) if skill_id in (p.get("skillIds") or [])][:limit]


def _drop_refs(ids: set[str]) -> None:
    if not ids:
        return
    with ledger._lock:
        rows = ledger.load()
        changed = False
        for row in rows.values():
            for p in row["passes"]:
                if p.get("proofId") in ids:
                    p.pop("proofId")
                    changed = True
        if changed:
            ledger._save(rows)


def delete(proof_id: str) -> bool:
    ok = _unlink(proof_id)
    if ok:
        _drop_refs({proof_id})
    return ok


def delete_for_skill(skill_id: str) -> int:
    gone = {p["id"] for p in _all() if skill_id in (p.get("skillIds") or []) and _unlink(p["id"])}
    _drop_refs(gone)
    return len(gone)


def wipe() -> int:
    """Every proof (data.delete proofs / all). The skill record keeps its passes, without the proof references."""
    gone = {p["id"] for p in _all() if _unlink(p["id"])}
    _drop_refs(gone)
    return len(gone)

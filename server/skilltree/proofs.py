"""Proof of a pass: what the learner's own work looked like when a step passed. ~/miyagi/state/proofs/<id>.json.

A proof is small and local: a snippet of the learner's file (the lines the step asked for), a notebook cell, or a
command and the tail of its output. Capped at MAX_CHARS / MAX_LINES, secrets redacted (server.redact), a secret file
(.env, keys) never read. It names the file by its path relative to the lesson folder (a reference, never a copy of the
file). Nothing here leaves the Mac; every proof can be deleted (one, a skill's, or all: Delete my data).

    build(step, file_text=, file_ref=, run=, cell=)  -> proof body | None   (pure)
    save(body, skill_ids=, lesson_id=, step_id=, now=) -> proof id
    get(proof_id) / for_skill(skill_id)            -> stored proofs
    delete(proof_id) / delete_for_skill(skill_id) / wipe()
"""

from __future__ import annotations

import logging
import re
import secrets
import time
from typing import Any

from server.redact import is_secret_file, redact_secrets
from server.sessions import store

from . import ledger

log = logging.getLogger("skilltree")

MAX_CHARS = 2000
MAX_LINES = 40
MAX_PROOFS = 300
MAX_FILE_BYTES = 200_000  # a bigger file is not scanned for the snippet
ID_RE = re.compile(r"^[a-z0-9-]{6,40}$")
KINDS = ("snippet", "cell", "output")


def _dir():
    return store.state_dir() / "proofs"


def _cap(text: str) -> tuple[str, bool]:
    lines = str(text or "").replace("\r\n", "\n").split("\n")
    cut = len(lines) > MAX_LINES
    text = "\n".join(lines[-MAX_LINES:] if cut else lines)
    if len(text) > MAX_CHARS:
        text, cut = text[-MAX_CHARS:], True
    return text.strip("\n"), cut


def _meaningful(code: str) -> list[str]:
    return [ln.strip() for ln in str(code or "").splitlines() if ln.strip() and not ln.strip().startswith(("#", "//"))]


def snippet(file_text: str, step_code: str) -> str | None:
    """The lines of the learner's file that hold the step's code: from the first line matching the step's first
    meaningful line to the last matching its last one (the learner's own spelling). None when it cannot be found."""
    want = _meaningful(step_code)
    if not file_text or not want:
        return None
    lines = file_text.splitlines()
    norm = [ln.strip() for ln in lines]
    try:
        start = norm.index(want[0])
    except ValueError:
        start = next((i for i, ln in enumerate(norm) if ln and (want[0] in ln or ln in want[0]) and len(ln) > 3), -1)
        if start < 0:
            return None
    window = range(start, min(len(lines), start + len(want) * 3 + 5))
    end = next((i for i in window if norm[i] == want[-1]), min(len(lines), start + len(want)) - 1)
    return "\n".join(lines[start:end + 1])


def build(step: dict, *, file_text: str | None = None, file_ref: str | None = None, run: Any = None,
          cell: dict | None = None) -> dict | None:
    """The proof body for a passed step, or None when there is nothing of the learner's to keep.
    run: anything with .command / .output_tail (orchestrator RunInfo) or a {command, output} dict.
    cell: {source, output} of the notebook cell that passed."""
    step = step if isinstance(step, dict) else {}
    body: dict[str, Any] | None = None
    if cell and isinstance(cell, dict) and str(cell.get("source") or "").strip():
        out = str(cell.get("output") or "")
        text = str(cell["source"]).rstrip() + (("\n# output\n" + out) if out.strip() else "")
        body = {"kind": "cell", "text": text}
    elif run is not None and (step.get("kind") == "run" or step.get("run_command") or not step.get("code")):
        cmd = run.get("command") if isinstance(run, dict) else getattr(run, "command", "")
        out = run.get("output") if isinstance(run, dict) else getattr(run, "output_tail", [])
        out = "\n".join(str(x) for x in out) if isinstance(out, list) else str(out or "")
        if str(cmd or "").strip() or out.strip():
            body = {"kind": "output", "text": f"$ {str(cmd or '').strip()}\n{out}".strip(), "command": str(cmd or "")[:300]}
    elif file_text and not is_secret_file(file_ref):
        if len(file_text.encode("utf-8", "ignore")) <= MAX_FILE_BYTES and (snip := snippet(file_text, step.get("code") or "")):
            body = {"kind": "snippet", "text": snip}
    if not body:
        return None
    body["text"], body["truncated"] = _cap(redact_secrets(body["text"]))
    if "command" in body:
        body["command"] = redact_secrets(body["command"])
    if not body["text"]:
        return None
    if file_ref and body["kind"] == "snippet":
        body["file"] = str(file_ref)[:200]
    return body


def _all() -> list[dict]:
    d = _dir()
    out = []
    for f in d.glob("*.json") if d.exists() else []:
        data = store._read(f)
        if isinstance(data, dict) and data.get("id") == f.stem:
            out.append(data)
    return sorted(out, key=lambda p: p.get("at") or 0)


def save(body: dict, *, skill_ids: list[str], lesson_id: str | None = None, step_id: str | None = None,
         now: float | None = None) -> str:
    """Store a proof; the oldest go past MAX_PROOFS. Returns its id."""
    now = time.time() if now is None else float(now)
    pid = f"p{int(now)}-{secrets.token_hex(4)}"
    rec = {"id": pid, "at": now, "skillIds": list(skill_ids)[:10], **{k: body[k] for k in body if k in
           ("kind", "text", "truncated", "file", "command")}}
    if lesson_id:
        rec["lessonId"] = str(lesson_id)[:120]
    if step_id:
        rec["stepId"] = str(step_id)[:120]
    store._write_atomic(_dir() / f"{pid}.json", rec)
    rows = _all()
    if len(rows) > MAX_PROOFS:
        for old in rows[:len(rows) - MAX_PROOFS]:
            _unlink(old["id"])
    return pid


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


def for_skill(skill_id: str, limit: int = 5) -> list[dict]:
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
    """Every proof (Delete my data). The skill record keeps its passes, without the proof references."""
    gone = {p["id"] for p in _all() if _unlink(p["id"])}
    _drop_refs(gone)
    return len(gone)

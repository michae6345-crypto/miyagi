"""Put the neural-net lesson back to its first moment, for the installed app's data. Moves, never deletes.

    python -m server.demokit.reset [--dry-run]        (scripts/miyagi-demo-reset.sh)

The lesson folder (~/miyagi/lessons/<slug>-<hash>):
    nn.py         the earlier one moves to ~/miyagi/lessons/.miyagi-state/attempts/<folder>/nn-<time>.py (the archive
                  the engine already keeps), then the clean starter is written
    other files   the learner's own (not dot entries, not README.md) move next to it, under <time>-files/
    .venv         kept, so NumPy stays installed; .vscode kept, and the calm view keys added (bigger font included)
The lesson's resume state moves to ~/miyagi/state/.demo-backups/<time>/ (a new folder each run, <time>-1/ when taken; with
manifest.json saying where each came from, written only when something moves):
    current.json and its graph file (only when they are this lesson's), context/<lessonId>.*, the proofs of this lesson,
    and its recent.json entry (recent.json is rewritten without it; the whole old file is in the backup).
Nothing else: other lessons, history, skills, prefs, onboarding and sign-in stay as they are.
Refuses while the miyagi app or an engine runs (it would write its own state back).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from .common import (
    FILE,
    MISSING,
    Layout,
    graph_name,
    lesson_key,
    read_code,
    read_json,
    running,
    tilde,
)

QUIT_FIRST = "miyagi is running ({}): quit miyagi first (osascript -e 'quit app \"miyagi\"'), then run this again."
KEEP_IN_FOLDER = {FILE, "README.md"}


@dataclass
class Move:
    src: Path
    dest: Path
    what: str


@dataclass
class Plan:
    folder: Path
    backup: Path
    moves: list[Move] = field(default_factory=list)
    write_starter: bool = False
    recent_drop: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.moves or self.write_starter or self.recent_drop)


def make_plan(lay: Layout, now: float | None = None) -> Plan:
    """What a reset would move and write (reads only)."""
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
    lid, _title = lay.lesson()
    folder = lay.folder()
    backup = _free(lay.backups / stamp)  # a second reset in the same second never reuses the first one's backup
    plan = Plan(folder=folder, backup=backup)

    # 1. the lesson folder
    if folder.is_dir():
        nn = folder / FILE
        cur = read_code(nn)
        keep = lay.attempts / folder.name
        if cur is None:  # there but unreadable (no read permission, not UTF-8 text): still the learner's, so move it
            plan.moves.append(Move(nn, keep / f"nn-{stamp}.py", f"your last {FILE} (it could not be read)"))
            plan.write_starter = True
        elif cur is MISSING:
            plan.write_starter = True
        elif cur != lay.starter():
            if cur.strip():
                plan.moves.append(Move(nn, keep / f"nn-{stamp}.py", f"your last {FILE}"))
            plan.write_starter = True
        for p in sorted(folder.iterdir()):
            if p.name in KEEP_IN_FOLDER or p.name.startswith("."):
                continue
            plan.moves.append(Move(p, keep / f"{stamp}-files" / p.name, f"{p.name} (left from an earlier take)"))
        if not (folder / ".venv").is_dir():
            plan.notes.append("no .venv yet: the lesson's setup card installs NumPy at the first start (needs Wi-Fi)")
    else:
        plan.notes.append("no lesson folder yet: miyagi makes a clean one at the first start")

    # 2. the resume state
    st = lay.state
    cur = read_json(st / "current.json")
    if isinstance(cur, dict) and cur.get("lessonId") == lid:
        step = cur.get("stepIndex")
        where = f" (step {int(step) + 1} of {cur.get('stepCount') or '?'})" if isinstance(step, int) else ""
        plan.moves.append(Move(st / "current.json", backup / "current.json", f"the saved place{where}"))
        names = {graph_name(lid)}
        if isinstance(cur.get("graphFile"), str) and "/" not in cur["graphFile"]:
            names.add(cur["graphFile"])
        for n in sorted(names):
            if (st / n).is_file():
                plan.moves.append(Move(st / n, backup / n, "its saved lesson graph"))
    elif (st / graph_name(lid)).is_file():  # left behind: nothing points at it, but it is this lesson's
        plan.moves.append(Move(st / graph_name(lid), backup / graph_name(lid), "an old saved lesson graph"))

    ctx = st / "context"
    if ctx.is_dir():
        key = lesson_key(lid)
        for p in sorted(ctx.iterdir()):
            if p.is_file() and p.name.startswith(key + "."):
                plan.moves.append(Move(p, backup / "context" / p.name, "its context notes"))

    proofs = st / "proofs"
    if proofs.is_dir():
        mine = [p for p in sorted(proofs.glob("pf-*.json"))
                if isinstance(rec := read_json(p), dict) and rec.get("lessonId") == lid]
        for p in mine:
            plan.moves.append(Move(p, backup / "proofs" / p.name, "a proof"))

    recent = read_json(st / "recent.json")
    if isinstance(recent, list):
        plan.recent_drop = [e for e in recent if isinstance(e, dict) and e.get("lessonId") == lid]
    return plan


def _write_atomic(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _free(dest: Path) -> Path:
    n, i = dest, 1
    while n.exists():
        n, i = dest.with_name(f"{dest.stem}-{i}{dest.suffix}"), i + 1
    return n


def _claim_backup(plan: Plan) -> None:
    """Make the plan's backup folder, a new one only: if it showed up since make_plan (another reset), take the next
    free name and point the plan's backup moves there."""
    while True:
        try:
            plan.backup.mkdir(parents=True)
            return
        except FileExistsError:
            old, new = plan.backup, _free(plan.backup)
            for m in plan.moves:
                if old in m.dest.parents:
                    m.dest = new / m.dest.relative_to(old)
            plan.backup = new


def apply(plan: Plan, lay: Layout, *, calm=None) -> list[str]:
    """Do the plan. Returns notes on what it did beyond the plan. Raises OSError on a failed move (what moved stays
    listed in the backup's manifest.json)."""
    out: list[str] = []
    if plan.empty and not plan.folder.is_dir():
        return out
    manifest = {"lessonId": lay.lesson()[0], "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "folder": str(plan.folder),
                "moves": [], "recentRemoved": plan.recent_drop, "done": False}
    if not plan.empty:
        _claim_backup(plan)

    def save_manifest() -> None:
        if not plan.empty:  # nothing moves: no manifest, so an earlier backup's record is never written over
            _write_atomic(plan.backup / "manifest.json", json.dumps(manifest, indent=1) + "\n")

    save_manifest()
    for m in plan.moves:
        dest = _free(m.dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(m.src), str(dest))
        manifest["moves"].append({"from": str(m.src), "to": str(dest), "what": m.what})
        save_manifest()
    if plan.recent_drop:
        rp = lay.state / "recent.json"
        old = rp.read_text(encoding="utf-8")
        _write_atomic(plan.backup / "recent.json", old)
        rest = [e for e in json.loads(old) if not (isinstance(e, dict) and e.get("lessonId") == manifest["lessonId"])]
        _write_atomic(rp, json.dumps(rest, ensure_ascii=False))
    if plan.write_starter and plan.folder.is_dir():
        (plan.folder / FILE).write_text(lay.starter(), encoding="utf-8")
    if plan.folder.is_dir():
        changed = (calm or _calm_view)(plan.folder)
        if changed is None:
            out.append("calm VS Code view: skipped (run with the repo's .venv to add it)")
        elif changed:
            out.append("calm VS Code view: added to .vscode/settings.json (bigger font included)")
    manifest["done"] = True
    save_manifest()
    return out


def _calm_view(folder: Path) -> bool | None:
    """The calm view keys with the demo font (server.workspace.core), or None when the engine's code can't load."""
    try:
        from server.workspace import core
    except Exception:  # noqa: BLE001 - a bare python3 without the engine's packages
        return None
    return core.ensure_calm_view(folder, demo=True)


def describe(plan: Plan, lay: Layout, *, dry: bool) -> list[str]:
    h = lay.home
    lines = [f"Neural-net lesson: {tilde(plan.folder, h)}"]
    for m in plan.moves:
        to = "backup" if plan.backup in m.dest.parents else tilde(m.dest, h)
        lines.append(f"  move   {m.what}: {tilde(m.src, h)} -> {to}")
    if plan.recent_drop:
        lines.append("  move   its entry in recent.json (\"Continue\" in the launcher) -> backup")
    if plan.write_starter:
        lines.append(f"  write  the clean starter {FILE}")
    if plan.folder.is_dir():
        if (plan.folder / ".venv").is_dir():
            lines.append("  keep   .venv (NumPy stays installed)")
        lines.append("  add    calm VS Code view keys (a value already there wins)")
    lines += [f"  note   {n}" for n in plan.notes]
    if plan.empty:
        lines.append("Already at its first moment: nothing to move.")
    elif dry:
        lines.append(f"Dry run: nothing moved. A real run backs up to {tilde(plan.backup, h)}")
    return lines


def main(argv: list[str] | None = None, *, lay: Layout | None = None, is_running=None, out=print) -> int:
    ap = argparse.ArgumentParser(prog="miyagi-demo-reset", description="Put the neural-net lesson back to its first moment.")
    ap.add_argument("--dry-run", action="store_true", help="only print what would move")
    args = ap.parse_args(argv)
    lay = lay or Layout(home=Path.home())
    busy = (is_running or (lambda: running(lay.port)))()
    if busy and not args.dry_run:
        out(QUIT_FIRST.format(" and ".join(busy)))
        return 2
    plan = make_plan(lay)
    for ln in describe(plan, lay, dry=args.dry_run):
        out(ln)
    if args.dry_run:
        if busy:
            out(QUIT_FIRST.format(" and ".join(busy)))
        return 0
    try:
        for ln in apply(plan, lay):
            out(f"  {ln}")
    except OSError as e:
        out(f"Stopped: {e}. Nothing was deleted; what moved is listed in {tilde(plan.backup / 'manifest.json', lay.home)}")
        return 1
    if not plan.empty:
        out(f"Done. Backup: {tilde(plan.backup, lay.home)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

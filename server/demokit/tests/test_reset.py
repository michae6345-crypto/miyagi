"""The demo reset, on a temp HOME and a temp app bundle only (never the real ~/miyagi)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from server.demokit import common, reset
from server.demokit.common import FILE, Layout

LID = "lesson-nn-from-scratch"
STARTER = "# starter\nimport numpy as np\n\n# The network\n"
FINISHED = STARTER + "W1 = np.random.randn(1, 4)\n"


def _app(tmp_path: Path) -> Path:
    """A fake installed app carrying its own engine source (lesson graph + starter)."""
    app = tmp_path / "Applications" / "miyagi.app"
    src = app / "Contents" / "Resources" / "engine" / "src"
    (src / "demo" / "cache" / "lessons").mkdir(parents=True)
    (src / "demo" / "nn-start.py").write_text(STARTER)
    (src / "demo" / "cache" / "lessons" / "text-nn-from-scratch.json").write_text(
        json.dumps({"lesson": {"id": LID, "title": "A neural net from scratch"}, "steps": []}))
    return app


@pytest.fixture()
def lay(tmp_path) -> Layout:
    home = tmp_path / "home"
    home.mkdir()
    return Layout(home=home, app=_app(tmp_path), repo=tmp_path / "no-repo", port=1)


def _used_lesson(lay: Layout) -> Path:
    """The state a finished demo take leaves: finished nn.py, a .venv, a saved place, notes, proofs, recent entry."""
    folder = lay.folder()
    (folder / ".venv" / "lib").mkdir(parents=True)
    (folder / ".vscode").mkdir()
    (folder / ".vscode" / "settings.json").write_text(json.dumps({"editor.fontSize": 20}))
    (folder / "README.md").write_text("# A neural net from scratch\n")
    (folder / FILE).write_text(FINISHED)
    (folder / "scratch.py").write_text("print(1)\n")
    st = lay.state
    (st / "context").mkdir(parents=True)
    (st / "proofs").mkdir()
    (st / "current.json").write_text(json.dumps({"lessonId": LID, "stepIndex": 3, "stepCount": 6,
                                                 "graphFile": f"graph-{LID}.json"}))
    (st / f"graph-{LID}.json").write_text(json.dumps({"lesson": {"id": LID}}))
    (st / "context" / f"{LID}.jsonl").write_text("{}\n")
    (st / "context" / f"{LID}.files.json").write_text("{}")
    (st / "context" / "lesson-other.jsonl").write_text("{}\n")
    (st / "context" / f"{LID}-v2.jsonl").write_text("{}\n")  # another lesson whose id starts the same
    (st / "proofs" / "pf-scratch-nn1-aaaaaa.json").write_text(json.dumps({"id": "pf-scratch-nn1-aaaaaa", "lessonId": LID}))
    (st / "proofs" / "pf-other-s1-bbbbbb.json").write_text(json.dumps({"id": "pf-other-s1-bbbbbb", "lessonId": "lesson-other"}))
    (st / "recent.json").write_text(json.dumps([{"lessonId": "lesson-other", "title": "Other"},
                                                {"lessonId": LID, "title": "A neural net from scratch"}]))
    for name in ("history.json", "skilltree.json", "mastery.json"):
        (st / name).write_text("[]")
    sup = lay.app_support
    sup.mkdir(parents=True)
    for name in ("auth.bin", "prefs.json", "onboarding.json"):
        (sup / name).write_bytes(b"x")
    other = lay.lessons / "build-a-ray-tracer-ebb86f"
    other.mkdir(parents=True)
    (other / "main.py").write_text("ray\n")
    return folder


def _tree(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def _run(lay, *args, busy=()):
    lines: list[str] = []
    code = reset.main(list(args), lay=lay, is_running=lambda: list(busy), out=lines.append)
    return code, lines


def test_folder_name_and_lesson_key_match_the_engine():
    from server.context.store import lesson_key
    from server.workspace.paths import folder_name

    g = {"lesson": {"id": LID, "title": "A neural net from scratch"}}
    assert common.folder_name(LID, "A neural net from scratch") == folder_name(g) == "a-neural-net-from-scratch-da5236"
    for lid in (LID, "lesson/../x y", "ünï"):
        assert common.lesson_key(lid) == lesson_key(lid)


def test_the_repo_lesson_and_starter_are_what_the_engine_uses(tmp_path):
    from server.orchestrator import curated

    lay = Layout(home=tmp_path, app=tmp_path / "none.app", repo=common.REPO_ROOT)
    assert lay.lesson() == (LID, "A neural net from scratch")
    assert lay.starter() == curated.STARTER_FILE.read_text(encoding="utf-8")


def test_the_installed_app_wins_over_the_checkout(lay):
    assert lay.starter() == STARTER and lay.folder().name == "a-neural-net-from-scratch-da5236"


def test_reset_puts_the_lesson_back_to_its_first_moment(lay):
    folder = _used_lesson(lay)
    code, lines = _run(lay)
    assert code == 0, lines
    st = lay.state
    assert (folder / FILE).read_text() == STARTER
    assert (folder / ".venv" / "lib").is_dir()  # NumPy stays
    assert (folder / "README.md").exists() and not (folder / "scratch.py").exists()
    arch = lay.attempts / folder.name
    kept = list(arch.glob("nn-*.py"))
    assert len(kept) == 1 and kept[0].read_text() == FINISHED
    assert [p.read_text() for p in arch.glob("*-files/scratch.py")] == ["print(1)\n"]
    assert not (st / "current.json").exists() and not (st / f"graph-{LID}.json").exists()
    assert not list((st / "context").glob(f"{LID}.*"))
    assert (st / "context" / "lesson-other.jsonl").exists() and (st / "context" / f"{LID}-v2.jsonl").exists()
    assert not (st / "proofs" / "pf-scratch-nn1-aaaaaa.json").exists()
    assert (st / "proofs" / "pf-other-s1-bbbbbb.json").exists()
    assert json.loads((st / "recent.json").read_text()) == [{"lessonId": "lesson-other", "title": "Other"}]
    backup = next(lay.backups.iterdir())
    for rel in ("current.json", f"graph-{LID}.json", f"context/{LID}.jsonl", f"context/{LID}.files.json",
                "proofs/pf-scratch-nn1-aaaaaa.json", "recent.json", "manifest.json"):
        assert (backup / rel).is_file(), rel
    assert len(json.loads((backup / "recent.json").read_text())) == 2
    man = json.loads((backup / "manifest.json").read_text())
    assert man["done"] is True and man["lessonId"] == LID and len(man["moves"]) == 7
    assert all(Path(m["to"]).exists() for m in man["moves"])
    assert all(not Path(m["from"]).exists() for m in man["moves"] if Path(m["from"]).name != FILE)  # nn.py: the starter
    assert any(ln.startswith("Done. Backup: ~/miyagi/state/.demo-backups/") for ln in lines)


def test_reset_touches_nothing_else(lay):
    _used_lesson(lay)
    sup, other = _tree(lay.app_support), _tree(lay.lessons / "build-a-ray-tracer-ebb86f")
    hist = {n: (lay.state / n).read_bytes() for n in ("history.json", "skilltree.json", "mastery.json")}
    assert _run(lay)[0] == 0
    assert _tree(lay.app_support) == sup and _tree(lay.lessons / "build-a-ray-tracer-ebb86f") == other
    assert {n: (lay.state / n).read_bytes() for n in hist} == hist


def test_nothing_is_ever_deleted(lay):
    _used_lesson(lay)
    before = {k: v for k, v in _tree(lay.home).items() if not k.endswith(".vscode/settings.json")}  # merged: below
    _run(lay)
    after = _tree(lay.home)
    # every old file's bytes are still somewhere under HOME (moved, not deleted)
    for blob in before.values():
        assert blob in after.values()


def test_the_calm_view_with_the_demo_font_is_added_and_a_value_there_wins(lay):
    folder = _used_lesson(lay)
    _run(lay)
    got = json.loads((folder / ".vscode" / "settings.json").read_text())
    assert got["editor.fontSize"] == 20 and got["terminal.integrated.fontSize"] == 15
    assert got["workbench.startupEditor"] == "none" and got["breadcrumbs.enabled"] is False


def test_a_saved_place_of_another_lesson_stays(lay):
    _used_lesson(lay)
    cur = {"lessonId": "lesson-other", "stepIndex": 1, "graphFile": "graph-lesson-other.json"}
    (lay.state / "current.json").write_text(json.dumps(cur))
    (lay.state / "graph-lesson-other.json").write_text("{}")
    _run(lay)
    assert json.loads((lay.state / "current.json").read_text()) == cur
    assert (lay.state / "graph-lesson-other.json").exists()
    assert not (lay.state / f"graph-{LID}.json").exists()  # this lesson's leftover graph still moves


def test_dry_run_moves_nothing(lay):
    _used_lesson(lay)
    before = _tree(lay.home)
    code, lines = _run(lay, "--dry-run")
    assert code == 0 and _tree(lay.home) == before
    assert not lay.backups.exists()
    text = "\n".join(lines)
    assert "your last nn.py" in text and "the saved place (step 4 of 6)" in text and "Dry run: nothing moved" in text
    assert "keep   .venv" in text


def test_refuses_while_miyagi_runs(lay):
    _used_lesson(lay)
    before = _tree(lay.home)
    code, lines = _run(lay, busy=["the miyagi app", "an engine on :8787"])
    assert code == 2 and _tree(lay.home) == before
    assert lines == [("miyagi is running (the miyagi app and an engine on :8787): quit miyagi first "
                      "(osascript -e 'quit app \"miyagi\"'), then run this again.")]


def test_dry_run_while_running_still_prints_and_says_quit(lay):
    _used_lesson(lay)
    code, lines = _run(lay, "--dry-run", busy=["the miyagi app"])
    assert code == 0 and lines[-1].startswith("miyagi is running (the miyagi app)")


def test_a_second_reset_finds_nothing_to_move(lay):
    _used_lesson(lay)
    _run(lay)
    code, lines = _run(lay)
    assert code == 0 and "Already at its first moment: nothing to move." in lines
    assert len(list(lay.backups.iterdir())) == 1


def test_no_folder_yet_is_fine(lay):
    code, lines = _run(lay)
    assert code == 0 and any("no lesson folder yet" in ln for ln in lines)
    assert not lay.folder().exists() and not lay.backups.exists()


def test_a_missing_nn_py_gets_the_starter(lay):
    folder = lay.folder()
    folder.mkdir(parents=True)
    _run(lay)
    assert (folder / FILE).read_text() == STARTER
    assert not (lay.attempts / folder.name).exists()


def test_two_resets_in_one_second_never_overwrite_the_archive(lay):
    folder = _used_lesson(lay)
    plan = reset.make_plan(lay, now=1_700_000_000)
    reset.apply(plan, lay, calm=lambda f: False)
    (folder / FILE).write_text("second take\n")
    reset.apply(reset.make_plan(lay, now=1_700_000_000), lay, calm=lambda f: False)
    kept = sorted(p.read_text() for p in (lay.attempts / folder.name).glob("nn-*.py"))
    assert kept == sorted([FINISHED, "second take\n"])


def test_running_reports_the_app_and_the_engine():
    procs = {common.APP_PROC: True, common.ENGINE_PROC: True}
    assert common.running(8787, port_probe=lambda p: False, proc_probe=procs.get) == ["the miyagi app", "an engine"]
    assert common.running(8787, port_probe=lambda p: True, proc_probe=lambda p: False) == ["an engine on :8787"]
    assert common.running(8787, port_probe=lambda p: False, proc_probe=lambda p: False) == []


def test_the_app_pattern_skips_its_helpers():
    import re

    rx = re.compile(common.APP_PROC)
    assert rx.search("/Applications/miyagi.app/Contents/MacOS/miyagi")
    assert not rx.search("/Applications/miyagi.app/Contents/Frameworks/miyagi Helper (Renderer).app/Contents/MacOS/"
                         "miyagi Helper (Renderer) --type=renderer")
    assert not rx.search("/Applications/miyagi.app/Contents/Resources/engine/python/bin/python3 -s -B -m "
                         "server.orchestrator.main")


@pytest.mark.skipif(shutil.which("pgrep") is None, reason="no pgrep")
def test_pgrep_takes_every_pattern():
    """Exit 2 is a usage error (a pattern read as an option): every pattern must give 0 (found) or 1 (not found)."""
    from server.demokit import check

    for pat in (common.APP_PROC, common.ENGINE_PROC, check.VSCODE_PROC, check.CAFFEINATE_PROC):
        assert subprocess.run([*common.PGREP, pat], capture_output=True, timeout=5, check=False).returncode in (0, 1), pat

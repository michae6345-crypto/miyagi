"""A fresh Mac: the only Python is miyagi.app's (MIYAGI_BUNDLED_PYTHON), PATH=/usr/bin:/bin, no Homebrew."""
import subprocess
import sys
from pathlib import Path

import pytest

from server.workspace import setup as S



@pytest.fixture(autouse=True)
def _lessons_root(monkeypatch, tmp_path):  # hermetic: never the real ~/Miyagi/lessons
    monkeypatch.setenv("MIYAGI_LESSONS_DIR", str(tmp_path / "lessons"))
    monkeypatch.setattr(S.paths, "lessons_root", lambda: tmp_path / "lessons")


def _no_path_pythons(monkeypatch, bundled: str, plain: str | None = None):
    monkeypatch.setenv("MIYAGI_BUNDLED_PYTHON", bundled)
    monkeypatch.setattr(S.shutil, "which", lambda name, *a, **k: plain if name == "python3" else None)
    monkeypatch.setattr(S, "_xcode_stub", lambda p: False)


def test_best_python_falls_back_to_the_bundle_before_plain_python3(monkeypatch):
    _no_path_pythons(monkeypatch, sys.executable, plain="/usr/bin/python3")  # Apple's 3.9 (Command Line Tools)
    assert S.best_python() == sys.executable and S.is_bundled(sys.executable)
    monkeypatch.setattr(S.shutil, "which", lambda name, *a, **k: "/opt/homebrew/bin/python3.12" if name == "python3.12" else None)
    assert S.best_python() == "/opt/homebrew/bin/python3.12" and not S.is_bundled(S.best_python())  # as before


def test_the_bundles_own_libraries_never_count_for_the_lesson(monkeypatch):
    seen = []
    monkeypatch.setenv("MIYAGI_BUNDLED_PYTHON", sys.executable)
    S.check_python_packages([{"tool": "x", "kind": "python_package", "pip_name": "x"}], sys.executable,
                            run=lambda argv, **k: seen.append(argv) or (0, ""))
    assert seen[0][1:3] == ["-I", "-S"]  # stdlib only: what a new .venv starts with
    seen.clear()
    S.check_python_packages([{"tool": "x", "kind": "python_package", "pip_name": "x"}], "/opt/homebrew/bin/python3.12",
                            run=lambda argv, **k: seen.append(argv) or (0, ""))
    assert seen[0][1] == "-c"


def test_ensure_venv_sets_a_broken_venv_aside_and_never_empties_a_symlinked_one(monkeypatch, tmp_path):
    monkeypatch.setenv("MIYAGI_BUNDLED_PYTHON", sys.executable)
    monkeypatch.setattr(S, "best_python", lambda: sys.executable)
    target = tmp_path / "elsewhere"
    target.mkdir()
    (target / "keep.txt").write_text("mine")
    wd = tmp_path / "lesson"
    wd.mkdir()
    (wd / ".venv").symlink_to(target)  # a .venv that is a link to someone's folder, with no bin/python
    ran = []

    def popen(argv, **kw):
        ran.append(argv)
        (Path(argv[-1]) / "bin").mkdir(parents=True)
        (Path(argv[-1]) / "bin" / "python").write_text("")
        return subprocess.Popen(["true"], stdout=subprocess.PIPE, text=True)

    py, err = S.ensure_venv(wd, popen=popen)
    assert py and not err and "--clear" not in ran[0] and ran[0][-1] == str(wd / ".venv")
    assert (target / "keep.txt").read_text() == "mine"  # the link's target is untouched
    assert sorted(p.name for p in wd.iterdir()) == [".venv"]  # the old link went outside the lesson folder
    assert [p.is_symlink() for p in (tmp_path / "lessons" / ".miyagi-state" / "old-venvs").iterdir()] == [True]


def test_never_a_venv_from_the_disk_image(monkeypatch, tmp_path):
    dmg = "/Volumes/miyagi/miyagi.app/Contents/Resources/engine/python/bin/python3"
    monkeypatch.setenv("MIYAGI_BUNDLED_PYTHON", dmg)
    monkeypatch.setattr(S, "best_python", lambda: dmg)
    monkeypatch.setattr(S, "bundled_python", lambda: dmg)
    py, err = S.ensure_venv(tmp_path, popen=lambda *a, **k: (_ for _ in ()).throw(AssertionError("ran")))
    assert py is None and err == S.NOT_INSTALLED_APP


def test_offline_precheck_only_where_the_host_is_certain(monkeypatch, tmp_path):
    for k in (*S._PROXY_ENV, *S._PIP_CONF, *S._BREW_MIRROR):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(S, "_pip_conf_files", lambda: [tmp_path / "pip.conf"])
    assert S._host_of({"method": "pip"}) == "pypi.org" and S._host_of({"method": "brew"}) == "ghcr.io"
    monkeypatch.setenv("PIP_INDEX_URL", "https://user:pass@nexus.corp:8443/simple")
    assert S._host_of({"method": "pip"}) is None
    monkeypatch.delenv("PIP_INDEX_URL")
    (tmp_path / "pip.conf").write_text("[global]\nindex-url = http://localhost:3141/simple\n")
    assert S._host_of({"method": "pip"}) is None
    (tmp_path / "pip.conf").unlink()
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy:3128")
    assert S._host_of({"method": "pip"}) is None and S._host_of({"method": "brew_cask"}) is None
    assert S.online(None) is True  # nothing certain to probe: the install decides


def test_local_list_maps_import_names_and_skips_non_python_tools():
    graph = {"lesson": {"libraries": {"python": "3", "sklearn": "1", "cv2": "4", "git": "2", "node": "20", "pandas": ""}},
             "steps": [{"id": "s1", "title": "t", "instructions": "", "file": "main.py"}]}
    raw = S.local_requirements(graph)
    pips = {(t["pip_name"], t["import_name"]) for t in raw["tools"] if t["kind"] == "python_package"}
    assert pips == {("scikit-learn", "sklearn"), ("opencv-python", "cv2"), ("pandas", "")}
    assert raw["editor"]["needed"] is True


def test_ipykernel_only_for_a_vs_code_notebook_lesson():
    nb = {"lesson": {"libraries": {"numpy": "1"}}, "steps": [{"id": "s1", "title": "t", "instructions": "", "file": "a.ipynb"}]}
    raw = {"editor": {"needed": True, "why": ""}, "tools": []}
    assert [it["tool"] for it in S._items(raw, nb)][-1] == "ipykernel"
    colab = {**nb, "lesson": {"title": "MNIST in Google Colab"}}
    assert "ipykernel" not in [it["tool"] for it in S._items(raw, colab)]
    assert "ipykernel" not in [it["tool"] for it in S._items({"editor": {"needed": False, "why": ""}, "tools": []}, nb)]


def test_one_venv_build_per_folder_at_a_time(monkeypatch, tmp_path):
    import threading
    import time

    monkeypatch.setattr(S, "best_python", lambda: sys.executable)
    monkeypatch.setattr(S.paths, "lessons_root", lambda: tmp_path)
    wd = tmp_path / "lesson"
    wd.mkdir()
    builds = []

    def popen(argv, **kw):  # a slow build: python appears first, "pip" a moment later
        builds.append(argv)
        (Path(argv[-1]) / "bin").mkdir(parents=True)
        (Path(argv[-1]) / "bin" / "python").write_text("")
        time.sleep(0.3)
        return subprocess.Popen(["true"], stdout=subprocess.PIPE, text=True)

    out = []
    ts = [threading.Thread(target=lambda: out.append(S.ensure_venv(wd, popen=popen))) for _ in range(3)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(builds) == 1 and all(py for py, _ in out)  # the others waited for it, none moved it aside
    assert sorted(p.name for p in wd.iterdir()) == [".venv"]


def test_a_broken_venv_goes_outside_the_lesson_folder(monkeypatch, tmp_path):
    monkeypatch.setattr(S, "best_python", lambda: sys.executable)
    monkeypatch.setattr(S.paths, "lessons_root", lambda: tmp_path)
    wd = tmp_path / "lesson"
    (wd / ".venv" / "bin").mkdir(parents=True)  # no python in it: broken

    def popen(argv, **kw):
        (Path(argv[-1]) / "bin").mkdir(parents=True)
        (Path(argv[-1]) / "bin" / "python").write_text("")
        return subprocess.Popen(["true"], stdout=subprocess.PIPE, text=True)

    py, _ = S.ensure_venv(wd, popen=popen)
    assert py and sorted(p.name for p in wd.iterdir()) == [".venv"]
    assert [p.name.startswith("lesson-") for p in (tmp_path / ".miyagi-state" / "old-venvs").iterdir()] == [True]


def test_lesson_venv_for_a_python_lesson_before_any_step_file(monkeypatch, tmp_path):
    from server.orchestrator import workspace as wsmod

    monkeypatch.setattr(S.paths, "lessons_root", lambda: tmp_path)
    monkeypatch.setattr(S, "best_python", lambda: "/b/python3")
    monkeypatch.setattr(S, "is_bundled", lambda py: py == "/b/python3")
    made = []
    monkeypatch.setattr(S, "ensure_venv", lambda folder, **k: made.append(folder) or ("/x/python", ""))
    monkeypatch.setattr(wsmod, "python_terminal_settings", lambda folder: True)
    wd = tmp_path / "video-lesson"
    wd.mkdir()  # no .py yet: a video lesson's VS Code opens before step 1's file
    assert wsmod.ensure_lesson_venv(wd) is False and not made
    assert wsmod.ensure_lesson_venv(wd, True) is True and made == [wd.resolve()]
    monkeypatch.setattr(S, "is_bundled", lambda py: False)  # the Mac has its own Python: never on open
    assert wsmod.ensure_lesson_venv(wd, True) is False
    assert wsmod.ensure_lesson_venv(tmp_path, True) is False  # the lessons root itself: never

"""A fresh Mac: the only Python is miyagi.app's (MIYAGI_BUNDLED_PYTHON), PATH=/usr/bin:/bin, no Homebrew."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from server.workspace import paths
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
    (target / "keep.txt").write_text("mine", encoding="utf-8")
    wd = tmp_path / "lesson"
    wd.mkdir()
    (wd / ".venv").symlink_to(target)  # a .venv that is a link to someone's folder, with no bin/python
    ran = []

    def popen(argv, **kw):
        ran.append(argv)
        paths.venv_bin(argv[-1]).mkdir(parents=True)
        paths.venv_python(argv[-1]).write_text("", encoding="utf-8")
        return subprocess.Popen(["true"], stdout=subprocess.PIPE, text=True)

    py, err = S.ensure_venv(wd, popen=popen)
    assert py and not err and "--clear" not in ran[0] and ran[0][-1] == str(wd / ".venv")
    assert (target / "keep.txt").read_text(encoding="utf-8") == "mine"  # the link's target is untouched
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
    (tmp_path / "pip.conf").write_text("[global]\nindex-url = http://localhost:3141/simple\n", encoding="utf-8")
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
    # Nov 26 (user test): Claude said "No editor needed" for a video that starts Jupyter in a browser. Miyagi runs every
    # non-Colab notebook lesson in VS Code, so the editor is needed and the kernel row is there anyway.
    items = S._items({"editor": {"needed": False, "why": "Jupyter runs in the browser"}, "tools": []}, nb)
    assert items[0]["kind"] == "editor" and items[0]["needed"] and items[0]["why"] == S.NOTEBOOK_EDITOR_WHY
    assert "ipykernel" in [it["tool"] for it in items]
    assert not S._items({"editor": {"needed": False, "why": "x"}, "tools": []}, colab)[0]["needed"]


def test_notebook_lesson_rows_kernel_first_no_jupyter_server_and_vscode_extensions():
    nb = {"lesson": {"title": "TensorFlow MNIST", "libraries": {"tensorflow": "2"}},
          "steps": [{"id": "s1", "title": "Open mnist.ipynb with the .venv kernel", "instructions": "", "file": "mnist.ipynb"}]}
    raw = {"editor": {"needed": False, "why": "the browser"},
           "tools": [{"tool": "python", "kind": "runtime"}, {"tool": "jupyter", "kind": "python_package"},
                     {"tool": "notebook", "kind": "python_package"}, {"tool": "tensorflow", "kind": "python_package"}]}
    tools = [it["tool"] for it in S._items(raw, nb)]
    # no Jupyter server packages (VS Code runs the cells), the kernel before TensorFlow, VS Code's extensions under it
    assert tools == ["vscode", S.VSCODE_NOTEBOOK, "python", "ipykernel", "tensorflow"]
    raw["tools"].append({"tool": "ipykernel", "kind": "python_package"})
    assert [it["tool"] for it in S._items(raw, nb)].count("ipykernel") == 1
    plain = {"lesson": {"title": "Flask"}, "steps": [{"id": "s1", "title": "t", "instructions": "", "file": "app.py"}]}
    assert S.VSCODE_NOTEBOOK not in [it["tool"] for it in S._items({"editor": {"needed": True, "why": ""}, "tools": []}, plain)]


def _ext_dir(tmp_path, monkeypatch, entries=None, folders=(), obsolete=None):
    d = tmp_path / "exts"
    d.mkdir(exist_ok=True)
    monkeypatch.setenv("VSCODE_EXTENSIONS", str(d))
    if entries is not None:
        (d / "extensions.json").write_text(json.dumps(entries), encoding="utf-8")
    for f in folders:
        (d / f).mkdir()
    if obsolete:
        (d / ".obsolete").write_text(json.dumps(obsolete), encoding="utf-8")
    return d


def test_vscode_extensions_from_the_index_or_folder_names(tmp_path, monkeypatch):
    _ext_dir(tmp_path, monkeypatch, entries=[
        {"identifier": {"id": "ms-python.python"}, "relativeLocation": "ms-python.python-2026.2.0-darwin-arm64"},
        {"identifier": {"id": "ms-toolsai.jupyter"}, "relativeLocation": "ms-toolsai.jupyter-2026.1.0"}],
        obsolete={"ms-toolsai.jupyter-2026.1.0": True})  # uninstalled, not pruned yet
    assert S.vscode_extensions() == {"ms-python.python": True, "ms-toolsai.jupyter": False}
    (tmp_path / "exts" / "extensions.json").unlink()
    (tmp_path / "exts" / ".obsolete").unlink()
    (tmp_path / "exts" / "ms-toolsai.jupyter-2026.1.0").mkdir()
    assert S.vscode_extensions() == {"ms-python.python": False, "ms-toolsai.jupyter": True}
    monkeypatch.setenv("VSCODE_EXTENSIONS", str(tmp_path / "none"))
    assert S.vscode_extensions() == {"ms-python.python": False, "ms-toolsai.jupyter": False}


def test_extension_row_checks_and_installs_only_the_missing_fixed_ids(tmp_path, monkeypatch):
    d = _ext_dir(tmp_path, monkeypatch, folders=("ms-python.python-2026.2.0",))
    row = S.check(dict(S.NOTEBOOK_EXT_ROW))
    assert not row["ok"] and row["missingExtensions"] == ["ms-toolsai.jupyter"]
    r = S.recipe(row, None)
    assert r["method"] == "vscode_ext" and "ms-toolsai.jupyter" in r["command"]
    monkeypatch.setattr(S, "_vscode_cli", lambda: "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code")
    ran = []

    def popen(argv, **kw):  # VS Code's CLI, mocked: it "installs" by making the folder
        ran.append(argv)
        (d / f"{argv[-1]}-1.0.0").mkdir()
        return subprocess.Popen(["true"], stdout=subprocess.PIPE, text=True)

    res = S.install({**row, "install": r}, popen=popen, net=lambda host: True)
    assert res["ok"] and ran == [[ran[0][0], "--install-extension", "ms-toolsai.jupyter"]]
    assert S.check(dict(S.NOTEBOOK_EXT_ROW))["ok"]
    monkeypatch.setattr(S, "_vscode_cli", lambda: None)
    shutil_rm = __import__("shutil").rmtree
    shutil_rm(d / "ms-toolsai.jupyter-1.0.0")
    res = S.install(dict(S.NOTEBOOK_EXT_ROW), popen=popen, net=lambda host: True)
    assert not res["ok"] and res["errorCode"] == "no_vscode" and "VS Code" in res["error"]


def test_kernel_check_says_why_the_notebook_kernel_cant_start(tmp_path):
    wd = tmp_path / "lesson"
    wd.mkdir()
    assert S.kernel_check(wd)["errorCode"] == "no_python"
    py = paths.venv_python(wd / ".venv")
    py.parent.mkdir(parents=True)
    py.write_text("", encoding="utf-8")
    seen = []
    ok = S.kernel_check(wd, run=lambda argv, timeout=0: seen.append(argv) or (0, "7.1.0\n"))
    assert ok == {"ok": True, "version": "7.1.0"} and seen[0][:2] == [str(py), "-c"] and "ipykernel" in seen[0][2]
    bad = S.kernel_check(wd, run=lambda argv, timeout=0: (1, "Traceback...\nModuleNotFoundError: No module named 'ipykernel'"))
    assert not bad["ok"] and bad["errorCode"] == "missing" and "ipykernel isn't installed" in bad["error"]
    slow = S.kernel_check(wd, run=lambda argv, timeout=0: (S.TIMEOUT, ""))
    assert not slow["ok"] and "too long" in slow["error"]
    broken = S.kernel_check(wd, run=lambda argv, timeout=0: (1, "ImportError: dlopen(libzmq.dylib): image not found"))
    assert not broken["ok"] and broken["errorCode"] == "broken_import" and "can't start" in broken["error"]


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
        paths.venv_bin(argv[-1]).mkdir(parents=True)
        paths.venv_python(argv[-1]).write_text("", encoding="utf-8")
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
    paths.venv_bin(wd / ".venv").mkdir(parents=True)  # no python in it: broken

    def popen(argv, **kw):
        paths.venv_bin(argv[-1]).mkdir(parents=True)
        paths.venv_python(argv[-1]).write_text("", encoding="utf-8")
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


def _fake_cli(root, app):
    cli = root / app / "Contents" / "Resources" / "app" / "bin" / "code"
    cli.parent.mkdir(parents=True)
    cli.write_text("#!/bin/sh\n", encoding="utf-8")
    return cli


def test_extensions_go_to_vs_code_never_to_a_cursor_code_shim(tmp_path, monkeypatch):
    # review of #296: Cursor puts its own `code` on PATH; `code --install-extension` then installed into Cursor
    monkeypatch.setitem(S._editor.EDITORS["vscode"], "bundled_cli", str(tmp_path / "none" / "code"))
    cursor = _fake_cli(tmp_path, "Cursor.app")
    shim = tmp_path / "bin" / "code"
    shim.parent.mkdir()
    shim.symlink_to(cursor)
    assert S._vscode_cli(which=lambda n: str(shim), app_path=lambda: None) is None
    vsc = _fake_cli(tmp_path / "Applications", "Visual Studio Code.app")
    app = str(tmp_path / "Applications" / "Visual Studio Code.app")
    assert S._vscode_cli(which=lambda n: str(shim), app_path=lambda: app) == str(vsc)  # the app's own CLI first
    shim.unlink()
    shim.symlink_to(vsc)  # VS Code's own "Install 'code' command in PATH" link
    assert S._vscode_cli(which=lambda n: str(shim), app_path=lambda: None) == str(shim)


def test_only_an_ipynb_file_or_a_jupyter_package_makes_a_vs_code_notebook_lesson():
    text_only = {"lesson": {"title": "pandas basics"},
                 "steps": [{"id": "s1", "title": "t", "instructions": "You could also try this in Jupyter.", "file": "a.py"}]}
    assert not S.vscode_notebook_lesson(text_only)
    assert S.vscode_notebook_lesson({"lesson": {"libraries": {"jupyter": "1"}}, "steps": []})
    nb = {"lesson": {"title": "t"}, "steps": [{"id": "s1", "title": "t", "instructions": "", "file": "a.ipynb"}]}
    assert S.vscode_notebook_lesson(nb)
    for where in ("Kaggle", "Deepnote", "Databricks", "Amazon SageMaker", "JupyterHub", "Google Colab"):
        hosted = {**nb, "lesson": {"title": f"MNIST on {where}"}}
        assert not S.vscode_notebook_lesson(hosted), where
        assert S._items({"editor": {"needed": False, "why": "browser"}, "tools": []}, hosted)[0]["needed"] is False


def test_repair_kernel_force_reinstalls_only_ipykernel_and_pyzmq(tmp_path):
    wd = tmp_path / "lesson"
    py = paths.venv_python(wd / ".venv")
    py.parent.mkdir(parents=True)
    py.write_text("", encoding="utf-8")
    ran = []

    def popen(argv, **kw):
        ran.append(argv)
        return subprocess.Popen(["true"], stdout=subprocess.PIPE, text=True)

    assert S.repair_kernel(wd, popen=popen)["ok"]
    assert ran == [[str(py), "-m", "pip", "install", "--force-reinstall", "ipykernel", "pyzmq"]]
    assert S.repair_kernel(tmp_path / "nothing", popen=popen)["errorCode"] == "no_python"

"""pip into a lesson .venv (user test Nov 25: TensorFlow didn't install on a MacBook Neo). No network, no real pip:
subprocess is faked, except one tiny `sleep` child for the stream deadline."""

from __future__ import annotations

import io
import sys
import threading

import pytest

from server.workspace import paths, pyinstall
from server.workspace import setup as S

# --------------------------------------------------------------------------- plan_package


def test_retired_mac_names_become_plain_tensorflow():
    for old in ("tensorflow-macos", "tensorflow_macos>=2.9", "tensorflow-cpu"):
        p = pyinstall.plan_package(old, py=(3, 12), machine="arm64")
        assert p.package == "tensorflow" and "plain tensorflow" in p.note and not p.error


def test_tensorflow_metal_is_skipped_not_installed():
    p = pyinstall.plan_package("tensorflow-metal", py=(3, 12), machine="arm64")
    assert p.package == "" and p.skip and p.code == "skipped_incompatible" and "2.20" in p.error


@pytest.mark.parametrize("py,machine,ok", [((3, 12), "arm64", True), ((3, 13), "arm64", True), ((3, 10), "arm64", True),
                                           ((3, 14), "arm64", False), ((3, 13), "x86_64", False), ((3, 12), "x86_64", True)])
def test_tensorflow_python_versions(py, machine, ok):
    p = pyinstall.plan_package("tensorflow", py=py, machine=machine)
    assert bool(p.package) is ok
    if not ok:
        assert p.code == "python_version" and f"Python {py[0]}.{py[1]}" in p.error
    assert p.heavy_mb >= 200


def test_other_packages_pass_through():
    p = pyinstall.plan_package("numpy>=1.26", py=(3, 14), machine="arm64")
    assert p.package == "numpy>=1.26" and not p.error and p.heavy_mb == 0


def test_best_python_skips_a_python_tensorflow_cannot_use(monkeypatch):
    found = {"python3.14": "/opt/homebrew/bin/python3.14", "python3.11": "/opt/homebrew/bin/python3.11"}
    monkeypatch.setattr(S.shutil, "which", lambda n: found.get(n))
    monkeypatch.setattr(S, "bundled_python", lambda: None)
    monkeypatch.setattr(S, "_xcode_stub", lambda p: False)
    monkeypatch.setattr(S, "PYTHON_PREFERENCE", (14, 11))
    tf = lambda v: pyinstall.python_ok("tensorflow", v, "arm64")  # noqa: E731
    assert S.best_python(tf) == "/opt/homebrew/bin/python3.11"


# --------------------------------------------------------------------------- progress + failures


def test_progress_reads_pip_raw_and_download_lines():
    pr = pyinstall.Progress()
    assert pr.feed("Collecting tensorflow")
    assert pr.payload() == {"phase": "resolving", "package": "tensorflow"}
    assert pr.feed("  Downloading tensorflow-2.21.0-cp312-cp312-macosx_12_0_arm64.whl (223.9 MB)")
    assert pr.payload()["totalBytes"] == 223_900_000
    assert pr.feed("Progress 111950000 of 223900000")
    assert pr.payload()["pct"] == 50
    assert not pr.feed("Progress 111950000 of 223900000")  # nothing new
    assert pr.feed("Installing collected packages: tensorflow")
    assert pr.payload() == {"phase": "installing", "package": "tensorflow"}


def test_pip_raw_needs_24_1():
    assert pyinstall.pip_version_ok_for_raw("pip 26.2.2 from /x (python 3.12)")
    assert pyinstall.pip_version_ok_for_raw("pip 24.1 from /x")
    assert not pyinstall.pip_version_ok_for_raw("pip 23.3.1 from /x")
    assert not pyinstall.pip_version_ok_for_raw("")


@pytest.mark.parametrize("text,code", [
    ("pip._vendor.urllib3.exceptions.ReadTimeoutError: HTTPSConnectionPool(host='files.pythonhosted.org'): Read timed out.", "timeout"),
    ("ERROR: Could not install packages due to an OSError: [Errno 28] No space left on device", "disk_full"),
    ("ERROR: No matching distribution found for tensorflow", "no_wheel"),
    ("Failed to establish a new connection: [Errno 8] nodename nor servname provided", "network"),
    ("ERROR: ResolutionImpossible: for help visit", "conflict"),
    ("something odd", "unknown"),
])
def test_classify(text, code):
    assert pyinstall.classify(text) == code


def test_explain_failure_is_plain_words():
    code, msg = pyinstall.explain_failure("ERROR: No matching distribution found for tensorflow", package="tensorflow",
                                          py=(3, 14), machine="arm64")
    assert code == "no_wheel" and "Python 3.14" in msg and "3.9 to 3.13" in msg and "ERROR" not in msg
    code, msg = pyinstall.explain_failure("x", package="tensorflow", exit_code=124)
    assert code == "timeout" and "Retry" in msg
    code, msg = pyinstall.explain_failure("Read timed out.", package="tensorflow", attempts=3)
    assert code == "timeout" and "tried 3 times" in msg
    assert "uninstall tensorflow-metal" in pyinstall.broken_import_hint(
        "installed but fails to import: NotFoundError: dlopen(.../tensorflow-plugins/libmetal_plugin.dylib)")


# --------------------------------------------------------------------------- install() with a fake pip


class ScriptedPopen:
    """Each pip run takes the next script entry: (output, exit code)."""
    script: list[tuple[str, int]] = []
    calls: list[list[str]] = []

    def __init__(self, argv, **kw):
        ScriptedPopen.calls.append(argv)
        out, self._code = ScriptedPopen.script.pop(0) if ScriptedPopen.script else ("", 0)
        self.stdout = io.StringIO(out)

    def wait(self, timeout=None):
        return self._code

    def kill(self):
        pass


@pytest.fixture
def lesson(tmp_path, monkeypatch):
    wd = tmp_path / "lesson"
    vpy = paths.venv_python(wd / ".venv")
    vpy.parent.mkdir(parents=True)
    vpy.write_text("", encoding="utf-8")  # an existing .venv: ensure_venv uses it
    monkeypatch.setattr(S, "PIP_RETRY_WAIT_S", (0.0, 0.0))
    ScriptedPopen.calls, ScriptedPopen.script = [], []
    return wd


def fake_run(pyver="3 12 arm64", pip="pip 26.2.2 from /x (python 3.12)", probe=None):
    def run(argv):
        if "-c" in argv and "platform.machine()" in argv[-1]:
            return 0, pyver + "\n"
        if argv[1:4] == ["-m", "pip", "--version"]:
            return 0, pip
        return 0, probe if probe is not None else '{"i": 0, "ok": true, "mod": "tensorflow", "ver": "2.21.0"}\n'
    return run


TF = {"tool": "tensorflow", "kind": "python_package", "label": "TensorFlow", "needed": True, "min_version": "",
      "pip_name": "tensorflow"}
STALL = "Collecting tensorflow\n  Downloading tensorflow-2.21.0-cp312-cp312-macosx_12_0_arm64.whl (223.9 MB)\n" \
        "Progress 10000000 of 223900000\nReadTimeoutError: HTTPSConnectionPool(host='files.pythonhosted.org'): Read timed out.\n"
OK = "Collecting tensorflow\n  Downloading tensorflow-2.21.0-cp312-cp312-macosx_12_0_arm64.whl (223.9 MB)\n" \
     "Progress 223900000 of 223900000\nInstalling collected packages: tensorflow\nSuccessfully installed tensorflow-2.21.0\n"


def test_a_stalled_download_is_retried_with_progress(lesson):
    ScriptedPopen.script = [(STALL, 1), (OK, 0)]
    prog, lines = [], []
    res = S.install(dict(TF), workdir=lesson, popen=ScriptedPopen, net=lambda h: True, run=fake_run(),
                    on_progress=prog.append, on_line=lines.append)
    assert res["ok"] and res["attempts"] == 2 and res["version"] == "2.21.0" and res["verified"]
    pip_runs = [c for c in ScriptedPopen.calls if "install" in c]
    assert len(pip_runs) == 2 and pip_runs[0][pip_runs[0].index("--progress-bar") + 1] == "raw"
    assert pip_runs[0][pip_runs[0].index("--timeout") + 1] == "120"  # heavy: a longer read stall
    assert any(p.get("pct") == 100 for p in prog) and any(p.get("phase") == "retrying" for p in prog)
    assert not any(ln.startswith("Progress ") for ln in lines)  # raw progress feeds the bar, not the log


def test_retries_give_up_with_a_clear_message_and_the_log(lesson):
    ScriptedPopen.script = [(STALL, 1)] * 3
    res = S.install(dict(TF), workdir=lesson, popen=ScriptedPopen, net=lambda h: True, run=fake_run())
    assert not res["ok"] and res["errorCode"] == "timeout" and res["attempts"] == 3
    assert "tried 3 times" in res["error"] and "Read timed out" in res["log"]


def test_no_wheel_is_not_retried(lesson):
    ScriptedPopen.script = [("ERROR: No matching distribution found for tensorflow\n", 1)]
    res = S.install(dict(TF), workdir=lesson, popen=ScriptedPopen, net=lambda h: True, run=fake_run(pyver="3 13 x86_64"))
    # x86_64 + 3.13: refused before pip even runs
    assert res["errorCode"] == "python_version" and not [c for c in ScriptedPopen.calls if "install" in c]
    ScriptedPopen.script = [("ERROR: No matching distribution found for tensorflow\n", 1)]
    res = S.install(dict(TF), workdir=lesson, popen=ScriptedPopen, net=lambda h: True, run=fake_run())
    assert res["errorCode"] == "no_wheel" and res["attempts"] == 1


def test_tensorflow_into_a_python_314_venv_is_refused_before_the_download(lesson):
    res = S.install(dict(TF), workdir=lesson, popen=ScriptedPopen, net=lambda h: True, run=fake_run(pyver="3 14 arm64"))
    assert not res["ok"] and res["errorCode"] == "python_version" and "3.14" in res["error"]
    assert ScriptedPopen.calls == []


def test_tensorflow_metal_is_skipped_ok(lesson):
    item = {**TF, "tool": "tensorflow-metal", "pip_name": "tensorflow-metal", "label": "tensorflow-metal"}
    res = S.install(item, workdir=lesson, popen=ScriptedPopen, net=lambda h: True, run=fake_run())
    assert res["ok"] and res["skipped"] and ScriptedPopen.calls == []


def test_a_slow_first_import_is_not_a_failure(lesson):
    ScriptedPopen.script = [(OK, 0)]
    res = S.install(dict(TF), workdir=lesson, popen=ScriptedPopen, net=lambda h: True, run=fake_run(probe=""))
    assert res["ok"] and res["verified"] is False and "couldn't confirm" in res["note"]


def test_a_broken_import_says_what_to_do(lesson):
    ScriptedPopen.script = [(OK, 0)]
    broken = '{"i": 0, "ok": true, "mod": "tensorflow", "ver": "", "broken": "NotFoundError: dlopen(.../tensorflow-plugins/libmetal_plugin.dylib)"}\n'
    res = S.install(dict(TF), workdir=lesson, popen=ScriptedPopen, net=lambda h: True, run=fake_run(probe=broken))
    assert not res["ok"] and res["errorCode"] == "broken_import" and "uninstall tensorflow-metal" in res["error"]


def test_wifi_off_between_attempts_says_offline(lesson):
    ScriptedPopen.script = [(STALL, 1)]
    seen = iter([True, False])
    res = S.install(dict(TF), workdir=lesson, popen=ScriptedPopen, net=lambda h: next(seen, False), run=fake_run())
    assert res.get("offline") and res["error"] == S.OFFLINE


# --------------------------------------------------------------------------- _stream deadline + cancel


def test_stream_deadline_holds_while_output_is_open():
    import subprocess

    code, txt = S._stream([sys.executable, "-c", "import time; time.sleep(20)"], lambda _l: None, {}, 0.5, subprocess.Popen)
    assert code == 124 and "timed out" in txt


def test_stream_cancel_kills_it():
    import subprocess

    ev = threading.Event()
    threading.Timer(0.3, ev.set).start()
    code, txt = S._stream([sys.executable, "-c", "import time; time.sleep(20)"], lambda _l: None, {}, 30.0,
                          subprocess.Popen, ev)
    assert code == S.CANCELLED_EXIT and "cancelled" in txt

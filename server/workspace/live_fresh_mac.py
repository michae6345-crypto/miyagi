"""Fresh-Mac setup smoke (claude/eng-fresh-mac-setup). Run ON the bundled Python, PATH=/usr/bin:/bin, a temp HOME:

    env -i HOME=<tmp> PATH=/usr/bin:/bin MIYAGI_BUNDLED_PYTHON=<bundle>/bin/python3 TUT_ENV=<empty> \
        <bundle>/bin/python3 -s -B smoke_fresh_mac.py <engine src> <mnist graph json> <requirements cache json> [--install]

Phase A (seconds, no network): Python pick, package probe isolation, local requirements fallback, offline card,
"VS Code not found" card. Phase B (--install, PyPI): every missing row of the cached MNIST lesson installed into a
new lesson .venv made from the bundled Python, then imported from that .venv.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

src, graph_path, cache_path = sys.argv[1:4]
do_install = "--install" in sys.argv
sys.path.insert(0, src)

from server.workspace import editor as E  # noqa: E402
from server.workspace import setup as S  # noqa: E402

ok = True


def check(cond, label):
    global ok
    print(("PASS " if cond else "FAIL ") + label, flush=True)
    ok = ok and bool(cond)


bundled = os.environ["MIYAGI_BUNDLED_PYTHON"]
print("PATH =", os.environ["PATH"], "| HOME =", os.environ["HOME"])
print("python3 on PATH:", shutil.which("python3"), "| python3.12 on PATH:", shutil.which("python3.12"))

# ---- A1: which Python a lesson .venv is built from
check(S.best_python() == bundled, f"best_python() is the bundled Python ({S.best_python()})")
check(S.is_bundled(S.best_python()), "is_bundled(best_python())")

graph = json.loads(Path(graph_path).read_text())
root = Path(os.environ["HOME"]) / "Miyagi" / "lessons"
wd = root / "mnist-smoke"
wd.mkdir(parents=True, exist_ok=True)
os.environ["MIYAGI_LESSONS_DIR"] = str(root)

# ---- A2: no requirements cache, no key -> the lesson's own list (never cached)
S.paths.lessons_root = lambda: root  # the temp HOME's lessons root, whatever env name paths.py reads
items = S.requirements(graph, workdir=wd, client=None) if S.make_client() is None else None
if items is None:
    print("SKIP A2: a model client exists in this env")
else:
    tools = [(it["tool"], it["kind"], it["install"]["method"]) for it in items]
    print("   local list:", tools)
    check(("ipykernel", "python_package", "pip") in tools, "local list: ipykernel row (notebook lesson)")
    check({"tensorflow", "numpy", "matplotlib"} <= {t for t, _, _ in tools}, "local list: lesson.libraries as pip rows")
    check(not any(t == "jupyter" for t, _, _ in tools), "local list: no jupyter metapackage (ipykernel instead)")
    check(not S._cache_file(graph).exists(), "local list is not cached")
    py_row = next(it for it in items if it["tool"] == "python")
    check(py_row["ok"] and py_row["where"] == bundled, f"Python row ok via the bundle ({py_row.get('version')})")
    pkgs = [it for it in items if it["kind"] == "python_package"]
    check(all(it["installed"] is False for it in pkgs), "no package counted from the engine's own site-packages")

# probe isolation, directly: Pillow is in the bundle (engine dep) but must not count for the lesson
probe = [{"tool": "pillow", "kind": "python_package", "pip_name": "pillow", "import_name": "PIL"}]
S.check_python_packages(probe, bundled)
check(probe[0]["installed"] is False, "Pillow (an engine library) is not counted for the lesson")

# ---- A3: the cached lesson (Claude's list for this video) -> same rows plus ipykernel/jupyter
cf = S._cache_file(graph)
cf.parent.mkdir(parents=True, exist_ok=True)
shutil.copy(cache_path, cf)
items = S.requirements(graph, workdir=wd)
print("   cached list:", [(it["tool"], it["kind"], it.get("ok"), it["install"]["method"]) for it in items])
miss = S.missing(items)
check(miss, f"cached list: missing rows {[it['tool'] for it in miss]}")
check(any(it["tool"] in ("jupyter", "ipykernel") for it in miss), "cached list: a kernel row (jupyter / ipykernel)")
card = S.setup_card(items)
print("   setup card:", card["title"], "|", card["body"], "|", card["actions"])

# ---- A4: network off -> calm error, nothing run
calls = []
res = S.install(next(it for it in miss if it["kind"] == "python_package"), workdir=wd,
                popen=lambda *a, **k: calls.append(a) or (_ for _ in ()).throw(AssertionError("ran")),
                net=lambda host: False)
check(res.get("offline") and res["error"] == S.OFFLINE and not calls, f"offline: {res['error']!r}, nothing run")
os.environ["PIP_INDEX_URL"] = "https://pypi.invalid/simple"  # real check, unreachable host
t0 = time.monotonic()
res = S.install(next(it for it in miss if it["kind"] == "python_package"), workdir=wd)
check(res.get("offline") and time.monotonic() - t0 < 10, f"offline (real socket check): {time.monotonic() - t0:.1f}s")
del os.environ["PIP_INDEX_URL"]
check(not (wd / ".venv").exists(), "offline: no half-made .venv")

# ---- A5: VS Code not found (simulated: no editor app, no CLI, no Homebrew)
real = (E.preferred_editor, S.find_app, S.brew_path, S.shutil.which)
E.preferred_editor = lambda installed=None: None
S._editor.preferred_editor = E.preferred_editor
S.find_app = lambda *a, **k: None
S.brew_path = lambda: None
S.shutil.which = lambda name, *a, **k: None if name == "code" else real[3](name, *a, **k)
found = S.editor_missing_card()
check(found is not None, "VS Code missing -> a card")
if found:
    card, item = found
    print("   card:", json.dumps({k: card[k] for k in ("kind", "title", "body", "actions")}))
    rows = card["setup"]["items"]
    sheet = (card["kind"] == "setup" and not card.get("where") and not card["setup"]["resources"]
             and set(card["actions"]) <= {"install", "install_all", "skip_setup"}
             and all(r["kind"] == "editor" and r["needed"] and not r["ok"] for r in rows)
             and all(r["install"]["method"] == "download" and r["install"]["url"] for r in rows))
    check(sheet, "card matches the v2 app's isEditorSheet (download row with url, install/skip only)")
S.brew_path = lambda: "/opt/homebrew/bin/brew"
found = S.editor_missing_card()
check(found and found[1]["install"]["method"] == "brew_cask", "with Homebrew: the row installs the cask")
E.preferred_editor, S.find_app, S.brew_path, S.shutil.which = real
S._editor.preferred_editor = E.preferred_editor
check(S.editor_missing_card() is None, "VS Code installed (this Mac) -> no card")

# ---- B: the real install of the cached lesson's missing rows, into a .venv from the bundled Python
if do_install:
    for it in [x for x in S.missing(S.requirements(graph, workdir=wd)) if x["kind"] == "python_package"]:
        t0 = time.monotonic()
        lines = []
        res = S.install(it, workdir=wd, on_line=lines.append)
        print(f"   install {it['tool']}: ok={res['ok']} v={res.get('version')} {time.monotonic() - t0:.0f}s"
              + ("" if res["ok"] else f" error={res.get('error')!r} last={lines[-3:]}"), flush=True)
        check(res["ok"], f"installed {it['tool']}")
    vpy = wd / ".venv" / "bin" / "python"
    cfg = (wd / ".venv" / "pyvenv.cfg").read_text()
    check(str(Path(bundled).parent) in cfg, ".venv was made from the bundled Python")
    r = subprocess.run([str(vpy), "-c", "import ipykernel, numpy, matplotlib, tensorflow as tf; "
                        "print(ipykernel.__version__, numpy.__version__, tf.__version__)"],
                       capture_output=True, text=True, env={"PATH": "/usr/bin:/bin", "HOME": os.environ["HOME"]})
    print("   .venv imports:", r.stdout.strip(), r.stderr.strip()[-300:])
    check(r.returncode == 0, ".venv imports ipykernel, numpy, matplotlib, tensorflow")
    r = subprocess.run([str(vpy), "-m", "ipykernel_launcher", "--help"], capture_output=True, text=True)
    check(r.returncode == 0, "ipykernel_launcher runs (VS Code's kernel entry point)")
    after = S.requirements(graph, workdir=wd)
    check(not S.missing(after), f"setup check after install: nothing missing ({[it['tool'] for it in S.missing(after)]})")

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)

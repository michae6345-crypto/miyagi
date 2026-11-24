"""Regression tests for the review of the round-2 step-check fixes: false fails the new gate rows added (a never-run
scratch cell, an unrun duplicate cell, a TypeScript ".js" import, a module-level name a function binds with global)
and the cost of two new checks. Each test pairs the case that must pass with one that must still fail. Offline."""
from __future__ import annotations

import struct
import time
from pathlib import Path

from server.checks import evaluator, model_files
from server.checks.code_equiv import broken_imports
from server.checks.notebook import Cell, Notebook
from server.checks.tests.test_round2_fixes import _gate, _nb

PREDICT = {"id": "s6", "run_command": "Run the cell (Shift+Enter)", "code": "p = model.predict(x)",
           "targets": [{"app": "Code", "file": "mnist.ipynb", "match": "model.predict(x)"}],
           "checks": [{"id": "a", "type": "file_contains", "label": "predict typed", "file": "mnist.ipynb",
                       "pattern": r"model\.predict\("}]}

SHAPE = {"id": "s3", "run_command": "Run the cell (Shift+Enter)", "code": "print(df.shape)",
         "targets": [{"app": "Code", "file": "nb.ipynb", "match": "print(df.shape)"}],
         "checks": [{"id": "a", "type": "file_contains", "label": "shape printed", "file": "nb.ipynb",
                     "pattern": r"df\.shape"}]}
SETUP = [{"src": "import pandas as pd", "n": 1}, {"src": "df = pd.read_csv('x.csv')", "n": 2}]


def _predict_cells(*middle, n=4):
    return [{"src": "import tf\nimport matplotlib.pyplot as plt", "n": 1}, {"src": "model = build()", "n": 2},
            *middle, {"src": "p = model.predict(x)\nplt.imshow(x[0])", "n": n, "out": "1/1 ok\n"}]


# -- stale_inputs: a never-run cell above is blamed only for setup nothing that ran gives ----------------------------

def test_a_never_run_cell_that_only_reads_a_name_is_not_missing_setup(tmp_path):
    for scratch in ("model.summary()", "plt.imshow(x[1], cmap='gray')", "print(model)"):
        _nb(tmp_path, _predict_cells({"src": "model.fit(x, y)", "n": 3}, {"src": scratch}), "mnist.ipynb")
        assert _gate(PREDICT, workdir=str(tmp_path))["passed"], scratch
    # the same layout with the training cell never run still fails
    _nb(tmp_path, _predict_cells({"src": "model.fit(x, y)"}, {"src": "model.summary()", "n": 3}), "mnist.ipynb")
    gate = _gate(PREDICT, workdir=str(tmp_path))
    assert not gate["passed"] and "model.fit" in gate["checks"][-1]["detail"]


def test_a_never_run_copy_of_a_setup_cell_that_ran_is_not_missing_setup(tmp_path):
    _nb(tmp_path, SETUP + [{"src": "df = pd.read_csv('x.csv')"}, {"src": "print(df.shape)", "n": 3,
                                                                  "out": "(10, 3)\n"}], "nb.ipynb")
    assert _gate(SHAPE, workdir=str(tmp_path))["passed"]
    _nb(tmp_path, _predict_cells({"src": "model.fit(x, y)", "n": 3}, {"src": "model.fit(x, y, epochs=10)"}),
        "mnist.ipynb")
    assert _gate(PREDICT, workdir=str(tmp_path))["passed"]
    # the only cell that binds df never ran (the step's cell read a df from somewhere else): still blamed
    _nb(tmp_path, [SETUP[0], {"src": "df = pd.read_csv('x.csv')"}, {"src": "print(df.shape)", "n": 2,
                                                                     "out": "(10, 3)\n"}], "nb.ipynb")
    gate = _gate(SHAPE, workdir=str(tmp_path))
    assert not gate["passed"] and "df" in gate["checks"][-1]["detail"]


def test_a_training_cell_from_before_a_restart_is_still_missing_setup(tmp_path):
    fit = "model.compile(opt)\nhistory = model.fit(x, y)"
    _nb(tmp_path, _predict_cells({"src": fit, "n": 19}, n=3), "mnist.ipynb")  # restart, then [1] [2], predict [3]
    gate = _gate(PREDICT, workdir=str(tmp_path))
    assert not gate["passed"] and "model" in gate["checks"][-1]["detail"]
    _nb(tmp_path, _predict_cells({"src": fit}, {"src": "model.summary()", "n": 3}), "mnist.ipynb")  # never run
    assert not _gate(PREDICT, workdir=str(tmp_path))["passed"]
    _nb(tmp_path, _predict_cells({"src": fit, "n": 3}), "mnist.ipynb")
    assert _gate(PREDICT, workdir=str(tmp_path))["passed"]


# -- cell_not_run: an unrun duplicate of the step's cell is not another cell to run ----------------------------------

def test_an_unrun_duplicate_of_the_steps_cell_does_not_block_it(tmp_path):
    ran = {"src": "print(df.shape)", "n": 3, "out": "(10, 3)\n"}
    _nb(tmp_path, SETUP + [ran, {"src": "print(df.shape)"}], "nb.ipynb")
    assert _gate(SHAPE, workdir=str(tmp_path))["passed"]
    _nb(tmp_path, SETUP + [{"src": "print( df.shape )"}, ran], "nb.ipynb")  # an abandoned copy above
    assert _gate(SHAPE, workdir=str(tmp_path))["passed"]
    _nb(tmp_path, SETUP + [{"src": "print(df.shape)"}], "nb.ipynb")  # the only copy never ran
    assert not _gate(SHAPE, workdir=str(tmp_path))["passed"]


# -- code_equiv: TypeScript ESM imports name the .js the .ts compiles to ---------------------------------------------

def test_a_typescript_import_of_dot_js_resolves_to_the_ts_file(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "util.ts").write_text("export function add(a: number, b: number) { return a + b }\n")
    (src / "main.ts").write_text('import { add } from "./util.js"\nconsole.log(add(1, 2))\n')
    assert broken_imports(str(tmp_path), ["src/main.ts"]) == []
    (src / "view.tsx").write_text("export const View = () => null\n")
    (src / "app.tsx").write_text('import { View } from "./view.jsx"\n')
    assert broken_imports(str(tmp_path), ["src/app.tsx"]) == []
    (src / "main.ts").write_text('import { add } from "./utils.js"\n')  # a misspelt module still doesn't exist
    assert broken_imports(str(tmp_path), ["src/main.ts"])
    (src / "main.ts").write_text('import { sum } from "./util.js"\n')  # nor does a name util.ts doesn't export
    assert broken_imports(str(tmp_path), ["src/main.ts"])


# -- code_equiv: a name a function binds with `global` is bound ------------------------------------------------------

def test_a_name_a_function_binds_with_global_is_not_a_missing_import(tmp_path):
    (tmp_path / "stats.py").write_text("total = 0\n")
    (tmp_path / "main.py").write_text("def setup():\n    global total\n    total = 0\n\nsetup()\nprint(total)\n")
    assert broken_imports(str(tmp_path), ["main.py"]) == []
    (tmp_path / "main.py").write_text("def setup():\n    global total\n    print(total)\n\nsetup()\n")
    assert broken_imports(str(tmp_path), ["main.py"])  # declared global but never bound: stats.py's total


# -- cost: the drawn-matrix search and the STL shell check -----------------------------------------------------------

def test_the_drawn_matrix_search_stays_fast_on_a_screen_full_of_number_rows():
    nb = Notebook(path=Path("x.ipynb"), cells=[Cell(source="ConfusionMatrixDisplay(cm).plot()", executed=True,
                                                    images=["image/png"])])
    lines = [f"{i} " + " ".join(str((i * 7 + k * 13) % 97) for k in range(10)) for i in range(200)]
    for pattern in (r"\[\[\s*13\s+0\s+1\]\s*\n?\s*\[\s*1\s+11\s+4\]",
                    r"\[\[\s*13\s+0\s+1\]\s*\n?\s*\[\s*1\s+11\s+4\]\]"):
        start = time.perf_counter()
        assert not evaluator._drawn_matrix(pattern, nb, lines)
        assert time.perf_counter() - start < 1.0
    drawn = ["Confusion matrix", "0 13 0 1", "True label 1 1 11 4", "2 0 2 9", "0 1 2"]
    assert evaluator._drawn_matrix(r"\[\[\s*13\s+0\s+1\]\s*\n?\s*\[\s*1\s+11\s+4\]", nb, drawn)
    assert evaluator._drawn_matrix(r"\[\[\s*13\s+0\s+1\]\s*\n?\s*\[\s*1\s+11\s+4\]\s*\n?\s*\[\s*0\s+2\s+9\]\]",
                                   nb, drawn)
    assert not evaluator._drawn_matrix(r"\[\[\s*13\s+0\s+1\]\s*\n?\s*\[\s*1\s+11\s+5\]", nb, drawn)


def _stl(path, tris):
    data = b"\0" * 80 + struct.pack("<I", len(tris))
    for tri in tris:
        data += struct.pack("<12fH", 0, 0, 0, *[c for p in tri for c in p], 0)
    path.write_bytes(data)


def test_the_stl_shell_check_parses_each_saved_file_once(tmp_path, monkeypatch):
    a, b, c, d = (0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)
    stl = tmp_path / "part.stl"
    _stl(stl, [(a, b, c), (a, b, d), (a, c, d), (b, c, d)])
    calls = []
    real = model_files._stl_triangles
    monkeypatch.setattr(model_files, "_stl_triangles", lambda p: calls.append(p) or real(p))
    assert model_files.open_mesh(str(stl)) is None
    assert model_files.open_mesh(str(stl)) is None
    assert len(calls) == 1
    _stl(stl, [(a, b, c), (a, b, d), (a, c, d)])  # saved again with a face missing: read again
    assert "not watertight" in (model_files.open_mesh(str(stl)) or "")
    assert len(calls) == 2

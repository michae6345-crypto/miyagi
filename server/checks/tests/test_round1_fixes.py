"""Regression tests for the wrong verdicts the round-1 step-check evals found (server/evals/checks, train cases).
One test (or a small group) per general fix. Offline: no model, no network."""
from __future__ import annotations

import json
import re

import pytest

from server.checks import RunContext, blocks, evaluate_gate, extract_metrics
from server.checks.code_equiv import broken_imports, equivalent_view
from server.checks.evaluator import _absent_hit


def _gate(step, **ctx):
    return evaluate_gate(step, RunContext(**ctx))


def _term(*rows):
    return {"Terminal": list(rows)}


# -- terminal history read per command (server.checks.blocks) ----------------------------------------------------------

def test_prompt_rows_split_a_terminal_into_commands_and_their_output():
    bl = blocks.parse(["tripi@mac ~ % git add x.py", "fatal: not a git repository", "tripi@mac ~ % ",
                       "Command: STLOUT", "Select solids: *Cancel*"])
    assert [b.command for b in bl] == ["git add x.py", "", "STLOUT"]
    assert bl[0].failure().startswith("fatal") and bl[2].failure()
    assert blocks.prompt_command("➜  Local:   http://localhost:5173/") is None  # Vite's output, not oh-my-zsh
    assert blocks.prompt_command("hello.md        learning.py     waiting.py") is None


STAGE = {"id": "s4", "checks": [{"id": "c", "type": "screen_contains", "label": "Updated file staged", "app": "Terminal",
                                 "pattern": r"git\s+add\s+learning"}]}


def test_a_command_whose_output_is_an_error_does_not_pass():
    bad = _gate(STAGE, screen=_term("me@mac ~ % git add learning.py",
                                    "fatal: not a git repository (or any of the parent directories): .git",
                                    "me@mac ~ % "))
    ok = _gate(STAGE, screen=_term("me@mac p1 % git add learning.py", "me@mac p1 % git status", "On branch main",
                                   "me@mac p1 % "))
    assert not bad["passed"] and "failed" in bad["checks"][0]["detail"]
    assert ok["passed"]


@pytest.mark.parametrize("rows", [
    ["me@mac p % git push origin x", " ! [rejected]        x -> x (fetch first)",
     "error: failed to push some refs", "me@mac p % "],
    ["me@mac p % git commit -m \"x -> x\"", "nothing added to commit but untracked files present", "me@mac p % "],
    ["me@mac ~ % cd projct1; git init x", "cd: no such file or directory: projct1",
     "Initialized empty Git repository in /Users/me/.git/ x -> x", "me@mac ~ % "],
])
def test_git_refusals_and_a_failed_chain_are_failures(rows):
    step = {"id": "s", "checks": [{"id": "c", "type": "screen_contains", "label": "done", "app": "Terminal",
                                   "pattern": r"x\s*->\s*x"}]}
    assert not _gate(step, screen=_term(*rows))["passed"]


def test_only_the_newest_run_of_a_command_counts():
    step = {"id": "t3", "checks": [{"id": "c", "type": "screen_contains", "label": "Vite build finished",
                                    "app": "Terminal", "pattern": r"built\s+in"},
                                   {"id": "d", "type": "screen_absent", "label": "Build has no errors",
                                    "app": "Terminal", "pattern": "error|ERR!"}]}
    old_ok_new_bad = _term("me@mac shop % npm run build", "✓ built in 812ms", "me@mac shop % npm run build",
                           "src/Cart.tsx:1:10 - error TS2305: Module has no exported member 'formatPrice'.",
                           "Found 1 error.", "me@mac shop %")
    old_bad_new_ok = _term("me@mac shop % npm run build", "src/Cart.tsx:1:10 - error TS2305: no member",
                           "me@mac shop % npm run build", "✓ built in 790ms", "me@mac shop %")
    g = _gate(step, screen=old_ok_new_bad)
    assert not g["passed"] and [r["status"] for r in g["checks"]] == ["fail", "fail"]
    assert _gate(step, screen=old_bad_new_ok)["passed"]


@pytest.mark.parametrize("line,hit", [
    ("1 failed, 2 passed in 0.03s", True),
    ("FAILED test_operations.py::test_divide - assert 2 == 2.5", True),
    ("src/a.tsx:1:10 - error TS2305: Module has no exported member", True),
    ("3 passed, 0 failed", False),
    ("final error rate 0.02", False),
])
def test_test_runner_and_compiler_failures_are_error_forms(line, hit):
    assert bool(_absent_hit("(?i:failed)|error|Error", "ok\n" + line)) is hit


def test_an_error_the_command_got_past_or_a_harmless_repeat_is_not_flagged():
    step = {"id": "s", "checks": [{"id": "c", "type": "screen_absent", "label": "No terminal errors",
                                   "app": "Terminal", "pattern": "Traceback|ERROR:|fatal:"}]}
    pip = _term("(venv) me@mac m % pip3 install numpy", "ERROR: pip's dependency resolver does not currently take "
                "into account all the packages that are installed.", "Successfully installed numpy-2.0.2",
                "(venv) me@mac m % ")
    rebase = _term("me@mac a % git add a.js && git rebase --continue", "Successfully rebased and updated refs/heads/x.",
                   "me@mac a % git rebase --continue", "fatal: No rebase in progress?", "me@mac a % ")
    real = _term("(venv) me@mac m % pip3 install tensorflow", "ERROR: No matching distribution found for tensorflow",
                 "(venv) me@mac m % ")
    assert _gate(step, screen=pip)["passed"]
    assert _gate(step, screen=rebase)["passed"]
    assert not _gate(step, screen=real)["passed"]


BRANCH = {"id": "s7", "targets": [{"app": "Terminal", "match": "git checkout -b update-name"}],
          "checks": [{"id": "c", "type": "screen_contains", "label": "Branch update-name active", "app": "Terminal",
                      "pattern": "update-name"}]}


@pytest.mark.parametrize("rows,passed", [
    (["me@mac g % git branch update-name", "me@mac g % git branch", "* main", "  update-name", "me@mac g % "], False),
    (["me@mac g % git switch -c update-name", "Switched to a new branch 'update-name'", "me@mac g % "], True),
    (["me@mac g % git checkout -b update-name", "Switched to a new branch 'update-name'", "me@mac g % "], True),
])
def test_the_steps_own_terminal_command_must_have_run(rows, passed):
    assert _gate(BRANCH, screen=_term(*rows))["passed"] is passed


def test_file_names_in_an_ls_listing_do_not_stage_a_file():
    step = {"id": "s3", "targets": [{"app": "Terminal", "match": "git add learning.py"}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "Staged learning.py", "app": "Terminal",
                        "pattern": r"learning\s*\.\s*py"}]}
    ls = _term("me@mac p % touch learning.py", "me@mac p % ls", "learning.py", "me@mac p % ")
    assert not _gate(step, screen=ls)["passed"]
    assert blocks.is_command("git add learning.py") and not blocks.is_command("epoch 3900")


def test_the_command_ran_clean_and_its_file_exists_passes_on_other_wording(tmp_path):
    (tmp_path / "project1" / ".git").mkdir(parents=True)
    step = {"id": "s2", "targets": [{"app": "Terminal", "match": "git i"}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "Git repository initialized",
                        "app": "Terminal", "pattern": r"Initialized\s+empty"}],
            "precision_checks": [{"id": "p", "type": "file_exists", "label": ".git", "file": "project1/.git"}]}
    reinit = _term("me@mac project1 % git init", "Reinitialized existing Git repository in /x/project1/.git/",
                   "me@mac project1 % ")
    assert _gate(step, screen=reinit, workdir=str(tmp_path))["passed"]
    assert not _gate(step, screen=reinit, workdir=str(tmp_path / "elsewhere"))["passed"]


def test_a_cancelled_command_line_app_command_does_not_pass():
    step = {"id": "s3", "checks": [{"id": "c", "type": "screen_contains", "label": "STL exported",
                                    "app": "AutoCAD", "pattern": "STLOUT"}]}
    cancelled = {"AutoCAD 2025": ["Command: STLOUT", "Select solids or watertight meshes: *Cancel*", "Command:"]}
    done = {"AutoCAD 2025": ["Command: STLOUT", "Select solids or watertight meshes: 1 found", "Command:"]}
    assert not _gate(step, screen=cancelled)["passed"]
    assert _gate(step, screen=done)["passed"]


# -- notebooks and metrics ---------------------------------------------------------------------------------------------

def _nb(path, cells):
    nb = {"cells": [{"cell_type": "code", "id": f"c{i}", "metadata": {}, "source": c["source"],
                     "execution_count": c.get("count"),
                     "outputs": ([{"output_type": "stream", "name": "stdout", "text": c["stdout"]}]
                                 if c.get("stdout") else [])} for i, c in enumerate(cells)],
          "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    path.write_text(json.dumps(nb), encoding="utf-8")


def test_a_nan_beside_the_checked_metric_fails_the_threshold(tmp_path):
    code = "history = model.fit(x, y, epochs=2)"
    _nb(tmp_path / "mnist.ipynb", [{"source": code, "count": 1, "stdout":
                                    "Epoch 1/2\n1875/1875 - accuracy: 0.9561 - loss: 0.16\n"
                                    "Epoch 2/2\n1875/1875 - accuracy: 0.9563 - loss: nan\n"}])
    step = {"id": "s5", "code": code, "targets": [{"app": "Code", "file": "mnist.ipynb", "match": "model.fit("}],
            "checks": [{"id": "c", "type": "metric_threshold", "label": "Training accuracy reaches 0.95",
                        "metric": "accuracy", "metric_pattern": r"accuracy:\s*(?P<value>\d+\.\d+)", "op": ">=",
                        "value": 0.95}]}
    g = _gate(step, workdir=str(tmp_path))
    assert not g["passed"] and "loss: nan" in g["checks"][0]["detail"]


def test_a_metric_printed_inside_a_tensor_is_read():
    pts = extract_metrics(r"epoch\s+(?P<step>\d+)\s+loss\s+(?P<value>[0-9.eE+-]+)",
                          "epoch 0 loss tensor(0.2614, grad_fn=<MseLossBackward0>)\nepoch 200 loss tensor(0.2488)")
    assert pts == [(0, 0.2614), (200, 0.2488)]


@pytest.mark.parametrize("counts,passed", [([1, 2, 3], True), ([1, 5, 4], False), ([2, 3, 4], False),
                                           ([1, 2, None], False)])
def test_restart_and_run_all_needs_the_run_counts_in_order_from_1(tmp_path, counts, passed):
    _nb(tmp_path / "steps.ipynb", [{"source": f"x{i} = {i}", "count": n} for i, n in enumerate(counts)])
    step = {"id": "j3", "run_command": "Restart the kernel, then run all cells",
            "targets": [{"app": "Code", "file": "steps.ipynb"}],
            "checks": [{"id": "c", "type": "screen_absent", "label": "No cell error", "app": "Code",
                        "pattern": r"Traceback|\w+Error"}]}
    g = _gate(step, workdir=str(tmp_path), screen={"Code": ["steps.ipynb", "[1]"]})
    assert g["passed"] is passed


# -- VS Code: equivalent code, the file a line belongs to, imports that don't resolve ---------------------------------

M2 = {"id": "m2", "kind": "code", "code": "from operations import add\n\nprint(add(2, 3))",
      "targets": [{"app": "Code", "file": "main.py", "match": "from operations import add"}],
      "checks": [{"id": "a", "type": "screen_contains", "label": "main.py imports add from operations", "app": "Code",
                  "pattern": r"from\s+operations\s+import\s+add"},
                 {"id": "b", "type": "screen_contains", "label": "main.py calls add(2, 3)", "app": "Code",
                  "pattern": r"print\(add\(2,\s*3\)\)"}]}
OPS = "def add(a, b):\n    return a + b\n"


@pytest.mark.parametrize("main", ["from operations import add as plus\nprint(plus(2, 3))",
                                  "import operations\nprint(operations.add(2, 3))",
                                  "from operations import (subtract,\n    add)\nprint(add(2, 3))"])
def test_python_import_forms_that_mean_the_same_pass(tmp_path, main):
    (tmp_path / "operations.py").write_text(OPS + "def subtract(a, b):\n    return a - b\n")
    (tmp_path / "main.py").write_text(main + "\n")
    assert _gate(M2, workdir=str(tmp_path), screen={"Code": ["main.py", *main.splitlines()]})["passed"]


@pytest.mark.parametrize("code,pattern", [
    ("import { formatDate, formatPrice } from '../utils'", r"import\s*\{\s*formatPrice\s*\}\s*from\s*['\"]\.\./utils"),
    ("import SiteHeader from './Header.jsx'\nreturn (<SiteHeader/>)", r"import\s+Header"),
    ("import SiteHeader from './Header.jsx'\nreturn (<SiteHeader/>)", r"<Header"),
    ("import * as u from '../utils'\nu.formatPrice(1)", r"import\s*\{\s*formatPrice\s*\}"),
    ("return (<Fragment><Header/></Fragment>)", r"<>"),
    ("return (<React.Fragment><Header/></React.Fragment>)", r"</>"),
])
def test_js_import_and_fragment_forms_that_mean_the_same_are_read(code, pattern):
    view = equivalent_view(code, "App.jsx")
    assert view is not None and re.search(pattern, view)


def test_a_jsx_tag_pattern_is_a_code_check_not_an_output_one():
    step = {"id": "s3", "targets": [{"app": "Code", "file": "src/App.jsx", "match": "<Header/>"}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "Header component rendered", "app": "Code",
                        "pattern": "<Header"}]}
    g = _gate(step, screen={"Code": ["App.jsx", "import SiteHeader from './Header.jsx'", "return (<SiteHeader/>)"]})
    assert g["passed"]


def test_a_line_seen_in_a_split_editor_counts_only_for_its_own_file(tmp_path):
    (tmp_path / "operations.py").write_text(OPS)
    (tmp_path / "main.py").write_text("print(add(2, 3))\n")
    (tmp_path / "test_operations.py").write_text("from operations import add\n\ndef test_add():\n    assert add(2, 3)\n")
    screen = {"Code": ["main.py", "test_operations.py", "print(add(2, 3))", "from operations import add"]}
    g = _gate(M2, workdir=str(tmp_path), screen=screen)
    assert not g["passed"] and "test_operations.py" in g["checks"][0]["detail"]
    (tmp_path / "main.py").write_text("from operations import add\nprint(add(2, 3))\n")
    assert _gate(M2, workdir=str(tmp_path), screen=screen)["passed"]


def test_an_import_of_a_name_the_module_no_longer_defines_fails_the_step(tmp_path):
    (tmp_path / "operations.py").write_text("def add_numbers(a, b):\n    return a + b\n")
    (tmp_path / "main.py").write_text("from operations import add\nprint(add_numbers(2, 3))\n")
    step = {"id": "m4", "targets": [{"app": "Code", "file": "operations.py", "match": "def add(a, b):"}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "main.py calls add_numbers(2, 3)",
                        "app": "Code", "pattern": r"add_numbers\(2,\s*3\)"}]}
    screen = {"Code": ["main.py", "from operations import add", "print(add_numbers(2, 3))"]}
    g = _gate(step, workdir=str(tmp_path), screen=screen)
    assert not g["passed"] and g["checks"][-1]["label"] == "Imports resolve"
    (tmp_path / "main.py").write_text("from operations import add_numbers\nprint(add_numbers(2, 3))\n")
    assert _gate(step, workdir=str(tmp_path), screen=screen)["passed"]


def test_js_default_and_named_imports_are_resolved_against_the_lessons_modules(tmp_path):
    src = tmp_path / "app" / "src"
    src.mkdir(parents=True)
    (src / "Header.jsx").write_text("export function Header() {\n  return <h1>x</h1>\n}\n")
    (src / "utils.ts").write_text("export function formatPrice(c: number) { return '' }\n")
    (src / "App.jsx").write_text("import Header from './Header.jsx'\nimport { formatPrice } from './utils'\n"
                                 "import React from 'react'\n")
    assert broken_imports(tmp_path, ["src/App.jsx"]) == [
        "App.jsx imports a default export from Header.jsx, which has none"]
    (src / "Header.jsx").write_text("function Header() {}\nexport default Header\n")
    (src / "utils.ts").write_text("export const formatCents = 1\n")
    assert broken_imports(tmp_path, ["src/App.jsx"]) == [
        "App.jsx imports formatPrice from utils.ts, which doesn't export it"]


# -- app lessons: menus on screen, scene dumps, exports, drawings -----------------------------------------------------

ADD_MENU = ["Object Mode View Select Add Object", "Add", "Mesh", "Curve", "Surface", "Light", "Light Probe", "Camera",
            "Point", "Sun", "Spot", "Area", "Scene Collection", "Collection", "Camera", "Light", "Mug"]
AREA = {"id": "s9", "checks": [{"id": "c", "type": "screen_contains", "label": "Area light added", "app": "Blender",
                                "pattern": "Area"}]}


def test_a_word_seen_only_as_an_open_menus_item_is_not_added():
    assert not _gate(AREA, screen={"Blender": ADD_MENU})["passed"]
    added = ["Object Mode View Select Add Object", "Scene Collection", "Collection", "Camera", "Light", "Mug", "Area",
             "Power 500 W"]
    assert _gate(AREA, screen={"Blender": added})["passed"]
    panel = ["Add Modifier", "Subdivision", "Catmull-Clark", "Simple", "Levels Viewport 2", "Render 2"]
    sub = {"id": "s3", "checks": [{"id": "c", "type": "screen_contains", "label": "Modifier added", "app": "Blender",
                                   "pattern": "Subdivision"}]}
    assert _gate(sub, screen={"Blender": panel})["passed"]


def _scene(tmp_path, objects, materials=()):
    (tmp_path / "mug.scene.json").write_text(json.dumps({"file": "mug.blend", "objects": objects,
                                                         "materials": list(materials)}, indent=1))


SUBSURF = {"id": "s5", "title": "Subdivision and smooth shading",
           "instructions": "Select the mug, add a Subdivision Surface modifier (Ctrl+2), then Shade Smooth.",
           "checks": [{"id": "c", "type": "file_contains", "label": "Subdivision modifier added",
                       "file": "mug.scene.json", "pattern": r"\"type\":\s*\"SUBSURF\""}]}
MOD = [{"name": "Subdivision", "type": "SUBSURF", "levels": 2}]


def test_a_scene_fact_counts_only_on_the_object_the_step_names(tmp_path):
    _scene(tmp_path, [{"name": "Cube", "modifiers": MOD}, {"name": "Mug", "modifiers": []}])
    assert not _gate(SUBSURF, workdir=str(tmp_path))["passed"]
    _scene(tmp_path, [{"name": "Cube", "modifiers": []}, {"name": "Mug", "modifiers": MOD}])
    assert _gate(SUBSURF, workdir=str(tmp_path))["passed"]


def test_a_material_counts_for_what_it_is_attached_to_not_for_a_word_of_the_instructions(tmp_path):
    step = {"id": "s8", "instructions": "With the mug selected, click New and set Roughness below 0.3 for a glossy "
                                        "ceramic look.",
            "checks": [{"id": "c", "type": "file_contains", "label": "Roughness under 0.3", "file": "mug.scene.json",
                        "pattern": r"\"roughness\":\s*0\.[0-2]\d*"}]}
    objs = [{"name": "Cube", "materials": ["Ceramic"]}, {"name": "Mug", "materials": ["Material"]}]
    _scene(tmp_path, objs, [{"name": "Material", "users": ["Mug"], "roughness": 0.5},
                            {"name": "Ceramic", "users": ["Cube"], "roughness": 0.2}])
    assert not _gate(step, workdir=str(tmp_path))["passed"]
    _scene(tmp_path, objs, [{"name": "Ceramic", "users": ["Mug"], "roughness": 0.2}])
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_float_noise_in_a_saved_value_is_that_value(tmp_path):
    _scene(tmp_path, [{"name": "Cone", "rotation_deg": [90.00000250447816, 0.0, 0.0]}])
    step = {"id": "s6", "instructions": "turn the cone 90 degrees around X",
            "checks": [{"id": "c", "type": "file_contains", "label": "Cone turned 90 degrees", "file": "mug.scene.json",
                        "pattern": r"\"rotation_deg\":\s*\[\s*90(?:\.0+)?\s*[,\]]"}]}
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_every_means_every_instance_of_the_key(tmp_path):
    feats = [{"name": "Sketch", "valid": True}, {"name": "Pad", "valid": True}, {"name": "Pocket", "valid": False}]
    (tmp_path / "plate.scene.json").write_text(json.dumps({"bodies": [{"name": "Body", "features": feats}]}, indent=1))
    step = {"id": "s9", "instructions": "fix any feature that turns red",
            "checks": [{"id": "c", "type": "file_contains", "label": "Every feature rebuilds",
                        "file": "plate.scene.json", "pattern": r"\"valid\":\s*true"}]}
    g = _gate(step, workdir=str(tmp_path))
    assert not g["passed"] and "false" in g["checks"][0]["detail"]
    feats[2]["valid"] = True
    (tmp_path / "plate.scene.json").write_text(json.dumps({"bodies": [{"name": "Body", "features": feats}]}, indent=1))
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_an_stl_export_with_no_triangles_is_not_saved(tmp_path):
    step = {"id": "s10", "instructions": "save it as hook.stl",
            "checks": [{"id": "a", "type": "file_exists", "label": "hook.stl saved", "file": "hook.stl"},
                       {"id": "b", "type": "file_contains", "label": "STL mesh", "file": "hook.stl",
                        "pattern": r"^solid\b"}]}
    (tmp_path / "hook.stl").write_text("solid Mesh\nendsolid Mesh\n")
    assert [r["status"] for r in _gate(step, workdir=str(tmp_path))["checks"]] == ["fail", "fail"]
    (tmp_path / "hook.stl").write_text("solid Mesh\nfacet normal 0 0 1\nouter loop\nendloop\nendfacet\nendsolid Mesh\n")
    assert _gate(step, workdir=str(tmp_path))["passed"]


DXF_DIM = "0\nSECTION\n2\nENTITIES\n0\nDIMENSION\n8\nDIMS\n1\n{text}\n42\n{measured}\n0\nENDSEC\n0\nEOF\n"


def test_a_number_typed_over_a_dxf_dimension_is_not_its_measurement(tmp_path):
    step = {"id": "s5", "instructions": "The body should measure 120 mm.",
            "checks": [{"id": "c", "type": "file_contains", "label": "Body is 120 mm long", "file": "car.dxf",
                        "pattern": r"\b120(?:\.0+)?\b"}]}
    (tmp_path / "car.dxf").write_text(DXF_DIM.format(text="120", measured="118.5"))
    assert not _gate(step, workdir=str(tmp_path))["passed"]
    (tmp_path / "car.dxf").write_text(DXF_DIM.format(text="<>", measured="120.0"))
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_a_file_the_step_never_named_may_have_any_name(tmp_path):
    step = {"id": "s10", "instructions": "Render with F12, then Image > Save As a PNG next to mug.blend.",
            "checks": [{"id": "c", "type": "file_exists", "label": "PNG render saved", "file": "mug.png"}]}
    assert not _gate(step, workdir=str(tmp_path))["passed"]
    (tmp_path / "untitled.png").write_bytes(b"PNG")
    assert _gate(step, workdir=str(tmp_path))["passed"]
    named = {**step, "instructions": "Save the render as mug.png next to mug.blend."}
    assert not _gate(named, workdir=str(tmp_path))["passed"]

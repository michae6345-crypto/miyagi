"""Regression tests for the wrong verdicts the round-3 step-check evals found (server/evals/checks, train cases).
One test per general fix. Offline: no model, no network."""
from __future__ import annotations

import json

from server.checks import RunContext, blocks, evaluate_gate
from server.checks.code_equiv import broken_imports, equivalent_view
from server.checks.evaluator import _alias_pattern


def _gate(step, **ctx):
    return evaluate_gate(step, RunContext(**ctx))


def _term(*rows):
    return {"Terminal": list(rows)}


def _dump(tmp_path, name, doc):
    (tmp_path / name).write_text(json.dumps(doc, indent=1))


def _obj(name, **kw):
    return {"name": name, "type": "MESH", "location": [0.0, 0.0, 0.0], "rotation_deg": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0], "dimensions": [2.0, 2.0, 2.0], **kw}


def _nb(tmp_path, cells, name="mnist.ipynb"):
    out = []
    for c in cells:
        outs = []
        if c.get("out"):
            outs.append({"output_type": "stream", "name": "stdout", "text": c["out"]})
        if c.get("err"):
            outs.append({"output_type": "error", "ename": c["err"], "evalue": c.get("evalue", ""), "traceback": []})
        out.append({"cell_type": "code", "metadata": {}, "source": c["src"], "outputs": outs,
                    "execution_count": c.get("n")})
    (tmp_path / name).write_text(json.dumps({"cells": out, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}))


def _cell_step(code, match, checks, file="mnist.ipynb", **kw):
    return {"id": "s", "run_command": "Run the cell (Shift+Enter)", "code": code,
            "targets": [{"app": "Code", "file": file, "match": match}], "checks": checks, **kw}


TYPED = [{"id": "c", "type": "file_contains", "label": "typed", "file": "mnist.ipynb", "pattern": r"\w"}]


# -- Jupyter: what the kernel holds -----------------------------------------------------------------------------------

def test_a_cell_that_rewrites_its_input_run_again_without_the_cell_that_makes_it(tmp_path):
    step = _cell_step("x = x.astype('float32') / 255", "x.astype('float32') / 255", TYPED)
    cells = [{"src": "x = load()", "n": 1}, {"src": "x = x.astype('float32') / 255\nprint(x.max())", "n": 4,
                                              "out": "1.53787e-05\n"}]
    _nb(tmp_path, cells)
    gate = _gate(step, workdir=str(tmp_path))
    assert not gate["passed"] and "3 times" in gate["checks"][-1]["detail"]
    cells[0]["n"], cells[1]["n"] = 3, 4  # the load ran again first: the cell divided once
    _nb(tmp_path, cells)
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_the_cell_that_made_a_name_re_run_after_the_cell_that_changed_it(tmp_path):
    step = _cell_step("p = model.predict(x)", "model.predict(x)", TYPED)
    cells = [{"src": "x = load()", "n": 1}, {"src": "model = build()", "n": 5}, {"src": "model.fit(x, y)", "n": 4},
             {"src": "p = model.predict(x)", "n": 6, "out": "1/1 ok\n"}]
    _nb(tmp_path, cells)
    gate = _gate(step, workdir=str(tmp_path))
    assert not gate["passed"] and "model" in gate["checks"][-1]["detail"]
    cells[1]["n"], cells[2]["n"] = 2, 4
    _nb(tmp_path, cells)
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_run_all_with_an_error_in_a_cell_scrolled_off_screen(tmp_path):
    step = {"id": "r", "run_command": "Restart the kernel, then run all cells", "file": "steps.ipynb",
            "checks": [{"id": "a", "type": "screen_absent", "label": "No error", "app": "Code",
                        "pattern": r"Traceback|\w+Error"}]}
    cells = [{"src": "steps = [1, 2]", "n": 1}, {"src": "plt.bar(steps)", "n": 2, "err": "NameError",
                                                  "evalue": "name 'plt' is not defined"}]
    _nb(tmp_path, cells, "steps.ipynb")
    screen = {"Code": ["steps.ipynb", "[1]", "steps = [1, 2]"]}
    gate = _gate(step, workdir=str(tmp_path), screen=screen)
    assert not gate["passed"] and "NameError" in gate["checks"][-1]["detail"]
    cells[1].pop("err")
    _nb(tmp_path, cells, "steps.ipynb")
    assert _gate(step, workdir=str(tmp_path), screen=screen)["passed"]


def test_a_cell_the_editor_shows_with_a_run_count_ran_though_the_file_is_unsaved(tmp_path):
    step = _cell_step("history = model.fit(x, y)", "model.fit(", TYPED)
    _nb(tmp_path, [{"src": "model = build()", "n": 1}, {"src": "history = model.fit(x, y)"}])
    assert not _gate(step, workdir=str(tmp_path), screen={"Code": ["mnist.ipynb", "history = model.fit(x, y)"]})["passed"]
    shown = {"Code": ["mnist.ipynb ●", "[2]", "history = model.fit(x, y)", "Epoch 1/1"]}
    assert _gate(step, workdir=str(tmp_path), screen=shown)["passed"]


# -- metrics ------------------------------------------------------------------------------------------------------------

ACC = [{"id": "a", "type": "metric_threshold", "label": "Accuracy reaches 0.95", "metric": "accuracy",
        "metric_pattern": r"accuracy:\s*(?P<value>\d+\.\d+)", "op": ">=", "value": 0.95}]


def test_keras_short_metric_name_reads_as_the_long_one(tmp_path):
    assert _alias_pattern(r"accuracy:\s*(?P<value>\d+\.\d+)") == r"acc(?:uracy)?:\s*(?P<value>\d+\.\d+)"
    step = _cell_step("history = model.fit(x, y, epochs=2)", "model.fit(", ACC)
    _nb(tmp_path, [{"src": step["code"], "n": 1, "out": "Epoch 1/2\n - acc: 0.91\nEpoch 2/2\n - acc: 0.9858\n"}])
    assert _gate(step, workdir=str(tmp_path))["passed"]
    _nb(tmp_path, [{"src": step["code"], "n": 1, "out": "Epoch 1/2\n - acc: 0.81\nEpoch 2/2\n - acc: 0.88\n"}])
    assert not _gate(step, workdir=str(tmp_path))["passed"]


def test_only_the_newest_cell_that_printed_the_metric_is_the_model_now(tmp_path):
    step = _cell_step("history = model.fit(x, y, epochs=2)", "model.fit(", ACC)
    bad = "Epoch 1/2\n - accuracy: 0.10 - loss: 1854.3\nEpoch 2/2\n - accuracy: 0.09 - loss: nan\n"
    good = "Epoch 1/2\n - accuracy: 0.87 - loss: 0.42\nEpoch 2/2\n - accuracy: 0.9858 - loss: 0.04\n"
    cells = [{"src": "history = model.fit(x, y, epochs=2)", "n": 1, "out": bad},
             {"src": "model = build()\nhistory = model.fit(x, y, epochs=2)", "n": 2, "out": good}]
    _nb(tmp_path, cells)
    assert _gate(step, workdir=str(tmp_path))["passed"]
    cells[0]["n"], cells[1]["n"] = 3, 2  # the NaN run is the newer one
    _nb(tmp_path, cells)
    assert not _gate(step, workdir=str(tmp_path))["passed"]


def test_a_printed_history_value_is_the_metric_when_the_fit_prints_no_epochs(tmp_path):
    code = "history = model.fit(x, y, epochs=5, verbose=0)\nprint(history.history['accuracy'][-1])"
    step = _cell_step(code, "model.fit(", ACC)
    _nb(tmp_path, [{"src": code, "n": 1, "out": "0.9858000040054321\n"}])
    assert _gate(step, workdir=str(tmp_path))["passed"]
    _nb(tmp_path, [{"src": code, "n": 1, "out": "0.8100000023841858\n"}])
    assert not _gate(step, workdir=str(tmp_path))["passed"]


def test_an_accuracy_above_100_is_a_count_not_a_fraction(tmp_path):
    check = [{"id": "a", "type": "metric_threshold", "label": "val acc above 0.9", "metric": "val_acc",
              "metric_pattern": r"epoch\s+(?P<step>\d+)\s+val\s+acc\s+(?P<value>[0-9.]+)", "op": ">", "value": 0.9}]
    step = _cell_step("for xb, yb in val_loader:\n    pass", "for xb, yb in val_loader:", check, file="p.ipynb")
    _nb(tmp_path, [{"src": step["code"], "n": 1, "out": "epoch 0 val acc 98.0\nepoch 1 val acc 121.0\n"}], "p.ipynb")
    gate = _gate(step, workdir=str(tmp_path))
    assert not gate["passed"] and "count" in gate["checks"][0]["detail"]
    _nb(tmp_path, [{"src": step["code"], "n": 1, "out": "epoch 0 val acc 0.85\nepoch 1 val acc 0.93\n"}], "p.ipynb")
    assert _gate(step, workdir=str(tmp_path))["passed"]
    _nb(tmp_path, [{"src": step["code"], "n": 1, "out": "epoch 0 val acc 85.0\nepoch 1 val acc 93.5\n"}], "p.ipynb")
    assert _gate(step, workdir=str(tmp_path))["passed"]  # a percentage


# -- terminal: what a command did ---------------------------------------------------------------------------------------

def test_a_command_left_at_a_continuation_prompt_never_ran():
    bl = blocks.parse(["me@mac p % git commit -m \"add waiting file", "dquote> "])
    assert bl[0].failure() is not None
    step = {"id": "s5", "targets": [{"app": "Terminal", "match": "git commit -m"}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "Commit recorded", "app": "Terminal",
                        "pattern": r"add\s+waiting\s+file"}]}
    assert not _gate(step, screen=_term("me@mac p % git commit -m \"add waiting file", "dquote> "))["passed"]
    assert _gate(step, screen=_term("me@mac p % git commit -m \"add waiting file\"",
                                    "[main 1a2b3c4] add waiting file", "me@mac p % "))["passed"]


def test_git_config_with_a_key_and_no_value_sets_nothing():
    assert blocks.config_read("git config --global user.name")
    assert not blocks.config_read("git config --global user.name 'Ada'")
    assert not blocks.config_read("git config --list")
    step = {"id": "s1", "targets": [{"app": "Terminal", "match": "git config --global"}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "User name set", "app": "Terminal",
                        "pattern": r"user\s*\.\s*name"}]}
    assert not _gate(step, screen=_term("me@mac ~ % git config --global user.name", "me@mac ~ % "))["passed"]
    assert _gate(step, screen=_term("me@mac ~ % git config --global user.name \"Ada\"",
                                    "me@mac ~ % git config --list", "user.name=Ada", "me@mac ~ % "))["passed"]


def test_a_dry_run_does_not_do_the_step():
    assert blocks.dry_run("git push --dry-run origin x") and blocks.dry_run("git push -n origin x")
    assert not blocks.dry_run("git push origin x") and not blocks.dry_run("git commit -n -m x")
    step = {"id": "s8", "targets": [{"app": "Terminal", "match": "git push origin update-name"}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "Branch pushed", "app": "Terminal",
                        "pattern": r"update-name\s*->\s*update-name"}]}
    out = " * [new branch]      update-name -> update-name"
    assert not _gate(step, screen=_term("me@mac g % git push --dry-run origin update-name", out, "me@mac g % "))["passed"]
    assert _gate(step, screen=_term("me@mac g % git push origin update-name", out, "me@mac g % "))["passed"]


def test_a_commit_made_before_switching_to_the_steps_new_branch():
    step = {"id": "s4", "instructions": "Make add-waffles with git switch -c add-waffles, then commit waffles.md.",
            "run_command": "git switch -c add-waffles",
            "targets": [{"app": "Terminal", "match": "git switch -c add-waffles"}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "Committed", "app": "Terminal",
                        "pattern": r"\]\s+Add\s+waffles"}]}
    commit = ["me@mac c % git commit -m \"Add waffles\"", "[{b} 5d6e7f8] Add waffles"]
    switch = ["me@mac c % git switch -c add-waffles", "Switched to a new branch 'add-waffles'"]
    rows = [commit[0], commit[1].format(b="main"), *switch, "me@mac c % "]
    gate = _gate(step, screen=_term(*rows))
    assert not gate["passed"] and "main" in gate["checks"][0]["detail"]
    assert _gate(step, screen=_term(*switch, commit[0], commit[1].format(b="add-waffles"), "me@mac c % "))["passed"]


def test_skipped_tests_are_not_every_test_passing():
    assert blocks.skipped_tests(["Tests:       2 skipped, 1 passed, 3 total"]) == 2
    assert blocks.skipped_tests(["===== 3 passed in 0.1s ====="]) == 0
    step = {"id": "t4", "instructions": "Run npm test. Every test should pass.", "run_command": "npm test",
            "targets": [{"app": "Terminal", "match": "npm test"}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "Tests pass", "app": "Terminal",
                        "pattern": r"\d+\s+passed"}]}
    skipped = ("me@mac s % npm test", "PASS src/a.test.ts", "Tests:       2 skipped, 1 passed, 3 total", "me@mac s % ")
    assert not _gate(step, screen=_term(*skipped))["passed"]
    assert _gate(step, screen=_term("me@mac s % npm test", "Tests:       3 passed, 3 total", "me@mac s % "))["passed"]


def test_a_rebasing_pull_is_a_pull_that_brought_changes_in():
    step = {"id": "s9", "targets": [{"app": "Terminal", "match": "git pull"}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "Pulled changes", "app": "Terminal",
                        "pattern": r"Fast-forward|insertion"}]}
    rebased = ("me@mac g % git pull", "   2b7e9f0..9f8e7d6  main       -> origin/main",
               "Successfully rebased and updated refs/heads/main.", "me@mac g % ")
    assert _gate(step, screen=_term(*rebased))["passed"]
    assert not _gate(step, screen=_term("me@mac g % git pull", "Already up to date.", "me@mac g % "))["passed"]


def test_a_failure_from_before_the_repository_was_set_up_is_history():
    rows = ["me@mac a % git init -b main", "Initialized empty Git repository in /tmp/a/.git/",
            "me@mac a % git log", "fatal: your current branch 'main' does not have any commits yet"]
    done = ["me@mac a % git commit -m \"first\"", "[main (root-commit) 1b2c3d4] first", "me@mac a % "]
    step = {"id": "s1", "instructions": "Run git init -b main, commit, and check the log.",
            "targets": [{"app": "Terminal", "match": "git log"}],
            "checks": [{"id": "a", "type": "screen_absent", "label": "No Git errors", "app": "Terminal",
                        "pattern": r"fatal:|error:"}]}
    assert not _gate(step, screen=_term(*rows, "me@mac a % "))["passed"]
    assert _gate(step, screen=_term(*rows, *done))["passed"]
    assert blocks.cured(blocks.parse([*rows, *done]), 1)


# -- code files ---------------------------------------------------------------------------------------------------------

def test_an_old_def_below_an_import_replaces_the_imported_name(tmp_path):
    (tmp_path / "operations.py").write_text("def add(a, b):\n    return a + b\n")
    (tmp_path / "main.py").write_text("from operations import add\n\n\ndef add(a, b):\n    return a + b\n\n"
                                      "print(add(2, 3))\n")
    found = broken_imports(str(tmp_path), ["main.py"])
    assert found and "replaces the add" in found[0]
    (tmp_path / "main.py").write_text("from operations import add\n\nprint(add(2, 3))\n")
    assert broken_imports(str(tmp_path), ["main.py"]) == []


def test_a_component_whose_block_body_never_returns_its_jsx(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Header.jsx").write_text("const Header = () => {\n  <header><h1>Hi</h1></header>\n}\n\n"
                                                 "export default Header\n")
    (tmp_path / "src" / "App.jsx").write_text("import Header from './Header.jsx'\n\nfunction App() {\n"
                                              "  return (<Header/>)\n}\n\nexport default App\n")
    found = broken_imports(str(tmp_path), ["src/App.jsx"])
    assert found and "never returns" in found[0]
    (tmp_path / "src" / "Header.jsx").write_text("const Header = () => {\n  return <header><h1>Hi</h1></header>\n}\n\n"
                                                 "export default Header\n")
    assert broken_imports(str(tmp_path), ["src/App.jsx"]) == []


def test_an_import_naming_the_modules_extension_is_the_same_import():
    view = equivalent_view("import { formatPrice } from '../utils.ts'\n", "Cart.tsx")
    assert view is not None and "import { formatPrice } from '../utils'" in view


def test_a_key_commented_out_in_tsconfig_is_not_set(tmp_path):
    step = {"id": "ts", "instructions": "Set strict to true in tsconfig.json.",
            "checks": [{"id": "c", "type": "file_contains", "label": "strict on", "file": "tsconfig.json",
                        "pattern": r"\"strict\"\s*:\s*true"}]}
    (tmp_path / "tsconfig.json").write_text('{\n  "compilerOptions": {\n    // "strict": true,\n'
                                            '    "outDir": "https://x//dist"\n  }\n}\n')
    assert not _gate(step, workdir=str(tmp_path))["passed"]
    (tmp_path / "tsconfig.json").write_text('{\n  "compilerOptions": {\n    /* on */ "strict": true\n  }\n}\n')
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_vscode_counting_type_errors_fails_a_tsc_step():
    step = {"id": "ts4", "run_command": "npx tsc && node dist/invoice.js", "file": "src/invoice.ts",
            "checks": [{"id": "c", "type": "screen_contains", "label": "total printed", "app": "Terminal",
                        "pattern": r"Invoice\s+total"}]}
    term = ["me@mac i % node dist/invoice.js", "Invoice total: $30.50", "me@mac i % "]
    gate = _gate(step, screen={"Code": ["invoice.ts", "⊗ 1 ⚠ 0"], "Terminal": term})
    assert not gate["passed"] and "1 error" in gate["checks"][-1]["detail"]
    assert _gate(step, screen={"Code": ["invoice.ts", "⊗ 0 ⚠ 0"], "Terminal": term})["passed"]


# -- app files ----------------------------------------------------------------------------------------------------------

def _dxf(*entities, layers=("0",)):
    rows = ["0", "SECTION", "2", "ENTITIES"]
    for e in entities:
        rows += [str(x) for x in e]
    rows += ["0", "ENDSEC", "0", "EOF"]
    return "\n".join(rows) + "\n"


def test_a_polyline_ended_on_its_first_point_is_still_open(tmp_path):
    step = {"id": "s1", "instructions": "Draw the profile with PLINE, then type C to close it.",
            "checks": [{"id": "c", "type": "file_contains", "label": "Profile is a polyline", "file": "car.dxf",
                        "pattern": r"\bLWPOLYLINE\b"}]}
    pts = [10, 0.0, 20, 0.0, 10, 120.0, 20, 0.0, 10, 120.0, 20, 28.0, 10, 0.0, 20, 0.0]
    (tmp_path / "car.dxf").write_text(_dxf([0, "LWPOLYLINE", 8, "BODY", 90, 4, 70, 0, *pts]))
    gate = _gate(step, workdir=str(tmp_path))
    assert not gate["passed"] and "open" in gate["checks"][-1]["detail"]
    (tmp_path / "car.dxf").write_text(_dxf([0, "LWPOLYLINE", 8, "BODY", 90, 4, 70, 1, *pts]))
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_a_dimension_reads_what_it_measures(tmp_path):
    step = {"id": "s3", "instructions": "Add a DIMLINEAR across the body: it should read 120.",
            "checks": [{"id": "c", "type": "file_contains", "label": "Dimension placed", "file": "car.dxf",
                        "pattern": r"\bDIMENSION\b"}]}
    (tmp_path / "car.dxf").write_text(_dxf([0, "DIMENSION", 8, "DIMS", 42, 102.0, 13, 18.0, 14, 120.0]))
    gate = _gate(step, workdir=str(tmp_path))
    assert not gate["passed"] and "102" in gate["checks"][-1]["detail"]
    (tmp_path / "car.dxf").write_text(_dxf([0, "DIMENSION", 8, "DIMS", 42, 120.0, 13, 0.0, 14, 120.0]))
    assert _gate(step, workdir=str(tmp_path))["passed"]


def _scene_step(label, pattern, instructions="", file="s.scene.json"):
    return {"id": "b", "instructions": instructions,
            "checks": [{"id": "c", "type": "file_contains", "label": label, "file": file, "pattern": pattern}]}


def test_an_object_at_a_value_on_the_named_axis(tmp_path):
    step = _scene_step("Cube at X 2", r"\"location\":\s*\[[^\]]*\b2(?:\.0+)?\b", "Press G, then X, type 2.")
    _dump(tmp_path, "s.scene.json", {"objects": [_obj("Cube", location=[0.0, 2.0, 0.0])]})
    assert not _gate(step, workdir=str(tmp_path))["passed"]
    _dump(tmp_path, "s.scene.json", {"objects": [_obj("Cube", location=[2.0, 0.0, 0.0])]})
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_every_channel_of_a_retimed_object_ends_on_the_frame(tmp_path):
    step = _scene_step("Keys end on frame 97", r"\[\s*97(?:\.0+)?,", "Select all of the ball's keys and press S 2.")
    fc = [{"data_path": "location", "index": 0, "keyframes": [[1.0, 0.0], [49.0, 6.0]]},
          {"data_path": "location", "index": 2, "keyframes": [[1.0, 3.0], [97.0, 0.5]]}]
    _dump(tmp_path, "s.scene.json", {"objects": [_obj("Ball", animation={"fcurves": fc})]})
    assert not _gate(step, workdir=str(tmp_path))["passed"]
    fc[0]["keyframes"][1][0] = 97.0
    _dump(tmp_path, "s.scene.json", {"objects": [_obj("Ball", animation={"fcurves": fc})]})
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_a_separate_object_pushed_against_a_part_that_must_be_one_piece(tmp_path):
    step = _scene_step("Mug is one piece", r"\"islands\":\s*1\b", "Extrude the handle from the mug in Edit mode.")
    mug = _obj("Mug", dimensions=[1.6, 1.6, 2.0], mesh={"islands": 1})
    torus = _obj("Torus", location=[1.05, 0.0, 1.0], dimensions=[0.875, 0.875, 0.175], mesh={"islands": 1})
    floor = _obj("Floor", dimensions=[20.0, 20.0, 0.0], mesh={"islands": 1})
    _dump(tmp_path, "s.scene.json", {"objects": [mug, torus, floor]})
    gate = _gate(step, workdir=str(tmp_path))
    assert not gate["passed"] and "Torus" in gate["checks"][-1]["detail"]
    _dump(tmp_path, "s.scene.json", {"objects": [mug, floor]})
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_the_last_keys_interpolation_changes_nothing(tmp_path):
    step = _scene_step("Constant keys", r"\"interpolation\":\s*\[\s*\"CONSTANT\",\s*\"CONSTANT\",\s*\"CONSTANT\"\s*\]")
    keys = [[1.0, 0.0], [25.0, -1.5], [49.0, -3.1]]
    fc = {"data_path": "rotation_euler", "index": 1, "keyframes": keys, "interpolation": ["CONSTANT", "CONSTANT", "BEZIER"]}
    _dump(tmp_path, "s.scene.json", {"objects": [_obj("Hand", animation={"fcurves": [fc]})]})
    assert _gate(step, workdir=str(tmp_path))["passed"]
    fc["interpolation"] = ["CONSTANT", "BEZIER", "BEZIER"]
    _dump(tmp_path, "s.scene.json", {"objects": [_obj("Hand", animation={"fcurves": [fc]})]})
    assert not _gate(step, workdir=str(tmp_path))["passed"]


def test_a_principled_input_renamed_in_blender_4_reads_under_its_old_name(tmp_path):
    step = _scene_step("Full transmission", r"\"transmission\":\s*1(?:\.0+)?\b")
    mats = [{"name": "Glass", "users": ["Ball"], "principled": {"transmission_weight": 1.0}}]
    _dump(tmp_path, "s.scene.json", {"objects": [_obj("Ball")], "materials": mats})
    assert _gate(step, workdir=str(tmp_path))["passed"]
    mats[0]["principled"]["transmission_weight"] = 0.0
    _dump(tmp_path, "s.scene.json", {"objects": [_obj("Ball")], "materials": mats})
    assert not _gate(step, workdir=str(tmp_path))["passed"]


def test_a_feature_health_warning_is_not_an_error(tmp_path):
    step = _scene_step("Every feature rebuilds", r"\"health\":\s*\"healthy\"", file="box.design.json")
    items = [{"name": "Sketch1", "health": "healthy"}, {"name": "Fillet1", "health": "warning"}]
    _dump(tmp_path, "box.design.json", {"design": "Box", "timeline": {"items": items}})
    assert _gate(step, workdir=str(tmp_path))["passed"]
    items[1]["health"] = "error"
    _dump(tmp_path, "box.design.json", {"design": "Box", "timeline": {"items": items}})
    assert not _gate(step, workdir=str(tmp_path))["passed"]


def test_a_hole_through_the_wrong_wall(tmp_path):
    step = _scene_step("Hole added", r"\"type\":\s*\"Hole\"", "Put the hole in one short wall of the box.",
                       file="box.design.json")
    hole = {"name": "Hole1", "type": "Hole", "diameter": 8.0, "axis": [0.0, 1.0, 0.0]}
    doc = {"components": [{"name": "Base", "bodies": [{"name": "Body1", "bound_box": [80.0, 50.0, 30.0]}]}],
           "features": [hole]}
    _dump(tmp_path, "box.design.json", doc)
    gate = _gate(step, workdir=str(tmp_path))
    assert not gate["passed"] and "long wall" in gate["checks"][-1]["detail"]
    hole["axis"] = [1.0, 0.0, 0.0]
    _dump(tmp_path, "box.design.json", doc)
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_a_body_built_while_another_component_was_active(tmp_path):
    step = _scene_step("Lid component", r"\"name\":\s*\"Lid\"",
                       "Activate the Lid component, then extrude the outline 3 mm into a new body.",
                       file="box.design.json")
    doc = {"components": [{"name": "Base", "bodies": [{"name": "Body1"}, {"name": "Body2"}]},
                          {"name": "Lid", "bodies": []}]}
    _dump(tmp_path, "box.design.json", doc)
    gate = _gate(step, workdir=str(tmp_path))
    assert not gate["passed"] and "Lid has no body" in gate["checks"][-1]["detail"]
    doc["components"][1]["bodies"].append(doc["components"][0]["bodies"].pop())
    _dump(tmp_path, "box.design.json", doc)
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_a_slicers_own_gcode_name_is_the_gcode_the_step_never_named(tmp_path):
    step = {"id": "s6", "instructions": "Open base.stl and lid.stl in the slicer and Export G-code for each.",
            "checks": [{"id": "a", "type": "file_exists", "label": "Base sliced", "file": "base.gcode"},
                       {"id": "b", "type": "file_exists", "label": "Lid sliced", "file": "lid.gcode"}]}
    (tmp_path / "base_0.2mm_PLA_MK4_1h12m.gcode").write_text("G28\n")
    assert not _gate(step, workdir=str(tmp_path))["passed"]  # the lid isn't sliced
    (tmp_path / "lid_0.2mm_PLA_MK4_24m.gcode").write_text("G28\n")
    assert _gate(step, workdir=str(tmp_path))["passed"]

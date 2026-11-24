"""Regression tests for the wrong verdicts the round-4 step-check evals found (server/evals/checks, train cases).
One test per general fix (each with the finished form that must still pass). Offline: no model, no network."""
from __future__ import annotations

import json

from server.checks import RunContext, blocks, evaluate_gate
from server.checks.code_equiv import adjacent_jsx, equivalent_view
from server.checks.evaluator import numpy_lists
from server.checks.screen import extract_metrics


def _gate(step, **ctx):
    return evaluate_gate(step, RunContext(**ctx))


def _term(*rows):
    return {"Terminal": list(rows)}


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def _dump(tmp_path, name, doc):
    _write(tmp_path, name, json.dumps(doc, indent=1))


def _obj(name, **kw):
    return {"name": name, "type": "MESH", "location": [0.0, 0.0, 0.0], "rotation_deg": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0], "dimensions": [2.0, 2.0, 2.0], **kw}


def _fc(tmp_path, name, pattern, label, step_text="", file_name="scene.json"):
    return {"id": "s", "title": "", "instructions": step_text,
            "checks": [{"id": "c", "type": "file_contains", "label": label, "file": file_name, "pattern": pattern}]}


def _nb(tmp_path, cells, name="nb.ipynb"):
    out = []
    for c in cells:
        outs = []
        if c.get("out"):
            outs.append({"output_type": "stream", "name": "stdout", "text": c["out"]})
        if c.get("result"):
            outs.append({"output_type": "execute_result", "execution_count": c.get("n"), "metadata": {},
                         "data": {"text/plain": c["result"]}})
        if c.get("image"):
            outs.append({"output_type": "display_data", "metadata": {},
                         "data": {"image/png": "iVBORw0KGgo=", "text/plain": "<Figure size 640x480 with 1 Axes>"}})
        out.append({"cell_type": "code", "metadata": {}, "source": c["src"], "outputs": outs,
                    "execution_count": c.get("n")})
    _write(tmp_path, name, json.dumps({"cells": out, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}))


def _cell_step(code, match, checks, file="nb.ipynb", **kw):
    return {"id": "s", "run_command": "Run the cell (Shift+Enter)", "code": code, "file": file,
            "targets": [{"app": "Code", "file": file, "match": match}], "checks": checks, **kw}


def _typed(pattern, file="nb.ipynb"):
    return [{"id": "c", "type": "file_contains", "label": "typed", "file": file, "pattern": pattern}]


def _printed(pattern, label="printed"):
    return [{"id": "o", "type": "screen_contains", "label": label, "app": "Code", "output": True, "pattern": pattern}]


# -- Blender / Fusion / FreeCAD / AutoCAD: what the saved model is ------------------------------------------------------

def test_a_rotation_typed_the_other_way_is_turned_by_the_same_angle(tmp_path):
    step = {"id": "s", "title": "Place the shapes", "instructions": "Turn the cone 90 degrees on X (R X 90).",
            "checks": [{"id": "c", "type": "file_contains", "label": "Cone turned 90 degrees", "file": "s.scene.json",
                        "pattern": r'"name":\s*"Cone",[^{}]*?"rotation_deg":\s*\[\s*90(?:\.0+)?\b'}]}
    _dump(tmp_path, "s.scene.json", {"objects": [_obj("Cone", rotation_deg=[-90.0, 0.0, 0.0])]})
    assert _gate(step, workdir=str(tmp_path))["passed"]
    step["instructions"] = "Turn the cone 90 degrees clockwise on X."  # the direction is the point: -90 is not it
    assert not _gate(step, workdir=str(tmp_path))["passed"]


def test_a_body_drawn_with_its_long_side_along_y_has_the_same_size(tmp_path):
    step = {"id": "s", "title": "Extrude it into a block", "instructions": "Press E, set 30 mm, OK.",
            "checks": [{"id": "c", "type": "file_contains", "label": "80 x 50 x 30 mm body", "file": "b.design.json",
                        "pattern": r'"bound_box":\s*\[\s*80(?:\.0+)?\b,\s*50(?:\.0+)?\b,\s*30(?:\.0+)?\b'}]}
    _dump(tmp_path, "b.design.json", {"components": [{"name": "Box", "bodies": [
        {"name": "Body1", "bound_box": [50.0, 80.0, 30.0]}]}]})
    assert _gate(step, workdir=str(tmp_path))["passed"]
    _dump(tmp_path, "b.design.json", {"components": [{"name": "Box", "bodies": [
        {"name": "Body1", "bound_box": [50.0, 30.0, 80.0]}]}]})
    assert not _gate(step, workdir=str(tmp_path))["passed"]


def test_numbers_the_step_gives_only_as_an_example_and_the_relation_it_asks_for(tmp_path):
    words = ("Pad the arm, then sketch the slot 0.3 mm wider than the arm (for example a 2 mm arm in a 2.3 mm slot) "
             "and pocket it.")
    step = {"id": "s", "title": "A snap-fit hook", "instructions": words, "checks": [
        {"id": "a", "type": "file_contains", "label": "Arm 2 mm", "file": "snap.scene.json",
         "pattern": r'"name":\s*"ArmWidth",\s*"type":\s*"Distance[XY]?",\s*"value":\s*2(?:\.0+)?\b'},
        {"id": "b", "type": "file_contains", "label": "Slot 0.3 mm wider than the arm", "file": "snap.scene.json",
         "pattern": r'"name":\s*"SlotWidth",\s*"type":\s*"Distance[XY]?",\s*"value":\s*2\.3\b'}]}

    def dump(arm, slot):
        _dump(tmp_path, "snap.scene.json", {"bodies": [
            {"name": "Hook", "features": [{"name": "Sketch", "constraints": [
                {"name": "ArmWidth", "type": "DistanceX", "value": arm}]}]},
            {"name": "Receiver", "features": [{"name": "Sketch003", "constraints": [
                {"name": "SlotWidth", "type": "DistanceX", "value": slot}]}]}]})

    dump(1.7, 2.0)
    assert _gate(step, workdir=str(tmp_path))["passed"]
    dump(1.7, 2.3)  # the example's slot around a thinner arm: 0.6 mm of play
    gate = _gate(step, workdir=str(tmp_path))
    assert not gate["passed"] and "0.6" in gate["checks"][1]["detail"]
    step["instructions"] = "Pad a 2 mm arm, then sketch a 2.3 mm slot (0.3 mm wider than the arm)."
    dump(1.7, 2.0)  # the step's own numbers: they are required
    assert not _gate(step, workdir=str(tmp_path))["passed"]


def test_a_modifier_switched_off_in_viewport_and_render_does_nothing(tmp_path):
    step = {"id": "s", "title": "Subdivision", "instructions": "Select the mug, add a Subdivision Surface modifier "
            "with Levels Viewport 2.", "checks": [
                {"id": "c", "type": "file_contains", "label": "Subdivision modifier", "file": "mug.scene.json",
                 "pattern": r'"type":\s*"SUBSURF"'}]}
    mod = {"name": "Subdivision", "type": "SUBSURF", "levels": 2, "show_viewport": False, "show_render": False}
    _dump(tmp_path, "mug.scene.json", {"objects": [_obj("Mug", modifiers=[mod])]})
    gate = _gate(step, workdir=str(tmp_path))
    assert not gate["passed"] and "switched off" in gate["checks"][-1]["detail"]
    mod["show_render"] = True
    _dump(tmp_path, "mug.scene.json", {"objects": [_obj("Mug", modifiers=[mod])]})
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_uv_islands_on_top_of_each_other_when_the_step_says_none_overlap(tmp_path):
    step = {"id": "s", "title": "Unwrap a crate", "instructions": "Press U > Unwrap: no island should overlap another.",
            "checks": [{"id": "c", "type": "file_contains", "label": "UV map", "file": "crate.scene.json",
                        "pattern": r'"uv_layers":\s*\[\s*"UVMap"'}]}
    mesh = {"uv_layers": ["UVMap"], "uv": {"islands": 6, "overlapping_islands": 6}}
    _dump(tmp_path, "crate.scene.json", {"objects": [_obj("Crate", mesh=mesh)]})
    assert not _gate(step, workdir=str(tmp_path))["passed"]
    mesh["uv"]["overlapping_islands"] = 0
    _dump(tmp_path, "crate.scene.json", {"objects": [_obj("Crate", mesh=mesh)]})
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_a_curve_that_should_overshoot_never_goes_above_its_last_key(tmp_path):
    step = {"id": "s", "title": "Graph Editor", "instructions": "Drag the handle so the curve rises past 5 before "
            "settling (an overshoot).", "checks": [
                {"id": "c", "type": "file_contains", "label": "Handles edited", "file": "slide.scene.json",
                 "pattern": r'"handle_types":\s*\[[^\]]*"(?:ALIGNED|FREE)"'}]}

    def dump(top):
        fc = {"data_path": "location", "index": 0, "keyframes": [[1.0, 0.0], [48.0, 5.0]],
              "handle_types": ["AUTO_CLAMPED", "ALIGNED"], "evaluated_range": [0.0, top]}
        _dump(tmp_path, "slide.scene.json", {"objects": [_obj("Cube", animation={"fcurves": [fc]})]})

    dump(5.0)
    assert not _gate(step, workdir=str(tmp_path))["passed"]
    dump(5.6)
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_a_shell_that_removed_no_face_is_closed(tmp_path):
    step = {"id": "s", "title": "Shell", "instructions": "Click the top face so it is removed, thickness 2 mm.",
            "checks": [{"id": "c", "type": "file_contains", "label": "2 mm walls", "file": "b.design.json",
                        "pattern": r'"thickness":\s*2(?:\.0+)?\b'}]}
    _dump(tmp_path, "b.design.json", {"features": [{"name": "Shell1", "type": "Shell", "thickness": 2.0,
                                                    "faces_removed": 0}]})
    assert not _gate(step, workdir=str(tmp_path))["passed"]
    _dump(tmp_path, "b.design.json", {"features": [{"name": "Shell1", "type": "Shell", "thickness": 2.0,
                                                    "faces_removed": 1}]})
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_a_symmetric_extrude_is_twice_as_tall(tmp_path):
    step = {"id": "s", "title": "Extrude", "instructions": "Set the distance to 30 mm.",
            "checks": [{"id": "c", "type": "file_contains", "label": "30 mm tall", "file": "b.design.json",
                        "pattern": r'"distance":\s*30(?:\.0+)?\b'}]}

    def dump(extent, z):
        _dump(tmp_path, "b.design.json", {"components": [{"name": "Box", "bodies": [
            {"name": "Body1", "bound_box": [80.0, 50.0, z]}]}], "features": [
            {"name": "Extrude1", "type": "Extrude", "extent": extent, "measurement": "one_side", "distance": 30.0}]})

    dump("symmetric", 60.0)
    gate = _gate(step, workdir=str(tmp_path))
    assert not gate["passed"] and "Symmetric" in gate["checks"][-1]["detail"]
    dump("one_side", 30.0)
    assert _gate(step, workdir=str(tmp_path))["passed"]


_DXF_HEAD = "0\nSECTION\n2\nENTITIES\n"


def test_a_dimension_on_layer_0_when_the_step_puts_it_on_its_layer(tmp_path):
    step = {"id": "s", "title": "Dimension the length", "instructions": "Make a layer DIMS and set it current. Add a "
            "DIMLINEAR across the body.", "checks": [
                {"id": "c", "type": "file_contains", "label": "On layer DIMS", "file": "car.dxf", "pattern": r"\bDIMS\b"}]}
    table = "0\nSECTION\n2\nTABLES\n0\nLAYER\n2\nDIMS\n70\n0\n0\nENDSEC\n"

    def dxf(layer):
        _write(tmp_path, "car.dxf", table + _DXF_HEAD + f"0\nDIMENSION\n8\n{layer}\n42\n120.0\n0\nENDSEC\n0\nEOF\n")

    dxf("0")
    gate = _gate(step, workdir=str(tmp_path))
    assert not gate["passed"] and "layer 0" in gate["checks"][-1]["detail"]
    dxf("DIMS")
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_a_render_named_for_other_frames_is_not_the_steps_animation(tmp_path):
    step = {"id": "s", "title": "Render the animation", "instructions": "Set the frame range to 1-96, then Render "
            "Animation and wait for frame 96.", "checks": [
                {"id": "c", "type": "file_exists", "label": "MP4 saved", "file": "bounce.mp4"}]}
    _write(tmp_path, "0001-0048.mp4", "ftyp")
    gate = _gate(step, workdir=str(tmp_path))
    assert not gate["passed"] and "1-48" in gate["checks"][0]["detail"]
    _write(tmp_path, "0001-0096.mp4", "ftyp")
    assert _gate(step, workdir=str(tmp_path))["passed"]


# -- terminal -------------------------------------------------------------------------------------------------------------

def test_a_merge_run_the_other_way_round_is_not_the_steps_merge():
    assert not blocks.runs("git merge main", "git merge add-waffles")
    assert blocks.runs("git merge add-waffles", "git merge add-waffles")
    assert blocks.runs("git merge origin/add-waffles", "git merge add-waffles")
    assert blocks.runs("git merge main", "git merge <branch>")
    assert blocks.runs("git rebase -i HEAD~4", "git rebase -i HEAD~3")  # how far back is the learner's call
    step = {"id": "s", "run_command": "git merge add-waffles",
            "targets": [{"app": "Terminal", "match": "git merge add-waffles"}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "Branch deleted", "app": "Terminal",
                        "pattern": r"Deleted\s+branch\s+add-waffles"}]}
    tail = ["me@mac c % git branch -D add-waffles", "Deleted branch add-waffles (was 5d6e7f8).", "me@mac c % "]
    assert not _gate(step, screen=_term("me@mac c % git merge main", "Already up to date.", *tail))["passed"]
    assert _gate(step, screen=_term("me@mac c % git merge add-waffles", "Fast-forward", *tail))["passed"]


def test_a_git_error_the_learner_got_past_with_the_same_subcommand():
    step = {"id": "s", "run_command": "git commit -m \"Add pancakes\"",
            "targets": [{"app": "Terminal", "match": "git commit -m"}],
            "checks": [{"id": "c", "type": "screen_absent", "label": "No Git errors", "app": "Terminal",
                        "pattern": "fatal:|error:"}]}
    first = ["me@mac c % git commit -m \"Add pancakes\" pancakes.md",
             "error: pathspec 'pancakes.md' did not match any file(s) known to git"]
    ok = ["me@mac c % git add pancakes.md", "me@mac c % git commit -m \"Add pancakes\"",
          "[main (root-commit) a1b2c3d] Add pancakes", "me@mac c % "]
    assert _gate(step, screen=_term(*first, *ok))["passed"]
    assert not _gate(step, screen=_term(*first, "me@mac c % git status", "On branch main", "me@mac c % "))["passed"]


def test_gh_repo_create_with_push_is_the_push_and_head_is_the_branch():
    assert blocks.runs("gh repo create cookbook --public --source=. --remote=origin --push", "git push -u origin main")
    assert not blocks.runs("gh repo create cookbook --public", "git push -u origin main")
    step = {"id": "s", "run_command": "git push -u origin main",
            "targets": [{"app": "Terminal", "match": "git push -u origin main"}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "main pushed", "app": "Terminal",
                        "pattern": r"main\s*->\s*main"}]}
    rows = ["me@mac c % gh repo create cookbook --public --source=. --remote=origin --push",
            "To github.com:ada/cookbook.git", " * [new branch]      HEAD -> main",
            "branch 'main' set up to track 'origin/main'.", "me@mac c % "]
    assert _gate(step, screen=_term(*rows))["passed"]
    rows[3] = "me@mac c % "  # no row says HEAD was main
    assert not _gate(step, screen=_term(*rows[:4]))["passed"]


def test_cargo_run_with_nothing_to_compile_built_the_current_sources(tmp_path):
    _write(tmp_path, "trail/Cargo.toml", '[package]\nname = "trail"\nversion = "0.1.0"\n')
    step = {"id": "s", "run_command": "cargo run", "targets": [{"app": "Terminal", "match": "cargo run"}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "Cargo builds the project", "app": "Terminal",
                        "pattern": r"Compiling\s+trail\s+v0\.1\.0"}]}
    fresh = ["me@mac trail % cargo run", "    Finished `dev` profile [unoptimized + debuginfo] target(s) in 0.01s",
             "     Running `target/debug/trail`", "Hello", "me@mac trail % "]
    assert _gate(step, workdir=str(tmp_path), screen=_term(*fresh))["passed"]
    other = [r.replace("target/debug/trail", "target/debug/other") for r in fresh]  # another package's binary
    assert not _gate(step, workdir=str(tmp_path), screen=_term(*other))["passed"]


def test_a_dev_servers_own_error_rows_when_the_terminal_must_show_no_errors():
    step = {"id": "s", "run_command": "npm run dev", "targets": [{"app": "Terminal", "match": "npm run dev"}],
            "checks": [{"id": "c", "type": "screen_absent", "label": "No compile errors in the terminal",
                        "app": "Terminal", "pattern": r"ERR!|Failed\s+to\s+compile"}]}
    rows = ["me@mac a % npm run dev", "VITE v5.4.10  ready in 296 ms",
            "4:31:52 PM [vite] Internal server error: /a/src/App.jsx: Unterminated JSX contents. (8:4)"]
    assert not _gate(step, screen=_term(*rows))["passed"]
    assert _gate(step, screen=_term(*rows, "4:32:10 PM [vite] hmr update /src/App.jsx"))["passed"]


def test_a_scaffolder_answered_with_an_option_the_step_does_not_choose():
    step = {"id": "s", "title": "Scaffold", "instructions": "Run npm create vite@latest choosing my-app, React, and "
            "JavaScript, then npm run dev.", "targets": [{"app": "Terminal", "match": "npm run dev"}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "Vite ready", "app": "Terminal",
                        "pattern": r"ready\s+in"}]}
    rows = ["me@mac p % npm create vite@latest", "✔ Project name: … my-app", "✔ Select a framework: › {fw}",
            "✔ Select a variant: › JavaScript", "me@mac p % npm run dev", "VITE v5.4.10  ready in 188 ms"]
    gate = _gate(step, screen=_term(*[r.format(fw="Vanilla") for r in rows]))
    assert not gate["passed"] and "Vanilla" in gate["checks"][-1]["detail"]
    assert _gate(step, screen=_term(*[r.format(fw="React") for r in rows]))["passed"]


# -- code -----------------------------------------------------------------------------------------------------------------

def test_a_type_hinted_def_is_the_same_def():
    view = equivalent_view("def add_numbers(a: int, b: int = 2) -> int:\n    return a + b\n", "ops.py")
    assert view is not None and "def add_numbers(a, b=2):" in view
    step = {"id": "s", "file": "ops.py", "checks": [{"id": "c", "type": "screen_contains", "label": "defines it",
                                                     "app": "Code", "pattern": r"def\s+add_numbers\(a,\s*b\):"}]}
    assert _gate(step, screen={"Code": ["ops.py", "def add_numbers(a: int, b: int) -> int:"]})["passed"]
    assert not _gate(step, screen={"Code": ["ops.py", "def add_numbers(a: int) -> int:"]})["passed"]


def test_a_destructured_callback_field_is_the_elements_property():
    text = "{items.map(({ id, price }) => (\n  <li key={id}>{formatPrice(price)}</li>\n))}"
    view = equivalent_view(text, "Cart.tsx")
    assert view is not None and "formatPrice(item.price)" in view
    step = {"id": "s", "file": "Cart.tsx", "checks": [{"id": "c", "type": "screen_contains", "label": "prices",
                                                       "app": "Code", "pattern": r"formatPrice\(\s*item\.price\s*\)"}]}
    assert _gate(step, screen={"Code": ["Cart.tsx", *text.splitlines()]})["passed"]
    assert not _gate(step, screen={"Code": ["Cart.tsx", "{items.map(({ id, price }) => <li>{price}</li>)}"]})["passed"]


def test_a_rename_that_keeps_the_old_name_defined(tmp_path):
    step = {"id": "s", "title": "Rename add to add_numbers", "file": "operations.py",
            "checks": [{"id": "c", "type": "screen_contains", "label": "defines add_numbers", "app": "Code",
                        "pattern": r"def\s+add_numbers\("}]}
    _write(tmp_path, "test_ops.py", "from operations import add\n\ndef test_add():\n    assert add(2, 3) == 5\n")
    _write(tmp_path, "operations.py", "def add(a, b):\n    return a + b\n\ndef add_numbers(a, b):\n    return a + b\n")
    screen = {"Code": ["operations.py", "def add_numbers(a, b):"]}
    gate = _gate(step, workdir=str(tmp_path), screen=screen)
    assert not gate["passed"] and "test_ops.py" in gate["checks"][-1]["detail"]
    _write(tmp_path, "test_ops.py", "from operations import add_numbers\n")
    _write(tmp_path, "operations.py", "def add_numbers(a, b):\n    return a + b\n")
    assert _gate(step, workdir=str(tmp_path), screen=screen)["passed"]


def test_an_import_beside_a_local_declaration_of_the_same_name(tmp_path):
    step = {"id": "s", "file": "src/Cart.tsx", "checks": [{"id": "c", "type": "screen_contains", "label": "imports",
                                                           "app": "Code", "pattern": r"import\s*\{\s*formatPrice"}]}
    _write(tmp_path, "src/utils.ts", "export function formatPrice(c: number) { return '$' + c }\n")
    body = "import { formatPrice } from './utils'\n\nexport const Cart = () => formatPrice(1)\n"
    _write(tmp_path, "src/Cart.tsx", body + "\nfunction formatPrice(n: number) {\n  return '$' + n\n}\n")
    screen = {"Code": ["Cart.tsx", "import { formatPrice } from './utils'"]}
    gate = _gate(step, workdir=str(tmp_path), screen=screen)
    assert not gate["passed"] and "own formatPrice" in gate["checks"][-1]["detail"]
    _write(tmp_path, "src/Cart.tsx", body)
    assert _gate(step, workdir=str(tmp_path), screen=screen)["passed"]


def test_two_jsx_elements_side_by_side_in_a_return():
    assert adjacent_jsx("function App() {\n  return (\n    <>\n      <Header/>\n    </>\n    <Footer/>\n  )\n}") == [2]
    assert adjacent_jsx("function App() {\n  return (\n    <>\n      <Header/>\n      <Footer/>\n    </>\n  )\n}") == []
    assert adjacent_jsx("const A = () => {\n  return (<div className=\"a\" onClick={() => x > 1}>{a}</div>)\n}") == []


def test_a_method_the_label_says_is_called_needs_its_parentheses():
    step = {"id": "s", "file": "src/Food.jsx", "checks": [{"id": "c", "type": "screen_contains",
                                                           "label": "toUpperCase method called", "app": "Code",
                                                           "pattern": "toUpperCase"}]}
    assert not _gate(step, screen={"Code": ["Food.jsx", "<li>{food2.toUpperCase}</li>"]})["passed"]
    assert _gate(step, screen={"Code": ["Food.jsx", "<li>{food2.toUpperCase()}</li>"]})["passed"]


# -- notebooks ------------------------------------------------------------------------------------------------------------

def test_a_whole_number_percentage_is_the_metric():
    assert extract_metrics(r"test\s*images:\s*(?P<value>\d+\.\d+)%", "on the 10000 test images: 98%") == [(0, 98.0)]
    assert extract_metrics(r"test\s*images:\s*(?P<value>\d+\.\d+)%", "on the test images: 97.59%") == [(0, 97.59)]


def test_a_numpy_column_printed_is_the_list(tmp_path):
    assert numpy_lists("[[0.]\n [0.]\n [0.]\n [1.]]") == "[0, 0, 0, 1]"
    assert numpy_lists("[0. 1. 0.5]") == "[0, 1, 0.5]"
    assert numpy_lists("[[1 2]\n [3 4]]") == ""  # a matrix stays a matrix
    code = "print(np.round(sigmoid(X @ w + b)))"
    step = _cell_step(code, "np.round(sigmoid(", _printed(r"\[\s*0,\s*0,\s*0,\s*1\s*\]"))
    _nb(tmp_path, [{"src": code, "n": 1, "out": "[[0.]\n [0.]\n [0.]\n [1.]]\n"}])
    assert _gate(step, workdir=str(tmp_path))["passed"]
    _nb(tmp_path, [{"src": code, "n": 1, "out": "[[0.]\n [0.]\n [1.]\n [1.]]\n"}])
    assert not _gate(step, workdir=str(tmp_path))["passed"]


def test_an_output_on_screen_from_another_cell_is_not_the_steps(tmp_path):
    code = "y_pred = knn.predict(X_test)\nprint(len(y_pred))"
    step = _cell_step(code, "knn.predict(", _printed(r"\b45\b", "45 predictions"))
    cells = [{"src": "print(X_train.shape, X_test.shape)", "n": 1, "out": "(133, 13) (45, 13)\n"},
             {"src": "y_pred = knn.predict(X_train)\nprint(len(y_pred))", "n": 2, "out": "133\n"}]
    _nb(tmp_path, cells)
    screen = {"Code": ["nb.ipynb", "[1]", "(133, 13) (45, 13)", "[2]", "y_pred = knn.predict(X_train)", "133"]}
    assert not _gate(step, workdir=str(tmp_path), screen=screen)["passed"]
    cells[1] = {"src": code, "n": 2, "out": "45\n"}
    _nb(tmp_path, cells)
    assert _gate(step, workdir=str(tmp_path), screen=screen)["passed"]


def test_an_output_printed_before_a_later_run_changed_what_it_shows(tmp_path):
    code = "for _ in range(9):\n    w -= lr * g(w)\nprint(predict(w).tolist())"
    step = _cell_step(code, "w -= lr * g(w)", _printed(r"\[\s*0,\s*1\s*\]"))
    cells = [{"src": "w = init()\nfor _ in range(9):\n    w -= lr * g(w)", "n": 3},
             {"src": "print(predict(w).tolist())", "n": 2, "out": "[0, 1]\n"}]
    _nb(tmp_path, cells)
    gate = _gate(step, workdir=str(tmp_path))
    assert not gate["passed"] and "[3]" in gate["checks"][-1]["detail"]
    cells[1]["n"] = 4
    _nb(tmp_path, cells)
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_backward_run_again_adds_to_the_gradient(tmp_path):
    code = "loss = (w * x - y) ** 2\nloss.backward()\nprint('autograd:', w.grad)"
    step = _cell_step(code, "loss.backward()", _printed(r"autograd:\s*tensor\("))
    cells = [{"src": "import torch", "n": 1}, {"src": "w = torch.tensor(1.0, requires_grad=True)", "n": 2},
             {"src": code, "n": 4, "out": "autograd: tensor(12.)\n"}]
    _nb(tmp_path, cells)
    gate = _gate(step, workdir=str(tmp_path))
    assert not gate["passed"] and "backward" in gate["checks"][-1]["detail"]
    cells[2]["n"] = 3
    _nb(tmp_path, cells)
    assert _gate(step, workdir=str(tmp_path))["passed"]
    cells[2] = {"src": "w.grad = None\n" + code, "n": 4, "out": "autograd: tensor(6.)\n"}  # zeroed first
    _nb(tmp_path, cells)
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_a_keyword_the_instructions_spell_out_left_out_of_the_call(tmp_path):
    code = "ax.hist(sums, bins=np.arange(1.5, 13.5), edgecolor='white')"
    step = _cell_step(code, "ax.hist(", _typed(r"ax\.hist\("),
                      instructions="Draw the sums with ax.hist, using bins=np.arange(1.5, 13.5).")
    _nb(tmp_path, [{"src": "ax.hist(sums)", "n": 1, "image": True}])
    gate = _gate(step, workdir=str(tmp_path))
    assert not gate["passed"] and "bins" in gate["checks"][-1]["detail"]
    _nb(tmp_path, [{"src": "ax.hist(sums, bins=range(2, 14))", "n": 1, "image": True}])  # any bins, no edgecolor
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_a_slice_of_the_data_where_the_step_trains_on_all_of_it(tmp_path):
    code = "history = model.fit(train_images, train_labels, epochs=5)"
    step = _cell_step(code, "model.fit(", _typed(r"model\.fit\("))
    _nb(tmp_path, [{"src": "history = model.fit(train_images[:1000], train_labels[:1000], epochs=5)", "n": 1}])
    gate = _gate(step, workdir=str(tmp_path))
    assert not gate["passed"] and "part of train_images" in gate["checks"][-1]["detail"]
    _nb(tmp_path, [{"src": code, "n": 1}])
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_drawing_on_axes_made_in_an_earlier_cell_shows_no_figure(tmp_path):
    code = "fig, ax = plt.subplots()\nax.plot(days, temps)"
    step = _cell_step(code, "ax.plot(", _typed(r"ax\.plot\("))
    _nb(tmp_path, [{"src": "fig, ax = plt.subplots()", "n": 1, "image": True},
                   {"src": "ax.plot(days, temps)", "n": 2, "result": "[<matplotlib.lines.Line2D at 0x1>]"}])
    gate = _gate(step, workdir=str(tmp_path))
    assert not gate["passed"] and "earlier cell" in gate["checks"][-1]["detail"]
    _nb(tmp_path, [{"src": code, "n": 1, "image": True}])
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_the_after_line_prints_the_value_from_before_the_update(tmp_path):
    code = ("loss = loss_fn(model(X), y)\nprint(f'before {loss.item():.4f}')\noptimizer.zero_grad()\n"
            "loss.backward()\noptimizer.step()\nprint(f'after {loss_fn(model(X), y).item():.4f}')")
    step = _cell_step(code, "optimizer.step()", _typed(r"optimizer\.step\(\)"))
    _nb(tmp_path, [{"src": code.replace("loss_fn(model(X), y).item()", "loss.item()"), "n": 1,
                    "out": "before 0.7134\nafter 0.7134\n"}])
    gate = _gate(step, workdir=str(tmp_path))
    assert not gate["passed"] and "before it" in gate["checks"][-1]["detail"]
    _nb(tmp_path, [{"src": code, "n": 1, "out": "before 0.7134\nafter 0.7012\n"}])
    assert _gate(step, workdir=str(tmp_path))["passed"]

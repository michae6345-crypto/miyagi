"""Regression tests for the wrong verdicts the round-2 step-check evals found (server/evals/checks, train cases).
One test (or a small group) per general fix. Offline: no model, no network."""
from __future__ import annotations

import json
import struct

from server.checks import RunContext, blocks, evaluate_gate
from server.checks.code_equiv import broken_imports, equivalent_view


def _gate(step, **ctx):
    return evaluate_gate(step, RunContext(**ctx))


def _term(*rows):
    return {"Terminal": list(rows)}


def _dump(tmp_path, name, doc):
    (tmp_path / name).write_text(json.dumps(doc, indent=1))


def _obj(name, **kw):
    return {"name": name, "type": "MESH", "location": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0],
            "dimensions": [2.0, 2.0, 2.0], **kw}


# -- scene dumps read as the app evaluates them (server.checks.model_files) ------------------------------------------

def test_a_material_in_a_slot_no_face_uses_is_not_on_the_object(tmp_path):
    step = {"id": "s8", "instructions": "With the mug selected, set Roughness below 0.3.",
            "checks": [{"id": "c", "type": "file_contains", "label": "Roughness under 0.3", "file": "mug.scene.json",
                        "pattern": r"\"roughness\":\s*0\.[0-2]\d*"}]}
    slots = [{"name": "Material", "faces": 294}, {"name": "Ceramic", "faces": 0}]
    doc = {"objects": [_obj("Mug", material_slots=slots)],
           "materials": [{"name": "Material", "users": ["Mug"], "principled": {"roughness": 0.5}},
                         {"name": "Ceramic", "users": ["Mug"], "principled": {"roughness": 0.2}}]}
    _dump(tmp_path, "mug.scene.json", doc)
    assert not _gate(step, workdir=str(tmp_path))["passed"]
    slots[1]["faces"], slots[0]["faces"] = 294, 0
    _dump(tmp_path, "mug.scene.json", doc)
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_the_steps_own_comparison_between_two_named_things_is_checked(tmp_path):
    step = {"id": "s5", "instructions": "Name them Key, Fill and Rim. Give the Key at least twice the Fill's power.",
            "checks": [{"id": "c", "type": "file_contains", "label": "Key light", "file": "crate.scene.json",
                        "pattern": r"\"name\":\s*\"Key\""}]}
    lights = [{"name": "Key", "type": "AREA", "energy": 400.0}, {"name": "Fill", "type": "AREA", "energy": 300.0}]
    _dump(tmp_path, "crate.scene.json", {"objects": [_obj("Crate")], "lights": lights})
    gate = _gate(step, workdir=str(tmp_path))
    assert not gate["passed"] and "at least 2 times" in gate["checks"][-1]["detail"]
    lights[0]["energy"] = 600.0
    _dump(tmp_path, "crate.scene.json", {"objects": [_obj("Crate")], "lights": lights})
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_an_animated_value_is_its_keyframe_at_the_current_frame(tmp_path):
    step = {"id": "s3", "instructions": "Key the cube at frame 1 and at X 5 on frame 48.",
            "checks": [{"id": "c", "type": "file_contains", "label": "Cube at X 5", "file": "slide.scene.json",
                        "pattern": r"\"name\":\s*\"Cube\",\s*\"type\":\s*\"MESH\",\s*\"location\":\s*\[\s*5(?:\.0+)?,"}]}
    keys = [[1.0, 0.0], [48.0, 0.0]]
    anim = {"fcurves": [{"data_path": "location", "index": 0, "keyframes": keys}]}
    doc = {"scene": {"frame_current": 48}, "objects": [_obj("Cube", location=[5.0, 0.0, 0.0], animation=anim)]}
    _dump(tmp_path, "slide.scene.json", doc)
    assert not _gate(step, workdir=str(tmp_path))["passed"]  # the unkeyed move is lost on the next frame change
    keys[1][1] = 5.0
    _dump(tmp_path, "slide.scene.json", doc)
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_an_edit_mode_step_reads_the_mesh_size_not_the_object_scale(tmp_path):
    step = {"id": "s4", "instructions": "Press Tab for Edit mode and move one top edge up 1 m.",
            "checks": [{"id": "c", "type": "file_contains", "label": "One edge 1 m higher", "file": "w.scene.json",
                        "pattern": r"\"dimensions\":\s*\[\s*2(?:\.0+)?,\s*2(?:\.0+)?,\s*3(?:\.0+)?\s*\]"}]}
    _dump(tmp_path, "w.scene.json", {"objects": [_obj("Cube", scale=[1.0, 1.0, 1.5], dimensions=[2.0, 2.0, 3.0])]})
    assert not _gate(step, workdir=str(tmp_path))["passed"]
    _dump(tmp_path, "w.scene.json", {"objects": [_obj("Cube", dimensions=[2.0, 2.0, 3.0])]})
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_an_abandoned_sketch_is_not_the_bodys(tmp_path):
    step = {"id": "s3", "instructions": "Constrain the rectangle to 60 by 40 until Fully constrained.",
            "checks": [{"id": "a", "type": "file_contains", "label": "60 mm", "file": "p.scene.json",
                        "pattern": r"\"value\":\s*60(?:\.0+)?\b"},
                       {"id": "b", "type": "file_contains", "label": "Fully constrained", "file": "p.scene.json",
                        "pattern": r"\"dof\":\s*0\b"}]}
    old = {"name": "Sketch", "type": "Sketcher::SketchObject", "constraints": [{"value": 30.0}], "dof": 0}
    new = {"name": "Sketch001", "type": "Sketcher::SketchObject", "constraints": [{"value": 60.0}], "dof": 2}
    _dump(tmp_path, "p.scene.json", {"bodies": [{"name": "Body", "tip": "Sketch001", "features": [old, new]}]})
    assert not _gate(step, workdir=str(tmp_path))["passed"]
    pad = {"name": "Pad", "type": "PartDesign::Pad", "profile": "Sketch"}  # used by a feature: part of the body
    new["dof"] = 0
    _dump(tmp_path, "p.scene.json", {"bodies": [{"name": "Body", "tip": "Sketch001", "features": [old, pad, new]}]})
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_an_applied_scale_and_a_radius_read_as_what_they_mean(tmp_path):
    step = {"id": "s6", "instructions": "Scale the sphere to half size.",
            "checks": [{"id": "c", "type": "file_contains", "label": "Sphere at half size", "file": "s.scene.json",
                        "pattern": r"\"scale\":\s*\[\s*0\.5,\s*0\.5,\s*0\.5\s*\]"}]}
    _dump(tmp_path, "s.scene.json", {"objects": [_obj("Sphere", dimensions=[1.0, 1.0, 1.0])]})
    assert _gate(step, workdir=str(tmp_path))["passed"]  # Ctrl+A > Scale: scale 1, a 1 m UV sphere
    _dump(tmp_path, "s.scene.json", {"objects": [_obj("Sphere")]})
    assert not _gate(step, workdir=str(tmp_path))["passed"]
    holes = {"id": "s5", "instructions": "Constrain the hole's diameter to 10.2 mm.",
             "checks": [{"id": "c", "type": "file_contains", "label": "10.2 mm hole", "file": "h.scene.json",
                         "pattern": r"\"type\":\s*\"Diameter\",\s*\"value\":\s*10\.20*\b"}]}
    _dump(tmp_path, "h.scene.json", {"bodies": [{"name": "Plate", "features": [
        {"name": "Sketch", "constraints": [{"type": "Radius", "value": 5.1}]}]}]})
    assert _gate(holes, workdir=str(tmp_path))["passed"]


def _stl(tris):
    rows = ["solid m"]
    for t in tris:
        rows += ["facet normal 0 0 0", "outer loop", *(f"vertex {x} {y} {z}" for x, y, z in t), "endloop", "endfacet"]
    return "\n".join(rows + ["endsolid m"]) + "\n"


def test_a_mesh_exported_to_print_must_be_a_closed_shell(tmp_path):
    step = {"id": "s10", "title": "Export an STL to print", "instructions": "save it as hook.stl",
            "checks": [{"id": "c", "type": "file_exists", "label": "hook.stl saved", "file": "hook.stl"}]}
    a, b, c, d = (0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)
    (tmp_path / "hook.stl").write_text(_stl([(a, b, c), (a, b, d), (a, c, d)]))  # a tetrahedron missing a face
    gate = _gate(step, workdir=str(tmp_path))
    assert not gate["passed"] and "watertight" in gate["checks"][0]["detail"]
    (tmp_path / "hook.stl").write_text(_stl([(a, b, c), (a, b, d), (a, c, d), (b, c, d)]))
    assert _gate(step, workdir=str(tmp_path))["passed"]
    binary = b"\0" * 80 + struct.pack("<I", 4) + b"".join(
        struct.pack("<12fH", 0, 0, 0, *t[0], *t[1], *t[2], 0) for t in [(a, b, c), (a, b, d), (a, c, d), (b, c, d)])
    (tmp_path / "hook.stl").write_bytes(binary)
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_an_autocad_layer_name_matches_in_any_case(tmp_path):
    step = {"id": "s4", "instructions": "Make a layer named WHEELS.",
            "checks": [{"id": "c", "type": "file_contains", "label": "On the WHEELS layer", "file": "car.dxf",
                        "pattern": r"\bWHEELS\b"}]}
    (tmp_path / "car.dxf").write_text("0\nSECTION\n2\nENTITIES\n0\nCIRCLE\n8\nWheels\n40\n9.0\n0\nENDSEC\n0\nEOF\n")
    assert _gate(step, workdir=str(tmp_path))["passed"]
    (tmp_path / "car.dxf").write_text("0\nSECTION\n2\nENTITIES\n0\nTEXT\n1\nwheels\n0\nENDSEC\n0\nEOF\n")
    assert not _gate(step, workdir=str(tmp_path))["passed"]  # typed text, not a name


def test_an_autocad_command_taken_back_by_undo_does_not_count():
    step = {"id": "s1", "checks": [{"id": "c", "type": "screen_contains", "label": "profile drawn",
                                    "app": "AutoCAD", "pattern": "LINE"}]}
    rows = ["Command: LINE", "Specify first point:", "Command: UNDO",
            "Enter the number of operations to undo or [Auto/Control/BEgin/End/Mark/Back] <1>: B", "LINE",
            "Everything has been undone", "Command:"]
    assert not _gate(step, screen={"AutoCAD": rows})["passed"]
    assert blocks.undone(blocks.parse(rows)) == {0}
    assert _gate(step, screen={"AutoCAD": rows[:2] + ["Command:"]})["passed"]


# -- notebooks --------------------------------------------------------------------------------------------------------

def _nb(tmp_path, cells, name="steps.ipynb"):
    out = []
    for c in cells:
        if c.get("md"):
            out.append({"cell_type": "markdown", "metadata": {}, "source": c["src"]})
            continue
        outs = []
        if c.get("out"):
            outs.append({"output_type": "stream", "name": "stdout", "text": c["out"]})
        if c.get("err"):
            outs.append({"output_type": "error", "ename": c["err"], "evalue": "", "traceback": []})
        if c.get("image"):
            outs.append({"output_type": "display_data", "metadata": {}, "data": {"image/png": "iVBOR"}})
        out.append({"cell_type": "code", "metadata": {}, "source": c["src"], "outputs": outs,
                    "execution_count": c.get("n")})
    (tmp_path / name).write_text(json.dumps({"cells": out, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}))


MD_STEP = {"id": "m", "instructions": "Add a Markdown cell with a # title, two headings and a list.",
           "run_command": "Run the cell (Shift+Enter)",
           "checks": [{"id": "t", "type": "file_contains", "label": "Markdown title", "file": "steps.ipynb",
                       "pattern": r"\"#\s+\S"},
                      {"id": "h", "type": "file_contains", "label": "Two headings", "file": "steps.ipynb",
                       "pattern": r"(?s)\"##\s+\S.*\"##\s+\S"}]}


def test_markdown_syntax_counts_only_in_a_markdown_cell_and_any_heading_level_is_a_heading(tmp_path):
    _nb(tmp_path, [{"src": ["# Step tracker\n", "## The data\n", "## Results"], "n": 1}])
    assert not _gate(MD_STEP, workdir=str(tmp_path))["passed"]  # Python comments in a code cell
    _nb(tmp_path, [{"md": True, "src": ["# Step tracker\n", "### The data\n", "### Results"]}])
    assert _gate(MD_STEP, workdir=str(tmp_path))["passed"]


def test_an_exported_notebooks_code_is_not_its_output(tmp_path):
    step = {"id": "e", "instructions": "Export the notebook as steps.html.",
            "checks": [{"id": "c", "type": "file_contains", "label": "Chart in the export", "file": "steps.html",
                        "pattern": r"Steps\s+per\s+day|data:image/png"}]}
    code = ('<div class="jp-Cell jp-CodeCell"><div class="highlight hl-ipython3"><pre>plt.title(\'Steps per day\')\n'
            '</pre></div></div>')
    (tmp_path / "steps.html").write_text(f'<body class="jp-Notebook">\n{code}\n</body>\n')
    assert not _gate(step, workdir=str(tmp_path))["passed"]
    (tmp_path / "steps.html").write_text(f'<body class="jp-Notebook">\n{code}\n<img src="data:image/png;base64,iV">\n')
    assert _gate(step, workdir=str(tmp_path))["passed"]


FIT = {"id": "s5", "run_command": "Run the cell (Shift+Enter)", "code": "history = model.fit(x, y, epochs=5)",
       "targets": [{"app": "Code", "file": "mnist.ipynb", "match": "model.fit("}],
       "checks": [{"id": "a", "type": "metric_threshold", "label": "Accuracy reaches 0.95", "metric": "accuracy",
                   "metric_pattern": r"accuracy:\s*(?P<value>\d+\.\d+)", "op": ">=", "value": 0.95}]}


def test_a_fit_that_stopped_before_its_last_epoch_has_not_trained(tmp_path):
    rows = "".join(f"Epoch {k}/5\n1875/1875 - accuracy: 0.96{k}\n" for k in (1, 2, 3))
    _nb(tmp_path, [{"src": FIT["code"], "n": 1, "out": rows + "Epoch 4/5\n"}], "mnist.ipynb")
    assert not _gate(FIT, workdir=str(tmp_path))["passed"]  # still running, or the kernel died
    _nb(tmp_path, [{"src": FIT["code"], "n": 1, "out": rows, "err": "KeyboardInterrupt"}], "mnist.ipynb")
    assert _gate(FIT, workdir=str(tmp_path))["checks"][0]["status"] == "fail"  # stopped with an error: not pending
    _nb(tmp_path, [{"src": FIT["code"], "n": 1, "out": rows + "Epoch 4/5\n1104/1875 - accuracy: 0.97\n",
                    "err": "KeyboardInterrupt"}], "mnist.ipynb")
    assert _gate(FIT, workdir=str(tmp_path))["checks"][0]["status"] == "fail"
    done = rows + "".join(f"Epoch {k}/5\n1875/1875 - accuracy: 0.98{k}\n" for k in (4, 5))
    _nb(tmp_path, [{"src": FIT["code"], "n": 1, "out": done}], "mnist.ipynb")
    assert _gate(FIT, workdir=str(tmp_path))["passed"]
    crashed = {"Code": ["mnist.ipynb", "The Kernel crashed while executing code in the current cell or a previous cell."]}
    assert not _gate(FIT, workdir=str(tmp_path), screen=crashed)["passed"]


def test_a_cell_run_after_a_restart_without_the_cell_above_that_sets_it_up(tmp_path):
    step = {"id": "s6", "run_command": "Run the cell (Shift+Enter)", "code": "p = model.predict(x)",
            "targets": [{"app": "Code", "file": "mnist.ipynb", "match": "model.predict(x)"}],
            "checks": [{"id": "a", "type": "file_contains", "label": "predict typed", "file": "mnist.ipynb",
                        "pattern": r"model\.predict\("}]}
    cells = [{"src": "import tf", "n": 1}, {"src": "model = build()", "n": 2}, {"src": "model.fit(x, y)", "n": 19},
             {"src": "p = model.predict(x)", "n": 3, "out": "1/1 ok\n"}]
    _nb(tmp_path, cells, "mnist.ipynb")
    gate = _gate(step, workdir=str(tmp_path))
    assert not gate["passed"] and "model" in gate["checks"][-1]["detail"]
    cells[2]["n"], cells[3]["n"] = 3, 4  # Run All after the restart: the fit ran before the predict
    _nb(tmp_path, cells, "mnist.ipynb")
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_every_cell_of_a_two_cell_step_must_have_run(tmp_path):
    step = {"id": "t", "run_command": "Run the cell (Shift+Enter)",
            "code": "%timeit sum(steps)\n\nsteps_array = np.array(steps)\n%timeit np.sum(steps_array)",
            "targets": [{"app": "Code", "file": "steps.ipynb", "match": "%timeit sum(steps)"}],
            "checks": [{"id": "a", "type": "file_contains", "label": "timeit typed", "file": "steps.ipynb",
                        "pattern": r"%timeit"}]}
    cells = [{"src": "%timeit sum(steps)", "n": 2, "out": "98 ns per loop\n"},
             {"src": "steps_array = np.array(steps)\n%timeit np.sum(steps_array)"}]
    _nb(tmp_path, cells)
    assert not _gate(step, workdir=str(tmp_path))["passed"]
    cells[1].update(n=3, out="1 us per loop\n")
    _nb(tmp_path, cells)
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_a_metric_printed_as_bare_numbers_by_the_steps_own_print_is_read(tmp_path):
    step = {"id": "x", "run_command": "Run the cell (Shift+Enter)", "code": "for epoch in range(2000):\n    pass",
            "targets": [{"app": "Code", "file": "xor.ipynb", "match": "for epoch in range(2000):"}],
            "checks": [{"id": "a", "type": "metric_trend", "label": "loss falls", "metric": "loss",
                        "metric_pattern": r"epoch\s+(?P<step>\d+)\s+loss\s+(?P<value>[0-9.eE+-]+)",
                        "trend": "decreasing", "window": 2000}]}
    rows = "".join(f"{e} {0.26 * 0.7 ** (e // 200)}\n" for e in range(0, 2000, 200))
    _nb(tmp_path, [{"src": "for epoch in range(2000):\n    print(epoch, loss.item())", "n": 1, "out": rows}],
        "xor.ipynb")
    assert _gate(step, workdir=str(tmp_path))["passed"]
    _nb(tmp_path, [{"src": "for epoch in range(2000):\n    print(epoch, acc)", "n": 1, "out": rows}], "xor.ipynb")
    assert not _gate(step, workdir=str(tmp_path))["passed"]  # its print isn't the loss


def test_a_matrix_drawn_as_a_figure_reads_as_the_printed_matrix(tmp_path):
    step = {"id": "k", "run_command": "Run the cell (Shift+Enter)", "code": "print(accuracy_score(y, p))",
            "targets": [{"app": "Code", "file": "wine.ipynb", "match": "accuracy_score(y, p)"}],
            "checks": [{"id": "a", "type": "screen_contains", "label": "3 by 3 matrix printed", "app": "Code",
                        "output": True, "pattern": r"\[\[\s*\d+\s+\d+\s+\d+\s*\]\s*\[\s*\d+\s+\d+\s+\d+\s*\]"
                                                   r"\s*\[\s*\d+\s+\d+\s+\d+\s*\]\]"}]}
    screen = {"Code": ["wine.ipynb", "0 13 0 1", "True label 1 1 11 4", "2 2 5 8", "0 1 2", "Predicted label"]}
    _nb(tmp_path, [{"src": "print(accuracy_score(y, p))\nConfusionMatrixDisplay.from_predictions(y, p)", "n": 2,
                    "out": "0.71\n", "image": True}], "wine.ipynb")
    assert _gate(step, workdir=str(tmp_path), screen=screen)["passed"]
    _nb(tmp_path, [{"src": "print(accuracy_score(y, p))", "n": 2, "out": "0.71\n"}], "wine.ipynb")
    assert not _gate(step, workdir=str(tmp_path), screen=screen)["passed"]  # no figure: those numbers are not it


# -- terminal history -------------------------------------------------------------------------------------------------

def test_a_mistyped_git_command_is_a_failure():
    step = {"id": "s1", "checks": [{"id": "c", "type": "screen_contains", "label": "alias set", "app": "Terminal",
                                    "pattern": r"alias\s*\.\s*i"}]}
    assert not _gate(step, screen=_term("me@mac ~ % git confg --global alias.i init",
                                        "git: 'confg' is not a git command. See 'git --help'.", "me@mac ~ % "))["passed"]


def test_a_label_naming_a_git_status_section_wants_the_file_there():
    step = {"id": "s3", "checks": [{"id": "c", "type": "screen_contains", "label": "Untracked waiting.py shown",
                                    "app": "Terminal", "pattern": r"waiting\.py"}]}
    status = ["me@mac p % git status", "Changes to be committed:", "  new file:   learning.py"]
    bad = status + ["  new file:   waiting.py", "me@mac p % "]
    ok = status + ["", "Untracked files:", "  waiting.py", "me@mac p % "]
    assert not _gate(step, screen=_term("me@mac p % touch waiting.py", *bad))["passed"]
    assert _gate(step, screen=_term("me@mac p % touch waiting.py", *ok))["passed"]


DEV = {"id": "s1", "instructions": "Create my-react-app with npm create vite, then npm run dev.",
       "targets": [{"app": "Terminal", "match": "npm run dev"}],
       "checks": [{"id": "c", "type": "screen_contains", "label": "Vite ready", "app": "Terminal",
                   "pattern": r"ready\s+in"}],
       "precision_checks": [{"id": "p", "type": "file_exists", "label": "app made", "file": "my-react-app/package.json"}]}


def test_the_steps_command_run_in_another_project_folder_does_not_count(tmp_path):
    (tmp_path / "shop").mkdir()
    rows = ["me@mac shop % npm run dev", "> shop@0.0.0 dev", "VITE v5.4.10  ready in 287 ms"]
    gate = _gate(DEV, workdir=str(tmp_path), screen=_term(*rows))
    assert not gate["passed"] and "ran in shop" in gate["checks"][0]["detail"]
    (tmp_path / "my-app").mkdir()  # the learner's own name for the project, made on screen: fine
    rows = ["me@mac Desktop % npm create vite@latest my-app", "me@mac my-app % npm run dev", "VITE ready in 287 ms"]
    assert _gate(DEV, workdir=str(tmp_path), screen=_term(*rows))["passed"]
    assert blocks.prompt_dir("me@box:~/a/lesson1$ ls") == "lesson1" and blocks.prompt_dir("me@mac ~ % pwd") == "~"


def test_a_command_the_step_names_that_failed_and_was_never_rerun():
    step = {"id": "s8", "instructions": "Commit the edit on update-name, and push to origin.",
            "targets": [{"app": "Terminal", "match": "git push origin update-name"}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "pushed", "app": "Terminal",
                        "pattern": r"update-name\s*->\s*update-name"}]}
    rows = ["me@mac g % git commit -m \"x\"", "no changes added to commit", "me@mac g % git push origin update-name",
            " * [new branch]      update-name -> update-name", "me@mac g % "]
    assert not _gate(step, screen=_term(*rows))["passed"]
    fixed = rows[:2] + ["me@mac g % git commit -am \"x\"", "[update-name 1a2b3c] x"] + rows[2:]
    assert _gate(step, screen=_term(*fixed))["passed"]


def test_a_test_run_of_one_selected_test_is_not_the_whole_suite():
    step = {"id": "m5", "run_command": "python3 -m pytest -q",
            "checks": [{"id": "c", "type": "screen_contains", "label": "tests passed", "app": "Terminal",
                        "pattern": r"\d+\s+passed"}]}
    assert not _gate(step, screen=_term("me@mac c % python3 -m pytest -q test_ops.py::test_add", "1 passed in 0.01s",
                                        "me@mac c % "))["passed"]
    assert _gate(step, screen=_term("me@mac c % python3 -m pytest -q", "3 passed in 0.01s", "me@mac c % "))["passed"]
    assert blocks.narrows("pytest -k add", "pytest") and not blocks.narrows("pytest -q", "pytest -q")


def test_a_home_folder_check_wants_the_prompts_own_user():
    step = {"id": "s5", "targets": [{"app": "Terminal", "match": "pwd"}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "pwd prints your home folder",
                        "app": "Terminal", "pattern": r"^/Users/[^/\s]+\s*$"}]}
    assert not _gate(step, screen=_term("tripi@mac Shared % pwd", "/Users/Shared", "tripi@mac Shared % "))["passed"]
    assert _gate(step, screen=_term("tripi@mac ~ % pwd", "/Users/tripi", "tripi@mac ~ % "))["passed"]


def test_a_label_that_says_each_holds_for_every_row_of_that_shape():
    step = {"id": "s5", "targets": [{"app": "Terminal", "match": "wc -l"}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "wc -l counts 3 lines per note",
                        "app": "Terminal", "pattern": r"^\s*3\s+\S+\.txt\s*$"}]}
    rows = ["me@mac t % wc -l a.txt b.txt", "  3 a.txt", "  {} b.txt", "  6 total", "me@mac t % "]
    assert not _gate(step, screen=_term(*[r.format(2) for r in rows]))["passed"]
    assert _gate(step, screen=_term(*[r.format(3) for r in rows]))["passed"]


def test_text_the_learner_quoted_keeps_its_own_case():
    step = {"id": "s5", "targets": [{"app": "Terminal", "match": "git commit -m"}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "Commit recorded", "app": "Terminal",
                        "pattern": r"add\s+waiting\s+file"}]}
    assert _gate(step, screen=_term("me@mac p % git commit -m \"Add waiting file\"", "[main 4b5c6d7] Add waiting file",
                                    "me@mac p % "))["passed"]
    assert not _gate(step, screen=_term("me@mac p % git log", "4b5c6d7 Add Waiting File", "me@mac p % "))["passed"]


# -- code across files (server.checks.code_equiv) ---------------------------------------------------------------------

def test_a_name_used_but_never_imported_from_the_module_that_defines_it(tmp_path):
    (tmp_path / "operations.py").write_text("def add(a, b):\n    return a + b\n\ndef add_numbers(a, b):\n"
                                            "    return add(a, b)\n")
    (tmp_path / "main.py").write_text("from operations import add\n\nprint(add_numbers(2, 3))\n")
    assert broken_imports(str(tmp_path), ["main.py"]) == [
        "main.py uses add_numbers, which it never imports (it is defined in operations.py)"]
    (tmp_path / "main.py").write_text("from operations import add_numbers\n\nprint(add_numbers(2, 3))\n")
    assert broken_imports(str(tmp_path), ["main.py"]) == []


def test_a_require_of_a_name_the_module_no_longer_exports_and_a_missing_relative_import(tmp_path):
    (tmp_path / "utils.js").write_text("function scaleRecipe(r, f) {}\n\nmodule.exports = { scaleRecipe }\n")
    (tmp_path / "scale.js").write_text("const { scale } = require('./utils')\nscaleRecipe([], 2)\n")
    assert broken_imports(str(tmp_path), ["scale.js"]) == ["scale.js requires scale from utils.js, which doesn't export it"]
    (tmp_path / "scale.js").write_text("const { scaleRecipe } = require('./utils')\nscaleRecipe([], 2)\n")
    assert broken_imports(str(tmp_path), ["scale.js"]) == []
    (tmp_path / "src" / "components").mkdir(parents=True)
    (tmp_path / "src" / "components" / "Header.jsx").write_text("export default function Header() {}\n")
    (tmp_path / "src" / "App.jsx").write_text("import Header from './Header'\n")
    assert "doesn't exist" in broken_imports(str(tmp_path), ["src/App.jsx"])[0]
    (tmp_path / "src" / "App.jsx").write_text("import Header from './components/Header'\n")
    assert broken_imports(str(tmp_path), ["src/App.jsx"]) == []


def test_an_arrow_function_bound_to_a_name_is_that_function():
    view = equivalent_view("const scaleRecipe = (recipe, factor) =>\n  recipe.map(x => x)\n", "utils.js")
    assert view is not None and "function scaleRecipe(recipe, factor)" in view
    assert "function double(x)" in equivalent_view("export const double = x => x * 2\n", "m.ts")


def test_an_import_through_a_tsconfig_path_alias_reads_as_the_relative_import(tmp_path):
    (tmp_path / "shop" / "src" / "components").mkdir(parents=True)
    (tmp_path / "shop" / "tsconfig.json").write_text(
        '{\n  // aliases\n  "compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]},},\n}\n')
    (tmp_path / "shop" / "src" / "components" / "Cart.tsx").write_text("import { formatPrice } from '@/utils'\n")
    step = {"id": "t2", "file": "src/components/Cart.tsx",
            "checks": [{"id": "c", "type": "screen_contains", "label": "Cart imports formatPrice", "app": "Code",
                        "pattern": r"import\s*\{\s*formatPrice\s*\}\s*from\s*['\"]\.\./utils['\"]"}]}
    screen = {"Code": ["Cart.tsx", "import { formatPrice } from '@/utils'"]}
    assert _gate(step, workdir=str(tmp_path), screen=screen)["passed"]
    assert not _gate(step, workdir=str(tmp_path), screen={"Code": ["import { formatPrice } from '@/other'"]})["passed"]


def test_a_label_naming_a_file_not_open_on_screen_is_read_from_disk(tmp_path):
    (tmp_path / "operations.py").write_text("def add_numbers(a, b):\n    return a + b\n")
    (tmp_path / "main.py").write_text("from operations import add_numbers\n\nprint(add_numbers(2, 3))\n")
    step = {"id": "m4", "file": "operations.py",
            "checks": [{"id": "c", "type": "screen_contains", "label": "main.py calls add_numbers(2, 3)",
                        "app": "Code", "pattern": r"add_numbers\(2,\s*3\)"}]}
    assert _gate(step, workdir=str(tmp_path), screen={"Code": ["operations.py", "def add_numbers(a, b):"]})["passed"]
    (tmp_path / "main.py").write_text("from operations import add_numbers\n\nprint(add_numbers(1, 3))\n")
    assert not _gate(step, workdir=str(tmp_path), screen={"Code": ["operations.py", "def add_numbers(a, b):"]})["passed"]


def test_a_config_key_outside_the_section_the_steps_code_puts_it_in(tmp_path):
    step = {"id": "ts", "code": '{\n  "compilerOptions": {\n    "outDir": "dist",\n    "strict": true\n  }\n}',
            "checks": [{"id": "c", "type": "file_contains", "label": "strict on", "file": "tsconfig.json",
                        "pattern": r"\"strict\"\s*:\s*true"}]}
    (tmp_path / "tsconfig.json").write_text('{\n  "strict": true,\n  "compilerOptions": {"outDir": "dist"}\n}\n')
    gate = _gate(step, workdir=str(tmp_path))
    assert not gate["passed"] and "compilerOptions" in gate["checks"][0]["detail"]
    (tmp_path / "tsconfig.json").write_text('{\n  // strict mode\n  "compilerOptions": {"strict": true,},\n}\n')
    assert _gate(step, workdir=str(tmp_path))["passed"]

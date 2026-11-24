"""Regression tests for the wrong verdicts the round-5 step-check evals found (server/evals/checks, train cases).
One test per general fix, each with the finished form that must still pass. Offline: no model, no network."""
from __future__ import annotations

import json
import struct

from server.checks import RunContext, blocks, evaluate_gate
from server.checks.code_equiv import broken_imports, equivalent_view
from server.checks.evaluator import printed_forms


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
            "scale": [1.0, 1.0, 1.0], "dimensions": [2.0, 2.0, 2.0], "parent": None, "modifiers": [], **kw}


def _scene_step(instructions, checks, title=""):
    return {"id": "s", "title": title, "instructions": instructions, "checks": checks}


_IDS = iter(range(10_000))


def _fc(pattern, label, file="s.scene.json"):
    return {"id": f"c{next(_IDS)}", "type": "file_contains", "label": label, "file": file, "pattern": pattern}


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
        if c.get("error"):
            ename, evalue = c["error"].split(": ", 1)
            outs.append({"output_type": "error", "ename": ename, "evalue": evalue, "traceback": []})
        out.append({"cell_type": "code", "metadata": {}, "source": c["src"], "outputs": outs,
                    "execution_count": c.get("n")})
    _write(tmp_path, name, json.dumps({"cells": out, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}))


def _cell_step(code, match, checks, instructions="", file="nb.ipynb", **kw):
    return {"id": "s", "run_command": "Run the cell (Shift+Enter)", "code": code, "file": file,
            "instructions": instructions, "targets": [{"app": "Code", "file": file, "match": match}],
            "checks": checks, **kw}


def _typed(pattern, file="nb.ipynb"):
    return [{"id": "c", "type": "file_contains", "label": "typed", "file": file, "pattern": pattern}]


def _printed(pattern, label="printed"):
    return [{"id": "o", "type": "screen_contains", "label": label, "app": "Code", "output": True, "pattern": pattern}]


# -- Blender / FreeCAD / Fusion / AutoCAD: what the saved model is ------------------------------------------------------

def _material(nodes, links):
    return {"name": "Wood", "users": ["Crate"], "use_nodes": True, "nodes": nodes, "links": links}


def test_non_color_goes_on_the_image_that_feeds_a_number_input(tmp_path):
    step = _scene_step("Connect the roughness image to Roughness and set that node's Color Space to Non-Color.",
                       [_fc(r'"colorspace":\s*"Non-Color"', "Non-Color set")])
    nodes = [{"name": "Principled BSDF", "type": "BSDF_PRINCIPLED"},
             {"name": "Image Texture", "type": "TEX_IMAGE", "image": "diffuse.png", "colorspace": "Non-Color"},
             {"name": "Image Texture.001", "type": "TEX_IMAGE", "image": "rough.png", "colorspace": "sRGB"}]
    links = [{"from": "Image Texture", "from_socket": "Color", "to": "Principled BSDF", "to_socket": "Base Color"},
             {"from": "Image Texture.001", "from_socket": "Color", "to": "Principled BSDF", "to_socket": "Roughness"}]
    _dump(tmp_path, "s.scene.json", {"objects": [_obj("Crate")], "materials": [_material(nodes, links)]})
    assert not _gate(step, workdir=str(tmp_path))["passed"]
    nodes[1]["colorspace"], nodes[2]["colorspace"] = "sRGB", "Non-Color"
    _dump(tmp_path, "s.scene.json", {"objects": [_obj("Crate")], "materials": [_material(nodes, links)]})
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_a_packed_image_is_still_the_file_it_was_opened_from(tmp_path):
    step = _scene_step("Open the .hdr file in an Environment Texture.",
                       [_fc(r'"filepath":\s*"[^"]*\.(?:hdr|exr)"', "HDR or EXR image")])
    img = {"name": "sky_2k.hdr", "filepath": "", "packed": True, "has_data": True}
    _dump(tmp_path, "s.scene.json", {"objects": [_obj("Crate")], "images": [img]})
    assert _gate(step, workdir=str(tmp_path))["passed"]
    img["packed"] = False  # not packed and no path: no image file at all
    _dump(tmp_path, "s.scene.json", {"objects": [_obj("Crate")], "images": [img]})
    assert not _gate(step, workdir=str(tmp_path))["passed"]


def test_every_blade_the_step_parents_has_the_parent(tmp_path):
    step = _scene_step("Select all three blades, then the Hub last, and press Ctrl+P > Object.",
                       [_fc(r'"parent":\s*"Hub"', "Blades parented to the hub")])
    objs = [_obj("Hub"), _obj("Blade1", parent="Hub"), _obj("Blade2", parent="Hub"), _obj("Blade3")]
    _dump(tmp_path, "s.scene.json", {"objects": objs})
    gate = _gate(step, workdir=str(tmp_path))
    assert not gate["passed"] and "Blade3" in gate["checks"][-1]["detail"]
    objs[3]["parent"] = "Hub"
    _dump(tmp_path, "s.scene.json", {"objects": objs})
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_a_modifier_of_size_zero_changes_nothing(tmp_path):
    step = _scene_step("Add a Bevel modifier to the Mug, Amount 0.02 m, Segments 3.",
                       [_fc(r'"type":\s*"BEVEL"', "Bevel modifier"), _fc(r'"segments":\s*3\b', "3 segments")])
    bevel = {"name": "Bevel", "type": "BEVEL", "width": 0.0, "segments": 3}
    _dump(tmp_path, "s.scene.json", {"objects": [_obj("Mug", modifiers=[bevel])]})
    assert not _gate(step, workdir=str(tmp_path))["passed"]
    bevel["width"] = 0.02
    _dump(tmp_path, "s.scene.json", {"objects": [_obj("Mug", modifiers=[bevel])]})
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_a_named_material_in_a_slot_no_face_uses(tmp_path):
    step = _scene_step("Give the Mug a material named Glaze with Roughness 0.2.",
                       [_fc(r'"name":\s*"Glaze"', "Material named Glaze"),
                        _fc(r'"users":\s*\[[^\]]*"Mug"', "On the mug")])
    mats = [{"name": "Material", "users": ["Mug"]}, {"name": "Glaze", "users": ["Mug"]}]
    slots = [{"slot": 0, "material": "Material", "faces": 254}, {"slot": 1, "material": "Glaze", "faces": 0}]
    _dump(tmp_path, "s.scene.json", {"objects": [_obj("Mug", material_slots=slots)], "materials": mats})
    assert not _gate(step, workdir=str(tmp_path))["passed"]
    slots[1]["faces"] = 254
    slots[0]["faces"] = 0
    _dump(tmp_path, "s.scene.json", {"objects": [_obj("Mug", material_slots=slots)], "materials": mats})
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_each_link_the_step_spells_out_is_in_the_node_tree(tmp_path):
    step = _scene_step("Connect the Noise's Fac to the Color Ramp's Fac and the Color Ramp's Color to the Principled "
                       "BSDF's Base Color.", [_fc(r'"to_socket":\s*"Base Color"', "Feeds Base Color")])
    nodes = [{"name": "Principled BSDF", "type": "BSDF_PRINCIPLED"}, {"name": "Noise Texture", "type": "TEX_NOISE"},
             {"name": "Color Ramp", "type": "VALTORGB"}]
    links = [{"from": "Noise Texture", "from_socket": "Color", "to": "Principled BSDF", "to_socket": "Base Color"},
             {"from": "Noise Texture", "from_socket": "Fac", "to": "Color Ramp", "to_socket": "Fac"},
             {"from": "Color Ramp", "from_socket": "Color", "to": "Principled BSDF", "to_socket": "Roughness"}]
    doc = {"objects": [_obj("Sphere")], "materials": [{"name": "M", "users": ["Sphere"], "nodes": nodes,
                                                      "links": links}]}
    _dump(tmp_path, "s.scene.json", doc)
    gate = _gate(step, workdir=str(tmp_path))
    assert not gate["passed"] and "Roughness" in gate["checks"][-1]["detail"]
    links[0], links[2]["to_socket"] = links[1], "Base Color"
    _dump(tmp_path, "s.scene.json", doc)
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_a_light_switched_to_area_is_an_area_light(tmp_path):
    step = _scene_step("Add an Area light above the mug.",
                       [_fc(r'"name":\s*"Area"[\s\S]*?"type":\s*"AREA"', "An area light")])
    doc = {"objects": [_obj("Mug"), _obj("Light", type="LIGHT")], "lights": [{"name": "Light", "type": "AREA"}]}
    _dump(tmp_path, "s.scene.json", doc)
    assert _gate(step, workdir=str(tmp_path))["passed"]
    doc["lights"][0]["type"] = "POINT"
    _dump(tmp_path, "s.scene.json", doc)
    assert not _gate(step, workdir=str(tmp_path))["passed"]


def _plate(holes, pocket_type="ThroughAll"):
    return {"bodies": [{"name": "Body", "tip": "Pocket", "features": [
        {"name": "Pad", "type": "PartDesign::Pad", "Length": 5.0},
        {"name": "Pocket", "type": "PartDesign::Pocket", "Type": pocket_type, "Length": 5.0}],
        "shape": {"valid": True, "bound_box": [60.0, 40.0, 5.0], "holes": holes}}]}


def test_two_holes_the_step_cuts_are_both_in_the_body(tmp_path):
    step = _scene_step("Draw two circles and Pocket them Through all: two 4 mm holes.",
                       [_fc(r'"type":\s*"PartDesign::Pocket"', "Pocket added")])
    hole = {"diameter": 4.0, "center": [10.0, 20.0], "through": True}
    _dump(tmp_path, "s.scene.json", _plate([hole]))
    assert not _gate(step, workdir=str(tmp_path))["passed"]
    _dump(tmp_path, "s.scene.json", _plate([hole, {**hole, "center": [50.0, 20.0]}]))
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_a_pocket_that_cuts_through_is_through_all(tmp_path):
    step = _scene_step("Click Pocket and set Type to Through all.",
                       [_fc(r'"Type":\s*"ThroughAll"', "Through all")])
    hole = {"diameter": 4.0, "center": [10.0, 20.0], "through": True}
    _dump(tmp_path, "s.scene.json", _plate([hole], pocket_type="Length"))
    assert _gate(step, workdir=str(tmp_path))["passed"]
    _dump(tmp_path, "s.scene.json", _plate([{**hole, "through": False}], pocket_type="Length"))
    assert not _gate(step, workdir=str(tmp_path))["passed"]


def test_a_hole_extrude_cut_through_the_wall_is_a_hole(tmp_path):
    step = _scene_step("Click Hole and pick one short wall; set the diameter to 8 mm.",
                       [_fc(r'"type":\s*"Hole"', "Hole feature added", "box.design.json"),
                        _fc(r'"diameter":\s*8(?:\.0+)?\b', "8 mm across", "box.design.json")])
    doc = {"components": [{"name": "Base", "bodies": [{"name": "Body1", "bound_box": [80.0, 50.0, 30.0],
                                                      "through_holes": [{"diameter": 8.0, "axis": [1.0, 0.0, 0.0]}]}]}],
           "features": [{"name": "Extrude2", "type": "Extrude", "operation": "Cut"}]}
    _dump(tmp_path, "box.design.json", doc)
    assert _gate(step, workdir=str(tmp_path))["passed"]
    doc["components"][0]["bodies"][0]["through_holes"] = []
    _dump(tmp_path, "box.design.json", doc)
    assert not _gate(step, workdir=str(tmp_path))["passed"]


def test_a_sketch_on_another_base_plane_than_the_step_picks(tmp_path):
    step = _scene_step("Click Create sketch, pick XY_Plane and draw one rectangle.",
                       [_fc(r'"closed_wires":\s*1\b', "One closed rectangle")])
    sketch = {"name": "Sketch", "type": "Sketcher::SketchObject", "support": "XZ_Plane", "closed_wires": 1}
    _dump(tmp_path, "s.scene.json", {"bodies": [{"name": "Body", "tip": "Sketch", "features": [sketch]}]})
    assert not _gate(step, workdir=str(tmp_path))["passed"]
    sketch["support"] = "XY_Plane"
    _dump(tmp_path, "s.scene.json", {"bodies": [{"name": "Body", "tip": "Sketch", "features": [sketch]}]})
    assert _gate(step, workdir=str(tmp_path))["passed"]


def _box_stl(path, x, y, z):
    corners = [(0, 0, 0), (x, 0, 0), (x, y, 0), (0, y, z)]
    tris = [corners[:3], corners[1:]]
    data = b"\0" * 80 + struct.pack("<I", len(tris))
    for t in tris:
        data += struct.pack("<12f", 0, 0, 0, *[c for v in t for c in v]) + b"\0\0"
    path.write_bytes(data)


def test_an_stl_exported_from_one_feature_is_not_the_body(tmp_path):
    step = _scene_step("Select the Body and export hook.stl.",
                       [{"id": "c", "type": "file_exists", "label": "hook.stl saved", "file": "hook.stl"}])
    _dump(tmp_path, "hook.scene.json", {"bodies": [{"name": "Body", "shape": {"bound_box": [60.0, 40.0, 35.0]}}]})
    _box_stl(tmp_path / "hook.stl", 60.0, 40.0, 5.0)
    gate = _gate(step, workdir=str(tmp_path))
    assert not gate["passed"] and "60 x 40 x 35" in gate["checks"][-1]["detail"]
    _box_stl(tmp_path / "hook.stl", 40.0, 60.0, 35.0)  # the whole body, in any orientation
    assert _gate(step, workdir=str(tmp_path))["passed"]


def _dxf(radius):
    ents = [("CIRCLE", [(8, "WHEELS"), (10, "25.0"), (20, "0.0"), (40, str(radius))]),
            ("CIRCLE", [(8, "WHEELS"), (10, "95.0"), (20, "0.0"), (40, str(radius))])]
    rows = ["0", "SECTION", "2", "ENTITIES"]
    for t, groups in ents:
        rows += ["0", t] + [x for c, v in groups for x in (str(c), v)]
    return "\n".join(rows + ["0", "ENDSEC", "0", "EOF"]) + "\n"


def test_a_circle_drawn_with_its_diameter_typed_as_the_radius(tmp_path):
    step = _scene_step("Run CIRCLE, click 25,0, type D for Diameter and enter 18; repeat at 95,0.",
                       [_fc(r"\bCIRCLE\b", "Two wheel circles", "car.dxf"),
                        _fc(r"\b18(?:\.0+)?\b", "Wheels 18 mm across", "car.dxf")])
    _write(tmp_path, "car.dxf", _dxf(18.0))
    gate = _gate(step, workdir=str(tmp_path))
    assert not gate["passed"] and "36" in gate["checks"][-1]["detail"]
    _write(tmp_path, "car.dxf", _dxf(9.0))
    step["checks"][1]["pattern"] = r"\b9(?:\.0+)?\b"
    assert _gate(step, workdir=str(tmp_path))["passed"]


# -- Jupyter notebooks --------------------------------------------------------------------------------------------------

def test_positional_numbers_the_step_spells_out(tmp_path):
    code = "fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))\nax1.plot(x)"
    step = _cell_step(code, "plt.subplots(", _typed(r"plt\.subplots\("),
                      instructions="Make fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4)) so they share a row.")
    _nb(tmp_path, [{"src": code.replace("(1, 2", "(2, 1"), "n": 1, "image": True}])
    gate = _gate(step, workdir=str(tmp_path))
    assert not gate["passed"] and "subplots(2, 1" in gate["checks"][-1]["detail"]
    _nb(tmp_path, [{"src": code, "n": 1, "image": True}])
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_a_step_done_in_one_cell_split_over_two(tmp_path):
    code = "rng = np.random.default_rng(42)\nrolls = rng.integers(1, 7, size=(1000, 2))\nprint('sevens:', 3)"
    step = _cell_step(code, "np.random.default_rng(42)", _typed(r"default_rng\(42\)"),
                      instructions="In one cell make rng = np.random.default_rng(42) and roll the dice.")
    _nb(tmp_path, [{"src": "import numpy as np\nrng = np.random.default_rng(42)", "n": 1},
                   {"src": "rolls = rng.integers(1, 7, size=(1000, 2))\nprint('sevens:', 3)", "n": 3, "out": "x\n"}])
    assert not _gate(step, workdir=str(tmp_path))["passed"]
    _nb(tmp_path, [{"src": "import numpy as np", "n": 1}, {"src": code, "n": 2, "out": "sevens: 3\n"}])
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_a_copy_returning_method_whose_result_is_dropped(tmp_path):
    code = "model = model.to(device)\nxb = xb.to(device)\nprint(xb.device)"
    step = _cell_step(code, "xb.device", _typed(r"\.to\(device\)"))
    setup = {"src": "model = nn.Sequential(nn.Linear(2, 1))\nxb = torch.zeros(2)", "n": 1}
    _nb(tmp_path, [setup, {"src": "model = model.to(device)\nxb.to(device)\nprint(xb.device)", "n": 2}])
    gate = _gate(step, workdir=str(tmp_path))
    assert not gate["passed"] and "xb = xb.to(device)" in gate["checks"][-1]["detail"]
    _nb(tmp_path, [setup, {"src": "model.to(device)\nxb = xb.to(device)\nprint(xb.device)", "n": 2}])
    assert _gate(step, workdir=str(tmp_path))["passed"]  # a model moves in place


def test_a_device_shown_as_out_reads_as_printed():
    shown = printed_forms("(device(type='mps', index=0), device(type='mps', index=0))")
    assert "mps:0 mps:0" in shown
    assert "cpu" in printed_forms("device(type='cpu')")
    assert printed_forms("(133, 13)") == "(133, 13)"  # any other tuple stays as shown


def test_an_earlier_cells_error_the_step_cell_got_past(tmp_path):
    code = "import matplotlib.pyplot as plt\nplt.bar(days, steps)\nplt.show()"
    checks = [*_typed(r"plt\.bar\("), {"id": "e", "type": "screen_absent", "label": "No cell error", "app": "Code",
                                       "pattern": r"Traceback|\w+Error"}]
    step = _cell_step(code, "plt.bar(days, steps)", checks)
    err = "ModuleNotFoundError: No module named 'matplotlib'"
    screen = {"Code": ["[2]", "import matplotlib.pyplot as plt", err, "[4]", *code.splitlines()]}
    _nb(tmp_path, [{"src": "import matplotlib.pyplot as plt", "n": 2, "error": err},
                   {"src": "%pip install matplotlib", "n": 3, "out": "Successfully installed matplotlib\n"},
                   {"src": code, "n": 4, "image": True}])
    assert _gate(step, workdir=str(tmp_path), screen=screen)["passed"]
    _nb(tmp_path, [{"src": "import matplotlib.pyplot as plt", "n": 5, "error": err},  # it raised after the chart cell
                   {"src": code, "n": 4, "image": True}])
    assert not _gate(step, workdir=str(tmp_path), screen=screen)["passed"]


def test_run_all_counts_skip_a_number(tmp_path):
    step = {"id": "s", "file": "nb.ipynb", "run_command": "Restart the kernel, then run all cells",
            "targets": [{"app": "Code", "file": "nb.ipynb"}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "Cells numbered from [1]", "app": "Code",
                        "pattern": r"\[\s*1\s*\]"}]}
    screen = {"Code": ["[1]", "steps = [1, 2]"]}
    _nb(tmp_path, [{"src": "steps = [1, 2]", "n": 1}, {"src": "x = goal", "n": 3}, {"src": "print(x)", "n": 4}])
    assert not _gate(step, workdir=str(tmp_path), screen=screen)["passed"]
    _nb(tmp_path, [{"src": "steps = [1, 2]", "n": 1}, {"src": "x = 8", "n": 2}, {"src": "print(x)", "n": 3}])
    assert _gate(step, workdir=str(tmp_path), screen=screen)["passed"]
    # the last cell run once more after Run All: a gap, but every name is still made, so Run All would work
    _nb(tmp_path, [{"src": "steps = [1, 2]", "n": 1}, {"src": "x = 8", "n": 2}, {"src": "print(x)", "n": 4}])
    assert _gate(step, workdir=str(tmp_path), screen=screen)["passed"]


def test_a_progress_line_silenced_with_verbose_0(tmp_path):
    code = "loss, acc = model.evaluate(x, y)\nprint(f'Accuracy: {acc * 100:.2f}%')"
    checks = [*_printed(r"Accuracy:\s*\d", "Accuracy printed"),
              {"id": "p", "type": "screen_contains", "label": "evaluate progress output shown", "app": "Code",
               "output": True, "pattern": r"accuracy:\s*0\.\d+"}]
    step = _cell_step(code, "model.evaluate(x, y)", checks)
    _nb(tmp_path, [{"src": code.replace("(x, y)", "(x, y, verbose=0)"), "n": 2, "out": "Accuracy: 97.59%\n"}])
    assert _gate(step, workdir=str(tmp_path))["passed"]
    _nb(tmp_path, [{"src": code, "n": 2, "out": "Accuracy: 97.59%\n"}])  # verbose on and no progress line: not run
    assert not _gate(step, workdir=str(tmp_path))["passed"]


# -- code files (Python, JS / React / TS) -------------------------------------------------------------------------------

def test_a_module_file_whose_case_differs_from_the_import(tmp_path):
    _write(tmp_path, "main.py", "from operations import add\n\nprint(add(2, 3))\n")
    _write(tmp_path, "Operations.py", "def add(a, b):\n    return a + b\n")
    why = broken_imports(str(tmp_path), ["main.py"])
    assert why and "Operations.py" in why[0]
    (tmp_path / "Operations.py").rename(tmp_path / "tmp.py")
    (tmp_path / "tmp.py").rename(tmp_path / "operations.py")
    assert broken_imports(str(tmp_path), ["main.py"]) == []


def test_a_value_kept_in_a_name_for_the_next_line():
    view = equivalent_view("from operations import add\n\ntotal = add(2, 3)\nprint(total)\n", "main.py") or ""
    assert "print(add(2, 3))" in view
    view = equivalent_view("total = add(2, 3)\nprint(total)\nprint(total * 2)\n", "main.py") or ""
    assert "print(add(2, 3))" not in view  # used twice: not a temporary


def test_export_default_function_is_a_default_export():
    view = equivalent_view("export default function Food() {\n  return <ul/>\n}\n", "Food.jsx") or ""
    assert "export default Food" in view


def _react(tmp_path, rel, text):
    _write(tmp_path, f"app/{rel}", text)


def test_a_page_that_threw_in_the_browser(tmp_path):
    step = {"id": "s", "file": "src/App.jsx", "run_command": "npm run dev", "instructions": "Check the browser.",
            "checks": [{"id": "c", "type": "screen_contains", "label": "className", "app": "Code",
                        "pattern": r"className="}]}
    _react(tmp_path, "src/App.jsx", "<div className=\"card\"/>\n")
    screen = {"Code": ["<div className=\"card\"/>"], "Google Chrome": ["Uncaught TypeError: x.toFixed is not a function"]}
    assert not _gate(step, workdir=str(tmp_path), screen=screen)["passed"]
    screen["Google Chrome"] = ["Red panda", "5 kg"]
    assert _gate(step, workdir=str(tmp_path), screen=screen)["passed"]


def test_a_cleanup_called_instead_of_returned(tmp_path):
    code = "useEffect(() => {\n  const id = setInterval(tick, 1000)\n  return () => clearInterval(id)\n}, [])"
    step = {"id": "s", "file": "src/Clock.jsx", "code": code,
            "checks": [{"id": "c", "type": "screen_contains", "label": "clears", "app": "Code",
                        "pattern": r"clearInterval\(\s*id\s*\)"}]}
    _react(tmp_path, "src/Clock.jsx", code.replace("return () => clearInterval", "return clearInterval"))
    screen = {"Code": ["return clearInterval(id)"]}
    assert not _gate(step, workdir=str(tmp_path), screen=screen)["passed"]
    _react(tmp_path, "src/Clock.jsx", code)
    assert _gate(step, workdir=str(tmp_path), screen={"Code": ["return () => clearInterval(id)"]})["passed"]


def test_one_fixed_key_for_every_list_item(tmp_path):
    code = "{todos.map(todo => (\n  <li key={todo.id}>{todo.text}</li>\n))}"
    step = {"id": "s", "file": "src/List.jsx", "code": code,
            "checks": [{"id": "c", "type": "screen_contains", "label": "key", "app": "Code", "pattern": "key="}]}
    _react(tmp_path, "src/List.jsx", code.replace("key={todo.id}", 'key="todo"'))
    assert not _gate(step, workdir=str(tmp_path), screen={"Code": ['<li key="todo">']})["passed"]
    _react(tmp_path, "src/List.jsx", code)
    assert _gate(step, workdir=str(tmp_path), screen={"Code": ["<li key={todo.id}>"]})["passed"]


def test_an_expression_left_as_jsx_text(tmp_path):
    step = {"id": "s", "instructions": "Embed {new Date().getFullYear()} in the <p>.",
            "targets": [{"app": "Code", "file": "src/Footer.jsx", "match": "getFullYear()"}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "year", "app": "Code",
                        "pattern": "getFullYear"}]}
    _react(tmp_path, "src/Footer.jsx", "const F = () => <p>&copy; new Date().getFullYear() Me</p>\n")
    assert not _gate(step, workdir=str(tmp_path), screen={"Code": ["getFullYear()"]})["passed"]
    _react(tmp_path, "src/Footer.jsx", "const F = () => <p>&copy; {new Date().getFullYear()} Me</p>\n")
    assert _gate(step, workdir=str(tmp_path), screen={"Code": ["getFullYear()"]})["passed"]


def test_the_steps_file_made_in_another_folder(tmp_path):
    step = {"id": "s", "file": ".vscode/settings.json",
            "checks": [{"id": "c", "type": "screen_contains", "label": "on", "app": "Code",
                        "pattern": r'"editor\.formatOnSave"\s*:\s*true'}]}
    screen = {"Code": ['"editor.formatOnSave": true']}
    _write(tmp_path, "box/settings.json", '{"editor.formatOnSave": true}')
    gate = _gate(step, workdir=str(tmp_path), screen=screen)
    assert not gate["passed"] and ".vscode" in gate["checks"][-1]["detail"]
    _write(tmp_path, "box/.vscode/settings.json", '{"editor.formatOnSave": true}')
    assert _gate(step, workdir=str(tmp_path), screen=screen)["passed"]


def test_a_type_error_fixed_by_typing_it_any(tmp_path):
    step = {"id": "s", "title": "Fix the last type error", "instructions": "Pass 3, not '3'. Run npx tsc.",
            "file": "src/invoice.ts", "run_command": "npx tsc && node dist/invoice.js",
            "checks": [{"id": "c", "type": "screen_contains", "label": "total", "app": "Terminal",
                        "pattern": r"Invoice\s+total"}]}
    screen = _term("me@mac i % npx tsc", "me@mac i % node dist/invoice.js", "Invoice total: $30.50", "me@mac i % ")
    _write(tmp_path, "src/invoice.ts", "import { lineTotal } from './prices'\nconsole.log(lineTotal('3', 4.5))\n")
    _write(tmp_path, "src/prices.ts", "export function lineTotal(qty: any, unit: number) { return qty * unit }\n")
    assert not _gate(step, workdir=str(tmp_path), screen=screen)["passed"]
    _write(tmp_path, "src/prices.ts", "export function lineTotal(qty: number, unit: number) { return qty * unit }\n")
    assert _gate(step, workdir=str(tmp_path), screen=screen)["passed"]


def test_an_npm_install_run_outside_the_project(tmp_path):
    step = {"id": "s", "run_command": "npm install date-fns",
            "targets": [{"app": "Terminal", "match": "npm install date-fns"}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "installed", "app": "Terminal",
                        "pattern": r"added\s+\d+\s+packages?"}]}
    screen = _term("me@mac projects % npm install date-fns", "added 1 package in 1s", "me@mac projects % ")
    _write(tmp_path, "shop/package.json", json.dumps({"name": "shop", "scripts": {"dev": "vite"}}))
    _write(tmp_path, "package.json", json.dumps({"dependencies": {"date-fns": "^4.1.0"}}))
    assert not _gate(step, workdir=str(tmp_path), screen=screen)["passed"]
    (tmp_path / "package.json").unlink()
    _write(tmp_path, "shop/package.json", json.dumps({"name": "shop", "dependencies": {"date-fns": "^4.1.0"}}))
    assert _gate(step, workdir=str(tmp_path), screen=screen)["passed"]


# -- terminal history ---------------------------------------------------------------------------------------------------

def test_a_pull_that_stopped_on_a_merge_conflict(tmp_path):
    step = {"id": "s", "instructions": "Run git pull and inspect the commit with git show.",
            "targets": [{"app": "Terminal", "match": "git pull"}, {"app": "Terminal", "match": "git show"}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "Commit details", "app": "Terminal",
                        "pattern": r"commit\s+[0-9a-f]"}]}
    pull = ["me@mac g % git pull", "Auto-merging index.html", "CONFLICT (content): Merge conflict in index.html",
            "Automatic merge failed; fix conflicts and then commit the result."]
    show = ["me@mac g % git show", "commit 6a7b8c9d0e1f", "me@mac g % "]
    assert not _gate(step, screen=_term(*pull, *show))["passed"]
    assert _gate(step, screen=_term("me@mac g % git pull", "Fast-forward", *show))["passed"]


def test_another_subcommand_on_the_same_arguments(tmp_path):
    assert blocks.operands("docker run hello-world") == ["hello-world"]
    step = {"id": "s", "run_command": "docker run hello-world",
            "targets": [{"app": "Terminal", "match": "docker run hello-world"},
                        {"app": "Terminal", "match": "docker ps -a"}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "listed", "app": "Terminal",
                        "pattern": "hello-world"}]}
    ps = ["me@mac d % docker ps -a", "8d2f  hello-world  Exited (0)", "me@mac d % "]
    gate = _gate(step, screen=_term("me@mac d % docker pull hello-world", "Pull complete", *ps))
    assert not gate["passed"] and "docker pull" in gate["checks"][0]["detail"]
    assert _gate(step, screen=_term("me@mac d % docker run hello-world", "Hello from Docker!", *ps))["passed"]


def test_a_commit_made_on_a_detached_head():
    step = {"id": "s", "instructions": "Commit it with git commit -am \"Double the sugar\".",
            "targets": [{"app": "Terminal", "match": "git commit -am \"Double the sugar\""}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "committed", "app": "Terminal",
                        "pattern": r"\]\s+Double\s+the\s+sugar"}]}
    rows = ["me@mac c % git commit -am \"Double the sugar\"", "[{head} 7e8f9a0] Double the sugar", "me@mac c % "]
    assert not _gate(step, screen=_term(*[r.format(head="detached HEAD") for r in rows]))["passed"]
    assert _gate(step, screen=_term(*[r.format(head="main") for r in rows]))["passed"]


def test_a_commit_that_added_a_file_gitignore_lists(tmp_path):
    step = {"id": "s", "instructions": "Stage only .gitignore and commit it.",
            "targets": [{"app": "Terminal", "match": "git commit -m \"Ignore .DS_Store\""}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "committed", "app": "Terminal",
                        "pattern": r"\]\s+Ignore\s+\.DS_Store"}]}
    _write(tmp_path, "c/.gitignore", ".DS_Store\n")
    rows = ["me@mac c % git commit -m \"Ignore .DS_Store\"", "[main 8c9d0e1] Ignore .DS_Store",
            " create mode 100644 .DS_Store", " create mode 100644 .gitignore", "me@mac c % "]
    assert not _gate(step, workdir=str(tmp_path), screen=_term(*rows))["passed"]
    assert _gate(step, workdir=str(tmp_path), screen=_term(*rows[:2], *rows[3:]))["passed"]


def test_a_flag_that_changes_the_result_left_out(tmp_path):
    assert blocks.short_flags("grep -hi rain notes/*.txt") == {"h", "i"}
    assert blocks.short_flags("grep --ignore-case -h rain x") == {"h", "i"}
    step = {"id": "s", "run_command": "grep -hi rain notes/*.txt | sort > rain.txt",
            "targets": [{"app": "Terminal", "match": "grep -hi rain notes/*.txt | sort > rain.txt"}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "cat shows", "app": "Terminal",
                        "pattern": "(?i)rain"}]}
    rows = ["me@mac t % {cmd} rain notes/*.txt | sort > rain.txt", "me@mac t % cat rain.txt", "Light rain",
            "me@mac t % "]
    gate = _gate(step, screen=_term(*[r.format(cmd="grep -h") for r in rows]))
    assert not gate["passed"] and "-i" in gate["checks"][0]["detail"]
    assert _gate(step, screen=_term(*[r.format(cmd="grep -ih") for r in rows]))["passed"]


def test_an_error_from_a_wrong_name_the_steps_command_got_past():
    step = {"id": "s", "run_command": "pip install scikit-learn",
            "targets": [{"app": "Terminal", "match": "pip install scikit-learn"}],
            "checks": [{"id": "c", "type": "screen_absent", "label": "No install errors", "app": "Terminal",
                        "pattern": "error:|ERROR:"}]}
    bad = ["(.venv) me@mac i % pip install sklearn", "error: metadata-generation-failed"]
    good = ["(.venv) me@mac i % pip install scikit-learn", "Successfully installed scikit-learn-1.5.2",
            "(.venv) me@mac i % "]
    assert _gate(step, screen=_term(*bad, *good))["passed"]
    # the second install left out a package the step installs: the first one's error still stands
    step["run_command"] = "pip install scikit-learn pandas"
    assert not _gate(step, screen=_term(*bad, *good))["passed"]


def test_brace_expansion_and_the_files_the_step_makes(tmp_path):
    assert blocks.expand_braces("notes/day{1,2,3}.txt") == ["notes/day1.txt", "notes/day2.txt", "notes/day3.txt"]
    assert blocks.runs("touch notes/day{1,2,3}.txt", "touch notes/day1.txt notes/day2.txt notes/day3.txt")
    step = {"id": "s", "run_command": "touch notes/day1.txt notes/day2.txt",
            "targets": [{"app": "Terminal", "match": "touch notes/day1.txt notes/day2.txt"}],
            "checks": [{"id": "a", "type": "file_exists", "label": "day1", "file": "t/notes/day1.txt"},
                       {"id": "b", "type": "file_exists", "label": "day2", "file": "t/notes/day2.txt"},
                       {"id": "c", "type": "screen_contains", "label": "ls shows the notes", "app": "Terminal",
                        "pattern": r"day2\.txt"}]}
    rows = ["me@mac t % touch notes/day{1,2}.txt", "me@mac t % ls notes | wc -l", "       2", "me@mac t % "]
    _write(tmp_path, "t/notes/day1.txt", "")
    assert not _gate(step, workdir=str(tmp_path), screen=_term(*rows))["passed"]  # day2.txt is missing
    _write(tmp_path, "t/notes/day2.txt", "")
    assert _gate(step, workdir=str(tmp_path), screen=_term(*rows))["passed"]

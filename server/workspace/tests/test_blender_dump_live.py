"""The real dump: tiny scenes built and saved by headless Blender, dumped by server.workspace.blender.dump_blend,
then scored by the lesson-check eval cases they stand in for.

Skipped when no Blender is installed. Blender only runs as --background --factory-startup (no window, no render);
each scene is a handful of objects. Offline: no network, no API calls."""

from __future__ import annotations

import copy
import json
import os
import subprocess
from pathlib import Path

import pytest

from server.workspace import blender

EXE = blender.find_blender()
pytestmark = pytest.mark.skipif(EXE is None, reason="Blender is not installed")

REPO = Path(__file__).resolve().parents[3]
CASES = REPO / "server" / "evals" / "checks" / "cases"
TOP_KEYS = ["dump", "blender", "file", "is_dirty", "scene", "objects", "materials", "lights", "camera", "cameras",
            "world", "images", "mode"]
MESH_KEYS = ["name", "type", "location", "rotation_deg", "scale", "dimensions", "parent", "hide_viewport", "mesh",
             "modifiers", "materials"]

# Builds every scene in one Blender run: object properties and bpy.data only, then a save per scene.
BUILD = r'''
import math, sys
import bmesh, bpy

out = sys.argv[sys.argv.index("--") + 1]
D = bpy.data


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=False)


def save(name):
    bpy.ops.wm.save_as_mainfile(filepath=f"{out}/{name}.blend")


def add_mesh(name, build):
    me = D.meshes.new(name)
    bm = bmesh.new()
    build(bm)
    bm.to_mesh(me)
    bm.free()
    ob = D.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def principled(mat):
    return next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


# mug: the default cube renamed, Subdivision level 2, smooth faces
reset()
mug = D.objects["Cube"]
mug.name = "Mug"
mod = mug.modifiers.new("Subdivision", "SUBSURF")
mod.levels = 2
for p in mug.data.polygons:
    p.use_smooth = True
save("mug")

# shapes: cube at X 2, cone turned 90 on X, sphere at half size
reset()
D.objects["Cube"].location.x = 2.0
cone = add_mesh("Cone", lambda bm: bmesh.ops.create_cone(bm, cap_ends=True, segments=32, radius1=1.0,
                                                         radius2=0.0, depth=2.0))
cone.location.y = 3.0
cone.rotation_euler.x = math.radians(90)
sphere = add_mesh("Sphere", lambda bm: bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=1.0))
sphere.location.x = -2.0
sphere.scale = (0.5, 0.5, 0.5)
save("shapes")

# bounce: 96 frames to an MPEG-4 / H.264 video in the lesson folder
reset()
sc = bpy.context.scene
sc.frame_end = 96
img = sc.render.image_settings
if hasattr(img, "media_type"):
    img.media_type = "VIDEO"
img.file_format = "FFMPEG"
sc.render.ffmpeg.format = "MPEG4"
sc.render.ffmpeg.codec = "H264"
sc.render.filepath = "//"
D.objects["Cube"].name = "Ball"
save("bounce")

# glass: a transmissive glass ball at IOR 1.52 and a glowing bulb
reset()
D.objects.remove(D.objects["Cube"])
ball = add_mesh("GlassBall", lambda bm: bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=1.0))
bulb = add_mesh("Bulb", lambda bm: bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=1.0))
bulb.location.x = 3.0
glass, glow = D.materials.new("Glass"), D.materials.new("Glow")
for mat in (glass, glow):
    if mat.node_tree is None:
        mat.use_nodes = True
p = principled(glass)
p.inputs["Transmission Weight"].default_value = 1.0
p.inputs["Roughness"].default_value = 0.0
p.inputs["IOR"].default_value = 1.52
principled(glow).inputs["Emission Strength"].default_value = 5.0
ball.data.materials.append(glass)
bulb.data.materials.append(glow)
save("glass")

# lab: a cube keyed on X at frames 1 and 48, an empty second slot, an AREA key light and a POINT fill light
reset()
cube = D.objects["Cube"]
cube.location.x = 0.0
cube.keyframe_insert("location", index=0, frame=1)
cube.location.x = 4.0
cube.keyframe_insert("location", index=0, frame=48)
cube.data.materials.append(D.materials.new("Glaze"))
D.objects["Light"].name = "Fill"
key = D.objects.new("Key", D.lights.new("KeyLight", "AREA"))
key.data.energy = 500.0
key.data.size = 2.0
bpy.context.scene.collection.objects.link(key)
save("lab")

# kit: one of each modifier the format names, a constraint with no target, a quaternion turn, a node chain,
# an image on disk, a second camera with depth of field, Cycles chosen (never rendered)
reset()
sc = bpy.context.scene
sc.render.engine = "CYCLES"
cube = D.objects["Cube"]
cube.rotation_mode = "QUATERNION"
cube.rotation_quaternion = (0.7071068, 0.0, 0.0, 0.7071068)
bev = cube.modifiers.new("Bevel", "BEVEL")
bev.width = 0.1
cube.modifiers.new("Mirror", "MIRROR")
cube.modifiers.new("Array", "ARRAY").count = 3
cube.modifiers.new("Solidify", "SOLIDIFY").thickness = 0.05
cube.modifiers.new("Displace", "DISPLACE").strength = 0.2
cutter = add_mesh("Cutter", lambda bm: bmesh.ops.create_cube(bm, size=1.0))
boolean = cube.modifiers.new("Boolean", "BOOLEAN")
boolean.object = cutter
cam = D.objects["Camera"]
cam.constraints.new("TRACK_TO")
mat = D.materials["Material"]
nt = mat.node_tree
noise, ramp = nt.nodes.new("ShaderNodeTexNoise"), nt.nodes.new("ShaderNodeValToRGB")
nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
nt.links.new(ramp.outputs["Color"], principled(mat).inputs["Roughness"])
img = D.images.new("crate.png", 4, 4)
img.filepath_raw = f"{out}/crate.png"
img.file_format = "PNG"
img.save()
tex = nt.nodes.new("ShaderNodeTexImage")
tex.image = img
img.colorspace_settings.name = "Non-Color"
cam2 = D.objects.new("Camera.001", D.cameras.new("Camera.001"))
cam2.data.dof.use_dof = True
cam2.data.dof.focus_object = cube
sc.collection.objects.link(cam2)
save("kit")
'''

# Dumps the open file twice in one run: the dumper must not change the scene.
TWICE = r'''
import importlib.util, json, sys
import bpy

script, out = sys.argv[sys.argv.index("--") + 1:]
spec = importlib.util.spec_from_file_location("scene_dump_twice", script)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
dirty = bpy.data.is_dirty
first = mod.to_json(mod.dump())
second = mod.to_json(mod.dump(bpy.context))
with open(out, "w") as fh:
    json.dump({"same": first == second, "dirty_before": dirty, "dirty_after": bpy.data.is_dirty,
               "first": first}, fh)
'''


def _headless(*args: str, timeout: float = 120.0) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in blender.PAID_KEYS}
    return subprocess.run([EXE, "--background", "--factory-startup", *args], capture_output=True, text=True,
                          timeout=timeout, env=env, stdin=subprocess.DEVNULL)


@pytest.fixture(scope="module")
def scenes(tmp_path_factory) -> dict[str, dict]:
    """name -> the real dump of that scene's saved .blend (and its X.scene.json written next to it)."""
    root = tmp_path_factory.mktemp("blender-scenes")
    build = root / "build_scenes.py"
    build.write_text(BUILD)
    done = _headless("--python-exit-code", "1", "--python", str(build), "--", str(root))
    assert done.returncode == 0, done.stderr[-2000:]
    out = {}
    for name in ("mug", "shapes", "bounce", "glass", "lab", "kit"):
        doc = blender.dump_blend(root / f"{name}.blend")
        assert doc is not None, f"{name}.blend did not dump"
        out[name] = doc
    out["_root"] = root
    return out


# ------------------------------------------------------------------ finding Blender on this Mac
def test_find_blender_on_this_mac():
    app = Path("/Applications/Blender.app/Contents/MacOS/Blender")
    if not app.is_file() or os.environ.get(blender.BLENDER_ENV):
        pytest.skip("no Blender in /Applications, or MIYAGI_BLENDER overrides it")
    assert blender.find_blender() == str(app)


# ------------------------------------------------------------------ format
def test_dump_format_and_key_order(scenes):
    doc = scenes["mug"]
    assert doc["dump"] == "dump_scene.py 1"
    assert list(doc) == TOP_KEYS
    assert doc["file"] == "mug.blend" and doc["is_dirty"] is False and doc["mode"] == "OBJECT"
    assert list(doc["scene"]) == ["name", "unit_system", "frame_start", "frame_end", "fps", "render", "fps_base",
                                  "frame_current", "camera"]
    assert list(doc["scene"]["render"])[:5] == ["engine", "resolution", "file_format", "filepath", "ffmpeg"]
    mug = next(o for o in doc["objects"] if o["name"] == "Mug")
    assert list(mug)[:len(MESH_KEYS)] == MESH_KEYS
    assert list(mug["mesh"])[:7] == ["verts", "edges", "faces", "smooth", "islands", "seams", "uv_layers"]
    assert mug["mesh"]["smooth"] is True and mug["mesh"]["islands"] == 1
    assert mug["modifiers"][0] == {"name": "Subdivision", "type": "SUBSURF", "levels": 2, "render_levels": 2,
                                   "show_viewport": True, "show_render": True}
    text = (scenes["_root"] / "mug.scene.json").read_text(encoding="utf-8")
    assert text == json.dumps(doc, indent=1, ensure_ascii=False) + "\n"


def test_floats_are_rounded_to_six_places(scenes):
    cone = next(o for o in scenes["shapes"]["objects"] if o["name"] == "Cone")
    assert cone["rotation_deg"][0] == 90.000003
    glass = next(m for m in scenes["glass"]["materials"] if m["name"] == "Glass")
    assert glass["principled"]["ior"] == 1.52 and glass["principled"]["transmission_weight"] == 1.0


def test_video_output_settings(scenes):
    render = scenes["bounce"]["scene"]["render"]
    assert scenes["bounce"]["scene"]["frame_end"] == 96
    assert render["file_format"] == "FFMPEG" and render["filepath"] == "//"
    assert render["ffmpeg"] == {"format": "MPEG4", "codec": "H264"}


# ------------------------------------------------------------------ the real dump scores the eval cases
def _swap_and_run(case_id: str, doc: dict) -> tuple[str, str]:
    from server.evals.checks.runner import run_case

    case = json.loads((CASES / f"{case_id}.json").read_text(encoding="utf-8"))
    case = copy.deepcopy(case)
    files = case["workspace"]["files"]
    rel = next(k for k in files if k.endswith(".scene.json"))
    files[rel] = {"json": doc}
    out = run_case(case)
    return out.got, case["expected"]


@pytest.mark.parametrize("case_id,scene", [
    ("blender-mug-subsurf-smooth-done", "mug"),
    ("blender-transform-cone-rotation-float", "shapes"),
    ("blender-anim-mp4-default-name", "bounce"),
    ("blender-glass-transmission-weight-42", "glass"),
])
def test_real_dump_scores_like_the_fixture(scenes, case_id, scene):
    got, expected = _swap_and_run(case_id, scenes[scene])
    assert got == expected


# ------------------------------------------------------------------ animation, lights, slots
def test_keyframes_come_from_the_slot_channelbag(scenes):
    cube = next(o for o in scenes["lab"]["objects"] if o["name"] == "Cube")
    anim = cube["animation"]
    assert anim["action"]
    fc = anim["fcurves"][0]
    assert list(fc) == ["data_path", "index", "keyframes", "interpolation", "handle_types", "handles",
                        "evaluated_range"]
    assert fc["data_path"] == "location" and fc["index"] == 0
    assert fc["keyframes"] == [[1.0, 0.0], [48.0, 4.0]]
    assert len(fc["interpolation"]) == 2 and len(fc["handle_types"]) == 2 and len(fc["handles"]) == 2
    assert fc["evaluated_range"] == [0.0, 4.0]


def test_lights_and_material_slots(scenes):
    lights = {l["name"]: l for l in scenes["lab"]["lights"]}
    assert lights["Key"] == {"name": "Key", "type": "AREA", "energy": 500.0, "size": 2.0}
    assert lights["Fill"]["type"] == "POINT" and "size" not in lights["Fill"]
    cube = next(o for o in scenes["lab"]["objects"] if o["name"] == "Cube")
    assert cube["material_slots"] == [
        {"slot": 0, "name": "Material", "material": "Material", "faces": 6},
        {"slot": 1, "name": "Glaze", "material": "Glaze", "faces": 0},
    ]
    glaze = next(m for m in scenes["lab"]["materials"] if m["name"] == "Glaze")
    assert glaze["users"] == ["Cube"]


def test_camera_framing(scenes):
    cam = scenes["mug"]["camera"]
    assert cam["name"] == "Camera" and cam["lens"] == 50.0
    assert cam["in_view"] == ["Mug"]
    f = cam["framing"][0]
    assert f["object"] == "Mug" and 0 < f["in_frame"] <= 1 and f["clipped_edges"] == []


def test_modifiers_constraints_nodes_images_cameras(scenes):
    doc = scenes["kit"]
    assert doc["scene"]["render"]["engine"] == "CYCLES"
    assert list(doc["scene"]["render"]["cycles"]) == ["samples", "use_denoising"]
    cube = next(o for o in doc["objects"] if o["name"] == "Cube")
    assert cube["rotation_deg"] == pytest.approx([0.0, 0.0, 90.0], abs=1e-3)  # (w, x, y, z): a quarter turn on Z
    assert "-0.0" not in json.dumps(cube["rotation_deg"])
    mods = {m["type"]: m for m in cube["modifiers"]}
    assert list(mods["BEVEL"]) == ["name", "type", "width", "segments", "limit_method", "angle_limit_deg",
                                   "show_viewport", "show_render"]
    assert mods["BEVEL"]["width"] == 0.1
    assert mods["MIRROR"]["use_axis"] == [True, False, False]
    assert mods["ARRAY"]["count"] == 3 and mods["SOLIDIFY"]["thickness"] == 0.05
    assert mods["DISPLACE"]["strength"] == 0.2
    assert mods["BOOLEAN"]["object"] == "Cutter" and mods["BOOLEAN"]["operation"] == "DIFFERENCE"
    cam = next(o for o in doc["objects"] if o["name"] == "Camera")
    con, = cam["constraints"]
    assert con["type"] == "TRACK_TO" and con["target"] is None and con["is_valid"] is False
    assert list(con) == ["name", "type", "target", "track_axis", "up_axis", "influence", "is_valid"]
    mat = next(m for m in doc["materials"] if m["name"] == "Material")
    nodes = {n["type"]: n for n in mat["nodes"]}
    assert nodes["TEX_IMAGE"]["image"] == "crate.png" and nodes["TEX_IMAGE"]["colorspace"] == "Non-Color"
    assert len(nodes["VALTORGB"]["elements"]) == 2 and "inputs" in nodes["TEX_NOISE"]
    assert "inputs" not in nodes["BSDF_PRINCIPLED"]
    assert {"from": nodes["VALTORGB"]["name"], "from_socket": "Color", "to": "Principled BSDF",
            "to_socket": "Roughness"} in mat["links"]
    img, = doc["images"]
    assert img["name"] == "crate.png" and img["packed"] is False and img["has_data"] is True
    assert img["colorspace"] == "Non-Color" and img["size"] == [4, 4]
    cams = {c["name"]: c for c in doc["cameras"]}
    assert cams["Camera.001"]["dof"]["use_dof"] is True and cams["Camera.001"]["dof"]["focus_object"] == "Cube"
    assert doc["world"]["name"] == "World" and doc["world"]["links"]


# ------------------------------------------------------------------ reading only
def test_dumping_twice_changes_nothing(scenes, tmp_path):
    helper, out = tmp_path / "twice.py", tmp_path / "twice.json"
    helper.write_text(TWICE)
    script = REPO / "blender-addon" / "miyagi_bridge" / "scene_dump.py"
    done = _headless("--disable-autoexec", str(scenes["_root"] / "lab.blend"), "--python-exit-code", "1",
                     "--python", str(helper), "--", str(script), str(out))
    assert done.returncode == 0, done.stderr[-2000:]
    res = json.loads(out.read_text())
    assert res["same"] is True
    assert res["dirty_before"] == res["dirty_after"]
    assert json.loads(res["first"]) == scenes["lab"]


def test_unreadable_blend_is_none_and_keeps_the_old_dump(tmp_path):
    stub = tmp_path / "mug.blend"
    stub.write_text("BLENDER-v402 (not a real .blend)\n")
    old = stub.with_name("mug.scene.json")
    old.write_text('{"dump": "dump_scene.py 1", "file": "old"}\n')
    before = old.read_bytes()
    assert blender.dump_blend(stub) is None
    assert old.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["mug.blend", "mug.scene.json"]

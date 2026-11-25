"""blender-addon/miyagi_bridge/ui_geom.py against the real Blender, headless.

Runs Blender only as `--background --factory-startup --python-exit-code 1 --python <script>`, with
ANTHROPIC_API_KEY / GEMINI_API_KEY removed from its environment and a 90 s timeout; skipped when Blender is not
installed. Nothing opens a window. Checks:

  - ui_geom.project of the factory Cube's 8 bound-box corners equals bpy_extras.view3d_utils.location_3d_to_region_2d
    (a SimpleNamespace region 1920 x 1080 and rv3d whose perspective_matrix is the factory camera's
    calc_matrix_camera(depsgraph, x=1920, y=1080) @ matrix_world.inverted()) within 0.5 px, and the Cube's centre
    equals world_to_camera_view(scene, camera, Cube.location) x (1920, 1080);
  - server.ui_payload() on the factory screen: the Cube's box in the 3D Viewport is the bounding box of
    location_3d_to_region_2d over its corners with that viewport's own WINDOW region and region_3d (window pixels),
    the Properties editor's tab column is its NAVIGATION_BAR region, and reading the shown tabs changes nothing.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
ADDON_DIR = REPO / "blender-addon"
BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"
TOL_PX = 0.5

SCRIPT = r'''
import json, sys
from types import SimpleNamespace

import bpy
from bpy_extras.object_utils import world_to_camera_view
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

addon_dir, out = sys.argv[sys.argv.index("--") + 1:]
sys.path.insert(0, addon_dir)
from miyagi_bridge import server, ui_geom  # noqa: E402  (server only: the add-on is never registered here)

W, H = 1920, 1080
scene = bpy.context.scene
cam, cube = scene.camera, bpy.data.objects["Cube"]
dg = bpy.context.evaluated_depsgraph_get()
persmat = cam.calc_matrix_camera(dg, x=W, y=H) @ cam.matrix_world.inverted()
region, rv3d = SimpleNamespace(width=W, height=H), SimpleNamespace(perspective_matrix=persmat)
corners = [cube.matrix_world @ Vector(c) for c in cube.bound_box]
m = ui_geom.matrix(persmat)
res = {
    "ref": [list(location_3d_to_region_2d(region, rv3d, c)) for c in corners],
    "mine": [list(ui_geom.project(m, tuple(c), W, H)) for c in corners],
    "box": list(ui_geom.object_box([tuple(c) for c in corners], m, W, H)),
}
v = world_to_camera_view(scene, cam, cube.location)
res["centre_ref"] = [v.x * W, v.y * H]
res["centre_mine"] = list(ui_geom.project(m, tuple(cube.location), W, H))

# the factory screen's own 3D Viewport and Properties editor
expected = None
for area in bpy.context.window_manager.windows[0].screen.areas:
    if area.type == "VIEW_3D":
        reg = next(r for r in area.regions if r.type == "WINDOW")
        pts = [location_3d_to_region_2d(reg, area.spaces.active.region_3d, c) for c in corners]
        xs, ys = [p.x for p in pts], [p.y for p in pts]
        x0, y0 = max(0.0, min(xs)), max(0.0, min(ys))
        x1, y1 = min(float(reg.width), max(xs)), min(float(reg.height), max(ys))
        expected = [reg.x + x0, reg.y + y0, x1 - x0, y1 - y0]
    if area.type == "PROPERTIES":
        nav = next(r for r in area.regions if r.type == "NAVIGATION_BAR")
        res["nav"] = {"x": nav.x, "y": nav.y, "width": nav.width, "height": nav.height}
        res["context_before"] = area.spaces.active.context
        props_space = area.spaces.active
res["cube_view_expected"] = expected
payload = server.ui_payload()
res["context_after"] = props_space.context
res["payload"] = payload
with open(out, "w") as f:
    json.dump(res, f)
'''


def _blender() -> str | None:
    return BLENDER if os.path.isfile(BLENDER) and os.access(BLENDER, os.X_OK) else None


@pytest.fixture(scope="module")
def headless(tmp_path_factory) -> dict:
    if _blender() is None:
        pytest.skip("Blender is not installed")
    tmp = tmp_path_factory.mktemp("blender_ui")
    script, out = tmp / "ui_geom_check.py", tmp / "out.json"
    script.write_text(SCRIPT)
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY")}
    argv = [_blender(), "--background", "--factory-startup", "--python-exit-code", "1", "--python", str(script),
            "--", str(ADDON_DIR), str(out)]
    assert "--background" in argv and "--factory-startup" in argv
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=90, env=env, check=False)
    assert proc.returncode == 0 and out.exists(), proc.stdout[-2000:] + proc.stderr[-2000:]
    return json.loads(out.read_text())


def test_projection_matches_location_3d_to_region_2d(headless):
    ref, mine = headless["ref"], headless["mine"]
    assert len(ref) == len(mine) == 8
    for (rx, ry), (mx, my) in zip(ref, mine, strict=True):
        assert abs(rx - mx) <= TOL_PX and abs(ry - my) <= TOL_PX
    xs, ys = [p[0] for p in ref], [p[1] for p in ref]
    bx, by, bw, bh = headless["box"]  # the whole Cube is in the camera's frame: its box is unclipped
    assert bx == pytest.approx(min(xs), abs=TOL_PX) and by == pytest.approx(min(ys), abs=TOL_PX)
    assert bw == pytest.approx(max(xs) - min(xs), abs=TOL_PX) and bh == pytest.approx(max(ys) - min(ys), abs=TOL_PX)


def test_cube_centre_matches_world_to_camera_view(headless):
    (rx, ry), (mx, my) = headless["centre_ref"], headless["centre_mine"]
    assert abs(rx - mx) <= TOL_PX and abs(ry - my) <= TOL_PX
    assert 0 < mx < 1920 and 0 < my < 1080


def test_ui_payload_on_the_factory_screen(headless):
    p = headless["payload"]
    assert p["ok"] is True and p["mode"] == "OBJECT" and p["active"] == "Cube"
    areas = {a["type"]: a for a in p["windows"][0]["areas"]}
    cube = next(o for o in areas["VIEW_3D"]["objects"] if o["name"] == "Cube")
    want = headless["cube_view_expected"]
    got = [cube["x"], cube["y"], cube["width"], cube["height"]]
    assert cube["type"] == "MESH" and all(abs(a - b) <= TOL_PX for a, b in zip(got, want, strict=True)), (got, want)
    props = areas["PROPERTIES"]["properties"]
    assert props["tabs"] == headless["nav"] and props["context"] == headless["context_before"]
    assert {"OBJECT", "MODIFIER", "MATERIAL"} <= set(props.get("contexts") or [])
    assert headless["context_after"] == headless["context_before"]  # reading the shown tabs changed nothing

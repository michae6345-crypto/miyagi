"""Read the open Blender scene into one plain dict: the "dump_scene.py 1" format the miyagi checks read.

    doc = dump()            # bpy.context's scene
    text = to_json(doc)     # indent 1, keys in format order, one trailing newline

The key order is part of the format: lesson checks match regexes such as
"name":\\s*"Cube",\\s*"type":\\s*"MESH",\\s*"location" on the JSON text, so every dict here is built in the order the
contract lists. Every float is round(x, 6); angles are degrees except fcurve values (raw, radians for rotation).

Reading only: no bpy.ops, no writes to bpy.data, no files. The headless CLI (../dump_scene.py) and the live
bridge both use this file, and the CLI loads it by path, so it has no relative imports.
"""

from __future__ import annotations

import json
import math
import os
import warnings

import bpy

FORMAT = "dump_scene.py 1"

UV_FACE_LIMIT = 100000
SOCKET_SETS = {
    "base_color": ("Base Color",),
    "roughness": ("Roughness",),
    "metallic": ("Metallic",),
    "ior": ("IOR",),
    "transmission_weight": ("Transmission Weight", "Transmission"),
    "emission_color": ("Emission Color", "Emission"),
    "emission_strength": ("Emission Strength",),
}


# ------------------------------------------------------------------ small values
def _f(x) -> float:
    """A float rounded to 6 places (1.5199999809265137 reads 1.52); -0.0 reads 0.0, so patterns see one zero."""
    return round(float(x), 6) + 0.0


def _vec(v) -> list[float]:
    return [_f(x) for x in v]


def _deg(v) -> list[float]:
    return [_f(math.degrees(x)) for x in v]


def _name(idblock) -> str | None:
    return idblock.name if idblock is not None else None


def _use_nodes(idblock) -> bool:
    """Material / World use_nodes; deprecated (always true) in Blender 5, so read it quietly."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return bool(getattr(idblock, "use_nodes", True))


def _flat(coll, attr: str, width: int, kind=float) -> list:
    """One attribute of every item of a bpy collection, read in one call."""
    out = [kind(0)] * (len(coll) * width)
    if out:
        coll.foreach_get(attr, out)
    return out


# ------------------------------------------------------------------ scene
def _render(scene) -> dict:
    r = scene.render
    img = r.image_settings
    out = {
        "engine": r.engine,
        "resolution": [int(r.resolution_x), int(r.resolution_y)],
        "file_format": img.file_format,
        "filepath": r.filepath,
        "ffmpeg": {"format": r.ffmpeg.format, "codec": r.ffmpeg.codec},
    }
    cycles = getattr(scene, "cycles", None)
    if r.engine == "CYCLES" and cycles is not None:
        out["cycles"] = {"samples": int(cycles.samples), "use_denoising": bool(cycles.use_denoising)}
    if hasattr(img, "media_type"):
        out["media_type"] = img.media_type
    return out


def _scene(scene) -> dict:
    r = scene.render
    return {
        "name": scene.name,
        "unit_system": scene.unit_settings.system,
        "frame_start": int(scene.frame_start),
        "frame_end": int(scene.frame_end),
        "fps": int(r.fps),
        "render": _render(scene),
        "fps_base": _f(r.fps_base),
        "frame_current": int(scene.frame_current),
        "camera": _name(scene.camera),
    }


# ------------------------------------------------------------------ mesh
def _islands(n_verts: int, edge_verts: list[int]) -> int:
    """Connected vertex groups over edges (union-find); a loose vertex is its own island."""
    parent = list(range(n_verts))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for k in range(0, len(edge_verts), 2):
        a, b = root(edge_verts[k]), root(edge_verts[k + 1])
        if a != b:
            parent[a] = b
    return sum(1 for i in range(n_verts) if root(i) == i)


def _poly_loops(me) -> list[tuple[int, int]]:
    starts = _flat(me.polygons, "loop_start", 1, int)
    totals = _flat(me.polygons, "loop_total", 1, int)
    return list(zip(starts, totals))


def _overlapping(boxes: list[tuple[float, float, float, float]]) -> int:
    """How many boxes overlap another box by a positive area (sweep over x)."""
    order = sorted(range(len(boxes)), key=lambda i: boxes[i][0])
    hit = set()
    for n, i in enumerate(order):
        x0, y0, x1, y1 = boxes[i]
        for j in order[n + 1:]:
            u0, v0, u1, v1 = boxes[j]
            if u0 >= x1:
                break
            if min(x1, u1) - max(x0, u0) > 1e-9 and min(y1, v1) - max(y0, v0) > 1e-9:
                hit.update((i, j))
    return len(hit)


def _uv(me) -> dict | None:
    layer = me.uv_layers.active
    if layer is None or len(me.polygons) > UV_FACE_LIMIT:
        return None
    from bpy_extras import mesh_utils

    uvs = _flat(layer.data, "uv", 2)
    loops = _poly_loops(me)
    area = 0.0
    for start, total in loops:  # shoelace per face
        s = 0.0
        for k in range(total):
            a, b = start + k, start + (k + 1) % total
            s += uvs[2 * a] * uvs[2 * b + 1] - uvs[2 * b] * uvs[2 * a + 1]
        area += abs(s) / 2.0
    islands = mesh_utils.mesh_linked_uv_islands(me)
    boxes = []
    for faces in islands:
        xs, ys = [], []
        for p in faces:
            start, total = loops[p]
            xs += uvs[2 * start:2 * (start + total):2]
            ys += uvs[2 * start + 1:2 * (start + total):2]
        if xs:
            boxes.append((min(xs), min(ys), max(xs), max(ys)))
    return {
        "layer": layer.name,
        "islands": len(islands),
        "overlapping_islands": _overlapping(boxes),
        "coverage": _f(min(1.0, area)),
    }


def _mesh(me) -> dict:
    faces = len(me.polygons)
    smooth = _flat(me.polygons, "use_smooth", 1, bool)
    out = {
        "verts": len(me.vertices),
        "edges": len(me.edges),
        "faces": faces,
        "smooth": bool(faces) and all(smooth),
        "islands": _islands(len(me.vertices), _flat(me.edges, "vertices", 2, int)),
        "seams": sum(_flat(me.edges, "use_seam", 1, bool)),
        "uv_layers": [layer.name for layer in me.uv_layers],
    }
    if (uv := _uv(me)) is not None:
        out["uv"] = uv
    return out


# ------------------------------------------------------------------ object parts
def _modifier(m) -> dict:
    out: dict = {"name": m.name, "type": m.type}
    t = m.type
    if t == "SUBSURF":
        out.update(levels=int(m.levels), render_levels=int(m.render_levels))
    elif t == "BEVEL":
        out.update(width=_f(m.width), segments=int(m.segments), limit_method=m.limit_method,
                   angle_limit_deg=_f(math.degrees(m.angle_limit)))
    elif t == "SOLIDIFY":
        out["thickness"] = _f(m.thickness)
    elif t == "ARRAY":
        out["count"] = int(m.count)
    elif t == "DISPLACE":
        out["strength"] = _f(m.strength)
    elif t == "MIRROR":
        out["use_axis"] = [bool(x) for x in m.use_axis]
    elif t == "BOOLEAN":
        out.update(operation=m.operation, object=_name(m.object))
    out["show_viewport"] = bool(m.show_viewport)
    out["show_render"] = bool(m.show_render)
    return out


def _slots(obj) -> list[dict]:
    per_index: dict[int, int] = {}
    if obj.type == "MESH" and obj.data is not None:
        for i in _flat(obj.data.polygons, "material_index", 1, int):
            per_index[i] = per_index.get(i, 0) + 1
    out = []
    for i, slot in enumerate(obj.material_slots):
        name = slot.material.name if slot.material else ""
        out.append({"slot": i, "name": name, "material": name, "faces": per_index.get(i, 0)})
    return out


def _constraint(c) -> dict:
    out: dict = {"name": c.name, "type": c.type, "target": _name(getattr(c, "target", None))}
    for key in ("track_axis", "up_axis"):
        if hasattr(c, key):
            out[key] = getattr(c, key)
    out["influence"] = _f(c.influence)
    out["is_valid"] = bool(c.is_valid)
    return out


def _fcurves(obj, action) -> list:
    """The object's own fcurves: the action slot's channelbag (Blender 4.4+), else the legacy action.fcurves."""
    try:
        from bpy_extras import anim_utils

        get = getattr(anim_utils, "action_get_channelbag_for_slot", None)
        slot = getattr(obj.animation_data, "action_slot", None)
        if get is not None and slot is not None:
            bag = get(action, slot)
            return list(bag.fcurves) if bag is not None else []
    except ImportError:
        pass
    return list(getattr(action, "fcurves", []) or [])


def _fcurve(fc) -> dict:
    points = list(fc.keyframe_points)
    frames = [p.co[0] for p in points]
    values = []
    if frames:
        lo, hi = math.ceil(min(frames)), math.floor(max(frames))
        values = [fc.evaluate(float(f)) for f in range(lo, hi + 1)] or [fc.evaluate(min(frames))]
    return {
        "data_path": fc.data_path,
        "index": int(fc.array_index),
        "keyframes": [[_f(p.co[0]), _f(p.co[1])] for p in points],
        "interpolation": [p.interpolation for p in points],
        "handle_types": [p.handle_left_type for p in points],
        "handles": [{"left": _vec(p.handle_left), "right": _vec(p.handle_right)} for p in points],
        "evaluated_range": [_f(min(values)), _f(max(values))] if values else [],
    }


def _animation(obj) -> dict | None:
    ad = obj.animation_data
    action = ad.action if ad is not None else None
    if action is None:
        return None
    return {"action": action.name, "fcurves": [_fcurve(fc) for fc in _fcurves(obj, action)]}


def _hidden(obj, view_layer) -> bool:
    if obj.hide_viewport:
        return True
    if view_layer is None:
        return False
    try:
        return bool(obj.hide_get(view_layer=view_layer))
    except (RuntimeError, TypeError):
        return False


def _rotation_deg(obj) -> list[float]:
    if obj.rotation_mode in ("QUATERNION", "AXIS_ANGLE"):
        return _deg(obj.matrix_basis.to_euler("XYZ"))
    return _deg(obj.rotation_euler)


def _object(obj, view_layer) -> dict:
    out: dict = {
        "name": obj.name,
        "type": obj.type,
        "location": _vec(obj.location),
        "rotation_deg": _rotation_deg(obj),
        "scale": _vec(obj.scale),
        "dimensions": _vec(obj.dimensions),
        "parent": _name(obj.parent),
        "hide_viewport": _hidden(obj, view_layer),
    }
    if obj.type == "MESH" and obj.data is not None:
        out["mesh"] = _mesh(obj.data)
    out["modifiers"] = [_modifier(m) for m in obj.modifiers]
    out["materials"] = [s.material.name for s in obj.material_slots if s.material]
    if len(obj.material_slots):
        out["material_slots"] = _slots(obj)
    if len(obj.constraints):
        out["constraints"] = [_constraint(c) for c in obj.constraints]
    if (anim := _animation(obj)) is not None:
        out["animation"] = anim
    return out


# ------------------------------------------------------------------ node trees
def _socket_value(v):
    """A socket default as JSON: float / int / bool / list of floats; None for anything else."""
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return _f(v)
    try:
        items = list(v)
    except TypeError:
        return None
    if items and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in items):
        return [_f(x) for x in items]
    return None


def _inputs(node) -> dict:
    out: dict = {}
    for s in node.inputs:
        if not getattr(s, "enabled", True) or getattr(s, "hide_value", False) or s.is_linked:
            continue
        if not hasattr(s, "default_value") or s.name in out:
            continue
        if (v := _socket_value(s.default_value)) is not None:
            out[s.name] = v
    return out


def _node(node) -> dict:
    out: dict = {"name": node.name, "type": node.type}
    image = getattr(node, "image", None) if node.type in ("TEX_IMAGE", "TEX_ENVIRONMENT") else None
    if image is not None:
        out["image"] = image.name
        out["colorspace"] = image.colorspace_settings.name
    if node.type != "BSDF_PRINCIPLED" and not node.type.startswith("OUTPUT_"):
        if inputs := _inputs(node):
            out["inputs"] = inputs
    if node.type == "VALTORGB":
        out["elements"] = [[_f(e.position), _vec(e.color)] for e in node.color_ramp.elements]
    return out


def _links(tree) -> list[dict]:
    return [{"from": ln.from_node.name, "from_socket": ln.from_socket.name,
             "to": ln.to_node.name, "to_socket": ln.to_socket.name}
            for ln in tree.links if ln.is_valid]


def _principled_node(tree):
    """The Principled BSDF feeding the active Material Output, else the first Principled BSDF."""
    for node in tree.nodes:
        if node.type == "OUTPUT_MATERIAL" and getattr(node, "is_active_output", False):
            surface = node.inputs.get("Surface")
            if surface is not None:
                for ln in surface.links:
                    if ln.from_node.type == "BSDF_PRINCIPLED":
                        return ln.from_node
    return next((n for n in tree.nodes if n.type == "BSDF_PRINCIPLED"), None)


def _principled(tree) -> dict | None:
    node = _principled_node(tree) if tree is not None else None
    if node is None:
        return None
    out = {}
    for key, names in SOCKET_SETS.items():
        sock = next((node.inputs[n] for n in names if n in node.inputs), None)
        out[key] = _socket_value(sock.default_value) if sock is not None else None
    return out


def _material(mat, user_names: list[str]) -> dict:
    tree = mat.node_tree
    return {
        "name": mat.name,
        "users": user_names,
        "principled": _principled(tree),
        "use_nodes": _use_nodes(mat),
        "nodes": [_node(n) for n in tree.nodes] if tree is not None else [],
        "links": _links(tree) if tree is not None else [],
    }


def _materials(objects) -> list[dict]:
    users: dict[str, list[str]] = {}
    for obj in objects:
        for slot in obj.material_slots:
            if slot.material is not None:
                names = users.setdefault(slot.material.name, [])
                if obj.name not in names:
                    names.append(obj.name)
    return [_material(m, users.get(m.name, [])) for m in bpy.data.materials
            if m.users > 0 and not getattr(m, "is_grease_pencil", False)]


def _world(world) -> dict | None:
    if world is None:
        return None
    tree = world.node_tree
    return {
        "name": world.name,
        "use_nodes": _use_nodes(world),
        "nodes": [_node(n) for n in tree.nodes] if tree is not None else [],
        "links": _links(tree) if tree is not None else [],
    }


# ------------------------------------------------------------------ lights, cameras, images
def _light(obj) -> dict:
    data = obj.data
    out = {"name": obj.name, "type": data.type, "energy": _f(data.energy)}
    if data.type == "AREA":
        out["size"] = _f(data.size)
    return out


def _framing(scene, cam, obj) -> dict | None:
    """Where obj's bound box lands in the camera frame (an approximation from the 8 box corners)."""
    from bpy_extras.object_utils import world_to_camera_view
    from mathutils import Vector

    pts = [world_to_camera_view(scene, cam, obj.matrix_world @ Vector(c)) for c in obj.bound_box]
    front = [p for p in pts if p.z > 0]
    if not front:
        return None
    x0, x1 = min(p.x for p in front), max(p.x for p in front)
    y0, y1 = min(p.y for p in front), max(p.y for p in front)
    cw, ch = max(0.0, min(x1, 1.0) - max(x0, 0.0)), max(0.0, min(y1, 1.0) - max(y0, 0.0))
    area = (x1 - x0) * (y1 - y0)
    if area > 1e-12:
        share = cw * ch / area
    else:
        share = 1.0 if 0 <= x0 <= 1 and 0 <= y0 <= 1 else 0.0
    if share <= 0:
        return None
    edges = [side for side, out in (("left", x0 < 0), ("right", x1 > 1), ("bottom", y0 < 0), ("top", y1 > 1)) if out]
    return {
        "object": obj.name,
        "in_frame": _f(min(1.0, share)),
        "bbox_ndc": [[round(x0, 2), round(y0, 2)], [round(x1, 2), round(y1, 2)]],
        "clipped_edges": edges,
    }


def _camera(scene, objects, view_layer) -> dict | None:
    cam = scene.camera
    if cam is None:
        return None
    framing = []
    if cam.type == "CAMERA":
        for obj in objects:
            if obj.type == "MESH" and not obj.hide_render and not _hidden(obj, view_layer):
                if (f := _framing(scene, cam, obj)) is not None:
                    framing.append(f)
    lens = getattr(cam.data, "lens", None)
    return {
        "name": cam.name,
        "lens": _f(lens) if lens is not None else None,
        "in_view": [f["object"] for f in framing],
        "framing": framing,
    }


def _camera_entry(obj) -> dict:
    cam = obj.data
    dof = cam.dof
    return {
        "name": obj.name,
        "lens": _f(cam.lens),
        "dof": {
            "use_dof": bool(dof.use_dof),
            "focus_object": _name(dof.focus_object),
            "focus_distance": _f(dof.focus_distance),
            "aperture_fstop": _f(dof.aperture_fstop),
        },
    }


def _image(img) -> dict:
    packed = img.packed_file is not None
    has_data = bool(img.has_data) or packed
    if not has_data and img.filepath:
        try:
            has_data = os.path.isfile(bpy.path.abspath(img.filepath, library=img.library))
        except (ValueError, OSError):
            has_data = False
    return {
        "name": img.name,
        "filepath": img.filepath,
        "colorspace": img.colorspace_settings.name,
        "packed": packed,
        "has_data": has_data,
        "size": [int(img.size[0]), int(img.size[1])],
    }


# ------------------------------------------------------------------ the dump
def dump(context=None) -> dict:
    """The "dump_scene.py 1" dict for context's scene (default bpy.context). Reads only."""
    ctx = context if context is not None else bpy.context
    scene = ctx.scene
    view_layer = getattr(ctx, "view_layer", None)
    objects = list(scene.objects)
    return {
        "dump": FORMAT,
        "blender": bpy.app.version_string,
        "file": os.path.basename(bpy.data.filepath),
        "is_dirty": bool(bpy.data.is_dirty),
        "scene": _scene(scene),
        "objects": [_object(o, view_layer) for o in objects],
        "materials": _materials(objects),
        "lights": [_light(o) for o in objects if o.type == "LIGHT"],
        "camera": _camera(scene, objects, view_layer),
        "cameras": [_camera_entry(o) for o in objects if o.type == "CAMERA"],
        "world": _world(scene.world),
        "images": [_image(i) for i in bpy.data.images if i.type == "IMAGE"],
        "mode": getattr(ctx, "mode", "OBJECT"),
    }


def to_json(doc: dict) -> str:
    """The dump as text: indent 1, key order kept, non-ASCII names as they are, one trailing newline."""
    return json.dumps(doc, indent=1, ensure_ascii=False) + "\n"

"""What an app lesson's saved files say, read the way the step means it (Blender / FreeCAD / AutoCAD / Fusion).

A file_contains check is a regex over a whole file. On a model's facts that is fooled in ways a careful reader isn't:

* the right fact on the wrong object: a scene dump (``mug.scene.json``: objects, materials, lights, bodies, each with a
  ``name``) holds the Subdivision modifier on the default Cube while the step is about the Mug. ``scoped_json`` keeps
  only the entries the step names (by name, as a word of its title / instructions / label) and the entries that refer
  to one of them (a material whose ``users`` holds "Mug");
* float noise: ``R X 90`` is stored as float32 radians, so the dump says ``90.00000250447816`` degrees;
  ``rounded`` writes every long decimal at 4 places (``90.0``) so ``90(?:\\.0+)?`` reads it;
* "every feature rebuilds" passed on the one feature that is valid: ``every_instance`` makes a check whose label says
  every / all / each hold for every ``"key": value`` of its pattern's key;
* an export with nothing in it: ``empty_mesh`` (an STL with no facets, an OBJ with no faces);
* a number typed over a drawing's text: in an ASCII DXF a value is a (group code, value) pair, and a number matched in
  a text group (a DIMENSION's override, group 1) is not a measurement: ``dxf_numeric_ok``.

Pure: reads files, never runs the apps.
"""
from __future__ import annotations

import json
import os
import re
import struct

# ---------------------------------------------------------------- scene dumps (JSON)


_PRIMARY = ("objects", "bodies", "parts", "components", "meshes", "entities", "layers")


def _named_lists(doc: dict) -> dict[str, list[dict]]:
    return {k: v for k, v in doc.items() if isinstance(v, list) and v
            and all(isinstance(e, dict) and isinstance(e.get("name"), str) for e in v)}


def _word_in(name: str, text: str) -> bool:
    return bool(name.strip()) and re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text, re.I) is not None


def _refers(entry: dict, subjects: set[str]) -> bool:
    """Does an entry name a subject in one of its own fields (``"users": ["Mug"]``, ``"profile": "Sketch"``)?"""
    for k, v in entry.items():
        if k == "name":
            continue
        vals = v if isinstance(v, list) else [v]
        if any(isinstance(x, str) and x in subjects for x in vals):
            return True
    return False


def scoped_json(text: str, subject_text: str) -> tuple[str, list[str]] | None:
    """A JSON scene dump narrowed to what the step is about: (the dump re-written with only the subject entries in
    its named lists, the subject names), or None when it isn't such a dump or the step names none of its entries."""
    try:
        doc = json.loads(text)
    except ValueError:
        return None
    if not isinstance(doc, dict):
        return None
    lists = _named_lists(doc)
    if not lists:
        return None
    # the subjects are the scene's own things the step names (objects / bodies: "the mug"); a material or a light is
    # kept for what it is attached to, never for a word of the instructions ("a glossy ceramic look")
    primary = next((k for k in lists if k.lower() in _PRIMARY), next(iter(lists)))
    subjects = {e["name"] for e in lists[primary] if _word_in(e["name"], subject_text)}
    if not subjects:
        return None
    out = {k: ([e for e in v if e["name"] in subjects or _refers(e, subjects)] if k in lists else v)
           for k, v in doc.items()}
    return json.dumps(out, indent=1, ensure_ascii=False), sorted(subjects)


# ---------------------------------------------------------------- the scene as the app evaluates it

_EDIT_MODE = re.compile(r"\bedit\s+mode\b", re.I)
_FEATURE_LISTS = ("features", "group", "children")


def _num(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _fcurve_value(keys: list, frame: float) -> float | None:
    """An fcurve's value at ``frame`` from its ``[frame, value]`` keyframes: a key's value on its frame, linear in
    between, constant outside (Blender holds the first / last key)."""
    pts = sorted((float(k[0]), float(k[1])) for k in keys
                 if isinstance(k, (list, tuple)) and len(k) >= 2 and _num(k[0]) and _num(k[1]))
    if not pts:
        return None
    if frame <= pts[0][0]:
        return pts[0][1]
    for (f0, v0), (f1, v1) in zip(pts, pts[1:]):
        if f0 <= frame <= f1:
            return v0 if f1 == f0 else v0 + (v1 - v0) * (frame - f0) / (f1 - f0)
    return pts[-1][1]


def _animated(doc: dict) -> bool:
    """An object's animated channels hold their keyed value: a location / scale typed on a frame and never keyed is
    lost as soon as the frame changes (the saved field still shows it). Each animated channel is set to its fcurve's
    value at the scene's current frame."""
    scene = doc.get("scene") if isinstance(doc.get("scene"), dict) else {}
    frame = next((float(scene[k]) for k in ("frame_current", "frame_start") if _num(scene.get(k))), 1.0)
    changed = False
    for obj in doc.get("objects") or []:
        anim = obj.get("animation") if isinstance(obj, dict) else None
        for fc in (anim.get("fcurves") or []) if isinstance(anim, dict) else []:
            if not isinstance(fc, dict):
                continue
            path, i = fc.get("data_path"), fc.get("index")
            field_ = {"rotation_euler": "rotation_deg"}.get(str(path), str(path))
            vec = obj.get(field_)
            if not isinstance(i, int) or not isinstance(vec, list) or not 0 <= i < len(vec) or not _num(vec[i]):
                continue
            v = _fcurve_value(fc.get("keyframes") or [], frame)
            if v is None:
                continue
            if field_ == "rotation_deg" and path == "rotation_euler":
                v = v * 180.0 / 3.141592653589793
            if abs(v - float(vec[i])) > 1e-6:
                vec[i] = round(v, 6)
                changed = True
    return changed


def _unused_slots(doc: dict) -> bool:
    """A material in a slot no face uses is on the object only in name (``material_slots``: ``faces`` 0): the object
    is dropped from that material's ``users``."""
    unused: dict[str, set[str]] = {}
    for obj in doc.get("objects") or []:
        if not isinstance(obj, dict) or not isinstance(obj.get("material_slots"), list):
            continue
        for slot in obj["material_slots"]:
            if isinstance(slot, dict) and slot.get("faces") == 0 and isinstance(slot.get("name"), str):
                unused.setdefault(slot["name"], set()).add(str(obj.get("name")))
    changed = False
    for mat in doc.get("materials") or []:
        if isinstance(mat, dict) and mat.get("name") in unused and isinstance(mat.get("users"), list):
            keep = [u for u in mat["users"] if u not in unused[mat["name"]]]
            if keep != mat["users"]:
                mat["users"] = keep
                changed = True
    return changed


def _refers_to(entry: dict, name: str) -> bool:
    for k, v in entry.items():
        if k == "name":
            continue
        for x in v if isinstance(v, list) else [v]:
            if isinstance(x, str) and (x == name or x.startswith(name + ":") or x.startswith(name + ".")):
                return True
    return False


def _orphan_sketches(node: object) -> bool:
    """In a body (an entry with a ``tip``), a sketch that is not the tip and that no other feature uses (as its
    profile, its support...) is an abandoned try: the body's shape never sees it, so its numbers are not the model's."""
    changed = False
    if isinstance(node, list):
        for x in node:
            changed = _orphan_sketches(x) or changed
        return changed
    if not isinstance(node, dict):
        return False
    feats = node.get("features")
    if isinstance(node.get("tip"), str) and isinstance(feats, list):
        keep = []
        for f in feats:
            if (isinstance(f, dict) and "sketch" in str(f.get("type") or "").lower() and f.get("name") != node["tip"]
                    and isinstance(f.get("name"), str)
                    and not any(isinstance(g, dict) and g is not f and _refers_to(g, f["name"]) for g in feats)):
                changed = True
                continue
            keep.append(f)
        node["features"] = keep
    for v in node.values():
        if isinstance(v, (list, dict)):
            changed = _orphan_sketches(v) or changed
    return changed


def _mesh_size(doc: dict) -> bool:
    """A step done in Edit mode changes the mesh, never the object's transform: each object's ``dimensions`` are read
    at scale 1 (an object scaled in Object mode to the same size did not do the step)."""
    changed = False
    for obj in doc.get("objects") or []:
        if not isinstance(obj, dict):
            continue
        dims, scale = obj.get("dimensions"), obj.get("scale")
        if not (isinstance(dims, list) and isinstance(scale, list) and len(dims) == len(scale)
                and all(_num(x) for x in dims + scale)) or all(abs(s - 1) < 1e-6 for s in scale):
            continue
        obj["dimensions"] = [round(d / s, 4) if s else d for d, s in zip(dims, scale)]
        changed = True
    return changed


def _last_key_mode(doc: dict) -> bool:
    """A keyframe's interpolation sets the curve from that key to the next one, so the last key's mode changes nothing
    (box-selecting all but the last key before T > Constant still makes the whole clip tick): it reads as the mode of
    the key before it."""
    changed = False
    for obj in doc.get("objects") or []:
        anim = obj.get("animation") if isinstance(obj, dict) else None
        for fc in (anim.get("fcurves") or []) if isinstance(anim, dict) else []:
            modes = fc.get("interpolation") if isinstance(fc, dict) else None
            if isinstance(modes, list) and len(modes) >= 2 and len(modes) == len(fc.get("keyframes") or []) \
                    and modes[-1] != modes[-2]:
                modes[-1] = modes[-2]
                changed = True
    return changed


def scene_view(text: str, subject_text: str = "") -> str | None:
    """A JSON scene dump as the app evaluates it (animated channels at the current frame, a curve's last key read as
    the key before it, materials only where faces use them, a body's abandoned sketches left out, an Edit-mode step's
    objects at their mesh size), re-written, or
    None when nothing changes (or it isn't JSON)."""
    try:
        doc = json.loads(text)
    except ValueError:
        return None
    if not isinstance(doc, dict):
        return None
    changed = _animated(doc)
    changed = _last_key_mode(doc) or changed
    changed = _unused_slots(doc) or changed
    changed = _orphan_sketches(doc) or changed
    if _EDIT_MODE.search(subject_text or ""):
        changed = _mesh_size(doc) or changed
    return json.dumps(doc, indent=1, ensure_ascii=False) if changed else None


# Blender's primitives as added (Shift+A), in metres: an object of one of these whose scale was applied (Ctrl+A) has
# scale 1 and the new size in its dimensions
_PRIMITIVE_SIZE = {"cube": (2.0, 2.0, 2.0), "sphere": (2.0, 2.0, 2.0), "icosphere": (2.0, 2.0, 2.0),
                   "cylinder": (2.0, 2.0, 2.0), "cone": (2.0, 2.0, 2.0), "torus": (2.5, 2.5, 0.5)}


def _applied_scale(doc: dict) -> bool:
    changed = False
    for obj in doc.get("objects") or []:
        if not isinstance(obj, dict) or str(obj.get("type") or "MESH") != "MESH":
            continue
        base = re.sub(r"\.\d+$", "", str(obj.get("name") or "")).lower()
        size, dims, scale = _PRIMITIVE_SIZE.get(base), obj.get("dimensions"), obj.get("scale")
        if size is None or not (isinstance(dims, list) and isinstance(scale, list) and len(dims) == 3 == len(scale)
                                and all(_num(x) for x in dims + scale)):
            continue
        if any(abs(s - 1) > 1e-6 for s in scale) or all(abs(d - z) < 1e-4 for d, z in zip(dims, size)):
            continue
        obj["scale"] = [round(d / z, 4) for d, z in zip(dims, size)]
        changed = True
    return changed


def _radius_diameter(node: object) -> bool:
    """A Radius constraint of r is a Diameter of 2r (and back): the same circle."""
    changed = False
    if isinstance(node, list):
        for x in node:
            changed = _radius_diameter(x) or changed
    elif isinstance(node, dict):
        t, v = node.get("type"), node.get("value")
        if t in ("Radius", "Diameter") and _num(v):
            node["type"], node["value"] = ("Diameter", round(v * 2, 6)) if t == "Radius" else ("Radius", round(v / 2, 6))
            changed = True
        for x in node.values():
            if isinstance(x, (list, dict)):
                changed = _radius_diameter(x) or changed
    return changed


# the Principled BSDF inputs Blender 4.0 renamed (3.x name: 4.x name): a lesson written for one reads a dump of the other
_BSDF_RENAMED = {"transmission": "transmission_weight", "subsurface": "subsurface_weight", "clearcoat": "coat_weight",
                 "clearcoat_roughness": "coat_roughness", "sheen": "sheen_weight", "specular": "specular_ior_level",
                 "emission": "emission_color"}


def _bsdf_names(node: object) -> bool:
    """Each renamed Principled BSDF input under its other name too (``transmission_weight`` is ``transmission``)."""
    changed = False
    if isinstance(node, list):
        for x in node:
            changed = _bsdf_names(x) or changed
    elif isinstance(node, dict):
        for old, new in _BSDF_RENAMED.items():
            for a, b in ((old, new), (new, old)):
                if a in node and b not in node:
                    node[b] = node[a]
                    changed = True
        for x in list(node.values()):
            if isinstance(x, (list, dict)):
                changed = _bsdf_names(x) or changed
    return changed


# a step that says which way a part turns or which axis a side runs along: the sign / the order is then the point
_DIRECTED_TURN = re.compile(r"\b(?:clockwise|counter-?clockwise|anti-?clockwise|negative|minus|backwards?|"
                            r"towards?|away)\b|(?<![\w.])-\s?\d", re.I)
_NAMED_AXIS = re.compile(r"(?<![\w.])[XY](?![\w])|\balong\b")


def _turn_magnitude(doc: dict) -> bool:
    """"Turn the cone 90 degrees on X": R X -90 turns it 90 degrees the other way round; each rotation is read as its
    size (``-90`` as ``90``)."""
    changed = False
    for o in _objects(doc):
        rot = o.get("rotation_deg")
        if isinstance(rot, list) and any(_num(v) and v < 0 for v in rot):
            o["rotation_deg"] = [abs(v) if _num(v) else v for v in rot]
            changed = True
    return changed


def _footprint_turned(doc: dict) -> bool:
    """"One body 80 by 50 by 30 mm": a rectangle drawn with its long side along Y is the same body turned on the
    sketch plane; each bound box is also read with its X and Y swapped."""
    changed = False
    for n in _walk(doc):
        bb = n.get("bound_box")
        if isinstance(bb, list) and len(bb) == 3 and all(_num(v) for v in bb) and bb[0] != bb[1]:
            n["bound_box"] = [bb[1], bb[0], bb[2]]
            changed = True
    return changed


def _packed_images(doc: dict) -> bool:
    """An image packed into the .blend (File > External Data > Pack Resources) has an empty filepath: it is still the
    file it was opened from, which its name keeps (``kloofendal_2k.hdr``)."""
    changed = False
    for img in doc.get("images") or []:
        if isinstance(img, dict) and img.get("packed") is True and not img.get("filepath") \
                and isinstance(img.get("name"), str) and "." in img["name"]:
            img["filepath"] = f"//{img['name']}"
            changed = True
    return changed


# the name Blender gives a light it adds (Shift+A > Light > Area is "Area"); the default scene's light is "Light"
_LIGHT_NAMES = {"POINT": "Point", "SUN": "Sun", "SPOT": "Spot", "AREA": "Area"}


def _lights_by_type(doc: dict) -> bool:
    """A light is the kind its type says, whatever it is called: the default "Light" switched to Area in Light
    Properties is an area light. Each light (and its object) is also read under the name Shift+A gives its type."""
    renamed: dict[str, str] = {}
    for light in doc.get("lights") or []:
        if not isinstance(light, dict) or not isinstance(light.get("name"), str):
            continue
        new = _LIGHT_NAMES.get(str(light.get("type") or "").upper())
        if new and light["name"] != new and not re.fullmatch(rf"{new}(?:\.\d+)?", light["name"]):
            renamed[light["name"]] = new
    if not renamed:
        return False
    for node in [*(doc.get("lights") or []), *(doc.get("objects") or [])]:
        if isinstance(node, dict) and node.get("name") in renamed:
            node["name"] = renamed[node["name"]]
    return True


def _body_holes(body: dict) -> list[dict]:
    shape = body.get("shape")
    holes = shape.get("holes") if isinstance(shape, dict) else None
    return [h for h in holes if isinstance(h, dict)] if isinstance(holes, list) else []


def _through_pockets(doc: dict) -> bool:
    """A Pocket of Type Length whose holes all go through the body (5 mm deep in a 5 mm plate) cuts what Through all
    cuts: its Type is also read as ThroughAll."""
    changed = False
    for body in _walk(doc):
        holes = _body_holes(body)
        if not holes or not all(h.get("through") is True for h in holes) or not isinstance(body.get("features"), list):
            continue
        for f in body["features"]:
            if isinstance(f, dict) and "pocket" in str(f.get("type") or "").lower() \
                    and str(f.get("Type") or "") not in ("", "ThroughAll"):
                f["Type"] = "ThroughAll"
                changed = True
    return changed


def _cut_holes(doc: dict) -> bool:
    """A round hole cut through a wall some other way (a circle sketched and Extrude-cut) is a hole all the same: each
    of a body's ``through_holes`` is also read as a Hole feature of its diameter."""
    holes = [h for n in _walk(doc) for h in (n.get("through_holes") or [])
             if isinstance(n.get("through_holes"), list) and isinstance(h, dict) and _num(h.get("diameter"))]
    feats = doc.get("features")
    if not holes or not isinstance(feats, list) or any(isinstance(f, dict) and str(f.get("type")) == "Hole"
                                                       for f in feats):
        return False
    for k, h in enumerate(holes):
        feats.append({"name": f"(cut hole {k + 1})", "type": "Hole", "diameter": h["diameter"],
                      **({"axis": h["axis"]} if isinstance(h.get("axis"), list) else {})})
    return True


def alt_views(text: str, subject_text: str = "") -> list[str]:
    """The same JSON scene written the other ways a step's numbers may be read (a second chance for a pattern): an
    applied scale as the primitive's scale (a 1 m sphere is a 2 m UV sphere at scale 0.5), a Radius as its Diameter,
    a Principled BSDF input under its Blender 3.x / 4.x name; and, unless the step's words give a direction or name
    an axis, a rotation by its size (R X -90 is turned 90 degrees) and a body's footprint turned on its plane (50 by
    80 is 80 by 50). Also a packed image under the file it came from, a light under its type's name, a Pocket that
    cuts through as Through all, and a hole Extrude-cut through a wall as a Hole."""
    out = []
    fs = [_applied_scale, _radius_diameter, _bsdf_names, _packed_images, _lights_by_type, _through_pockets,
          _cut_holes]
    if not _DIRECTED_TURN.search(subject_text or ""):
        fs.append(_turn_magnitude)
    if not _NAMED_AXIS.search(subject_text or ""):
        fs.append(_footprint_turned)
    for f in fs:
        try:
            doc = json.loads(text)
        except ValueError:
            return out
        if isinstance(doc, dict) and f(doc):
            out.append(json.dumps(doc, indent=1, ensure_ascii=False))
    return out


# "Give the Key at least twice the Fill's power": a comparison between two of the scene's own things
_TIMES = {"twice": 2.0, "double": 2.0, "triple": 3.0, "thrice": 3.0, "half": 0.5}
_WORD_N = {"two": 2.0, "three": 3.0, "four": 4.0, "five": 5.0, "ten": 10.0}
_PROPERTY = {"power": ("energy", "power", "watts"), "brightness": ("energy", "strength", "power"),
             "strength": ("strength", "energy"), "energy": ("energy",), "size": ("size",), "radius": ("radius",)}


def _factor(word: str) -> float | None:
    w = re.sub(r"\s+", " ", word.strip().lower())
    if w in _TIMES:
        return _TIMES[w]
    m = re.fullmatch(r"(\d+(?:\.\d+)?|two|three|four|five|ten)\s*(?:times|x|×)", w)
    if not m:
        return None
    return _WORD_N.get(m.group(1)) or float(m.group(1))


def claims(text: str, doc: dict) -> list[str]:
    """What the step's own words say about the scene that the dump contradicts: a comparison between two named entries
    ("the Key at least twice the Fill's power": ["Key's energy 400 is not at least 2 times Fill's 300"]), an object's
    place on one axis ("Cube at X 2"), where every key of a curve ends ("Keys end on frame 97"), a part that must be
    one piece with what it touches, which wall a hole goes through, and a component the step builds a body in."""
    out: list[str] = [*_axis_claims(text, doc), *_key_end_claims(text, doc), *_one_piece_claims(text, doc),
                      *_wall_claims(text, doc), *_component_claims(text, doc), *_modifier_off_claims(text, doc),
                      *_uv_overlap_claims(text, doc), *_overshoot_claims(text, doc), *_shell_open_claims(text, doc),
                      *_height_claims(text, doc), *_colorspace_claims(text, doc), *_parent_claims(text, doc),
                      *_zero_modifier_claims(text, doc), *_slot_claims(text, doc), *_link_claims(text, doc),
                      *_hole_count_claims(text, doc), *_plane_claims(text, doc)]
    for entries in _named_lists(doc).values():
        by_name = {e["name"]: e for e in entries}
        for a, ea in by_name.items():
            for b, eb in by_name.items():
                if a == b or not _word_in(a, text) or not _word_in(b, text):
                    continue
                rx = re.compile(rf"(?<!\w){re.escape(a)}(?!\w)[^.;]{{0,40}}?\bat\s+(least|most)\s+"
                                rf"(twice|double|triple|thrice|half|(?:\d+(?:\.\d+)?|two|three|four|five|ten)\s*"
                                rf"(?:times|x|×))\s+(?:(?:as\s+\w+\s+as\s+)?the\s+)?{re.escape(b)}(?:'s|’s)?\s+(\w+)",
                                re.I)
                for m in rx.finditer(text):
                    n = _factor(m.group(2))
                    keys = _PROPERTY.get(m.group(3).lower(), (m.group(3).lower(),))
                    key = next((k for k in keys if _num(ea.get(k)) and _num(eb.get(k))), None)
                    if n is None or key is None:
                        continue
                    va, vb = float(ea[key]), float(eb[key])
                    ok = va >= n * vb - 1e-9 if m.group(1).lower() == "least" else va <= n * vb + 1e-9
                    if not ok:
                        out.append(f"{a}'s {key} {va:g} is not at {m.group(1).lower()} {n:g} times {b}'s {vb:g}")
    return out


_AXES = "XYZ"


def _objects(doc: dict) -> list[dict]:
    return [o for o in doc.get("objects") or [] if isinstance(o, dict) and isinstance(o.get("name"), str)]


def _axis_claims(text: str, doc: dict) -> list[str]:
    """"Cube at X 2": the named object's location on that axis is 2 (G Y 2 put the 2 on the wrong axis)."""
    out = []
    for o in _objects(doc):
        loc = o.get("location")
        if not (isinstance(loc, list) and len(loc) == 3 and all(_num(v) for v in loc)):
            continue
        rx = re.compile(rf"(?<!\w){re.escape(o['name'])}(?!\w)\s+(?:is\s+|sits\s+|now\s+)?at\s+([XYZ])\s*=?\s*"
                        rf"(-?\d+(?:\.\d+)?)(?!\.?\d)", re.I)
        for m in rx.finditer(text):
            k, want = _AXES.index(m.group(1).upper()), float(m.group(2))
            if abs(float(loc[k]) - want) > 1e-3:
                out.append(f"{o['name']} is at {m.group(1).upper()} {float(loc[k]):g}, not {want:g} "
                           f"(location {', '.join(f'{v:g}' for v in loc)})")
    return out


_KEYS_END = re.compile(r"\bkey(?:s|frames?)\b[^.;]{0,30}?\bend\w*\s+(?:on|at)\s+frame\s+(\d+)", re.I)


def _key_end_claims(text: str, doc: dict) -> list[str]:
    """"Keys end on frame 97": every animated channel of the step's objects ends there (scaling only the Z channel in
    the Graph Editor leaves the X travel ending on frame 49)."""
    out = []
    for m in _KEYS_END.finditer(text):
        end = float(m.group(1))
        animated = [o for o in _objects(doc) if isinstance(o.get("animation"), dict)]
        named = [o for o in animated if _word_in(o["name"], text)] or animated
        for o in named:
            for fc in o["animation"].get("fcurves") or []:
                frames = [float(k[0]) for k in (fc.get("keyframes") or []) if isinstance(fc, dict)
                          and isinstance(k, (list, tuple)) and k and _num(k[0])]
                if frames and abs(max(frames) - end) > 1e-3:
                    ch = f"{fc.get('data_path')}[{fc.get('index')}]" if fc.get("index") is not None \
                        else str(fc.get("data_path"))
                    out.append(f"{o['name']}'s {ch} keys end on frame {max(frames):g}, not {end:g}: select all of its "
                               f"keys before scaling")
                    break
    return out


_ONE_PIECE = re.compile(r"\bone\s+(?:piece|mesh|object)\b|\bjoin(?:s|ed)?\b", re.I)


def _box(o: dict, widest: bool) -> list[tuple[float, float]] | None:
    loc, dims = o.get("location"), o.get("dimensions")
    if not (isinstance(loc, list) and isinstance(dims, list) and len(loc) == 3 == len(dims)
            and all(_num(v) for v in loc + dims)):
        return None
    half = [max(dims) / 2] * 3 if widest else [d / 2 for d in dims]
    return [(c - h * 1.1, c + h * 1.1) for c, h in zip(loc, half)]


def _one_piece_claims(text: str, doc: dict) -> list[str]:
    """A step whose part must be one piece with the object it is about ("the handle joins the mug", "Mug is one
    piece"), where another mesh object the step never names touches that object: it is a separate object pushed
    against it (a Torus for a handle), not part of its mesh. A flat object (a floor plane) is never such a part."""
    if not _ONE_PIECE.search(text):
        return []
    meshes = [o for o in _objects(doc) if str(o.get("type") or "MESH") == "MESH"]
    subjects = [o for o in meshes if _word_in(o["name"], text)]
    out = []
    for o in meshes:
        dims = o.get("dimensions")
        if o in subjects or not isinstance(dims, list) or not all(_num(d) and d > 0 for d in dims):
            continue
        ob = _box(o, widest=True)
        for subj in subjects:
            sb = _box(subj, widest=False)
            if ob and sb and all(a0 <= b1 and b0 <= a1 for (a0, a1), (b0, b1) in zip(ob, sb)):
                out.append(f"{o['name']} is a separate object against {subj['name']}, not part of its mesh: build it "
                           f"from {subj['name']}'s own faces in Edit mode (or join it, Ctrl+J)")
                break
    return out


_WALL = re.compile(r"\b(short|long)(?:er)?\s+(?:wall|side|end|face)s?\b", re.I)


def _walk(node: object):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _wall_claims(text: str, doc: dict) -> list[str]:
    """"Pick the outside face of one short wall": a Hole's axis runs along the body's long side through a short wall
    (and across it through a long wall). The body is the largest bounding box in the design."""
    m = _WALL.search(text)
    if not m:
        return []
    boxes = [n["bound_box"] for n in _walk(doc) if isinstance(n.get("bound_box"), list) and len(n["bound_box"]) >= 2
             and all(_num(v) for v in n["bound_box"][:2])]
    if not boxes:
        return []
    bx = max(boxes, key=lambda b: b[0] * b[1])
    if abs(bx[0] - bx[1]) < 1e-6:
        return []
    long_axis = 0 if bx[0] > bx[1] else 1
    want = long_axis if m.group(1).lower() == "short" else 1 - long_axis
    out = []
    for n in _walk(doc):
        axis = n.get("axis")
        if str(n.get("type") or "").lower() != "hole" or not (isinstance(axis, list) and len(axis) >= 2
                                                             and all(_num(v) for v in axis[:2])):
            continue
        k = 0 if abs(axis[0]) >= abs(axis[1]) else 1
        if abs(axis[k]) > 1e-6 and k != want:
            side = "long" if m.group(1).lower() == "short" else "short"
            out.append(f"{n.get('name') or 'the hole'} goes through a {side} wall (its axis runs along "
                       f"{_AXES[k]}, across the {bx[1 - k]:g} mm side), not a {m.group(1).lower()} one")
    return out


_BUILDS_BODY = re.compile(r"\bactivat\w*\b|\bnew\s+body\b|\bextrud\w*\b", re.I)


def _component_claims(text: str, doc: dict) -> list[str]:
    """A component the step names and builds a body in ("activate the Lid component ... extrude ... into a new body")
    that has no body: the extrude went into another component (the one still active)."""
    if not _BUILDS_BODY.search(text):
        return []
    out = []
    for c in doc.get("components") or []:
        if isinstance(c, dict) and isinstance(c.get("name"), str) and isinstance(c.get("bodies"), list) \
                and not c["bodies"] and _word_in(c["name"], text) \
                and re.search(rf"\bactivat\w*\b[^.]{{0,60}}(?<!\w){re.escape(c['name'])}(?!\w)|"
                              rf"(?<!\w){re.escape(c['name'])}(?!\w)[^.]{{0,40}}\bactiv", text, re.I):
            out.append(f"{c['name']} has no body: the new body went into another component (activate {c['name']} "
                       f"first, then extrude)")
    return out


def _subject_objects(text: str, doc: dict) -> list[dict]:
    objs = _objects(doc)
    return [o for o in objs if _word_in(o["name"], text)] or objs


_TURNS_OFF = re.compile(r"\b(?:disabl\w*|hid(?:e|es|den|ing)|turn\w*\s+(?:it\s+)?off|toggl\w*|show_\w+|mute\w*)\b",
                        re.I)


def _modifier_off_claims(text: str, doc: dict) -> list[str]:
    """A modifier the step adds that is switched off in both the viewport and the render (the monitor and camera icons
    in its header): it is in the stack but changes nothing, so its settings are not the model's."""
    if not re.search(r"\bmodifier", text, re.I) or _TURNS_OFF.search(text):
        return []
    out = []
    for o in _subject_objects(text, doc):
        for m in o.get("modifiers") or []:
            if isinstance(m, dict) and m.get("show_viewport") is False and m.get("show_render") is False:
                out.append(f"{o['name']}'s {m.get('name') or m.get('type')} modifier is switched off in the viewport "
                           f"and the render (the monitor and camera icons in its header): turn them back on")
    return out


_NO_OVERLAP = re.compile(r"\b(?:no|not|don'?t|doesn'?t|never|without)\b[^.;]{0,40}?\boverlap|\bnon-?overlapping\b",
                         re.I)


def _uv_overlap_claims(text: str, doc: dict) -> list[str]:
    """"No island should overlap another": the subject's UV map has islands on top of each other (U > Reset lays every
    face over the whole square)."""
    if not _NO_OVERLAP.search(text):
        return []
    out = []
    for o in _subject_objects(text, doc):
        uv = o["mesh"].get("uv") if isinstance(o.get("mesh"), dict) else None
        n = uv.get("overlapping_islands") if isinstance(uv, dict) else None
        if _num(n) and n > 0:
            out.append(f"{o['name']}'s UV map has {n:g} overlapping island{'s' if n != 1 else ''}: select all and "
                       f"press U > Unwrap (not Reset)")
    return out


_OVERSHOOT = re.compile(r"\bovershoot\w*|\b(?:rise|rises|rising|go|goes|swing|swings)\s+(?:above|past|beyond|over)\b",
                        re.I)


def _overshoot_claims(text: str, doc: dict) -> list[str]:
    """"The curve rises past 5 before settling": no animated curve of the subject goes above its last key (the
    evaluated curve's maximum is the final value: the handles were flattened, not tilted)."""
    if not _OVERSHOOT.search(text):
        return []
    curves = []
    for o in _subject_objects(text, doc):
        anim = o.get("animation")
        for fc in (anim.get("fcurves") or []) if isinstance(anim, dict) else []:
            rng, keys = (fc.get("evaluated_range"), fc.get("keyframes")) if isinstance(fc, dict) else (None, None)
            if isinstance(rng, list) and len(rng) == 2 and all(_num(v) for v in rng) and isinstance(keys, list) \
                    and keys and isinstance(keys[-1], (list, tuple)) and len(keys[-1]) >= 2 and _num(keys[-1][1]):
                curves.append((o["name"], fc, float(rng[1]), float(keys[-1][1])))
    if not curves or any(hi > last + 1e-6 for _, _, hi, last in curves):
        return []
    name, fc, hi, _ = curves[0]
    return [(f"{name}'s {fc.get('data_path')}[{fc.get('index')}] curve never rises above its last key ({hi:g}): "
             f"tilt the key's handle so the curve overshoots")]


_OPEN_FACE = re.compile(r"\bopen\b|\bopening\b|\bremov\w*\b", re.I)


def _shell_open_claims(text: str, doc: dict) -> list[str]:
    """A Shell the step opens ("click the top face so it is removed") that removed no face: the body is a closed box
    with a hidden skin inside."""
    if not _OPEN_FACE.search(text):
        return []
    return [f"{n.get('name') or 'the Shell'} removed no face: the body is closed; edit it and click the face to open"
            for n in _walk(doc) if "shell" in str(n.get("type") or "").lower() and n.get("faces_removed") == 0]


_TALL = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*mm\s+(?:tall|high)\b", re.I)


def _height_claims(text: str, doc: dict) -> list[str]:
    """"30 mm tall" from an extrude of distance 30 set to Symmetric (measured one side): 30 mm each way, 60 mm tall.
    Only when no body of the design measures 30 on any side (a whole-length symmetric extrude does)."""
    m = _TALL.search(text)
    if not m:
        return []
    want = float(m.group(1))
    boxes = [n["bound_box"] for n in _walk(doc) if isinstance(n.get("bound_box"), list) and len(n["bound_box"]) == 3
             and all(_num(v) for v in n["bound_box"])]
    if any(abs(v - want) <= 1e-3 for bb in boxes for v in bb):
        return []
    out = []
    for n in _walk(doc):
        if str(n.get("extent") or "").lower() == "symmetric" and _num(n.get("distance")) \
                and abs(float(n["distance"]) - want) <= 1e-3 \
                and not re.search(r"whole|full|total", str(n.get("measurement") or ""), re.I):
            size = f": the body measures {' x '.join(f'{v:g}' for v in boxes[0])} mm" if boxes else ""
            out.append(f"{n.get('name') or 'the extrude'} is Symmetric, so its {want:g} mm go both ways ({2 * want:g} "
                       f"mm tall){size}; set Direction to One Side")
    return out


_NON_COLOR = re.compile(r"\bnon[-\s]?colou?r\b", re.I)
# a shader input that takes numbers, not colours: an image feeding one must be read as Non-Color data
_DATA_SOCKETS = frozenset("""roughness metallic normal specular alpha height displacement strength ior distance
anisotropic""".split()) | {"specular ior level", "specular tint", "coat weight", "coat roughness", "transmission weight",
                           "subsurface weight", "sheen weight", "emission strength"}
_DATA_NODES = frozenset({"NORMAL_MAP", "BUMP", "DISPLACEMENT", "VECTOR_DISPLACEMENT"})


def _node_trees(doc: dict) -> list[dict]:
    return [t for t in [*(doc.get("materials") or []), doc.get("world")] if isinstance(t, dict)
            and isinstance(t.get("nodes"), list) and isinstance(t.get("links"), list)]


def _colorspace_claims(text: str, doc: dict) -> list[str]:
    """A step that sets an image's Color Space to Non-Color: an Image Texture that feeds a number input (Roughness,
    Metallic, a Normal Map) must be Non-Color, and one that feeds a colour (Base Color) must not be (Non-Color on the
    wrong node washes the colours out and leaves the roughness gamma-curved)."""
    if not _NON_COLOR.search(text):
        return []
    out = []
    for tree in _node_trees(doc):
        nodes = {n["name"]: n for n in tree["nodes"] if isinstance(n, dict) and isinstance(n.get("name"), str)}
        for link in tree["links"]:
            if not isinstance(link, dict):
                continue
            n, to = nodes.get(str(link.get("from"))), nodes.get(str(link.get("to")))
            if not n or str(n.get("type")) != "TEX_IMAGE" or not isinstance(n.get("colorspace"), str):
                continue
            sock, cs, what = str(link.get("to_socket") or ""), n["colorspace"], n.get("image") or n["name"]
            data = sock.lower() in _DATA_SOCKETS or (to is not None and str(to.get("type")) in _DATA_NODES)
            if data and cs != "Non-Color":
                out.append(f"{what} feeds {sock} but its Color Space is {cs}: set that node to Non-Color")
            elif not data and "color" in sock.lower() and cs == "Non-Color":
                out.append(f"{what} feeds {sock} but is set to Non-Color: a colour image stays sRGB (Non-Color goes on "
                           f"the image that feeds a number input such as Roughness)")
    return out


_PARENTING = re.compile(r"\bparent\w*\b|\bchild(?:ren)?\s+of\b|\bctrl\s*\+\s*p\b", re.I)


def _name_stem(name: str) -> str:
    return re.sub(r"[\s._-]*\d+$", "", name).lower()


def _parent_claims(text: str, doc: dict) -> list[str]:
    """"Parent the blades to the hub": every object of the kind the step names in the plural (Blade1, Blade2, Blade3
    for "blades") has that parent, not only the ones that were in the selection."""
    if not _PARENTING.search(text):
        return []
    objs = _objects(doc)
    out = []
    for p in sorted({o["parent"] for o in objs if isinstance(o.get("parent"), str)}):
        if not _word_in(p, text):
            continue
        for stem in sorted({_name_stem(o["name"]) for o in objs if o.get("parent") == p}):
            if not stem or not re.search(rf"(?<!\w){re.escape(stem)}s(?!\w)", text, re.I):
                continue
            for o in objs:
                if _name_stem(o["name"]) == stem and o["name"] != p and o.get("parent") != p:
                    out.append(f"{o['name']} is not parented to {p} (its parent is {o.get('parent') or 'none'}): "
                               f"select it with the others, {p} last, and press Ctrl+P > Object")
    return out


# the setting that makes a modifier do anything: at 0 (an Array of 1) it is in the stack and changes nothing
_MODIFIER_SIZE = {"BEVEL": ("width", "Amount"), "SOLIDIFY": ("thickness", "Thickness"),
                  "DISPLACE": ("strength", "Strength"), "SUBSURF": ("levels", "Levels"), "ARRAY": ("count", "Count")}


def _zero_modifier_claims(text: str, doc: dict) -> list[str]:
    """A modifier the step adds (its name in the step's words) whose size is zero: a Bevel of Amount 0 rounds nothing,
    a Solidify of Thickness 0 adds no wall."""
    out = []
    for o in _subject_objects(text, doc):
        for m in o.get("modifiers") or []:
            t = str(m.get("type") or "").upper() if isinstance(m, dict) else ""
            if t not in _MODIFIER_SIZE or not (_word_in(str(m.get("name") or ""), text) or _word_in(t, text)):
                continue
            key, shown = _MODIFIER_SIZE[t]
            v = m.get(key)
            if _num(v) and (v <= 1 if t == "ARRAY" else abs(v) < 1e-9):
                out.append(f"{o['name']}'s {m.get('name') or t} modifier has {shown} {v:g}: it changes nothing; "
                           f"set {shown} to the step's value")
    return out


def _slot_claims(text: str, doc: dict) -> list[str]:
    """A material the step names that sits in one of the object's slots no face uses (a second slot added and never
    Assigned): the object renders with the other slot's material."""
    # a name the step gives ("Glaze"); Blender's default "Material" is only ever the word "material"
    named = {m["name"] for m in doc.get("materials") or [] if isinstance(m, dict) and isinstance(m.get("name"), str)
             and not re.fullmatch(r"Material(?:\.\d+)?", m["name"]) and _word_in(m["name"], text)}
    out = []
    for o in _objects(doc):
        slots = [s for s in o.get("material_slots") or [] if isinstance(s, dict)]
        for s in slots:
            mat = s.get("material")
            if mat in named and s.get("faces") == 0 \
                    and not any(x.get("material") == mat and _num(x.get("faces")) and x["faces"] > 0 for x in slots):
                out.append(f"{mat} is in a slot of {o['name']} but no face uses it: select the faces in Edit Mode and "
                           f"click Assign (or put {mat} in the first slot)")
    return out


_CONNECT = re.compile(r"\b(?:connect|link|plug|wire)\w*\b([^.;]*)", re.I)
_NAMED = r"[A-Z][\w]*(?:\s+[A-Z][\w]*)*"
_LINK = re.compile(rf"(?:the\s+)?(?P<a>{_NAMED})['’]s\s+(?P<sa>{_NAMED})\s+(?:(?:output|socket)\s+)?(?:in)?to\s+"
                   rf"(?:the\s+)?(?P<b>{_NAMED})['’]s\s+(?P<sb>{_NAMED})")


def _link_claims(text: str, doc: dict) -> list[str]:
    """"Connect the Noise's Fac to the Color Ramp's Fac and the Color Ramp's Color to the Principled BSDF's Base
    Color": each link the step spells out (node's socket to node's socket) is in the node tree that holds both nodes.
    A node is named by a word of its name ("the Noise" is "Noise Texture")."""
    want = [m for c in _CONNECT.finditer(text) for m in _LINK.finditer(c.group(1))]
    out = []
    for m in want:
        for tree in _node_trees(doc):
            names = [n["name"] for n in tree["nodes"] if isinstance(n, dict) and isinstance(n.get("name"), str)]
            a = [n for n in names if _word_in(m.group("a"), n)]
            b = [n for n in names if _word_in(m.group("b"), n)]
            if not a or not b:
                continue
            links = [x for x in tree["links"] if isinstance(x, dict)]

            def same(v: object, want_: str) -> bool:
                return v is None or str(v).casefold() == want_.casefold()

            if any(x.get("from") in a and x.get("to") in b and same(x.get("from_socket"), m.group("sa"))
                   and same(x.get("to_socket"), m.group("sb")) for x in links):
                continue
            went = [x for x in links if x.get("from") in a and same(x.get("from_socket"), m.group("sa"))]
            where = f" goes to {went[0].get('to')}'s {went[0].get('to_socket')}" if went else " is not connected"
            out.append(f"the {m.group('a')}'s {m.group('sa')}{where}, not the {m.group('b')}'s {m.group('sb')}: "
                       f"drag it onto {m.group('sb')}")
    return out


_COUNTS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "eight": 8}
_N_HOLES = re.compile(r"\b(one|two|three|four|five|six|eight|\d+)(?!\s*(?:mm|cm|m|in)\b)\s+"
                      r"(?:\d+(?:\.\d+)?\s*mm\s+)?(?:[a-z]+\s+)?(holes|circles)\b", re.I)


def _box_area(body: dict) -> float:
    shape = body.get("shape")
    bx = (shape.get("bound_box") if isinstance(shape, dict) else None) or body.get("bound_box")
    if isinstance(bx, list) and len(bx) >= 2 and all(_num(v) for v in bx[:2]):
        return float(bx[0]) * float(bx[1])
    return 0.0


def _hole_count_claims(text: str, doc: dict) -> list[str]:
    """"Two 4 mm holes go through the plate": the body's shape has that many holes. A circle sketched off the solid
    (its centre past the plate's end) is in the sketch and the Pocket recomputes, but cuts nothing. Only the bodies
    the step names are counted; when it names none, the bodies that already have a hole (or else the largest one)."""
    if not re.search(r"\bholes?\b|\bpocket", text, re.I):
        return []
    found = []
    for m in _N_HOLES.finditer(text):
        w = m.group(1).lower()
        found.append((m.group(2).lower() != "holes", int(w) if w.isdigit() else _COUNTS.get(w, 0)))
    counts = [n for _, n in sorted(found, key=lambda x: x[0]) if n >= 2]
    if not counts:
        return []
    want = counts[0]
    bodies = [b for b in _walk(doc) if isinstance(b.get("shape"), dict) and isinstance(b["shape"].get("holes"), list)]
    named = [b for b in bodies if isinstance(b.get("name"), str) and _word_in(b["name"], text)]
    if named:
        bodies = named
    elif len(bodies) > 1:
        bodies = [b for b in bodies if _body_holes(b)] or [max(bodies, key=_box_area)]
    out = []
    for body in bodies:
        got = len(_body_holes(body))
        if got < want:
            out.append(f"{body.get('name') or 'the body'} has {got} hole{'s' if got != 1 else ''}, not {want}: a "
                       f"circle whose centre is off the part cuts nothing (check each centre)")
    return out


_BASE_PLANE = re.compile(r"\b(XY|XZ|YZ)[_\s-]?plane\b", re.I)
_SUPPORT_PLANE = re.compile(r"^(XY|XZ|YZ)(?:[_\s]Plane)?\b", re.I)


def _plane_claims(text: str, doc: dict) -> list[str]:
    """"Pick XY_Plane": the sketch is on that base plane, not another one picked in the list (XZ stands the part on
    its end). Only when the step names one base plane and no sketch on a base plane uses it."""
    named = {m.group(1).upper() for m in _BASE_PLANE.finditer(text)}
    if len(named) != 1:
        return []
    want = named.pop()
    on_planes = [(n, m.group(1).upper()) for n in _walk(doc) if "sketch" in str(n.get("type") or "").lower()
                 for key in ("support", "plane") if isinstance(n.get(key), str)
                 and (m := _SUPPORT_PLANE.match(n[key].strip()))]
    if not on_planes or any(p == want for _, p in on_planes):
        return []
    n, p = on_planes[0]
    return [f"{n.get('name') or 'the sketch'} is on the {p} plane, not {want}: make the sketch again and pick "
            f"{want}_Plane"]


# ---------------------------------------------------------------- ASCII DXF: what the drawing is

def _dxf_entities(raw: str) -> list[tuple[str, list[tuple[int, str]]]]:
    """The ENTITIES section of an ASCII DXF: (type, [(group code, value), ...]) per entity."""
    lines = raw.splitlines()
    pairs = []
    for k in range(0, len(lines) - 1, 2):
        try:
            pairs.append((int(lines[k].strip()), lines[k + 1].strip()))
        except ValueError:
            return []
    out: list[tuple[str, list[tuple[int, str]]]] = []
    inside = False
    for k, (code, val) in enumerate(pairs):
        if code == 2 and k and pairs[k - 1] == (0, "SECTION"):
            inside = val == "ENTITIES"
            continue
        if not inside:
            continue
        if code == 0:
            if val in ("ENDSEC", "EOF"):
                inside = False
                continue
            out.append((val, []))
        elif out:
            out[-1][1].append((code, val))
    return out


def _dxf_float(groups: list[tuple[int, str]], code: int) -> float | None:
    for c, v in groups:
        if c == code:
            try:
                return float(v)
            except ValueError:
                return None
    return None


# what a step calls the entities it draws (DXF entity type: its words)
_ENTITY_WORDS = {"DIMENSION": r"\bdim(?:ension\w*|linear|aligned|radius|diameter)\b", "CIRCLE": r"\bcircles?\b",
                 "LWPOLYLINE": r"\b(?:p?lines?|polylines?|rectangles?|rectang)\b", "LINE": r"\blines?\b",
                 "ARC": r"\barcs?\b", "INSERT": r"\b(?:blocks?|insert\w*)\b", "MTEXT": r"\b(?:m?text|labels?)\b",
                 "TEXT": r"\b(?:text|labels?)\b", "HATCH": r"\bhatch\w*\b"}
_ON_LAYER = re.compile(r"\bon\s+(?:the\s+)?layer\s+[\"'“]?([A-Za-z0-9_$-]+)", re.I)


def _layer_claims(text: str, ents: list[tuple[str, list[tuple[int, str]]]]) -> list[str]:
    """"On layer DIMS": the entities the step draws (its dimension) are all on another layer (group 8). A layer that
    only exists in the layer table holds nothing: it was made but never set current."""
    types = {t for t, w in _ENTITY_WORDS.items() if re.search(w, text, re.I)}
    mine = [g for t, g in ents if t in types]
    if not mine:
        return []
    layers = [next((v for c, v in g if c == 8), "0").upper() for g in mine]
    out = []
    for m in _ON_LAYER.finditer(text):
        layer = m.group(1).upper()
        if layer not in layers:
            out.append(f"what the step draws is on layer {layers[-1]}, not {layer}: set {layer} current before "
                       f"drawing (or move it there in Properties)")
    return out


# a circle's size across in the step's words: "18 mm across", "a diameter of 18", "type D for Diameter and enter 18"
_ACROSS = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(?:mm\s+)?(?:across|in\s+diameter|diameter)\b"
                     r"|\bdiameter\b[^.;\d]{0,40}?(?<![\w.])(\d+(?:\.\d+)?)(?![\d.]*\s*,)", re.I)


def _circle_size_claims(text: str, ents: list[tuple[str, list[tuple[int, str]]]]) -> list[str]:
    """Circles the step sizes by their diameter whose saved size is not it: a DXF CIRCLE stores its radius (group 40),
    and typing the number straight away at AutoCAD's CIRCLE prompt makes it the radius (twice the size)."""
    if not re.search(r"\bcircles?\b|\bCIRCLE\b", text, re.I):
        return []
    sizes = {float(m.group(1) or m.group(2)) for m in _ACROSS.finditer(text)}
    radii = [r for t, g in ents if t == "CIRCLE" and (r := _dxf_float(g, 40)) is not None]
    if len(sizes) != 1 or not radii:
        return []
    want = sizes.pop()
    if any(abs(2 * r - want) <= max(1e-3, want * 1e-4) for r in radii):
        return []
    r = radii[-1]
    how = " (the number typed at the CIRCLE prompt is the radius: type D first)" if abs(r - want) <= 1e-3 else ""
    return [f"the circles are {2 * r:g} across (radius {r:g}), not {want:g}{how}"]


_CLOSE_WORDS = re.compile(r"\bclosed?\b", re.I)
_READS = re.compile(r"\b(?:reads?|measures?|shows?)\s+(\d+(?:\.\d+)?)\b", re.I)


def dxf_claims(text: str, raw: str) -> list[str]:
    """What the step's own words say about an ASCII DXF drawing that the drawing contradicts: a profile it closes
    ("type C to close it") whose polylines are all open (group 70's closed bit is 0: clicking back on the start point
    is not closing it), and a dimension that should read a length (group 42, what it measures) when every dimension
    measures something else."""
    ents = _dxf_entities(raw)
    out = []
    polys = [g for t, g in ents if t in ("LWPOLYLINE", "POLYLINE")]
    if polys and _CLOSE_WORDS.search(text) and not any(int(_dxf_float(g, 70) or 0) & 1 for g in polys):
        out.append("the polyline is open (its closed flag is off): clicking back on the first point doesn't close it; "
                   "finish PLINE with C")
    out += _layer_claims(text, ents)
    out += _circle_size_claims(text, ents)
    dims = [g for t, g in ents if t == "DIMENSION"]
    if dims and re.search(r"\bdimension", text, re.I) and (m := _READS.search(text)):
        want = float(m.group(1))
        got = [v for g in dims if (v := _dxf_float(g, 42)) is not None]
        if got and not any(abs(v - want) <= max(0.01, want * 1e-4) for v in got):
            out.append(f"the dimension measures {got[-1]:g}, not {want:g}: pick the two corners it should span")
    return out


# ---------------------------------------------------------------- numbers a step gives as an example

# a number written into a check's regex (``2(?:\.0+)?``, ``2\.3``), not a quantifier, a class or an escape
_PATTERN_NUMBER = re.compile(r"(?<![\\\w{,.\[-])(\d+(?:\\\.\d+)?)(?:\(\?:\\\.0\+\)\?)?(?![\d,}\]-])")
_EXAMPLE = re.compile(r"\b(?:for\s+example|for\s+instance|e\.\s?g\.|such\s+as|say)\b(?:[^.()]|\.(?=\d))*", re.I)
_RELATION = re.compile(r"^\s*(?P<a>[A-Za-z]\w*)\s+(?P<n>\d+(?:\.\d+)?)\s*(?:mm|cm|m|in|°|degrees?)?\s+"
                       r"(?P<cmp>wider|narrower|longer|shorter|bigger|larger|smaller|taller|thicker|thinner|deeper|"
                       r"shallower|higher|lower|more|less)\s+than\s+(?:the\s+|its\s+)?(?P<b>[A-Za-z]\w*)", re.I)
_LESS_WORDS = frozenset({"narrower", "shorter", "smaller", "thinner", "shallower", "lower", "less"})
_PATTERN_NAME = re.compile(r'\\?"name\\?":\\s\*\\?"(\w+)\\?"')


def _only_in_examples(value: float, text: str) -> bool:
    """Does ``value`` appear in ``text``, and only inside "for example ..." clauses?"""
    num = rf"(?<![\d.]){re.escape(f'{value:g}')}(?:\.0+)?(?!\d|\.\d)"
    spans = [m.span() for m in _EXAMPLE.finditer(text)]
    hits = [m.start() for m in re.finditer(num, text)]
    return bool(hits) and all(any(a <= h < b for a, b in spans) for h in hits)


def _named_values(node: object) -> dict[str, float]:
    return {n["name"].lower(): float(n["value"]) for n in _walk(node)
            if isinstance(n.get("name"), str) and n["name"] and _num(n.get("value"))}


def example_value(check: dict, text: str) -> tuple[bool, str] | None:
    """A JSON check whose numbers the step only gives as an example ("0.3 mm wider than the arm (for example a 2 mm
    arm in a 2.3 mm slot)"): (passes, why) read from what the step really asks, else None (the numbers are the step's
    own, or the dump doesn't say). A label that states a relation ("Slot 0.3 mm wider than the arm") is checked on the
    two named values (SlotWidth - ArmWidth); otherwise the named value only has to be there, at any number."""
    pattern, subject = str(check.get("pattern") or ""), str(check.get("_subject") or "")
    label = str(check.get("label") or "")
    instructions = subject[:len(subject) - len(label)] if label and subject.endswith(label) else subject
    nums = _PATTERN_NUMBER.findall(pattern)
    if not nums or not all(_only_in_examples(float(n.replace("\\", "")), instructions) for n in nums):
        return None
    try:
        doc = json.loads(text)
    except ValueError:
        return None
    rel = _RELATION.match(label)
    name = _PATTERN_NAME.search(pattern)
    if rel and name:
        values = _named_values(doc)
        mine = name.group(1)
        a, b = rel.group("a"), rel.group("b")
        other = re.sub(re.escape(a), b, mine, count=1, flags=re.I) if re.search(re.escape(a), mine, re.I) else None
        if other is None or mine.lower() not in values or other.lower() not in values:
            return None
        n, va, vb = float(rel.group("n")), values[mine.lower()], values[other.lower()]
        diff = vb - va if rel.group("cmp").lower() in _LESS_WORDS else va - vb
        ok = abs(diff - n) <= max(1e-6, n * 1e-4)
        return ok, (f"{mine} {va:g} is {n:g} {rel.group('cmp').lower()} than {other} {vb:g}" if ok else
                    f"{mine} {va:g} is {abs(va - vb):g} from {other} {vb:g}, not {n:g} {rel.group('cmp').lower()}")
    try:
        rx = re.compile(_PATTERN_NUMBER.sub(lambda m: r"-?\d+(?:\.\d+)?", pattern), re.MULTILINE)
    except re.error:
        return None
    if rx.search(text) is None:
        return None
    return True, f"set (the step's {', '.join(n.replace(chr(92), '') for n in nums)} is an example)"


# ---------------------------------------------------------------- float noise

_LONG_DECIMAL = re.compile(r"(?<![\w.])(-?\d+\.\d{6,})(?!\d)")


def _short(m: re.Match[str]) -> str:
    v = round(float(m.group(1)), 4)
    if v == 0:
        v = 0.0  # never -0.0
    return f"{v:.1f}" if v == int(v) else repr(v)


# files an app writes its model's numbers into (scene dumps, drawings, meshes, exchange formats, data tables): their
# long decimals are binary noise. Never source code, where 0.0010004 is a value someone typed.
DUMP_EXTS = (".json", ".dxf", ".obj", ".stl", ".ply", ".gltf", ".dae", ".step", ".stp", ".iges", ".igs", ".csv",
             ".tsv", ".xml", ".usda")


def is_dump(name: str) -> bool:
    """Is ``name`` a model / data dump (``rounded`` applies), not code?"""
    return str(name).lower().endswith(DUMP_EXTS)


def rounded(text: str) -> str:
    """``text`` with every long decimal (6+ places: float32 / binary noise) written at 4 places, line structure kept:
    ``90.00000250447816`` -> ``90.0``, ``1.5707963705062866`` -> ``1.5708``."""
    return _LONG_DECIMAL.sub(_short, text)


# ---------------------------------------------------------------- every / all

_UNIVERSAL = re.compile(r"\b(?:every|all|each)\b", re.I)
_KEY_PATTERN = re.compile(r'^\\?"([A-Za-z_][\w]*)\\?"')


def every_instance(check: dict, text: str, rx: re.Pattern[str]) -> str | None:
    """A check whose label says every / all / each and whose pattern is about one JSON key (``"valid":\\s*true``):
    the first instance of that key whose value doesn't match ("``"valid": false`` at line 79"), else None."""
    # "Through all" whose pattern is "ThroughAll": the word names the value the check wants, it says nothing of how many
    if not any(w.lower() not in str(check.get("pattern") or "").lower()
               for w in _UNIVERSAL.findall(str(check.get("label") or ""))):
        return None
    m = _KEY_PATTERN.match(str(check.get("pattern") or ""))
    if not m:
        return None
    key = re.compile(rf'"{re.escape(m.group(1))}"\s*:')
    # a feature's health "warning" (Fusion turns it yellow: computed, with a note) is not an error, unless the check is
    # about warnings
    warn_ok = m.group(1).lower() in _HEALTH_KEYS and not re.search(r"warn", f"{check.get('label')} {check.get('pattern')}",
                                                                 re.I)
    for k in key.finditer(text):
        end = text.find("\n", k.start())
        item = text[k.start():len(text) if end < 0 else end]
        if not rx.match(item) and not (warn_ok and re.search(r':\s*"warning"', item, re.I)):
            return f"{item.strip().rstrip(',')} at line {text.count(chr(10), 0, k.start()) + 1}"
    return None


_HEALTH_KEYS = frozenset({"health", "status", "state"})


# ---------------------------------------------------------------- exports with nothing in them

def empty_mesh(path: str) -> str | None:
    """Why a mesh export holds no geometry (an ASCII STL with no ``facet``, a binary STL with 0 triangles, an OBJ with
    no ``f`` lines), else None (not a mesh file, unreadable, or has geometry)."""
    low = path.lower()
    if not low.endswith((".stl", ".obj")):
        return None
    name = os.path.basename(path)
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            head = fh.read(min(size, 1024 * 1024))
    except OSError:
        return None
    if low.endswith(".obj"):
        return None if re.search(rb"^\s*f\s", head, re.M) else f"{name} has no faces"
    if b"facet" in head:  # ASCII: "solid x / facet normal ... / endsolid x"
        return None
    if size >= 84:  # binary: an 80-byte header, a uint32 count, 50 bytes per triangle
        (count,) = struct.unpack("<I", head[80:84])
        if count > 0 and 84 + 50 * count == size:
            return None
    return f"{name} has no triangles (an empty export)"


MAX_MESH_TRIANGLES = 500_000
_OPEN_MESH_CACHE: dict[tuple, str | None] = {}  # (path, mtime, size) -> open_mesh's answer
_OPEN_MESH_CACHE_MAX = 32
_MISS = object()
_STL_VERTEX = re.compile(rb"^\s*vertex\s+(\S+)\s+(\S+)\s+(\S+)", re.M)

# a step whose mesh is for printing: a slicer needs a closed (watertight) shell
PRINT_WORDS = re.compile(r"\b(?:3d[\s-]*print\w*|print(?:ing|able|er)?|watertight|manifold|slicer|closed\s+shell)\b",
                         re.I)


def _stl_triangles(path: str) -> list[tuple] | None:
    try:
        size = os.path.getsize(path)
        if size > 50 * MAX_MESH_TRIANGLES + 84:
            return None
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return None
    if size >= 84:
        (count,) = struct.unpack("<I", data[80:84])
        if count and 84 + 50 * count == size:
            tris = []
            for k in range(count):
                vals = struct.unpack_from("<12f", data, 84 + 50 * k)
                tris.append((vals[3:6], vals[6:9], vals[9:12]))
            return tris
    verts = []
    for m in _STL_VERTEX.finditer(data):
        try:
            verts.append(tuple(float(x) for x in m.groups()))
        except ValueError:
            return None
    if not verts or len(verts) % 3:
        return None
    return [tuple(verts[i:i + 3]) for i in range(0, len(verts), 3)]


def mesh_extent(path: str) -> list[float] | None:
    """An STL's size along X, Y, Z (its vertices' bounding box), or None (not an STL, unreadable, empty)."""
    tris = _stl_triangles(path)
    pts = [v for t in tris or [] for v in t]
    if not pts:
        return None
    return [max(p[k] for p in pts) - min(p[k] for p in pts) for k in range(3)]


def mesh_vs_bodies(mesh: str, dump_text: str) -> str | None:
    """An exported mesh whose size is no body's in the model's scene dump (``bodies[].shape.bound_box``): File > Export
    with one feature selected (the first Pad) writes that feature's shape, not the finished body. Why, else None (no
    bodies with a size, or the mesh matches one of them, in any orientation)."""
    try:
        doc = json.loads(dump_text)
    except ValueError:
        return None
    boxes = [(str(n.get("name") or "the body"), [float(v) for v in n["shape"]["bound_box"]])
             for n in _walk(doc) if isinstance(n.get("shape"), dict) and isinstance(n["shape"].get("bound_box"), list)
             and len(n["shape"]["bound_box"]) == 3 and all(_num(v) for v in n["shape"]["bound_box"])]
    ext = mesh_extent(mesh)
    if not boxes or ext is None:
        return None

    def same(a: list[float], b: list[float]) -> bool:
        return all(abs(x - y) <= max(0.05, 0.01 * max(abs(x), abs(y))) for x, y in zip(sorted(a), sorted(b)))

    if any(same(ext, bb) for _, bb in boxes):
        return None
    name, bb = max(boxes, key=lambda x: x[1][0] * x[1][1] * x[1][2])
    return (f"{os.path.basename(mesh)} measures {' x '.join(f'{v:g}' for v in ext)} but {name} measures "
            f"{' x '.join(f'{v:g}' for v in bb)}: select the Body (not one of its features) and export again")


def open_mesh(path: str) -> str | None:
    """Why an STL is not a closed shell (an edge that belongs to one triangle only: a hole, an export of some faces
    instead of the body), else None (closed, not an STL, unreadable, or no vertices to judge)."""
    if not path.lower().endswith(".stl"):
        return None
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = (os.path.abspath(path), st.st_mtime_ns, st.st_size)
    cached = _OPEN_MESH_CACHE.get(key, _MISS)  # a print step's check runs on every evaluation: parse each file once
    if cached is not _MISS:
        return cached  # type: ignore[return-value]
    why = _open_edges(path)
    if len(_OPEN_MESH_CACHE) >= _OPEN_MESH_CACHE_MAX:
        _OPEN_MESH_CACHE.clear()
    _OPEN_MESH_CACHE[key] = why
    return why


def _open_edges(path: str) -> str | None:
    tris = _stl_triangles(path)
    if not tris:
        return None
    edges: dict[tuple, int] = {}
    for tri in tris:
        pts = [tuple(round(c, 4) for c in p) for p in tri]
        for a, b in ((pts[0], pts[1]), (pts[1], pts[2]), (pts[2], pts[0])):
            if a != b:
                e = (a, b) if a < b else (b, a)
                edges[e] = edges.get(e, 0) + 1
    border = sum(1 for n in edges.values() if n == 1)
    if not border:
        return None
    return (f"{os.path.basename(path)} is not watertight: {border} edge{'s' if border != 1 else ''} belong to one "
            f"triangle only (an open shell, not the whole body)")


# ---------------------------------------------------------------- DXF group codes

def _string_code(code: int) -> bool:
    """DXF group codes whose value is text (an entity type, a name, a dimension's text override...)."""
    return (0 <= code <= 9 or code in (100, 102, 105, 999) or 300 <= code <= 369 or 390 <= code <= 399
            or 410 <= code <= 419 or 430 <= code <= 439 or 470 <= code <= 481 or 1000 <= code <= 1009)


_NUMBER = re.compile(r"[-+]?\d+(?:\.\d+)?")


def dxf_numeric_ok(lines: list[str], line_no: int, matched: str) -> bool:
    """Is a match on (1-based) line ``line_no`` of an ASCII DXF fine to count? A number counts only as the value of a
    numeric group (a coordinate, a measurement: group 10, 42...), never as text (group 1, a DIMENSION's typed
    override) or as a group code itself. Anything that isn't a bare number always counts."""
    if not _NUMBER.fullmatch(matched.strip()):
        return True
    if line_no % 2 == 1:
        return False  # a group code line (DXF: code, value, code, value ... from line 1)
    try:
        code = int(lines[line_no - 2].strip())
    except (IndexError, ValueError):
        return True
    return not _string_code(code)


# DXF group codes whose value is a symbol table name AutoCAD compares without case: a block / table entry's name (2),
# a layer (8), a linetype (6), a text style (7)
_NAME_CODES = frozenset({2, 6, 7, 8})


def dxf_name_ok(lines: list[str], line_no: int) -> bool:
    """Is (1-based) line ``line_no`` of an ASCII DXF the value of a name group (a layer, a block, a style)? AutoCAD
    names ignore case (a layer typed ``Wheels`` is the layer WHEELS to every command), so a name is matched without
    case there and nowhere else."""
    if line_no % 2 == 1 or line_no < 2:
        return False
    try:
        return int(lines[line_no - 2].strip()) in _NAME_CODES
    except (IndexError, ValueError):
        return False

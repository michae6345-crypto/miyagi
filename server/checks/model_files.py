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


def scene_view(text: str, subject_text: str = "") -> str | None:
    """A JSON scene dump as the app evaluates it (animated channels at the current frame, materials only where faces
    use them, a body's abandoned sketches left out, an Edit-mode step's objects at their mesh size), re-written, or
    None when nothing changes (or it isn't JSON)."""
    try:
        doc = json.loads(text)
    except ValueError:
        return None
    if not isinstance(doc, dict):
        return None
    changed = _animated(doc)
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


def alt_views(text: str) -> list[str]:
    """The same JSON scene written the other ways a step's numbers may be read (a second chance for a pattern): an
    applied scale as the primitive's scale (a 1 m sphere is a 2 m UV sphere at scale 0.5), a Radius as its Diameter."""
    out = []
    for f in (_applied_scale, _radius_diameter):
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
    """What the step's own words compare between two named entries of a dump ("the Key at least twice the Fill's
    power") that the dump contradicts: ["Key's energy 400 is not at least 2 times Fill's 300"]."""
    out: list[str] = []
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
    if not _UNIVERSAL.search(str(check.get("label") or "")):
        return None
    m = _KEY_PATTERN.match(str(check.get("pattern") or ""))
    if not m:
        return None
    key = re.compile(rf'"{re.escape(m.group(1))}"\s*:')
    for k in key.finditer(text):
        end = text.find("\n", k.start())
        item = text[k.start():len(text) if end < 0 else end]
        if not rx.match(item):
            return f"{item.strip().rstrip(',')} at line {text.count(chr(10), 0, k.start()) + 1}"
    return None


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

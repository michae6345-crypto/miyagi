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


# ---------------------------------------------------------------- float noise

_LONG_DECIMAL = re.compile(r"(?<![\w.])(-?\d+\.\d{6,})(?!\d)")


def _short(m: re.Match[str]) -> str:
    v = round(float(m.group(1)), 4)
    if v == 0:
        v = 0.0  # never -0.0
    return f"{v:.1f}" if v == int(v) else repr(v)


def rounded(text: str) -> str:
    """``text`` with every long decimal (6+ places: float32 / binary noise) written at 4 places, line structure kept:
    ``90.00000250447816`` -> ``90.0``, ``119.9999999999999`` -> ``120.0``."""
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

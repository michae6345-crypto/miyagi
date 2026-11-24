"""Which catalog skills a lesson step practises. Deterministic, no model call.

Order of evidence (the first that names a skill wins):
1. the step's own tags: step.skillIds / step.skills that are catalog ids (a lesson built from the catalog may carry them);
2. the lesson's catalog metadata: lesson.grows (ids), else the catalog lesson whose goal / title is this lesson's
   (catalog.match_lesson) and its `grows`. One skill: every practice step gets it. Two: a step gets the one its words
   name (title, instructions, code, command), both when its words name neither;
3. the model-free fallback, for a lesson outside the catalog: the tracks the lesson is about (the tool it names, the
   step files' languages, its libraries) and, inside them, the skills whose keywords the step's words hit best (at
   most MAX_FALLBACK, never a skill the step's words do not name).

A "read" step (nothing to do) still gets tags but is not practice: ledger.record_pass ignores it.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import catalog

MAX_FALLBACK = 2
MAX_TEXT = 6000
STOP = frozenset("and the with a an of to in on for your you it its is are into by from as at or not".split())

# Extra words a step about the skill tends to use (the label and the id already count). Blender and CAD in full; the
# code tracks lean on their labels plus a few constructs.
EXTRA: dict[str, tuple[str, ...]] = {
    # Blender
    "bl.navigate": ("orbit", "pan", "zoom", "numpad", "front view", "top view", "frame selected", "viewport"),
    "bl.transform": ("move", "rotate", "scale", "grab", "location", "rotation", "g key", "r key", "s key"),
    "bl.edit": ("edit mode", "vertex", "vertices", "edge", "edges", "face", "faces", "tab key", "select mode"),
    "bl.extrude": ("extrude", "inset", "e key", "i key"),
    "bl.loops": ("loop cut", "bevel", "edge loop", "ctrl r", "ctrl b"),
    "bl.modifiers": ("modifier", "subdivision", "mirror modifier", "array modifier", "solidify", "bevel modifier"),
    "bl.materials": ("material", "base color", "roughness", "metallic", "shading"),
    "bl.lighting": ("light", "lamp", "sun", "area light", "point light", "camera"),
    "bl.render": ("render", "f12", "render image", "save image", "output"),
    "bla.keyframes": ("keyframe", "insert keyframe", "i key"),
    "bla.timeline": ("timeline", "frame", "frames", "playhead"),
    "bla.easing": ("interpolation", "ease", "bezier", "linear"),
    "bla.graph": ("graph editor", "f-curve", "fcurve", "handles"),
    "bla.parenting": ("parent", "child", "ctrl p", "empty"),
    "bla.dopesheet": ("dope sheet",),
    "bla.output": ("render animation", "ffmpeg", "mp4", "video"),
    "blm.principled": ("principled", "bsdf"),
    "blm.glass": ("glass", "emission", "transmission"),
    "blm.nodes": ("shader editor", "node", "nodes"),
    "blm.uv": ("uv", "unwrap", "seam"),
    "blm.textures": ("image texture", "texture"),
    "blm.world": ("hdri", "world", "environment texture"),
    "blm.three_point": ("key light", "fill light", "rim light", "three point"),
    "blm.dof": ("depth of field", "focus", "f-stop", "aperture"),
    "blm.engines": ("cycles", "eevee", "samples"),
    # CAD (FreeCAD)
    "cad.navigate": ("part design", "workbench", "body", "tree view", "freecad"),
    "cad.sketch": ("sketch", "sketcher", "polyline", "rectangle", "circle"),
    "cad.constrain": ("constraint", "constrain", "fully constrained", "dimension", "horizontal", "vertical", "coincident"),
    "cad.pad": ("pad",),
    "cad.pocket": ("pocket", "hole", "through all"),
    "cad.fillet": ("fillet", "chamfer"),
    "cad.pattern": ("pattern", "polar pattern", "linear pattern", "mirrored"),
    "cad.parametric": ("spreadsheet", "parameter", "expression", "change the size"),
    "cad.export": ("export", "stl", "3mf", "step file"),
    "cadp.clearance": ("clearance", "gap", "tolerance"),
    "cadp.walls": ("wall thickness", "thickness"),
    "cadp.overhangs": ("overhang", "45 degrees", "support"),
    "cadp.orient": ("orientation", "orient", "build plate"),
    "cadp.press": ("press fit", "interference"),
    "cadp.snap": ("snap fit", "cantilever", "clip"),
    "cadp.enclosure": ("box", "lid", "enclosure"),
    "cadp.bosses": ("boss", "screw", "standoff"),
    "cadp.slicer": ("slicer", "slice", "cura", "prusaslicer", "bambu"),
    # Fusion and Onshape
    "fus.sketch": ("sketch", "rectangle", "circle", "line"),
    "fus.constrain": ("constraint", "dimension", "fully defined"),
    "fus.extrude": ("extrude",),
    "fus.fillet": ("fillet", "chamfer"),
    "fus.shell": ("shell",),
    "fus.hole": ("hole", "counterbore", "countersink"),
    "fus.timeline": ("timeline", "edit feature"),
    "fus.export": ("export", "stl", "3mf"),
    "ons.sketch": ("sketch",),
    "ons.constrain": ("constraint", "dimension"),
    "ons.extrude": ("extrude",),
    "ons.cut": ("cut", "hole", "remove"),
    "ons.fillet": ("fillet", "chamfer"),
    "ons.mates": ("mate", "fastened", "revolute"),
    "ons.export": ("version", "export", "stl"),
    # Python (the constructs a step's code shows)
    "py.run": ("python3", "run the script", "terminal"),
    "py.variables": ("variable", "assign"),
    "py.strings": ("f-string", "string", "upper", "lower", "format"),
    "py.conditions": ("if", "elif", "else"),
    "py.loops": ("for", "while", "range"),
    "py.lists": ("list", "append"),
    "py.functions": ("def", "return", "function"),
    "py.dicts": ("dict", "dictionary", "keys", "items"),
    "py.files": ("open", "read", "readlines", "with open"),
    "py.errors": ("traceback", "error", "exception"),
}

# tracks a lesson is about: what its words / tool / files / libraries name
TRACK_WORDS: dict[str, str] = {
    "blender": r"\bblender\b|\bbpy\b", "cad": r"\bfreecad\b|\bfcstd\b|\b3d print", "fusion": r"\bfusion(?: 360)?\b",
    "onshape": r"\bonshape\b", "python": r"\bpython\b", "javascript": r"\bjavascript\b|\bnode(?:\.js)?\b",
    "typescript": r"\btypescript\b", "react": r"\breact\b", "rust": r"\brust\b|\bcargo\b", "go": r"\bgolang\b|\bgo run\b",
    "swift": r"\bswift(?:ui)?\b", "xcode": r"\bxcode\b", "sql": r"\bsql(?:ite)?\b", "git": r"\bgit\b",
    "terminal": r"\bterminal\b|\bshell\b|\bbash\b|\bzsh\b", "docker": r"\bdocker\b", "excel": r"\bexcel\b",
    "sheets": r"\bgoogle sheets\b", "figma": r"\bfigma\b", "godot": r"\bgodot\b|\bgdscript\b", "unity": r"\bunity\b",
    "arduino": r"\barduino\b", "jupyter": r"\bjupyter\b|\bnotebook\b", "numpy": r"\bnumpy\b", "pandas": r"\bpandas\b",
    "plotting": r"\bmatplotlib\b|\bplot\b", "pytorch": r"\bpytorch\b|\btorch\b", "scikit-learn": r"\bscikit|\bsklearn\b",
    "neural networks": r"\bneural net", "language models": r"\bllm\b|\blanguage model|\bclaude api\b|\bopenai\b",
    "c": r"\bin c\b|\bgcc\b|\bclang\b", "c++": r"\bc\+\+", "c#": r"\bc#|\bdotnet\b", "java": r"\bjava\b", "r": r"\brstudio\b",
    "web": r"\bhtml\b|\bcss\b", "vs code": r"\bvs ?code\b",
}
SUFFIX_TRACK = {".py": "python", ".js": "javascript", ".mjs": "javascript", ".ts": "typescript", ".tsx": "react",
                ".jsx": "react", ".rs": "rust", ".go": "go", ".swift": "swift", ".sql": "sql", ".sh": "terminal",
                ".html": "web", ".css": "web", ".c": "c", ".cpp": "c++", ".cs": "c#", ".java": "java", ".r": "r",
                ".ipynb": "jupyter", ".blend": "blender", ".fcstd": "cad", ".gd": "godot", ".ino": "arduino"}
LIBRARY_TRACK = {"numpy": "numpy", "pandas": "pandas", "torch": "pytorch", "pytorch": "pytorch", "sklearn": "scikit-learn",
                 "scikit-learn": "scikit-learn", "matplotlib": "plotting", "anthropic": "language models", "openai": "language models",
                 "bpy": "blender"}


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9#+]+", text.lower()) if w not in STOP and len(w) > 1]


@lru_cache(maxsize=2048)
def _patterns(skill_id: str) -> tuple[re.Pattern, ...]:
    sk = catalog.skill(skill_id)
    if sk is None:
        return ()
    phrases = set(EXTRA.get(skill_id, ()))
    phrases.update(w for w in _words(sk.label) if len(w) > 2)
    phrases.update(w for w in _words(skill_id.split(".", 1)[-1].replace("_", " ")) if len(w) > 2)
    return tuple(re.compile(r"(?<![a-z0-9])" + re.escape(p.lower()) + r"(?![a-z0-9])") for p in sorted(phrases))


def _score(skill_id: str, text: str) -> int:
    return sum(1 for rx in _patterns(skill_id) if rx.search(text))


def step_text(step: dict) -> str:
    parts = [step.get(k) for k in ("title", "what", "instructions", "code", "run_command", "file")]
    for h in step.get("hints") or []:
        parts.append(h.get("text") if isinstance(h, dict) else h)
    return " ".join(str(p) for p in parts if isinstance(p, str))[:MAX_TEXT].lower()


def lesson_tracks(lesson: dict | None, steps: list[dict] = ()) -> list[str]:
    """The catalog tracks a lesson is about, most specific first (a library before the language it runs on)."""
    lesson = lesson or {}
    known = catalog.get().tracks_by_id
    out: list[str] = []
    libs = lesson.get("libraries")
    for name in (libs.keys() if isinstance(libs, dict) else libs if isinstance(libs, list) else []):
        t = LIBRARY_TRACK.get(str(name).lower())
        if t and t not in out:
            out.append(t)
    words = " ".join(str(lesson.get(k) or "") for k in ("title", "goal", "asked", "tool")).lower()
    for t, rx in TRACK_WORDS.items():
        if t not in out and re.search(rx, words):
            out.append(t)
    for st in steps:
        suf = Path(str(st.get("file") or "")).suffix.lower()
        t = SUFFIX_TRACK.get(suf)
        if t and t not in out:
            out.append(t)
    return [t for t in out if t in known]


def _explicit(step: dict) -> list[str]:
    raw = step.get("skillIds") or step.get("skills") or []
    return [s for s in raw if isinstance(s, str) and catalog.skill(s)] if isinstance(raw, list) else []


def lesson_grows(lesson: dict | None) -> list[str]:
    """The catalog skills a lesson grows: lesson.grows when it carries catalog ids, else its catalog match's."""
    lesson = lesson or {}
    raw = lesson.get("grows")
    if isinstance(raw, list) and (ids := [s for s in raw if isinstance(s, str) and catalog.skill(s)]):
        return ids
    hit = catalog.match_lesson(lesson)
    return [s for s in (hit[1].get("grows") or []) if catalog.skill(s)] if hit else []


def tag_step(step: dict, lesson: dict | None = None, *, grows: list[str] | None = None,
             tracks: list[str] | None = None) -> list[str]:
    """The skill ids one step practises (may be empty). `grows` / `tracks` let tag_graph compute the lesson part once."""
    if not isinstance(step, dict):
        return []
    if ids := _explicit(step):
        return ids
    grows = lesson_grows(lesson) if grows is None else grows
    text = step_text(step)
    if len(grows) == 1:
        return list(grows)
    if grows:
        scores = {s: _score(s, text) for s in grows}
        best = max(scores.values())
        return [s for s in grows if scores[s] == best] if best > 0 else list(grows)
    tracks = lesson_tracks(lesson, [step]) if tracks is None else tracks
    cands: list[tuple[int, int, str]] = []
    known = catalog.get().tracks_by_id
    for ti, t in enumerate(tracks):
        for sk in known[t].skills:
            if (n := _score(sk.id, text)) > 0:
                cands.append((-n, ti, sk.id))
    cands.sort()
    if not cands:
        return []
    top = -cands[0][0]
    return [sid for n, _, sid in cands if -n >= max(1, top - 1)][:MAX_FALLBACK]


def tag_graph(graph: dict | None) -> dict[str, list[str]]:
    """stepId -> skill ids for every step of a lesson graph."""
    graph = graph if isinstance(graph, dict) else {}
    lesson = graph.get("lesson") if isinstance(graph.get("lesson"), dict) else {}
    steps = [s for s in graph.get("steps") or [] if isinstance(s, dict) and s.get("id")]
    grows = lesson_grows(lesson)
    tracks = [] if grows else lesson_tracks(lesson, steps)
    return {s["id"]: tag_step(s, lesson, grows=grows, tracks=tracks) for s in steps}

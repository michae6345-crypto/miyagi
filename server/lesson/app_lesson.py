"""App-based (no-code) lessons: AutoCAD, Blender, Photoshop, Tinkercad... The steps talk about the app, the checks look
at the app.

Michael, Nov 22 ("AutoCAD - Toy Car Creation for 3D Printer"): the drawer said "type along in your editor" for a lesson
done entirely in AutoCAD. A lesson whose title names a desktop or web app (server.workspace.apps.app_in_text) and has
no code (no code file, no run command) is an app lesson:

  - lesson.app = {tool, label}: additive, for the app and the coach
  - "in your editor" / "in VS Code" in a step's title or instructions reads "in AutoCAD"
  - checks look at the screen and the app, never at files: file_* / command_* / output_contains checks go (there is
    no lesson folder or terminal to read; they would gate forever), and a screen check or target with no app gets the
    app's window name ("AutoCAD" matches "AutoCAD 2025")
  - Blender is the one exception (Nov 24): a file_contains on "<name>.scene.json" stays. That file is the scene as the
    engine reads it (blender-addon/dump_scene.py, or the live miyagi bridge), written next to the learner's .blend by
    server/checks/scene_refresh.py, so a check on it grades the model itself, not a file the learner types

Code lessons are never touched, even when their title names an app ("Read Excel files with pandas").
"""
from __future__ import annotations

import re

# code-like apps that app_in_text spots in titles keep their gating checks: Arduino (.ino), Processing (.pde),
# Godot (.gd, .gdshader), OpenSCAD (.scad), shaders, HDL, Flutter, Vue / Svelte...
CODE_FILE = re.compile(r"\.(?:py|ipynb|js|mjs|cjs|ts|tsx|jsx|rs|go|java|kt|kts|c|cc|cpp|h|hpp|cs|rb|php|swift|sh|r|jl|m|"
                       r"html|css|scss|sql|toml|ya?ml|json|ino|pde|gd|gdshader|scad|lua|glsl|hlsl|shader|frag|vert|"
                       r"v|sv|vhdl?|dart|scala|vue|svelte|zig|ex|exs|hs|ml|clj|pl|ps1|bat)$", re.I)
# what an app saves (a drawing, a model, a document): a file_contains check on one doesn't make the lesson a code lesson
APP_DOC = re.compile(r"\.(?:dwg|dxf|blend|psd|ai|indd|fig|sketch|skp|f3d|fcstd|stl|obj|3mf|step|stp|xlsx?|docx?|pptx?|key|"
                     r"numbers|pages|pdf|png|jpe?g|gif|svg|mp4|mov|wav|mp3|als|logicx|band|prproj|aep|kra|xcf)$", re.I)
# the scene dump the engine writes next to a .blend (mug.blend -> mug.scene.json): app state, never code the learner types
SCENE_DUMP = re.compile(r"\.scene\.json$", re.I)
FILE_CHECKS = frozenset({"file_exists", "file_contains", "command_exit_ok", "output_contains"})
_EDITOR = re.compile(r"\b(?:in|into|inside)\s+(?:your|the)\s+(?:code\s+)?editor\b|\b(?:in|into)\s+VS\s*Code\b", re.I)
_TYPE_ALONG = re.compile(r"\btype along\b", re.I)
# a title that is about code even when it names an app ("Automate Excel with Python openpyxl"): used where there are no
# steps yet to read (builder.provisional_graph's placeholder, before preflight's style is known)
CODE_TITLE = re.compile(r"\b(?:python|javascript|typescript|java|rust|golang|vba|pandas|openpyxl|numpy|"
                        r"script(?:s|ing)?|cod(?:e|ing)|program(?:ming)?|api|sdk|macro(?:s)?)\b", re.I)


def _apps():
    from server.workspace import apps

    return apps


def work_app(graph: dict) -> str | None:
    """The app the lesson's (or its video's) title names, else None."""
    les = graph.get("lesson") or {}
    titles = [str(les.get("title") or "")] + [str(s.get("title") or "") for s in graph.get("sources") or [] if isinstance(s, dict)]
    for t in titles:
        if app := _apps().app_in_text(t):
            return app
    return None


def _code_file(f) -> bool:
    """A file the learner writes code in (app.py, settings.json), never a scene dump (mug.scene.json)."""
    f = str(f or "").strip()
    return bool(CODE_FILE.search(f)) and not SCENE_DUMP.search(f)


def has_code(graph: dict) -> bool:
    """Does any step write or run code (a code file anywhere, a run command, a file a file_contains check reads)?
    A check on a scene dump (mug.scene.json) reads the app's scene, so it is no code."""
    for st in graph.get("steps") or []:
        if not isinstance(st, dict):
            continue
        if str(st.get("run_command") or "").strip():
            return True
        files = [st.get("file")] + [x.get("file") for x in (st.get("checks") or []) + (st.get("targets") or [])
                                    + (st.get("precision_checks") or []) if isinstance(x, dict)]
        if any(_code_file(f) for f in files):
            return True
        # a file whose text a check reads is one the learner edits (notes.txt, a G-code file...): never stripped
        for c in (st.get("checks") or []) + (st.get("precision_checks") or []):
            f = str((c.get("file") or st.get("file") or "") if isinstance(c, dict) else "").strip()
            if f and c.get("type") == "file_contains" and not APP_DOC.search(f) and not SCENE_DUMP.search(f):
                return True
    return False


def app_words(text: str, label: str) -> str:
    """'Type along in your editor' -> 'Follow along in AutoCAD'."""
    out = _EDITOR.sub(lambda m: ("In " if m.group(0)[0].isupper() else "in ") + label, text or "")
    return _TYPE_ALONG.sub(lambda m: "Follow along" if m.group(0)[0].isupper() else "follow along", out)


def _kept(c, app: str) -> bool:
    """Does an app lesson keep this check? Everything but file / command / output checks, and in Blender a
    file_contains on the scene dump too (the engine keeps mug.scene.json fresh, see the module doc)."""
    if not isinstance(c, dict) or c.get("type") not in FILE_CHECKS:
        return True
    return app == "blender" and c.get("type") == "file_contains" and bool(SCENE_DUMP.search(str(c.get("file") or "").strip()))


def adapt(graph: dict, *, force: bool = False) -> dict:
    """In place for an app lesson (see the module doc); any other lesson is returned untouched. force: the lesson was
    already judged an app lesson (its step 1 went out as one, builder first-step path): its code check is not redone."""
    app = work_app(graph)
    if not app or (has_code(graph) and not force):
        return graph
    apps = _apps()
    label = apps.label(app)
    window = (apps.process_names(app) or [label])[0]
    web = app in apps.WEB_APPS
    graph.setdefault("lesson", {})["app"] = {"tool": app, "label": label}
    for st in graph.get("steps") or []:
        if not isinstance(st, dict):
            continue
        for k in ("title", "instructions"):
            if isinstance(st.get(k), str):
                st[k] = app_words(st[k], label)
        for key in ("checks", "precision_checks"):
            if isinstance(st.get(key), list):
                st[key] = [c for c in st[key] if _kept(c, app)]
        if web:
            continue  # a web app runs in whichever browser the learner has: no window name to pin
        for x in (st.get("checks") or []) + (st.get("targets") or []):
            if isinstance(x, dict) and str(x.get("type") or "screen").startswith("screen") and not x.get("app"):
                x["app"] = window
    return graph


# How to grade a Blender step from the scene (Nov 24). The engine keeps "<name>.scene.json" next to the learner's
# "<name>.blend" (server/checks/scene_refresh.py: the live miyagi bridge, else a headless Blender dump after a save),
# written by blender-addon/dump_scene.py as JSON with indent 1 and a fixed key order (format "dump_scene.py 1"). It
# starts with a newline: it follows STACK_GUIDE in the step prompt (claude.STEP_HEAD).
SCENE_GUIDE = r"""
Blender lessons: grade the model itself from its scene dump. The engine writes "<name>.scene.json" next to the
learner's "<name>.blend" whenever the scene changes or is saved (JSON, indent 1, keys always in this order):
  scene {name, unit_system, frame_start, frame_end, fps, render {engine, resolution, file_format, filepath, ffmpeg},
  fps_base, frame_current, camera}; objects[] {name, type, location, rotation_deg, scale, dimensions, parent,
  hide_viewport, mesh {verts, edges, faces, smooth, islands, seams, uv_layers}, modifiers[] {name, type, then levels /
  render_levels / width / segments / thickness / count by type, show_viewport, show_render}, materials,
  material_slots, constraints, animation {action, fcurves[] {data_path, index, keyframes, interpolation}}};
  materials[] {name, users, principled {base_color, roughness, metallic, ior, transmission_weight, emission_color,
  emission_strength}, use_nodes, nodes[] {name, type, inputs}, links[] {from, from_socket, to, to_socket}};
  lights[] {name, type, energy}; camera {name, lens, in_view}; cameras; world; images.
  rotation_deg is in degrees; fcurve keyframes are [frame, value] pairs with raw values (radians for
  rotation_euler); floats carry up to 6 decimals; colours are [r, g, b, a].
- A step that changes the scene: set the step's "file" to the learner's .blend (e.g. "donut.blend") and add one
  file_contains check per scene fact on "<stem of that .blend>.scene.json" (e.g. "donut.scene.json").
- Short regexes with \s* that pass for ANY learner's names: "type":\s*"SUBSURF", "levels":\s*2\b,
  "smooth":\s*true, "type":\s*"SOLIDIFY", "frame_end":\s*96\b, "to_socket":\s*"Base Color". Names only the demo
  uses (its object and material names, exact colours) go in precision_checks.
- Render engine: match BLENDER_EEVEE\w* or CYCLES, never a longer engine name.
- A UI-only step (a menu, panel or pie opened, nothing in the scene changes) keeps screen_contains with app "Blender"
  on the menu or panel text."""


def scene_guide(title: str) -> str:
    """The Blender check-writing block for the step prompt when the lesson title names Blender, else ""."""
    return SCENE_GUIDE if work_app({"lesson": {"title": str(title or "")}}) == "blender" else ""


def _app_phrase(names: list[str]) -> re.Pattern:
    """"in AutoCAD" / "open Autodesk AutoCAD 2025" for any of the app's names (the verb or preposition is kept)."""
    alts = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    return re.compile(rf"\b(in|into|inside|within|open|launch|start|switch to)\s+(?:Autodesk\s+|Adobe\s+|Microsoft\s+)?"
                      rf"(?:{alts})(?:\s+(?:LT|20\d\d))?\b", re.I)


def repin(graph: dict, tool: str, window: str | None, label: str | None) -> bool:
    """The learner works in another app than the one the lesson names (Nov 22: FreeCAD for AutoCAD), or said "I have
    it" while this Mac shows no such app (a VM, a school machine). Screen checks and targets that adapt (or the model)
    pinned to the lesson's app ("AutoCAD") would wait forever, so they move to `window` ("FreeCAD"), or lose the pin
    when there is no window name to give (a web alternative, an unfound "I have it"): the judge and "Can I move on?"
    decide. With `label`, step copy "in AutoCAD" reads "in FreeCAD". In place, idempotent; -> True when anything
    changed. Code lessons are never touched."""
    if not tool or has_code(graph):
        return False
    apps = _apps()
    names = [n for n in dict.fromkeys([apps.label(tool), *apps.process_names(tool)]) if len(n) >= 3]
    if not names:
        return False
    low = [n.lower() for n in names]
    phrase = _app_phrase(names) if label else None
    changed = False
    for st in graph.get("steps") or []:
        if not isinstance(st, dict):
            continue
        for x in (st.get("checks") or []) + (st.get("precision_checks") or []) + (st.get("targets") or []):
            a = x.get("app") if isinstance(x, dict) else None
            if not isinstance(a, str) or not any(n in a.lower() for n in low):
                continue
            if window:
                x["app"] = window
            else:
                x.pop("app")
            changed = True
        if phrase is not None:
            for k in ("title", "instructions"):
                if isinstance(st.get(k), str) and (new := phrase.sub(lambda m: f"{m.group(1)} {label}", st[k])) != st[k]:
                    st[k] = new
                    changed = True
    les = graph.get("lesson") or {}
    if isinstance(les.get("app"), dict) and les["app"].get("tool") == tool and label and les["app"].get("using") != label:
        les["app"]["using"] = label  # additive: the coach sees which app the learner really uses
        changed = True
    return changed


def alternative_window(alt_tool: str) -> str | None:
    """The window name a free desktop alternative shows ("FreeCAD", "Blender"); None for a web app or an app whose
    window name we don't know (its checks then go unpinned)."""
    apps = _apps()
    if alt_tool in apps.FREE_APPS:
        return (apps.process_names(alt_tool) or [None])[0]
    from server.workspace import setup as S

    cat = S.CATALOG.get(alt_tool) or {}
    return cat.get("app") if cat.get("kind") == "app" else None

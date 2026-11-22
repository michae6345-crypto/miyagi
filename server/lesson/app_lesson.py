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

Code lessons are never touched, even when their title names an app ("Read Excel files with pandas").
"""
from __future__ import annotations

import re

CODE_FILE = re.compile(r"\.(?:py|ipynb|js|mjs|cjs|ts|tsx|jsx|rs|go|java|kt|c|cc|cpp|h|hpp|cs|rb|php|swift|sh|r|jl|m|"
                       r"html|css|scss|sql|toml|ya?ml|json)$", re.I)
FILE_CHECKS = frozenset({"file_exists", "file_contains", "command_exit_ok", "output_contains"})
_EDITOR = re.compile(r"\b(?:in|into|inside)\s+(?:your|the)\s+(?:code\s+)?editor\b|\b(?:in|into)\s+VS\s*Code\b", re.I)
_TYPE_ALONG = re.compile(r"\btype along\b", re.I)


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


def has_code(graph: dict) -> bool:
    """Does any step write or run code (a code file anywhere, a run command)?"""
    for st in graph.get("steps") or []:
        if not isinstance(st, dict):
            continue
        if str(st.get("run_command") or "").strip():
            return True
        files = [st.get("file")] + [x.get("file") for x in (st.get("checks") or []) + (st.get("targets") or [])
                                    + (st.get("precision_checks") or []) if isinstance(x, dict)]
        if any(CODE_FILE.search(str(f or "")) for f in files):
            return True
    return False


def app_words(text: str, label: str) -> str:
    """'Type along in your editor' -> 'Follow along in AutoCAD'."""
    out = _EDITOR.sub(lambda m: ("In " if m.group(0)[0].isupper() else "in ") + label, text or "")
    return _TYPE_ALONG.sub(lambda m: "Follow along" if m.group(0)[0].isupper() else "follow along", out)


def adapt(graph: dict) -> dict:
    """In place for an app lesson (see the module doc); any other lesson is returned untouched."""
    app = work_app(graph)
    if not app or has_code(graph):
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
                st[key] = [c for c in st[key] if not (isinstance(c, dict) and c.get("type") in FILE_CHECKS)]
        if web:
            continue  # a web app runs in whichever browser the learner has: no window name to pin
        for x in (st.get("checks") or []) + (st.get("targets") or []):
            if isinstance(x, dict) and str(x.get("type") or "screen").startswith("screen") and not x.get("app"):
                x["app"] = window
    return graph

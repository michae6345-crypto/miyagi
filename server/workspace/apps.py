"""Desktop apps a lesson needs: which ones miyagi may install, which ones it must never install, and finding them.

Michael's AutoCAD lesson (Nov 22): the setup card said "Missing: autocad. Install now?" with only Skip. AutoCAD is
commercial software: no package manager installs it, and miyagi must never pretend it can. Every tool a lesson needs
now gets a setup kind:

  package       pip / npm / Homebrew formula (runtimes, CLIs, Python packages): the existing allowlisted Install
  free_app      a free desktop app with an allowlisted Homebrew cask (Blender, FreeCAD, GIMP...): Install, with a confirm
  licensed_app  commercial or licensed (AutoCAD, Fusion, Photoshop, Excel, MATLAB...): never installed. The learner
                gets "I have it", "Get it" (the vendor's own download / trial page) and a free alternative when one exists
  web_app       a website (Tinkercad, Botpress...): Open

Detection is read-only and real: /Applications and ~/Applications (also one folder down, where Autodesk and Adobe put
their apps: /Applications/Autodesk/AutoCAD 2025/AutoCAD 2025.app), then Spotlight by bundle id prefix
(com.autodesk.AutoCAD*), then the version from Info.plist. The session re-checks when the learner says "I have it" and
when an app comes to the front.

What the learner said about an app ("I have it", "use FreeCAD instead") is kept per Mac in
<lessons root>/.miyagi-state/mac-apps.json, so the next lesson that needs AutoCAD doesn't ask again, and a one-line
summary of it goes into the coach's context (context_line).
"""

from __future__ import annotations

import fnmatch
import json
import logging
import re
import sys
import time
from collections.abc import Callable
from pathlib import Path

from . import paths

log = logging.getLogger("server.workspace")

Runner = Callable[[list[str]], tuple[int, str]]

SETUP_KINDS = ("package", "free_app", "licensed_app", "web_app")
ITEM_ACTIONS = ("install", "have_it", "get_it", "alternative", "skip")

# --------------------------------------------------------------------------- free apps (allowlisted Homebrew casks)
# Each name is a real Homebrew cask. A cask a model suggests installs only when it is on this list (or is the setup
# catalog's own): a GUI app from an unknown cask could be anything, or a paid app with a cask (microsoft-excel).
FREE_APPS: dict[str, dict] = {
    "freecad": {"label": "FreeCAD", "bundle": "org.freecad.FreeCAD", "app": "FreeCAD", "cask": "freecad",
                "url": "https://www.freecad.org/downloads.php"},
    "gimp": {"label": "GIMP", "bundle": "org.gimp.gimp-2.10", "app": "GIMP", "cask": "gimp",
             "url": "https://www.gimp.org/downloads/", "globs": ["GIMP*.app"]},
    "inkscape": {"label": "Inkscape", "bundle": "org.inkscape.Inkscape", "app": "Inkscape", "cask": "inkscape",
                 "url": "https://inkscape.org/release/"},
    "krita": {"label": "Krita", "bundle": "org.kde.krita", "app": "krita", "cask": "krita", "url": "https://krita.org/en/download/"},
    "audacity": {"label": "Audacity", "bundle": "org.audacityteam.audacity", "app": "Audacity", "cask": "audacity",
                 "url": "https://www.audacityteam.org/download/"},
    "shotcut": {"label": "Shotcut", "bundle": "org.shotcut.Shotcut", "app": "Shotcut", "cask": "shotcut",
                "url": "https://shotcut.org/download/"},
    "libreoffice": {"label": "LibreOffice", "bundle": "org.libreoffice.script", "app": "LibreOffice", "cask": "libreoffice",
                    "url": "https://www.libreoffice.org/download/download-libreoffice/"},
    "obs": {"label": "OBS Studio", "bundle": "com.obsproject.obs-studio", "app": "OBS", "cask": "obs",
            "url": "https://obsproject.com/download"},
    "kicad": {"label": "KiCad", "bundle": "org.kicad.kicad", "app": "KiCad", "cask": "kicad", "url": "https://www.kicad.org/download/macos/",
              "globs": ["KiCad/KiCad.app"]},
    "openscad": {"label": "OpenSCAD", "bundle": "org.openscad.OpenSCAD", "app": "OpenSCAD", "cask": "openscad",
                 "url": "https://openscad.org/downloads.html"},
    "ultimaker-cura": {"label": "UltiMaker Cura", "bundle": "nl.ultimaker.cura", "app": "UltiMaker Cura", "cask": "ultimaker-cura",
                       "url": "https://ultimaker.com/software/ultimaker-cura/", "globs": ["UltiMaker Cura*.app", "Ultimaker Cura*.app"]},
    "prusaslicer": {"label": "PrusaSlicer", "bundle": "com.prusa3d.slic3r", "app": "PrusaSlicer", "cask": "prusaslicer",
                    "url": "https://www.prusa3d.com/page/prusaslicer_424/"},
    "godot": {"label": "Godot", "bundle": "org.godotengine.godot", "app": "Godot", "cask": "godot", "url": "https://godotengine.org/download/macos/"},
    "arduino-ide": {"label": "Arduino IDE", "bundle": "cc.arduino.IDE2", "app": "Arduino IDE", "cask": "arduino-ide",
                    "url": "https://www.arduino.cc/en/software"},
    "musescore": {"label": "MuseScore", "bundle": "org.musescore.MuseScore", "app": "MuseScore 4", "cask": "musescore",
                  "url": "https://musescore.org/en/download", "globs": ["MuseScore*.app"]},
    "darktable": {"label": "darktable", "bundle": "org.darktable", "app": "darktable", "cask": "darktable",
                  "url": "https://www.darktable.org/install/"},
    "scribus": {"label": "Scribus", "bundle": "net.scribus", "app": "Scribus", "cask": "scribus", "url": "https://www.scribus.net/downloads/"},
}

# Websites offered as a free alternative (nothing to install).
WEB_APPS: dict[str, dict] = {
    "tinkercad": {"label": "Tinkercad", "url": "https://www.tinkercad.com"},
    "onshape": {"label": "Onshape", "url": "https://www.onshape.com/en/education/"},
    "photopea": {"label": "Photopea", "url": "https://www.photopea.com"},
}

# --------------------------------------------------------------------------- licensed apps (never installed)
# vendor_url: the vendor's own download / free-trial / education page (opened only through the safe open helper,
# which checks the host against VENDOR_HOSTS). alternative: a tool id in FREE_APPS / WEB_APPS / CATALOG.
# bundles are prefixes (AutoCAD's id carries its year: com.autodesk.AutoCAD2025). mac False: no macOS version.
_ALT = "alternative"
LICENSED: dict[str, dict] = {
    "autocad": {"label": "AutoCAD", "vendor": "Autodesk", "bundles": ["com.autodesk.AutoCAD"],
                "globs": ["Autodesk/AutoCAD*/AutoCAD*.app", "AutoCAD*.app"],
                "vendor_url": "https://www.autodesk.com/products/autocad/free-trial", _ALT: "freecad",
                "aliases": ["autocad lt", "autodesk autocad", "acad"]},
    "fusion": {"label": "Autodesk Fusion", "vendor": "Autodesk", "bundles": ["com.autodesk.fusion360", "com.autodesk.Fusion"],
               "globs": ["Autodesk Fusion*.app", "Fusion 360*.app"],
               "vendor_url": "https://www.autodesk.com/products/fusion-360/personal", _ALT: "freecad",
               "aliases": ["fusion 360", "fusion360", "autodesk fusion 360", "autodesk fusion"]},
    "maya": {"label": "Maya", "vendor": "Autodesk", "bundles": ["com.autodesk.Maya"], "globs": ["Autodesk/maya*/Maya.app"],
             "vendor_url": "https://www.autodesk.com/products/maya/free-trial", _ALT: "blender", "aliases": ["autodesk maya"]},
    "3ds-max": {"label": "3ds Max", "vendor": "Autodesk", "mac": False, "vendor_url": "https://www.autodesk.com/products/3ds-max/free-trial",
                _ALT: "blender", "aliases": ["3dsmax", "3ds max", "autodesk 3ds max"]},
    "revit": {"label": "Revit", "vendor": "Autodesk", "mac": False, "vendor_url": "https://www.autodesk.com/products/revit/free-trial",
              _ALT: "freecad", "aliases": ["autodesk revit"]},
    "inventor": {"label": "Inventor", "vendor": "Autodesk", "mac": False,
                 "vendor_url": "https://www.autodesk.com/products/inventor/free-trial", _ALT: "freecad", "aliases": ["autodesk inventor"]},
    "solidworks": {"label": "SOLIDWORKS", "vendor": "Dassault Systèmes", "mac": False,
                   "vendor_url": "https://www.solidworks.com/product/solidworks-3d-cad", _ALT: "onshape", "aliases": ["solid works"]},
    "photoshop": {"label": "Photoshop", "vendor": "Adobe", "bundles": ["com.adobe.Photoshop"],
                  "globs": ["Adobe Photoshop*/Adobe Photoshop*.app"],
                  "vendor_url": "https://www.adobe.com/products/photoshop/free-trial-download.html", _ALT: "gimp",
                  "aliases": ["adobe photoshop"]},
    "illustrator": {"label": "Illustrator", "vendor": "Adobe", "bundles": ["com.adobe.illustrator"],
                    "globs": ["Adobe Illustrator*/Adobe Illustrator*.app"],
                    "vendor_url": "https://www.adobe.com/products/illustrator/free-trial-download.html", _ALT: "inkscape",
                    "aliases": ["adobe illustrator"]},
    "premiere-pro": {"label": "Premiere Pro", "vendor": "Adobe", "bundles": ["com.adobe.PremierePro"],
                     "globs": ["Adobe Premiere Pro*/Adobe Premiere Pro*.app"],
                     "vendor_url": "https://www.adobe.com/products/premiere/free-trial-download.html", _ALT: "shotcut",
                     "aliases": ["premiere", "adobe premiere", "adobe premiere pro"]},
    "after-effects": {"label": "After Effects", "vendor": "Adobe", "bundles": ["com.adobe.AfterEffects"],
                      "globs": ["Adobe After Effects*/Adobe After Effects*.app"],
                      "vendor_url": "https://www.adobe.com/products/aftereffects/free-trial-download.html", _ALT: "blender",
                      "aliases": ["adobe after effects", "aftereffects"]},
    "lightroom": {"label": "Lightroom", "vendor": "Adobe", "bundles": ["com.adobe.LightroomClassic", "com.adobe.mas.lightroomCC"],
                  "globs": ["Adobe Lightroom*/Adobe Lightroom*.app", "Adobe Lightroom*.app"],
                  "vendor_url": "https://www.adobe.com/products/photoshop-lightroom/free-trial-download.html", _ALT: "darktable",
                  "aliases": ["adobe lightroom", "lightroom classic"]},
    "indesign": {"label": "InDesign", "vendor": "Adobe", "bundles": ["com.adobe.InDesign"], "globs": ["Adobe InDesign*/Adobe InDesign*.app"],
                 "vendor_url": "https://www.adobe.com/products/indesign/free-trial-download.html", _ALT: "scribus",
                 "aliases": ["adobe indesign"]},
    "excel": {"label": "Microsoft Excel", "vendor": "Microsoft", "bundles": ["com.microsoft.Excel"], "app": "Microsoft Excel",
              "vendor_url": "https://www.microsoft.com/microsoft-365/excel", _ALT: "google-sheets",
              "aliases": ["microsoft excel", "ms excel", "excel 365"]},
    "word": {"label": "Microsoft Word", "vendor": "Microsoft", "bundles": ["com.microsoft.Word"], "app": "Microsoft Word",
             "vendor_url": "https://www.microsoft.com/microsoft-365/word", _ALT: "libreoffice", "aliases": ["microsoft word", "ms word"]},
    "powerpoint": {"label": "Microsoft PowerPoint", "vendor": "Microsoft", "bundles": ["com.microsoft.Powerpoint"],
                   "app": "Microsoft PowerPoint", "vendor_url": "https://www.microsoft.com/microsoft-365/powerpoint",
                   _ALT: "libreoffice", "aliases": ["microsoft powerpoint", "ms powerpoint"]},
    "matlab": {"label": "MATLAB", "vendor": "MathWorks", "bundles": ["com.mathworks.matlab"], "globs": ["MATLAB_R*.app", "MATLAB*.app"],
               "vendor_url": "https://www.mathworks.com/products/matlab.html", _ALT: "octave", "aliases": ["mathworks matlab"]},
    "sketchup": {"label": "SketchUp", "vendor": "Trimble", "bundles": ["com.sketchup.SketchUp"], "globs": ["SketchUp*/SketchUp.app"],
                 "vendor_url": "https://www.sketchup.com/try-sketchup", _ALT: "freecad", "aliases": ["sketchup pro"]},
    "rhino": {"label": "Rhino", "vendor": "McNeel", "bundles": ["com.mcneel.rhinoceros"], "globs": ["Rhino*.app", "Rhinoceros*.app"],
              "vendor_url": "https://www.rhino3d.com/download/", _ALT: "freecad", "aliases": ["rhinoceros", "rhino3d", "rhino 3d"]},
    "cinema-4d": {"label": "Cinema 4D", "vendor": "Maxon", "bundles": ["net.maxon.cinema4d"], "globs": ["Maxon Cinema 4D*/Cinema 4D.app"],
                  "vendor_url": "https://www.maxon.net/en/try", _ALT: "blender", "aliases": ["cinema4d", "c4d", "maxon cinema 4d"]},
    "final-cut-pro": {"label": "Final Cut Pro", "vendor": "Apple", "bundles": ["com.apple.FinalCut"], "app": "Final Cut Pro",
                      "vendor_url": "https://apps.apple.com/us/app/final-cut-pro/id424389933", _ALT: "shotcut",
                      "aliases": ["final cut", "fcp", "fcpx", "final cut pro x"]},
    "logic-pro": {"label": "Logic Pro", "vendor": "Apple", "bundles": ["com.apple.logic10"], "app": "Logic Pro",
                  "vendor_url": "https://apps.apple.com/us/app/logic-pro/id634148309", _ALT: "audacity",
                  "aliases": ["logic", "logic pro x"]},
    "ableton-live": {"label": "Ableton Live", "vendor": "Ableton", "bundles": ["com.ableton.live"], "globs": ["Ableton Live*.app"],
                     "vendor_url": "https://www.ableton.com/en/trial/", _ALT: "audacity", "aliases": ["ableton", "ableton live 12"]},
    "fl-studio": {"label": "FL Studio", "vendor": "Image-Line", "bundles": ["com.image-line.flstudio"], "globs": ["FL Studio*.app"],
                  "vendor_url": "https://www.image-line.com/fl-studio-download/", _ALT: "audacity", "aliases": ["fruity loops", "fl studio 21"]},
}

# Free alternatives that are CATALOG entries elsewhere (setup.CATALOG): their label and page, for the card.
_OTHER_ALTS = {"blender": {"label": "Blender", "url": "https://www.blender.org/download/"},
               "google-sheets": {"label": "Google Sheets", "url": "https://sheets.google.com"},
               "octave": {"label": "GNU Octave", "url": "https://octave.org/download"}}

# Hosts "Get it" and "Free alternative" may open. Everything else stays text (server.safety.browser_url_allowed).
VENDOR_HOSTS = frozenset({"autodesk.com", "adobe.com", "microsoft.com", "mathworks.com", "apps.apple.com", "apple.com",
                          "solidworks.com", "sketchup.com", "rhino3d.com", "maxon.net", "ableton.com", "image-line.com"})


def _host(url: str) -> str:
    m = re.match(r"https://(?:www\.)?([A-Za-z0-9.-]+)", url or "")
    return m.group(1).lower() if m else ""


def link_hosts() -> frozenset[str]:
    """Every host this module links to (vendor pages and free alternatives' pages)."""
    urls = [e["vendor_url"] for e in LICENSED.values()] + [e["url"] for e in FREE_APPS.values()]
    urls += [e["url"] for e in WEB_APPS.values()] + [e["url"] for e in _OTHER_ALTS.values()]
    return frozenset(h for h in (_host(u) for u in urls) if h) | VENDOR_HOSTS


# --------------------------------------------------------------------------- names

_YEAR = re.compile(r"\s+r?(?:19|20)\d\d[ab]?\b|\s+v?\d+(?:\.\d+)*$|\s+(?:cc|lt|pro\s+x)$")
_ALIASES: dict[str, str] = {}
for _tid, _e in LICENSED.items():
    for _n in [_tid, _e["label"], *_e.get("aliases", [])]:
        _ALIASES[re.sub(r"[\s_-]+", " ", _n.lower()).strip()] = _tid
for _tid, _e in {**FREE_APPS, **WEB_APPS}.items():
    for _n in (_tid, _e["label"]):
        _ALIASES.setdefault(re.sub(r"[\s_-]+", " ", _n.lower()).strip(), _tid)
_ALIASES.update({"gimp 2": "gimp", "obs studio": "obs", "cura": "ultimaker-cura", "ultimaker cura": "ultimaker-cura",
                 "musescore 4": "musescore", "arduino": "arduino-ide", "libre office": "libreoffice",
                 # the setup catalog's own desktop apps (server.workspace.setup.CATALOG), for app_in_text
                 "blender": "blender", "figma": "figma", "unity hub": "unity"})


def canonical(name: str, kind: str | None = None) -> str | None:
    """A tool id from this module for a model's or a title's name ("AutoCAD 2025", "Autodesk Fusion 360", "Adobe
    Photoshop CC"), else None. A bare AMBIGUOUS name ("rhino": the Mozilla JS engine too, "word", "logic", "maya") is
    an app only when the caller says kind "app"; with the vendor ("Microsoft Word") it always is."""
    t = re.sub(r"[\s_-]+", " ", (name or "").strip().lower())
    if not t:
        return None
    bare = _YEAR.sub("", t).strip()
    for cand in (t, bare, re.sub(r"^(autodesk|adobe|microsoft|ms|apple|maxon)\s+", "", bare).strip()):
        if cand in _ALIASES:
            if cand in AMBIGUOUS and cand in (t, bare) and kind != "app":
                continue
            return _ALIASES[cand]
    return None


def licensed(tool: str) -> dict | None:
    return LICENSED.get(tool or "")


def alternative(tool: str) -> dict | None:
    """{tool, name, url, installable} for a licensed app's free alternative, else None."""
    e = LICENSED.get(tool or "")
    alt = (e or {}).get(_ALT)
    if not alt:
        return None
    src = FREE_APPS.get(alt) or WEB_APPS.get(alt) or _OTHER_ALTS.get(alt)
    if not src:
        return None
    return {"tool": alt, "name": src["label"], "url": src["url"], "installable": bool(src.get("cask")) or alt == "blender"}


# Names that are ordinary words too ("nuclear fusion", "an inventor", "logic"): never matched alone in a title.
AMBIGUOUS = frozenset({"word", "logic", "fusion", "maya", "rhino", "inventor", "premiere", "krita", "obs", "c4d", "fcp", "acad"})


def app_in_text(text: str) -> str | None:
    """The licensed or free desktop app a title names ("AutoCAD - Toy Car Creation for 3D Printer" -> "autocad"), else
    None. Whole words only, longest name first (so "AutoCAD LT" wins over "AutoCAD")."""
    low = " " + re.sub(r"[^a-z0-9+]+", " ", (text or "").lower()) + " "
    names = sorted(_ALIASES, key=len, reverse=True)
    for n in names:
        if n in AMBIGUOUS or len(n) < 4:
            continue  # the full "microsoft word" / "autodesk fusion" still counts
        if f" {re.sub(r'[^a-z0-9+]+', ' ', n)} " in low:
            return _ALIASES[n]
    return None


_CATALOG_LABELS = {"blender": "Blender", "figma": "Figma", "unity": "Unity Hub"}


def label(tool: str) -> str:
    e = LICENSED.get(tool) or FREE_APPS.get(tool) or WEB_APPS.get(tool) or _OTHER_ALTS.get(tool) or {}
    return e.get("label") or _CATALOG_LABELS.get(tool) or tool


def process_names(tool: str, item: dict | None = None) -> list[str]:
    """What the app's windows are called in the window list (a frontmost check / a screen check's `app`): "AutoCAD"
    matches "AutoCAD 2025"."""
    e = LICENSED.get(tool) or FREE_APPS.get(tool) or {}
    names = [e.get("app") or "", e.get("label") or "", (item or {}).get("label") or ""]
    out: list[str] = []
    for n in names:
        n = re.sub(r"^(Autodesk|Adobe|Microsoft)\s+", "", n).strip()
        if n and n.lower() not in (x.lower() for x in out):
            out.append(n)
    return out


# --------------------------------------------------------------------------- classification

def classify(item: dict) -> str:
    """package | free_app | licensed_app | web_app for a requirements() item."""
    tool, kind = item.get("tool") or "", item.get("kind") or ""
    if tool in LICENSED or item.get("licensed"):
        return "licensed_app"
    if kind == "web_app" or tool in WEB_APPS:
        return "web_app"
    if kind in ("app", "editor") or tool in FREE_APPS:
        return "free_app"
    return "package"


def item_actions(item: dict) -> list[str]:
    """The buttons one setup row offers (contract SetupItem.actions). An app that's there needs none."""
    sk = classify(item)
    method = (item.get("install") or {}).get("method")
    if item.get("ok") or item.get("haveIt") or item.get("using"):
        return []
    if sk == "licensed_app":
        acts = ["have_it", "get_it"] + (["alternative"] if alternative(item.get("tool", "")) else [])
        return acts + ["skip"]
    if sk == "web_app":
        return []
    acts = ["install"] if method in ("brew", "brew_cask", "pip") else (["get_it"] if method == "download" else [])
    if sk == "free_app":
        acts = acts + ["have_it"]
    return acts + ["skip"]


# --------------------------------------------------------------------------- detection (read-only)

APP_ROOTS: list[Path] | None = None  # tests point this at a temp folder; None = /Applications + ~/Applications


def roots() -> list[Path]:
    return list(APP_ROOTS) if APP_ROOTS is not None else [Path("/Applications"), Path.home() / "Applications"]


def _glob(root: Path, pattern: str) -> list[Path]:
    """`pattern` under `root`, at most one folder down ("Autodesk/AutoCAD*/AutoCAD*.app"), never a deep walk."""
    parts = pattern.split("/")
    level = [root]
    for part in parts:
        nxt: list[Path] = []
        for d in level:
            try:
                kids = sorted(d.iterdir())
            except OSError:
                continue
            nxt += [k for k in kids if fnmatch.fnmatch(k.name.lower(), part.lower())]
        level = nxt[:20]
    return [p for p in level if p.suffix == ".app"]


def _version(app: Path, run: Runner) -> str:
    plist = app / "Contents" / "Info.plist"
    try:
        import plistlib

        with plist.open("rb") as f:
            v = str(plistlib.load(f).get("CFBundleShortVersionString") or "")
            m = re.search(r"\d+(?:\.\d+){0,3}", v)
            if m:
                return m.group(0)
    except Exception:  # noqa: BLE001 - a binary / missing plist: ask `defaults`
        pass
    code, out = run(["defaults", "read", str(app / "Contents" / "Info"), "CFBundleShortVersionString"])
    m = re.search(r"\d+(?:\.\d+){0,3}", out or "") if code == 0 else None
    return m.group(0) if m else ""


def detect(tool: str, run: Runner, *, extra: dict | None = None) -> dict:
    """{installed, where, version} for an app in LICENSED / FREE_APPS (or `extra`: a CATALOG entry). Read-only:
    folder listings, one Spotlight query per bundle id prefix, Info.plist."""
    e = {**(extra or {}), **(LICENSED.get(tool) or FREE_APPS.get(tool) or {})}
    if e.get("mac") is False:
        return {"installed": False, "where": "", "version": "", "noMac": True}
    names = [n for n in (e.get("app"), e.get("label")) if n]
    pats = [f"{n}.app" for n in names] + list(e.get("globs") or [])
    for root in roots():
        for pat in pats:
            hits = _glob(root, pat)
            if hits:
                app = hits[-1]  # the newest year sorts last (AutoCAD 2025 after AutoCAD 2024)
                return {"installed": True, "where": str(app), "version": _version(app, run)}
    bundles = list(e.get("bundles") or ([e["bundle"]] if e.get("bundle") else []))
    if sys.platform == "darwin" or APP_ROOTS is not None:
        for bid in bundles:
            if not re.fullmatch(r"[A-Za-z0-9.\-]+", bid):
                continue
            code, out = run(["mdfind", f"kMDItemCFBundleIdentifier == '{bid}*'"])
            first = next((ln.strip() for ln in (out or "").splitlines() if ln.strip().endswith(".app")), None) if code == 0 else None
            if first:
                return {"installed": True, "where": first, "version": _version(Path(first), run)}
    return {"installed": False, "where": "", "version": ""}


def matches_front(item: dict, front: str) -> bool:
    """Is the frontmost app (a window owner name, "AutoCAD 2025") this row's app?"""
    f = (front or "").strip().lower()
    return bool(f) and any(n.lower() in f for n in process_names(item.get("tool", ""), item) if len(n) >= 3)


# --------------------------------------------------------------------------- what this Mac has (kept between lessons)

def _memory_file() -> Path:
    return paths.lessons_root() / ".miyagi-state" / "mac-apps.json"


def recall() -> dict[str, dict]:
    try:
        data = json.loads(_memory_file().read_text(encoding="utf-8"))
        return {str(k): v for k, v in data.items() if isinstance(v, dict)} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def remember(tool: str, **facts) -> None:
    """Keep what we learned about `tool` on this Mac: installed / version / where from a scan, haveIt (the learner
    said so), choice ("alternative:<tool>"). Never raises: a memory, not a requirement."""
    if not tool or not re.fullmatch(r"[a-z0-9][a-z0-9._+@\-]{0,40}", tool):
        return
    try:
        f = _memory_file()
        data = recall()
        now = int(time.time())
        row = {**data.get(tool, {}), **{k: v for k, v in facts.items() if v is not None}, "checkedAt": now}
        if facts.get("haveIt"):
            row["haveItAt"] = now  # "I have it" lasts HAVE_IT_DAYS (have_it_fresh), so a mistaken press undoes itself
        data[tool] = row
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(f)
    except OSError as e:
        log.info("mac-apps memory not saved: %s", e)


HAVE_IT_DAYS = 14


def have_it_fresh(row: dict, now: float | None = None) -> bool:
    """Does an "I have it" from an earlier lesson still stand? It lasts HAVE_IT_DAYS from the press: a mistaken press
    (or an app since removed) stops hiding the row, and the card asks again; a learner on a VM just presses it again.
    A row kept before haveItAt existed counts as stale (asked once more)."""
    if not row.get("haveIt"):
        return False
    try:
        at = float(row.get("haveItAt") or 0)
    except (TypeError, ValueError):
        return False
    return at > 0 and ((now if now is not None else time.time()) - at) < HAVE_IT_DAYS * 86400


def remember_scan(items: list[dict]) -> None:
    """After a setup scan: what each app row found (packages change per lesson .venv, so only apps are kept)."""
    for it in items or []:
        if classify(it) in ("licensed_app", "free_app") and it.get("kind") != "editor" and not it.get("unknown"):
            remember(it["tool"], installed=bool(it.get("installed")), version=it.get("version") or "", where=it.get("where") or "")


def context_line(items: list[dict]) -> str:
    """One line for the coach: which app the lesson works in and what this Mac has. "" for a lesson with no app rows
    (a code lesson's context stays as it was)."""
    parts = []
    for it in items or []:
        sk = classify(it)
        if sk not in ("licensed_app", "free_app") or it.get("kind") == "editor" or not it.get("needed"):
            continue
        name = it.get("label") or it.get("tool")
        if it.get("using"):
            parts.append(f"{name}: the learner uses {it['using']} instead")
        elif it.get("installed"):
            parts.append(f"{name} {it.get('version') or ''}".strip() + " is installed")
        elif it.get("haveIt"):
            parts.append(f"{name}: the learner says they have it")
        else:
            parts.append(f"{name} is not on this Mac yet")
    return ("Apps on this Mac: " + "; ".join(parts) + ".") if parts else ""

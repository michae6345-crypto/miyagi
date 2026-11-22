"""Where lesson folders live, how they are named, and which lesson is the demo hero."""

from __future__ import annotations

import hashlib
import os
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
HERO_WORKDIR_DEFAULT = REPO_ROOT / "demo" / "pinn-lab"

# The hero: Toscano, "Learning Physics Informed Machine Learning Part 1 - PINNs" (1D diffusion).
# Ids of its cached step graphs in demo/cache/lessons/ (built against two different workdirs).
HERO_VIDEO_IDS = {"AXXnSzmpyoI"}
HERO_LESSON_IDS = {"lesson-aebc6b8f", "lesson-9649077b"}


def lessons_root() -> Path:
    """MIYAGI_LESSONS_DIR > ~/miyagi/lessons."""
    v = os.environ.get("MIYAGI_LESSONS_DIR")
    return Path(v).expanduser() if v else Path.home() / "miyagi" / "lessons"


# A lesson .venv's layout: bin/python and lib/python3.x/site-packages on macOS and Linux, Scripts\python.exe and
# Lib\site-packages on Windows (python -m venv makes no bin/ there).

def _windows() -> bool:
    return sys.platform == "win32"


def venv_bin(venv: Path | str) -> Path:
    """The venv's scripts folder (what goes first on PATH): <venv>/bin, or <venv>\\Scripts on Windows."""
    return Path(venv) / ("Scripts" if _windows() else "bin")


def venv_python(venv: Path | str) -> Path:
    """The venv's interpreter: <venv>/bin/python, or <venv>\\Scripts\\python.exe on Windows."""
    return venv_bin(venv) / ("python.exe" if _windows() else "python")


def venv_site_packages(venv: Path | str) -> list[Path]:
    """The venv's site-packages folders that exist: lib/python3.x/site-packages, or Lib\\site-packages on Windows."""
    v = Path(venv)
    if _windows():
        sp = v / "Lib" / "site-packages"
        return [sp] if sp.is_dir() else []
    return sorted(v.glob("lib/python*/site-packages"))


def venv_run_prefix() -> str:
    """How a command line names the lesson .venv's python, relative to the lesson folder (Run it for me):
    `.venv/bin/python`, or `.venv\\Scripts\\python` on Windows (cmd.exe and PowerShell both run it)."""
    return ".venv\\Scripts\\python" if _windows() else ".venv/bin/python"


def slugify(text: str, max_len: int = 48) -> str:
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    if len(t) > max_len:
        t = t[:max_len].rsplit("-", 1)[0] or t[:max_len]
    return t or "lesson"


def lesson_meta(graph: dict) -> dict:
    """The graph's `lesson` object (accepts the whole step graph or just `lesson`)."""
    return graph.get("lesson") if isinstance(graph.get("lesson"), dict) else graph


def primary_url(graph: dict) -> str:
    for s in graph.get("sources") or []:
        if s.get("url"):
            return s["url"]
    return ""


def folder_name(graph: dict) -> str:
    """`<slug-of-title>-<6 hex>`; the hash is over the lesson id (else the video URL), so a
    rebuilt lesson for the same video + goal lands in the same folder."""
    meta = lesson_meta(graph)
    title = meta.get("title") or meta.get("goal") or "lesson"
    basis = meta.get("id") or primary_url(graph) or title
    return f"{slugify(title)}-{hashlib.sha1(basis.encode()).hexdigest()[:6]}"


def video_id(url: str) -> str | None:
    try:
        u = urlparse(url)
    except ValueError:
        return None
    if u.hostname and u.hostname.endswith("youtu.be"):
        return u.path.lstrip("/") or None
    if u.hostname and "youtube" in u.hostname:
        if v := parse_qs(u.query).get("v"):
            return v[0]
        m = re.match(r"/(?:embed|shorts|live)/([\w-]{6,})", u.path)
        return m.group(1) if m else None
    return None


def hero_workdir(graph: dict) -> Path | None:
    """The hero lesson's folder (ORCH_HERO_WORKDIR > demo/pinn-lab) if `graph` is the hero, else None.

    The hero is recognised by its cached lesson id (HERO_LESSON_IDS, plus ORCH_HERO_LESSON_IDS,
    comma-separated) or by its video: AXXnSzmpyoI, or the video in ORCH_LESSON_URL (the lesson
    scripts/miyagi-engine.sh autostarts)."""
    meta = lesson_meta(graph)
    ids = set(HERO_LESSON_IDS) | {x.strip() for x in os.environ.get("ORCH_HERO_LESSON_IDS", "").split(",") if x.strip()}
    graph_vids = {s.get("videoId") or video_id(s.get("url", "")) for s in graph.get("sources") or []}
    return _hero_dir() if meta.get("id") in ids or (graph_vids & _hero_video_ids()) else None


def _hero_video_ids() -> set[str]:
    vids = set(HERO_VIDEO_IDS)
    if v := video_id(os.environ.get("ORCH_LESSON_URL", "")):
        vids.add(v)
    return vids


def _hero_dir() -> Path:
    env = os.environ.get("ORCH_HERO_WORKDIR")
    return (Path(env).expanduser() if env else HERO_WORKDIR_DEFAULT).resolve()


def build_workdir(source_url: str) -> str:
    """The workdir to pass to build_lesson(), before the lesson (and so its folder) exists.

    Hero video -> its folder (the builder adapts checks to pinn_diffusion.py). Anything else ->
    a path that does not exist, so the builder plans for a learner starting from scratch instead
    of adapting checks to demo/pinn-lab's files. prepare() then sets the real folder."""
    return str(_hero_dir() if video_id(source_url) in _hero_video_ids() else lessons_root() / "_new")

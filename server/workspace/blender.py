"""Read a saved .blend headlessly: find Blender, run blender-addon/dump_scene.py on the file, keep X.scene.json.

    from server.workspace import blender
    exe = blender.find_blender()                 # "/Applications/Blender.app/Contents/MacOS/Blender", or None
    doc = blender.dump_blend("lesson/mug.blend") # writes lesson/mug.scene.json, returns its dict (or None)

The dump is the "dump_scene.py 1" format the Blender lesson checks read (file_contains on X.scene.json). Blender
only ever runs with --background --factory-startup --disable-autoexec: no window, no learner add-ons, no scripts
saved in the file. dump_blend never raises; any failure returns None and leaves the old X.scene.json as it was.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DUMP_SCRIPT = REPO_ROOT / "blender-addon" / "dump_scene.py"
BLENDER_ENV = "MIYAGI_BLENDER"
FORMAT = "dump_scene.py 1"

BUNDLE_ID = "org.blenderfoundation.blender"
APP_BINARY = Path("Contents") / "MacOS" / "Blender"
SYSTEM_APP = Path("/Applications/Blender.app")
PAID_KEYS = ("ANTHROPIC_API_KEY", "GEMINI_API_KEY")

Runner = Callable[[list[str], float], int]


# ------------------------------------------------------------------ finding Blender
def _is_exe(path: str | os.PathLike | None) -> bool:
    return bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)


def _spotlight_app() -> str | None:
    """Blender.app wherever Spotlight knows it (setup.find_app), loaded only when the usual places miss."""
    try:
        from server.workspace import setup

        app = setup.find_app(BUNDLE_ID, "Blender")
    except Exception:  # noqa: BLE001 - a broken lookup just means "not found here"
        return None
    return str(Path(app) / APP_BINARY) if app else None


def _candidates() -> Iterator[str | None]:
    yield os.environ.get(BLENDER_ENV)
    yield str(SYSTEM_APP / APP_BINARY)
    yield str(Path.home() / "Applications" / "Blender.app" / APP_BINARY)
    yield _spotlight_app()
    yield shutil.which("blender")


def find_blender() -> str | None:
    """The Blender executable: $MIYAGI_BLENDER, /Applications, ~/Applications, Spotlight, then PATH. None if absent."""
    return next((c for c in _candidates() if _is_exe(c)), None)


# ------------------------------------------------------------------ the dump
def scene_json_path(blend_path: str | os.PathLike) -> Path:
    """X.blend -> X.scene.json in the same folder."""
    p = Path(blend_path)
    return p.with_name(p.stem + ".scene.json")


def dump_argv(blend_path: str | os.PathLike, out_path: str | os.PathLike, *, blender: str) -> list[str]:
    """The headless command line that dumps blend_path to out_path."""
    return [blender, "--background", "--factory-startup", "--disable-autoexec", str(blend_path),
            "--python-exit-code", "1", "--python", str(DUMP_SCRIPT), "--", str(out_path)]


def _clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in PAID_KEYS}


def run_blender(argv: list[str], timeout: float) -> int:
    """Run argv quietly; its return code, or -1 on a timeout or when it cannot start."""
    try:
        done = subprocess.run(argv, capture_output=True, timeout=timeout, env=_clean_env(),
                              stdin=subprocess.DEVNULL, check=False)
    except subprocess.TimeoutExpired:
        return -1
    except OSError:
        return -1
    return done.returncode


def _read_dump(path: Path) -> dict | None:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) and doc.get("dump") == FORMAT else None


def dump_blend(blend_path: str | os.PathLike, out_path: str | os.PathLike | None = None, *,
               timeout: float = 60.0, runner: Runner | None = None, blender: str | None = None) -> dict | None:
    """Dump blend_path with headless Blender into out_path (default X.scene.json); the dict, or None on any failure.

    Blender writes to a temp file next to out_path; only a good dump replaces out_path. Never raises."""
    tmp: Path | None = None
    try:
        blend = Path(blend_path).resolve()
        out = Path(out_path).resolve() if out_path is not None else scene_json_path(blend)
        exe = blender or find_blender()
        if not exe or not blend.is_file() or not DUMP_SCRIPT.is_file():
            return None
        tmp = out.with_name(f".{out.name}.{uuid.uuid4().hex[:8]}.tmp")
        code = (runner or run_blender)(dump_argv(blend, tmp, blender=exe), timeout)
        if code != 0:
            return None
        doc = _read_dump(tmp)
        if doc is None:
            return None
        os.replace(tmp, out)
        tmp = None
        return doc
    except Exception:  # noqa: BLE001 - the contract: a failed dump is None, never an exception
        return None
    finally:
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


# ------------------------------------------------------------------ a new scene (Open in Blender, Nov 24)
NEW_BLEND_EXPR = "import bpy,sys; bpy.ops.wm.save_as_mainfile(filepath=sys.argv[-1])"
BLEND_MAGIC = (b"BLENDER", b"\x28\xb5\x2f\xfd", b"\x1f\x8b")  # plain, zstd- and gzip-compressed .blend


def new_blend_argv(out_path: str | os.PathLike, *, blender: str) -> list[str]:
    """The headless command line that saves Blender's factory scene (cube, camera, light) to out_path."""
    return [blender, "--background", "--factory-startup", "--disable-autoexec", "--python-exit-code", "1",
            "--python-expr", NEW_BLEND_EXPR, "--", str(out_path)]


def has_content(path: str | os.PathLike) -> bool:
    """A file that is there and not empty (lesson mode touches step files: a 0-byte .blend was never saved)."""
    try:
        return os.path.getsize(path) > 0
    except OSError:
        return False


def _looks_like_blend(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            head = fh.read(8)
    except OSError:
        return False
    return any(head.startswith(m) for m in BLEND_MAGIC)


def create_blend(path: str | os.PathLike, *, runner: Runner | None = None, blender: str | None = None,
                 timeout: float = 60.0) -> bool:
    """Make path a new .blend from Blender's factory scene, headless (--background --factory-startup
    --disable-autoexec). Blender writes a temp file next to path; it replaces path only while path is still missing
    or empty, so a scene the learner saved meanwhile is never rewritten. -> True when path now holds a scene (also
    when it already did: nothing runs then), False on any failure (no Blender, a non-zero exit, no or a bad output
    file). The temp file never stays behind. Never raises."""
    tmp: Path | None = None
    try:
        out = Path(path).expanduser().absolute()
        if has_content(out):
            return True
        exe = blender or find_blender()
        if not exe or not out.parent.is_dir():
            return False
        tmp = out.with_name(f".{out.stem}.{uuid.uuid4().hex[:8]}.tmp.blend")
        code = (runner or run_blender)(new_blend_argv(tmp, blender=exe), timeout)
        if code != 0 or not has_content(tmp) or not _looks_like_blend(tmp):
            return False
        if has_content(out):  # the learner saved while Blender ran: theirs stays
            return True
        os.replace(tmp, out)
        tmp = None
        return True
    except Exception:  # noqa: BLE001 - the contract: a failed create is False, never an exception
        return False
    finally:
        if tmp is not None:
            for leftover in (tmp, tmp.with_name(tmp.name + "1")):  # and Blender's .blend1 backup, if it made one
                try:
                    leftover.unlink(missing_ok=True)
                except OSError:
                    pass

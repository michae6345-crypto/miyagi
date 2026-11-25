"""Headless scene dump: write the open .blend's "dump_scene.py 1" JSON to the path after "--".

    <blender> --background --factory-startup --disable-autoexec <file.blend> \\
        --python-exit-code 1 --python <repo>/blender-addon/dump_scene.py -- <out.json>

Loads miyagi_bridge/scene_dump.py by its path (not the miyagi_bridge package, so the bridge server never starts),
writes the JSON through a temp file and os.replace, and exits non-zero on any error. A .blend that Blender could not
open leaves the factory scene loaded; that is an error too, so a broken file never dumps as a default cube.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCENE_DUMP = os.path.join(HERE, "miyagi_bridge", "scene_dump.py")


def load_scene_dump():
    """scene_dump.py as a module, loaded from its file."""
    spec = importlib.util.spec_from_file_location("miyagi_scene_dump", SCENE_DUMP)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {SCENE_DUMP}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def script_args(argv: list[str]) -> tuple[list[str], list[str]]:
    """Blender's own args and the args after "--"."""
    if "--" in argv:
        i = argv.index("--")
        return argv[:i], argv[i + 1:]
    return argv, []


def write_atomic(path: str, text: str) -> None:
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=".scene-dump-", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def main(argv: list[str] | None = None) -> int:
    import bpy

    own, rest = script_args(list(sys.argv if argv is None else argv))
    if not rest:
        print("dump_scene.py: give the output path after --", file=sys.stderr)
        return 2
    if any(a.lower().endswith(".blend") for a in own[1:]) and not bpy.data.filepath:
        print("dump_scene.py: Blender could not open the .blend", file=sys.stderr)
        return 3
    mod = load_scene_dump()
    write_atomic(rest[0], mod.to_json(mod.dump(bpy.context)))
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:  # noqa: BLE001 - any failure is a non-zero exit, with the reason on stderr
        print(f"dump_scene.py: {type(exc).__name__}: {exc}", file=sys.stderr)
        code = 1
    if code:
        sys.exit(code)

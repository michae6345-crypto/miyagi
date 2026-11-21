"""The engine's per-launch token on disk, for the clients that run beside it on this Mac (ROADMAP 5.3).

    engine_token.write(token, port)   # main.run(): ~/.miyagi/engine-tokens/<port>.json, mode 0600, removed on exit
    engine_token.read(port)           # the token of the live engine on <port>, else None
    engine_token.live_tokens()        # every live engine's token (the VS Code companion accepts any of them)

Who reads it: the VS Code companion (it sends X-Miyagi-Token on POST /vscode/event and requires it on its own API
while a live engine has written one), `tut run` (POST /ingest) and the dev CLI (server/orchestrator/client.py). The
token is the app's MIYAGI_ENGINE_TOKEN when the app started the engine, else a fresh random one per launch (it then
guards only the engine -> companion calls; the engine's own HTTP routes need a token only when the app set one).

One file per port, so a stage runner's engine on :8791 never replaces the main engine's. A file whose pid is gone
(the engine crashed) is ignored by every reader. The folder is MIYAGI_ENGINE_TOKEN_DIR, else ~/.miyagi/engine-tokens;
mode 0700, files 0600: other accounts on this Mac can't read them. The token is never logged.
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path

HEADER = "X-Miyagi-Token"
DIR_ENV = "MIYAGI_ENGINE_TOKEN_DIR"


def token_dir() -> Path:
    return Path(os.environ.get(DIR_ENV) or Path.home() / ".miyagi" / "engine-tokens").expanduser()


def _file(port: int) -> Path:
    return token_dir() / f"{int(port)}.json"


def _alive(pid: object) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _load(p: Path) -> dict | None:
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("token"), str) or not data["token"]:
        return None
    return data if _alive(data.get("pid")) else None


def write(token: str, port: int) -> Path | None:
    """Write this engine's token for `port` (atomic, 0600). None when the folder can't be written (logged by the
    caller); the engine still runs, the companion then accepts token-less calls as before."""
    d = token_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            os.chmod(d, 0o700)
        p = _file(port)
        tmp = p.with_name(f".{p.name}.{os.getpid()}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"token": token, "pid": os.getpid(), "port": int(port)}, f)
        os.replace(tmp, p)
        return p
    except OSError:
        return None


def remove(token: str, port: int) -> None:
    """Remove the file for `port` if it is still this engine's (another engine may have taken the port since)."""
    p = _file(port)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if isinstance(data, dict) and data.get("token") == token and data.get("pid") == os.getpid():
        with contextlib.suppress(OSError):
            p.unlink()


def read(port: int) -> str | None:
    data = _load(_file(port))
    return data["token"] if data else None


def live_tokens() -> list[str]:
    out: list[str] = []
    try:
        files = sorted(token_dir().glob("*.json"))
    except OSError:
        return out
    for p in files:
        data = _load(p)
        if data and data["token"] not in out:
            out.append(data["token"])
    return out

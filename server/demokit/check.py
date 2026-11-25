"""Pre-demo check: is this Mac ready to show the neural-net lesson? Reads only, never prompts, never prints a secret.

    python -m server.demokit.check [--offline] [--port N]       (scripts/miyagi-demo-check.sh)

Each row is ok, fix (with the exact fix on the next line), skip (can't check now) or note (a reminder). Exit code 0
when no row says fix. One network call leaves this Mac: GET https://miyagi-cloud.onrender.com/healthz (free, 5 s
timeout; --offline skips it). The engine is asked GET /health on 127.0.0.1 only while the miyagi app runs.
"""

from __future__ import annotations

import argparse
import json
import plistlib
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .common import (
    APP_PROC,
    ENGINE_PORT,
    FILE,
    Layout,
    pgrep,
    port_open,
    read_json,
    saved_lesson_id,
)

CLOUD_HEALTHZ = "https://miyagi-cloud.onrender.com/healthz"
VSCODE_PROC = r"Visual Studio Code\.app/Contents/MacOS/"
CAFFEINATE_PROC = r"(^|/)caffeinate( |$)"
RESET = "Quit miyagi, then run scripts/miyagi-demo-reset.sh"
SETTINGS = "System Settings > Privacy & Security > {}: turn on miyagi, then quit and reopen miyagi"
PANES = {"accessibility": ("Accessibility", "Accessibility"),
         "screen": ("Screen Recording", "Screen & System Audio Recording")}


@dataclass
class Row:
    status: str  # ok | fix | skip | note
    text: str
    fix: str = ""


class Probes:
    """Everything the check asks the Mac. Tests replace these methods; nothing here writes, opens or prompts."""

    def __init__(self, lay: Layout) -> None:
        self.lay = lay

    def app_running(self) -> bool:
        return pgrep(APP_PROC)

    def port_open(self, port: int) -> bool:
        return port_open(port)

    def http_get(self, url: str, timeout: float) -> tuple[int, str] | None:
        """(status, body up to 256 KB), or None when nothing answered."""
        req = urllib.request.Request(url, headers={"User-Agent": "miyagi-demo-check"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read(256 * 1024).decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, ""
        except (OSError, ValueError):
            return None

    def vscode(self) -> dict | None:
        """VS Code from the engine's own lookup (server.workspace.editor): {app_path, cli}, or None if not installed."""
        from server.workspace import editor

        return next((e for e in editor.installed_editors() if e["id"] == "vscode"), None)

    def companion(self) -> tuple[bool | None, str | None]:
        from server.orchestrator import health

        return health.companion_installed()

    def vscode_running(self) -> bool:
        return pgrep(VSCODE_PROC)

    def vscode_windows(self) -> int | None:
        """VS Code windows whose miyagi companion answers on 127.0.0.1 (none opened, nothing focused), or None."""
        try:
            from server.workspace import vscode_ext

            return len(vscode_ext.windows()) or None
        except Exception:  # noqa: BLE001
            return None

    def caffeinated(self) -> bool:
        return pgrep(CAFFEINATE_PROC)

    def on_battery(self) -> bool | None:
        try:
            out = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5, check=False).stdout
        except (OSError, subprocess.SubprocessError):
            return None
        return True if "Battery Power" in out else False if "AC Power" in out else None


def _app_version(app: Path) -> str:
    try:
        with (app / "Contents" / "Info.plist").open("rb") as f:
            return str(plistlib.load(f).get("CFBundleShortVersionString") or "")
    except (OSError, ValueError, plistlib.InvalidFileException):
        return ""


def app_row(lay: Layout) -> Row:
    if not lay.app.is_dir():
        return Row("fix", f"miyagi.app is not in {lay.app.parent}", "Install the latest miyagi build into /Applications")
    v = _app_version(lay.app)
    return Row("ok", f"miyagi.app {v}".strip())


def engine_rows(lay: Layout, p: Probes, app_up: bool) -> tuple[list[Row], dict | None]:
    """The engine row and, when it answers, its setup checklist (GET /health?checks=1, read-only)."""
    port = lay.port
    if not app_up:
        if p.port_open(port):
            return [Row("fix", f"something already holds :{port} while the app is closed (a dev engine?)",
                        f"Stop it (Ctrl-C in its terminal; lsof -nP -iTCP:{port} -sTCP:LISTEN shows it), so the app "
                        "starts its own engine with your real lessons")], None
        return [Row("skip", f"engine on :{port}: miyagi isn't open yet (open it, then run this again to check)")], None
    got = p.http_get(f"http://127.0.0.1:{port}/health?checks=1", 4)
    body = None
    if got and got[0] == 200:
        try:
            body = json.loads(got[1]) if got[1].strip().startswith("{") else None
        except ValueError:
            body = None
    if not (isinstance(body, dict) and body.get("ok")):
        return [Row("fix", f"the engine doesn't answer on :{port}",
                    "Quit miyagi and open it again (it starts its engine); logs: ~/miyagi/engine/logs")], None
    return [Row("ok", f"engine answers on :{port}")], body


def cloud_row(p: Probes, offline: bool) -> Row:
    if offline:
        return Row("skip", "miyagi-cloud: --offline")
    got = p.http_get(CLOUD_HEALTHZ, 5)
    if got and got[0] == 200 and "ok" in got[1].lower():
        return Row("ok", "miyagi-cloud answers (healthz ok)")
    why = "didn't answer in 5 s" if got is None else f"answered {got[0]}"
    return Row("fix", f"miyagi-cloud {why}",
               "Check Wi-Fi, then run this again (a sleeping server can take a minute to wake up)")


def signed_in_row(lay: Layout) -> Row:
    if (lay.app_support / "auth.bin").is_file():  # existence only: never read
        return Row("ok", "signed in")
    return Row("fix", "not signed in", "Open miyagi and sign in")


def vscode_rows(p: Probes) -> list[Row]:
    try:
        ed = p.vscode()
    except Exception as e:  # noqa: BLE001 - a python without the engine's packages
        return [Row("skip", f"VS Code: couldn't load the engine's lookup ({type(e).__name__}); run with the repo .venv")]
    if not ed or not ed.get("app_path"):
        return [Row("fix", "VS Code is not installed", "Install it: https://code.visualstudio.com/download")]
    rows = [Row("ok", "VS Code and its code CLI") if ed.get("cli") else
            Row("fix", "VS Code's code CLI is missing",
                "In VS Code: Cmd+Shift+P > Shell Command: Install 'code' command in PATH")]
    try:
        have, ver = p.companion()
    except Exception:  # noqa: BLE001
        have, ver = None, None
    if have:
        rows.append(Row("ok", f"miyagi's VS Code companion {ver or ''}".rstrip()))
    elif have is False:
        rows.append(Row("fix", "miyagi's VS Code companion is not installed",
                        "Open miyagi: its setup list has Install companion (docs/DEMO.md section 1 has the manual way)"))
    return rows


def permission_rows(health: dict | None) -> list[Row]:
    """Accessibility and Screen Recording as the app's engine sees them (it is the app's child, so macOS answers for
    miyagi). Without the engine: one line to check by hand."""
    items = {i.get("id"): i for i in (health or {}).get("items") or [] if isinstance(i, dict)}
    rows, manual = [], []
    for rid, (short, pane) in PANES.items():
        state = (items.get(rid) or {}).get("state")
        if state == "ok":
            rows.append(Row("ok", f"{short} is on for miyagi"))
        elif state == "missing":
            rows.append(Row("fix", f"{short} is off for miyagi", SETTINGS.format(pane)))
        else:
            manual.append(pane)
    if manual:
        rows.append(Row("note", "Check by hand: System Settings > Privacy & Security > "
                                f"{' and '.join(manual)}: miyagi is on"))
    return rows


def lesson_rows(lay: Layout) -> list[Row]:
    lid, _ = lay.lesson()
    folder = lay.folder()
    left = []
    if folder.is_dir():
        nn = folder / FILE
        try:
            cur = nn.read_text(encoding="utf-8", errors="replace") if nn.is_file() else None
        except OSError:
            cur = None
        if cur is not None and cur != lay.starter():
            left.append(f"{FILE} holds an earlier take")
    if saved_lesson_id(lay.state) == lid:
        left.append("a saved place would offer Continue")
    recent = read_json(lay.state / "recent.json")
    if isinstance(recent, list) and any(isinstance(e, dict) and e.get("lessonId") == lid for e in recent):
        left.append("it's on the launcher's Continue list")
    if left:
        return [Row("fix", f"neural-net lesson: {'; '.join(left)}", RESET)]
    rows = [Row("ok", "neural-net lesson starts clean" + ("" if folder.is_dir() else " (no folder yet)"))]
    if not any(folder.glob(".venv/lib/python*/site-packages/numpy")):
        rows.append(Row("note", "NumPy isn't in the lesson's .venv yet: do one take before the demo "
                                "(its setup card installs it, needs Wi-Fi)"))
    return rows


def vscode_window_row(p: Probes) -> Row:
    if not p.vscode_running():
        return Row("ok", "VS Code is closed (miyagi opens one clean window)")
    n = p.vscode_windows()
    what = f"VS Code is open ({n} window{'s' if n != 1 else ''})" if n else "VS Code is open"
    return Row("fix", what, "Quit VS Code (Cmd+Q) so miyagi opens one clean window")


def reminder_rows(p: Probes) -> list[Row]:
    rows = [Row("note", "Turn on Do Not Disturb: Control Center > Focus > Do Not Disturb (no banners on the projector)")]
    rows.append(Row("ok", "caffeinate keeps the display awake") if p.caffeinated() else
                Row("note", "Keep the display awake: run caffeinate -d in a spare Terminal tab (Ctrl-C after the demo)"))
    batt = p.on_battery()
    if batt:
        rows.append(Row("note", "On battery: plug in the charger"))
    return rows


def run(lay: Layout, p: Probes, *, offline: bool = False) -> list[Row]:
    app_up = p.app_running()
    rows = [app_row(lay)]
    eng, health = engine_rows(lay, p, app_up)
    rows += eng
    rows.append(cloud_row(p, offline))
    rows.append(signed_in_row(lay))
    rows += vscode_rows(p)
    rows += permission_rows(health)
    rows += lesson_rows(lay)
    rows.append(vscode_window_row(p))
    rows += reminder_rows(p)
    return rows


def render(rows: list[Row]) -> list[str]:
    out = ["miyagi pre-demo check"]
    for r in rows:
        out.append(f"  {r.status:<5} {r.text}")
        if r.fix:
            out.append(f"        -> {r.fix}")
    fixes = sum(r.status == "fix" for r in rows)
    out.append("All set." if not fixes else f"{fixes} to fix.")
    return out


def main(argv: list[str] | None = None, *, lay: Layout | None = None, probes: Probes | None = None, out=print) -> int:
    ap = argparse.ArgumentParser(prog="miyagi-demo-check", description="Read-only pre-demo checklist.")
    ap.add_argument("--offline", action="store_true", help="skip the miyagi-cloud check (no network)")
    ap.add_argument("--port", type=int, default=ENGINE_PORT, help=f"the app's engine port (default {ENGINE_PORT})")
    args = ap.parse_args(argv)
    lay = lay or Layout(home=Path.home(), port=args.port)
    rows = run(lay, probes or Probes(lay), offline=args.offline)
    for ln in render(rows):
        out(ln)
    return 0 if not any(r.status == "fix" for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())

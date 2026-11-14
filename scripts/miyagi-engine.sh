#!/usr/bin/env bash
# Start the engine in LIVE mode for LAN access: real modules, real screen, VS Code auto-open.
#
#   scripts/miyagi-engine.sh                 # ws://<this-mac>.local:8787 and ws://localhost:8787
#   scripts/miyagi-engine.sh --port 8788     # extra args go to the engine (--host/--port)
#   DEMO=1 scripts/miyagi-engine.sh          # cached/canned demo data instead of live APIs
#
# Keys come from the shared .env (TUT_ENV, else this checkout's .env, else the main checkout's)
# or from the app's Settings (config.keys), which win.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-$ROOT/.venv/bin/python}"
if [ ! -x "$PY" ]; then
  echo "[miyagi] first run: creating .venv with Python 3.12…"
  command -v uv >/dev/null || { echo "[miyagi] needs uv: curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; }
  uv venv -q --python 3.12 .venv
  uv pip install -q --python .venv/bin/python -e "server[dev]"
  [ -f cli/pyproject.toml ] && uv pip install -q --python .venv/bin/python -e cli
  PY="$ROOT/.venv/bin/python"
fi

export ENGINE_HOST="${ENGINE_HOST:-0.0.0.0}"
export ENGINE_PORT="${ENGINE_PORT:-8787}"
export ORCH_SCREEN="${ORCH_SCREEN:-1}"
export ORCH_OPEN_WORKSPACE="${ORCH_OPEN_WORKSPACE:-1}"
export TUT_WORKDIR="${TUT_WORKDIR:-$ROOT/demo/pinn-lab}"

# --- macOS Screen Recording permission (the screen reader needs it) ---------------------
if [ "$(uname)" = "Darwin" ] && [ "$ORCH_SCREEN" = "1" ]; then
  if ! "$PY" -c "import sys, Quartz; sys.exit(0 if Quartz.CGPreflightScreenCaptureAccess() else 1)" 2>/dev/null; then
    HOST_APP="${TERM_PROGRAM:-the app that runs this script}"
    case "$HOST_APP" in
      Apple_Terminal) HOST_APP="Terminal" ;;
      iTerm.app) HOST_APP="iTerm" ;;
      vscode) HOST_APP="Visual Studio Code" ;;
    esac
    cat <<EOF

[miyagi] Screen capture is DENIED, so the engine can't see your screen.
  Grant it:  System Settings › Privacy & Security › Screen & System Audio Recording
             → turn ON "$HOST_APP"  (the app running this script / python)
  Then QUIT and reopen $HOST_APP and run this script again.
  (Shortcut: open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture")

EOF
    "$PY" -c "import Quartz; Quartz.CGRequestScreenCaptureAccess()" 2>/dev/null || true
    echo "[miyagi] Starting anyway: file saves and \`tut run\` still grade steps; screen checks wait."
  fi
fi

if command -v lsof >/dev/null && lsof -nP -iTCP:"$ENGINE_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "[miyagi] port $ENGINE_PORT is already in use (another engine or the app's mock?):"
  lsof -nP -iTCP:"$ENGINE_PORT" -sTCP:LISTEN | tail -n +2
  exit 1
fi

HOSTNAME_LOCAL="$(scutil --get LocalHostName 2>/dev/null || hostname -s).local"
echo "[miyagi] engine: ws://localhost:$ENGINE_PORT  ·  LAN: ws://$HOSTNAME_LOCAL:$ENGINE_PORT"
echo "[miyagi] workspace: $TUT_WORKDIR   mode: $([ "${DEMO:-0}" = "1" ] && echo DEMO || echo LIVE)"
exec "$PY" -m server.orchestrator.main --host "$ENGINE_HOST" --port "$ENGINE_PORT" "$@"

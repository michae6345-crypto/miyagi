#!/usr/bin/env bash
# Put the neural-net lesson back to its first moment, for the installed miyagi app (docs/DEMO.md, "Before any demo").
#
#   scripts/miyagi-demo-reset.sh             quit miyagi first; moves the old nn.py and the lesson's saved place aside
#   scripts/miyagi-demo-reset.sh --dry-run   only print what it would move
#
# Never deletes: the old nn.py goes to ~/miyagi/lessons/.miyagi-state/attempts/, the saved place to
# ~/miyagi/state/.demo-backups/<time>/ (manifest.json lists every move). .venv stays, so NumPy stays installed.
# Other lessons, prefs, onboarding and sign-in are not touched. The code: server/demokit/reset.py.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLED="/Applications/miyagi.app/Contents/Resources/engine/python/bin/python3"
PY="${PYTHON:-}"
for c in "$ROOT/.venv/bin/python" "$BUNDLED" "$(command -v python3 || true)"; do
  [ -z "$PY" ] && [ -n "$c" ] && [ -x "$c" ] && PY="$c"
done
[ -n "$PY" ] || { echo "[demo-reset] no python3 found"; exit 1; }
cd "$ROOT"
PYTHONPATH="$ROOT" exec "$PY" -B -m server.demokit.reset "$@"

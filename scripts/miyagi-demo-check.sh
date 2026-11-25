#!/usr/bin/env bash
# Pre-demo check for the installed miyagi app (docs/DEMO.md, "Before any demo"). Reads only; never prints a secret.
#
#   scripts/miyagi-demo-check.sh             ok / fix lines, with the exact fix under each; exit 0 when nothing to fix
#   scripts/miyagi-demo-check.sh --offline   skip the miyagi-cloud healthz GET (the only call off this Mac)
#
# The code: server/demokit/check.py.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLED="/Applications/miyagi.app/Contents/Resources/engine/python/bin/python3"
PY="${PYTHON:-}"
for c in "$ROOT/.venv/bin/python" "$BUNDLED" "$(command -v python3 || true)"; do
  [ -z "$PY" ] && [ -n "$c" ] && [ -x "$c" ] && PY="$c"
done
[ -n "$PY" ] || { echo "[demo-check] no python3 found"; exit 1; }
cd "$ROOT"
PYTHONPATH="$ROOT" exec "$PY" -B -m server.demokit.check "$@"

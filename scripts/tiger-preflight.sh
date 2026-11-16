#!/usr/bin/env bash
# Tiger Data preflight: run it before recording and again at the judging table.
# The venue Wi-Fi blocks Tiger Cloud's port, so turn on the VPN (or a phone hotspot) first.
#
#   scripts/tiger-preflight.sh
#
# 1. ping Tiger Cloud (TCP, login, timescaledb version, hypertables + continuous aggregates, row counts)
# 2. if part of the schema is missing: `tut db init` (idempotent), then ping again
# 3. upload the offline spool (~/.miyagi/tiger-spool) now instead of waiting for the engine's 30 s retry
# 4. if the engine is running: check that GET /stats/data answers online
# Exit 0 = Tiger reachable, schema complete, spool empty: http://localhost:8787/stats shows live numbers.
# Never prints the user, password or connection string.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
[ -x "$PY" ] || { echo "[tiger] no $PY yet: run scripts/miyagi-engine.sh once (it creates .venv)"; exit 1; }
TUT="$ROOT/.venv/bin/tut"
PORT="${ENGINE_PORT:-8787}"

ping_json() { "$PY" -m server.checks.tiger --ping --json 2>/dev/null | tail -n 1; }
field() { "$PY" -c 'import json,sys
try: d = json.loads(sys.argv[1])
except Exception: d = {}
v = d.get(sys.argv[2])
print(" ".join(v) if isinstance(v, list) else ("" if v is None else v))' "$1" "$2"; }

echo "[tiger] 1/4 ping"
"$PY" -m server.checks.tiger --ping
J="$(ping_json)"
if [ "$(field "$J" ok)" != "True" ]; then
  echo
  echo "[tiger] NOT REACHABLE. Turn on the VPN or a phone hotspot, then run this again."
  echo "[tiger] Nothing is lost meanwhile: rows wait in ~/.miyagi/tiger-spool."
  exit 1
fi

MISSING="$(field "$J" missing)"
if [ -n "$MISSING" ]; then
  echo "[tiger] 2/4 schema incomplete ($MISSING): running tut db init"
  [ -x "$TUT" ] || { echo "[tiger] no $TUT: uv pip install --python .venv/bin/python -e cli"; exit 1; }
  "$TUT" db init || exit 1
  J="$(ping_json)"
  MISSING="$(field "$J" missing)"
  [ -z "$MISSING" ] || { echo "[tiger] still missing after init: $MISSING"; exit 1; }
else
  echo "[tiger] 2/4 schema complete"
fi

echo "[tiger] 3/4 upload the spool"
"$PY" -m server.checks.tiger --flush-spool || exit 1

echo "[tiger] 4/4 engine /stats"
if S="$(curl -s -m 8 "http://127.0.0.1:$PORT/stats/data")" && [ -n "$S" ]; then
  if [ "$(field "$S" online)" = "True" ]; then
    echo "[tiger] /stats online: open http://localhost:$PORT/stats"
  else
    echo "[tiger] the engine's /stats still says offline ($(field "$S" error))."
    echo "[tiger] It retries every 30 s; reload the page in a minute. If it stays offline, restart the engine."
    exit 1
  fi
else
  echo "[tiger] engine not running on :$PORT (start it, then open http://localhost:$PORT/stats)"
fi

echo
"$PY" -m server.checks.tiger --ping | tail -n 4
echo "[tiger] READY"

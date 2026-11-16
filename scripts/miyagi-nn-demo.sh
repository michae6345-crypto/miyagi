#!/usr/bin/env bash
# The offline neural-net demo: the real engine (real screen, real checks) with DEMO=1, so the lesson, coach card,
# Explain / Hint / Ask cards and the live network diagrams all come from demo/cache. No API calls, no network.
#   scripts/miyagi-nn-demo.sh                 (extra args go to the engine, e.g. --port 8788)
# Then in miyagi: open the launcher, type "build a neural network", pick "Just teach me".
# (LIVE needs no script: scripts/miyagi-engine.sh serves the same lesson for any neural-network goal, coach live.)
# Needs numpy for python3 (pip3 install numpy, or brew install numpy). Rebuild the data: python3 scripts/make_nn_demo.py
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAB="$ROOT/demo/nn-lab"
# Every take starts from the same file (the curated lesson only fills nn.py when it's empty in a pinned folder).
cp "$ROOT/demo/nn-start.py" "$LAB/nn.py"
# Its own saved-progress folder, wiped every take, so the lesson always starts at step 1 (no "Continue?" card).
export MIYAGI_STATE_DIR="$ROOT/demo/.nn-state"
rm -rf "$MIYAGI_STATE_DIR"
export DEMO=1
export TUT_WORKDIR="$LAB"
export COACH_OFFLINE_FALLBACK=1
exec "$ROOT/scripts/miyagi-engine.sh" "$@"

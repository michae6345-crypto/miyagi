#!/usr/bin/env bash
# The offline neural-net demo: the real engine (real screen, real checks) with DEMO=1, so the lesson, coach card,
# Explain / Hint / Ask cards and the live network diagrams all come from demo/cache. No API calls, no network.
#   scripts/miyagi-nn-demo.sh                 (extra args go to the engine, e.g. --port 8788)
# Then in miyagi: open the launcher, type "build a neural net from scratch", pick "Just teach me".
# Needs numpy for python3 (pip3 install numpy). Rebuild the data with: python3 scripts/make_nn_demo.py
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAB="$ROOT/demo/nn-lab"
# Every take starts from the same empty file.
cp "$ROOT/demo/nn-start.py" "$LAB/nn.py"
# Under DEMO=1, "Just teach me" loads the newest lesson-mode lesson in demo/cache/lessons: make it this one.
touch "$ROOT/demo/cache/lessons/text-nn-from-scratch.json"
# Its own saved-progress folder, wiped every take, so the lesson always starts at step 1 (no "Continue?" card).
export MIYAGI_STATE_DIR="$ROOT/demo/.nn-state"
rm -rf "$MIYAGI_STATE_DIR"
export DEMO=1
export TUT_WORKDIR="$LAB"
export ORCH_LESSON="${ORCH_LESSON:-demo/cache/lessons/text-nn-from-scratch.json}"
export COACH_OFFLINE_FALLBACK=1
exec "$ROOT/scripts/miyagi-engine.sh" "$@"

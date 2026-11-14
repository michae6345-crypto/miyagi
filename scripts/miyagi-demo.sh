#!/usr/bin/env bash
# The stage hero: Toscano's diffusion PINN lesson (YouTube AXXnSzmpyoI), autostarted on demo/pinn-lab with
# E2's cached lesson, everything else LIVE (real checks, screen, coach). Hero failure: lr = 0.3 -> coach -> 1e-3.
#   scripts/miyagi-demo.sh            (extra args go to the engine)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export TUT_WORKDIR="${TUT_WORKDIR:-$ROOT/demo/pinn-lab}"
export ORCH_LESSON_URL="${ORCH_LESSON_URL:-https://www.youtube.com/watch?v=AXXnSzmpyoI}"
export ORCH_AUTOSTART=1
exec "$ROOT/scripts/miyagi-engine.sh" "$@"

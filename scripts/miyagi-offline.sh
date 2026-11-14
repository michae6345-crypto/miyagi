#!/usr/bin/env bash
# The stage fallback when the network is dead: the hero lesson autostarted from demo/cache with DEMO=1.
# Measured in docs/REHEARSAL.md: search, lesson, checks, `tut run` and the Tiger spool all work with no network;
# the coach card is E5's curated `lr_too_high` playbook card (demo/cache/coach/s8.json), not a live Opus call,
# so it appears at once instead of waiting out Opus' timeout on a half-dead network. Fix the lr by hand offline.
#   scripts/miyagi-offline.sh                 (extra args go to the engine, e.g. --port 8788)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export DEMO=1
export ORCH_AUTOSTART="${ORCH_AUTOSTART:-1}"   # the lesson is live as soon as the engine is up
# ORCH_LESSON wins over the pick under DEMO=1 (two cached lessons are the hero video; this is the stage one)
export ORCH_LESSON="${ORCH_LESSON:-demo/cache/lessons/aebc6b8fba02dac5.json}"
export ORCH_HERO_WORKDIR="${ORCH_HERO_WORKDIR:-$ROOT/demo/pinn-lab}"
exec "$ROOT/scripts/miyagi-engine.sh" "$@"

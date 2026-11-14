"""Engine hub (E4). See README.md. Entry point: server.orchestrator.main:app"""

import sys as _sys
from pathlib import Path as _Path

# `shared/contracts` is a plain folder, not an installed package: put the repo root on
# sys.path before any submodule imports `shared.contracts.events`.
_ROOT = str(_Path(__file__).resolve().parents[2])
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)

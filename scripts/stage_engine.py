"""Launcher for the engine that scripts/stage.py starts on its spare port.

Same app as `python -m server.orchestrator.main` (FastAPI + uvicorn), but under its own command line, so a
`pkill -f server.orchestrator.main` aimed at the :8787 dev engine doesn't take the stage runner's engine down
mid-build (that happened on 2026-11-14 during the any-topic run).

  .venv/bin/python scripts/stage_engine.py --port 8790
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.orchestrator.main import run  # noqa: E402

if __name__ == "__main__":
    run()

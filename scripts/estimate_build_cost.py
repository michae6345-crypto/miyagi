"""Offline: what one lesson build costs before (no caching) and after (prompt caching), from token counts.

    python scripts/estimate_build_cost.py [profile.json]

Reads server/lesson/tests/fixtures/build_cost_profile.json by default; prices from server/lesson/cost.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.lesson import build_cost_estimate as est

if __name__ == "__main__":
    print(est.report(est.load(sys.argv[1]) if len(sys.argv) > 1 else None))

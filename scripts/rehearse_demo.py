#!/usr/bin/env python3
"""Rehearse the judged Demo (docs/DEMO.md) headless, on a PRIVATE engine, and print a pass/fail table per step.

  .venv/bin/python scripts/rehearse_demo.py                 # port 8899, temp HOME / lessons / state, no paid keys
  .venv/bin/python scripts/rehearse_demo.py -v --keep       # live log; keep the temp folder (engine.log, nn.py)
  .venv/bin/python scripts/rehearse_demo.py --json out.json # the report as JSON too

Never touches :8787, the real VS Code companion, ~/miyagi or the screen (server/tests/demo_rehearsal.py has the
details). Exit code 0 when every DEMO.md row passes ("brief" rows are reported, never fail it).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.tests import demo_rehearsal as dr  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=dr.DEFAULT_PORT, help=f"engine port (default {dr.DEFAULT_PORT})")
    ap.add_argument("--keep", action="store_true", help="keep the temp folder (engine.log, lessons, state)")
    ap.add_argument("--json", type=Path, help="write the report here too")
    ap.add_argument("-v", "--verbose", action="store_true", help="print each row as it runs")
    ap.add_argument("--env", action="append", default=[], metavar="K=V", help="extra engine env, e.g. MIYAGI_STAGE_STUCK=always")
    args = ap.parse_args()
    if args.port == dr.LIVE_PORT:
        sys.exit("never :8787 (the live engine): pick a spare port")
    if why := dr.deps_missing():
        sys.exit(f"can't rehearse here: {why}")
    base = Path(tempfile.mkdtemp(prefix="miyagi-demo-rehearsal-"))
    extra = dict(kv.split("=", 1) for kv in args.env)
    try:
        report = asyncio.run(dr.rehearse(args.port, base, verbose=args.verbose, extra_env=extra))
    finally:
        if not args.keep:
            shutil.rmtree(base, ignore_errors=True)
    print(dr.table(report, color=sys.stdout.isatty() and not os.environ.get("NO_COLOR")))
    if args.keep:
        print(f"\nkept: {base}")
    if args.json:
        args.json.write_text(json.dumps(report, indent=1))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

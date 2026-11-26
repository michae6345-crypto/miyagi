"""The judged Demo, rehearsed end to end on a private engine (server/tests/demo_rehearsal.py): ~1.5 min.

    python -m pytest server/tests/test_demo_rehearsal.py -q          # just this
    python -m pytest server -m "not demo_rehearsal"                  # everything but this
    MIYAGI_SKIP_REHEARSAL=1 python -m pytest server                  # same

Skips cleanly when a dependency (websockets, httpx, uvicorn, fastapi, the lesson's recorded runs) is missing. Fails
with the full pass/fail table when any DEMO.md row fails; "brief" rows are printed, never fail it.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from server.tests import demo_rehearsal as dr

pytestmark = pytest.mark.demo_rehearsal


@pytest.mark.skipif(bool(os.environ.get("MIYAGI_SKIP_REHEARSAL")), reason="MIYAGI_SKIP_REHEARSAL is set")
def test_the_judged_demo_rehearses_clean(tmp_path, capsys):
    if why := dr.deps_missing():
        pytest.skip(f"Demo rehearsal: {why}")
    report = asyncio.run(dr.rehearse(dr.free_port(), tmp_path / "rehearsal", slack=1.5))
    table = dr.table(report)
    if report["ok"]:  # the timings and the brief rows, also when it passes (a failure prints it below)
        with capsys.disabled():
            print("\n" + table)
    failed = [r["id"] for r in report["rows"] if r["tier"] == "demo" and not r["ok"]]
    assert report["ok"], f"DEMO.md rows failed: {failed}\n\n{table}"

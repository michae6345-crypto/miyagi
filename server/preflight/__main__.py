"""python -m server.preflight URL --goal "..." [--timeout 5] [--json]  -> prints the card + latencies."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging

from .core import preflight, preflight_card


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--goal", default="")
    ap.add_argument("--timeout", type=float, default=5.0)
    ap.add_argument("--no-requirements", action="store_true")
    ap.add_argument("--json", action="store_true", help="print the full result too")
    a = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(_run(a))


async def _run(a) -> None:
    got_late = asyncio.Event()

    def on_late(r: dict) -> None:
        print("\n--- late update (card re-emitted) ---")
        _show(r, a.json)
        got_late.set()

    res = await preflight(a.url, a.goal, timeout=a.timeout, requirements_fn=None if a.no_requirements else True,
                          on_late=on_late)
    _show(res, a.json)
    if {"requirements", "claude"} & set(res["missing"]):
        try:
            await asyncio.wait_for(got_late.wait(), 15)
        except TimeoutError:
            print("(no late update)")


def _show(res: dict, full: bool) -> None:
    print(json.dumps(preflight_card(res), indent=1, ensure_ascii=False))
    print("timings:", res["timings"], "| missing:", res["missing"], "| notes:", res["notes"])
    if full:
        print(json.dumps({k: v for k, v in res.items() if k != "description"}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()

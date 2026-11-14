"""python -m server.finder "train a PINN on the convection equation" [--refresh] [--json] [-v]

Runs a real search and prints the ranked results with their URLs. Streams rows as they
arrive (with the time since start), then prints the final ranking."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time

from . import cache
from .search import search


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m server.finder", description=__doc__.splitlines()[0])
    ap.add_argument("query", nargs="+")
    ap.add_argument("--refresh", action="store_true", help="ignore demo/cache/search and search live")
    ap.add_argument("--no-cache", action="store_true", help="don't read or write the cache")
    ap.add_argument("--json", action="store_true", help="print the final list as JSON")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(name)s: %(message)s", stream=sys.stderr)
    query = " ".join(args.query)
    t0 = time.monotonic()

    async def on_result(r: dict) -> None:
        if not args.json:
            print(f"  +{time.monotonic() - t0:5.1f}s  [{r['kind']:8}] {r['score']:3d}  {r['title'][:70]}", file=sys.stderr)

    async def run() -> list[dict]:
        return await search(query, on_result, use_cache=not args.no_cache, refresh=args.refresh)

    if not args.json:
        print(f"searching: {query}", file=sys.stderr)
    results = asyncio.run(run())
    took = time.monotonic() - t0
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return
    print(f"\n{len(results)} results in {took:.1f}s (best first):\n")
    for i, r in enumerate(results, 1):
        print(f"{i:2d}. [{r['kind']}] {r['score']:3d}  {r['title']}")
        print(f"      {r['meta']}")
        print(f"      {r['reason']}")
        print(f"      {r['url']}")
        for w in r.get("warnings", []):
            print(f"      ! comment: {w[:100]}")
    hit = cache.load(query)
    if hit:
        print(f"\ncache: {cache.path_for(query)}  providers: {', '.join(hit.get('providers', [])) or 'cached'}")
        for n in hit.get("notes", [])[:8]:
            print(f"  note: {n}")


if __name__ == "__main__":
    main()

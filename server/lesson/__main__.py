"""CLI: python -m server.lesson <youtube-url> --goal "..." --workdir path [--report fixture.json]

Prints the step graph (JSON) to stdout; progress and the precision report go to stderr,
so `> graph.json` captures just the graph.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from .builder import build_lesson
from .precision import format_report, report
from .workdir import scan


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m server.lesson", description=__doc__.splitlines()[0])
    ap.add_argument("url", nargs="?", help="public YouTube URL")
    ap.add_argument("--goal", default="", help="what the learner wants to learn")
    ap.add_argument("--workdir", default=".", help="learner's project folder (checks are adapted to it)")
    ap.add_argument("--refresh", action="store_true", help="ignore the cache and call Gemini again")
    ap.add_argument("--readapt", action="store_true", help="reuse the cached video draft, redo only the adapt pass")
    ap.add_argument("--no-cache", action="store_true", help="don't read or write demo/cache (e.g. to compare engines)")
    ap.add_argument("--engine", choices=["auto", "gemini", "claude"], help="override LESSON_ENGINE")
    ap.add_argument("--detail", action="store_true", help="per-step clip pass at 2 fps (one extra request per step)")
    ap.add_argument("--graph", help="score an existing graph JSON instead of building one")
    ap.add_argument("--report", metavar="EXPECTED", help="print a precision report against a hand-written graph (fixtures/*.json)")
    ap.add_argument("--report-json", action="store_true", help="print the report as JSON instead of a table")
    ap.add_argument("-q", "--quiet", action="store_true", help="don't print the graph")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, stream=sys.stderr, format="%(levelname)s %(name)s: %(message)s")

    if a.graph:
        graph = json.loads(Path(a.graph).read_text(encoding="utf-8"))
    elif a.url:
        if not a.goal:
            ap.error("--goal is required when building a lesson")
        if a.engine:
            os.environ["LESSON_ENGINE"] = a.engine
        graph = asyncio.run(build_lesson(a.url, a.goal, a.workdir, refresh=a.refresh, readapt=a.readapt, detail=a.detail, cache=not a.no_cache))
    else:
        ap.error("give a YouTube URL or --graph FILE")

    if not a.quiet:
        print(json.dumps(graph, indent=2))
    if a.report:
        expected = json.loads(Path(a.report).read_text(encoding="utf-8"))
        info = scan(a.workdir)
        r = report(graph, expected, info.metrics, set(info.files))
        print(json.dumps(r, indent=2) if a.report_json else format_report(r), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

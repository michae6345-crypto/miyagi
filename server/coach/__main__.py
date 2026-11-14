"""python -m server.coach demo [--live | --replay] [--record] [--json]

Runs the hero case (PINN, convection, β=30, flat loss) through diagnose() and prints the card.
Default: live API if ANTHROPIC_API_KEY is set, otherwise the recorded fixture.
--record writes the live response to server/coach/fixtures/ for CI replay.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import textwrap

from . import llm
from .common import set_lesson
from .demo_case import CODE, FAILED_CHECKS, LESSON, METRICS, STEP
from .diagnose import diagnose, public
from .explain import explain
from .hints import hint


def _print_card(card: dict) -> None:
    w = 64
    bar = "─" * w
    sev = {"warn": "◐ amber", "fail": "● red"}.get(card.get("severity", ""), "")
    print(f"┌{bar}┐")
    print(f"│ {sev:<{w - 1}}│")
    print(f"│ {card['title']:<{w - 1}}│")
    print(f"├{bar}┤")
    for line in textwrap.wrap(card["body"], w - 2):
        print(f"│ {line:<{w - 1}}│")
    if d := card.get("diff"):
        print(f"├{bar}┤")
        loc = f"{d.get('file', '')}:{d.get('line', '')}".strip(":")
        if loc:
            print(f"│ {loc:<{w - 1}}│")
        for l in (d.get("yours") or "").splitlines():
            print(f"│ - {l[: w - 3]:<{w - 3}}│")
        for l in d["expected"].splitlines():
            print(f"│ + {l[: w - 3]:<{w - 3}}│")
    if c := card.get("citation"):
        print(f"├{bar}┤")
        print(f"│ {c['label'][: w - 1]:<{w - 1}}│")
        print(f"│ {c['url'][: w - 1]:<{w - 1}}│")
    print(f"├{bar}┤")
    acts = "  ".join(f"[{a}]" for a in card.get("actions", []))
    print(f"│ {acts:<{w - 1}}│")
    print(f"└{bar}┘")


async def demo(args) -> None:
    if args.replay or (not args.live and not llm.has_credentials()):
        os.environ.setdefault("COACH_REPLAY_DIR", str(llm.FIXTURES_DIR))
        os.environ.setdefault("DEMO", "1")  # replay is demo mode: offline cards allowed
        print(f"(replaying recorded fixture from {os.environ['COACH_REPLAY_DIR']}; use --live with ANTHROPIC_API_KEY for a real call)\n")
    if args.record:
        os.environ["COACH_RECORD_DIR"] = str(llm.FIXTURES_DIR)
    set_lesson(LESSON)
    card = await diagnose(STEP, FAILED_CHECKS, METRICS, CODE)
    meta = card.get("_meta", {})
    _print_card(card)
    print(f"\nroute={meta.get('route')} triage={meta.get('triage', {}).get('by')} model={meta.get('model', '-')} "
          f"latency={meta.get('latency_s', '-')}s source={meta.get('source', '-')}")
    if meta.get("usage"):
        print(f"usage={meta['usage']}")
    if meta.get("fallback_reason"):
        print(f"fallback: {meta['fallback_reason']}")
    if args.json:
        print("\nofftrack payload:\n" + json.dumps(public(card), indent=2, ensure_ascii=False))
    if args.ladder:
        print("\nhint ladder:")
        for lvl in range(4):
            h = hint(STEP, lvl)
            print(f"  {lvl} {h['levelName']:<8} {h['title']}: {h['body']}" + (f"  → {h['videoJump']['label']}" if h.get("videoJump") else ""))
    if args.explain:
        c = await explain(STEP, None, {"metrics_summary": METRICS})
        print(f"\nexplain card: {c['title']} — {c['body']}" + (f"  → {c['videoJump']['label']}" if c.get("videoJump") else ""))


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m server.coach")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="run the PINN flat-loss case and print the card")
    g = d.add_mutually_exclusive_group()
    g.add_argument("--live", action="store_true", help="force a live API call")
    g.add_argument("--replay", action="store_true", help="force the recorded fixture")
    d.add_argument("--record", action="store_true", help="save live responses as fixtures")
    d.add_argument("--json", action="store_true", help="also print the raw offtrack payload")
    d.add_argument("--ladder", action="store_true", help="also print the hint ladder")
    d.add_argument("--explain", action="store_true", help="also run explain() for the card")
    args = p.parse_args()
    if args.cmd == "demo":
        asyncio.run(demo(args))


if __name__ == "__main__":
    main()

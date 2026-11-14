"""Preflight: what the picked video is, how well it fits the goal and what it needs, in <= 5 s,
before the lesson build starts.

    from server.preflight import preflight, preflight_card, prefetch
    prefetch(rows, goal)                                 # on search.done: top 3 videos, in the background
    res = await preflight(url, goal, row=picked_row, on_late=lambda r: emit("card", preflight_card(r)))
    await emit("card", preflight_card(res))              # buttons: build / pick_another (+ install)
"""

from .core import (
    build_plan,
    cached_skim,
    classify,
    clear_memo,
    light_graph,
    needs_line,
    prefetch,
    preflight,
    preflight_card,
)
from .meta import parse_chapters, parse_watch_page

__all__ = ["build_plan", "cached_skim", "classify", "clear_memo", "light_graph", "needs_line", "parse_chapters",
           "parse_watch_page", "prefetch", "preflight", "preflight_card"]

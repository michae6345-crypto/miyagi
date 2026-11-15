"""Lesson builder (E2): YouTube tutorial -> step graph with machine-checkable checks.

    from server.lesson import build_lesson
    graph = await build_lesson(url, goal="train a PINN on convection", workdir="demo/pinn")
"""

from .builder import build_lesson, cache_key
from .textlesson import build_text_lesson

__all__ = ["build_lesson", "build_text_lesson", "cache_key"]

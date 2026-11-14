"""server/finder: real tutorial search (YouTube, blogs, notebooks, repos, papers) + Gemini triage.

The orchestrator calls `await search(query)` (optionally with on_result to stream rows).
Each row is a `search.result` payload plus "url"; the chosen row's url goes straight
into lesson.build_lesson(url, goal, workdir)."""

from .search import search

__all__ = ["search"]

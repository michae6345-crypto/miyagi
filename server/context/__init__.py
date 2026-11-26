"""Context memory: short, local notes of what a lesson saw and did, so later answers are context-aware.

    from server.context import ContextStore, FileScanner, what_we_know, wipe_all
    See README.md: store.py (save, dedupe, redact, caps, wipe), extract.py (rule-based summaries), scan.py (incremental
    file outlines), recall.py (the "what we know so far" block a coach prompt carries as untrusted data).
"""

from server.context.recall import what_we_know
from server.context.scan import FileScanner
from server.context.store import PRIVACY_FACT, ContextStore, enabled, facts, prune, wipe_all, wipe_lesson

__all__ = ["PRIVACY_FACT", "ContextStore", "FileScanner", "enabled", "facts", "prune", "what_we_know", "wipe_all",
           "wipe_lesson"]

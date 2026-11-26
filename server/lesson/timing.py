"""Step timing without watching the video: pin each step's start to where it begins in the video's own text.

The Claude path reads the transcript, so its step starts are whole seconds copied off "[m:ss]" transcript lines, and
it sometimes picks a line a few seconds to half a minute away from where the tutorial actually moves on. Two things
YouTube publishes say where a step begins:

1. **Chapter marks** (from the description): the uploader's own boundaries. A step start within CHAPTER_WINDOW_S of a
   mark that no earlier step took moves to the mark.
2. **Caption lines**: otherwise the start moves to the exact start of the caption line it names (the line whose
   whole second it is), else the line being spoken at that moment (at most CAPTION_WINDOW_S earlier), so playback
   starts at the beginning of a sentence, not halfway through one.

A pin never reorders steps, never leaves a step shorter than MIN_KEEP_S, and only trims the previous step's end when
the new start moved into it. `evals/lesson/timing_eval.py` measures it offline against chapter marks.
"""

from __future__ import annotations

CHAPTER_WINDOW_S = 15.0  # held-out eval: 15 s or less is neutral, 30 s pulls steps onto neighbouring marks (report.md)
CAPTION_WINDOW_S = 8.0
MIN_KEEP_S = 5.0


def caption_start(t: float, lines: list[dict], window: float = CAPTION_WINDOW_S) -> float | None:
    """The start of the caption line a step starting at `t` begins on: a line starting in the same whole second
    (the "[m:ss]" the model copied), else the line being spoken at `t` (started at most `window` s before), else None."""
    if not lines:
        return None
    sec = int(t)
    for ln in lines:
        lt = ln.get("t")
        if isinstance(lt, (int, float)) and int(lt) == sec:
            return float(lt)
    before = [float(ln["t"]) for ln in lines if isinstance(ln.get("t"), (int, float)) and ln["t"] <= t and t - ln["t"] <= window]
    return max(before) if before else None


def pin_starts(steps: list[dict], transcript: list[dict] | None, chapters: list[dict] | None, *,
               chapter_window: float = CHAPTER_WINDOW_S, caption_window: float = CAPTION_WINDOW_S) -> dict:
    """Pin each step's `start` (seconds, steps in time order) in place. Returns {"chapter": n, "caption": n, "kept": n}."""
    lines = sorted((ln for ln in transcript or [] if isinstance(ln.get("t"), (int, float))), key=lambda ln: ln["t"])
    marks = sorted({float(c["t"]) for c in chapters or [] if isinstance(c.get("t"), (int, float))})
    used: set[float] = set()
    stats = {"chapter": 0, "caption": 0, "kept": 0}
    for i, st in enumerate(steps):
        t, end = float(st["start"]), float(st["end"])
        prev = steps[i - 1] if i else None
        lo = float(prev["start"]) + MIN_KEEP_S if prev else -1.0  # never before (or onto) the previous step's start
        new, how = None, "kept"
        near = [m for m in marks if abs(m - t) <= chapter_window and m not in used and lo < m < end - MIN_KEEP_S]
        if near:
            new, how = min(near, key=lambda m: (abs(m - t), m)), "chapter"
        else:
            c = caption_start(t, lines, caption_window)
            if c is not None and lo < c < end - MIN_KEEP_S:
                new, how = c, "caption"
        if new is None or new == t:
            stats["kept" if new is None else how] += 1
            if how == "chapter":
                used.add(new)
            continue
        if prev is not None and float(prev["end"]) > new:
            prev["end"] = new  # moved into the previous step: it now ends where this one begins
        st["start"] = new
        if how == "chapter":
            used.add(new)
        stats[how] += 1
    return stats

"""Learner-vs-tutorial curve comparison on Tiger Data (metrics_1s continuous aggregate).

    from server.checks.curves import compare_to_reference
    with psycopg.connect(os.environ["TIGER_DATABASE_URL"]) as conn:
        cmp = compare_to_reference(conn, learner_run_id, metric="loss")

Returns {"tutorial_run_id", "metric", "points": [{step, learner, tutorial, gap_decades}],
"latest": {...} | None, "summary": str}. The coach can quote ``summary`` directly
("at step 3000 your loss is 18x the tutorial's").
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

SQL_PATH = Path(__file__).parent / "sql" / "compare_curves.sql"

# Only tutorial curves of the SAME lesson; same step first, then newest. Never another lesson's curve.
FIND_REFERENCE_SQL = """
SELECT id FROM runs
WHERE source = 'tutorial' AND lesson_id = %(lesson)s
ORDER BY (step_id IS NOT DISTINCT FROM %(step)s) DESC, started_at DESC NULLS LAST
LIMIT 1
"""


def find_reference_run(conn: Any, learner_run_id: str, lesson_id: str | None = None,
                       step_id: str | None = None) -> str | None:
    """The tutorial reference run for a learner run, or None.

    ``lesson_id``/``step_id`` default to the learner run's own row in ``runs``. Screen-first
    runs (``screen-<lesson>``) have no ``runs`` row, so pass ``lesson_id`` for those; the
    ``screen-`` prefix is also understood. Without a known lesson there is no reference.
    """
    if lesson_id is None:
        row = conn.execute("SELECT lesson_id, step_id FROM runs WHERE id = %s", (learner_run_id,)).fetchone()
        if row:
            lesson_id, step_id = row[0], step_id or row[1]
        elif learner_run_id.startswith("screen-"):
            lesson_id = learner_run_id[len("screen-"):]
    if not lesson_id:
        return None
    row = conn.execute(FIND_REFERENCE_SQL, {"lesson": lesson_id, "step": step_id}).fetchone()
    return row[0] if row else None


def compare_to_reference(conn: Any, learner_run_id: str, metric: str = "loss",
                         tutorial_run_id: str | None = None, lesson_id: str | None = None,
                         step_id: str | None = None) -> dict:
    tutorial_run_id = tutorial_run_id or find_reference_run(conn, learner_run_id, lesson_id, step_id)
    if not tutorial_run_id:
        return {"tutorial_run_id": None, "metric": metric, "points": [], "latest": None,
                "summary": "no tutorial reference curve for this lesson"}
    rows = conn.execute(SQL_PATH.read_text(encoding="utf-8"), {"learner": learner_run_id, "tutorial": tutorial_run_id,
                                               "metric": metric}).fetchall()
    points = [{"step": r[1], "learner": r[2], "tutorial": r[3], "tutorial_step": r[4],
               "gap_decades": float(r[5]) if r[5] is not None else None} for r in rows]
    paired = [p for p in points if p["gap_decades"] is not None]
    latest = paired[-1] if paired else None
    if latest is None:
        summary = f"no overlapping {metric} steps with the tutorial yet"
    else:
        ratio = 10 ** latest["gap_decades"]
        if abs(latest["gap_decades"]) < 0.15:
            rel = "on track with"
        elif ratio > 1:
            rel = f"{ratio:.1f}x higher than"
        else:
            rel = f"{1 / ratio:.1f}x lower than"
        summary = f"at step {latest['step']} your {metric} {latest['learner']:.3g} is {rel} the tutorial's ({latest['tutorial']:.3g})"
    return {"tutorial_run_id": tutorial_run_id, "metric": metric, "points": points, "latest": latest, "summary": summary}

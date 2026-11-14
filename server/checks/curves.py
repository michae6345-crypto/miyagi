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

FIND_REFERENCE_SQL = """
SELECT r.id FROM runs r
LEFT JOIN runs l ON l.id = %(learner)s
WHERE r.source = 'tutorial'
ORDER BY (r.lesson_id IS NOT DISTINCT FROM l.lesson_id AND r.step_id IS NOT DISTINCT FROM l.step_id) DESC,
         (r.lesson_id IS NOT DISTINCT FROM l.lesson_id) DESC,
         r.started_at DESC NULLS LAST
LIMIT 1
"""


def find_reference_run(conn: Any, learner_run_id: str) -> str | None:
    row = conn.execute(FIND_REFERENCE_SQL, {"learner": learner_run_id}).fetchone()
    return row[0] if row else None


def compare_to_reference(conn: Any, learner_run_id: str, metric: str = "loss",
                         tutorial_run_id: str | None = None) -> dict:
    tutorial_run_id = tutorial_run_id or find_reference_run(conn, learner_run_id)
    if not tutorial_run_id:
        return {"tutorial_run_id": None, "metric": metric, "points": [], "latest": None,
                "summary": "no tutorial reference curve loaded"}
    rows = conn.execute(SQL_PATH.read_text(), {"learner": learner_run_id, "tutorial": tutorial_run_id,
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

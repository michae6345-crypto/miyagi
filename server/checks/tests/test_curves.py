"""find_reference_run must never hand back another lesson's tutorial curve."""
from server.checks.curves import compare_to_reference, find_reference_run

RUNS = [  # id, lesson_id, step_id, source, started_at (ISO, sortable)
    ("ref_other", "react-hooks", "s5", "tutorial", "2026-11-14T20:00"),  # newest, but another lesson
    ("ref_pinn_s4", "pinn", "s4", "tutorial", "2026-11-14T18:00"),
    ("ref_pinn_s5", "pinn", "s5", "tutorial", "2026-11-14T17:00"),
    ("run_l1", "pinn", "s5", "learner", "2026-11-14T21:00"),
    ("run_nolesson", None, None, "learner", "2026-11-14T21:00"),
    ("run_blender", "blender", "s1", "learner", "2026-11-14T21:00"),
]


class R:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class FakeRuns:
    """Evaluates the two queries curves.py issues against RUNS in Python."""

    def execute(self, sql, params=None):
        if "WHERE id = %s" in sql:
            return R([(r[1], r[2]) for r in RUNS if r[0] == params[0]])
        if "source = 'tutorial'" in sql:
            cands = [r for r in RUNS if r[3] == "tutorial" and r[1] == params["lesson"]]
            cands.sort(key=lambda r: (r[2] == params["step"], r[4]), reverse=True)
            return R([(c[0],) for c in cands[:1]])
        return R([])


def test_same_lesson_same_step_preferred():
    assert find_reference_run(FakeRuns(), "run_l1") == "ref_pinn_s5"


def test_never_another_lessons_curve():
    assert find_reference_run(FakeRuns(), "run_nolesson") is None
    assert find_reference_run(FakeRuns(), "run_blender") is None
    assert find_reference_run(FakeRuns(), "run_unknown") is None


def test_screen_runs_and_explicit_lesson():
    assert find_reference_run(FakeRuns(), "screen-pinn") == "ref_pinn_s4"  # newest of the lesson
    assert find_reference_run(FakeRuns(), "screen-pinn", step_id="s5") == "ref_pinn_s5"
    assert find_reference_run(FakeRuns(), "anything", lesson_id="pinn", step_id="s4") == "ref_pinn_s4"
    res = compare_to_reference(FakeRuns(), "run_nolesson")
    assert res["tutorial_run_id"] is None and "no tutorial reference" in res["summary"]

"""The ambient help card stops watching while a lesson holds the screen (main.lesson_holds_screen), but not on a
finished lesson's completion screen (phase "done", graph still held): there a card asked keeps advancing on its own."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from server.orchestrator.main import lesson_holds_screen


@pytest.mark.parametrize(("graph", "phase", "holds"), [
    (None, "idle", False),
    (None, "searching", True),
    (None, "building", True),
    ({"lesson": {}}, "building", True),
    ({"lesson": {}}, "preflight", True),
    ({"lesson": {}}, "active", True),
    ({"lesson": {}}, "done", False),
    ({"lesson": {}}, "idle", True),  # a lesson restored but not started yet still holds the screen
])
def test_lesson_holds_screen(graph, phase, holds):
    assert lesson_holds_screen(SimpleNamespace(graph=graph, phase=phase)) is holds

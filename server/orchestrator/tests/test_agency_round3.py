"""eng-agency leftovers in the session (offline: no model, no process; `open` and pbcopy are mocked)."""
from __future__ import annotations

import threading

from server.orchestrator.tests.test_agency import _WS, _rig_with
from server.orchestrator.tests.test_session import _text_lesson, run
from server.safety import regex_worker


def test_a_command_with_a_hidden_character_is_never_copied(tmp_path, monkeypatch):
    rig, _ = _rig_with(tmp_path, monkeypatch, _text_lesson())
    copied = []

    async def clip(text):
        copied.append(text)
        return True

    monkeypatch.setattr(type(rig.s), "_clipboard", staticmethod(clip))

    async def go():
        await rig.s.learn("calc", mode="lesson")
        await rig.settle()
        # a zero-width space and a right-to-left override: the card would read one command, the paste run another
        rig.s.last_offtrack = {"title": "x", "body": "y", "diff": {"command": "pip install num\u200bpy \u202eevil"}}
        await rig.s._apply_fix(rig.s.step)

    run(go())
    assert copied == []
    card = [c for c in rig.of("card") if c["title"] == "Check this command"][-1]
    assert card["output"] == "pip install num<U+200B>py <U+202E>evil" and "U+200B" in card["body"]


def test_a_plain_multi_line_command_is_still_copied_as_shown(tmp_path, monkeypatch):
    rig, _ = _rig_with(tmp_path, monkeypatch, _text_lesson())
    copied = []

    async def clip(text):
        copied.append(text)
        return True

    monkeypatch.setattr(type(rig.s), "_clipboard", staticmethod(clip))

    async def go():
        await rig.s.learn("calc", mode="lesson")
        await rig.settle()
        rig.s.last_offtrack = {"title": "x", "body": "y", "diff": {"command": "cd calc\npython3 calc.py"}}
        await rig.s._apply_fix(rig.s.step)

    run(go())
    card = [c for c in rig.of("card") if c["title"] == "Command copied"][-1]
    assert copied == ["cd calc\npython3 calc.py"] == [card["output"]]


def test_an_unknown_link_card_writes_out_hidden_characters(tmp_path, monkeypatch):
    rig, _ = _rig_with(tmp_path, monkeypatch, _text_lesson())
    ws = _WS()

    async def go():
        await rig.s.learn("calc", mode="lesson")
        await rig.settle()
        rig.s.workspace = ws
        rig.s.reqs = [{"tool": "evil", "label": "Evil", "install": {"url": "https://evil.example/\u202egol"}}]
        await rig.s.action("open_in_browser", "evil")

    run(go())
    assert ws.opened == []
    shown = [c for c in rig.of("card") if c["title"] == "From the tutorial: check it before opening"]
    assert shown and shown[-1]["output"] == "https://evil.example/<U+202E>gol"


def test_checks_are_graded_off_the_event_loop_with_the_lessons_regex_budget(tmp_path, monkeypatch):
    rig, _ = _rig_with(tmp_path, monkeypatch, _text_lesson())
    seen = []
    real = rig.s.m.evaluate_gate

    def gate(step, ctx, screen=None, precision_mode=False):
        seen.append((threading.current_thread() is threading.main_thread(), regex_worker._CURRENT.get(),
                     ctx.runs is rig.s.step_runs))
        return real(step, ctx, screen, precision_mode)

    monkeypatch.setattr(rig.s.m, "evaluate_gate", gate)

    async def go():
        await rig.s.learn("calc", mode="lesson")
        await rig.settle()
        await rig.s.evaluate("check")
        await rig.settle()

    run(go())
    assert seen
    on_loop, budget, live = seen[-1]
    assert not on_loop and budget is not None and budget.key == rig.s._regex_key() and not live

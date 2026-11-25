"""Blender lessons are told how to check the scene dump, and lint accepts those checks (Nov 24). Offline: the prompt
text is built, no model is called."""

from __future__ import annotations

from server.lesson import app_lesson, claude, gemini, schema

STEP = {"id": "s3", "index": 1, "title": "Add subdivision surface", "file": "mug.blend",
        "instructions": "Add a Subdivision Surface modifier and shade smooth.",
        "checks": [{"id": "s3c1", "type": "file_contains", "label": "Subsurf added", "file": "mug.scene.json",
                    "pattern": r'"type":\s*"SUBSURF"'},
                   {"id": "s3c2", "type": "file_contains", "label": "Level 2", "file": "mug.scene.json",
                    "pattern": r'"levels":\s*2\b'}],
        "hints": ["Ctrl+2"]}


def test_step_head_for_a_blender_lesson_holds_the_scene_block():
    head = claude.step_head("model a mug", "Intro to Blender: the mug", "1. Mug")
    assert app_lesson.SCENE_GUIDE in head and ".scene.json" in head


def test_step_head_for_other_lessons_is_unchanged():
    head = claude.step_head("learn pandas", "Python pandas basics", "1. Load")
    assert head == claude.STEP_HEAD.format(goal="learn pandas", lesson="Python pandas basics", outline="1. Load",
                                           stack_guide=gemini.STACK_GUIDE)
    assert ".scene.json" not in head


def _graph(step: dict) -> dict:
    return {"lesson": {"title": "Intro to Blender"}, "steps": [step]}


def test_lint_accepts_scene_dump_checks_in_checks():
    problems = schema.lint(_graph(STEP), known_files={"mug.blend"})
    assert problems == [], problems


def test_lint_still_flags_code_file_checks_in_checks():
    step = {**STEP, "checks": [{"id": "s3c1", "type": "file_contains", "label": "Code", "file": "app.py",
                                "pattern": "def main"}]}
    problems = schema.lint(_graph(step))
    assert any("type 'file_contains' not allowed in `checks`" in p for p in problems), problems


def test_scene_dump_is_creatable():
    assert schema._creatable("mug.scene.json") and not schema._creatable("sub/mug.scene.json")
    assert not schema._creatable("settings.json")
    assert schema.is_scene_check(STEP["checks"][0])
    assert not schema.is_scene_check({"type": "file_exists", "file": "mug.scene.json"})

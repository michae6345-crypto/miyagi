"""Blender lessons are told how to check the scene dump, and lint accepts those checks (Nov 24). Offline: the prompt
text is built, no model is called."""

from __future__ import annotations

import asyncio

from server.lesson import app_lesson, builder, claude, gemini, schema
from server.lesson.workdir import WorkdirInfo

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


def test_scene_guide_puts_scene_checks_in_checks():
    assert "NOT precision_checks" in app_lesson.SCENE_GUIDE


# --- the build keeps scene checks gating (repair, assemble, the adapt prompt) ---------------------------------------

def test_repair_keeps_scene_checks_in_checks():
    g = builder.repair(_graph(dict(STEP, precision_checks=[])), WorkdirInfo(root="/x", exists=False))
    st = g["steps"][0]
    assert [c["file"] for c in st["checks"]] == ["mug.scene.json", "mug.scene.json"]
    assert [c["pattern"] for c in st["checks"]] == [c["pattern"] for c in STEP["checks"]]
    assert st["precision_checks"] == []


def test_repair_still_moves_other_file_checks_to_precision():
    code = {"id": "s3c3", "type": "file_contains", "label": "Main", "file": "app.py", "pattern": "def main"}
    g = builder.repair(_graph(dict(STEP, checks=STEP["checks"] + [code], precision_checks=[])),
                       WorkdirInfo(root="/x", exists=False))
    st = g["steps"][0]
    assert [c["file"] for c in st["checks"]] == ["mug.scene.json", "mug.scene.json"]
    assert [c["file"] for c in st["precision_checks"]] == ["app.py"]


def _draft() -> dict:
    return {"title": "Blender mug", "files": ["mug.blend"],
            "steps": [{"index": 1, "start": 0, "end": 60, "title": "Add subdivision", "instructions": "Add it.",
                       "file": "mug.blend",
                       "checks": STEP["checks"] + [{"type": "screen_contains", "label": "Panel open", "app": "Blender",
                                                     "pattern": "Subdivision"},
                                                    {"type": "file_exists", "label": "Saved", "file": "mug.blend"}]}]}


def test_assemble_without_adapt_keeps_draft_scene_checks_gating():
    st = builder.assemble(_draft(), "model a mug", {"steps": []})["steps"][0]
    assert [c["type"] for c in st["checks"]] == ["file_contains", "file_contains", "screen_contains"]
    assert [c.get("file") for c in st["checks"][:2]] == ["mug.scene.json", "mug.scene.json"]
    assert [(c["type"], c.get("file")) for c in st["precision_checks"]] == [("file_exists", "mug.blend")]


def _base_prompt(monkeypatch):
    # gemini.adapt_prompt wraps the workdir in a block with a random id: a fixed stand-in keeps the comparison exact
    monkeypatch.setattr(gemini, "adapt_prompt", lambda goal, steps, summary, feedback=None: f"BASE {goal}")


def test_adapt_prompt_for_a_blender_lesson_keeps_scene_checks_in_checks(monkeypatch):
    _base_prompt(monkeypatch)
    prompt = claude.adapt_prompt("model a mug", _draft()["steps"], "empty")
    assert prompt == "BASE model a mug\n" + claude.ADAPT_SCENE_RULE + app_lesson.SCENE_GUIDE
    # the goal alone (no Blender step yet) is enough too
    assert claude.ADAPT_SCENE_RULE in claude.adapt_prompt("Learn Blender: the donut", [{"index": 1}], "empty")


def test_adapt_prompt_for_other_lessons_is_unchanged(monkeypatch):
    _base_prompt(monkeypatch)
    steps = [{"index": 1, "title": "Load", "file": "app.py",
              "checks": [{"type": "screen_contains", "app": "Code", "pattern": "read_csv"}]}]
    assert claude.adapt_prompt("learn pandas", steps, "empty") == "BASE learn pandas"


def test_adapt_checks_sends_the_scene_block_offline(monkeypatch):
    seen = {}

    async def fake_generate(system, prompt, schema, **kw):
        seen.update(system=system, prompt=prompt)
        return {"steps": []}

    monkeypatch.setattr(claude, "_generate_json", fake_generate)
    asyncio.run(claude.adapt_checks("model a mug", _draft()["steps"], "empty"))
    assert seen["system"] == gemini.ADAPT_SYSTEM  # the cached system prompt is untouched
    assert claude.ADAPT_SCENE_RULE in seen["prompt"]


def test_scene_lesson_reads_the_title_or_the_steps():
    assert app_lesson.scene_lesson("Beginner Blender 4.0 Tutorial")
    assert app_lesson.scene_lesson("make a mug", [{"file": "mug.blend"}])
    assert app_lesson.scene_lesson("make a mug", [{"targets": [{"app": "Blender", "match": "Add"}]}])
    assert app_lesson.scene_lesson("make a mug", [{"checks": [{"type": "file_contains", "file": "mug.scene.json"}]}])
    assert not app_lesson.scene_lesson("Python pandas basics", [{"file": "app.py"}, "junk"])

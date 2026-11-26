"""App-based (no-code) lessons talk about the app and check the app (Nov 22, Michael's AutoCAD lesson: the drawer said
"Watch 0:00-5:00 and type along in your editor" for a lesson done entirely in AutoCAD)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from server.lesson import app_lesson, builder

FIX = Path(__file__).resolve().parents[2] / "workspace" / "tests" / "fixtures"


def autocad() -> dict:
    return json.loads((FIX / "autocad_toy_car.json").read_text(encoding="utf-8"))


def test_autocad_steps_talk_about_autocad_and_check_the_app_not_files():
    g = app_lesson.adapt(autocad())
    assert g["lesson"]["app"] == {"tool": "autocad", "label": "AutoCAD"}
    s1, s2, s3 = g["steps"]
    assert s1["instructions"] == "Follow along in AutoCAD: draw the side profile of the car with LINE and ARC."
    assert s2["title"] == "Extrude the body in AutoCAD" and s2["instructions"].startswith("In AutoCAD, extrude")
    text = json.dumps(g["steps"]).lower()
    assert "editor" not in text and "vs code" not in text
    types = [c["type"] for s in g["steps"] for c in s["checks"]]
    assert types == ["screen_contains", "screen_contains", "screen_contains"]  # file / command checks gone
    assert all(c["app"] == "AutoCAD" for s in g["steps"] for c in s["checks"])
    assert s1["targets"][0]["app"] == "AutoCAD"


def test_normalize_checks_adapts_app_lessons():
    g = builder.normalize_checks(autocad(), set())
    assert g["lesson"]["app"]["tool"] == "autocad" and not any(c["type"] == "file_exists" for c in g["steps"][0]["checks"])


def test_code_lessons_are_never_touched_even_when_the_title_names_an_app():
    g = autocad()
    g["lesson"]["title"] = g["sources"][0]["title"] = "Read Excel files with pandas"
    g["steps"][0]["file"] = "read_excel.py"
    before = copy.deepcopy(g)
    assert app_lesson.adapt(g) == before
    plain = autocad()
    plain["lesson"]["title"] = plain["sources"][0]["title"] = "Build a calculator"
    assert app_lesson.adapt(copy.deepcopy(plain)) == plain


def test_web_app_lessons_keep_checks_unpinned():
    g = autocad()
    g["lesson"]["title"] = g["sources"][0]["title"] = "Tinkercad toy car for 3D printing"
    g = app_lesson.adapt(g)
    assert g["lesson"]["app"]["tool"] == "tinkercad" and g["steps"][0]["instructions"].startswith("Follow along in Tinkercad")
    assert "app" not in g["steps"][2]["checks"][0]  # any browser


CHAPTERS = [{"t": 0, "title": "Intro"}, {"t": 30, "title": "Car profile"}, {"t": 300, "title": "Wheels"}]


def test_placeholder_step_follows_along_in_the_app():
    g = builder.provisional_graph({"title": "AutoCAD - Toy Car Creation for 3D Printer", "length_s": 1056, "chapters": CHAPTERS},
                                  "AcadToyCar1", "https://www.youtube.com/watch?v=AcadToyCar1", "toy car", "/tmp/w")
    s1 = g["steps"][0]
    assert s1["instructions"] == "Watch 0:30-5:00 (Car profile) and follow along in AutoCAD; detailed steps are on the way."
    assert "editor" not in s1["instructions"]


def test_placeholder_step_wording_by_style():
    meta = {"title": "Design thinking basics", "length_s": 600, "chapters": CHAPTERS}
    no_code = builder.provisional_graph({**meta, "style": "no-code"}, "x" * 11, "https://youtu.be/xxxxxxxxxxx", "", "/tmp/w")
    assert no_code["steps"][0]["instructions"].endswith(" and follow along; detailed steps are on the way.")
    coding = builder.provisional_graph({**meta, "title": "Python calculator"}, "x" * 11, "https://youtu.be/xxxxxxxxxxx", "", "/tmp/w")
    assert coding["steps"][0]["instructions"].endswith("type along in your editor; detailed steps are on the way.")
    assert builder.normalize_video_meta({"title": "t", "style": "no-code"})["style"] == "no-code"


def test_repin_moves_app_checks_and_copy_and_is_idempotent():
    g = app_lesson.adapt(autocad())
    assert app_lesson.repin(g, "autocad", "FreeCAD", "FreeCAD") is True
    assert all(x["app"] == "FreeCAD" for s in g["steps"] for x in s["checks"] + s["targets"])
    assert g["steps"][1]["title"] == "Extrude the body in FreeCAD"
    assert g["steps"][1]["instructions"].startswith("In FreeCAD, extrude")
    assert app_lesson.repin(g, "autocad", "FreeCAD", "FreeCAD") is False
    web = app_lesson.adapt(autocad())
    assert app_lesson.repin(web, "autocad", None, "Tinkercad") is True
    assert not any("app" in x for s in web["steps"] for x in s["checks"] + s["targets"])
    assert web["steps"][0]["instructions"].startswith("Follow along in Tinkercad")


def test_repin_never_touches_a_code_lesson():
    g = autocad()
    g["steps"][0]["file"] = "car.py"
    before = copy.deepcopy(g)
    assert app_lesson.repin(g, "autocad", "FreeCAD", "FreeCAD") is False and g == before


def test_alternative_window():
    assert app_lesson.alternative_window("freecad") == "FreeCAD"
    assert app_lesson.alternative_window("blender") == "Blender"
    assert app_lesson.alternative_window("tinkercad") is None and app_lesson.alternative_window("google-sheets") is None


def test_placeholder_step_of_a_coding_video_about_an_app_types_along_in_the_editor():
    """Fix round 1: "Automate Excel with Python openpyxl" is a code lesson: never "follow along in Microsoft Excel"."""
    meta = {"title": "Automate Excel with Python openpyxl", "length_s": 600, "chapters": CHAPTERS}
    for m in ({**meta, "style": "coding"}, meta):
        s1 = builder.provisional_graph(m, "x" * 11, "https://youtu.be/xxxxxxxxxxx", "", "/tmp/w")["steps"][0]
        assert s1["instructions"].endswith("type along in your editor; detailed steps are on the way."), m
    excel = builder.provisional_graph({**meta, "title": "Excel pivot tables for beginners", "style": "no-code"},
                                      "x" * 11, "https://youtu.be/xxxxxxxxxxx", "", "/tmp/w")["steps"][0]
    assert "follow along in" in excel["instructions"] and "Excel" in excel["instructions"]


def _code_app_lesson(title: str, file: str, needle: str) -> dict:
    return {"lesson": {"title": title}, "sources": [{"title": title}],
            "steps": [{"id": "s1", "title": "Write the sketch", "instructions": "Type along in your editor.", "file": file,
                       "checks": [{"type": "file_exists", "file": file}, {"type": "file_contains", "file": file, "needle": needle}]}]}


def test_code_like_app_lessons_keep_their_file_checks():
    # review of the smart-setup merge: Arduino / Godot / OpenSCAD lessons lost every gating check and read "in Arduino IDE"
    for title, file, needle in [("Arduino Blink LED for beginners", "Blink.ino", "digitalWrite"),
                                ("Godot 4 platformer", "player.gd", "move_and_slide"),
                                ("OpenSCAD parametric box", "box.scad", "cube(")]:
        g = _code_app_lesson(title, file, needle)
        before = copy.deepcopy(g)
        assert app_lesson.has_code(g), title
        assert app_lesson.adapt(g) == before, title  # checks kept, copy untouched, no lesson.app


def test_a_text_file_a_check_reads_is_never_stripped():
    g = _code_app_lesson("Blender donut tutorial", "notes.txt", "donut")  # .txt is no code file, but a check reads it
    before = copy.deepcopy(g)
    assert app_lesson.adapt(g) == before
    g = autocad()  # a check reading the app's own drawing doesn't make AutoCAD a code lesson
    g["steps"][0]["checks"].append({"type": "file_contains", "file": "toy_car.dwg", "needle": "wheel"})
    assert app_lesson.adapt(g)["lesson"]["app"]["tool"] == "autocad"
    assert not any(c["type"].startswith("file_") for s in g["steps"] for c in s["checks"])


# ------------------------------------------------------------------ Blender scene checks (Nov 24)

def blender_donut() -> dict:
    return json.loads((FIX / "blender_donut.json").read_text(encoding="utf-8"))


def _with_scene_checks(g: dict) -> dict:
    """The donut lesson with step 3 graded from the scene dump, plus file / command / output checks to strip."""
    s3 = g["steps"][2]
    s3["file"] = "donut.blend"
    s3["checks"] += [{"id": "s3c2", "type": "file_contains", "label": "Subsurf added", "file": "donut.scene.json",
                      "pattern": r'"type":\s*"SUBSURF"'},
                     {"id": "s3c3", "type": "file_exists", "label": "Dump saved", "file": "donut.scene.json"},
                     {"id": "s3c4", "type": "command_exit_ok", "label": "Runs", "command": "python3 x.py"},
                     {"id": "s3c5", "type": "output_contains", "label": "Prints", "pattern": "done"}]
    s3["precision_checks"] = [{"id": "s3p1", "type": "file_contains", "label": "Demo name", "file": "donut.scene.json",
                               "pattern": r'"name":\s*"Donut"'},
                              {"id": "s3p2", "type": "file_contains", "label": "Blend", "file": "donut.blend",
                               "pattern": "x"}]
    return g


def test_blender_lessons_keep_scene_dump_checks_and_strip_other_file_checks():
    g = app_lesson.adapt(_with_scene_checks(blender_donut()))
    assert g["lesson"]["app"] == {"tool": "blender", "label": "Blender"}
    s3 = g["steps"][2]
    assert [c["id"] for c in s3["checks"]] == ["s3c1", "s3c2"]  # screen + scene dump; file_exists / command / output gone
    assert [c["id"] for c in s3["precision_checks"]] == ["s3p1"]
    assert "app" not in s3["checks"][1]  # a file check is never pinned to a window
    assert all(c["app"] == "Blender" for s in g["steps"] for c in s["checks"] if c["type"] == "screen_contains")


def test_blender_donut_screen_checks_still_get_the_blender_window():
    g = app_lesson.adapt(blender_donut())
    assert g["lesson"]["app"]["tool"] == "blender"
    assert [c["app"] for s in g["steps"] for c in s["checks"]] == ["Blender"] * 4


def test_other_apps_strip_dump_like_checks_as_before():
    g = autocad()
    g["steps"][0]["checks"] += [{"type": "file_contains", "file": "toy_car.dxf", "pattern": "WHEEL"},
                                {"type": "file_contains", "file": "toy_car.scene.json", "pattern": "x"}]
    g = app_lesson.adapt(g)
    assert g["lesson"]["app"]["tool"] == "autocad"
    assert not any(c["type"].startswith("file_") for s in g["steps"] for c in s["checks"])


def test_a_scene_dump_check_is_no_code():
    g = _with_scene_checks(blender_donut())
    for s in g["steps"]:  # only the screen and scene dump checks are left
        s["checks"] = [c for c in s["checks"] if c["type"] in ("screen_contains", "file_contains")]
        s.pop("precision_checks", None)
    assert app_lesson.has_code(g) is False
    py = copy.deepcopy(g)
    py["steps"][0]["file"] = "make_donut.py"
    assert app_lesson.has_code(py) is True
    run = copy.deepcopy(g)
    run["steps"][1]["run_command"] = "python3 make_donut.py"
    assert app_lesson.has_code(run) is True
    js = copy.deepcopy(g)  # a real JSON file the learner edits is still code
    js["steps"][0]["checks"].append({"type": "file_contains", "file": "settings.json", "pattern": "x"})
    assert app_lesson.has_code(js) is True


def test_scene_guide_only_for_blender_titles():
    text = app_lesson.scene_guide("Beginner Blender 4.0 Tutorial")
    assert ".scene.json" in text and r'"type":\s*"SUBSURF"' in text and "screen_contains" in text
    assert "precision_checks" in text and r"BLENDER_EEVEE\w*" in text and "radians" in text
    assert "EEVEE_NEXT" not in text
    # the dump is made only from <stem>.blend in the lesson folder: the first scene step must say to save there
    assert "FIRST step that" in text and "File > Save As" in text and '"<stem>.blend" in the lesson folder' in text
    assert "same name" in text
    assert app_lesson.scene_guide("Python pandas basics") == ""
    assert app_lesson.scene_guide("") == ""

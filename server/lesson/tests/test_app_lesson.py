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

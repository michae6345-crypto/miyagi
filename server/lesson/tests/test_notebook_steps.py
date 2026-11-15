"""server/lesson/notebook_steps.py on the cached TensorFlow lesson (desktop test 10) and small graphs."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from server.lesson.notebook_steps import fix_copy, notebook_name, use_lesson_notebook
from server.lesson.venv_steps import use_lesson_venv

CACHED = Path(__file__).resolve().parents[3] / "demo" / "cache" / "lessons" / "5c0ea8a49f419487.json"


def _cached() -> dict:
    g = json.loads(CACHED.read_text(encoding="utf-8"))
    use_lesson_venv(g)  # what load_graph runs first
    return g


def test_cached_lesson_gets_mnist_notebook_everywhere_and_is_idempotent():
    g = _cached()
    assert use_lesson_notebook(g) == ["s1", "s2", "s3", "s4", "s5", "s6", "s7"]
    assert g["lesson"]["notebook"] == "mnist.ipynb"
    once = copy.deepcopy(g)
    assert use_lesson_notebook(g) == [] and g == once
    assert "Untitled" not in json.dumps(g["steps"])
    s1 = g["steps"][0]
    assert s1["title"] == "Open mnist.ipynb with the .venv kernel" and "run_command" not in s1
    assert [c["id"] for c in s1["checks"]] == ["s1c2", "s1c3"] and [c["id"] for c in s1["precision_checks"]] == ["s1p1"]
    told = {k: v for k, v in s1.items() if k != "explanations"}  # (the video's own topic may name Jupyter Notebook)
    assert "jupyter notebook" not in json.dumps(told).lower()
    assert g["steps"][1]["instructions"].startswith("In mnist.ipynb, import tensorflow")


def test_colab_and_plain_lessons_are_left_alone():
    colab = {"lesson": {"title": "PyTorch in Google Colab"}, "steps": [{"id": "s1", "targets": [{"file": "Untitled0.ipynb"}]}]}
    plain = {"lesson": {"title": "Flask app"}, "steps": [{"id": "s1", "targets": [{"file": "app.py"}]}]}
    for g in (colab, plain):
        before = copy.deepcopy(g)
        assert use_lesson_notebook(g) == [] and g == before


def test_notebook_name_keeps_a_real_name_else_the_topic_else_notebook():
    def g(file, text=""):
        return {"lesson": {"title": text}, "steps": [{"id": "s1", "instructions": text, "targets": [{"file": file}]}]}

    assert notebook_name(g("classifier.ipynb", "mnist")) == "classifier.ipynb"
    assert notebook_name(g("Untitled1.ipynb", "Load tf.keras.datasets.mnist")) == "mnist.ipynb"
    assert notebook_name(g("Untitled.ipynb", "pandas basics in Jupyter")) == "notebook.ipynb"


def test_fix_copy_names_the_notebook_and_vscode():
    assert fix_copy("Open Untitled.ipynb in Jupyter or Colab", "mnist.ipynb") == "Open mnist.ipynb in VS Code"
    assert fix_copy("Open x.ipynb in Colab or Jupyter so I can see it.", "x.ipynb") == "Open x.ipynb in VS Code so I can see it."

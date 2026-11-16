"""Desktop test 10 first-timer review (TensorFlow notebook lesson, demo/cache/lessons/5c0ea8a49f419487.json):
- notebook steps say what to type: "Add a cell with the code below to <notebook>, then press Shift+Enter", and the code
  goes out as the step's snippet in a video lesson too;
- the Tutorial files card is an information card that names its file, offered once, only when the folder lacks it;
- a pass while the clip still plays never jumps the video past what's left of it;
- copy: no "te… …", one style for accuracy labels ("at least 95%"), an accurate README;
- the completion card's proof for a notebook lesson: the notebook's last printed accuracy.
Offline: no API calls, no screen."""

from __future__ import annotations

import copy
import json
import types
from pathlib import Path

from server.orchestrator import lesson_end
from server.orchestrator.session import LessonSession as Session, _metric_labels

ROOT = Path(__file__).resolve().parents[2]
LESSON = ROOT / "demo" / "cache" / "lessons" / "5c0ea8a49f419487.json"


def _graph() -> dict:
    return copy.deepcopy(json.loads(LESSON.read_text()))


def _session(tmp_path: Path, graph: dict | None = None) -> Session:
    s = Session.__new__(Session)  # no engine, no screen: just the step copy helpers
    s.graph = graph or _graph()
    s.workdir = str(tmp_path)
    s.has_python = True
    s.lesson_epoch = 1
    return s


def _step(g: dict, sid: str) -> dict:
    return next(x for x in g["steps"] if x["id"] == sid)


def test_notebook_steps_say_add_a_cell_and_send_the_code(tmp_path):
    g = _graph()
    s = _session(tmp_path, g)
    for sid in ("s2", "s3", "s4", "s6", "s7"):
        st = _step(g, sid)
        line = s._action_line(st)
        assert line == "Add a cell with the code below to Untitled.ipynb, then press Shift+Enter", (sid, line)
        assert s._snippet(st) == {"snippet": st["code"][:1200]}
    s3 = _step(g, "s3")  # no file on the step: the lesson's notebook (claude/t10-flow names it)
    s3 = {**s3, "targets": [], "precision_checks": []}
    g["lesson"]["notebook"] = "mnist.ipynb"
    assert s._action_line(s3) == "Add a cell with the code below to mnist.ipynb, then press Shift+Enter"
    # renamed (t10-flow: every Untitled.ipynb -> mnist.ipynb)
    s4 = json.loads(json.dumps(_step(g, "s4")).replace("Untitled.ipynb", "mnist.ipynb"))
    assert s._action_line(s4) == "Add a cell with the code below to mnist.ipynb, then press Shift+Enter"
    # s1 is a shell step: still a run line, no snippet
    s1 = _step(g, "s1")
    assert "Add a cell" not in s._action_line(s1)
    assert s._snippet(s1) == {}


def test_no_double_ellipsis(tmp_path):
    s = _session(tmp_path)
    (tmp_path / "app.py").write_text("")
    st = {"id": "x", "title": "t", "instructions": "type it", "file": "app.py",
          "code": "test_loss, test_accuracy = model.evaluate(test_images, test_labels)\nprint(test_accuracy)"}
    line = s._action_line(st)
    assert "… …" not in line and line.endswith("… in app.py"), line


def test_accuracy_labels_one_style():
    g = _graph()
    _metric_labels(g)
    labels = [c["label"] for st in g["steps"] for c in st.get("checks") or [] if c.get("type") == "metric_threshold"]
    assert "Training accuracy at least 95%" in labels and "Test accuracy at least 95%" in labels, labels
    _metric_labels(g)  # idempotent
    assert [c["label"] for st in g["steps"] for c in st.get("checks") or []
            if c.get("type") == "metric_threshold"] == labels


def test_tutorial_files_card(tmp_path):
    s = _session(tmp_path)
    found = [{"name": "mnist.ipynb", "url": "https://github.com/kiecodes/mnist/blob/main/mnist.ipynb", "kind": "notebook"}]
    card = s._tutorial_files_card(found, str(tmp_path))
    assert card["kind"] != "hint" and card["dismissAfterMs"] <= 10000 and card["actions"] == ["download"]
    assert "mnist.ipynb" in card["body"] and "github.com/kiecodes/mnist" in card["body"], card["body"]
    assert "file(s)" not in card["body"] and card["setup"]["resources"][0]["name"] == "mnist.ipynb"
    assert s._tutorial_files_card(found, str(tmp_path)) is None  # once per lesson
    s.lesson_epoch = 2
    (tmp_path / "tutorial").mkdir()
    (tmp_path / "tutorial" / "mnist.ipynb").write_text("{}")
    assert s._tutorial_files_card(found, str(tmp_path)) is None  # already in tutorial/
    two = found + [{"name": "data.csv", "url": "https://example.com/data.csv", "kind": "file"}]
    s.lesson_epoch = 3
    card = s._tutorial_files_card(two, str(tmp_path))
    assert card["body"].startswith("The video links a file, data.csv"), card["body"]
    (tmp_path / "tutorial" / "mnist.ipynb").unlink()
    s.lesson_epoch = 4
    assert "2 files" in s._tutorial_files_card(two, str(tmp_path))["body"]


def test_clip_plays_on_into_next_segment(tmp_path):
    g = _graph()
    s = _session(tmp_path, g)
    s.idx, s.phase, s.segment_done = 3, "active", False  # s4 (151-251 s) passed at 3:03 while its clip plays
    now = [1000.0]
    s.clock = lambda: now[0]
    s.video_t = None
    s._play_at = (183.0, 1000.0)
    assert s._clip_runs_into(4) == 183.0
    now[0] = 1010.0
    assert s._clip_runs_into(4) == 193.0
    s._play_at = None  # paused: the next step starts at its own segment as before
    assert s._clip_runs_into(4) is None
    s._play_at = (183.0, 1000.0)
    s.segment_done = True  # the clip already ended
    assert s._clip_runs_into(4) is None


def test_readme_after_normalisation(tmp_path):
    from server.workspace import core

    folder = tmp_path / "lesson"
    folder.mkdir()
    (folder / ".venv").mkdir()
    (folder / "tutorial").mkdir()
    (folder / ".miyagi").mkdir(exist_ok=True)
    core._state_file(folder).parent.mkdir(parents=True, exist_ok=True)
    core._state_file(folder).write_text(json.dumps({"scaffolded": True, "lesson_kind": "code", "files": []}))
    g = _graph()
    g["steps"][0]["title"] = "Open mnist.ipynb with the .venv kernel"
    assert core.refresh_readme(folder, g)
    text = (folder / "README.md").read_text()
    assert "Open mnist.ipynb with the .venv kernel" in text and "Create venv and start Jupyter" not in text
    assert "starts empty" not in text and "`.venv/`" in text and "`tutorial/`" in text


def test_completion_card_reads_notebook_accuracy(tmp_path):
    nb = {"cells": [
        {"cell_type": "code", "source": ["model.fit(x)"], "execution_count": 1,
         "outputs": [{"output_type": "stream", "name": "stdout", "text": ["Epoch 5/5 - accuracy: 0.9880 - loss: 0.04\n"]}]},
        {"cell_type": "code", "source": ["print(acc)"], "execution_count": 2,
         "outputs": [{"output_type": "stream", "name": "stdout",
                      "text": ["313/313 - accuracy: 0.9759 - loss: 0.0811\n",
                               "Accuracy of the neural network on the 10000 test images: 97.59%\n"]}]}],
        "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    (tmp_path / "Untitled.ipynb").write_text(json.dumps(nb))
    g = _graph()
    s = types.SimpleNamespace(graph=g, steps=g["steps"], workdir=str(tmp_path), runs={}, notebook_lesson=True)
    assert lesson_end.notebook_line(s) == "Test accuracy 97.59% in your notebook."
    assert lesson_end.evidence(s) == "Test accuracy 97.59% in your notebook."

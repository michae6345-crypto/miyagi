"""Desktop test 9 ("Watch a video", Nov 15 06:12-06:19), V5 copy bugs, on the cached lesson the demo replays
(demo/cache/lessons/5c0ea8a49f419487.json, copied to fixtures/t9_mnist_video_lesson.json):

  - the step line read "Run Run the cell (Shift+Enter) in the VS Code terminal" (the build's run_command is the action
    in words, and a notebook cell doesn't run in the terminal);
  - the preflight card read "Kie Codes Codes and trains a…" with no final period (the app runs body lines together);
  - the preflight line said "No captions" (finder: no CC badge) although the build used a 181-line transcript.
Run from the repo root:  python -m pytest server/orchestrator/tests/test_t9_copy.py -q"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from server.finder import core as finder_core
from server.finder import youtube
from server.orchestrator.tests.test_session import rig  # noqa: F401 (fixture)
from server.preflight import core as pf
from server.preflight.meta import parse_watch_page

LESSON = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "t9_mnist_video_lesson.json").read_text())
STEPS = {s["id"]: s for s in LESSON["steps"]}


def test_cached_notebook_step_line_has_one_verb_and_no_terminal(rig):  # noqa: F811
    s = rig.s
    assert STEPS["s2"]["run_command"] == "Run the cell (Shift+Enter)"  # the cached lesson, as the demo replays it
    for sid in ("s2", "s3", "s4"):
        p = s._step_started_payload(STEPS[sid])
        # t10: the step says what to type (its code shows under the line), never only "Run the cell"
        assert re.fullmatch(r"Add a cell with the code below to [\w.-]+\.ipynb, then press Shift\+Enter",
                            p["instructions"]), (sid, p["instructions"])
        assert "Run Run" not in p["instructions"] and "terminal" not in p["instructions"]
        assert p["code"] == STEPS[sid]["code"].strip()  # the code to type, not "Run the cell (Shift+Enter)"
    # a .ipynb step whose run_command is words without Shift+Enter: still the notebook, still one verb
    nb = {"id": "x", "title": "Run it", "instructions": "Run the cell.", "run_command": "run the cell",
          "targets": [{"app": "Code", "file": "mnist.ipynb", "match": "x"}]}
    assert s._action_line(nb) == "Run the cell in the notebook"


def test_shell_run_lines_unchanged_and_never_doubled(rig):  # noqa: F811
    s = rig.s
    step = {"id": "s7", "title": "Run it", "file": "calculator.py", "code": "python calculator.py\n",
            "targets": [{"file": "calculator.py", "match": "calculator"}]}
    assert s._action_line(step) == "Run python calculator.py in the VS Code terminal"
    words = {"id": "s8", "title": "Run it", "instructions": "Run it.", "run_command": "Run python3 app.py"}
    assert s._action_line(words) == "Run python3 app.py in the VS Code terminal"
    line = s._action_line(STEPS["s1"])  # step 1's real shell command still runs in the terminal
    assert line.startswith("Run python3 -m venv venv && ") and line.endswith(" in the VS Code terminal")


def _t9_preflight_result() -> dict:
    return {"videoId": "VPlFpvLOgtQ", "url": youtube.watch_url("VPlFpvLOgtQ"),
            "title": "Code your first Neural Network with TensorFlow", "channel": "Kie Codes", "style": "coding",
            "durationS": 520, "chapters": [{"start": i * 60, "title": f"c{i}"} for i in range(7)],
            "topic": "Codes and trains a handwritten-digit MNIST neural network classifier in TensorFlow",
            "goalMatch": {"score": 0.93, "note": "Builds a real neural network you can train and test, though only a "
                                                 "basic MNIST digit classifier"},
            "buildPlan": {"strategy": "whole", "cached": True, "estSecondsToFirstSteps": 0},
            "cachedLesson": {"file": "5c0ea8a49f419487.json", "steps": 7, "workdir": "/tmp/x"}, "requirements": []}


def test_preflight_summary_no_doubled_channel_and_ends_with_period():
    body = pf.preflight_card(_t9_preflight_result())["body"]
    shown = " ".join(body.split("\n"))  # how the app shows it: the lines run together
    assert "Kie Codes Codes" not in shown
    assert shown == ("Kie Codes codes and trains a handwritten-digit MNIST neural network "
                     "classifier in TensorFlow. Builds a real neural network you can train and test, though only a "
                     "basic MNIST digit classifier. Built before: ready instantly (7 steps).")
    other = pf.preflight_card({**_t9_preflight_result(), "channel": "Andrej Karpathy"})["body"]
    assert other.startswith("Codes and trains a handwritten-digit MNIST "  # t10: no meta line (the app draws it)
                            "neural network classifier in TensorFlow.\n")


def _search_data(badges: list[str]) -> dict:
    return {"contents": [{"videoRenderer": {
        "videoId": "VPlFpvLOgtQ", "title": {"runs": [{"text": "Code your first Neural Network with TensorFlow"}]},
        "lengthText": {"simpleText": "8:40"}, "ownerText": {"runs": [{"text": "Kie Codes"}]},
        "badges": [{"metadataBadgeRenderer": {"label": b}} for b in badges]}}]}


def test_captions_never_no_from_a_missing_badge_and_true_when_known(tmp_path, monkeypatch):
    # finder: no CC badge is "unknown" (auto captions carry none): the public row has no captions field, so the
    # app shows no "No captions"; a CC badge still says Captions
    row = youtube.parse_search(_search_data([]))[0]
    assert row["captions"] is None and "captions" not in finder_core.public({**row, "id": "yt-VPlFpvLOgtQ"})
    assert youtube.parse_search(_search_data(["CC"]))[0]["captions"] is True
    # the watch page lists caption tracks (auto captions too)
    assert parse_watch_page('{"lengthSeconds":"520","captionTracks":[{"baseUrl":"x"}]}')["captions"] is True
    assert "captions" not in parse_watch_page('{"lengthSeconds":"520"}')
    # the transcript the build used (181 lines) is cached: preflight knows the video has captions
    from server.lesson import transcript

    cache = tmp_path / "VPlFpvLOgtQ.json"
    cache.write_text(json.dumps({"video_id": "VPlFpvLOgtQ", "transcript": [{"start": i, "text": "x"} for i in range(181)]}))
    monkeypatch.setattr(transcript, "_cache_path", lambda vid: cache if vid == "VPlFpvLOgtQ" else tmp_path / "none.json")
    assert pf._transcript_cached("VPlFpvLOgtQ") and not pf._transcript_cached("other")


def test_preflight_resends_the_picked_row_with_what_it_knows(rig):  # noqa: F811
    s = rig.s
    row = {"id": "yt-VPlFpvLOgtQ", "kind": "video", "title": "Code your first Neural Network with TensorFlow", "score": 80.0,
           "meta": "YouTube · Kie Codes · 8:40 · chapters: 7", "reason": "Codes a first neural network in TensorFlow",
           "url": youtube.watch_url("VPlFpvLOgtQ"), "videoId": "VPlFpvLOgtQ", "captions": False}

    async def go():
        s.results = {row["id"]: dict(row)}
        mark = rig.mark()
        await s._sync_row_captions({"videoId": "VPlFpvLOgtQ", "captions": True})
        assert [e["payload"].get("captions") for e in rig.since(mark) if e["type"] == "search.result"] == [True]
        s.results = {row["id"]: dict(row)}
        mark = rig.mark()
        await s._sync_row_captions({"videoId": "VPlFpvLOgtQ"})  # unknown: drop the false "No captions"
        sent = [e["payload"] for e in rig.since(mark) if e["type"] == "search.result"]
        assert len(sent) == 1 and "captions" not in sent[0] and sent[0]["id"] == row["id"]
        mark = rig.mark()
        await s._sync_row_captions({"videoId": "VPlFpvLOgtQ"})  # nothing changed: nothing re-sent
        assert not [e for e in rig.since(mark) if e["type"] == "search.result"]

    asyncio.run(go())

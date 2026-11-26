"""Desktop test 9 (video lesson "Code your first Neural Network with TensorFlow", s3), V9:

(a) the coach boxed `fig, axes = plt.subplots(1, 10, figsize=(10, 10))` as "Assign fig, axes here": a caption that only
    restates the code already on the boxed line becomes the read-only pointer "Look here".
(b) the box stayed on the old y when the notebook's output appeared above it and pushed the code down: the off-track box
    was never followed (the step's own target was re-located and refused under it: "no step box …: the offtrack box is
    up"), and a still screen inside the 2 s gap was never re-measured. Now the off-track box follows its own line, and a
    run end / companion event / frame inside the gap re-measures it (the latest frame's text: no model call).

Stubbed screen (FakeScreen) and companion events; no paid API calls."""
from __future__ import annotations

import asyncio

import pytest

from server.coach.screen import Box, ScreenContext
from server.orchestrator import captions
from server.orchestrator.screen_bridge import FakeScreen
from server.orchestrator.tests.test_session import Rig, run

LINE = "fig, axes = plt.subplots(1, 10, figsize=(10, 10))"


# ------------------------------------------------------------------ (a) captions

@pytest.mark.parametrize("caption,line", [
    ("Assign fig, axes here", LINE),
    ("Call plt.subplots here", LINE),
    ("Import numpy here", "import numpy as np"),
    ("Define the model here", "model = tf.keras.Sequential(["),
    ("Change to return response.json()", "    return response.json()"),
    ("Print the shape here", "print(x_train.shape)"),
])
def test_a_caption_that_restates_the_boxed_code_is_a_look_here_pointer(caption, line):
    assert captions.restates_line(caption, line)
    assert captions.for_line(caption, line) == "Look here"


@pytest.mark.parametrize("caption,line", [
    ("Add a comma here", LINE),
    ("Lower the learning rate", "learning_rate = 0.5"),
    ("Set lr to 0.1", "lr = 0.5"),
    ("Change to return response.json()", "    return response.text"),
    ("Plot the first 10 training digits with labels", LINE),
    ("Open calculator.py here", "calculator.py"),
    ("Run the cell here", LINE),
    ("Add figsize here", "fig, axes = plt.subplots(1, 10)"),
    # the curated lesson's (nn1-nn6) and the engine's own captions: never touched
    ("Type below sigmoid_slope", "sigmoid_slope = 1"),
    ("Paste the network under this line", "# --- Step 2: the network ---"),
    ("Paste the loop under this line", "for epoch in range(5000):"),
    ("Type it here", "def sigmoid(x):"),
    ("Type below this line", "import numpy as np"),
    ("Add a new line here", "import numpy as np"),
    ("Run it here", "python3 nn.py"),
    ("Click ▷ to run", "nn.py"),
    ("Change this line", "W1 = np.random.randn(2, 4)"),
    ("Delete this line", "print(W1)"),
    ("Finish this function", "def sigmoid(x):"),
    ("Look here", LINE),
    ("Assign fig, axes here", ""),  # no line text: nothing to compare with
])
def test_real_actions_places_and_pointers_keep_their_caption(caption, line):
    assert not captions.restates_line(caption, line)
    assert captions.for_line(caption, line) == caption


def test_the_coachs_screen_target_label_on_existing_code_reads_look_here():
    """screen.resolve_targets (the coach's set-of-mark targets -> card targets + the streamed box)."""
    screen = ScreenContext(image=None, cursor=(0.0, 0.0), boxes=[
        Box(id=1, text=LINE, x=474.7, y=486.5, w=271.3, h=18.3),
        Box(id=2, text="", x=474.7, y=520.0, w=271.3, h=18.3)])
    out = screen.resolve_targets([{"box_id": 1, "label": "Assign fig, axes here"},
                                  {"box_id": 2, "label": "Add plt.show() here"}])
    assert [t["label"] for t in out] == ["Look here", "Add plt.show() here"]


def test_target_spot_and_the_sent_box_never_restate_the_line(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    rig = Rig(tmp_path, screen=FakeScreen())
    spot = rig.s._target_spot({"rect": {"x": 474.7, "y": 486.5, "w": 271.3, "h": 18.3},
                               "label": "Assign fig, axes here", "text": LINE})
    assert spot["caption"] == "Look here" and spot["matched"] == LINE

    async def go():
        await rig.start_lesson()
        await rig.s.goto_step(1)
        await rig.s._show_spot({"rect": {"x": 10.0, "y": 300.0, "w": 400.0, "h": 20.0},
                                "caption": "Import numpy here", "matched": "import numpy as np"}, owner="offtrack")

    run(go())
    assert rig.of("spotlight")[-1]["caption"] == "Look here"


# ------------------------------------------------------------------ (b) the box follows a layout change without a scroll

def _video_rig(tmp_path, monkeypatch):
    monkeypatch.setenv("TUT_WORKDIR", str(tmp_path))
    screen = FakeScreen()
    rig = Rig(tmp_path, screen=screen)
    rig.s.SPOT_MIN_GAP_S = 2.0
    rig.s.RELAYOUT_S = (0.01, 0.02, 0.03)
    screen.text["Code"] = ["import torch.nn as nn", "", "class Net(nn.Module):", "    pass", LINE]
    return rig, screen


async def _offtrack_box_up(rig) -> dict:
    """Video step 2 (its own target tracked), then the coach's off-track box on LINE (row 4: y = 180)."""
    await rig.start_lesson()
    await rig.s.goto_step(1)
    await rig.s._spotlight_target(rig.s.step)
    assert rig.s.spot_track is not None and not rig.s.lesson_mode
    rig.s.last_offtrack = {"stepId": rig.s.step["id"], "title": "Plot cell not executed yet, no output"}
    rig.clock.t += 2.5
    spot = rig.s._target_spot({"rect": {"x": 100.0, "y": 180.0, "w": 400.0, "h": 20.0},
                               "label": "Assign fig, axes here", "text": LINE})
    await rig.s._show_spot(spot, owner="offtrack")
    box = rig.of("spotlight")[-1]
    assert box["rect"]["y"] == 180.0 and box["caption"] == "Look here" and rig.s._spot_owner[0] == "offtrack"
    return box


def test_the_offtrack_box_follows_its_line_when_output_pushes_the_code_down(tmp_path, monkeypatch):
    """Test 9: the cell above printed its output; LINE moved down 3 rows; the frames came, the box stayed."""
    rig, screen = _video_rig(tmp_path, monkeypatch)

    async def go():
        await _offtrack_box_up(rig)
        n = len(rig.of("spotlight"))
        screen.text["Code"][1:1] = ["Shape of the images: (60000, 28, 28)", "60000", "10000"]  # the cell output
        rig.clock.t += 2.5
        await rig.s._follow_spot()  # the next frame
        return n

    n = run(go())
    boxes = rig.of("spotlight")
    assert len(boxes) == n + 1
    assert boxes[-1]["rect"]["y"] == 240.0 and boxes[-1]["caption"] == "Look here"
    assert rig.s._spot_owner[0] == "offtrack"  # moved as the off-track's own box, not refused as the step's


def test_a_still_screen_inside_the_gap_is_re_measured(tmp_path, monkeypatch):
    """The output landed 0.5 s after the box went up: that frame was inside the 2 s gap and the screen then stayed
    still (no more frames). A short re-measure moves the box anyway."""
    rig, screen = _video_rig(tmp_path, monkeypatch)

    async def go():
        await _offtrack_box_up(rig)
        n = len(rig.of("spotlight"))
        screen.text["Code"][1:1] = ["Shape of the images: (60000, 28, 28)", "60000"]
        await rig.s._follow_spot()  # the one frame, inside the gap: nothing yet
        assert len(rig.of("spotlight")) == n
        await asyncio.sleep(0.1)  # RELAYOUT_S (stubbed short)
        return n

    n = run(go())
    assert len(rig.of("spotlight")) == n + 1 and rig.of("spotlight")[-1]["rect"]["y"] == 220.0


def test_a_run_end_or_a_companion_event_re_measures_and_a_miss_never_clears(tmp_path, monkeypatch):
    rig, screen = _video_rig(tmp_path, monkeypatch)

    async def go():
        await _offtrack_box_up(rig)
        n = len(rig.of("spotlight"))
        screen.text["Code"][1:1] = ["Epoch 1/5", "1875/1875 - loss: 0.26"]
        await rig.s.ingest({"kind": "run_started", "run_id": "r1", "command": "python nn.py"})
        await rig.s.ingest({"kind": "run_ended", "run_id": "r1", "exit_code": 0})
        await asyncio.sleep(0.1)
        moved = rig.of("spotlight")[n:]
        screen.text["Code"] = ["(the notebook redrawing)"]  # a re-measure that finds nothing
        rig.s.relayout("VS Code dirty")
        await asyncio.sleep(0.1)
        return n, moved

    n, moved = run(go())
    assert moved and moved[-1]["rect"]["y"] == 220.0
    assert not any(b.get("clear") for b in rig.of("spotlight")[n:]) and rig.s.spot_rect is not None


def test_relayout_is_video_only_and_needs_a_box(tmp_path, monkeypatch):
    rig, _ = _video_rig(tmp_path, monkeypatch)

    async def go():
        await rig.start_lesson()
        await rig.s.goto_step(1)
        rig.s.relayout("no box yet")
        assert getattr(rig.s, "_relayout_task", None) is None
        rig.s.graph["lesson"]["mode"] = "lesson"
        rig.s.spot_rect = {"x": 0.0, "y": 0.0, "w": 10.0, "h": 10.0}
        rig.s.relayout("lesson mode: rows follow by line")
        assert getattr(rig.s, "_relayout_task", None) is None

    run(go())

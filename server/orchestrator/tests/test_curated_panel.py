"""The curated lesson's network panel (curated.py, t7): a preview of the lesson's own network until the learner's first
real run (data.preview, no epoch / loss, never a training run), then only their runs carry epoch and loss. The Demo's
zeros take looks stuck (identical dark neurons, loss 0.49) and its random take learns, with nothing before step 4 saying
otherwise; after a good run the prediction readout sits next to its own target (t6: "0.933 target -0.141").
Run from the repo root:  python -m pytest server/orchestrator/tests/test_curated_panel.py -q"""

from __future__ import annotations

import json
import math

from server.orchestrator import curated, stage
from server.orchestrator.tests.test_stage import NN1_ZEROS, RANDOM, ZEROS, code, rig, run, save, settle  # noqa: F401
from shared.contracts.events import validate_engine_payload

HALF_PI = round(math.pi / 2, 4)
# What a preview must never say before the learner's run shows it (t7: "EPOCH 20,000 · LOSS 7.8e-4" at step 1).
RUN_WORDS = ("Your run", "Your network", "Your trained", "settles on", "loss falls")


def is_preview(d: dict) -> bool:
    data = d["data"]
    return (data.get("preview") is True and data.get("mode") in ("forward", "backward", "stuck")
            and "epochs" not in data and bool(data["frames"])
            and all("epoch" not in f and "loss" not in f for f in data["frames"]))


def is_run(d: dict) -> bool:
    data = d["data"]
    return not data.get("preview") and bool(data["frames"]) and all(
        isinstance(f.get("epoch"), int) and isinstance(f.get("loss"), (int, float)) for f in data["frames"])


def still(d: dict) -> bool:
    """Every frame has the same weights: nothing trains."""
    return len({json.dumps([f["W"], f["b"]]) for f in d["data"]["frames"]}) == 1


def fired_right(f: dict) -> bool:
    """`a` is what the frame's own weights give for its input (the app fires the neurons from it), to the cache's
    rounding (make_nn_demo.py fires the unrounded weights)."""
    want = curated.activations(f["W"], f["b"], f["input"])
    return len(f["a"]) == len(want) and all(
        len(x) == len(y) and all(abs(u - v) <= 2e-4 for u, v in zip(x, y)) for x, y in zip(f["a"], want))


def prediction(d: dict) -> tuple[float, float]:
    """The panel's "Prediction … target …": the frame the app keeps up (the last) and its target."""
    f = d["data"]["frames"][-1]
    return f["a"][-1][0], f.get("target", d["data"].get("target"))


def diagrams(events: list[dict]) -> list[dict]:
    return [e["payload"] for e in events if e["type"] == "diagram"]


def test_demo_panel_tells_the_zeros_story(rig):
    async def go():
        await rig.s.learn("anything", mode="demo")
        await settle(rig)
        await save(rig, NN1_ZEROS)  # step 1 with the presenter's shortcut
        await save(rig, code("nn2"))
        await save(rig, code("nn3"))
        assert rig.s.step["id"] == "nn4"
        before = diagrams(rig.events)  # every step's picture up to Train it's first run

        m = rig.mark()
        await rig.s.action("run_command")  # the zeros take: stuck
        await settle(rig)
        stuck = diagrams(rig.since(m))
        assert rig.of("offtrack")

        await save(rig, RANDOM)
        m = rig.mark()
        await rig.s.action("run_command")  # the random take: it learns
        await settle(rig)
        good = diagrams(rig.since(m))
        assert rig.s.step["id"] == "nn5"
        nn5 = [d for d in rig.of("diagram") if d.get("stepId") == "nn5"]

        await save(rig, code("nn5"))
        m = rig.mark()
        await rig.s.action("run_command")  # See what it learned: the weights it printed
        await settle(rig)
        final = diagrams(rig.since(m))
        return before, stuck, good, nn5, final

    before, stuck, good, nn5, final = run(go())

    # Before the first run: previews only, one per step, no run stats, nothing training, nothing claiming it learned.
    assert [d["stepId"] for d in before] == ["nn1", "nn2", "nn3", "nn4"]
    for d in before:
        assert is_preview(d), d["stepId"]
        assert not any(w in d["caption"] for w in RUN_WORDS), d["caption"]
        assert all(fired_right(f) for f in d["data"]["frames"])
        assert validate_engine_payload("diagram", d)["data"]["preview"] is True  # survives the contract's dump
    by = {d["stepId"]: d for d in before}
    assert by["nn1"]["data"]["mode"] == "forward" and by["nn2"]["data"]["mode"] == "backward"
    for sid in ("nn3", "nn4"):  # the network the loop starts from, standing still (no animated training run)
        assert by[sid]["data"]["mode"] == "forward" and still(by[sid])
        assert by[sid]["data"]["frames"][-1]["input"] == HALF_PI

    # The zeros take: their run, stuck. Identical dark hidden neurons, the loss at 0.49 on every frame.
    d = stuck[-1]
    assert is_run(d) and d["data"]["mode"] == "stuck" and "same neuron" in d["caption"]
    for f in d["data"]["frames"]:
        assert abs(f["loss"] - curated.STUCK_LOSS) <= 0.0015
        assert f["a"][1] == [0.0] * 4 and f["a"][2] == [0.0] * 4 and f["a"][3] == [0.0]

    # The random take: their run, learning. The loss falls from 0.8187, the weights move, the prediction meets 1.
    assert good
    for d in good + nn5:
        assert is_run(d) and d["data"]["mode"] == "train" and not still(d)
        fr = d["data"]["frames"]
        assert fr[0]["loss"] > 0.8 and fr[-1]["loss"] < 0.01
        assert all(f["input"] == HALF_PI and f["target"] == 1.0 for f in fr) and d["data"]["target"] == 1.0
        assert all(fired_right(f) for f in fr)
        y, target = prediction(d)
        assert target == 1.0 and abs(y - target) < 0.05, (y, target)

    # The last run: their network answering, from the weights nn.py printed; the frame left up is π/2 -> about 1.
    d = final[-1]
    assert is_run(d) and d["data"]["mode"] == "forward" and "printed" in d["caption"]
    y, target = prediction(d)
    assert d["data"]["frames"][-1]["input"] == HALF_PI and target == 1.0 and abs(y - 1.0) < 0.05, (y, target)
    assert all(abs(f["a"][-1][0] - f["target"]) < 0.05 for f in d["data"]["frames"])  # fits at -π/2, 0 and π/2


def test_the_random_take_learns_with_no_stuck_picture(rig):
    async def go():
        await rig.s.learn("anything", mode="demo")
        await settle(rig)
        for sid in ("nn1", "nn2", "nn3"):
            await save(rig, code(sid))
        m = rig.mark()
        await rig.s.action("run_command")
        await settle(rig)
        return diagrams(rig.since(m))

    ds = run(go())
    assert ds and all(is_run(d) and d["data"]["mode"] == "train" and not still(d) for d in ds)


def test_a_second_take_starts_with_previews_again(rig):
    """Each Demo take is fresh: after ⌃⌥⌘R the last take's run never shows before this take's own run."""
    async def go():
        await rig.s.learn("anything", mode="demo")
        await settle(rig)
        for sid in ("nn1", "nn2", "nn3"):
            await save(rig, code(sid))
        await rig.s.action("run_command")  # take 1 trains
        await settle(rig)
        assert rig.s.step["id"] == "nn5"
        m = rig.mark()
        await stage.restart(rig.s)
        await settle(rig)
        await save(rig, NN1_ZEROS)
        await save(rig, code("nn2"))
        await save(rig, code("nn3"))
        assert rig.s.step["id"] == "nn4"
        return diagrams(rig.since(m))

    ds = run(go())
    assert [d["stepId"] for d in ds] == ["nn1", "nn2", "nn3", "nn4"] and all(is_preview(d) for d in ds)


def test_the_stuck_picture_before_a_stuck_run_is_a_preview(rig):
    """The Diagram tab's gradients before any run, or after a good one: the stuck picture as a preview, never "Your
    run" over the zeros' weights (it used to draw their good loss on the zero network)."""
    async def go():
        await rig.s.learn("anything", mode="demo")
        await settle(rig)
        m = rig.mark()
        await rig.s.action("diagram", "gradients")
        await settle(rig)
        early = diagrams(rig.since(m))
        for sid in ("nn1", "nn2", "nn3"):
            await save(rig, code(sid))
        await rig.s.action("run_command")  # a good run: nn4 passes
        await settle(rig)
        m = rig.mark()
        await rig.s.action("diagram", "gradients")
        await settle(rig)
        late = diagrams(rig.since(m))
        m = rig.mark()
        await rig.s.action("diagram", "network")
        await settle(rig)
        return early, late, diagrams(rig.since(m))

    early, late, network = run(go())
    for d in (early[-1], late[-1]):
        assert is_preview(d) and d["data"]["mode"] == "stuck" and d["caption"] == curated.STUCK_PREVIEW_CAPTION
        assert all(f["a"][1] == [0.0] * 4 for f in d["data"]["frames"])
    assert is_run(network[-1])  # the network tab after their run: their run


def test_just_teach_me_starts_with_a_preview(rig):
    async def go():
        await rig.s.learn("build a neural network", mode="lesson")
        await settle(rig)
        return rig.of("diagram")

    ds = run(go())
    assert ds and ds[0]["stepId"] == "nn1" and is_preview(ds[0])


def test_every_step_picture_previews_without_run_stats():
    for k in range(1, 7):
        sid = f"nn{k}"
        ref = curated._ref(f"{sid}-network")
        d = curated.preview(ref, curated.PREVIEW_CAPTION.get(sid))
        assert is_preview(d) and all(fired_right(f) for f in d["data"]["frames"]), sid
        assert not any(w in d["caption"] for w in RUN_WORDS), (sid, d["caption"])
        assert any("epoch" in f for f in ref["data"]["frames"])  # the cached reference keeps its run (live_frames)
        validate_engine_payload("diagram", {**d, "stepId": sid})


def test_printed_weights_without_loss_lines_carry_no_reference_stats():
    ref = curated._ref(f"{curated.TRAIN_STEP}-network")["data"]["frames"]
    final = {"W": [[[0.5] * 4], [[0.1] * 4] * 4, [[0.2]] * 4], "b": [[0.0] * 4, [0.0] * 4, [0.0]]}
    frames, same = curated.live_frames(ref, [], final)
    assert not same and len(frames) == 1
    f = frames[0]
    assert "epoch" not in f and "loss" not in f and f["W"] == final["W"] and fired_right(f)

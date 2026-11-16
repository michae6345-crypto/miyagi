"""Nov 15, the one real Gemini build for "build a neural network" (Kie Codes, "Code your first Neural Network with
TensorFlow", VPlFpvLOgtQ): what it showed about the video path, offline (Gemini and Claude faked).

1. Its training step got `metric_trend loss` with metric_pattern "Epoch\\s*(?P<step>\\d+)/\\d+[\\s\\S]*?loss:..." and
   window 5. The checker reads ONE printed line at a time (Keras prints "Epoch 1/5" on its own line) and a trend needs
   8 points inside its window, so that check could never pass: the video would stay paused at step 5 for good.
2. In auto mode a non-RuntimeError from the transcript (Claude) side, e.g. the Anthropic SDK's TypeError when no key is
   set, ended the whole build although Gemini's draft was on its way.
"""

import asyncio
import json

from server.checks import extract_metrics
from server.checks import evaluator
from server.lesson import builder, claude, gemini, schema, transcript
from server.lesson.workdir import scan

from .test_builder import DRAFT, URL, WORKDIR, fake  # noqa: F401  (fixture)

KERAS_OUT = """Epoch 1/5
1875/1875 ━━━━━━━━━━━━━━━━━━━━ 3s 1ms/step - accuracy: 0.9231 - loss: 0.2634
Epoch 2/5
1875/1875 ━━━━━━━━━━━━━━━━━━━━ 3s 1ms/step - accuracy: 0.9668 - loss: 0.1110
Epoch 3/5
1875/1875 ━━━━━━━━━━━━━━━━━━━━ 3s 1ms/step - accuracy: 0.9764 - loss: 0.0776
Epoch 4/5
1875/1875 ━━━━━━━━━━━━━━━━━━━━ 3s 1ms/step - accuracy: 0.9822 - loss: 0.0576
Epoch 5/5
1875/1875 ━━━━━━━━━━━━━━━━━━━━ 3s 1ms/step - accuracy: 0.9862 - loss: 0.0441"""

# the built lesson's step 5 checks, as the adapt pass wrote them
CROSS = r"Epoch\s*(?P<step>\d+)/\d+[\s\S]*?loss:\s*(?P<value>\d+\.\d+)"
TREND = {"id": "s5c3", "type": "metric_trend", "label": "Training loss decreases", "metric": "loss",
         "metric_pattern": CROSS, "trend": "decreasing", "window": 5}
ACC = {"id": "s5c4", "type": "metric_threshold", "label": "Training accuracy reaches 0.95", "metric": "accuracy",
       "metric_pattern": r"accuracy:\s*(?P<value>\d+\.\d+)", "op": ">=", "value": 0.95}


def test_trend_constant_matches_the_checks_module():
    assert schema.TREND_MIN_POINTS == evaluator.TREND_MIN_POINTS


def test_the_checker_reads_one_line_so_a_line_spanning_pattern_never_matches():
    assert extract_metrics(CROSS, KERAS_OUT) == []  # the bug: no point, ever
    assert [v for _, v in extract_metrics(schema.value_line(CROSS), KERAS_OUT)] == [0.2634, 0.1110, 0.0776, 0.0576, 0.0441]


def test_spans_lines_and_value_line():
    for p in (CROSS, r"Epoch (?P<step>\d+)\n.*loss: (?P<value>[\d.]+)", r"(?s)Epoch (?P<step>\d+).*loss: (?P<value>[\d.]+)",
              r"a[\S\s]+b(?P<value>\d)", r"a[\w\W]*?(?P<value>\d)"):
        assert schema.spans_lines(p), p
    for p in (r"loss:\s*(?P<value>\d+\.\d+)", r"[\d\s]+(?P<value>\d)", r"step\W+(?P<step>\d+)\W+(?P<value>[0-9.eE+-]+)",
              r"(?P<step>\d+)\s+(?P<value>[\d.]+)", r"\\n(?P<value>\d)"):
        assert not schema.spans_lines(p), p
    assert schema.value_line(CROSS) == r"loss:\s*(?P<value>\d+\.\d+)"
    assert schema.value_line(r"Epoch (?P<step>\d+)\nloss: (?P<value>[\d.]+)") == r"loss: (?P<value>[\d.]+)"
    assert schema.value_line(r"(?P<value>\d)[\s\S]*end") == r"(?P<value>\d)"


def test_lint_flags_checks_that_can_never_pass():
    probs = schema.check_problems(dict(TREND), list(schema.SCREEN_TYPES), "checks")
    assert any("spans lines" in p for p in probs) and any("window 5 can never hold the 8 points" in p for p in probs)
    ok_trend = {**TREND, "metric_pattern": r"step\s+(?P<step>\d+)\s+loss\s+(?P<value>[\d.]+)", "window": 1000}
    assert schema.check_problems(ok_trend, list(schema.SCREEN_TYPES), "checks") == []
    assert schema.check_problems(dict(ACC), list(schema.SCREEN_TYPES), "checks") == []


def _keras_graph(checks: list[dict]) -> dict:
    return {"lesson": {"id": "lesson-x", "title": "Keras", "goal": "build a neural network", "libraries": {"tensorflow": "2.15.0"}},
            "sources": [], "steps": [{"id": "s5", "index": 5, "title": "Compile and train the model", "instructions": "Train it.",
                                      "video": {"sourceId": "src1", "start": 251.0, "end": 437.0},
                                      "run_command": builder.NOTEBOOK_RUN, "code": "history = model.fit(train_images, train_labels, epochs=5)",
                                      "checks": checks, "precision_checks": [], "targets": [], "explanations": [], "hints": [],
                                      "common_mistakes": []}]}


def test_repair_keeps_the_step_passable():
    """normalize (deterministic, every adapt round) rewrites the pattern to the value's line; the 5-epoch trend that is
    left can't gather 8 points, so repair drops it; compile / fit / accuracy still gate the step."""
    fit = {"id": "s5c2", "type": "screen_contains", "label": "model.fit called", "app": "Code", "pattern": r"model\s*\.\s*fit\s*\("}
    g = builder.normalize_checks(_keras_graph([fit, dict(TREND), dict(ACC)]), set())
    trend = next(c for c in g["steps"][0]["checks"] if c["type"] == "metric_trend")
    assert trend["metric_pattern"] == r"loss:\s*(?P<value>\d+\.\d+)"
    g = builder.repair(g, scan("/nonexistent/_new"))
    types = [c["type"] for c in g["steps"][0]["checks"]]
    assert types == ["screen_contains", "metric_threshold"]
    assert schema.lint(g) == []
    acc = g["steps"][0]["checks"][1]
    assert extract_metrics(acc["metric_pattern"], KERAS_OUT)[-1][1] == 0.9862  # >= 0.95: the step can pass


def test_a_line_spanning_threshold_is_rewritten_not_dropped():
    thr = {"id": "s5c9", "type": "metric_threshold", "label": "Loss below 0.1", "metric": "loss", "metric_pattern": CROSS,
           "op": "<", "value": 0.1}
    g = builder.repair(builder.normalize_checks(_keras_graph([thr]), set()), scan("/nonexistent/_new"))
    c = g["steps"][0]["checks"][0]
    assert c["type"] == "metric_threshold" and c["metric_pattern"] == r"loss:\s*(?P<value>\d+\.\d+)"


def test_the_race_survives_a_non_runtime_error_from_the_transcript_side(fake, monkeypatch):  # noqa: F811
    """auto: the Anthropic SDK raises TypeError (no key) in Claude's draft; Gemini's draft must still win."""
    monkeypatch.setenv("LESSON_ENGINE", "auto")

    async def info(vid):
        return {"video_id": vid, "title": "t", "description": "", "length_s": 600, "chapters": [],
                "transcript": [{"t": 0.0, "text": "hi"}], "sources": {"transcript": "fake"}}

    async def no_key(info, goal):
        raise TypeError('"Could not resolve authentication method. Expected one of api_key, auth_token, or credentials"')

    async def slow_gemini(url, goal, fps=None, **kw):
        await asyncio.sleep(0.2)  # Claude's side fails first
        return json.loads(json.dumps(DRAFT))

    monkeypatch.setattr(transcript, "fetch_video_info", info)
    monkeypatch.setattr(claude, "watch_transcript", no_key)
    monkeypatch.setattr(gemini, "watch_video", slow_gemini)
    gemini.last_model = "gemini-4-hydrogen"
    g = asyncio.run(builder.build_lesson(URL, "x", WORKDIR, refresh=True))
    assert g["build"]["model"]["video"].startswith("gemini-4-hydrogen")
    assert g["lesson"]["builtBy"] == "gemini"

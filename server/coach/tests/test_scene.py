"""Scene look (coach/scene.py): offline only. A stub client stands in for Haiku (cost freeze: no API call)."""

from __future__ import annotations

import asyncio
import json
import types

import pytest

from server.coach import llm, scene

STEP = {"id": "s2", "title": "Write add()", "instructions": "Define add(a, b) in calc.py.", "file": "calc.py",
        "code": "def add(a, b):\n    return a + b\n",
        "checks": [{"id": "c1", "label": "add() defined", "file": "calc.py"}]}
ANSWER = {"app": "Code", "window_title": "calc.py — calculator", "active_file": "src/calc.py", "step_file_open": True,
          "step_code_visible": True, "typed_fraction": 40, "error_visible": "none", "dialog_visible": "",
          "learner_doing": "typing add() in calc.py", "spotlight_target_visible": False}


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _fresh_registry():
    scene.clear()
    scene.reset_stats()
    yield
    scene.clear()


class _Messages:
    def __init__(self, text: str, stop: str = "end_turn"):
        self.text, self.stop, self.kwargs = text, stop, None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return types.SimpleNamespace(
            content=[types.SimpleNamespace(type="text", text=self.text)], stop_reason=self.stop,
            usage=types.SimpleNamespace(input_tokens=2300, output_tokens=100))


def _client(text: str, stop: str = "end_turn"):
    return types.SimpleNamespace(messages=_Messages(text, stop))


def _image(w: int = 2560, h: int = 1600):
    from PIL import Image

    return Image.new("RGB", (w, h), (200, 200, 200))


def test_parse_normalizes_the_answer():
    d = scene.parse(ANSWER)
    assert d["active_file"] == "calc.py"  # a path -> the file name
    assert d["typed_fraction"] == pytest.approx(0.4)  # "40" meant 40 %
    assert d["error_visible"] is None and d["dialog_visible"] is None  # "none" / "" -> None
    assert d["step_file_open"] is True and d["spotlight_target_visible"] is False


def test_look_sends_one_haiku_request_and_logs_cost():
    c = _client(json.dumps(ANSWER))
    sc = run(scene.look(_image(), STEP, step_file="calc.py", spot="the line in calc.py", front_app="Code", frame=7,
                        client=c))
    kw = c.messages.kwargs
    assert kw["model"] == scene.MODEL and kw["thinking"] == {"type": "disabled"}
    assert kw["output_config"]["effort"] == "low" and kw["output_config"]["format"]["schema"] is scene.SCHEMA
    image, text = kw["messages"][0]["content"]
    assert image["type"] == "image" and "CODE TO TYPE" in text["text"] and "SPOTLIGHT TARGET" in text["text"]
    assert sc.step_id == "s2" and sc.frame == 7 and sc.active_file == "calc.py"
    assert sc.cost_usd == pytest.approx(2300 * 0.10 / 1e6 + 100 * 0.50 / 1e6)
    assert scene.stats()["looks"] == 1


def test_look_without_key_or_offline_never_calls(monkeypatch):
    monkeypatch.setattr(llm, "has_credentials", lambda: False)
    with pytest.raises(llm.CoachLLMError) as e:
        run(scene.look(_image(), STEP))
    assert e.value.kind == "no_key"
    monkeypatch.setenv("DEMO", "1")
    with pytest.raises(llm.CoachLLMError) as e:
        run(scene.look(_image(), STEP))
    assert e.value.kind == "offline"


def test_refusal_is_an_error_not_a_scene():
    with pytest.raises(llm.CoachLLMError):
        run(scene.look(_image(), STEP, client=_client("", stop="refusal")))


def test_encode_downscales_and_masks():
    jpeg, size = scene.encode(_image(), mask=[{"x": 0, "y": 0, "w": 100, "h": 100}], scale=2.0)
    assert max(size) <= scene.MAX_W and jpeg[:2] == b"\xff\xd8"


def test_fake_look_and_the_registry():
    fake = scene.FakeLook([{"step_file_open": False}, {"error_visible": "NameError: name 'ad' is not defined"}])
    a = run(fake(None, STEP, frame=1))
    b = run(fake(None, STEP, frame=2))
    c = run(fake(None, STEP, frame=3))  # the last answer repeats
    assert not a.step_file_open and b.error_visible and c.error_visible and len(fake.calls) == 3
    assert scene.fresh("s2") is None and scene.prompt_line("s2") == ""
    scene.publish(b)
    assert scene.fresh("s2") is b and scene.fresh("s9") is None
    assert "context only" in scene.prompt_line("s2")
    assert scene.with_error("s2", "Traceback ...") == "Traceback ..."  # no run this step: unchanged
    b.after_run = True
    assert "NameError" in scene.with_error("s2", "")
    assert scene.with_error("s2", "NameError: name 'ad' is not defined") == "NameError: name 'ad' is not defined"

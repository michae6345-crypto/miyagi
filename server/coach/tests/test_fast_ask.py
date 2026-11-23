"""server/coach/fast_ask.py, offline: the streamed circle answer, its [DRAW] tag, the warm-up and the model choice.

No network: the Anthropic SDK talks to an httpx2 MockTransport that plays back SSE events, so the SDK's own stream
parser runs; nothing leaves the process and nothing is billed."""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

import anthropic
import httpx2
import pytest

from server import models
from server.coach import fast_ask, llm
from shared.capture_file import Capture

REGION = {"x": 100.0, "y": 200.0, "w": 300.0, "h": 80.0, "displayId": 69733378, "scale": 2.0}
OBS = {"blocks": [{"text": "Run", "rect": {"x": 120, "y": 220, "w": 40, "h": 18}, "app": "Code"},
                  {"text": "import numpy as np", "rect": {"x": 180, "y": 220, "w": 160, "h": 18}, "app": "Code"}],
       "screen": {"x": 0, "y": 0, "w": 1512, "h": 982}, "scale": 2.0, "app": "Code", "windows": []}


def image():
    from PIL import Image

    return Image.new("RGB", (3024, 1964), (240, 240, 235))


def jpeg_of(w: int, h: int) -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), (250, 250, 250)).save(buf, format="JPEG", quality=80)
    return buf.getvalue()


# ---------------------------------------------------------------------------------------------------- fakes

def sse(events: list[dict]) -> bytes:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


def text_events(chunks: list[str], *, model: str = "claude-haiku-5-5", stop: str = "end_turn",
                error: bool = False) -> list[dict]:
    ev: list[dict] = [{"type": "message_start", "message": {
        "id": "msg_1", "type": "message", "role": "assistant", "model": model, "content": [], "stop_reason": None,
        "stop_sequence": None, "usage": {"input_tokens": 900, "output_tokens": 1, "cache_read_input_tokens": 700,
                                         "cache_creation_input_tokens": 0}}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}]
    ev += [{"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": c}} for c in chunks]
    if error:
        ev.append({"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}})
        return ev
    ev += [{"type": "content_block_stop", "index": 0},
           {"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None},
            "usage": {"output_tokens": 42}},
           {"type": "message_stop"}]
    return ev


class FakeAPI:
    """An AsyncAnthropic on a MockTransport: `respond(request_json) -> httpx2.Response`; every request body kept."""

    def __init__(self, respond: Any) -> None:
        self.requests: list[dict] = []
        self.respond = respond

        def handler(req: httpx2.Request) -> httpx2.Response:
            body = json.loads(req.content.decode())
            self.requests.append(body)
            return self.respond(body)

        self.client = anthropic.AsyncAnthropic(api_key="test-key", base_url="http://fake.anthropic.test",
                                               max_retries=0,
                                               http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)))


def streaming(events: list[dict]) -> Any:
    return lambda body: httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=sse(events))


def failing(status: int = 500) -> Any:
    return lambda body: httpx2.Response(status, json={"type": "error",
                                                      "error": {"type": "api_error", "message": "boom"}})


@pytest.fixture
def api(monkeypatch):
    """Credentials on, the shared client replaced by the fake. Tests set api.respond."""
    fake = FakeAPI(streaming(text_events(["[DRAW:none]\nHello."])))
    monkeypatch.setattr(llm, "get_client", lambda: fake.client)
    monkeypatch.setattr(llm, "has_credentials", lambda: True)
    monkeypatch.setattr(llm, "offline_mode", lambda: False)
    monkeypatch.setattr(llm, "record_cost", lambda *a, **k: 0.0)
    fast_ask.reset_warm()
    yield fake
    fast_ask.reset_warm()


class Timer:
    def __init__(self) -> None:
        self.marks: list[str] = []
        self.flags: dict = {}

    def mark(self, name: str) -> None:
        self.marks.append(name)

    def flag(self, k: str, v: Any) -> None:
        self.flags[k] = v


def run(coro):
    return asyncio.run(coro)


async def ask(question: str = "", *, capture: Any = None, obs: Any = OBS, img: Any = "make", ask_id: str = "a1"):
    deltas: list[tuple[str, bool]] = []
    marks: list[list[dict]] = []
    order: list[str] = []
    timer = Timer()

    async def on_delta(text: str, done: bool) -> None:
        deltas.append((text, done))
        order.append("delta")

    async def on_mark(m: list[dict]) -> None:
        marks.append(m)
        order.append("mark")

    card = await fast_ask.circle_stream(None, question, dict(REGION), obs=obs,
                                        image=image() if img == "make" else img, capture=capture, ask_id=ask_id,
                                        on_delta=on_delta, on_mark=on_mark, timer=timer)
    return card, deltas, marks, order, timer


# ---------------------------------------------------------------------------------------------------- the tag

def feed_all(chunks: list[str]) -> tuple[fast_ask.DrawParser, str]:
    p = fast_ask.DrawParser()
    out = "".join(p.feed(c) for c in chunks) + p.finish()
    return p, out


@pytest.mark.parametrize("split", [1, 2, 3, 5, 7, 11])
def test_a_tag_split_across_chunks_is_read_and_never_shown(split):
    text = "[DRAW:212,48,30:Run button]\nThe Run button starts your script."
    chunks = [text[i:i + split] for i in range(0, len(text), split)]
    p, out = feed_all(chunks)
    assert p.status == "found" and p.tag == {"x": 212.0, "y": 48.0, "r": 30.0, "label": "Run button"}
    assert out == "The Run button starts your script."


def test_draw_none_is_hidden_and_no_mark():
    p, out = feed_all(["  [DRAW:", "none]", "\n", "This is the import line."])
    assert p.status == "none" and p.tag == "none" and out == "This is the import line."
    assert fast_ask.mark_from_tag(p.tag, fast_ask.Crop(b"", 100, 100, (0, 0, 50, 50))) is None


@pytest.mark.parametrize("chunks", [["[DRAW:abc,1,2]\nKept text."], ["[DRAW:1,2\nKept text."],
                                    ["[DRAW:12;40]", "\nKept text."], ["[DRAW:1,2,3:", "x" * 200 + " Kept text."]])
def test_a_malformed_tag_keeps_the_text_and_skips_the_mark(chunks):
    p, out = feed_all(chunks)
    assert p.status == "malformed" and p.tag is None
    assert "Kept text." in out and "[DRAW" not in out


def test_no_tag_keeps_every_word_including_brackets():
    p, out = feed_all(["a[0] is the ", "first [item]."])
    assert p.status == "missing" and out == "a[0] is the first [item]."


def test_a_second_tag_later_in_the_text_is_hidden_too():
    _p, out = feed_all(["[DRAW:none]\nThe Run", " button [DR", "AW:1,2,3] runs it."])
    assert out == "The Run button runs it."


def test_points_outside_the_picture_draw_nothing():
    crop = fast_ask.Crop(b"", 400, 200, (100.0, 200.0, 200.0, 100.0))
    for x, y in ((5000, 50), (50, -400), (-100, 10), (401 + 0.06 * 400, 10)):
        assert fast_ask.mark_from_tag({"x": x, "y": y, "r": 10, "label": "x"}, crop) is None
    m = fast_ask.mark_from_tag({"x": 200, "y": 100, "r": 40, "label": "Run button now please"}, crop)
    # crop pixel (200, 100) -> screen (100 + 200 * 200/400, 200 + 100 * 100/200) = (200, 250); r 40 px -> 20 pt
    assert m == {"x": 180.0, "y": 230.0, "w": 40.0, "h": 40.0, "why": "answer", "label": "Run button now please"}
    tiny = fast_ask.mark_from_tag({"x": 200, "y": 100, "r": 0, "label": ""}, crop)
    assert tiny["w"] == 2 * fast_ask.MIN_R_PT and "label" not in tiny


# ---------------------------------------------------------------------------------------------------- model choice

@pytest.mark.parametrize("words, haiku", [("", True), ("What is this?", True), ("what's that thing", True),
                                          ("hey miyagi what is this", True), ("this?", True),
                                          ("why does my loss go up after epoch three", False),
                                          ("how do I fix this import error", False)])
def test_the_model_is_haiku_for_no_or_short_words_and_sonnet_for_real_questions(words, haiku):
    assert models.ask_model(words) == (models.HAIKU if haiku else models.SONNET)


def test_thinking_is_off_in_the_way_each_model_takes_it():
    assert fast_ask.thinking_for(models.SONNET) == {"type": "between_tools"}
    assert fast_ask.thinking_for(models.HAIKU) == {"type": "disabled"}
    assert "opus" not in models.ask_model("why does this explode") and "opus" not in models.ask_warm_model()


def test_the_system_prompt_is_long_enough_to_cache_and_fixed():
    # >= 512 tokens: about 4 characters a token for this English, so 2,600 characters is a safe floor (not measured
    # with count_tokens: that would be a live call)
    assert len(fast_ask.FAST_SYSTEM) >= 2600
    assert "[DRAW:x,y,r:label]" in fast_ask.FAST_SYSTEM and "[DRAW:none]" in fast_ask.FAST_SYSTEM
    assert "W×H" in fast_ask.FAST_SYSTEM


# ---------------------------------------------------------------------------------------------------- streaming

def test_streams_deltas_draws_the_mark_first_and_returns_the_full_card(api):
    api.respond = streaming(text_events(["[DRAW:2", "00,80,30:Run but", "ton]\nThe Run button ", "starts your ",
                                         "script. It runs the open file."], model="claude-sonnet-5-5"))
    card, deltas, marks, order, timer = run(ask("why does this button exist at all here"))
    assert order[0] == "mark"  # the buddy starts drawing before the first words
    [[mark]] = marks
    assert mark["why"] == "answer" and mark["askId"] == "a1" and mark["displayId"] == REGION["displayId"]
    assert mark["label"] == "Run button" and mark["id"] == "ask-a1-0"
    text = "".join(t for t, _ in deltas)
    assert text == "The Run button starts your script. It runs the open file."
    assert "[DRAW" not in text and deltas[-1][1] is True and all(not d for _, d in deltas[:-1])
    assert card["kind"] == "answer" and card["body"] == text and card["title"] == "Run button"
    assert card["askId"] == "a1" and card["marks"] == []  # drawn already through on_mark
    assert card["_meta"]["route"] == "stream" and card["_meta"]["draw"] == "found"
    assert {"first_byte", "first_text", "first_delta", "done"} <= set(timer.marks)
    assert timer.flags["model"] == models.SONNET and timer.flags["picture"] == "frame"
    [body] = api.requests
    assert body["stream"] is True and body["max_tokens"] == fast_ask.MAX_TOKENS
    assert body["model"] == models.SONNET and body["thinking"] == {"type": "between_tools"}
    assert body["output_config"] == {"effort": "low"}
    assert body["system"] == [{"type": "text", "text": fast_ask.FAST_SYSTEM, "cache_control": {"type": "ephemeral"}}]
    content = body["messages"][0]["content"]
    assert content[0]["type"] == "image" and content[1]["type"] == "text"  # the image first
    assert "<untrusted" in content[1]["text"] and "LEARNER ASKS: why does this button" in content[1]["text"]
    assert "pixels (W×H)" in content[1]["text"]


def test_no_words_go_to_haiku_with_thinking_disabled(api):
    run(ask(""))
    [body] = api.requests
    assert body["model"] == models.HAIKU and body["thinking"] == {"type": "disabled"}
    assert "LEARNER ASKS: What is this?" in body["messages"][0]["content"][1]["text"]


def test_a_malformed_tag_still_answers_without_a_mark(api):
    api.respond = streaming(text_events(["[DRAW:oops]\n", "The import line loads numpy."]))
    card, _deltas, marks, _order, timer = run(ask())
    assert marks == [] and card["marks"] == [] and timer.flags["draw"] == "malformed"
    assert card["body"] == "The import line loads numpy." and card["title"] == "About this"


def test_an_out_of_range_point_answers_without_a_mark(api):
    api.respond = streaming(text_events(["[DRAW:99999,5,10:Far]\nThe Run button."]))
    card, _deltas, marks, _order, _timer = run(ask())
    assert marks == [] and card["marks"] == [] and card["body"] == "The Run button."


def test_with_the_apps_capture_the_capture_is_sent_and_points_map_through_its_rect(api):
    jpeg = jpeg_of(600, 160)
    cap = Capture(jpeg=jpeg, w=600, h=160, rect=(90.0, 190.0, 320.0, 100.0 * 160 / 160 * 0.85), displayId=7)
    api.respond = streaming(text_events(["[DRAW:300,80,60:Run]\nThe Run button."]))
    card, _d, marks, _o, timer = run(ask(capture=cap, obs=None, img=None))
    [body] = api.requests
    assert base64.b64decode(body["messages"][0]["content"][0]["source"]["data"]) == jpeg  # the bytes as they came
    assert "PICTURE: 600×160 pixels" in body["messages"][0]["content"][1]["text"]
    [[mark]] = marks
    # crop_to_screen: (90 + 300 * 320/600, 190 + 80 * 85/160) = (250, 232.5); r 60 px * 320/600 = 32 pt
    assert (mark["x"], mark["y"], mark["w"]) == (218.0, 200.5, 64.0)
    assert timer.flags["picture"] == "capture" and card["body"] == "The Run button."


def test_without_a_capture_the_frame_is_cropped_and_points_map_through_the_crop(api):
    api.respond = streaming(text_events(["[DRAW:0,0,0:Corner]\nThe Run button."]))
    _card, _d, marks, _o, _t = run(ask())
    [body] = api.requests
    text = body["messages"][0]["content"][1]["text"]
    # the region +4 pt each side at 2 px a point: 616 x 176 px, under the 1092 px cap
    assert "PICTURE: 616×176 pixels" in text
    [[mark]] = marks
    assert (mark["x"], mark["y"]) == (96.0 - fast_ask.MIN_R_PT, 196.0 - fast_ask.MIN_R_PT)  # crop (0,0) = (96, 196)


def test_secret_rows_in_the_last_frame_are_blacked_out_of_the_apps_capture(api):
    import io

    from PIL import Image

    cap = Capture(jpeg=jpeg_of(600, 200), w=600, h=200, rect=(100.0, 200.0, 300.0, 100.0), displayId=1)
    obs = dict(OBS, blocks=[*OBS["blocks"], {"text": "API_KEY=[secret]", "rect": {"x": 150, "y": 260, "w": 100,
                                                                                   "h": 20}}])
    run(ask(capture=cap, obs=obs, img=None))
    sent = base64.b64decode(api.requests[0]["messages"][0]["content"][0]["source"]["data"])
    img = Image.open(io.BytesIO(sent)).convert("L")
    assert img.getpixel((200, 140)) < 40  # the key row (100..300 x 120..160 px) is black
    assert img.getpixel((20, 20)) > 200  # the rest is untouched


@pytest.mark.parametrize("respond, kind", [(failing(500), "api"), (failing(429), "api"),
                                           (streaming(text_events(["[DRAW:none]\nHal"], error=True)), "api"),
                                           (streaming(text_events(["[DRAW:none]\n"])), "empty"),
                                           (streaming(text_events(["No."], stop="refusal")), "refusal")])
def test_a_stream_error_raises_for_the_fallback(api, respond, kind):
    api.respond = respond
    with pytest.raises(fast_ask.FastAskError) as e:
        run(ask())
    assert e.value.kind == kind


def test_a_mark_drawn_before_the_stream_broke_is_reported(api):
    api.respond = streaming(text_events(["[DRAW:100,40,20:Run]\nThe Run", " button"], error=True))
    with pytest.raises(fast_ask.FastAskError) as e:
        run(ask())
    assert e.value.drew is True and e.value.sent is True


def test_offline_or_no_key_never_calls_out(api, monkeypatch):
    monkeypatch.setattr(llm, "offline_mode", lambda: True)
    with pytest.raises(fast_ask.FastAskError) as e:
        run(ask())
    assert e.value.kind == "offline" and api.requests == []
    monkeypatch.setattr(llm, "offline_mode", lambda: False)
    monkeypatch.setattr(llm, "has_credentials", lambda: False)
    with pytest.raises(fast_ask.FastAskError) as e:
        run(ask())
    assert e.value.kind == "no_key" and api.requests == []


def test_deltas_are_coalesced():
    sent: list[str] = []
    now = [0.0]

    async def send(t: str, done: bool) -> None:
        sent.append(t)

    c = fast_ask.Coalescer(send, every_s=0.06, clock=lambda: now[0])

    async def go():
        await c.add("The")  # the first words: at once
        for w in (" Run", " button", " starts"):
            now[0] += 0.01
            await c.add(w)  # held: under 60 ms
        now[0] += 0.05
        await c.add(" your")  # 60 ms since the last send
        await c.add(" script.")  # a sentence end
        await c.add(" It")
        await c.flush(done=True)

    run(go())
    assert sent == ["The", " Run button starts your", " script.", " It"]


# ---------------------------------------------------------------------------------------------------- warm-up

def test_warm_sends_one_max_tokens_zero_request_and_is_rate_limited(api):
    api.respond = lambda body: httpx2.Response(200, json={
        "id": "msg_w", "type": "message", "role": "assistant", "model": body["model"], "content": [],
        "stop_reason": "max_tokens", "stop_sequence": None,
        "usage": {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 720}})

    async def go():
        assert fast_ask.warm(now=1000.0) is True
        assert fast_ask.warm(now=1000.0 + 60) is False  # within 4 minutes: nothing
        await asyncio.sleep(0.05)
        while fast_ask._warm_tasks:
            await asyncio.sleep(0.01)
        assert fast_ask.warm(now=1000.0 + fast_ask.WARM_EVERY_S + 1) is True
        while fast_ask._warm_tasks:
            await asyncio.sleep(0.01)

    run(go())
    assert len(api.requests) == 2
    body = api.requests[0]
    assert body["max_tokens"] == 0 and "stream" not in body
    assert body["model"] == models.ask_warm_model() == models.SONNET
    assert body["thinking"] == fast_ask.thinking_for(models.SONNET) and body["output_config"] == {"effort": "low"}
    assert body["system"] == [{"type": "text", "text": fast_ask.FAST_SYSTEM, "cache_control": {"type": "ephemeral"}}]


def test_warm_never_blocks_and_an_error_is_one_log_line(api, caplog):
    api.respond = failing(500)

    async def go():
        assert fast_ask.warm(now=5.0) is True  # returns at once: the request runs in the background
        while fast_ask._warm_tasks:
            await asyncio.sleep(0.01)

    with caplog.at_level("INFO", logger="coach.fast_ask"):
        run(go())
    assert [r.getMessage() for r in caplog.records if "warm-up failed" in r.getMessage()] == \
        ["fast ask: warm-up failed (InternalServerError)"]


def test_warm_is_skipped_offline_and_after_a_streamed_ask(api, monkeypatch):
    async def go():
        await fast_ask.circle_stream(None, "why is this slow when it runs", dict(REGION), obs=OBS, image=image())
        return fast_ask.warm()  # the ask just wrote the same cache entry

    assert run(go()) is False and len(api.requests) == 1
    fast_ask.reset_warm()
    monkeypatch.setattr(llm, "offline_mode", lambda: True)

    async def go2():
        return fast_ask.warm()

    assert run(go2()) is False

"""Streamed /v1/anthropic/messages answers pass through with no buffering, offline.

The upstream is an httpx.MockTransport on the app's client that sends SSE in timed chunks (or holds the rest of the
answer until the client has its first chunk). One test runs the app under a real uvicorn server on 127.0.0.1, so
the chunks cross a real socket. Nothing reaches a real provider.

    cd cloud && python -m pytest tests -q
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time

import httpx
import pytest

from test_caps import install, make_cloud  # noqa: F401  (make_cloud is a fixture)
from test_security import Upstream, msg, post_anthropic

SONNET = "claude-sonnet-5-5"
HAIKU = "claude-haiku-5-5"
PATH = "/v1/anthropic/v1/messages"
SSE = {"content-type": "text/event-stream; charset=utf-8"}


def sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


def answer_events(model: str = SONNET, inp: int = 1200, out: int = 40) -> list[bytes]:
    """A circle-to-ask answer as Anthropic streams it: the [DRAW:...] line first, then the words, then usage."""
    words = ["[DRAW:412,230,36:the loop]\n", "That ", "loop ", "runs ", "once ", "per ", "item."]
    return ([sse("message_start", {"type": "message_start", "message": {"model": model, "usage": {"input_tokens": inp, "output_tokens": 1}}}),
             sse("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}})]
            + [sse("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": w}}) for w in words]
            + [sse("content_block_stop", {"type": "content_block_stop", "index": 0}),
               sse("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"input_tokens": inp, "output_tokens": out}}),
               sse("message_stop", {"type": "message_stop"})])


class TimedStream(httpx.AsyncByteStream):
    """Sends each chunk `gap` seconds after the last and records when it sent each one and when it ended."""

    def __init__(self, chunks: list[bytes], gap: float) -> None:
        self.chunks, self.gap = chunks, gap
        self.sent: list[float] = []
        self.ended: float | None = None

    async def __aiter__(self):
        for i, c in enumerate(self.chunks):
            if i:
                await asyncio.sleep(self.gap)
            self.sent.append(time.monotonic())
            yield c
        self.ended = time.monotonic()


class GatedStream(httpx.AsyncByteStream):
    """Sends the first chunk, then holds the rest until `gate` is set. A proxy that buffered would never let the
    client see the first chunk, so the gate would never open: the test then times out instead of passing."""

    def __init__(self, chunks: list[bytes], gate: asyncio.Event) -> None:
        self.chunks, self.gate = chunks, gate
        self.ended = False

    async def __aiter__(self):
        yield self.chunks[0]
        await self.gate.wait()
        for c in self.chunks[1:]:
            yield c
        self.ended = True


def stream_upstream(app_mod, make_stream):
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, stream=make_stream(), headers=SSE)

    app_mod.http = app_mod.upstream_client(httpx.MockTransport(handler))
    return seen


async def asgi_stream(app, headers: dict, body: dict, on_body=None):
    """One raw ASGI request. Returns (status, response headers, [(arrival time, body bytes)])."""
    raw = json.dumps(body).encode()
    start: dict = {}
    chunks: list[tuple[float, bytes]] = []
    done = asyncio.Event()
    first = [True]

    async def receive():
        if first[0]:
            first[0] = False
            return {"type": "http.request", "body": raw, "more_body": False}
        await done.wait()
        return {"type": "http.disconnect"}

    async def send(m):
        if m["type"] == "http.response.start":
            start.update(m)
        elif m["type"] == "http.response.body":
            if m.get("body"):
                chunks.append((time.monotonic(), m["body"]))
                if on_body:
                    on_body(m["body"])
            if not m.get("more_body"):
                done.set()

    hs = [(k.lower().encode(), v.encode()) for k, v in {**headers, "content-type": "application/json",
                                                         "content-length": str(len(raw))}.items()]
    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"}, "http_version": "1.1", "method": "POST",
             "scheme": "http", "path": PATH, "raw_path": PATH.encode(), "query_string": b"", "root_path": "",
             "headers": hs, "client": ("127.0.0.1", 40000), "server": ("testserver", 80)}
    await app(scope, receive, send)
    out_headers = {k.decode().lower(): v.decode() for k, v in start.get("headers", [])}
    return start.get("status"), out_headers, chunks


def ask(stream: bool = True, max_tokens: int = 1024, model: str = SONNET) -> dict:
    return {"model": model, "max_tokens": max_tokens, "stream": stream, "messages": msg("what does this loop do?")}


# --------------------------------------------------------------------------- no buffering

def test_first_chunk_reaches_the_client_before_the_upstream_ends(make_cloud):
    client, app_mod = make_cloud()
    h, _ = install(client)
    gate = asyncio.Event()
    streams: list[GatedStream] = []

    def make():
        streams.append(GatedStream(answer_events(), gate))
        return streams[-1]

    stream_upstream(app_mod, make)

    def on_body(_b):
        assert not streams[0].ended  # the client has a chunk while the upstream is still open
        gate.set()

    async def scenario():
        return await asyncio.wait_for(asgi_stream(app_mod.app, h, ask(), on_body), 5)

    status, headers, chunks = asyncio.run(scenario())
    assert status == 200 and streams[0].ended
    assert chunks[0][1].startswith(b"event: message_start")
    assert b"".join(c for _, c in chunks) == b"".join(answer_events())  # every byte, unchanged


def test_timed_chunks_arrive_as_they_are_sent(make_cloud):
    client, app_mod = make_cloud()
    h, _ = install(client)
    gap = 0.15
    streams: list[TimedStream] = []

    def make():
        streams.append(TimedStream(answer_events(), gap))
        return streams[-1]

    stream_upstream(app_mod, make)
    status, headers, chunks = asyncio.run(asgi_stream(app_mod.app, h, ask()))
    up = streams[0]
    assert status == 200 and up.ended is not None
    # the first chunk was at the client well before the upstream finished (it took gap x (chunks - 1))
    assert chunks[0][0] < up.ended - gap * (len(up.sent) - 2)
    # each chunk went out before the upstream produced the next one: no batching anywhere on the way
    assert len(chunks) == len(up.sent)
    for (arrived, _), sent_next in zip(chunks, up.sent[1:]):
        assert arrived < sent_next


def test_stream_headers_stop_proxy_buffering(make_cloud):
    client, app_mod = make_cloud()
    h, _ = install(client)
    stream_upstream(app_mod, lambda: TimedStream(answer_events(), 0))
    status, headers, _ = asyncio.run(asgi_stream(app_mod.app, h, ask()))
    assert status == 200
    assert headers["x-accel-buffering"] == "no"
    assert headers["cache-control"] == "no-cache"
    assert headers["content-type"].startswith("text/event-stream")
    assert "content-length" not in headers


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_chunks_cross_a_real_socket_unbuffered(make_cloud):
    """Under uvicorn on 127.0.0.1 (the server Render runs): the client reads the first event while the upstream is
    still holding the rest of the answer."""
    uvicorn = pytest.importorskip("uvicorn")
    client, app_mod = make_cloud()
    h, _ = install(client)
    gate = threading.Event()
    ended = threading.Event()

    class ThreadGated(httpx.AsyncByteStream):
        async def __aiter__(self):
            events = answer_events()
            yield events[0]
            while not gate.is_set():
                await asyncio.sleep(0.01)
            for c in events[1:]:
                yield c
            ended.set()

    stream_upstream(app_mod, ThreadGated)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app_mod.app, host="127.0.0.1", port=port, lifespan="off", log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    try:
        for _ in range(500):
            if server.started:
                break
            time.sleep(0.01)
        assert server.started
        got = b""
        with httpx.Client(timeout=5) as c:
            with c.stream("POST", f"http://127.0.0.1:{port}{PATH}", headers=h, json=ask()) as r:
                assert r.status_code == 200 and r.headers["x-accel-buffering"] == "no"
                for chunk in r.iter_raw():
                    if not gate.is_set():
                        assert chunk.startswith(b"event: message_start") and not ended.is_set()
                        gate.set()
                    got += chunk
        assert ended.is_set() and got == b"".join(answer_events())
    finally:
        server.should_exit = True
        t.join(5)


# --------------------------------------------------------------------------- caps and accounting still apply

def test_streamed_usage_is_counted_at_the_real_cost(make_cloud):
    client, app_mod = make_cloud(FREE_DAILY_USD="5")
    h, _ = install(client)
    th = app_mod.hash_token(h["Authorization"][7:])
    stream_upstream(app_mod, lambda: TimedStream(answer_events(inp=1200, out=40), 0.01))
    status, _, _ = asyncio.run(asgi_stream(app_mod.app, h, ask()))
    assert status == 200
    assert app_mod.store.usd_today_for(th) == pytest.approx(app_mod.estimate_usd(SONNET, 1200, 40))
    assert app_mod.store.requests_today(th) == 1
    assert app_mod.inflight.total == 0 and app_mod.inflight.per == {}


def test_kill_switch_and_caps_stop_a_stream_before_the_upstream(make_cloud):
    client, app_mod = make_cloud(PROXY_ENABLED="false")
    h = {"Authorization": "Bearer any"}  # /v1/install is off too: the switch answers before any token check
    seen = stream_upstream(app_mod, lambda: TimedStream(answer_events(), 0))
    status, _, chunks = asyncio.run(asgi_stream(app_mod.app, h, ask()))
    assert status == 503 and b"proxy_disabled" in b"".join(c for _, c in chunks) and not seen


def test_a_stream_over_the_usd_cap_is_refused_before_the_upstream(make_cloud):
    client, app_mod = make_cloud(FREE_DAILY_USD="0.001")
    h, _ = install(client)
    seen = stream_upstream(app_mod, lambda: TimedStream(answer_events(), 0))
    status, _, chunks = asyncio.run(asgi_stream(app_mod.app, h, ask(max_tokens=1024)))  # reserves ~$0.01 on Sonnet
    assert status == 429 and b"miyagi_quota" in b"".join(c for _, c in chunks) and not seen


# --------------------------------------------------------------------------- prompt-cache warm-up

SYSTEM = "You are miyagi, a patient tutor. " * 120  # about 600+ tokens: above the cacheable minimum


def warmup(stream: bool = False) -> dict:
    return {"model": SONNET, "max_tokens": 0, "stream": stream,
            "output_config": {"effort": "low"},
            "system": [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            "messages": msg("warmup")}


def test_cache_warmup_is_allowed_and_cheap_under_the_caps(make_cloud):
    # a tight cap: about 5 cents a day still lets a warm-up through, and it settles at the cache write alone
    client, app_mod = make_cloud(FREE_DAILY_USD="0.05")
    up = Upstream(app_mod, body={"type": "message", "model": SONNET, "content": [], "stop_reason": "max_tokens",
                                 "usage": {"input_tokens": 3, "cache_creation_input_tokens": 700,
                                           "cache_read_input_tokens": 0, "output_tokens": 0}})
    h, _ = install(client)
    th = app_mod.hash_token(h["Authorization"][7:])
    r = post_anthropic(client, h, warmup())
    assert r.status_code == 200 and r.json()["content"] == []
    sent = up.last
    assert sent["max_tokens"] == 0 and sent["stream"] is False
    assert sent["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert sent["output_config"] == {"effort": "low"}
    cost = app_mod.store.usd_today_for(th)
    assert cost == pytest.approx(app_mod.estimate_usd(SONNET, 703, 0, 0, 700))
    assert cost < 0.002  # a fraction of a cent
    # its reservation is the input alone (max_tokens 0 reserves no output)
    clean, uses, tokens = app_mod.sanitize_anthropic(warmup())
    assert app_mod.anthropic_reserve(clean, len(json.dumps(clean).encode()), uses, tokens) < 0.003


def test_streamed_warmup_is_refused_without_a_round_trip(make_cloud):
    client, app_mod = make_cloud()
    up = Upstream(app_mod)
    h, _ = install(client)
    r = post_anthropic(client, h, warmup(stream=True))
    assert r.status_code == 400 and "stream false" in r.json()["error"]["message"]
    assert not up.requests


# --------------------------------------------------------------------------- one keep-alive client

def test_one_keepalive_upstream_client_per_process(make_cloud):
    client, app_mod = make_cloud()
    made = app_mod.http  # made once by the lifespan, reused by every call
    pool = made._transport._pool
    assert pool._keepalive_expiry == app_mod.UPSTREAM_KEEPALIVE_S == 90
    assert pool._max_connections > app_mod.GLOBAL_INFLIGHT
    assert pool._http2 is app_mod.UPSTREAM_HTTP2
    h, _ = install(client)
    seen = stream_upstream(app_mod, lambda: TimedStream(answer_events(), 0))
    shared = app_mod.http
    asyncio.run(asgi_stream(app_mod.app, h, ask()))
    asyncio.run(asgi_stream(app_mod.app, h, ask()))
    assert len(seen) == 2 and app_mod.http is shared

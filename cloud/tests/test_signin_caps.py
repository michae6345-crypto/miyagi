"""REQUIRE_SIGNIN on every model route, the per-user daily caps (dollars and tokens) and the per-user lesson build
cap, offline.

The upstreams point at a closed local port, so a call that gets past the gate and the caps fails with 502
(upstream_unreachable) and never reaches a real provider. JWTs are signed here and checked against an injected JWKS.

    cd cloud && python -m pytest tests -q
"""

from __future__ import annotations

import importlib
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

jwt = pytest.importorskip("jwt")
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402

CLOUD = Path(__file__).resolve().parents[1]
ADMIN_TOKEN = "miyagi-tests-admin-0123456789-abcdefghijklmnop"
ADMIN = {"X-Admin-Token": ADMIN_TOKEN}
URL = "https://example-project.supabase.co"
USER = "0b5d2c1e-8a4f-4e3b-9c7d-1f2e3a4b5c6d"
VID = "dQw4w9WgXcQ"
HAIKU = "claude-haiku-5-5"
KEY = ec.generate_private_key(ec.SECP256R1())
JWKS = {"keys": [json.loads(jwt.algorithms.ECAlgorithm.to_jwk(KEY.public_key())) | {"kid": "k1", "alg": "ES256", "use": "sig"}]}
SIGNIN_BODY = {"error": "signin_required", "message": "Sign in to keep using miyagi."}


def access_token(sub: str = USER) -> str:
    now = int(time.time())
    claims = {"sub": sub, "aud": "authenticated", "iss": f"{URL}/auth/v1", "iat": now, "exp": now + 3600,
              "role": "authenticated", "is_anonymous": False, "app_metadata": {"provider": "google", "providers": ["google"]}}
    return jwt.encode(claims, KEY, algorithm="ES256", headers={"kid": "k1"})


@pytest.fixture
def make_cloud(tmp_path, monkeypatch):
    clients = []

    def make(unset=(), **env):
        base = {"ADMIN_TOKEN": ADMIN_TOKEN, "DB_PATH": str(tmp_path / "miyagi.db"), "SUPABASE_URL": URL,
                "ANTHROPIC_API_KEY": "fake-upstream-key", "GEMINI_API_KEY": "fake-upstream-key",
                "UPSTREAM_ANTHROPIC_URL": "http://127.0.0.1:9/v1/messages",  # closed port: never a real call
                "UPSTREAM_GEMINI_URL": "http://127.0.0.1:9/{model}:{method}", "ALLOWED_GEMINI_MODELS": "gemini-3.8-flash",
                "FREE_DAILY_REQUESTS": "0", "DAILY_USD_CAP": "0", "FREE_DAILY_USD": "0", "LINKED_DAILY_REQUESTS": "0",
                "LINKED_DAILY_USD": "0", "LINKED_DAILY_TOKENS": "0", "ANON_DAILY_USD_PER_NETWORK": "0",
                "REQUIRE_SIGNIN": "0", "FREE_LESSON_BUILDS_PER_MONTH": "3"}
        for k, v in {**base, **env}.items():
            monkeypatch.setenv(k, v)
        for k in unset:
            monkeypatch.delenv(k, raising=False)
        monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
        monkeypatch.syspath_prepend(str(CLOUD))
        for mod in ("app", "store", "supabase_auth"):
            sys.modules.pop(mod, None)
        app_mod = importlib.import_module("app")
        app_mod.verifier = app_mod.supabase_auth.SupabaseVerifier(URL, "", lambda _url: JWKS)
        from fastapi.testclient import TestClient

        client = TestClient(app_mod.app)
        client.__enter__()
        clients.append(client)
        return client, app_mod

    yield make
    for c in clients:
        c.__exit__(None, None, None)
    for mod in ("app", "store", "supabase_auth"):
        sys.modules.pop(mod, None)


def install(client) -> dict:
    r = client.post("/v1/install", json={"app": "test", "os": "darwin", "arch": "arm64"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def th(app_mod, h) -> str:
    return app_mod.hash_token(h["Authorization"][7:])


ANTHROPIC_BODY = {"model": HAIKU, "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]}
GEMINI_BODY = {"contents": [{"role": "user", "parts": [{"text": "hi"}]}]}

# Every route that spends money: (method, path, json body, what it answers once past the gate with nothing upstream)
MODEL_ROUTES = [
    ("POST", "/v1/anthropic/messages", ANTHROPIC_BODY, 502),
    ("POST", "/v1/anthropic/v1/messages", ANTHROPIC_BODY, 502),
    ("POST", "/v1/gemini/gemini-3.8-flash:generateContent", GEMINI_BODY, 502),
    ("POST", "/v1/gemini/gemini-3.8-flash:streamGenerateContent", GEMINI_BODY, 502),
    ("POST", "/v1/gemini/v1beta/models/gemini-3.8-flash:generateContent", GEMINI_BODY, 502),
    ("POST", "/v1/gemini/v1beta/models/gemini-3.8-flash:streamGenerateContent", GEMINI_BODY, 502),
    ("POST", f"/v1/lessons/{VID}/build", None, 200),
]
ROUTE_IDS = [f"{m} {p}" for m, p, _, _ in MODEL_ROUTES]


def call(client, h, method, path, body):
    return client.request(method, path, headers=h, json=body)


def test_defaults():
    """Read the code defaults, not the test env: the flag is off and the token cap is 20M."""
    src = (CLOUD / "app.py").read_text()
    assert 'REQUIRE_SIGNIN = _env_bool("REQUIRE_SIGNIN", False)' in src
    assert 'LINKED_DAILY_TOKENS = _env_int("LINKED_DAILY_TOKENS", 20_000_000)' in src
    render = (CLOUD / "render.yaml").read_text()
    assert '- key: REQUIRE_SIGNIN\n        value: "0"' in render


def test_flag_defaults_to_off_when_unset(make_cloud):
    client, app_mod = make_cloud(unset=("REQUIRE_SIGNIN", "LINKED_DAILY_TOKENS"))
    assert app_mod.REQUIRE_SIGNIN is False and app_mod.LINKED_DAILY_TOKENS == 20_000_000
    assert client.get("/healthz").json()["require_signin"] is False


# --------------------------------------------------------------------------- 1. REQUIRE_SIGNIN

@pytest.mark.parametrize("method,path,body,passed", MODEL_ROUTES, ids=ROUTE_IDS)
def test_flag_off_anonymous_installs_still_reach_every_model_route(make_cloud, method, path, body, passed):
    client, _ = make_cloud(REQUIRE_SIGNIN="0")
    r = call(client, install(client), method, path, body)
    assert r.status_code == passed, r.text


@pytest.mark.parametrize("method,path,body,passed", MODEL_ROUTES, ids=ROUTE_IDS)
def test_flag_on_anonymous_install_gets_signin_required_on_every_model_route(make_cloud, method, path, body, passed):
    client, app_mod = make_cloud(REQUIRE_SIGNIN="1")
    h = install(client)
    r = call(client, h, method, path, body)
    assert r.status_code == 401 and r.json() == SIGNIN_BODY
    assert r.headers["x-should-retry"] == "false"
    assert app_mod.store.requests_today(th(app_mod, h)) == 0  # nothing counted, nothing reserved
    assert app_mod.store.builds_in_month(th(app_mod, h)) == 0


@pytest.mark.parametrize("method,path,body,passed", MODEL_ROUTES, ids=ROUTE_IDS)
def test_flag_on_linked_install_passes_every_model_route(make_cloud, method, path, body, passed):
    client, app_mod = make_cloud(REQUIRE_SIGNIN="1")
    h = install(client)
    app_mod.store.link_user(th(app_mod, h), USER)
    r = call(client, h, method, path, body)
    assert r.status_code == passed, r.text


def test_flag_on_signing_in_through_v1_link_unlocks_the_install(make_cloud):
    client, _ = make_cloud(REQUIRE_SIGNIN="1")
    h = install(client)
    assert client.post("/v1/anthropic/v1/messages", headers=h, json=ANTHROPIC_BODY).status_code == 401
    r = client.post("/v1/link", headers=h, json={"access_token": access_token()})
    assert r.status_code == 200 and r.json()["user_id"] == USER
    assert client.post("/v1/anthropic/v1/messages", headers=h, json=ANTHROPIC_BODY).status_code == 502


def test_flag_on_gemini_off_still_answers_signin_first(make_cloud):
    client, _ = make_cloud(REQUIRE_SIGNIN="1", ALLOWED_GEMINI_MODELS="none")
    h = install(client)
    r = client.post("/v1/gemini/gemini-3.8-flash:generateContent", headers=h, json=GEMINI_BODY)
    assert r.status_code == 401 and r.json() == SIGNIN_BODY


def test_flag_on_token_errors_keep_their_own_answers(make_cloud):
    client, app_mod = make_cloud(REQUIRE_SIGNIN="1")
    r = client.post("/v1/anthropic/v1/messages", headers={"Authorization": "Bearer mi_unknown"}, json=ANTHROPIC_BODY)
    assert r.status_code == 401 and r.json()["error"]["type"] == "authentication_error"
    r = client.post("/v1/anthropic/v1/messages", json=ANTHROPIC_BODY)
    assert r.status_code == 401 and r.json()["error"]["type"] == "authentication_error"
    h = install(client)
    prefix = th(app_mod, h)[:12]
    assert client.post(f"/admin/tokens/{prefix}/disable", headers=ADMIN).status_code == 200
    r = client.post("/v1/anthropic/v1/messages", headers=h, json=ANTHROPIC_BODY)
    assert r.status_code == 403 and r.json()["error"]["type"] == "permission_error"


def test_flag_on_pro_is_not_exempt(make_cloud):
    client, app_mod = make_cloud(REQUIRE_SIGNIN="1")
    h = install(client)
    prefix = th(app_mod, h)[:12]
    assert client.post(f"/admin/tokens/{prefix}/plan", json={"plan": "pro"}, headers=ADMIN).status_code == 200
    assert client.post("/v1/anthropic/v1/messages", headers=h, json=ANTHROPIC_BODY).status_code == 401


def test_flag_on_non_model_routes_stay_open(make_cloud):
    client, app_mod = make_cloud(REQUIRE_SIGNIN="1")
    health = client.get("/healthz")
    assert health.status_code == 200 and health.json()["require_signin"] is True
    h = install(client)  # /v1/install
    r = client.post("/v1/register", json={"install_id": "x", "app_version": "1", "platform": "darwin"})
    assert r.status_code == 200
    r = client.post("/v1/events", headers=h, json={"events": [{"name": "step_passed", "at": "2026-11-22T00:00:00Z"}]})
    assert r.status_code == 202
    r = client.get(f"/v1/lessons/{VID}?schema=1", headers=h)  # a cache read is free
    assert r.status_code == 404 and r.json()["error"]["type"] == "lesson_not_cached"
    r = client.post("/v1/link", headers=h, json={"access_token": access_token()})
    assert r.status_code == 200
    other = install(client)
    r = client.post("/v1/account/delete", headers=other, json={})  # signed out delete
    assert r.status_code == 200 and r.json()["install"] is True
    assert SIGNIN_BODY["error"] not in r.text


# --------------------------------------------------------------------------- 2. per-user daily caps

def _midnight_iso() -> str:
    from datetime import timedelta
    now = datetime.now(UTC)
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _assert_user_cap(r, unit: str) -> dict:
    assert r.status_code == 429, r.text
    err = r.json()["error"]
    assert err["type"] == "miyagi_quota" and err["limit"] == "user_daily_cap" and err["scope"] == "account"
    assert err["unit"] == unit
    assert err["message"] == "You've used today's free help. It resets at midnight UTC."
    assert err["resets_at"] == _midnight_iso()
    assert r.headers["x-should-retry"] == "false" and int(r.headers["retry-after"]) >= 60
    return err


def test_user_daily_token_cap_counts_every_install_of_the_user(make_cloud):
    client, app_mod = make_cloud(LINKED_DAILY_TOKENS="1000")
    a, b, loner = install(client), install(client), install(client)
    for h in (a, b):
        app_mod.store.link_user(th(app_mod, h), USER)
    app_mod.store.add_tokens(th(app_mod, a), "anthropic", HAIKU, 600, 0, 0.0)
    assert client.post("/v1/anthropic/v1/messages", headers=b, json=ANTHROPIC_BODY).status_code == 502  # 600 < 1000
    app_mod.store.add_tokens(th(app_mod, b), "anthropic", HAIKU, 0, 400, 0.0)
    for h in (a, b):
        err = _assert_user_cap(client.post("/v1/anthropic/v1/messages", headers=h, json=ANTHROPIC_BODY), "tokens")
        assert err["used"] == 1000 and err["cap"] == 1000
    r = client.post("/v1/gemini/gemini-3.8-flash:generateContent", headers=a, json=GEMINI_BODY)
    _assert_user_cap(r, "tokens")
    # anonymous installs have no token cap (their dollars are capped per install and per network)
    app_mod.store.add_tokens(th(app_mod, loner), "anthropic", HAIKU, 5000, 5000, 0.0)
    assert client.post("/v1/anthropic/v1/messages", headers=loner, json=ANTHROPIC_BODY).status_code == 502


def test_user_daily_usd_cap_answers_user_daily_cap(make_cloud):
    client, app_mod = make_cloud(LINKED_DAILY_USD="0.50")
    h = install(client)
    app_mod.store.link_user(th(app_mod, h), USER)
    app_mod.store.add_tokens(th(app_mod, h), "anthropic", HAIKU, 10, 10, 0.50)
    err = _assert_user_cap(client.post("/v1/anthropic/v1/messages", headers=h, json=ANTHROPIC_BODY), "usd")
    assert err["used"] == 0.5 and err["cap"] == 0.5


def test_anonymous_install_cap_keeps_its_own_shape(make_cloud):
    client, app_mod = make_cloud(FREE_DAILY_USD="0.05")
    h = install(client)
    app_mod.store.add_tokens(th(app_mod, h), "anthropic", HAIKU, 10, 10, 0.05)
    err = client.post("/v1/anthropic/v1/messages", headers=h, json=ANTHROPIC_BODY).json()["error"]
    assert err["limit"] == "daily_spend" and err["scope"] == "install" and "unit" not in err


def test_global_brake_is_checked_before_the_user_caps(make_cloud):
    client, app_mod = make_cloud(DAILY_USD_CAP="1.00", LINKED_DAILY_USD="0.50", LINKED_DAILY_TOKENS="10")
    h = install(client)
    app_mod.store.link_user(th(app_mod, h), USER)
    app_mod.store.add_tokens(th(app_mod, h), "anthropic", HAIKU, 100, 100, 1.00)
    err = client.post("/v1/anthropic/v1/messages", headers=h, json=ANTHROPIC_BODY).json()["error"]
    assert err["limit"] == "daily_usd"


def test_pro_skips_the_user_token_cap(make_cloud):
    client, app_mod = make_cloud(LINKED_DAILY_TOKENS="10")
    h = install(client)
    app_mod.store.link_user(th(app_mod, h), USER)
    app_mod.store.add_tokens(th(app_mod, h), "anthropic", HAIKU, 100, 100, 0.0)
    assert client.post(f"/admin/tokens/{th(app_mod, h)[:12]}/plan", json={"plan": "pro"}, headers=ADMIN).status_code == 200
    assert client.post("/v1/anthropic/v1/messages", headers=h, json=ANTHROPIC_BODY).status_code == 502


# --------------------------------------------------------------------------- 3. lesson builds per user

def _build(client, h, vid):
    return client.post(f"/v1/lessons/{vid}/build", headers=h)


def test_build_cap_is_per_user_across_linked_installs(make_cloud):
    client, app_mod = make_cloud(FREE_LESSON_BUILDS_PER_MONTH="3")
    a, b, loner = install(client), install(client), install(client)
    for h in (a, b):
        app_mod.store.link_user(th(app_mod, h), USER)
    assert _build(client, a, "aaaaaaaaaaa").json()["builds"]["used"] == 1
    assert _build(client, a, "bbbbbbbbbbb").json()["builds"]["used"] == 2
    # the same video from the user's other Mac is free, and lets that Mac share the lesson
    r = _build(client, b, "aaaaaaaaaaa")
    assert r.status_code == 200 and r.json()["builds"]["used"] == 2
    assert app_mod.store.has_build(th(app_mod, b), "aaaaaaaaaaa")
    assert _build(client, b, "ccccccccccc").json()["builds"]["used"] == 3
    r = _build(client, b, "ddddddddddd")
    assert r.status_code == 429 and r.json()["error"]["type"] == "miyagi_lesson_quota"
    assert _build(client, a, "eeeeeeeeeee").status_code == 429  # the other Mac too
    # the cache miss tells either Mac how many are left for the account
    miss = client.get(f"/v1/lessons/{VID}?schema=1", headers=a).json()["error"]["builds"]
    assert miss["used"] == 3 and miss["cap"] == 3
    # an anonymous install keeps its own count
    assert _build(client, loner, "ddddddddddd").status_code == 200


def test_anonymous_build_cap_is_still_per_install(make_cloud):
    client, _ = make_cloud(FREE_LESSON_BUILDS_PER_MONTH="1")
    a, b = install(client), install(client)
    assert _build(client, a, "aaaaaaaaaaa").status_code == 200
    assert _build(client, a, "bbbbbbbbbbb").status_code == 429
    assert _build(client, b, "bbbbbbbbbbb").status_code == 200

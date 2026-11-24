"""POST /v1/session: the desktop app's sign-in call (verify, link, then plan, caps and the sign-in mode), offline.

JWTs are signed here and checked against an injected JWKS; nothing reaches Supabase or a provider.

    cd cloud && python -m pytest tests -q
"""

from __future__ import annotations

import importlib
import json
import logging
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

jwt = pytest.importorskip("jwt")
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402

CLOUD = Path(__file__).resolve().parents[1]
ADMIN_TOKEN = "miyagi-tests-admin-0123456789-abcdefghijklmnop"
ADMIN = {"X-Admin-Token": ADMIN_TOKEN}
URL = "https://example-project.supabase.co"
USER = "5a8c1e2f-7b3d-4c9a-8e6f-0d1c2b3a4f5e"
OTHER = "9e8d7c6b-5a4f-4e3d-8c2b-1a0f9e8d7c6b"
EMAIL = "learner.private@example.com"
HAIKU = "claude-haiku-5-5"
KEY = ec.generate_private_key(ec.SECP256R1())
JWKS = {"keys": [json.loads(jwt.algorithms.ECAlgorithm.to_jwk(KEY.public_key())) | {"kid": "k1", "alg": "ES256", "use": "sig"}]}


def access_token(sub: str = USER, verified: bool | None = True, **claims) -> str:
    now = int(time.time())
    payload = {"sub": sub, "aud": "authenticated", "iss": f"{URL}/auth/v1", "iat": now, "exp": now + 3600,
               "role": "authenticated", "is_anonymous": False, "email": EMAIL,
               "app_metadata": {"provider": "google", "providers": ["google"]},
               "user_metadata": {"email": EMAIL, **({"email_verified": verified} if verified is not None else {})}}
    return jwt.encode(payload | claims, KEY, algorithm="ES256", headers={"kid": "k1"})


@pytest.fixture
def make_cloud(tmp_path, monkeypatch):
    clients = []

    def make(fetcher=None, **env):
        base = {"ADMIN_TOKEN": ADMIN_TOKEN, "DB_PATH": str(tmp_path / "miyagi.db"), "SUPABASE_URL": URL,
                "ANTHROPIC_API_KEY": "fake-upstream-key", "UPSTREAM_ANTHROPIC_URL": "http://127.0.0.1:9/v1/messages",
                "REQUIRE_SIGNIN": "0", "LINKED_DAILY_USD": "3.00", "LINKED_DAILY_TOKENS": "20000000"}
        for k, v in {**base, **env}.items():
            monkeypatch.setenv(k, v)
        monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
        monkeypatch.syspath_prepend(str(CLOUD))
        for mod in ("app", "store", "supabase_auth"):
            sys.modules.pop(mod, None)
        app_mod = importlib.import_module("app")
        app_mod.verifier = app_mod.supabase_auth.SupabaseVerifier(URL, "", fetcher or (lambda _url: JWKS))
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


def install(client) -> tuple[str, dict]:
    r = client.post("/v1/install", json={"app": "test", "os": "darwin", "arch": "arm64"})
    assert r.status_code == 200
    tok = r.json()["token"]
    return tok, {"Authorization": f"Bearer {tok}"}


def session(client, h, token=None):
    return client.post("/v1/session", headers=h, json={"access_token": token if token is not None else access_token()})


def midnight() -> str:
    now = datetime.now(UTC)
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_first_call_links_the_install_and_answers_the_account(make_cloud):
    client, app_mod = make_cloud()
    tok, h = install(client)
    th = app_mod.hash_token(tok)
    assert app_mod.store.get_link(th) is None
    r = session(client, h)
    assert r.status_code == 200, r.text
    assert r.json() == {"account": {"id": USER, "email_verified": True}, "plan": "free", "linked": True,
                        "caps": {"daily_usd": 3.0, "used_usd": 0.0, "tokens": 20_000_000, "used_tokens": 0,
                                 "resets_at": midnight()},
                        "signin_mode": "off"}
    assert app_mod.store.get_link(th)["user_id"] == USER


def test_idempotent(make_cloud):
    client, app_mod = make_cloud()
    tok, h = install(client)
    first = session(client, h)
    linked_at = app_mod.store.get_link(app_mod.hash_token(tok))["linked_at"]
    second = session(client, h)
    assert first.status_code == second.status_code == 200 and first.json() == second.json()
    assert app_mod.store.get_link(app_mod.hash_token(tok))["linked_at"] == linked_at
    # an install already linked through /v1/link is fine too
    tok2, h2 = install(client)
    assert client.post("/v1/link", headers=h2, json={"access_token": access_token()}).json() == {"ok": True, "user_id": USER}
    assert session(client, h2).status_code == 200


def test_caps_numbers_are_the_users_whole_day(make_cloud):
    client, app_mod = make_cloud(LINKED_DAILY_USD="2.50", LINKED_DAILY_TOKENS="5000")
    tok_a, a = install(client)
    tok_b, b = install(client)
    tok_c, c = install(client)  # someone else's install: not counted
    assert session(client, a).status_code == 200
    assert session(client, b).status_code == 200
    assert session(client, c, access_token(sub=OTHER)).status_code == 200
    app_mod.store.add_tokens(app_mod.hash_token(tok_a), "anthropic", HAIKU, 1000, 200, 0.75)
    app_mod.store.add_tokens(app_mod.hash_token(tok_b), "anthropic", HAIKU, 300, 100, 0.25)
    app_mod.store.add_tokens(app_mod.hash_token(tok_c), "anthropic", HAIKU, 9999, 9999, 9.0)
    caps = session(client, a).json()["caps"]
    assert caps == {"daily_usd": 2.5, "used_usd": 1.0, "tokens": 5000, "used_tokens": 1600, "resets_at": midnight()}
    # the same numbers admit_call's caps read
    assert app_mod.store.user_usage_today(USER)[1:] == (1.0, 1600)


def test_pro_and_caps_off_read_null(make_cloud):
    client, app_mod = make_cloud(LINKED_DAILY_TOKENS="0")
    tok, h = install(client)
    body = session(client, h).json()
    assert body["caps"]["tokens"] is None and body["caps"]["daily_usd"] == 3.0
    prefix = app_mod.hash_token(tok)[:12]
    assert client.post(f"/admin/tokens/{prefix}/plan", json={"plan": "pro"}, headers=ADMIN).status_code == 200
    body = session(client, h).json()
    assert body["plan"] == "pro" and body["caps"]["daily_usd"] is None and body["caps"]["tokens"] is None


def test_email_verified_is_read_as_a_strict_boolean(make_cloud):
    client, _ = make_cloud()
    _, h = install(client)
    assert session(client, h, access_token(verified=None)).json()["account"]["email_verified"] is False
    assert session(client, h, access_token(verified="true")).json()["account"]["email_verified"] is False  # noqa


def test_bad_jwt(make_cloud):
    client, app_mod = make_cloud()
    tok, h = install(client)
    other_key = ec.generate_private_key(ec.SECP256R1())
    forged = jwt.encode({"sub": USER, "aud": "authenticated", "iss": f"{URL}/auth/v1", "exp": int(time.time()) + 60,
                         "role": "authenticated", "app_metadata": {"provider": "google"}}, other_key, algorithm="ES256",
                        headers={"kid": "k1"})
    for bad in (forged, "not-a-jwt", "", access_token(exp=int(time.time()) - 3600),
                access_token(app_metadata={"provider": "email"}), access_token(is_anonymous=True)):
        r = session(client, h, bad)
        assert r.status_code == 403 and r.json() == {"error": "bad_access_token"}, bad[:20]
    r = client.post("/v1/session", headers=h, json={})
    assert r.status_code == 403 and r.json() == {"error": "bad_access_token"}
    assert app_mod.store.get_link(app_mod.hash_token(tok)) is None


def test_unknown_missing_or_disabled_install_token(make_cloud):
    client, app_mod = make_cloud()
    for h in ({"Authorization": "Bearer mi_unknown"}, {}):
        r = session(client, h)
        assert r.status_code == 401 and r.json() == {"error": "bad_install_token"}
    tok, h = install(client)
    assert client.post(f"/admin/tokens/{app_mod.hash_token(tok)[:12]}/disable", headers=ADMIN).status_code == 200
    r = session(client, h)
    assert r.status_code == 401 and r.json() == {"error": "bad_install_token"}


def test_jwks_unreachable_is_503(make_cloud):
    def offline(_url):
        raise OSError("offline")

    client, _ = make_cloud(fetcher=offline)
    _, h = install(client)
    r = session(client, h)
    assert r.status_code == 503 and r.json() == {"error": "link_unavailable"}


def test_too_many_installs_like_link(make_cloud):
    client, _ = make_cloud(LINK_MAX_INSTALLS_PER_USER="1")
    _, a = install(client)
    _, b = install(client)
    assert session(client, a).status_code == 200
    r = session(client, b)
    assert r.status_code == 403 and r.json() == {"error": "too_many_installs"}


def test_no_email_or_tokens_in_answer_or_logs(make_cloud, caplog):
    client, _ = make_cloud()
    tok, h = install(client)
    jwt_token = access_token()
    with caplog.at_level(logging.DEBUG):
        r = session(client, h, jwt_token)
        session(client, h, "not-a-jwt")
        session(client, {"Authorization": "Bearer mi_unknown"}, jwt_token)
    assert r.status_code == 200
    for secret in (EMAIL, jwt_token, tok):
        assert secret not in r.text
        assert secret not in caplog.text
    assert USER not in caplog.text  # the account id is in the answer for the app, never in a log line
    assert any("/v1/session" in rec.getMessage() for rec in caplog.records)


@pytest.mark.parametrize("mode", ["off", "build", "all"])
def test_signin_mode_is_reflected_and_the_route_stays_open(make_cloud, mode):
    client, _ = make_cloud(REQUIRE_SIGNIN=mode)
    _, h = install(client)
    body = {"model": HAIKU, "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]}
    if mode == "all":
        assert client.post("/v1/anthropic/v1/messages", headers=h, json=body).status_code == 401
    r = session(client, h)
    assert r.status_code == 200 and r.json()["signin_mode"] == mode
    assert client.post("/v1/anthropic/v1/messages", headers=h, json=body).status_code == 502  # linked: past the gate


def test_rate_limited_per_ip_like_link(make_cloud):
    client, _ = make_cloud(RATE_LIMIT_PER_IP_PER_HOUR="4")
    _, h = install(client)  # 1
    assert [session(client, h).status_code for _ in range(3)] == [200, 200, 200]  # 2-4
    r = session(client, h)
    assert r.status_code == 429 and r.json()["error"]["limit"] == "ip_hourly"


def test_body_cap_like_link(make_cloud):
    client, _ = make_cloud()
    _, h = install(client)
    r = client.post("/v1/session", headers={**h, "content-type": "application/json"},
                    content=json.dumps({"access_token": "x" * (17 * 1024)}))
    assert r.status_code == 413


def test_link_answer_is_unchanged(make_cloud):
    client, _ = make_cloud()
    _, h = install(client)
    r = client.post("/v1/link", headers=h, json={"access_token": access_token()})
    assert r.status_code == 200 and r.json() == {"ok": True, "user_id": USER}

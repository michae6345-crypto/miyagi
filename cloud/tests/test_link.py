"""POST /v1/link and the Supabase JWT check (supabase_auth.py), offline.

Key pairs are generated here and served through an injected JWKS fetcher, so nothing reaches Supabase.
The Anthropic upstream points at a closed local port, so a forwarded call fails with 502, never a real call.

    cd cloud && python -m pytest tests -q
"""

from __future__ import annotations

import importlib
import json
import logging
import sys
import time
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa

CLOUD = Path(__file__).resolve().parents[1]
URL = "https://example-project.supabase.co"
ISS = f"{URL}/auth/v1"
SECRET = "legacy-test-secret-that-is-long-enough-for-hs256"
USER = "7f1c9a52-3b8e-4d0f-9a61-2c5e8b4d1f03"

EC_KEY = ec.generate_private_key(ec.SECP256R1())
RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_EC_KEY = ec.generate_private_key(ec.SECP256R1())


def _jwk(alg_cls, public_key, kid: str, alg: str) -> dict:
    return json.loads(alg_cls.to_jwk(public_key)) | {"kid": kid, "alg": alg, "use": "sig"}


JWKS = {"keys": [
    _jwk(jwt.algorithms.ECAlgorithm, EC_KEY.public_key(), "ec-1", "ES256"),
    _jwk(jwt.algorithms.RSAAlgorithm, RSA_KEY.public_key(), "rsa-1", "RS256"),
]}


def make_token(alg: str = "ES256", key=None, kid: str | None = "ec-1", **claims) -> str:
    now = int(time.time())
    payload = {"sub": USER, "aud": "authenticated", "iss": ISS, "iat": now, "exp": now + 3600,
               "role": "authenticated", "email": "learner@example.com"} | claims
    payload = {k: v for k, v in payload.items() if v is not None}
    if key is None:
        key = {"ES256": EC_KEY, "RS256": RSA_KEY, "HS256": SECRET}[alg]
    headers = {"kid": kid} if kid else {}
    return jwt.encode(payload, key, algorithm=alg, headers=headers)


class FakeJwks:
    """Injected fetcher: counts calls, can fail, never touches the network."""

    def __init__(self, doc: dict | None = JWKS) -> None:
        self.doc, self.calls, self.urls = doc, 0, []

    def __call__(self, url: str) -> dict:
        self.calls += 1
        self.urls.append(url)
        if self.doc is None:
            raise OSError("offline")
        return self.doc


@pytest.fixture
def cloud(tmp_path, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "admin-test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "miyagi.db"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-upstream-key")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-upstream-key")
    monkeypatch.setenv("UPSTREAM_ANTHROPIC_URL", "http://127.0.0.1:9/v1/messages")  # closed port: never a real call
    monkeypatch.setenv("UPSTREAM_GEMINI_URL", "http://127.0.0.1:9/{model}:{method}")
    monkeypatch.setenv("SUPABASE_URL", URL)
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    monkeypatch.syspath_prepend(str(CLOUD))
    for mod in ("app", "store", "supabase_auth"):
        sys.modules.pop(mod, None)
    app_mod = importlib.import_module("app")
    from fastapi.testclient import TestClient

    def use(fetcher=None, secret: str = "", **kw):
        app_mod.verifier = app_mod.supabase_auth.SupabaseVerifier(URL, secret, fetcher or FakeJwks(), **kw)
        return app_mod.verifier

    use()
    with TestClient(app_mod.app) as client:
        yield client, app_mod, use
    for mod in ("app", "store", "supabase_auth"):
        sys.modules.pop(mod, None)


def install(client) -> tuple[str, dict]:
    r = client.post("/v1/install", json={"app": "test", "os": "darwin", "arch": "arm64"})
    assert r.status_code == 200
    tok = r.json()["token"]
    return tok, {"Authorization": f"Bearer {tok}"}


def link(client, headers, access_token):
    return client.post("/v1/link", headers=headers, json={"access_token": access_token})


# --------------------------------------------------------------------------- the contract


def test_valid_es256_links(cloud):
    client, app_mod, _ = cloud
    tok, h = install(client)
    r = link(client, h, make_token("ES256"))
    assert r.status_code == 200
    assert r.json() == {"ok": True, "user_id": USER}
    row = app_mod.store.get_link(app_mod.hash_token(tok))
    assert row["user_id"] == USER and row["linked_at"] > 0


def test_valid_rs256_links(cloud):
    client, _, _ = cloud
    _, h = install(client)
    r = link(client, h, make_token("RS256", kid="rsa-1"))
    assert r.status_code == 200 and r.json()["user_id"] == USER


def test_expired_token(cloud):
    client, _, _ = cloud
    _, h = install(client)
    r = link(client, h, make_token(exp=int(time.time()) - 5))
    assert r.status_code == 403 and r.json() == {"error": "bad_access_token"}


def test_missing_exp(cloud):
    client, _, _ = cloud
    _, h = install(client)
    assert link(client, h, make_token(exp=None)).status_code == 403


def test_wrong_audience(cloud):
    client, _, _ = cloud
    _, h = install(client)
    r = link(client, h, make_token(aud="anon"))
    assert r.status_code == 403 and r.json() == {"error": "bad_access_token"}


def test_wrong_issuer(cloud):
    client, _, _ = cloud
    _, h = install(client)
    r = link(client, h, make_token(iss="https://someone-else.supabase.co/auth/v1"))
    assert r.status_code == 403 and r.json() == {"error": "bad_access_token"}


def test_bad_signature(cloud):
    client, _, _ = cloud
    _, h = install(client)
    forged = make_token("ES256", key=OTHER_EC_KEY, kid="ec-1")  # right kid, wrong private key
    r = link(client, h, forged)
    assert r.status_code == 403 and r.json() == {"error": "bad_access_token"}


def test_tampered_payload(cloud):
    client, _, _ = cloud
    _, h = install(client)
    head, _, sig = make_token().split(".")
    body = jwt.utils.base64url_encode(json.dumps({"sub": "someone-else", "aud": "authenticated", "iss": ISS,
                                                  "exp": int(time.time()) + 3600}).encode()).decode()
    assert link(client, h, f"{head}.{body}.{sig}").status_code == 403


def test_unknown_kid(cloud):
    client, _, _ = cloud
    _, h = install(client)
    assert link(client, h, make_token("ES256", key=OTHER_EC_KEY, kid="ec-unknown")).status_code == 403


def test_hs256_with_secret(cloud):
    client, _, use = cloud
    use(secret=SECRET)
    _, h = install(client)
    r = link(client, h, make_token("HS256", kid=None))
    assert r.status_code == 200 and r.json() == {"ok": True, "user_id": USER}


def test_hs256_wrong_secret(cloud):
    client, _, use = cloud
    use(secret=SECRET)
    _, h = install(client)
    r = link(client, h, make_token("HS256", key="some-other-secret-that-is-also-long-enough", kid=None))
    assert r.status_code == 403 and r.json() == {"error": "bad_access_token"}


def test_hs256_without_secret_is_unavailable(cloud):
    client, _, _ = cloud
    _, h = install(client)
    r = link(client, h, make_token("HS256", kid=None))
    assert r.status_code == 503 and r.json() == {"error": "link_unavailable"}


def test_hs256_secret_from_env(cloud, monkeypatch):
    _, app_mod, _ = cloud
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    v = app_mod.supabase_auth.SupabaseVerifier.from_env(FakeJwks())
    assert v.secret == SECRET and v.issuer == ISS
    assert v.verify(make_token("HS256", kid=None))["sub"] == USER


def test_public_key_is_not_an_hmac_secret(cloud):
    """Algorithm confusion: an HS256 token signed with the published public key must not pass."""
    client, _, use = cloud
    use(secret=SECRET)
    _, h = install(client)
    pem = jwt.algorithms.RSAAlgorithm.to_jwk(RSA_KEY.public_key())
    import hashlib, hmac, base64  # noqa: E401  (hand-rolled so PyJWT's own guard does not stop the encode)
    seg = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()  # noqa: E731
    head = seg(json.dumps({"alg": "HS256", "typ": "JWT", "kid": "rsa-1"}).encode())
    body = seg(json.dumps({"sub": USER, "aud": "authenticated", "iss": ISS, "exp": int(time.time()) + 3600}).encode())
    sig = seg(hmac.new(pem.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest())
    assert link(client, h, f"{head}.{body}.{sig}").status_code == 403


@pytest.mark.parametrize("bad", ["", "not-a-jwt", "a.b.c", None, 42])
def test_garbage_access_token(cloud, bad):
    client, _, _ = cloud
    _, h = install(client)
    r = client.post("/v1/link", headers=h, json={"access_token": bad})
    assert r.status_code == 403 and r.json() == {"error": "bad_access_token"}


def test_alg_none_rejected(cloud):
    client, _, _ = cloud
    _, h = install(client)
    tok = jwt.encode({"sub": USER, "aud": "authenticated", "iss": ISS, "exp": int(time.time()) + 3600}, None, algorithm="none")
    assert link(client, h, tok).status_code == 403


def test_missing_body_is_bad_access_token(cloud):
    client, _, _ = cloud
    _, h = install(client)
    r = client.post("/v1/link", headers=h, content=b"not json")
    assert r.status_code == 403 and r.json() == {"error": "bad_access_token"}


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer mi_not-a-real-token"}, {"Authorization": "Bearer " + "x" * 300}])
def test_bad_install_token(cloud, headers):
    client, _, _ = cloud
    r = link(client, headers, make_token())
    assert r.status_code == 401 and r.json() == {"error": "bad_install_token"}


def test_disabled_install_cannot_link(cloud):
    client, app_mod, _ = cloud
    tok, h = install(client)
    app_mod.store.set_disabled(app_mod.hash_token(tok)[:16], True)
    assert link(client, h, make_token()).status_code == 401


def test_install_token_checked_before_access_token(cloud):
    client, _, use = cloud
    use(FakeJwks(None))
    r = link(client, {"Authorization": "Bearer mi_unknown"}, make_token())
    assert r.status_code == 401


def test_relink_is_idempotent(cloud):
    client, app_mod, _ = cloud
    tok, h = install(client)
    assert link(client, h, make_token()).status_code == 200
    first = app_mod.store.get_link(app_mod.hash_token(tok))
    r = link(client, h, make_token("RS256", kid="rsa-1"))
    assert r.status_code == 200 and r.json() == {"ok": True, "user_id": USER}
    assert app_mod.store.get_link(app_mod.hash_token(tok)) == first  # same pair: linked_at kept


def test_link_to_another_account_replaces_user(cloud):
    client, app_mod, _ = cloud
    tok, h = install(client)
    assert link(client, h, make_token()).status_code == 200
    r = link(client, h, make_token(sub="0b9e6a1d-other-user"))
    assert r.status_code == 200 and r.json()["user_id"] == "0b9e6a1d-other-user"
    assert app_mod.store.get_link(app_mod.hash_token(tok))["user_id"] == "0b9e6a1d-other-user"


def test_no_jwks_is_unavailable(cloud):
    client, _, use = cloud
    use(FakeJwks(None))
    _, h = install(client)
    r = link(client, h, make_token())
    assert r.status_code == 503 and r.json() == {"error": "link_unavailable"}


def test_empty_jwks_is_unavailable(cloud):
    client, _, use = cloud
    use(FakeJwks({"keys": []}))
    _, h = install(client)
    assert link(client, h, make_token()).status_code == 503


def test_no_jwks_with_secret_still_unavailable_for_es256(cloud):
    client, _, use = cloud
    use(FakeJwks(None), secret=SECRET)
    _, h = install(client)
    assert link(client, h, make_token()).status_code == 503
    assert link(client, h, make_token("HS256", kid=None)).status_code == 200


# --------------------------------------------------------------------------- JWKS cache


def test_jwks_url_and_cache(cloud):
    client, _, use = cloud
    clock = [1000.0]
    fake = FakeJwks()
    use(fake, clock=lambda: clock[0])
    _, h = install(client)
    for _ in range(3):
        assert link(client, h, make_token()).status_code == 200
    assert fake.calls == 1 and fake.urls == [f"{ISS}/.well-known/jwks.json"]
    clock[0] += 599
    assert link(client, h, make_token()).status_code == 200
    assert fake.calls == 1
    clock[0] += 2  # past 10 minutes
    assert link(client, h, make_token()).status_code == 200
    assert fake.calls == 2


def test_stale_jwks_used_when_refresh_fails(cloud):
    client, _, use = cloud
    clock = [1000.0]
    fake = FakeJwks()
    use(fake, clock=lambda: clock[0])
    _, h = install(client)
    assert link(client, h, make_token()).status_code == 200
    fake.doc = None
    clock[0] += 700
    assert link(client, h, make_token()).status_code == 200  # stale keys beat a 503
    assert fake.calls == 2


def test_failed_fetch_backs_off(cloud):
    client, _, use = cloud
    clock = [1000.0]
    fake = FakeJwks(None)
    use(fake, clock=lambda: clock[0])
    _, h = install(client)
    assert link(client, h, make_token()).status_code == 503
    assert link(client, h, make_token()).status_code == 503
    assert fake.calls == 1
    fake.doc = JWKS
    clock[0] += 31
    assert link(client, h, make_token()).status_code == 200
    assert fake.calls == 2


def test_unknown_kid_refetches_for_rotation(cloud):
    client, _, use = cloud
    clock = [1000.0]
    fake = FakeJwks()
    use(fake, clock=lambda: clock[0])
    _, h = install(client)
    assert link(client, h, make_token()).status_code == 200
    rotated = make_token("ES256", key=OTHER_EC_KEY, kid="ec-2")
    assert link(client, h, rotated).status_code == 403  # just fetched: no refetch yet
    assert fake.calls == 1
    fake.doc = {"keys": JWKS["keys"] + [_jwk(jwt.algorithms.ECAlgorithm, OTHER_EC_KEY.public_key(), "ec-2", "ES256")]}
    clock[0] += 61
    assert link(client, h, rotated).status_code == 200
    assert fake.calls == 2


# --------------------------------------------------------------------------- the rest of the proxy


def test_unlinked_install_still_uses_the_proxy(cloud):
    client, _, _ = cloud
    _, h = install(client)
    r = client.post("/v1/anthropic/messages", headers=h,
                    json={"model": "claude-haiku-5-5", "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 502  # got past auth to the (closed) upstream


def test_user_id_in_usage_and_logs_without_tokens(cloud, caplog):
    client, app_mod, _ = cloud
    tok, h = install(client)
    access = make_token()
    with caplog.at_level(logging.INFO, logger="miyagi.cloud"):
        assert link(client, h, access).status_code == 200
        client.post("/v1/anthropic/messages", headers=h,
                    json={"model": "claude-haiku-5-5", "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]})
    text = caplog.text
    assert f"user={USER}" in text
    assert tok not in text and access not in text and access.split(".")[2] not in text
    report = client.get("/admin/usage", headers={"x-admin-token": "admin-test"}).json()
    rows = [r for r in report["by_token"] if r["token"] == app_mod.hash_token(tok)[:12]]
    assert rows and rows[0]["user_id"] == USER

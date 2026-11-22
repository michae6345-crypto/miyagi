"""Enforced caps (check_quota) and the DAILY_USD_CAP abuse brake, offline.

The upstreams point at a closed local port, so a call that gets past the caps fails with 502
(upstream_unreachable) and never reaches a real provider.

    cd cloud && python -m pytest tests -q
"""

from __future__ import annotations

import importlib
import sys
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

CLOUD = Path(__file__).resolve().parents[1]
ADMIN_TOKEN = "miyagi-tests-admin-0123456789-abcdefghijklmnop"  # 32+ characters: a weak token turns /admin off
ADMIN = {"X-Admin-Token": ADMIN_TOKEN}


def _cloud(tmp_path, monkeypatch, unset=(), **env):
    base = {"ADMIN_TOKEN": ADMIN_TOKEN, "DB_PATH": str(tmp_path / "miyagi.db"),
            "ANTHROPIC_API_KEY": "fake-upstream-key", "GEMINI_API_KEY": "fake-upstream-key",
            "UPSTREAM_ANTHROPIC_URL": "http://127.0.0.1:9/v1/messages",  # closed port: never a real call
            "UPSTREAM_GEMINI_URL": "http://127.0.0.1:9/{model}:{method}",
            "FREE_DAILY_REQUESTS": "0", "DAILY_USD_CAP": "0", "ALLOWED_GEMINI_MODELS": "gemini-3.8-flash",
            "FREE_DAILY_USD": "0", "LINKED_DAILY_REQUESTS": "0", "LINKED_DAILY_USD": "0",
            "ANON_DAILY_USD_PER_NETWORK": "0"}
    for k, v in {**base, **env}.items():
        monkeypatch.setenv(k, v)
    for k in unset:  # back to the default in app.py
        monkeypatch.delenv(k, raising=False)
    monkeypatch.syspath_prepend(str(CLOUD))
    for mod in ("app", "store"):
        sys.modules.pop(mod, None)
    return importlib.import_module("app")


@pytest.fixture
def make_cloud(tmp_path, monkeypatch):
    clients = []

    def make(unset=(), **env):
        app_mod = _cloud(tmp_path, monkeypatch, unset, **env)
        from fastapi.testclient import TestClient

        client = TestClient(app_mod.app)
        client.__enter__()
        clients.append(client)
        return client, app_mod

    yield make
    for c in clients:
        c.__exit__(None, None, None)
    for mod in ("app", "store"):
        sys.modules.pop(mod, None)


def install(client) -> tuple[dict, str]:
    r = client.post("/v1/install", json={"app": "test", "os": "darwin", "arch": "arm64"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["token_id"]


def anthropic(client, h, role: str | None = "coach"):
    body = {"model": "claude-haiku-5-5", "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]}
    headers = {**h, **({"x-miyagi-role": role} if role else {})}
    return client.post("/v1/anthropic/v1/messages", headers=headers, json=body)


def gemini(client, h, role: str | None = "lesson"):
    headers = {**h, **({"x-miyagi-role": role} if role else {})}
    return client.post("/v1/gemini/gemini-3.8-flash:generateContent", headers=headers, json={"contents": []})


# --------------------------------------------------------------------------- caps

def test_refused_calls_are_not_counted_and_every_role_counts_the_same(make_cloud):
    client, app_mod = make_cloud(FREE_DAILY_REQUESTS="4")
    h, _ = install(client)
    th = app_mod.hash_token(h["Authorization"][7:])
    assert anthropic(client, h, role="coach").status_code == 502
    assert anthropic(client, h, role="scene").status_code == 502
    assert gemini(client, h, role="lesson").status_code == 502
    assert anthropic(client, h, role=None).status_code == 502
    for role in ("coach", "scene", "lesson", "screen", None, "anything-else"):
        r = anthropic(client, h, role=role)
        assert r.status_code == 429 and r.json()["error"]["limit"] == "daily_requests"
    assert app_mod.store.requests_today(th) == 4


def test_daily_request_cap_covers_every_call(make_cloud):
    client, _ = make_cloud(FREE_DAILY_REQUESTS="3")
    h, _ = install(client)
    assert [anthropic(client, h, role=None).status_code for _ in range(3)] == [502, 502, 502]
    r = gemini(client, h)
    assert r.status_code == 429
    err = r.json()["error"]
    assert err["limit"] == "daily_requests" and err["used"] == 3 and err["cap"] == 3
    assert r.headers["x-should-retry"] == "false"
    # every install has its own
    other, _ = install(client)
    assert gemini(client, other).status_code == 502


def test_pro_has_no_per_install_caps(make_cloud):
    client, _ = make_cloud(FREE_DAILY_REQUESTS="1", FREE_DAILY_USD="0.01")
    h, token_id = install(client)
    assert client.post(f"/admin/tokens/{token_id}/plan", json={"plan": "pro"}, headers=ADMIN).status_code == 200
    assert [anthropic(client, h).status_code for _ in range(4)] == [502] * 4


def test_caps_hold_under_parallel_calls(make_cloud):
    client, app_mod = make_cloud()
    h, _ = install(client)
    th = app_mod.hash_token(h["Authorization"][7:])
    results: list[tuple[str | None, int, int]] = []
    lock = threading.Lock()

    def call():
        r = app_mod.store.admit_call(th, "anthropic", "claude-haiku-5-5", "coach", 0, usd_cap=0.625, reserve_usd=0.125)
        with lock:
            results.append(r)

    threads = [threading.Thread(target=call) for _ in range(40)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(1 for hit, _, _ in results if hit is None) == 5
    assert app_mod.store.role_requests_today(th, "coach") == 5
    assert app_mod.store.requests_today(th) == 5
    assert app_mod.store.usd_today_for(th) == 0.625


# --------------------------------------------------------------------------- DAILY_USD_CAP

@pytest.mark.parametrize("value", [None, "", "  ", "0"])
def test_global_brake_is_off_unless_set(make_cloud, value):
    """DAILY_USD_CAP is an abuse brake, off by default: a busy day does not stop everyone (D13)."""
    if value is None:
        client, app_mod = make_cloud(unset=("DAILY_USD_CAP",))
    else:
        client, app_mod = make_cloud(DAILY_USD_CAP=value)
    assert app_mod.DAILY_USD_CAP == 0
    h, _ = install(client)
    other, _ = install(client)
    th = app_mod.hash_token(h["Authorization"][7:])
    app_mod.store.add_tokens(th, "anthropic", "claude-haiku-5-5", 10**9, 10**9, 9999.0)
    assert anthropic(client, other).status_code == 502


def test_usd_cap_stops_every_install_until_midnight(make_cloud):
    client, app_mod = make_cloud(DAILY_USD_CAP="5")
    a, a_id = install(client)
    b, b_id = install(client)
    assert client.post(f"/admin/tokens/{b_id}/plan", json={"plan": "pro"}, headers=ADMIN).status_code == 200
    ta = app_mod.hash_token(a["Authorization"][7:])
    app_mod.store.add_tokens(ta, "anthropic", "claude-haiku-5-5", 1000, 1000, 4.99)
    assert anthropic(client, a).status_code == 502  # just under the cap
    app_mod.store.add_tokens(ta, "gemini", "gemini-3.8-flash", 1000, 1000, 0.02)
    for h in (a, b):  # pro included: it is a kill switch
        for r in (anthropic(client, h), gemini(client, h)):
            assert r.status_code == 429
            err = r.json()["error"]
            assert err["type"] == "miyagi_quota" and err["status"] == "MIYAGI_QUOTA" and err["code"] == 429
            assert err["limit"] == "daily_usd" and err["cap"] == 5.0 and err["used"] == 5.01
            assert r.headers["x-should-retry"] == "false"
            assert "—" not in err["message"] and "miyagi" in err["message"] and len(err["message"].split()) <= 12
            resets = datetime.strptime(err["resets_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            assert timedelta(0) < resets - datetime.now(UTC) <= timedelta(days=1)
    assert app_mod.store.usd_today() == 5.01
    # the shared lesson cache keeps working
    assert client.get("/v1/lessons/dQw4w9WgXcQ?schema=1", headers=a).status_code == 404


def test_usd_cap_counts_only_today(make_cloud):
    client, app_mod = make_cloud(DAILY_USD_CAP="1")
    h, _ = install(client)
    th = app_mod.hash_token(h["Authorization"][7:])
    yesterday = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")
    app_mod.store._q("INSERT INTO usage (token_hash, day, provider, model, usd) VALUES (?, ?, 'anthropic', 'm', 50)", (th, yesterday))
    assert app_mod.store.usd_today() == 0
    assert anthropic(client, h).status_code == 502

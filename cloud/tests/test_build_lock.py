"""The build claim lock on POST /v1/lessons/{id}/build (LESSON_CLAIM_TTL_S), offline.

The engine's client (server/lesson/cloud_cache.py on integration/live) reads 200 {"held": true} as "another install is
building this video": it polls GET for up to 12 s, then builds locally.

    cd cloud && python -m pytest tests -q
"""

from __future__ import annotations

import importlib
import json
import sys
import time
from pathlib import Path

import pytest

CLOUD = Path(__file__).resolve().parents[1]
ADMIN_TOKEN = "miyagi-tests-admin-0123456789-abcdefghijklmnop"
VID = "dQw4w9WgXcQ"
LESSON = {"title": "Build a CNN", "steps": [{"title": "Install torch", "start": 0, "end": 60}]}


@pytest.fixture
def make_cloud(tmp_path, monkeypatch):
    clients = []

    def make(**env):
        base = {"ADMIN_TOKEN": ADMIN_TOKEN, "DB_PATH": str(tmp_path / "miyagi.db"), "FREE_LESSON_BUILDS_PER_MONTH": "3",
                "LESSON_CLAIM_TTL_S": "600", "LESSON_SCHEMAS": "1,2", "LESSON_AUTO_APPROVE_VALIDATED": "0"}
        for k, v in {**base, **env}.items():
            monkeypatch.setenv(k, v)
        monkeypatch.syspath_prepend(str(CLOUD))
        for mod in ("app", "store"):
            sys.modules.pop(mod, None)
        app_mod = importlib.import_module("app")
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


def install(client) -> dict:
    r = client.post("/v1/install", json={"app": "test", "os": "darwin", "arch": "arm64"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def th(app_mod, h) -> str:
    return app_mod.hash_token(h["Authorization"][7:])


def build(client, h, vid=VID, schema=None):
    return client.post(f"/v1/lessons/{vid}/build" + (f"?schema={schema}" if schema else ""), headers=h)


def put(client, h, lesson=LESSON, vid=VID, schema=1):
    return client.put(f"/v1/lessons/{vid}", headers=h, content=json.dumps({"schema": schema, "lesson": lesson}))


def expire_all(app_mod) -> None:
    app_mod.store._q("UPDATE lesson_claims SET expires_at = ?", (time.time() - 1,))


def test_second_claim_is_held_and_counts_nothing(make_cloud):
    client, app_mod = make_cloud()
    a, b = install(client), install(client)
    r = build(client, a)
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["builds"]["used"] == 1
    r = build(client, b)
    assert r.status_code == 200 and r.json() == {"held": True}
    assert app_mod.store.builds_in_month(th(app_mod, b)) == 0
    assert not app_mod.store.has_build(th(app_mod, b), VID)
    assert app_mod.store.lesson_claims_of(th(app_mod, b)) == []
    # another video is not held
    assert build(client, b, vid="aaaaaaaaaaa").json()["ok"] is True


def test_claims_are_stored_by_token_hash_with_the_ttl(make_cloud):
    client, app_mod = make_cloud(LESSON_CLAIM_TTL_S="600")
    a = install(client)
    before = time.time()
    build(client, a)
    claims = app_mod.store.lesson_claims_of(th(app_mod, a))
    assert len(claims) == 1 and claims[0]["video_id"] == VID and claims[0]["schema"] == 0
    assert before + 599 <= claims[0]["expires_at"] <= time.time() + 601
    cols = [r["name"] for r in app_mod.store._q("PRAGMA table_info(lesson_claims)")]
    assert cols == ["video_id", "schema", "token_hash", "claimed_at", "expires_at"]


def test_own_reclaim_is_idempotent(make_cloud):
    client, app_mod = make_cloud()
    a = install(client)
    first = build(client, a).json()
    expires = app_mod.store.lesson_claims_of(th(app_mod, a))[0]["expires_at"]
    again = build(client, a)
    assert again.status_code == 200 and again.json()["ok"] is True
    assert again.json()["builds"]["used"] == first["builds"]["used"] == 1
    assert app_mod.store.lesson_claims_of(th(app_mod, a))[0]["expires_at"] == expires  # not extended


def test_expired_claims_are_ignored_and_pruned(make_cloud):
    client, app_mod = make_cloud()
    a, b = install(client), install(client)
    build(client, a)
    expire_all(app_mod)
    r = build(client, b)
    assert r.status_code == 200 and r.json()["ok"] is True  # a's expired claim no longer holds the video
    assert build(client, a).json() == {"held": True}  # now b holds it
    expire_all(app_mod)
    assert app_mod.store.prune()["lesson_claims"] == 2
    assert app_mod.store._q("SELECT COUNT(*) AS n FROM lesson_claims")[0]["n"] == 0


def test_ttl_zero_turns_the_lock_off(make_cloud):
    client, app_mod = make_cloud(LESSON_CLAIM_TTL_S="0")
    a, b = install(client), install(client)
    assert build(client, a).json()["ok"] is True and build(client, b).json()["ok"] is True
    assert app_mod.store._q("SELECT COUNT(*) AS n FROM lesson_claims")[0]["n"] == 0


def test_the_claimers_put_releases_the_claim(make_cloud):
    client, app_mod = make_cloud()
    a, b = install(client), install(client)
    build(client, a)
    assert build(client, b).json() == {"held": True}
    assert put(client, a).status_code == 201
    assert app_mod.store.lesson_claims_of(th(app_mod, a)) == []
    assert build(client, b).json()["ok"] is True


def test_a_refused_put_by_the_claimer_still_releases(make_cloud):
    client, app_mod = make_cloud()
    a, b = install(client), install(client)
    build(client, a)
    r = put(client, a, lesson={"steps": [{"title": "x", "unknown_key": 1}]})
    assert r.status_code == 400
    assert build(client, b).json()["ok"] is True


def test_a_stored_put_by_anyone_releases_every_claim_on_the_video(make_cloud):
    client, app_mod = make_cloud()
    a, b, c = install(client), install(client), install(client)
    build(client, b)  # b claimed first, then its claim ran out
    expire_all(app_mod)
    build(client, a)  # a holds the video now
    assert build(client, c).json() == {"held": True}
    assert put(client, b).status_code == 201  # b's lesson is stored
    assert app_mod.store.lesson_claims_of(th(app_mod, a)) == []
    assert build(client, c).json()["ok"] is True


def test_schemas(make_cloud):
    client, _ = make_cloud()
    a, b, c = install(client), install(client), install(client)
    assert build(client, a, schema=1).json()["ok"] is True
    assert build(client, b, schema=2).json()["ok"] is True  # another schema is another lesson
    assert build(client, c).json() == {"held": True}  # no schema (the engine): any claim on the video holds it
    assert build(client, c, schema=9).status_code == 400  # not in LESSON_SCHEMAS


def test_a_capped_claim_takes_no_lock(make_cloud):
    client, app_mod = make_cloud(FREE_LESSON_BUILDS_PER_MONTH="1")
    a, b = install(client), install(client)
    assert build(client, a, vid="aaaaaaaaaaa").status_code == 200
    r = build(client, a)
    assert r.status_code == 429 and r.json()["error"]["type"] == "miyagi_lesson_quota"
    assert build(client, b).json()["ok"] is True


def test_delete_account_wipes_the_callers_claims(make_cloud):
    client, app_mod = make_cloud()
    a, b = install(client), install(client)
    build(client, a)
    build(client, a, vid="aaaaaaaaaaa")
    th_a = th(app_mod, a)
    assert len(app_mod.store.lesson_claims_of(th_a)) == 2
    r = client.post("/v1/account/delete", headers=a, json={})
    assert r.status_code == 200 and r.json()["install"] is True
    assert app_mod.store.lesson_claims_of(th_a) == []
    assert build(client, b).json()["ok"] is True


def test_held_answer_matches_the_engine_client():
    """server/lesson/cloud_cache.py claim(): `r.status_code == 200 and body.get("held") is True` -> "held"."""
    src = (CLOUD / "app.py").read_text()
    assert 'return {"held": True}' in src

"""Shared lesson cache (GET/PUT /v1/lessons/{video_id}) and free tier caps, against a throwaway SQLite file.

No network: the Anthropic upstream points at a closed local port, so a call that gets past the caps fails
with 502 (upstream_unreachable), never reaching a real provider.

    cd cloud && python -m pytest tests -q
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

import pytest

CLOUD = Path(__file__).resolve().parents[1]
VID = "dQw4w9WgXcQ"
LESSON = {"title": "Build a CNN", "steps": [{"title": "Install torch", "start": 0, "end": 60}]}


@pytest.fixture
def cloud(tmp_path, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "admin-test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "miyagi.db"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-upstream-key")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-upstream-key")
    monkeypatch.setenv("UPSTREAM_ANTHROPIC_URL", "http://127.0.0.1:9/v1/messages")  # closed port: never a real call
    monkeypatch.setenv("UPSTREAM_GEMINI_URL", "http://127.0.0.1:9/{model}:{method}")
    monkeypatch.setenv("FREE_LESSON_BUILDS_PER_MONTH", "3")
    monkeypatch.setenv("FREE_COACH_CALLS_PER_DAY", "2")
    monkeypatch.setenv("MAX_LESSON_KB", "4")
    monkeypatch.syspath_prepend(str(CLOUD))
    for mod in ("app", "store"):
        sys.modules.pop(mod, None)
    app_mod = importlib.import_module("app")
    from fastapi.testclient import TestClient

    with TestClient(app_mod.app) as client:
        yield client, app_mod
    for mod in ("app", "store"):
        sys.modules.pop(mod, None)


def install(client) -> dict:
    r = client.post("/v1/install", json={"app": "test", "os": "darwin", "arch": "arm64"})
    assert r.status_code == 200
    tok = r.json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def put(client, h, vid=VID, schema=1, lesson=None):
    return client.put(f"/v1/lessons/{vid}", headers=h, content=json.dumps({"schema": schema, "lesson": lesson or LESSON}))


def test_lessons_need_an_install_token(cloud):
    client, _ = cloud
    assert client.get(f"/v1/lessons/{VID}?schema=1").status_code == 401
    assert client.put(f"/v1/lessons/{VID}", content="{}").status_code == 401
    assert client.post(f"/v1/lessons/{VID}/build").status_code == 401
    assert client.get(f"/v1/lessons/{VID}?schema=1", headers={"Authorization": "Bearer mi_nope"}).status_code == 401


def test_miss_build_upload_then_another_install_hits(cloud):
    client, _ = cloud
    a, b = install(client), install(client)
    miss = client.get(f"/v1/lessons/{VID}?schema=1", headers=a)
    assert miss.status_code == 404
    err = miss.json()["error"]
    assert err["type"] == "lesson_not_cached"
    assert err["builds"]["used"] == 0 and err["builds"]["cap"] == 3

    assert put(client, a).status_code == 403  # must claim a build first
    claim = client.post(f"/v1/lessons/{VID}/build", headers=a)
    assert claim.status_code == 200 and claim.json()["builds"]["used"] == 1
    r = put(client, a)
    assert r.status_code == 201 and r.json()["stored"] is True

    hit = client.get(f"/v1/lessons/{VID}?schema=1", headers=b)
    assert hit.status_code == 200
    body = hit.json()
    assert body["lesson"] == LESSON and body["schema"] == 1 and body["video_id"] == VID
    # a hit uses none of b's builds
    assert client.get("/v1/lessons/aaaaaaaaaaa?schema=1", headers=b).json()["error"]["builds"]["used"] == 0


def test_first_upload_wins(cloud):
    client, _ = cloud
    a, b = install(client), install(client)
    for h in (a, b):
        client.post(f"/v1/lessons/{VID}/build", headers=h)
    assert put(client, a).status_code == 201
    other = {"steps": [{"title": "something else"}]}
    assert put(client, b, lesson=other).status_code == 409
    assert client.get(f"/v1/lessons/{VID}?schema=1", headers=b).json()["lesson"] == LESSON


def test_schema_versions_are_separate_and_checked(cloud):
    client, _ = cloud
    a = install(client)
    client.post(f"/v1/lessons/{VID}/build", headers=a)
    assert put(client, a, schema=1).status_code == 201
    assert client.get(f"/v1/lessons/{VID}?schema=2", headers=a).status_code == 404
    assert put(client, a, schema=2).status_code == 201
    assert client.get(f"/v1/lessons/{VID}?schema=100", headers=a).json()["error"]["type"] == "schema_unsupported"
    assert client.get(f"/v1/lessons/{VID}", headers=a).status_code == 400  # schema is required
    assert client.get(f"/v1/lessons/{VID}?schema=abc", headers=a).status_code == 400
    assert put(client, a, schema=0).status_code == 400
    r = client.put(f"/v1/lessons/{VID}", headers=a, content=json.dumps({"schema": True, "lesson": LESSON}))
    assert r.status_code == 400


def test_bad_ids_and_bodies(cloud):
    client, _ = cloud
    a = install(client)
    assert client.get("/v1/lessons/short?schema=1", headers=a).status_code == 400
    assert client.post("/v1/lessons/has%20space!!/build", headers=a).status_code == 400
    client.post(f"/v1/lessons/{VID}/build", headers=a)
    assert client.put(f"/v1/lessons/{VID}", headers=a, content="not json").status_code == 400
    assert put(client, a, lesson={"steps": []}).status_code == 400
    assert put(client, a, lesson={"steps": ["x"]}).status_code == 400


def test_size_limit(cloud):
    client, _ = cloud
    a = install(client)
    client.post(f"/v1/lessons/{VID}/build", headers=a)
    big = {"steps": [{"title": "x" * 5000}]}  # MAX_LESSON_KB=4 in this fixture
    r = put(client, a, lesson=big)
    assert r.status_code == 413 and r.json()["error"]["type"] == "request_too_large"


def test_free_tier_three_new_builds_a_month(cloud):
    client, _ = cloud
    a = install(client)
    vids = ["aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"]
    for i, v in enumerate(vids, 1):
        r = client.post(f"/v1/lessons/{v}/build", headers=a)
        assert r.status_code == 200 and r.json()["builds"]["used"] == i
    again = client.post(f"/v1/lessons/{vids[0]}/build", headers=a)  # a retry of a claimed video is free
    assert again.status_code == 200 and again.json()["builds"]["used"] == 3
    r = client.post("/v1/lessons/ddddddddddd/build", headers=a)
    assert r.status_code == 429
    assert r.headers["x-should-retry"] == "false" and int(r.headers["retry-after"]) >= 60
    err = r.json()["error"]
    assert err["type"] == "miyagi_lesson_quota" and err["status"] == "MIYAGI_LESSON_QUOTA" and err["code"] == 429
    assert err["limit"] == "lesson_builds" and err["used"] == 3 and err["cap"] == 3
    assert err["resets_at"].endswith("Z")
    assert "—" not in err["message"]
    # another install still has its own three
    assert client.post("/v1/lessons/ddddddddddd/build", headers=install(client)).status_code == 200


def test_pro_plan_has_no_caps(cloud):
    client, _ = cloud
    r = client.post("/v1/install", json={})
    token, token_id = r.json()["token"], r.json()["token_id"]
    h = {"Authorization": f"Bearer {token}"}
    admin = {"X-Admin-Token": "admin-test"}
    assert client.post(f"/admin/tokens/{token_id}/plan", json={"plan": "pro"}).status_code == 401
    assert client.post(f"/admin/tokens/{token_id}/plan", json={"plan": "gold"}, headers=admin).status_code == 400
    assert client.post(f"/admin/tokens/{token_id}/plan", json={"plan": "pro"}, headers=admin).json()["plan"] == "pro"
    for v in ["aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc", "ddddddddddd", "eeeeeeeeeee"]:
        assert client.post(f"/v1/lessons/{v}/build", headers=h).status_code == 200


def _coach(client, h, role="coach"):
    body = {"model": "claude-haiku-5-5", "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]}
    return client.post("/v1/anthropic/v1/messages", headers={**h, "x-miyagi-role": role}, json=body)


def test_coach_calls_capped_per_day(cloud):
    client, _ = cloud
    a = install(client)
    # FREE_COACH_CALLS_PER_DAY=2: the first two get past the cap (and fail upstream: closed port, no real call)
    assert _coach(client, a).status_code == 502
    assert _coach(client, a).status_code == 502
    r = _coach(client, a)
    assert r.status_code == 429
    err = r.json()["error"]
    assert err["type"] == "miyagi_quota" and err["limit"] == "coach_calls" and err["cap"] == 2
    assert r.headers["x-should-retry"] == "false"
    # other roles are not coach calls
    assert _coach(client, a, role="lesson").status_code == 502


def test_admin_delete_lesson(cloud):
    client, _ = cloud
    a = install(client)
    client.post(f"/v1/lessons/{VID}/build", headers=a)
    put(client, a)
    admin = {"X-Admin-Token": "admin-test"}
    assert client.delete(f"/admin/lessons/{VID}").status_code == 401
    assert client.delete(f"/admin/lessons/{VID}", headers=admin).json()["deleted"] == 1
    assert client.get(f"/v1/lessons/{VID}?schema=1", headers=a).status_code == 404
    report = client.get("/admin/usage", headers=admin).json()
    assert report["lessons"]["cached"] == 0 and report["lessons"]["builds_this_month"] == 1


def test_old_database_gets_the_plan_column(tmp_path, monkeypatch):
    import sqlite3

    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE tokens (token_hash TEXT PRIMARY KEY, install_id TEXT NOT NULL, app_version TEXT NOT NULL, "
                "platform TEXT NOT NULL, created_at REAL NOT NULL, disabled INTEGER NOT NULL DEFAULT 0)")
    con.execute("INSERT INTO tokens VALUES ('abc', 'i', 'v', 'p', 0, 0)")
    con.commit()
    con.close()
    monkeypatch.syspath_prepend(str(CLOUD))
    sys.modules.pop("store", None)
    store = importlib.import_module("store")
    s = store.Store(str(db))
    assert s.get_token("abc")["plan"] == "free"
    sys.modules.pop("store", None)
    assert os.path.exists(db)

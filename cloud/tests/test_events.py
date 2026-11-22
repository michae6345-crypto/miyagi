"""POST /v1/events (product event counts) and the admin views of events and spend, offline.

    cd cloud && python -m pytest tests -q
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from test_caps import ADMIN, ADMIN_TOKEN, anthropic, install, make_cloud  # noqa: F401  (make_cloud is a fixture)


def ev(name="step_passed", props=None, at=None):
    return {"name": name, "at": at or datetime.now(UTC).isoformat().replace("+00:00", "Z"), "props": props or {}}


def test_events_counted_per_name_per_day_per_install(make_cloud):
    client, app_mod = make_cloud()
    a, _ = install(client)
    b, _ = install(client)
    body = {"source": "app", "app": "1.2.3", "platform": "darwin/arm64",  # the app's extra fields are ignored
            "events": [ev("step_passed"), ev("step_passed"), ev("hint_used")]}
    r = client.post("/v1/events", headers=a, json=body)
    assert r.status_code == 202 and r.json() == {"ok": True}
    assert client.post("/v1/events", headers=b, json={"events": [ev("step_passed")]}).status_code == 202
    ta = app_mod.hash_token(a["Authorization"][7:])
    assert app_mod.store.event_counts(ta) == {"step_passed": 2, "hint_used": 1}
    assert app_mod.store.event_counts() == {"step_passed": 3, "hint_used": 1}
    report = client.get("/admin/usage", headers=ADMIN).json()["events"]
    row = next(x for x in report if x["name"] == "step_passed")
    assert row["count"] == 3 and row["installs"] == 2


def test_events_keep_only_allowlisted_scalar_props(make_cloud):
    client, app_mod = make_cloud()
    h, _ = install(client)
    secret = "sk-ant-api03-SECRET"
    events = [
        ev("crash", {"kind": "renderer", "message": f"TypeError at /Users/someone/x.py {secret}"}),
        ev("lesson_built", {"built_by": "gemini", "steps": 7, "cached": False, "minutes": 12.5,
                            "title": "My private project", "query": "how do I", "mode": "a sentence with, punctuation!",
                            "level": {"nested": 1}, "steps_list": [1, 2]}),
        ev("cost_usd", {"usd": 0.25}),
        ev("cost_usd", {"usd": 0.5, "seconds": float("inf")}),
    ]
    # json.dumps writes inf as Infinity, which Python's json reads back: the prop check has to drop it
    assert client.post("/v1/events", headers=h, content=json.dumps({"events": events})).status_code == 202
    th = app_mod.hash_token(h["Authorization"][7:])
    rows = {(r["name"], r["key"], r["value"]): (r["count"], r["total"]) for r in app_mod.store.event_props_rows(th)}
    assert rows == {
        ("crash", "kind", "renderer"): (1, 0.0),
        ("lesson_built", "built_by", "gemini"): (1, 0.0),
        ("lesson_built", "steps", ""): (1, 7.0),
        ("lesson_built", "cached", "false"): (1, 0.0),
        ("lesson_built", "minutes", ""): (1, 12.5),
        ("cost_usd", "usd", ""): (2, 0.75),
    }
    # nothing of the dropped props reached the database files (the main file and its WAL)
    db = Path(app_mod.store.path)
    raw = b"".join(p.read_bytes() for p in db.parent.glob(db.name + "*"))
    assert b"renderer" in raw  # what was kept is visible to this check
    for leaked in (b"SECRET", b"someone", b"private project", b"how do I", b"punctuation"):
        assert leaked not in raw


def test_events_drop_unknown_and_malformed_items(make_cloud):
    client, app_mod = make_cloud()
    h, _ = install(client)
    events = [ev("step_passed"), ev("made_up_event"), "not an object", {"at": "x"}, {"name": 5}, ev("hint_used", props=["x"])]
    assert client.post("/v1/events", headers=h, json={"events": events}).status_code == 202
    th = app_mod.hash_token(h["Authorization"][7:])
    assert app_mod.store.event_counts(th) == {"step_passed": 1, "hint_used": 1}


def test_event_day_from_at(make_cloud):
    client, app_mod = make_cloud()
    h, _ = install(client)
    now = datetime.now(UTC)
    yesterday = (now - timedelta(days=1)).replace(hour=12)
    events = [ev("step_passed", at=yesterday.isoformat()),           # recent: its own day
              ev("step_passed", at="2001-01-01T00:00:00Z"),          # long ago: today
              ev("step_passed", at=(now + timedelta(days=3)).isoformat()),  # the future: today
              ev("step_passed", at="not a time"),
              {"name": "step_passed"}]                                # no at: today
    assert client.post("/v1/events", headers=h, json={"events": events}).status_code == 202
    th = app_mod.hash_token(h["Authorization"][7:])
    assert app_mod.store.event_counts(th, yesterday.strftime("%Y-%m-%d")) == {"step_passed": 1}
    assert app_mod.store.event_counts(th) == {"step_passed": 4}


def test_events_auth(make_cloud):
    client, _ = make_cloud()
    body = {"events": [ev()]}
    assert client.post("/v1/events", json=body).status_code == 401
    assert client.post("/v1/events", headers={"Authorization": "Bearer mi_nope"}, json=body).status_code == 401
    assert client.post("/v1/events", headers={"Authorization": "Bearer " + "x" * 300}, json=body).status_code == 401
    h, token_id = install(client)
    assert client.post(f"/admin/tokens/{token_id}/disable", headers=ADMIN).status_code == 200
    r = client.post("/v1/events", headers=h, json=body)
    assert r.status_code == 401 and r.json()["error"]["type"] == "authentication_error"


def test_events_size_limits(make_cloud):
    client, app_mod = make_cloud()
    h, _ = install(client)
    th = app_mod.hash_token(h["Authorization"][7:])
    assert client.post("/v1/events", headers=h, json={"events": [ev()] * 50}).status_code == 202
    r = client.post("/v1/events", headers=h, json={"events": [ev()] * 51})
    assert r.status_code == 413 and r.json()["error"]["type"] == "request_too_large"
    big = {"events": [ev(props={"kind": "x"})], "pad": "x" * (32 * 1024)}
    assert client.post("/v1/events", headers=h, json=big).status_code == 413
    assert app_mod.store.event_counts(th) == {"step_passed": 50}  # the refused requests stored nothing


def test_events_bad_bodies(make_cloud):
    client, _ = make_cloud()
    h, _ = install(client)
    for content in ("not json", "[]", '{"events": {}}', "{}", '{"events": "x"}'):
        assert client.post("/v1/events", headers=h, content=content).status_code == 400


def test_events_daily_cap_per_install(make_cloud):
    client, app_mod = make_cloud(EVENTS_PER_DAY_PER_INSTALL="60")
    h, _ = install(client)
    th = app_mod.hash_token(h["Authorization"][7:])
    for _ in range(3):
        assert client.post("/v1/events", headers=h, json={"events": [ev()] * 25}).status_code == 202
    assert app_mod.store.event_counts(th) == {"step_passed": 60}
    other, _ = install(client)
    assert client.post("/v1/events", headers=other, json={"events": [ev()]}).status_code == 202
    assert app_mod.store.event_counts() == {"step_passed": 61}


def test_usd_cap_leaves_events_working(make_cloud):
    client, app_mod = make_cloud(DAILY_USD_CAP="1")
    h, _ = install(client)
    app_mod.store.add_tokens(app_mod.hash_token(h["Authorization"][7:]), "anthropic", "claude-haiku-5-5", 10, 10, 2.5)
    assert anthropic(client, h).status_code == 429
    assert client.post("/v1/events", headers=h, json={"events": [ev()]}).status_code == 202


def test_admin_shows_events_and_spend(make_cloud):
    client, app_mod = make_cloud(DAILY_USD_CAP="25")
    h, _ = install(client)
    app_mod.store.add_tokens(app_mod.hash_token(h["Authorization"][7:]), "gemini", "gemini-3.8-flash", 10, 10, 1.25)
    client.post("/v1/events", headers=h, json={"events": [ev("lesson_completed")]})
    report = client.get("/admin/usage", headers=ADMIN).json()
    assert report["usd_today"] == 1.25
    assert [(e["name"], e["count"], e["installs"]) for e in report["events"]] == [("lesson_completed", 1, 1)]
    page = client.post("/admin", data={"admin_token": ADMIN_TOKEN}).text
    assert "Events per day" in page and "lesson_completed" in page and "global spend brake: $25.0" in page

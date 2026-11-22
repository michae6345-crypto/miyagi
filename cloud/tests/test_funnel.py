"""POST /v1/funnel (activation milestones) and GET /admin/funnel, offline.

    cd cloud && python -m pytest tests -q
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from test_caps import ADMIN, install, make_cloud  # noqa: F401  (make_cloud is a fixture)

STEPS = ["first_launch", "signed_in", "permissions_granted", "lesson_started", "step_passed", "lesson_finished"]


def iso(t: datetime) -> str:
    return t.astimezone(UTC).isoformat().replace("+00:00", "Z")


def ms(start: datetime, minutes: list[float], names=STEPS) -> dict:
    return {"milestones": [{"name": n, "at": iso(start + timedelta(minutes=m))} for n, m in zip(names, minutes)]}


def test_keeps_earliest_time_per_install_and_name(make_cloud):
    client, app_mod = make_cloud()
    h, _ = install(client)
    t0 = datetime.now(UTC) - timedelta(hours=2)
    r = client.post("/v1/funnel", headers=h, json=ms(t0, [0, 5]))
    assert r.status_code == 202 and r.json() == {"ok": True}
    # a later time for the same name never moves it; an earlier one does
    assert client.post("/v1/funnel", headers=h, json=ms(t0, [30, 1])).status_code == 202
    th = app_mod.hash_token(h["Authorization"][7:])
    rows = {r["name"]: r["first_at"] for r in app_mod.store.funnel_rows(th)}
    assert rows == {"first_launch": t0.timestamp(), "signed_in": (t0 + timedelta(minutes=1)).timestamp()}


def test_drops_unknown_names_bad_times_and_extra_fields(make_cloud):
    client, app_mod = make_cloud()
    h, _ = install(client)
    now = datetime.now(UTC)
    body = {"milestones": [
        {"name": "first_launch", "at": iso(now - timedelta(minutes=10)), "email": "a@b.co", "title": "secret"},
        {"name": "credit_card", "at": iso(now)},
        {"name": "signed_in", "at": "yesterday"},
        {"name": "lesson_started", "at": iso(now - timedelta(days=900))},  # too old: dropped
        {"name": "step_passed", "at": iso(now + timedelta(days=3))},  # from the future: counts as now
    ], "user_id": "someone"}
    assert client.post("/v1/funnel", headers=h, json=body).status_code == 202
    th = app_mod.hash_token(h["Authorization"][7:])
    rows = {r["name"]: r["first_at"] for r in app_mod.store.funnel_rows(th)}
    assert set(rows) == {"first_launch", "step_passed"}
    assert abs(rows["step_passed"] - now.timestamp()) < 60
    # the table has names and times only
    cols = [r[1] for r in app_mod.store._q("PRAGMA table_info(funnel)")]
    assert cols == ["token_hash", "name", "first_at"]


def test_auth_shape_and_size(make_cloud):
    client, _ = make_cloud()
    assert client.post("/v1/funnel", json={"milestones": []}).status_code == 401
    assert client.post("/v1/funnel", headers={"Authorization": "Bearer mi_nope"}, json={"milestones": []}).status_code == 401
    h, _ = install(client)
    assert client.post("/v1/funnel", headers=h, json={"events": []}).status_code == 400
    assert client.post("/v1/funnel", headers=h, content=b"not json").status_code == 400
    seven = {"milestones": [{"name": "first_launch", "at": iso(datetime.now(UTC))}] * 7}
    assert client.post("/v1/funnel", headers=h, json=seven).status_code == 413
    big = {"milestones": [{"name": "first_launch", "at": "x" * 3000}]}
    assert client.post("/v1/funnel", headers=h, json=big).status_code == 413


def test_admin_report_counts_shares_and_median_gaps(make_cloud):
    client, _ = make_cloud()
    t0 = datetime.now(UTC) - timedelta(days=1)
    a, _ = install(client)
    b, _ = install(client)
    c, _ = install(client)
    client.post("/v1/funnel", headers=a, json=ms(t0, [0, 2, 4, 10, 12, 30]))
    client.post("/v1/funnel", headers=b, json=ms(t0, [0, 4, 8]))
    client.post("/v1/funnel", headers=c, json=ms(t0, [0]))
    assert client.get("/admin/funnel").status_code in (401, 403)
    rep = client.get("/admin/funnel", headers=ADMIN).json()
    assert rep["installs"] == 3 and rep["installs_minted"] == 3
    steps = {s["name"]: s for s in rep["steps"]}
    assert [s["name"] for s in rep["steps"]] == STEPS
    assert steps["first_launch"]["installs"] == 3 and steps["first_launch"]["median_s_from_prev"] is None
    assert steps["signed_in"]["installs"] == 2 and steps["signed_in"]["share"] == round(2 / 3, 4)
    assert steps["signed_in"]["median_s_from_prev"] == 180.0  # 2 and 4 minutes
    assert steps["lesson_finished"]["installs"] == 1 and steps["lesson_finished"]["median_s_from_prev"] == 1080.0
    # days=0 is all time; a 1-hour-old cutoff (days counts whole days) keeps installs that launched yesterday out
    assert client.get("/admin/funnel?days=0", headers=ADMIN).json()["installs"] == 3
    assert client.get("/admin/funnel?days=1", headers=ADMIN).json()["installs"] == 0


def test_account_delete_removes_funnel_rows(make_cloud):
    client, app_mod = make_cloud()
    h, _ = install(client)
    client.post("/v1/funnel", headers=h, json=ms(datetime.now(UTC), [0, 1]))
    th = app_mod.hash_token(h["Authorization"][7:])
    assert app_mod.store.funnel_rows(th)
    n = app_mod.store.delete_account(th)
    assert n["funnel"] == 2 and app_mod.store.funnel_rows(th) == []

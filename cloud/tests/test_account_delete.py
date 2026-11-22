"""POST /v1/account/delete, the retention prune and the network hashes (data minimisation), offline.

Supabase is never reached: access tokens are signed with local keys served through an injected JWKS fetcher
(test_link.py), and the Admin API delete goes to an httpx.MockTransport. No upstream AI key is set.

    cd cloud && python -m pytest tests -q
"""

from __future__ import annotations

import importlib
import json
import logging
import sqlite3
import sys
import time
from datetime import UTC, datetime, timedelta

import httpx
import pytest

pytest.importorskip("jwt")  # PyJWT (cloud/requirements.txt), as in test_link.py

from test_link import ADMIN_TOKEN, CLOUD, URL, USER, FakeJwks, make_token  # noqa: E402

OTHER = "0d3e5b1c-7a29-4f86-b2c4-9e1f0a6d8c35"
SERVICE_KEY = "sb_secret_test-service-key"
ADMIN = {"X-Admin-Token": ADMIN_TOKEN}
VIDEO, VIDEO2 = "dQw4w9WgXcQ", "oHg5SJYRHA0"
HOOK = "https://hooks.example.test/alert"


class FakeSupabase:
    """The Admin API, as an httpx transport: records every request, answers `status` (or raises)."""

    def __init__(self, status: int = 200, fail: bool = False) -> None:
        self.status, self.fail, self.requests = status, fail, []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail:
            raise httpx.ConnectError("offline", request=request)
        return httpx.Response(self.status, json={})


@pytest.fixture
def make_cloud(tmp_path, monkeypatch):
    """make(service_key=..., **env) -> (client, app_mod, supabase). No upstream key is set; the JWKS and the Supabase
    Admin API are fakes."""
    clients = []

    def make(service_key: str | None = SERVICE_KEY, supabase: FakeSupabase | None = None, **env):
        for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_JWT_SECRET", "NET_HASH_KEY",
                  "ALERT_WEBHOOK_URL"):
            monkeypatch.delenv(k, raising=False)
        base = {"ADMIN_TOKEN": ADMIN_TOKEN, "DB_PATH": str(tmp_path / "miyagi.db"), "SUPABASE_URL": URL,
                "UPSTREAM_ANTHROPIC_URL": "http://127.0.0.1:9/v1/messages"}
        if service_key is not None:
            base["SUPABASE_SERVICE_ROLE_KEY"] = service_key
        for k, v in {**base, **env}.items():
            monkeypatch.setenv(k, v)
        monkeypatch.syspath_prepend(str(CLOUD))
        for mod in ("app", "store", "supabase_auth"):
            sys.modules.pop(mod, None)
        app_mod = importlib.import_module("app")
        app_mod.verifier = app_mod.supabase_auth.SupabaseVerifier(URL, "", FakeJwks())
        supabase = supabase or FakeSupabase()
        app_mod.supabase_transport = httpx.MockTransport(supabase)
        from fastapi.testclient import TestClient

        client = TestClient(app_mod.app)
        client.__enter__()
        clients.append(client)
        return client, app_mod, supabase

    yield make
    for c in clients:
        c.__exit__(None, None, None)
    for mod in ("app", "store", "supabase_auth"):
        sys.modules.pop(mod, None)


def new_install(client, ip: str = "198.51.100.7") -> tuple[dict, str]:
    r = client.post("/v1/install", headers={"X-Forwarded-For": ip}, json={"app": "test", "os": "darwin", "arch": "arm64"})
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    return {"Authorization": f"Bearer {tok}"}, tok


def delete(client, headers, body=None, **kw):
    return client.post("/v1/account/delete", headers=headers, json={} if body is None else body, **kw)


def seed(app_mod, h: str, video: str, approved: bool = False) -> None:
    """One row in every per-install table for install `h`."""
    s = app_mod.store
    s.add_tokens(h, "anthropic", "claude-haiku-5-5", 100, 20, 0.01)
    s.count_role(h, "coach")
    assert s.claim_build(h, video, 0)[0]
    s.add_events(h, [(datetime.now(UTC).date().isoformat(), "step_passed", {"kind": "code", "usd": 0.5})], 0)
    assert s.claim_lesson_put(h, 0)[0]
    lesson = {"title": video, "steps": []}
    digest = app_mod.lesson_hash(lesson)
    assert s.put_candidate(video, 1, h, json.dumps(lesson), digest, "203.0.113.0/24") is None
    if approved:
        assert len(s.approve_lesson(video, digest[:16], 1)) == 1
    assert s.claim_alert(f"token:{h[:12]}")


def rows_mentioning(app_mod, *needles: str) -> dict[str, int]:
    """Every row of every table where any cell contains any of `needles`, counted per table."""
    con = sqlite3.connect(app_mod.store.path)
    found: dict[str, int] = {}
    for (table,) in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'"):
        for row in con.execute(f"SELECT * FROM {table}"):
            if any(isinstance(v, str) and any(n in v for n in needles) for v in row):
                found[table] = found.get(table, 0) + 1
    con.close()
    return found


def table_counts(app_mod, h: str) -> dict[str, int]:
    con = sqlite3.connect(app_mod.store.path)
    out = {t: con.execute(f"SELECT COUNT(*) FROM {t} WHERE token_hash = ?", (h,)).fetchone()[0]
           for t in ("tokens", "links", "usage", "role_usage", "builds", "events", "event_props", "event_intake", "lesson_puts")}
    out["lesson_candidates"] = con.execute("SELECT COUNT(*) FROM lesson_candidates WHERE uploader = ?", (h,)).fetchone()[0]
    con.close()
    return out


# --------------------------------------------------------------------------- the contract


def test_signed_in_delete_wipes_the_user_and_every_linked_install(make_cloud):
    client, app_mod, supabase = make_cloud()
    ha, ta = new_install(client)
    hb, tb = new_install(client)
    hc, tc = new_install(client)  # another user's install
    hd, td = new_install(client)  # an anonymous install
    a, b, c, d = (app_mod.hash_token(t) for t in (ta, tb, tc, td))
    app_mod.store.link_user(a, USER)
    app_mod.store.link_user(b, USER)
    app_mod.store.link_user(c, USER)
    for h, v, approved in ((a, VIDEO, True), (b, VIDEO2, False), (c, VIDEO2, False), (d, VIDEO2, False)):
        seed(app_mod, h, v, approved)
    app_mod.store.link_user(c, OTHER)  # c moved from USER to OTHER after spending: a moved_usage row names USER
    assert rows_mentioning(app_mod, USER).get("moved_usage") == 1
    before_c, before_d = table_counts(app_mod, c), table_counts(app_mod, d)

    r = delete(client, ha, {"access_token": make_token()})
    assert r.status_code == 200 and r.json() == {"ok": True, "install": True, "account": "deleted"}

    # nothing anywhere still names the user, either install, or their token prefix
    assert rows_mentioning(app_mod, USER, a, b, a[:12], b[:12], ta, tb) == {}
    # another user's and an anonymous install's rows are untouched
    assert table_counts(app_mod, c) == before_c and table_counts(app_mod, d) == before_d
    assert app_mod.store.get_link(c)["user_id"] == OTHER
    # the approved shared lesson stays, unattributed; the deleted installs' pending uploads are gone
    row = app_mod.store._q("SELECT uploader, net, status FROM lesson_candidates WHERE video_id = ?", (VIDEO,))
    assert [dict(x) | {"uploader": x["uploader"][:8]} for x in row] == [{"uploader": "deleted-", "net": "", "status": "approved"}]
    got = client.get(f"/v1/lessons/{VIDEO}?schema=1", headers=hc)
    assert got.status_code == 200 and got.json()["lesson"]["title"] == VIDEO
    # the Supabase auth user is deleted through the Admin API with the service key
    assert len(supabase.requests) == 1
    req = supabase.requests[0]
    assert req.method == "DELETE" and str(req.url) == f"{URL}/auth/v1/admin/users/{USER}"
    assert req.headers["apikey"] == SERVICE_KEY and req.headers["authorization"] == f"Bearer {SERVICE_KEY}"
    assert app_mod.store.deletion_requests() == []
    # both deleted installs are dead; the others still work
    for h in (ha, hb):
        assert client.get(f"/v1/lessons/{VIDEO}?schema=1", headers=h).status_code == 401
    assert client.get(f"/v1/lessons/{VIDEO}?schema=1", headers=hd).status_code == 200


def test_signed_out_delete_wipes_only_the_calling_install(make_cloud):
    client, app_mod, supabase = make_cloud()
    ha, ta = new_install(client)
    hb, tb = new_install(client)
    a, b = app_mod.hash_token(ta), app_mod.hash_token(tb)
    app_mod.store.link_user(a, USER)
    app_mod.store.link_user(b, USER)
    seed(app_mod, a, VIDEO)
    seed(app_mod, b, VIDEO2)
    before_b = table_counts(app_mod, b)

    r = delete(client, ha)  # {}
    assert r.status_code == 200 and r.json() == {"ok": True, "install": True, "account": "none"}
    assert rows_mentioning(app_mod, a, a[:12], ta) == {}
    assert table_counts(app_mod, b) == before_b and app_mod.store.get_link(b)["user_id"] == USER
    assert supabase.requests == []  # no access token: the account is not touched

    # an empty body and {"access_token": null} are the signed-out form too
    hd, td = new_install(client)
    assert client.post("/v1/account/delete", headers=hd).json()["account"] == "none"
    he, _ = new_install(client)
    assert delete(client, he, {"access_token": None}).json()["account"] == "none"


def test_anonymous_install_delete_keeps_its_network_spend_counted(make_cloud):
    """Deleting a spent anonymous install and minting a new one cannot reset ANON_DAILY_USD_PER_NETWORK, and the
    day's total still holds what it cost. Neither keeps anything that names the install."""
    client, app_mod, _ = make_cloud(ANON_DAILY_USD_PER_NETWORK="0.50", FREE_DAILY_USD="5")
    h, tok = new_install(client, "192.0.2.10")
    th = app_mod.hash_token(tok)
    app_mod.store.add_tokens(th, "anthropic", "claude-haiku-5-5", 10, 10, 0.50)
    assert delete(client, h).status_code == 200
    assert rows_mentioning(app_mod, th, th[:12], "192.0.2.10") == {}
    assert app_mod.store.usd_today() == pytest.approx(0.50)
    _, tok2 = new_install(client, "192.0.2.10")
    # no upstream key is set, so ask the caps directly (what /v1/anthropic runs before forwarding)
    r = app_mod.check_quota(app_mod.hash_token(tok2), None, "anthropic", "claude-haiku-5-5", 0.01, dry_run=True)
    assert r is not None and r.status_code == 429 and json.loads(r.body)["error"]["scope"] == "network"


def test_bad_access_token_deletes_nothing(make_cloud):
    client, app_mod, supabase = make_cloud()
    h, tok = new_install(client)
    th = app_mod.hash_token(tok)
    app_mod.store.link_user(th, USER)
    seed(app_mod, th, VIDEO)
    before = table_counts(app_mod, th)
    for bad in ("not-a-jwt", make_token(exp=int(time.time()) - 3600), make_token(sub=None), make_token(is_anonymous=True),
                make_token(app_metadata={"provider": "email"}), 42):
        r = delete(client, h, {"access_token": bad})
        assert r.status_code == 403 and r.json() == {"error": "bad_access_token"}, bad
    assert table_counts(app_mod, th) == before and supabase.requests == []
    # not a JSON object: 400, nothing deleted
    r = client.post("/v1/account/delete", headers={**h, "content-type": "application/json"}, content=b"[1, 2]")
    assert r.status_code == 400 and r.json() == {"error": "bad_request"}
    # the JWKS cannot be fetched: 503, nothing deleted, the app retries
    app_mod.verifier = app_mod.supabase_auth.SupabaseVerifier(URL, "", FakeJwks(None))
    r = delete(client, h, {"access_token": make_token()})
    assert r.status_code == 503 and r.json() == {"error": "delete_unavailable"}
    assert table_counts(app_mod, th) == before


def test_unknown_disabled_and_repeated_calls_get_401(make_cloud):
    client, app_mod, _ = make_cloud()
    h, tok = new_install(client)
    assert delete(client, h, {"access_token": make_token()}).json()["account"] == "deleted"
    r = delete(client, h, {"access_token": make_token()})  # the same token again: already deleted
    assert r.status_code == 401 and r.json() == {"error": "bad_install_token"}
    assert delete(client, h).status_code == 401
    assert delete(client, {"Authorization": "Bearer mi_never-minted"}).status_code == 401
    assert delete(client, {}).status_code == 401
    h2, tok2 = new_install(client)
    app_mod.store.set_disabled(app_mod.hash_token(tok2)[:16], True)
    assert delete(client, h2).json() == {"error": "bad_install_token"}


def test_pending_when_the_service_key_is_missing_then_admin_retry(make_cloud):
    sent: list[dict] = []
    client, app_mod, supabase = make_cloud(service_key=None, ALERT_WEBHOOK_URL=HOOK)
    app_mod._dispatch = sent.append
    h, tok = new_install(client)
    th = app_mod.hash_token(tok)
    app_mod.store.link_user(th, USER)
    seed(app_mod, th, VIDEO)

    r = delete(client, h, {"access_token": make_token()})
    assert r.status_code == 200 and r.json() == {"ok": True, "install": True, "account": "pending"}
    assert supabase.requests == []
    # the cloud data is gone already; only the minimal request row names the user
    assert rows_mentioning(app_mod, USER, th, th[:12]) == {"deletion_requests": 1}
    assert [x["user_id"] for x in app_mod.store.deletion_requests()] == [USER]
    assert len(sent) == 1 and "pending" in json.dumps(sent[0]) and USER not in json.dumps(sent[0])
    # /admin shows it
    listed = client.get("/admin/deletions", headers=ADMIN).json()
    assert listed["service_key"] is False and [x["user_id"] for x in listed["pending"]] == [USER]
    assert client.get("/admin/deletions").status_code == 401
    page = client.post("/admin", data={"admin_token": ADMIN_TOKEN}).text
    assert "Account deletions pending" in page and "<b>1</b>" in page.split("Account deletions pending", 1)[1][:120]

    # still no key: the retry keeps it pending
    assert client.post("/admin/deletions/retry", headers=ADMIN).json()["deleted"] == 0
    # the key is set (a redeploy): the retry deletes the Supabase user and the request
    app_mod.SUPABASE_SERVICE_ROLE_KEY = SERVICE_KEY
    out = client.post("/admin/deletions/retry", headers=ADMIN).json()
    assert out == {"deleted": 1, "pending": []}
    assert [str(q.url) for q in supabase.requests] == [f"{URL}/auth/v1/admin/users/{USER}"]
    assert rows_mentioning(app_mod, USER) == {}


@pytest.mark.parametrize("fake, account", [
    (FakeSupabase(500), "pending"),
    (FakeSupabase(401), "pending"),
    (FakeSupabase(fail=True), "pending"),
    (FakeSupabase(404), "deleted"),  # already gone in Supabase: done
    (FakeSupabase(204), "deleted"),
])
def test_supabase_answers(make_cloud, fake, account):
    client, app_mod, supabase = make_cloud(supabase=fake)
    h, _ = new_install(client)
    assert delete(client, h, {"access_token": make_token()}).json()["account"] == account
    assert len(supabase.requests) == 1
    assert bool(app_mod.store.deletion_requests()) == (account == "pending")


def test_retry_also_wipes_what_the_account_linked_since(make_cloud):
    client, app_mod, _ = make_cloud(service_key=None)
    h, _ = new_install(client)
    assert delete(client, h, {"access_token": make_token()}).json()["account"] == "pending"
    h2, tok2 = new_install(client)  # the user signs in again before the retry
    assert client.post("/v1/link", headers=h2, json={"access_token": make_token()}).status_code == 200
    app_mod.SUPABASE_SERVICE_ROLE_KEY = SERVICE_KEY
    assert client.post("/admin/deletions/retry", headers=ADMIN).json()["deleted"] == 1
    assert app_mod.store.get_token(app_mod.hash_token(tok2)) is None and rows_mentioning(app_mod, USER) == {}


def test_service_key_is_trimmed_and_listed_in_render_yaml(make_cloud):
    _, app_mod, _ = make_cloud(service_key=f'  "{SERVICE_KEY}"\n')
    assert app_mod.SUPABASE_SERVICE_ROLE_KEY == SERVICE_KEY
    render = (CLOUD / "render.yaml").read_text()
    block = render.split("key: SUPABASE_SERVICE_ROLE_KEY", 1)[1].split("- key:", 1)[0]
    assert "sync: false" in block and "value:" not in block


def test_delete_is_rate_limited_per_ip_and_body_capped(make_cloud):
    client, app_mod, _ = make_cloud(RATE_LIMIT_PER_IP_PER_HOUR="2", REGISTER_LIMIT_PER_HOUR="100")
    ip = {"X-Forwarded-For": "192.0.2.77"}
    h, _ = new_install(client, "192.0.2.76")
    big = {"access_token": "x" * (app_mod.LINK_MAX_BODY + 10)}
    assert client.post("/v1/account/delete", headers={**h, **ip}, json=big).status_code == 413
    for _ in range(2):
        assert client.post("/v1/account/delete", headers={"Authorization": "Bearer mi_guess", **ip}, json={}).status_code == 401
    r = client.post("/v1/account/delete", headers={**h, **ip}, json={})
    assert r.status_code == 429 and r.json()["error"]["limit"] == "ip_hourly"
    assert app_mod.store.get_token(app_mod.hash_token(h["Authorization"][7:])) is not None  # nothing deleted


def test_log_lines_never_carry_the_account_id_tokens_or_addresses(make_cloud, caplog):
    client, app_mod, _ = make_cloud(service_key=None)
    with caplog.at_level(logging.INFO, logger="miyagi.cloud"):
        h, tok = new_install(client, "192.0.2.99")
        access = make_token()
        assert client.post("/v1/link", headers=h, json={"access_token": access}).status_code == 200
        client.get(f"/v1/lessons/{VIDEO}?schema=1", headers=h)
        assert delete(client, h, {"access_token": access}).json()["account"] == "pending"
        client.get("/admin/usage", headers={"X-Admin-Token": "wrong", "X-Forwarded-For": "192.0.2.99"})
    text = caplog.text
    assert "account delete: 1 install(s), signed in" in text and "linked=1" in text
    for secret in (USER, tok, access, "192.0.2.99", SERVICE_KEY):
        assert secret not in text


# --------------------------------------------------------------------------- data minimisation


def test_networks_are_stored_only_as_keyed_hashes(make_cloud):
    client, app_mod, _ = make_cloud(LESSON_PUTS_PER_DAY="5")
    h, tok = new_install(client, "192.0.2.33")
    th = app_mod.hash_token(tok)
    assert client.post(f"/v1/lessons/{VIDEO}/build", headers=h).status_code == 200
    r = client.put(f"/v1/lessons/{VIDEO}", headers={**h, "X-Forwarded-For": "192.0.2.33"},
                   json={"schema": 1, "lesson": {"title": "t", "steps": []}})
    assert r.status_code in (201, 400), r.text  # stored, or refused by the lesson validator: either way no address
    row = app_mod.store.get_token(th)
    assert row["mint_net"].startswith("n1:") and row["mint_net"] == app_mod.store.hash_net("192.0.2.33")
    assert rows_mentioning(app_mod, "192.0.2", "192.0.2.33") == {}
    bucket = app_mod.store._q("SELECT bucket FROM mints")[0]["bucket"]
    assert bucket == app_mod.store.hash_net("192.0.2.33")
    # the hash is keyed: another key gives another hash
    other = app_mod.store.__class__(app_mod.store.path + ".other", net_key=b"another key")
    assert other.hash_net("192.0.2.33") != app_mod.store.hash_net("192.0.2.33")
    assert app_mod.store.hash_net(row["mint_net"]) == row["mint_net"]  # idempotent


def test_linking_drops_the_mint_network_and_approval_drops_the_lesson_network(make_cloud):
    client, app_mod, _ = make_cloud()
    h, tok = new_install(client)
    th = app_mod.hash_token(tok)
    assert app_mod.store.get_token(th)["mint_net"]
    assert client.post("/v1/link", headers=h, json={"access_token": make_token()}).status_code == 200
    assert app_mod.store.get_token(th)["mint_net"] is None
    seed(app_mod, th, VIDEO, approved=True)
    assert app_mod.store._q("SELECT net FROM lesson_candidates")[0]["net"] == ""


def test_old_database_networks_are_hashed_on_open(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(CLOUD))
    monkeypatch.setenv("NET_HASH_KEY", "k")
    sys.modules.pop("store", None)
    store_mod = importlib.import_module("store")
    db = str(tmp_path / "old.db")
    s = store_mod.Store(db)
    s.add_token("a" * 64, "client-install-id", "1", "darwin", mint_net="198.51.100.4")
    s.add_token("b" * 64, "i", "1", "darwin", mint_net="198.51.100.4")
    s._db.execute("UPDATE tokens SET mint_net = '198.51.100.4', install_id = 'client-install-id'")  # as before this version
    s._db.execute("INSERT INTO mints (bucket, hour, n) VALUES ('198.51.100.4', ?, 3)", (int(time.time() // 3600),))
    s._db.execute("INSERT INTO lesson_candidates (video_id, schema, uploader, body, bytes, body_hash, net, status, created_at) "
                  "VALUES ('v', 1, 'u', '{}', 2, 'h', '198.51.100.0/24', 'pending', ?), "
                  "('w', 1, 'u', '{}', 2, 'h', '198.51.100.0/24', 'approved', ?)", (time.time(), time.time()))
    s._db.execute("INSERT INTO moved_usage (token_hash, day, from_user, from_net, requests, usd) VALUES ('c', ?, NULL, "
                  "'198.51.100.4', 1, 0.1)", (store_mod.today(),))
    s._db.close()
    s2 = store_mod.Store(db)  # the new version opens it
    con = sqlite3.connect(db)
    dump = "\n".join(str(r) for t in ("tokens", "mints", "lesson_candidates", "moved_usage") for r in con.execute(f"SELECT * FROM {t}"))
    assert "198.51.100" not in dump and "client-install-id" not in dump
    want = s2.hash_net("198.51.100.4")
    assert {s2.get_token(x * 64)["mint_net"] for x in "ab"} == {want}  # grouping kept
    assert s2.mint_check("198.51.100.4", 4, 0, 0)["hit"] is None and s2.mint_check("198.51.100.4", 4, 0, 0)["hit"] == "hour"
    nets = {r["status"]: r["net"] for r in s2._q("SELECT status, net FROM lesson_candidates")}
    assert nets == {"pending": s2.hash_net("198.51.100.0/24"), "approved": ""}
    sys.modules.pop("store", None)


def _days_ago(n: int) -> str:
    return (datetime.now(UTC) - timedelta(days=n)).strftime("%Y-%m-%d")


def _seed_old(s, h: str, days: int) -> None:
    d = _days_ago(days)
    s._db.execute("INSERT INTO usage (token_hash, day, provider, model, requests, input_tokens, output_tokens, usd) "
                  "VALUES (?, ?, 'anthropic', 'claude-haiku-5-5', 2, 100, 10, 0.25)", (h, d))
    s._db.execute("INSERT INTO role_usage (token_hash, day, role, requests) VALUES (?, ?, 'coach', 2)", (h, d))
    s._db.execute("INSERT INTO events (token_hash, day, name, count) VALUES (?, ?, 'step_passed', 3)", (h, d))
    s._db.execute("INSERT INTO event_props (token_hash, day, name, key, value, count, total) "
                  "VALUES (?, ?, 'step_passed', 'usd', '', 3, 1.5)", (h, d))
    s._db.execute("INSERT INTO builds (token_hash, month, video_id, created_at) VALUES (?, ?, ?, ?)",
                  (h, d[:7], f"v{days}", time.time() - days * 86400))
    for t, col in (("event_intake", "taken"), ("lesson_puts", "n")):
        s._db.execute(f"INSERT INTO {t} (token_hash, day, {col}) VALUES (?, ?, 1)", (h, d))
    s._db.execute("INSERT INTO moved_usage (token_hash, day, from_user, requests, usd) VALUES (?, ?, 'u', 1, 0.1)", (h, d))
    s._db.execute("INSERT INTO alerts_sent (day, key, sent_at) VALUES (?, ?, 0)", (d, f"token:{h[:12]}"))


def test_prune_folds_and_drops_old_per_install_rows(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(CLOUD))
    sys.modules.pop("store", None)
    store_mod = importlib.import_module("store")
    s = store_mod.Store(str(tmp_path / "p.db"), net_key=b"k")
    a, b = "a" * 64, "b" * 64
    for h in (a, b):
        _seed_old(s, h, 40)  # past retention
    _seed_old(s, a, 34)  # inside retention (34 days: kept even when asked for 1 day)
    s._db.execute("INSERT INTO mints (bucket, hour, n) VALUES ('n1:x', ?, 1)", (int(time.time() // 3600) - 49,))
    s._db.execute("INSERT INTO lesson_candidates (video_id, schema, uploader, body, bytes, body_hash, net, status, created_at) "
                  "VALUES ('old', 1, ?, '{}', 2, 'h', '', 'pending', ?), ('kept', 1, ?, '{}', 2, 'h', '', 'approved', ?)",
                  (a, time.time() - 20 * 86400, a, time.time() - 400 * 86400))

    n = s.prune(retain_days=1, pending_max_age_s=14 * 86400)  # below the minimum: 35 days are kept
    assert n["usage"] == 2 and n["events"] == 2 and n["builds"] == 2 and n["mints"] == 1 and n["lesson_candidates"] == 1
    old, kept = _days_ago(40), _days_ago(34)
    for t in ("usage", "role_usage", "events", "event_props"):
        rows = s._q(f"SELECT token_hash, day FROM {t}")
        assert sorted((r["token_hash"][:1], r["day"]) for r in rows) == sorted(
            [("a", kept)] + ([("*", old)] if t != "role_usage" else [])), t
    # folded totals: both installs' numbers, under no install
    u = s._q("SELECT requests, input_tokens, usd FROM usage WHERE token_hash = '*'")[0]
    assert (u["requests"], u["input_tokens"], round(u["usd"], 2)) == (4, 200, 0.5)
    assert s._q("SELECT count FROM events WHERE token_hash = '*'")[0]["count"] == 6
    p = s._q("SELECT count, total FROM event_props WHERE token_hash = '*'")[0]
    assert (p["count"], p["total"]) == (6, 3.0)
    assert [r["video_id"] for r in s._q("SELECT video_id FROM builds")] == ["v34"]
    for t in ("event_intake", "lesson_puts", "moved_usage", "alerts_sent"):  # short-lived: today's caps only
        assert s._q(f"SELECT COUNT(*) AS n FROM {t}")[0]["n"] == 0, t
    assert [r["video_id"] for r in s._q("SELECT video_id FROM lesson_candidates")] == ["kept"]
    # a second run changes nothing (the folded rows are not folded again)
    assert not any(s.prune().values())
    assert s._q("SELECT requests FROM usage WHERE token_hash = '*'")[0]["requests"] == 4
    sys.modules.pop("store", None)


def test_mint_network_ttl_is_optional(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(CLOUD))
    sys.modules.pop("store", None)
    s = importlib.import_module("store").Store(str(tmp_path / "t.db"), net_key=b"k")
    s.add_token("o" * 64, "", "1", "darwin", mint_net="192.0.2.1")
    s.add_token("y" * 64, "", "1", "darwin", mint_net="192.0.2.1")
    s._db.execute("UPDATE tokens SET created_at = ? WHERE token_hash = ?", (time.time() - 10 * 86400, "o" * 64))
    assert s.prune()["mint_net"] == 0  # default: kept while the install is anonymous
    assert s.prune(mint_net_days=7)["mint_net"] == 1
    assert s.get_token("o" * 64)["mint_net"] is None and s.get_token("y" * 64)["mint_net"] == s.hash_net("192.0.2.1")
    sys.modules.pop("store", None)


def test_prune_runs_at_startup(make_cloud, tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(CLOUD))
    sys.modules.pop("store", None)
    s = importlib.import_module("store").Store(str(tmp_path / "miyagi.db"), net_key=b"k")
    _seed_old(s, "c" * 64, 60)
    s._db.close()
    _, app_mod, _ = make_cloud()
    assert rows_mentioning(app_mod, "c" * 12) == {}
    assert app_mod.RETAIN_DAYS >= 35 and app_mod.store._q("SELECT COUNT(*) AS n FROM usage WHERE token_hash = '*'")[0]["n"] == 1

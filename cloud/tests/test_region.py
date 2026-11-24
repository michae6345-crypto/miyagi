"""Region block (REGION_BLOCK, decision D9), offline: a tiny country database written here, no outside calls.

    cd cloud && python -m pytest tests -q
"""

from __future__ import annotations

import gzip
import importlib
import logging
import sqlite3
import sys
from pathlib import Path

import pytest

CLOUD = Path(__file__).resolve().parents[1]
ADMIN_TOKEN = "miyagi-tests-admin-0123456789-abcdefghijklmnop"
ADMIN = {"X-Admin-Token": ADMIN_TOKEN}
VID = "dQw4w9WgXcQ"
BLOCKED_BODY = {"error": "region_unavailable", "message": "miyagi isn't available in your region yet."}
DB_CSV = """1.0.0.0,1.0.0.255,DE
1.0.1.0,1.0.1.255,DE
5.0.0.0,5.0.0.255,RU
8.8.8.0,8.8.8.255,US
9.9.9.0,9.9.9.255,ZZ
2001:db8::,2001:db8:0:ffff:ffff:ffff:ffff:ffff,FR
2001:db8:1::,2001:db8:1:ffff:ffff:ffff:ffff:ffff,US
"""
DE, US, RU, UNKNOWN, FR6, US6 = "1.0.0.7", "8.8.8.8", "5.0.0.9", "203.0.113.5", "2001:db8::42", "2001:db8:1::42"
ANTHROPIC_BODY = {"model": "claude-haiku-5-5", "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]}


def at(ip: str) -> dict:
    return {"X-Forwarded-For": ip}  # TRUSTED_PROXY_HOPS=1: the last entry is the client


@pytest.fixture
def make_cloud(tmp_path, monkeypatch):
    clients = []
    db = tmp_path / "dbip-country-lite.csv.gz"
    with gzip.open(db, "wt") as f:
        f.write(DB_CSV)

    def make(db_path: str | None = str(db), **env):
        base = {"ADMIN_TOKEN": ADMIN_TOKEN, "DB_PATH": str(tmp_path / "miyagi.db"), "REGION_BLOCK": "1",
                "ANTHROPIC_API_KEY": "fake-upstream-key", "UPSTREAM_ANTHROPIC_URL": "http://127.0.0.1:9/v1/messages",
                "TRUSTED_PROXY_HOPS": "1", "ALLOWED_GEMINI_MODELS": "gemini-3.8-flash", "GEMINI_API_KEY": "fake",
                "UPSTREAM_GEMINI_URL": "http://127.0.0.1:9/{model}:{method}"}
        for k, v in {**base, **env}.items():
            monkeypatch.setenv(k, v)
        for k in ("COUNTRY_HEADER", "BLOCKED_COUNTRIES", "COUNTRY_DB_PATH"):
            if k not in env:
                monkeypatch.delenv(k, raising=False)
        if db_path:
            monkeypatch.setenv("COUNTRY_DB_PATH", db_path)
        monkeypatch.syspath_prepend(str(CLOUD))
        for mod in ("app", "store", "geo"):
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
    for mod in ("app", "store", "geo"):
        sys.modules.pop(mod, None)


def install(client, ip=US):
    return client.post("/v1/install", headers=at(ip), json={"app": "test"})


def bearer(r) -> dict:
    return {"Authorization": f"Bearer {r.json()['token']}"}


def regions(client) -> dict:
    rows = client.get("/admin/regions", headers=ADMIN).json()["days"]
    return {r["country"]: (r["allowed"], r["blocked"]) for r in rows}


def test_defaults_follow_d9():
    sys.path.insert(0, str(CLOUD))
    sys.modules.pop("geo", None)
    geo = importlib.import_module("geo")
    blocked = set(geo.DEFAULT_BLOCKED.split(","))
    assert {"DE", "FR", "IE", "NO", "IS", "LI", "GB", "CH", "RU", "CN", "IR", "KP", "CU", "SY", "BY", "HK"} <= blocked
    assert not {"US", "CA", "MX", "JP", "IN", "UA", "TR", "RS"} & blocked
    assert all(len(c) == 2 and c.isupper() for c in blocked) and len(blocked) == len(geo.DEFAULT_BLOCKED.split(","))


def test_flag_off_blocks_nothing(make_cloud):
    client, app_mod = make_cloud(REGION_BLOCK="0")
    assert app_mod.REGION_BLOCK is False
    r = install(client, DE)
    assert r.status_code == 200
    assert client.post("/v1/anthropic/v1/messages", headers={**bearer(r), **at(DE)}, json=ANTHROPIC_BODY).status_code == 502
    assert regions(client) == {}  # nothing looked up, nothing counted


def test_blocked_country_gets_451_on_install_and_every_money_route(make_cloud):
    client, _ = make_cloud()
    for ip in (DE, RU, FR6):
        r = install(client, ip)
        assert r.status_code == 451 and r.json() == BLOCKED_BODY and r.headers["x-should-retry"] == "false"
    r = client.post("/v1/register", headers=at(DE), json={"install_id": "x", "app_version": "1", "platform": "darwin"})
    assert r.status_code == 451
    h = bearer(install(client, US))  # minted while in the US, then used from a blocked country
    for method, path, body in (("POST", "/v1/anthropic/v1/messages", ANTHROPIC_BODY),
                               ("POST", "/v1/anthropic/messages", ANTHROPIC_BODY),
                               ("POST", "/v1/gemini/gemini-3.8-flash:generateContent", {"contents": []}),
                               ("POST", f"/v1/lessons/{VID}/build", None)):
        r = client.request(method, path, headers={**h, **at(DE)}, json=body)
        assert r.status_code == 451 and r.json() == BLOCKED_BODY, path
    # the block comes before the token check: a blocked client learns nothing about tokens
    r = client.post("/v1/anthropic/v1/messages", headers={"Authorization": "Bearer mi_nope", **at(DE)}, json=ANTHROPIC_BODY)
    assert r.status_code == 451


def test_allowed_country_passes(make_cloud):
    client, _ = make_cloud()
    for ip in (US, US6, f"::ffff:{US}"):
        r = install(client, ip)
        assert r.status_code == 200, ip
    h = bearer(install(client, US))
    assert client.post("/v1/anthropic/v1/messages", headers={**h, **at(US)}, json=ANTHROPIC_BODY).status_code == 502
    assert client.post(f"/v1/lessons/{VID}/build", headers={**h, **at(US)}).status_code == 200


def test_unknown_country_is_allowed_and_counted(make_cloud):
    client, _ = make_cloud()
    assert install(client, UNKNOWN).status_code == 200
    assert install(client, "9.9.9.9").status_code == 200  # db-ip's ZZ: not a country
    assert install(client, DE).status_code == 451
    assert install(client, US).status_code == 200
    assert regions(client) == {"unknown": (2, 0), "DE": (0, 1), "US": (1, 0)}


def test_delete_health_admin_and_other_routes_are_never_blocked(make_cloud):
    client, _ = make_cloud()
    h = bearer(install(client, US))
    assert client.get("/healthz", headers=at(DE)).status_code == 200
    assert client.get("/admin/regions", headers={**ADMIN, **at(DE)}).status_code == 200
    assert client.get("/admin/proxy", headers={**ADMIN, **at(DE)}).status_code == 200
    r = client.post("/v1/events", headers={**h, **at(DE)}, json={"events": []})
    assert r.status_code == 202
    r = client.get(f"/v1/lessons/{VID}?schema=1", headers={**h, **at(DE)})
    assert r.status_code == 404  # a free cache read: not a route that spends money
    r = client.post("/v1/account/delete", headers={**h, **at(DE)}, json={})
    assert r.status_code == 200 and r.json()["install"] is True


def test_header_source(make_cloud):
    client, app_mod = make_cloud(db_path=None, COUNTRY_HEADER="cf-ipcountry")
    assert app_mod.country_db is None
    assert install(client, UNKNOWN).status_code == 200  # no header: unknown
    r = client.post("/v1/install", headers={**at(UNKNOWN), "CF-IPCountry": "de"}, json={})
    assert r.status_code == 451
    for cc in ("US", "XX", "T1", "not-a-country", ""):
        assert client.post("/v1/install", headers={**at(UNKNOWN), "CF-IPCountry": cc}, json={}).status_code == 200, cc


def test_header_wins_over_the_database_and_db_fills_in(make_cloud):
    client, _ = make_cloud(COUNTRY_HEADER="cf-ipcountry")
    assert client.post("/v1/install", headers={**at(DE), "CF-IPCountry": "US"}, json={}).status_code == 200
    assert client.post("/v1/install", headers={**at(US), "CF-IPCountry": "GB"}, json={}).status_code == 451
    assert client.post("/v1/install", headers={**at(DE), "CF-IPCountry": "XX"}, json={}).status_code == 451  # DB: DE


def test_database_source_uses_the_rate_limiters_client_ip(make_cloud):
    client, _ = make_cloud()
    # the client writes DE on the left; the trusted hop (the last entry, what Render appended) is the US address
    assert client.post("/v1/install", headers={"X-Forwarded-For": f"{DE}, {US}"}, json={}).status_code == 200
    assert client.post("/v1/install", headers={"X-Forwarded-For": f"{US}, {DE}"}, json={}).status_code == 451


def test_no_header_is_trusted_unless_configured(make_cloud):
    client, _ = make_cloud()  # COUNTRY_HEADER unset: a client's own CF-IPCountry means nothing
    assert client.post("/v1/install", headers={**at(US), "CF-IPCountry": "DE"}, json={}).status_code == 200
    assert client.post("/v1/install", headers={**at(DE), "CF-IPCountry": "US"}, json={}).status_code == 451


def test_custom_blocked_list(make_cloud):
    client, app_mod = make_cloud(BLOCKED_COUNTRIES="us, ru,bogus,")
    assert app_mod.BLOCKED_COUNTRIES == frozenset({"US", "RU"})
    assert install(client, US).status_code == 451
    assert install(client, DE).status_code == 200


def test_no_source_allows_everyone_and_says_so(make_cloud, caplog):
    with caplog.at_level(logging.ERROR):
        client, _ = make_cloud(db_path=None)
    assert "no country source" in caplog.text
    assert install(client, DE).status_code == 200


def test_unreadable_database_is_not_fatal(make_cloud, tmp_path, caplog):
    bad = tmp_path / "missing.csv"
    with caplog.at_level(logging.ERROR):
        client, app_mod = make_cloud(db_path=str(bad))
    assert app_mod.country_db is None and "could not be read" in caplog.text
    assert install(client, DE).status_code == 200


def test_nothing_is_stored_or_logged_per_request(make_cloud, tmp_path, caplog):
    client, app_mod = make_cloud()
    with caplog.at_level(logging.DEBUG):
        ok = install(client, US)
        assert install(client, DE).status_code == 451
        client.post("/v1/anthropic/v1/messages", headers={**bearer(ok), **at(DE)}, json=ANTHROPIC_BODY)
    regions(client)  # flushes the day's counts
    for needle in (US, DE, '"DE"', "country=", "region="):
        assert needle not in caplog.text
    con = sqlite3.connect(str(tmp_path / "miyagi.db"))
    tables = {t for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    for t in tables:  # no table but the daily counts holds a country column; no addresses anywhere
        cols = [c[1] for c in con.execute(f"PRAGMA table_info({t})")]
        assert ("country" in cols) == (t == "region_days"), t
        for row in con.execute(f"SELECT * FROM {t}"):
            assert not any(isinstance(v, str) and (US in v or DE in v) for v in row), t
    assert [c[1] for c in con.execute("PRAGMA table_info(region_days)")] == ["day", "country", "blocked", "n"]
    assert sorted((c, b, n) for _, c, b, n in con.execute("SELECT * FROM region_days")) == [("DE", 1, 2), ("US", 0, 1)]


def test_country_db_merges_and_looks_up(make_cloud):
    sys.path.insert(0, str(CLOUD))
    geo = importlib.import_module("geo")
    db = geo.CountryDB.from_text(DB_CSV + "garbage,row\nfirst_ip,last_ip,country\n")
    assert db.rows == 6 and len(db) == 5  # the two adjacent DE ranges merge; ZZ is dropped
    assert db.lookup("1.0.1.200") == "DE" and db.lookup("1.0.2.0") is None and db.lookup("not an ip") is None
    assert db.lookup(FR6) == "FR" and db.lookup(US6) == "US" and db.lookup("2001:db8:2::1") is None

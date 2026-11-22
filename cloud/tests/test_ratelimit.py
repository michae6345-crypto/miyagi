"""Rate limits (class RateLimit in app.py), client IP parsing and the install mint limiter, offline.

The upstreams point at a closed local port (see test_caps.py), so nothing here reaches a real provider.

    cd cloud && python -m pytest tests -q
"""

from __future__ import annotations

import logging
import re
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest


from test_caps import ADMIN, ADMIN_TOKEN, CLOUD, install, make_cloud  # noqa: F401  (make_cloud is a fixture)


def xff(ip: str) -> dict:
    return {"X-Forwarded-For": ip}


def assert_rate_limited(r, limit: str) -> dict:
    assert r.status_code == 429, r.text
    err = r.json()["error"]
    assert r.json()["type"] == "error"
    assert err["type"] == "rate_limit_error" and err["status"] == "RATE_LIMIT_ERROR" and err["code"] == 429
    assert err["limit"] == limit and err["message"]
    resets = datetime.strptime(err["resets_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    assert resets > datetime.now(UTC)
    assert int(r.headers["retry-after"]) >= 1
    if int(r.headers["retry-after"]) > 60:
        assert r.headers["x-should-retry"] == "false"
    return err


# --------------------------------------------------------------------------- where it sits

def test_ratelimit_is_registered_directly_before_guard():
    src = (CLOUD / "app.py").read_text()
    lines = [ln for ln in src.splitlines() if ln.startswith("app.add_middleware(")]  # module level, not the docstring
    assert [ln.split("#")[0].strip() for ln in lines] == ["app.add_middleware(RateLimit)", "app.add_middleware(Guard)"]
    i = src.index("\napp.add_middleware(RateLimit)") + 1
    assert src[i:].splitlines()[1].startswith("app.add_middleware(Guard)")
    guard, ratelimit = src.index("\nclass Guard:"), src.index("\nclass RateLimit:")
    assert guard < ratelimit and "\nclass " not in src[guard + 1:ratelimit] and "\ndef " not in src[guard + 1:ratelimit]
    readme = (CLOUD / "README.md").read_text()
    section = readme[readme.index("## Rate limits"):]
    assert "app.add_middleware(RateLimit)\napp.add_middleware(Guard)" in section


def test_guard_is_the_outer_middleware(make_cloud):
    _, app_mod = make_cloud()
    assert [m.cls.__name__ for m in app_mod.app.user_middleware] == ["Guard", "RateLimit"]  # first = outermost


# --------------------------------------------------------------------------- per IP

def test_101st_link_from_one_ip_is_429(make_cloud, caplog):
    client, _ = make_cloud()
    h, _ = install(client)  # from the test client's own address
    headers = {**h, **xff("203.0.113.7")}
    for _ in range(100):
        assert client.post("/v1/link", headers=headers, json={}).status_code == 403  # bad_access_token, but counted
    with caplog.at_level(logging.INFO, logger="miyagi.cloud"):
        r = client.post("/v1/link", headers=headers, json={})
    err = assert_rate_limited(r, "ip_hourly")
    assert int(r.headers["retry-after"]) > 60 and r.headers["x-should-retry"] == "false"
    assert "429" in caplog.text and "rl=ip_hourly" in caplog.text  # Guard (outer) logged it
    assert "203.0.113.7" not in caplog.text  # the log line carries no address
    # another client is not affected
    assert client.post("/v1/link", headers={**h, **xff("203.0.113.8")}, json={}).status_code == 403
    assert err["resets_at"].endswith("Z")


def test_101st_install_from_one_ip_is_429(make_cloud):
    client, _ = make_cloud(REGISTER_LIMIT_PER_HOUR="1000", REGISTER_LIMIT_PER_DAY="1000")
    for _ in range(100):
        assert client.post("/v1/install", headers=xff("198.51.100.20"), json={}).status_code == 200
    assert_rate_limited(client.post("/v1/install", headers=xff("198.51.100.20"), json={}), "ip_hourly")
    assert_rate_limited(client.post("/v1/register", headers=xff("198.51.100.20"),
                                    json={"install_id": "x", "app_version": "1", "platform": "p"}), "ip_hourly")


def test_healthz_is_never_limited(make_cloud):
    client, _ = make_cloud(RATE_LIMIT_PER_IP_PER_HOUR="2")
    for _ in range(2):
        client.post("/v1/install", headers=xff("192.0.2.1"), json={})
    assert client.post("/v1/install", headers=xff("192.0.2.1"), json={}).status_code == 429
    for _ in range(300):
        assert client.get("/healthz", headers=xff("192.0.2.1")).status_code == 200


def test_rate_limit_can_be_turned_off(make_cloud):
    client, _ = make_cloud(RATE_LIMIT_ENABLED="0", RATE_LIMIT_PER_IP_PER_HOUR="1")
    h, _ = install(client)
    for _ in range(5):
        assert client.post("/v1/link", headers=h, json={}).status_code == 403


# --------------------------------------------------------------------------- per token

def test_valid_tokens_behind_one_ip_have_their_own_budget(make_cloud):
    client, app_mod = make_cloud()
    ip = xff("100.64.0.1")
    a = {**install(client)[0], **ip}
    b = {**install(client)[0], **ip}
    for _ in range(150):  # each token alone sends more than the IP's 100 an hour
        assert client.post("/v1/events", headers=a, json={"events": []}).status_code == 202
        assert client.post("/v1/events", headers=b, json={"events": []}).status_code == 202
    # neither consumed the IP's budget: an IP-counted route from that address still works 100 times
    for _ in range(100):
        assert client.post("/v1/link", headers=a, json={}).status_code == 403
    assert_rate_limited(client.post("/v1/link", headers=a, json={}), "ip_hourly")
    # each token's own budget is 600 an hour
    for _ in range(450):
        assert client.post("/v1/events", headers=a, json={"events": []}).status_code == 202
    assert_rate_limited(client.post("/v1/events", headers=a, json={"events": []}), "token_hourly")
    assert client.post("/v1/events", headers=b, json={"events": []}).status_code == 202
    assert app_mod.RATE_LIMIT_PER_TOKEN_PER_HOUR == 600 and app_mod.RATE_LIMIT_PER_IP_PER_HOUR == 100


def test_unknown_token_counts_against_the_ip(make_cloud):
    """Guessing install tokens is limited per IP: unknown tokens never get a fresh 600/h bucket each."""
    client, _ = make_cloud()
    ip = xff("100.64.0.2")
    body = {"model": "claude-haiku-5-5", "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]}
    for i in range(100):
        guess = {"Authorization": f"Bearer mi_guess{i:04d}", **ip}
        assert client.post("/v1/anthropic/v1/messages", headers=guess, json=body).status_code == 401
    assert_rate_limited(client.post("/v1/anthropic/v1/messages", headers={"x-api-key": "mi_guess9999", **ip}, json=body),
                        "ip_hourly")
    assert_rate_limited(client.get("/v1/lessons/dQw4w9WgXcQ?schema=1", headers=ip), "ip_hourly")  # no token at all
    # a real install behind the same address still works: it counts against its own token
    h, _ = install(client)
    assert client.post("/v1/anthropic/v1/messages", headers={**h, **ip}, json=body).status_code == 502  # closed upstream


def test_duplicated_auth_header_cannot_move_guesses_to_a_valid_tokens_budget(make_cloud):
    """[Bearer <guess>, Bearer <valid>]: authenticate() checks the first (the guess), so the limiter must count the
    first too. Counted against the valid token, every guess got a 401 and none a 429."""
    client, app_mod = make_cloud(RATE_LIMIT_PER_IP_PER_HOUR="5")
    valid, _ = install(client)
    body = {"model": "claude-haiku-5-5", "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]}
    statuses = []
    for i in range(20):
        headers = [("Authorization", f"Bearer mi_guess{i:04d}"), ("Authorization", valid["Authorization"]),
                   ("X-Forwarded-For", "100.64.0.9")]
        statuses.append(client.post("/v1/anthropic/v1/messages", headers=headers, json=body).status_code)
    assert statuses[:5] == [401] * 5 and statuses[5:] == [429] * 15
    # the other order is the valid token first: counted against it, and it works
    headers = [("Authorization", valid["Authorization"]), ("Authorization", "Bearer mi_guess"), ("X-Forwarded-For", "100.64.0.9")]
    assert client.post("/v1/anthropic/v1/messages", headers=headers, json=body).status_code == 502  # closed upstream
    # same for x-api-key and x-goog-api-key
    for name in ("x-api-key", "x-goog-api-key"):
        headers = [(name, "mi_guess"), (name, valid["Authorization"][7:]), ("X-Forwarded-For", "100.64.0.9")]
        assert client.post("/v1/anthropic/v1/messages", headers=headers, json=body).status_code == 429


def test_disabled_token_counts_against_the_ip(make_cloud):
    client, _ = make_cloud(RATE_LIMIT_PER_IP_PER_HOUR="3")
    h, token_id = install(client)
    assert client.post(f"/admin/tokens/{token_id}/disable", headers={**ADMIN, **xff("10.9.9.9")}).status_code == 200
    ip = xff("100.64.0.3")
    for _ in range(3):
        assert client.post("/v1/events", headers={**h, **ip}, json={"events": []}).status_code == 401
    assert_rate_limited(client.post("/v1/events", headers={**h, **ip}, json={"events": []}), "ip_hourly")


# --------------------------------------------------------------------------- admin

def test_21st_admin_request_per_ip_is_429(make_cloud):
    client, _ = make_cloud()
    ip = xff("192.0.2.50")
    for _ in range(20):
        assert client.get("/admin/usage", headers={**ADMIN, **ip}).status_code == 200
    assert_rate_limited(client.get("/admin/usage", headers={**ADMIN, **ip}), "admin")
    assert_rate_limited(client.get("/admin", headers=ip), "admin")  # the login page counts too
    assert client.get("/admin/usage", headers={**ADMIN, **xff("192.0.2.51")}).status_code == 200


def test_admin_lockout_after_five_wrong_tokens(make_cloud, caplog, monkeypatch):
    client, app_mod = make_cloud()
    ip = xff("192.0.2.60")
    wrong = [f"wrong-guess-{i}-{'x' * 30}" for i in range(5)]
    with caplog.at_level(logging.WARNING, logger="miyagi.cloud"):
        for i, guess in enumerate(wrong):
            if i % 2:  # the HTML form counts too
                assert "Wrong token" in client.post("/admin", headers=ip, data={"admin_token": guess}).text
            else:
                assert client.get("/admin/usage", headers={"X-Admin-Token": guess, **ip}).status_code == 401
    fails = [r for r in caplog.records if "admin auth failed" in r.getMessage()]
    assert len(fails) == 5 and all("192.0.2.60" in r.getMessage() for r in fails)
    for guess in wrong:
        assert guess not in caplog.text
    # the right token from that IP is locked out too, until the window passes
    err = assert_rate_limited(client.get("/admin/usage", headers={**ADMIN, **ip}), "admin_lockout")
    assert err["message"] and ADMIN_TOKEN not in caplog.text
    assert_rate_limited(client.post("/admin/tokens/0123456789ab/disable", headers={**ADMIN, **ip}), "admin_lockout")
    # another IP is fine
    assert client.get("/admin/usage", headers={**ADMIN, **xff("192.0.2.61")}).status_code == 200
    # 59 minutes later: still locked; an hour after the first failure: open again
    t0 = time.time()
    monkeypatch.setattr(app_mod, "_now", lambda: t0 + 59 * 60)
    assert_rate_limited(client.get("/admin/usage", headers={**ADMIN, **ip}), "admin_lockout")
    monkeypatch.setattr(app_mod, "_now", lambda: t0 + 3601)
    assert client.get("/admin/usage", headers={**ADMIN, **ip}).status_code == 200


def test_admin_failure_memory_is_small_and_bounded(make_cloud):
    """Its own bound (20000, not the limiter's 200000) and a tuple of a few floats per bucket, not a deque."""
    _, app_mod = make_cloud()
    fails = app_mod.admin_failures
    assert fails.max_keys == app_mod.ADMIN_FAILURE_MAX_KEYS == 20_000
    for i in range(30_000):
        fails.record(f"2001:db8:{i >> 16 & 0xffff:x}:{i & 0xffff:x}::/64")
    assert len(fails) == 20_000
    rec = next(iter(fails._d.values()))
    assert isinstance(rec, tuple) and len(rec) <= app_mod.ADMIN_LOCKOUT_FAILURES
    # five failures still lock, and only the last ADMIN_LOCKOUT_FAILURES times are kept
    for _ in range(7):
        n = fails.record("192.0.2.99")
    assert n == 5 and len(fails._d["192.0.2.99"]) == 5 and fails.locked("192.0.2.99") > 0
    _, app_mod = make_cloud(ADMIN_FAILURE_MAX_KEYS="10")
    assert app_mod.admin_failures.max_keys == 10


def test_admin_lockout_holds_with_rate_limits_off(make_cloud):
    client, _ = make_cloud(RATE_LIMIT_ENABLED="0")
    ip = xff("192.0.2.70")
    for _ in range(5):
        client.get("/admin/usage", headers={"X-Admin-Token": "nope", **ip})
    assert_rate_limited(client.get("/admin/usage", headers={**ADMIN, **ip}), "admin_lockout")


# --------------------------------------------------------------------------- client IP

def _scope(xff_values: list[str] | None = None, peer: str = "10.0.0.1", **headers) -> dict:
    hs = [(b"x-forwarded-for", v.encode()) for v in (xff_values or [])]
    hs += [(k.replace("_", "-").encode(), v.encode()) for k, v in headers.items()]
    return {"type": "http", "headers": hs, "client": (peer, 5555)}


def test_client_ip_uses_the_trusted_hop_only(make_cloud):
    _, app_mod = make_cloud(TRUSTED_PROXY_HOPS="1")
    ip = app_mod.client_ip_scope
    assert ip(_scope(["198.51.100.9"])) == "198.51.100.9"
    # a client-prepended (spoofed) entry never changes the result: the rightmost entry is the proxy's
    assert ip(_scope(["6.6.6.6, 198.51.100.9"])) == "198.51.100.9"
    assert ip(_scope(["6.6.6.6", "198.51.100.9"])) == "198.51.100.9"  # several headers join in order
    assert ip(_scope(["198.51.100.9:44321"])) == "198.51.100.9"  # port stripped
    assert ip(_scope(["[2001:db8::5]:443"])) == "2001:db8::5"
    assert ip(_scope(["not-an-ip"])) == "10.0.0.1"  # invalid: the socket peer
    assert ip(_scope(["1.2.3.4, garbage"])) == "10.0.0.1"  # never trusts further left
    assert ip(_scope([])) == "10.0.0.1"  # no header: the peer


def test_client_ip_fewer_entries_than_hops_uses_the_peer(make_cloud):
    _, app_mod = make_cloud(TRUSTED_PROXY_HOPS="2")
    ip = app_mod.client_ip_scope
    assert ip(_scope(["198.51.100.9"])) == "10.0.0.1"
    assert ip(_scope(["203.0.113.1, 198.51.100.9"])) == "203.0.113.1"
    assert ip(_scope(["6.6.6.6, 203.0.113.1, 198.51.100.9"])) == "203.0.113.1"


def test_client_ip_header_only_when_set(make_cloud):
    _, app_mod = make_cloud(CLIENT_IP_HEADER="CF-Connecting-IP")
    ip = app_mod.client_ip_scope
    assert ip(_scope(["198.51.100.9"], cf_connecting_ip="203.0.113.44")) == "203.0.113.44"
    assert ip(_scope(["198.51.100.9"], cf_connecting_ip="nonsense")) == "198.51.100.9"
    _, app_mod = make_cloud(unset=("CLIENT_IP_HEADER",))
    assert app_mod.client_ip_scope(_scope(["198.51.100.9"], cf_connecting_ip="203.0.113.44")) == "198.51.100.9"


def test_spoofed_xff_does_not_change_the_bucket(make_cloud):
    client, _ = make_cloud(TRUSTED_PROXY_HOPS="1")
    h, _ = install(client)
    for i in range(100):
        spoof = f"10.{i}.0.1, 198.51.100.77"  # the client rotates what it prepends
        assert client.post("/v1/link", headers={**h, **xff(spoof)}, json={}).status_code == 403
    assert_rate_limited(client.post("/v1/link", headers={**h, **xff("8.8.8.8, 198.51.100.77")}, json={}), "ip_hourly")


def test_ipv6_is_bucketed_by_64(make_cloud):
    client, app_mod = make_cloud()
    assert app_mod.ip_bucket("2001:db8:1:2::1") == app_mod.ip_bucket("2001:db8:1:2:ffff::9") == "2001:db8:1:2::/64"
    assert app_mod.ip_bucket("2001:db8:1:3::1") != app_mod.ip_bucket("2001:db8:1:2::1")
    assert app_mod.ip_bucket("::ffff:198.51.100.3") == "198.51.100.3"
    assert app_mod.ip_bucket("198.51.100.3") == "198.51.100.3"  # IPv4 stays the full address
    h, _ = install(client)
    for i in range(100):
        assert client.post("/v1/link", headers={**h, **xff(f"2001:db8:1:2::{i + 1:x}")}, json={}).status_code == 403
    assert_rate_limited(client.post("/v1/link", headers={**h, **xff("2001:db8:1:2:abcd::1")}, json={}), "ip_hourly")
    assert client.post("/v1/link", headers={**h, **xff("2001:db8:1:3::1")}, json={}).status_code == 403


def test_xff_count_logged_once_without_addresses(make_cloud, caplog):
    client, _ = make_cloud()
    with caplog.at_level(logging.INFO, logger="miyagi.cloud"):
        client.post("/v1/install", headers=xff("6.6.6.6, 81.2.69.160"), json={})
        client.post("/v1/install", headers=xff("81.2.69.161"), json={})
    lines = [r.getMessage() for r in caplog.records if "X-Forwarded-For" in r.getMessage()]
    assert lines == ["first request: 2 X-Forwarded-For entries (TRUSTED_PROXY_HOPS=1); the chosen entry is a global address"]
    assert "81.2.69.16" not in caplog.text and "6.6.6.6" not in caplog.text


def test_xff_log_says_when_the_chosen_entry_is_a_proxy(make_cloud, caplog):
    """The staging release gate: a Cloudflare or private chosen entry means TRUSTED_PROXY_HOPS is wrong."""
    client, app_mod = make_cloud()
    with caplog.at_level(logging.INFO, logger="miyagi.cloud"):
        client.post("/v1/install", json={})  # no X-Forwarded-For (an internal check): logged, then one more chance
        client.post("/v1/install", headers=xff("81.2.69.160, 104.16.1.1"), json={})
        client.post("/v1/install", headers=xff("10.0.0.7"), json={})
    lines = [r.getMessage() for r in caplog.records if "X-Forwarded-For" in r.getMessage()]
    assert lines == ["first request: 0 X-Forwarded-For entries (TRUSTED_PROXY_HOPS=1); the chosen entry is none "
                     "(the socket peer is used)",
                     "first request: 2 X-Forwarded-For entries (TRUSTED_PROXY_HOPS=1); the chosen entry is a Cloudflare "
                     "address (wrong hop count)"]
    assert "104.16.1.1" not in caplog.text and "81.2.69.160" not in caplog.text
    kind = app_mod._ip_kind
    ip = app_mod.ipaddress.ip_address
    assert kind(ip("10.1.2.3")).startswith("a private") and kind(ip("2606:4700::1")).startswith("a Cloudflare")
    assert kind(ip("2a00:1450::1")) == "a global address" and kind(None).startswith("not a valid")


# --------------------------------------------------------------------------- the limiter itself

def test_sliding_window_counts_and_weighs_the_previous_window(make_cloud):
    _, app_mod = make_cloud()
    lim = app_mod.SlidingWindowLimiter(1000)
    t = 1_000 * 3600.0  # the start of an hour
    assert all(lim.hit("k", 10, now=t + i) == 0.0 for i in range(10))
    wait = lim.hit("k", 10, now=t + 10)
    # full for the rest of this hour, then 10% into the next one, where the 10 still weigh 9.x
    assert 3590 + 359 <= wait <= 3590 + 361
    # half way into the next hour the previous 10 weigh 5: five more fit, the sixth does not
    mid = t + 3600 + 1800
    assert all(lim.hit("k", 10, now=mid) == 0.0 for _ in range(5))
    assert lim.hit("k", 10, now=mid) > 0
    # two hours of quiet: a fresh budget
    assert lim.hit("k", 10, now=t + 3 * 3600 + 1) == 0.0
    assert lim.hit("other", 0, now=t) == 0.0  # 0 = no limit


def test_limiter_memory_is_bounded(make_cloud):
    _, app_mod = make_cloud()
    lim = app_mod.limiter
    assert lim.max_keys == app_mod.RATE_LIMIT_MAX_KEYS == 200_000
    start = time.perf_counter()
    now = time.time()
    for i in range(300_000):
        lim.hit(f"ip:10.{i >> 16 & 255}.{i >> 8 & 255}.{i & 255}", 100, now=now)
        assert len(lim) <= app_mod.RATE_LIMIT_MAX_KEYS if i % 50_000 == 0 else True
    assert len(lim) <= app_mod.RATE_LIMIT_MAX_KEYS
    assert time.perf_counter() - start < 10
    # the newest keys survive, the oldest were evicted
    assert "ip:10.4.147.223" in lim._d and "ip:10.0.0.0" not in lim._d


def test_limiter_sweeps_expired_keys(make_cloud):
    _, app_mod = make_cloud()
    lim = app_mod.SlidingWindowLimiter(1000)
    t = 2_000 * 3600.0
    for i in range(500):
        lim.hit(f"k{i}", 5, now=t)
    lim.hit("late", 5, now=t + 3600)
    assert len(lim) == 501
    lim.hit("fresh", 5, now=t + 2 * 3600 + 120)  # two windows on: the first 500 have expired
    assert len(lim) == 2 and "late" in lim._d


# --------------------------------------------------------------------------- install minting (SQLite)

def test_install_mint_limit_per_hour_survives_a_restart(make_cloud):
    client, _ = make_cloud(REGISTER_LIMIT_PER_HOUR="3")
    for _ in range(3):
        assert client.post("/v1/install", headers=xff("198.51.100.30"), json={}).status_code == 200
    assert_rate_limited(client.post("/v1/install", headers=xff("198.51.100.30"), json={}), "install_hourly")
    # a new process on the same database (a deploy): the count is still there
    client2, app2 = make_cloud(REGISTER_LIMIT_PER_HOUR="3")
    assert_rate_limited(client2.post("/v1/install", headers=xff("198.51.100.30"), json={}), "install_hourly")
    assert client2.post("/v1/install", headers=xff("198.51.100.31"), json={}).status_code == 200


def test_mint_counts_persist_across_store_reopen(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(CLOUD))
    import importlib
    import sys

    sys.modules.pop("store", None)
    store_mod = importlib.import_module("store")
    db = str(tmp_path / "mints.db")
    t = 5_000 * 3600.0 + 10
    s = store_mod.Store(db)
    assert all(s.mint_check("1.2.3.4", 20, 60, 0, now=t)["hit"] is None for _ in range(20))
    assert s.mint_check("1.2.3.4", 20, 60, 0, now=t)["hit"] == "hour"
    s._db.close()
    s2 = store_mod.Store(db)  # a new process
    r = s2.mint_check("1.2.3.4", 20, 60, 0, now=t)
    assert r["hit"] == "hour" and r["used"] == 20 and 0 < r["retry_s"] <= 3600
    # the daily limit spans hours: 20 + 20 + 20 over three hours, then refused for the rest of the 24 h
    for h in (1, 2):
        assert all(s2.mint_check("1.2.3.4", 20, 60, 0, now=t + h * 3600)["hit"] is None for _ in range(20))
    r = s2.mint_check("1.2.3.4", 20, 60, 0, now=t + 3 * 3600)
    assert r["hit"] == "day" and r["used"] == 60 and abs(r["retry_s"] - (21 * 3600 - 10)) < 2
    assert s2.mint_check("1.2.3.4", 20, 60, 0, now=t + 24 * 3600)["hit"] is None  # the first hour fell out
    # rows older than two days are pruned
    s2.mint_check("9.9.9.9", 20, 60, 0, now=t + 60 * 3600)
    hours = {r["hour"] for r in s2._q("SELECT DISTINCT hour FROM mints")}
    assert min(hours) >= int((t + 60 * 3600) // 3600) - 48
    sys.modules.pop("store", None)


def test_global_mint_ceiling(make_cloud, caplog):
    client, _ = make_cloud(GLOBAL_MINTS_PER_HOUR="4", GLOBAL_MINTS_WARN_PER_HOUR="3")
    with caplog.at_level(logging.WARNING, logger="miyagi.cloud"):
        for i in range(4):
            assert client.post("/v1/install", headers=xff(f"198.51.100.{40 + i}"), json={}).status_code == 200
        err = assert_rate_limited(client.post("/v1/install", headers=xff("198.51.100.99"), json={}), "install_global")
    assert "install minting is high" in caplog.text and "install mint ceiling reached" in caplog.text
    assert err["message"]


def test_install_daily_limit_default_and_ipv6_buckets(make_cloud):
    client, app_mod = make_cloud(REGISTER_LIMIT_PER_HOUR="2")
    assert app_mod.REGISTER_PER_DAY == 60 and app_mod.GLOBAL_MINTS_MAX == 2000 and app_mod.GLOBAL_MINTS_WARN == 500
    assert client.post("/v1/install", headers=xff("2001:db8:9:9::a"), json={}).status_code == 200
    assert client.post("/v1/install", headers=xff("2001:db8:9:9::b"), json={}).status_code == 200
    assert_rate_limited(client.post("/v1/install", headers=xff("2001:db8:9:9:1::c"), json={}), "install_hourly")


def test_install_mints_count_ipv6_by_48(make_cloud):
    """One home gets a /56 or a /48: rotating /64s inside it must not multiply the mint limit."""
    client, app_mod = make_cloud(REGISTER_LIMIT_PER_HOUR="3")
    assert app_mod.MINT_IPV6_PREFIX == 48
    assert app_mod.mint_bucket("2001:db8:aa:1::1") == app_mod.mint_bucket("2001:db8:aa:ff00::1") == "2001:db8:aa::/48"
    assert app_mod.mint_bucket("198.51.100.3") == "198.51.100.3" and app_mod.mint_bucket("::ffff:198.51.100.3") == "198.51.100.3"
    for i in range(3):  # three different /64s of one /48
        assert client.post("/v1/install", headers=xff(f"2001:db8:aa:{i}::1"), json={}).status_code == 200
    assert_rate_limited(client.post("/v1/install", headers=xff("2001:db8:aa:9999::1"), json={}), "install_hourly")
    assert client.post("/v1/install", headers=xff("2001:db8:ab::1"), json={}).status_code == 200  # another /48
    # the per-IP request limiter still counts IPv6 by /64
    assert app_mod.ip_bucket("2001:db8:aa:1::1") == "2001:db8:aa:1::/64"


def test_anonymous_spend_is_capped_per_minting_network(make_cloud):
    """Minting many installs from one network cannot multiply FREE_DAILY_USD (nor trip DAILY_USD_CAP for everyone)."""
    client, app_mod = make_cloud(ANON_DAILY_USD_PER_NETWORK="0.50", FREE_DAILY_USD="1.00", REGISTER_LIMIT_PER_HOUR="100")
    hashes = []
    for i in range(3):
        r = client.post("/v1/install", headers=xff(f"2001:db8:cc:{i}::1"), json={})  # three /64s of one /48
        hashes.append((r.json()["token"], app_mod.hash_token(r.json()["token"])))
    assert {app_mod.store.get_token(h)["mint_net"] for _, h in hashes} == {"2001:db8:cc::/48"}
    for _, h in hashes[:2]:
        app_mod.store.add_tokens(h, "anthropic", "claude-haiku-5-5", 10, 10, 0.25)  # $0.50 from that network today
    body = {"model": "claude-haiku-5-5", "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]}
    r = client.post("/v1/anthropic/v1/messages", headers={"Authorization": f"Bearer {hashes[2][0]}"}, json=body)
    assert r.status_code == 429, r.text
    err = r.json()["error"]
    assert err["type"] == "miyagi_quota" and err["limit"] == "daily_spend" and err["scope"] == "network"
    assert err["cap"] == 0.5 and r.headers["x-should-retry"] == "false"
    # another network is not affected
    other = client.post("/v1/install", headers=xff("2001:db8:cd::1"), json={}).json()["token"]
    assert client.post("/v1/anthropic/v1/messages", headers={"Authorization": f"Bearer {other}"}, json=body).status_code == 502
    # a linked install from that network counts per user instead, but what it spent today before linking stays in
    # the network's sum: linking a spent install does not free the pool for the others
    app_mod.store.link_user(hashes[0][1], "user-1")
    r = client.post("/v1/anthropic/v1/messages", headers={"Authorization": f"Bearer {hashes[0][0]}"}, json=body)
    assert r.status_code == 502
    r = client.post("/v1/anthropic/v1/messages", headers={"Authorization": f"Bearer {hashes[2][0]}"}, json=body)
    assert r.status_code == 429 and r.json()["error"]["scope"] == "network"
    assert r.json()["error"]["used"] == pytest.approx(0.5)  # not more: its spend after linking counts per user
    _, app_mod = make_cloud(unset=("ANON_DAILY_USD_PER_NETWORK",))
    assert app_mod.ANON_DAILY_USD_PER_NETWORK == 5.0


def test_one_ipv4_cannot_mint_past_the_kill_switch(make_cloud):
    """60 installs a day x FREE_DAILY_USD would be $60 > DAILY_USD_CAP 25: the network ceiling stops it at $5."""
    client, app_mod = make_cloud(unset=("ANON_DAILY_USD_PER_NETWORK",), FREE_DAILY_USD="1.00", DAILY_USD_CAP="25",
                                 REGISTER_LIMIT_PER_HOUR="60")
    tokens = [client.post("/v1/install", headers=xff("81.2.69.200"), json={}).json()["token"] for _ in range(10)]
    for t in tokens[:5]:
        app_mod.store.add_tokens(app_mod.hash_token(t), "anthropic", "claude-haiku-5-5", 10, 10, 1.0)
    body = {"model": "claude-haiku-5-5", "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]}
    for t in tokens[5:]:
        r = client.post("/v1/anthropic/v1/messages", headers={"Authorization": f"Bearer {t}"}, json=body)
        assert r.status_code == 429 and r.json()["error"]["scope"] == "network"
    assert app_mod.store.usd_today() == pytest.approx(5.0)


def test_register_limit_defaults(make_cloud):
    _, app_mod = make_cloud(unset=("REGISTER_LIMIT_PER_HOUR", "REGISTER_LIMIT_PER_DAY"))
    assert app_mod.REGISTER_PER_HOUR == 20 and app_mod.REGISTER_PER_DAY == 60
    assert not hasattr(app_mod, "_register_hits")  # the in-memory limiter is gone


def test_every_setting_is_documented_and_the_new_ones_are_in_render_yaml():
    names = set()
    for f in ("app.py", "store.py", "supabase_auth.py"):
        names |= set(re.findall(r'(?:_env_[a-z]+|os\.environ\.get)\("([A-Z_0-9]+)"', (CLOUD / f).read_text()))
    readme, render = (CLOUD / "README.md").read_text(), (CLOUD / "render.yaml").read_text()
    assert not [n for n in sorted(names) if f"`{n}`" not in readme]
    new = ["RATE_LIMIT_ENABLED", "RATE_LIMIT_PER_IP_PER_HOUR", "RATE_LIMIT_PER_TOKEN_PER_HOUR", "ADMIN_RATE_LIMIT_PER_IP_PER_HOUR",
           "ADMIN_LOCKOUT_FAILURES", "RATE_LIMIT_MAX_KEYS", "TRUSTED_PROXY_HOPS", "CLIENT_IP_HEADER", "REGISTER_LIMIT_PER_HOUR",
           "REGISTER_LIMIT_PER_DAY", "GLOBAL_MINTS_WARN_PER_HOUR", "GLOBAL_MINTS_PER_HOUR", "PER_TOKEN_INFLIGHT", "GLOBAL_INFLIGHT",
           "FREE_DAILY_REQUESTS", "FREE_DAILY_USD", "LINKED_DAILY_REQUESTS", "LINKED_DAILY_USD", "DAILY_USD_CAP",
           "MAX_GEMINI_BODY_MB", "ANTHROPIC_BETAS", "ANTHROPIC_SERVER_TOOLS", "SERVER_TOOL_MAX_USES", "GEMINI_MAX_OUTPUT_TOKENS",
           "GEMINI_MAX_THINKING_TOKENS", "LESSON_SCHEMAS", "MAX_LESSON_KB", "LESSON_PUTS_PER_DAY", "LESSON_AUTO_APPROVE_N",
           "LESSON_DISK_MAX_PCT", "SUPABASE_ALLOW_HS256", "LINK_MAX_INSTALLS_PER_USER", "ADMIN_FAILURE_MAX_KEYS",
           "ANON_DAILY_USD_PER_NETWORK", "BODY_READ_TIMEOUT_S", "GEMINI_VIDEO_RESERVE_TOKENS",
           "MINT_IPV6_PREFIX", "WEB_FETCH_MAX_CONTENT_TOKENS", "MAX_INFLIGHT_BODY_MB", "MAX_INFLIGHT_BODY_PER_IP_MB",
           "JSON_MAX_OBJECTS", "LESSON_PENDING_MAX_DAYS", "LESSON_PENDING_MAX_MB", "LESSON_PENDING_PER_NET_MB"]
    assert not [n for n in new if n not in render]
    assert "key: DAILY_USD_CAP" in render and "sync: false" in render.split("key: DAILY_USD_CAP", 1)[1].split("- key:", 1)[0]
    assert "ADMIN_TOKEN=test" not in readme and "secrets.token_urlsafe(32)" in readme


def test_no_slowapi_dependency():
    reqs = Path(CLOUD / "requirements.txt").read_text().lower()
    assert "slowapi" not in reqs and "limits" not in re.split(r"[=\n]", reqs)

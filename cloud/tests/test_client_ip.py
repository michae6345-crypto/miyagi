"""The client IP behind Render (client_ip_scope), and that a spoofed X-Forwarded-For dodges none of its users:
the rate limiter, install minting, the anonymous network spend pool, the region block and the admin lockout. Offline.

Render's proxy appends the address it saw to X-Forwarded-For; everything left of that is whatever the client sent.

    cd cloud && python -m pytest tests -q
"""

from __future__ import annotations

import gzip
import importlib
import logging
import sys
from pathlib import Path

import pytest

CLOUD = Path(__file__).resolve().parents[1]
ADMIN_TOKEN = "miyagi-tests-admin-0123456789-abcdefghijklmnop"
REAL = "81.2.69.160"  # what Render appended: the real client
HAIKU_BODY = {"model": "claude-haiku-5-5", "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]}


@pytest.fixture
def make_cloud(tmp_path, monkeypatch):
    clients = []

    def make(unset=(), **env):
        base = {"ADMIN_TOKEN": ADMIN_TOKEN, "DB_PATH": str(tmp_path / "miyagi.db"), "TRUSTED_PROXY_HOPS": "1",
                "ANTHROPIC_API_KEY": "fake-upstream-key", "UPSTREAM_ANTHROPIC_URL": "http://127.0.0.1:9/v1/messages",
                "FREE_DAILY_USD": "0", "ANON_DAILY_USD_PER_NETWORK": "0", "REGION_BLOCK": "0"}
        for k, v in {**base, **env}.items():
            monkeypatch.setenv(k, v)
        for k in ("CLIENT_IP_HEADER", "FORWARDED_ALLOW_IPS", "COUNTRY_DB_PATH", "COUNTRY_HEADER", *unset):
            if k not in env:
                monkeypatch.delenv(k, raising=False)
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


def scope(*xff: str, peer: str = "10.0.0.1", **headers: str) -> dict:
    raw = [(b"x-forwarded-for", v.encode()) for v in xff]
    raw += [(k.replace("_", "-").encode(), v.encode()) for k, v in headers.items()]
    return {"type": "http", "headers": raw, "client": (peer, 1234)}


def spoofed(i: int) -> dict:
    """A client rotating what it writes on the left; Render's appended entry (the right) stays REAL."""
    return {"X-Forwarded-For": f"203.0.113.{i % 250 + 1}, 10.{i % 250}.0.1, {REAL}"}


# --------------------------------------------------------------------------- the helper

def test_rightmost_trusted_hop_never_the_leftmost(make_cloud):
    _, app_mod = make_cloud()
    ip = app_mod.client_ip_scope
    assert ip(scope(REAL)) == REAL
    assert ip(scope(f"1.1.1.1, {REAL}")) == REAL
    assert ip(scope(f"1.1.1.1, 2.2.2.2, 3.3.3.3, {REAL}")) == REAL
    assert ip(scope("1.1.1.1", REAL)) == REAL  # two header lines: proxies append, so the last line's last entry


def test_hop_count_is_configurable(make_cloud):
    _, app_mod = make_cloud(TRUSTED_PROXY_HOPS="2")
    ip = app_mod.client_ip_scope
    assert ip(scope(f"6.6.6.6, {REAL}, 104.16.1.1")) == REAL  # e.g. Cloudflare then Render
    assert ip(scope(REAL)) == "10.0.0.1"  # fewer entries than hops: the socket peer, never a client entry
    _, app_mod = make_cloud(TRUSTED_PROXY_HOPS="0")
    assert app_mod.client_ip_scope(scope(f"6.6.6.6, {REAL}")) == "10.0.0.1"
    _, app_mod = make_cloud(TRUSTED_PROXY_HOPS="-3")
    assert app_mod.PROXY_HOPS == 0


def test_no_header_uses_the_socket_peer(make_cloud):
    _, app_mod = make_cloud()
    ip = app_mod.client_ip_scope
    assert ip(scope()) == "10.0.0.1"
    assert ip(scope(peer="2001:db8::7")) == "2001:db8::7"
    assert ip({"type": "http", "headers": []}) == "unknown"


@pytest.mark.parametrize("value,expected", [
    ("garbage", "10.0.0.1"), ("unknown", "10.0.0.1"), ("", "10.0.0.1"), (" , ,", "10.0.0.1"),
    ("1.2.3.4.5", "10.0.0.1"), ("999.1.1.1", "10.0.0.1"), ("x" * 500, "10.0.0.1"),
    (f'"{REAL}"', REAL), (f"  {REAL}  ", REAL), (f"{REAL}:4431", REAL), (f"6.6.6.6,{REAL}", REAL),
    ("[2001:db8::1]:443", "2001:db8::1"), ("2001:DB8:0::1", "2001:db8::1"), ("fe80::1%eth0", "fe80::1"),
    ("::ffff:81.2.69.160", REAL), ("[::ffff:81.2.69.160]:80", REAL),
])
def test_values_are_stripped_validated_and_normalised(make_cloud, value, expected):
    _, app_mod = make_cloud()
    assert app_mod.client_ip_scope(scope(value)) == expected


def test_a_malformed_trusted_entry_falls_back_to_the_peer_not_to_a_client_entry(make_cloud):
    _, app_mod = make_cloud()
    assert app_mod.client_ip_scope(scope(f"{REAL}, not-an-ip")) == "10.0.0.1"


def test_client_ip_header_when_configured(make_cloud):
    _, app_mod = make_cloud(CLIENT_IP_HEADER="CF-Connecting-IP")
    ip = app_mod.client_ip_scope
    assert app_mod.CLIENT_IP_HEADER == "cf-connecting-ip"
    assert ip(scope(f"6.6.6.6, {REAL}", cf_connecting_ip="198.51.100.4")) == "198.51.100.4"
    assert ip(scope(REAL, cf_connecting_ip="::ffff:198.51.100.4")) == "198.51.100.4"
    assert ip(scope(REAL, cf_connecting_ip="nonsense")) == REAL  # invalid: the trusted hop
    assert ip(scope(REAL)) == REAL  # absent: the trusted hop


def test_edge_headers_are_ignored_unless_configured(make_cloud):
    _, app_mod = make_cloud()
    for name in ("cf_connecting_ip", "true_client_ip", "x_real_ip"):
        assert app_mod.client_ip_scope(scope(REAL, **{name: "6.6.6.6"})) == REAL


def test_every_caller_goes_through_the_helper():
    src = (CLOUD / "app.py").read_text()
    helper = src[src.index("def client_ip_scope"):src.index("def ip_bucket")]
    rest = src.replace(helper, "")
    readers = ('b"x-forwarded-for"', "headers.get(\"x-forwarded-for", "headers.get('x-forwarded-for", 'scope.get("client")',
               "scope['client']", 'scope["client"]', "request.client")
    for f, text in [("app.py", rest)] + [(f, (CLOUD / f).read_text()) for f in ("store.py", "geo.py", "supabase_auth.py")]:
        low = text.lower()
        assert not [r for r in readers if r.lower() in low], f
    assert rest.count("client_ip_scope(") >= 2  # client_ip() and the rate limiter


# --------------------------------------------------------------------------- a spoofed leftmost entry dodges nothing

def test_spoofing_does_not_dodge_the_ip_rate_limit(make_cloud):
    client, _ = make_cloud(RATE_LIMIT_PER_IP_PER_HOUR="5", REGISTER_LIMIT_PER_HOUR="100")
    codes = [client.post("/v1/install", headers=spoofed(i), json={}).status_code for i in range(6)]
    assert codes == [200] * 5 + [429]
    other = client.post("/v1/install", headers={"X-Forwarded-For": f"{REAL}, 8.8.8.8"}, json={})
    assert other.status_code == 200  # a different real address has its own bucket


def test_spoofing_does_not_dodge_the_mint_limit(make_cloud):
    client, _ = make_cloud(REGISTER_LIMIT_PER_HOUR="3")
    codes = [client.post("/v1/install", headers=spoofed(i), json={}) for i in range(4)]
    assert [r.status_code for r in codes] == [200, 200, 200, 429]
    assert codes[-1].json()["error"]["limit"] == "install_hourly"


def test_spoofing_does_not_dodge_the_network_spend_pool(make_cloud):
    client, app_mod = make_cloud(ANON_DAILY_USD_PER_NETWORK="1.00", FREE_DAILY_USD="5", REGISTER_LIMIT_PER_HOUR="20")
    tokens = [client.post("/v1/install", headers=spoofed(i), json={}).json()["token"] for i in range(3)]
    nets = {app_mod.store.get_token(app_mod.hash_token(t))["mint_net"] for t in tokens}
    assert len(nets) == 1  # one network, whatever the client wrote
    app_mod.store.add_tokens(app_mod.hash_token(tokens[0]), "anthropic", "claude-haiku-5-5", 10, 10, 1.00)
    r = client.post("/v1/anthropic/v1/messages", headers={"Authorization": f"Bearer {tokens[2]}", **spoofed(9)},
                    json=HAIKU_BODY)
    assert r.status_code == 429 and r.json()["error"]["scope"] == "network"


def test_spoofing_does_not_dodge_the_region_block(make_cloud, tmp_path):
    db = tmp_path / "c.csv.gz"
    with gzip.open(db, "wt") as f:
        f.write(f"{REAL},{REAL},DE\n8.8.8.0,8.8.8.255,US\n")
    client, _ = make_cloud(REGION_BLOCK="1", COUNTRY_DB_PATH=str(db))
    r = client.post("/v1/install", headers={"X-Forwarded-For": f"8.8.8.8, {REAL}"}, json={})
    assert r.status_code == 451  # the US address on the left is the client's own text
    assert client.post("/v1/install", headers={"X-Forwarded-For": f"{REAL}, 8.8.8.8"}, json={}).status_code == 200


def test_spoofing_does_not_dodge_the_admin_lockout(make_cloud):
    client, _ = make_cloud(ADMIN_LOCKOUT_FAILURES="3", ADMIN_RATE_LIMIT_PER_IP_PER_HOUR="100")
    for i in range(3):
        r = client.get("/admin/usage", headers={"X-Admin-Token": f"wrong-{i}", **spoofed(i)})
        assert r.status_code in (401, 403)
    r = client.get("/admin/usage", headers={"X-Admin-Token": ADMIN_TOKEN, **spoofed(7)})
    assert r.status_code == 429 and r.json()["error"]["limit"] == "admin_lockout"
    ok = client.get("/admin/usage", headers={"X-Admin-Token": ADMIN_TOKEN, "X-Forwarded-For": "8.8.4.4"})
    assert ok.status_code == 200  # another real network is not locked out


def test_ipv6_spoofing_does_not_dodge_the_rate_limit(make_cloud):
    client, _ = make_cloud(RATE_LIMIT_PER_IP_PER_HOUR="3", REGISTER_LIMIT_PER_HOUR="100")
    real6 = "2001:db8:5:6::1"
    codes = [client.post("/v1/install", headers={"X-Forwarded-For": f"2001:db8:{i}::1, [{real6}]:443"}, json={}).status_code
             for i in range(4)]
    assert codes == [200, 200, 200, 429]


# --------------------------------------------------------------------------- the staging check's log lines

def test_first_request_logs_the_edge_headers_without_values(make_cloud, caplog):
    client, _ = make_cloud()
    with caplog.at_level(logging.INFO, logger="miyagi.cloud"):
        client.post("/v1/install", json={}, headers={"X-Forwarded-For": f"1.2.3.4, {REAL}",
                                                       "CF-Connecting-IP": REAL, "True-Client-IP": "1.2.3.4"})
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith(("first request", "edge client-IP"))]
    assert lines == [
        "first request: 2 X-Forwarded-For entries (TRUSTED_PROXY_HOPS=1); the chosen entry is a global address",
        "edge client-IP headers: cf-connecting-ip a global address, same as the chosen entry; true-client-ip a global "
        "address, differs from the chosen entry, EQUALS AN ENTRY THE CLIENT WROTE (not overwritten by the edge: never "
        "trust it); x-real-ip absent; CLIENT_IP_HEADER=unset"]
    assert REAL not in caplog.text and "1.2.3.4" not in caplog.text


def test_forwarded_allow_ips_warns(make_cloud, caplog):
    with caplog.at_level(logging.WARNING, logger="miyagi.cloud"):
        make_cloud(FORWARDED_ALLOW_IPS="*")
    assert "--no-proxy-headers" in caplog.text


def test_render_start_command_turns_uvicorns_proxy_headers_off():
    assert "--no-proxy-headers" in (CLOUD / "render.yaml").read_text()

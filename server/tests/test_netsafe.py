"""server.netsafe refuses every way a fetched URL could reach this Mac, the LAN or a metadata service
(claude/eng-keys-ssrf). Zero real network: an httpx.MockTransport serves the pages, socket.getaddrinfo is
monkeypatched, and a small wrapper plays the socket (it reports the peer address the way httpcore does)."""

from __future__ import annotations

import asyncio
import gzip
import socket
from pathlib import Path

import httpx
import pytest

from server import netsafe

PUBLIC = "93.184.216.34"
DNS = {  # what the fake resolver answers
    "example.com": [PUBLIC],
    "www.youtube.com": ["142.250.80.46"],
    "cdn.example.net": [PUBLIC, "2606:2800:220:1:248:1893:25c8:1946"],
    "rebind.example": [PUBLIC],                 # checked as public, then the socket lands on loopback
    "evil.example": ["127.0.0.1"],
    "lan.example": ["192.168.1.10"],
    "mixed.example": [PUBLIC, "10.0.0.7"],      # one bad address is enough to refuse
    "mapped.example": ["::ffff:127.0.0.1"],
    "ula.example": ["fd00::5"],
}
PEER = {"rebind.example": "127.0.0.1"}  # where the fake socket really connects, when not the DNS answer


@pytest.fixture(autouse=True)
def fake_dns(monkeypatch):
    lookups: list[str] = []

    def getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        lookups.append(host)
        if host not in DNS:
            raise socket.gaierror(socket.EAI_NONAME, "nodename nor servname provided")
        out = []
        for ip in DNS[host]:
            fam = socket.AF_INET6 if ":" in ip else socket.AF_INET
            sa = (ip, port, 0, 0) if fam == socket.AF_INET6 else (ip, port)
            out.append((fam, socket.SOCK_STREAM, 6, "", sa))
        return out

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    return lookups


class _Stream:
    def __init__(self, addr):
        self.addr = addr

    def get_extra_info(self, name):
        return self.addr if name == "server_addr" else None


class FakeNet(httpx.AsyncBaseTransport):
    """A MockTransport behind a pretend socket: the response carries network_stream.server_addr, the address the
    connection reached (the DNS answer, or PEER's)."""

    def __init__(self, handler):
        self.mock = httpx.MockTransport(handler)
        self.seen: list[str] = []

    async def handle_async_request(self, request):
        self.seen.append(str(request.url))
        resp = await self.mock.handle_async_request(request)
        host = request.url.host
        ip = PEER.get(host) or (DNS.get(host) or [host])[0]
        resp.extensions["network_stream"] = _Stream((ip, request.url.port or 443))
        return resp


def redirecting(routes: dict[str, httpx.Response]):
    def handler(req: httpx.Request) -> httpx.Response:
        key = f"{req.url.host}{req.url.path}"
        if key in routes:
            return routes[key]
        return httpx.Response(200, text=f"page {req.url}")
    return handler


def fetch(url, net=None, **kw):
    async def go():
        async with netsafe.async_client(transport=net or FakeNet(redirecting({}))) as c:
            return await netsafe.get(url, client=c, **kw)
    return asyncio.run(go())


def refused(url, net=None, **kw) -> str:
    with pytest.raises(netsafe.BlockedURL) as e:
        fetch(url, net, **kw)
    return str(e.value)


# --------------------------------------------------------------------------- redirects to private places


@pytest.mark.parametrize("target", [
    "http://127.0.0.1:8791/text",          # the VS Code companion
    "http://127.0.0.1:8787/debug",         # the engine
    "http://10.0.0.5/",
    "http://169.254.169.254/latest/meta-data/",
    "http://[::1]:8791/text",
    "http://evil.example/",                # a name that resolves to 127.0.0.1
    "http://lan.example/admin",
    "http://mixed.example/",
    "http://mapped.example/",
    "http://ula.example/",
    "http://[::ffff:7f00:1]/",
    "http://[fd12:3456::1]/",
    "http://[fe80::1]/",
    "http://100.64.0.1/",
    "http://0.0.0.0:8787/",
    "http://[::]/",
    "http://224.0.0.1/",
    "http://2130706433/",                  # 127.0.0.1 as a single number
    "http://0x7f.1/",
    "http://localhost:8787/",
    "http://miyagi.localhost/",
    "file:///etc/passwd",
    "ftp://example.com/x",
])
def test_a_public_page_that_redirects_somewhere_private_is_refused(target):
    net = FakeNet(redirecting({"example.com/go": httpx.Response(302, headers={"Location": target})}))
    refused("https://example.com/go", net)
    assert all("example.com" in u for u in net.seen), net.seen  # the private hop was never requested


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8791/text", "http://10.0.0.5/", "http://169.254.169.254/", "http://[::1]/",
    "http://evil.example/", "file:///etc/passwd", "ftp://example.com/", "gopher://example.com/",
    "http://user:pw@example.com/", "http://172.16.0.1/", "http://192.168.0.1/",
])
def test_a_private_url_is_refused_before_any_request(url):
    net = FakeNet(redirecting({}))
    refused(url, net)
    assert net.seen == []


def test_more_than_three_redirects_is_refused():
    routes = {f"example.com/r{i}": httpx.Response(302, headers={"Location": f"/r{i + 1}"}) for i in range(5)}
    net = FakeNet(redirecting(routes))
    assert "redirects" in refused("https://example.com/r0", net)
    assert len(net.seen) == 4  # the first request and three hops


def test_three_redirects_are_followed():
    routes = {f"example.com/r{i}": httpx.Response(302, headers={"Location": f"/r{i + 1}"}) for i in range(3)}
    r = fetch("https://example.com/r0", FakeNet(redirecting(routes)))
    assert r.status_code == 200 and str(r.url) == "https://example.com/r3"


def test_dns_rebinding_is_caught_at_the_socket():
    """The name resolved to a public address when checked, but the connection reached 127.0.0.1."""
    assert "non-public" in refused("https://rebind.example/")


def test_a_public_200_succeeds(fake_dns):
    r = fetch("https://example.com/page")
    assert r.status_code == 200 and r.text == "page https://example.com/page"
    assert "example.com" in fake_dns  # the host really was resolved


def test_ipv6_and_redirect_to_another_public_host():
    net = FakeNet(redirecting({"example.com/x": httpx.Response(301, headers={"Location": "https://cdn.example.net/y"})}))
    r = fetch("https://example.com/x", net)
    assert r.status_code == 200 and r.url.host == "cdn.example.net"


def test_cookie_and_authorization_do_not_follow_a_redirect_to_another_host():
    sent: dict[str, httpx.Headers] = {}

    def handler(req):
        sent[req.url.host] = req.headers
        if req.url.host == "example.com":
            return httpx.Response(302, headers={"Location": "https://cdn.example.net/"})
        return httpx.Response(200, text="ok")

    fetch("https://example.com/", FakeNet(handler), headers={"Cookie": "CONSENT=YES+1", "Authorization": "Bearer t"})
    assert sent["example.com"]["cookie"] == "CONSENT=YES+1"
    assert "cookie" not in sent["cdn.example.net"] and "authorization" not in sent["cdn.example.net"]


def test_no_cookie_jar():
    seen: list[str | None] = []

    def handler(req):
        seen.append(req.headers.get("cookie"))
        return httpx.Response(200, headers={"Set-Cookie": "sid=abc; Path=/"}, text="ok")

    async def go():
        async with netsafe.async_client(transport=FakeNet(handler)) as c:
            await netsafe.get("https://example.com/a", client=c)
            await netsafe.get("https://example.com/b", client=c)
    asyncio.run(go())
    assert seen == [None, None]


# --------------------------------------------------------------------------- body cap


def test_a_body_over_the_cap_is_refused():
    big = FakeNet(lambda req: httpx.Response(200, content=b"x" * 5000))
    with pytest.raises(netsafe.BodyTooLarge):
        fetch("https://example.com/big", big, max_bytes=1000)


def test_a_body_over_the_cap_can_be_truncated():
    big = FakeNet(lambda req: httpx.Response(200, content=b"x" * 5000))
    r = fetch("https://example.com/big", big, max_bytes=1000, truncate=True)
    assert len(r.content) == 1000


def test_the_cap_counts_decoded_bytes():
    """A small gzip body that inflates past the cap (a zip bomb) stops at the cap."""
    bomb = gzip.compress(b"0" * 3_000_000)
    net = FakeNet(lambda req: httpx.Response(200, content=bomb, headers={"Content-Encoding": "gzip"}))
    assert len(bomb) < 100_000
    with pytest.raises(netsafe.BodyTooLarge):
        fetch("https://example.com/bomb", net)  # default cap: 2 MB
    r = fetch("https://example.com/small", FakeNet(lambda req: httpx.Response(
        200, content=gzip.compress(b"hello"), headers={"Content-Encoding": "gzip"})))
    assert r.text == "hello"


def test_the_default_cap_is_two_megabytes():
    assert netsafe.MAX_BYTES == 2 * 1024 * 1024


# --------------------------------------------------------------------------- the guarded client (finder)


def test_the_guarded_client_checks_every_hop_httpx_follows():
    """A client made with redirects=True (the finder's, shared with sources / verify) refuses a private hop too."""
    net = FakeNet(redirecting({"example.com/go": httpx.Response(302, headers={"Location": "http://127.0.0.1:8791/text"})}))

    async def go():
        async with netsafe.async_client(transport=net, redirects=True) as c:
            return await c.get("https://example.com/go")
    with pytest.raises(netsafe.BlockedURL):
        asyncio.run(go())
    assert net.seen == ["https://example.com/go"]


def test_the_guarded_client_stops_after_three_hops():
    routes = {f"example.com/r{i}": httpx.Response(302, headers={"Location": f"/r{i + 1}"}) for i in range(5)}

    async def go():
        async with netsafe.async_client(transport=FakeNet(redirecting(routes)), redirects=True) as c:
            return await c.get("https://example.com/r0")
    with pytest.raises(httpx.TooManyRedirects):
        asyncio.run(go())


def test_blocked_is_an_httpx_error():
    """Callers that catch httpx.HTTPError (finder/verify.py) treat a refusal as unreachable."""
    assert issubclass(netsafe.BlockedURL, httpx.HTTPError) and issubclass(netsafe.BodyTooLarge, httpx.HTTPError)


def test_a_mock_transport_is_not_resolved(fake_dns):
    """A bare MockTransport makes no connection: names are not looked up (so replay tests stay offline), but a
    literal private address is still refused."""
    async def go(url):
        async with netsafe.async_client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="ok"))) as c:
            return await netsafe.get(url, client=c)
    assert asyncio.run(go("https://unlisted.example/")).text == "ok"
    assert fake_dns == []
    with pytest.raises(netsafe.BlockedURL):
        asyncio.run(go("http://127.0.0.1:8791/text"))


def test_without_a_client_netsafe_uses_its_own(monkeypatch):
    monkeypatch.setattr(netsafe, "TRANSPORT", FakeNet(redirecting(
        {"example.com/go": httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/meta-data/"})})))
    with pytest.raises(netsafe.BlockedURL):
        asyncio.run(netsafe.get("https://example.com/go"))
    assert asyncio.run(netsafe.get("https://example.com/ok")).status_code == 200


@pytest.mark.parametrize("ip,ok", [
    ("93.184.216.34", True), ("8.8.8.8", True), ("2606:4700:4700::1111", True),
    ("127.0.0.1", False), ("127.8.9.10", False), ("10.1.2.3", False), ("172.16.0.1", False), ("172.31.255.255", False),
    ("192.168.1.1", False), ("169.254.169.254", False), ("100.64.0.1", False), ("100.127.255.255", False),
    ("0.0.0.0", False), ("255.255.255.255", False), ("224.0.0.251", False), ("::1", False), ("::", False),
    ("fc00::1", False), ("fd00::1", False), ("fe80::1%en0", False), ("ff02::1", False), ("ff0e::1", False),
    ("::ffff:127.0.0.1", False), ("::ffff:10.0.0.1", False), ("::ffff:8.8.8.8", True),
    ("2002:7f00:0001::", False), ("64:ff9b::7f00:1", False), ("64:ff9b::808:808", True), ("not-an-ip", False),
])
def test_ip_allowed(ip, ok):
    assert netsafe.ip_allowed(ip) is ok


# --------------------------------------------------------------------------- the wired callers


YT_PAGE = ('<html><script>var ytInitialPlayerResponse = {"videoDetails": {"title": "PINNs", "shortDescription": '
           '"0:00 Intro\\n1:00 Setup\\n2:00 Train", "lengthSeconds": "600"}, "captions": {"playerCaptionsTracklistRenderer":'
           ' {"captionTracks": [{"baseUrl": "https://www.youtube.com/api/timedtext?v=abc", "languageCode": "en"}]}}};'
           '</script></html>')
CAPTIONS = '{"events": [{"tStartMs": 0, "segs": [{"utf8": "hello"}]}, {"tStartMs": 1500, "segs": [{"utf8": "world"}]}]}'


def test_youtube_transcript_still_works_through_netsafe(monkeypatch):
    from server.lesson import transcript

    def handler(req):
        if req.url.path == "/watch":
            assert req.headers["cookie"] == "CONSENT=YES+1"
            return httpx.Response(200, text=YT_PAGE)
        if req.url.path == "/api/timedtext":
            assert req.url.params["fmt"] == "json3"
            return httpx.Response(200, text=CAPTIONS)
        return httpx.Response(404)

    net = FakeNet(handler)
    monkeypatch.setattr(netsafe, "TRANSPORT", net)
    monkeypatch.setattr(transcript, "_yta_transcript", lambda vid: pytest.fail("the direct path should have worked"))
    transcript._meta_tasks.clear()
    info = asyncio.run(transcript._fetch_video_info("abc"))
    assert info["title"] == "PINNs" and len(info["chapters"]) == 3
    assert info["transcript"] == [{"t": 0.0, "text": "hello"}, {"t": 1.5, "text": "world"}]
    assert info["sources"]["transcript"] == "youtube.com timedtext"
    transcript._meta_tasks.clear()


def test_a_poisoned_caption_track_url_is_not_fetched(monkeypatch):
    """The caption baseUrl comes from the page: pointing it at the companion gets nothing."""
    from server.lesson import transcript

    net = FakeNet(lambda req: httpx.Response(200, text="secret code"))
    monkeypatch.setattr(netsafe, "TRANSPORT", net)
    with pytest.raises(netsafe.BlockedURL):
        asyncio.run(transcript._direct_captions([{"baseUrl": "http://127.0.0.1:8791/text?x=1", "languageCode": "en"}]))
    assert net.seen == []


def test_lesson_links_never_fetch_private_hosts_and_drop_the_query(monkeypatch):
    from server.lesson import links

    def handler(req):
        if req.url.host == "example.com" and req.url.path == "/hop":
            return httpx.Response(302, headers={"Location": "http://10.0.0.5/"})
        return httpx.Response(200)

    net = FakeNet(handler)
    monkeypatch.setattr(netsafe, "TRANSPORT", net)
    steps = [{"id": "s1", "instructions": "See https://example.com/repo?token=abc and https://example.com/hop and "
                                          "http://evil.example/x and http://172.20.0.3:8080/app"}]
    bad = asyncio.run(links.find_bad_urls(steps, ""))
    assert bad == {"https://example.com/hop", "http://evil.example/x"}
    assert all("?" not in u for u in net.seen), net.seen  # the query string never left
    assert not any(h in u for u in net.seen for h in ("10.0.0.5", "evil.example", "172.20.0.3")), net.seen


def test_preflight_watch_page_refuses_a_redirect_to_the_engine(fake_dns):
    from server.preflight import meta

    seen: list[str] = []

    def handler(req):
        seen.append(str(req.url))
        return httpx.Response(302, headers={"Location": "http://127.0.0.1:8787/v1/state"})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await meta._direct(c, "https://www.youtube.com/watch?v=abc&hl=en", 3.0)
    with pytest.raises(netsafe.BlockedURL):
        asyncio.run(go())
    assert seen == ["https://www.youtube.com/watch?v=abc&hl=en"]


def _finder_run(client):
    import time

    from server.finder import core, sources
    from server.finder.env import Keys

    run = core._Run.__new__(core._Run)
    run.query, run.keys, run.t0 = "pinn", Keys(gemini=None, anthropic="test-key", github=None), time.monotonic()
    run.ctx = sources.Ctx(client=client, keys=run.keys)
    return run


def test_finder_page_read_refuses_a_search_hit_that_redirects_to_the_lan(monkeypatch):
    """finder/core.py _read: a page from search results that 302s to 192.168.1.1 is never fetched or read."""
    from server.finder import claude as finder_claude

    net = FakeNet(redirecting({"example.com/post": httpx.Response(302, headers={"Location": "http://192.168.1.1/"})}))
    monkeypatch.setattr(finder_claude, "read", lambda *a, **k: pytest.fail("a refused page must not reach Claude"))

    async def go():
        async with netsafe.async_client(transport=net, redirects=True) as c:
            cand = {"id": "blog-1", "kind": "blog", "url": "https://example.com/post"}
            await _finder_run(c)._read(cand)
            return cand
    cand = asyncio.run(go())
    assert cand["watched"] == "not read: page fetch failed"
    assert net.seen == ["https://example.com/post"]


def test_finder_builds_its_client_with_netsafe(monkeypatch):
    from server.finder import core

    made: list[dict] = []
    real = netsafe.async_client

    def spy(**kw):
        made.append(kw)
        return real(**kw)

    async def no_sources(self):
        return None

    async def no_deep(self, client):
        return None

    monkeypatch.setattr(netsafe, "async_client", spy)
    monkeypatch.setattr(core._Run, "_gather_sources", no_sources)
    monkeypatch.setattr(core._Run, "_deep_pass", no_deep)
    monkeypatch.setattr(core, "HTTP_TRANSPORT", httpx.MockTransport(lambda r: httpx.Response(404)))
    from server.finder.env import Keys

    run = core._Run("pinn", Keys(gemini=None, anthropic=None, github=None), None, skim_top=0, emit_updates=False)
    asyncio.run(run.go())
    assert made and made[0]["redirects"] is True and made[0]["transport"] is core.HTTP_TRANSPORT
    assert made[0]["headers"]["Cookie"] == "CONSENT=YES+1"
    src = Path(core.__file__).read_text()
    assert "follow_redirects=True" not in src

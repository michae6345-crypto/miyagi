"""Outbound HTTP to URLs the engine did not choose itself (claude/eng-keys-ssrf).

Web search results, links in a lesson, a YouTube page's caption URL and every redirect come from the internet, so
an attacker can choose them. Without this, a page that redirects to http://127.0.0.1:8791/text (the VS Code
companion), http://127.0.0.1:8787 (this engine), a router at 192.168.1.1 or 169.254.169.254 would have the engine
fetch it and hand the answer to a model, a card or the lesson. These fetches go through here: the finder
(finder/core.py and the guarded client it hands to finder/sources.py and verify.py), lesson/transcript.py,
lesson/links.py, preflight/meta.py and workspace/resources.py (the tutorial files linked from a video description).
One is still outside: server/coach/web.py (the coach's web search page fetch) builds its own
httpx.AsyncClient(follow_redirects=True); it needs `get` from here in a follow-up by that file's owner. What this
module does:

- http and https only, no user:password@ in the URL;
- redirects are followed by hand (follow_redirects=False on the wire), at most MAX_REDIRECTS hops, and a Cookie or
  Authorization header passed to `get` / `request` is dropped when a hop leaves the first host. Headers set on the
  client itself are merged back into every request httpx builds, so they go to every hop (the finder's static
  `Cookie: CONSENT=YES+1` does; it is not a secret). Never put a secret in a guarded client's headers;
- before each hop the host is resolved with getaddrinfo and EVERY address must be public (`ip_allowed`): no
  loopback, RFC 1918, link-local / 169.254.169.254, CGNAT 100.64/10, multicast, ULA fc00::/7, 0.0.0.0 / ::, and no
  IPv4-mapped, 6to4 or NAT64 spelling of one;
- after connecting, the peer address the socket really reached (response.extensions['network_stream']
  .get_extra_info('server_addr')) is checked too, so when DNS rebinds between the check and the connect the
  response is never read (nothing from a private address reaches a model, a card or the lesson). This does NOT stop
  the request itself: the peer is only known after the request has been sent, so a rebinding host still gets one
  blind GET to a LAN or loopback address. Our own engine and the VS Code companion check Host and their token, so
  they are covered. Follow-up: an httpcore network backend that resolves, checks each address, then connects to the
  checked IP;
- the body is capped (MAX_BYTES, 2 MB, by default). Requests ask for Accept-Encoding: identity; a gzip or deflate
  body a server sends anyway is inflated here from the raw chunks, never more than cap + 1 bytes at a time, so a
  bomb stops at the cap (httpx's own decoder would inflate a whole 64 KB chunk, ~64 MB, before any check). Other
  encodings are refused;
- per-read timeouts always, plus a deadline for the whole fetch (every hop and the body; default
  DEADLINE_FACTOR x the timeout), so a server that drips a byte every few seconds cannot hold a lesson build;
- no cookie jar, no proxy or .netrc from the environment (trust_env=False).

Known limits: trust_env=False also means HTTPS_PROXY / HTTP_PROXY are ignored, so a learner behind a mandatory
proxy gets every guarded fetch refused as unreachable; and fake-IP DNS tools (Surge, Clash, some VPNs) answer with
198.18.0.0/15, which is not global, so every guarded fetch is refused there too.

`get` / `head` fetch one URL; `get_sync` / `request_sync` (with `sync_client`) do the same for blocking code in a
worker thread (workspace/resources.py). `async_client` builds a client whose transport makes the same checks on
every request and every redirect hop, for code that hands one client to many helpers (the finder). Refusals raise `BlockedURL`
(an httpx.RequestError, so `except httpx.HTTPError` callers treat it as unreachable); an oversized body raises
`BodyTooLarge` unless the caller asked for `truncate=True`; a fetch past its deadline raises httpx.TimeoutException.
Only `get` / `head` / `request(_sync)` have the deadline and the safe inflate: a guarded client used directly
(client.get) has the per-hop checks, httpx's own redirect cap and per-read timeouts only.

Tests: an httpx.MockTransport makes no connection, so nothing is resolved for it (literal IPs and schemes are still
checked). To exercise resolution, wrap the mock in a transport of your own and monkeypatch socket.getaddrinfo.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
import time
import zlib
from http.cookiejar import CookieJar, DefaultCookiePolicy
from typing import Any

import httpx

log = logging.getLogger("server.netsafe")

MAX_BYTES = 2 * 1024 * 1024
PAGE_MAX_BYTES = 8 * 1024 * 1024  # a YouTube watch page is 1-3 MB of HTML; caption tracks of long videos a few MB
MAX_REDIRECTS = 3
DEFAULT_TIMEOUT = 10.0
DEADLINE_FACTOR = 3.0  # a whole fetch may take at most this many per-call timeouts
SCHEMES = ("http", "https")
_CROSS_HOST_DROP = ("cookie", "authorization", "proxy-authorization")
# tests swap in a fake network (a transport that is not an httpx.MockTransport is resolved like the real one)
TRANSPORT: httpx.AsyncBaseTransport | None = None
SYNC_TRANSPORT: httpx.BaseTransport | None = None

_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_NAT64_LOCAL = ipaddress.ip_network("64:ff9b:1::/48")


class BlockedURL(httpx.RequestError):
    """The URL, a redirect hop or the address it reached is not a public http(s) server."""


class BodyTooLarge(httpx.HTTPError):
    """The response body is larger than the caller's cap."""


def ip_allowed(ip: str | ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True only for a globally routable unicast address. IPv6 forms that embed an IPv4 address (IPv4-mapped
    ::ffff:a.b.c.d, 6to4 2002::/16, NAT64 64:ff9b::/96) are judged by the IPv4 address inside."""
    try:
        a = ipaddress.ip_address(ip.split("%", 1)[0] if isinstance(ip, str) else ip)  # drop an IPv6 zone id
    except ValueError:
        return False
    if isinstance(a, ipaddress.IPv6Address):
        if a.ipv4_mapped is not None:
            return ip_allowed(a.ipv4_mapped)
        if a.sixtofour is not None:
            return ip_allowed(a.sixtofour)
        if a in _NAT64:
            return ip_allowed(ipaddress.IPv4Address(int(a) & 0xFFFFFFFF))
        if a in _NAT64_LOCAL:
            return False
    if a.is_multicast or a.is_unspecified or a.is_loopback or a.is_link_local or a.is_private or a.is_reserved:
        return False
    if isinstance(a, ipaddress.IPv6Address) and a.is_site_local:  # deprecated fec0::/10
        return False
    return a.is_global


def _literal_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    h = host.strip("[]")
    try:
        return ipaddress.ip_address(h.split("%", 1)[0])
    except ValueError:
        pass
    # inet_aton spellings the resolver accepts as IPv4: 2130706433, 0x7f.1, 017700000001, 127.1
    if h and all(c in "0123456789abcdefxABCDEFX." for c in h) and any(c.isdigit() for c in h):
        try:
            return ipaddress.IPv4Address(socket.inet_aton(h))
        except OSError:
            return None
    return None


def check_url(url: str | httpx.URL) -> httpx.URL:
    """Scheme, credentials and the host's spelling (no DNS). Raises BlockedURL; returns the parsed URL."""
    try:
        u = url if isinstance(url, httpx.URL) else httpx.URL(url)
    except (httpx.InvalidURL, TypeError, ValueError) as e:
        raise BlockedURL(f"not a URL: {e}") from None
    if u.scheme not in SCHEMES:
        raise BlockedURL(f"scheme {u.scheme or '(none)'!r} is not http(s)")
    host = (u.host or "").lower().rstrip(".")
    if not host:
        raise BlockedURL("no host")
    if u.userinfo:
        raise BlockedURL(f"credentials in the URL for {host}")
    if host == "localhost" or host.endswith(".localhost"):
        raise BlockedURL(f"{host} is this Mac")
    ip = _literal_ip(host)
    if ip is not None and not ip_allowed(ip):
        raise BlockedURL(f"{host} is not a public address")
    return u


def _port(u: httpx.URL) -> int:
    return u.port or (443 if u.scheme == "https" else 80)


def _check_addrs(host: str, infos: list) -> None:
    addrs = {info[4][0] for info in infos if info and len(info) > 4 and info[4]}
    if not addrs:
        raise BlockedURL(f"{host} did not resolve")
    bad = sorted(a for a in addrs if not ip_allowed(a))
    if bad:
        raise BlockedURL(f"{host} resolves to a non-public address ({bad[0]})")


def check_host(u: httpx.URL) -> None:
    """Resolve the URL's host (blocking getaddrinfo) and refuse it unless every address is public."""
    host = u.host
    if _literal_ip(host) is not None:
        return  # check_url judged it
    try:
        infos = socket.getaddrinfo(host, _port(u), type=socket.SOCK_STREAM)
    except (OSError, UnicodeError) as e:
        raise BlockedURL(f"{host} did not resolve: {e}") from None
    _check_addrs(host, infos)


async def acheck_url(url: str | httpx.URL, *, resolve: bool = True) -> httpx.URL:
    """check_url, then (resolve=True) the host's addresses, off the event loop."""
    u = check_url(url)
    if resolve:
        await asyncio.to_thread(check_host, u)
    return u


def check_peer(response: httpx.Response) -> None:
    """Refuse a response whose socket reached a non-public address (DNS rebinding after the check): its body is never
    read. The request has already been sent by then (a blind GET; see the module docstring). Transports that report
    no network stream (HTTP/2, test transports) are judged by the pre-connect check alone."""
    stream = response.extensions.get("network_stream")
    get = getattr(stream, "get_extra_info", None)
    if get is None:
        return
    try:
        addr = get("server_addr")
    except Exception:  # noqa: BLE001  a transport without the info
        return
    if isinstance(addr, tuple) and addr and isinstance(addr[0], str) and not ip_allowed(addr[0]):
        raise BlockedURL(f"{response.request.url.host} connected to a non-public address ({addr[0]})")


def _makes_connections(transport: Any) -> bool:
    return not isinstance(transport, httpx.MockTransport)


class GuardTransport(httpx.AsyncBaseTransport):
    """Checks every request (so every redirect hop a client follows) before it leaves and the peer after it lands."""

    def __init__(self, inner: httpx.AsyncBaseTransport | None = None, *, resolve: bool | None = None,
                 limits: httpx.Limits | None = None) -> None:
        if inner is None:
            inner = TRANSPORT
        if inner is None:
            inner = httpx.AsyncHTTPTransport(limits=limits) if limits else httpx.AsyncHTTPTransport()
        self.inner = inner
        self.resolve = _makes_connections(inner) if resolve is None else resolve

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        await acheck_url(request.url, resolve=self.resolve)
        response = await self.inner.handle_async_request(request)
        try:
            response.request = request
            check_peer(response)
        except BlockedURL:
            await response.aclose()
            raise
        return response

    async def aclose(self) -> None:
        await self.inner.aclose()


class _NoCookies(DefaultCookiePolicy):
    def set_ok(self, cookie, request) -> bool:  # type: ignore[override]
        return False

    def return_ok(self, cookie, request) -> bool:  # type: ignore[override]
        return False


def no_cookie_jar() -> CookieJar:
    """A jar that never stores or sends a cookie (a static Cookie header the caller sets still goes out)."""
    return CookieJar(policy=_NoCookies())


def async_client(*, transport: httpx.AsyncBaseTransport | None = None, headers: dict | None = None,
                 timeout: float | httpx.Timeout = DEFAULT_TIMEOUT, redirects: bool = False,
                 limits: httpx.Limits | None = None, resolve: bool | None = None) -> httpx.AsyncClient:
    """An AsyncClient whose every request is checked (GuardTransport), with no cookie jar and nothing from the
    environment. `get(url, client=...)` on it follows redirects by hand and caps the body.

    redirects=True is for a client handed to helpers that call client.get / head / stream themselves (the finder's
    sources and verify): httpx then follows at most MAX_REDIRECTS hops, and each hop is a new request through
    GuardTransport, so it gets the same scheme, DNS and peer checks as a hand-followed one (cookies are dropped on
    every hop, Authorization when the host changes)."""
    return httpx.AsyncClient(transport=GuardTransport(transport, resolve=resolve, limits=limits), headers=headers,
                             timeout=timeout, follow_redirects=redirects, max_redirects=MAX_REDIRECTS,
                             trust_env=False, cookies=no_cookie_jar())


class SyncGuardTransport(httpx.BaseTransport):
    """GuardTransport for a blocking httpx.Client (workspace/resources.py runs in a worker thread)."""

    def __init__(self, inner: httpx.BaseTransport | None = None, *, resolve: bool | None = None) -> None:
        if inner is None:
            inner = SYNC_TRANSPORT
        if inner is None:
            inner = httpx.HTTPTransport()
        self.inner = inner
        self.resolve = _makes_connections(inner) if resolve is None else resolve

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        u = check_url(request.url)
        if self.resolve:
            check_host(u)
        response = self.inner.handle_request(request)
        try:
            response.request = request
            check_peer(response)
        except BlockedURL:
            response.close()
            raise
        return response

    def close(self) -> None:
        self.inner.close()


def sync_client(*, transport: httpx.BaseTransport | None = None, headers: dict | None = None,
                timeout: float | httpx.Timeout = DEFAULT_TIMEOUT, redirects: bool = False,
                resolve: bool | None = None) -> httpx.Client:
    """async_client for blocking code: every request checked (SyncGuardTransport), no cookie jar, nothing from the
    environment. Use it with `get_sync(url, client=...)`."""
    return httpx.Client(transport=SyncGuardTransport(transport, resolve=resolve), headers=headers, timeout=timeout,
                        follow_redirects=redirects, max_redirects=MAX_REDIRECTS, trust_env=False,
                        cookies=no_cookie_jar())


def _client_checks_itself(client: httpx.Client | httpx.AsyncClient, url: httpx.URL) -> tuple[bool, bool]:
    """(guarded, resolve): does the client's transport already check (a Guard transport), and does it connect at
    all."""
    try:
        t = client._transport_for_url(url)  # httpx picks a mount (a proxy) per URL
    except Exception:  # noqa: BLE001  another httpx: check everything ourselves
        return False, True
    return isinstance(t, (GuardTransport, SyncGuardTransport)), _makes_connections(t)


# --------------------------------------------------------------------------- the body: capped while it inflates


class _Body:
    """Collects a response body from its RAW chunks and decodes it here, so the cap holds on decoded bytes without
    ever inflating more than cap + 1 bytes (httpx's own decoder inflates a whole 64 KB chunk at once, about 64 MB
    for a deflate bomb). Requests ask for Accept-Encoding: identity; gzip and deflate are still decoded in case a
    server ignores that, any other encoding is refused.

    A response built in memory (httpx.Response(content=...), as test transports return) arrives already read and
    decoded by httpx; `in_memory` takes its content as is."""

    def __init__(self, response: httpx.Response, max_bytes: int, truncate: bool) -> None:
        self.host = response.request.url.host
        self.max_bytes, self.truncate = max_bytes, truncate
        self.out = bytearray()
        self.done = False
        self.in_memory = response.is_stream_consumed
        enc = [e.strip().lower() for e in response.headers.get("content-encoding", "").split(",") if e.strip()]
        enc = [e for e in enc if e != "identity" and not self.in_memory]
        if len(enc) > 1 or (enc and enc[0] not in ("gzip", "x-gzip", "deflate")):
            raise httpx.DecodingError(f"{self.host}: content-encoding {', '.join(enc)!r} is not supported",
                                      request=response.request)
        self.enc = enc[0] if enc else ""
        self._z = None
        if self.enc:
            self._z = zlib.decompressobj(zlib.MAX_WBITS if self.enc == "deflate" else zlib.MAX_WBITS | 16)
        self._first = True
        declared = response.headers.get("content-length", "")
        if not self.enc and declared.isdigit() and int(declared) > max_bytes and not truncate:
            raise BodyTooLarge(f"{self.host}: {declared} bytes is over the {max_bytes}-byte cap")

    def feed(self, raw: bytes) -> bool:
        """Add one raw chunk; never holds more than cap + 1 decoded bytes. True once truncated at the cap."""
        room = self.max_bytes - len(self.out) + 1
        if self._z is None:
            data = raw[:room]
        else:
            try:
                data = self._z.decompress(raw, room)
            except zlib.error as e:
                if not (self._first and self.enc == "deflate"):
                    raise httpx.DecodingError(f"{self.host}: {e}") from None
                self._z = zlib.decompressobj(-zlib.MAX_WBITS)  # raw deflate, as httpx's DeflateDecoder allows
                try:
                    data = self._z.decompress(raw, room)
                except zlib.error as e2:
                    raise httpx.DecodingError(f"{self.host}: {e2}") from None
        self._first = False
        self.out += data
        if len(self.out) > self.max_bytes:
            if not self.truncate:
                raise BodyTooLarge(f"{self.host}: the body is over the {self.max_bytes}-byte cap")
            del self.out[self.max_bytes:]
            self.done = True
        return self.done

    def bytes(self) -> bytes:
        return bytes(self.out)


# --------------------------------------------------------------------------- one request, every hop checked


def _deadline_for(timeout: float | httpx.Timeout | None, deadline: float | None) -> float:
    """The whole request's wall-clock budget. httpx's timeouts are per read, so a server that drips one byte every
    few seconds would otherwise hold a fetch for days. Default: DEADLINE_FACTOR x the per-call timeout."""
    if deadline is not None:
        return float(deadline)
    if isinstance(timeout, httpx.Timeout):
        parts = [t for t in (timeout.connect, timeout.read, timeout.write, timeout.pool) if t is not None]
        timeout = max(parts) if parts else DEFAULT_TIMEOUT
    return DEADLINE_FACTOR * float(timeout if timeout is not None else DEFAULT_TIMEOUT)


def _prepare(url: str | httpx.URL, params: dict | None, headers: dict | None) -> tuple[httpx.URL, dict]:
    first = check_url(url)
    if params:
        first = first.copy_merge_params(params)
    hdrs = dict(headers or {})
    if not any(k.lower() == "accept-encoding" for k in hdrs):
        hdrs["Accept-Encoding"] = "identity"
    return first, hdrs


def _redirect(resp: httpx.Response, req: httpx.Request, first: httpx.URL, current: httpx.URL, hop: int,
              max_redirects: int, hdrs: dict) -> tuple[httpx.URL, dict] | None:
    """(next URL, headers for it) when resp is a redirect, checked (scheme, credentials, literal IP); else None."""
    location = resp.headers.get("location") if resp.is_redirect else None
    if not location:
        return None
    if hop == max_redirects:
        raise BlockedURL(f"more than {max_redirects} redirects from {first.host}", request=req)
    try:
        nxt = current.join(location)
    except (httpx.InvalidURL, ValueError) as e:
        raise BlockedURL(f"bad redirect from {current.host}: {e}", request=req) from None
    check_url(nxt)
    if not _same_host(first, nxt):
        hdrs = {k: v for k, v in hdrs.items() if k.lower() not in _CROSS_HOST_DROP}
    return nxt, hdrs


def _final(resp: httpx.Response, req: httpx.Request, body: bytes) -> httpx.Response:
    kept = [(k, v) for k, v in resp.headers.multi_items()
            if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")]
    return httpx.Response(resp.status_code, headers=kept, content=body, request=req,
                          extensions={"http_version": resp.extensions.get("http_version", b"HTTP/1.1")})


def _same_host(a: httpx.URL, b: httpx.URL) -> bool:
    return (a.scheme, a.host, _port(a)) == (b.scheme, b.host, _port(b)) or (
        a.host == b.host and a.scheme == "http" and b.scheme == "https")


def _too_slow(url: str | httpx.URL, limit: float, req: httpx.Request | None = None) -> httpx.TimeoutException:
    try:
        host = (url if isinstance(url, httpx.URL) else httpx.URL(url)).host
    except Exception:  # noqa: BLE001
        host = "the server"
    return httpx.TimeoutException(f"{host}: no complete answer within {limit:g} s", request=req)


async def request(method: str, url: str | httpx.URL, *, client: httpx.AsyncClient | None = None,
                  headers: dict | None = None, params: dict | None = None,
                  timeout: float | httpx.Timeout = DEFAULT_TIMEOUT, max_bytes: int = MAX_BYTES,
                  max_redirects: int = MAX_REDIRECTS, truncate: bool = False,
                  deadline: float | None = None) -> httpx.Response:
    """One GET / HEAD with every hop checked and the body capped. Returns a read response (any status; call
    raise_for_status yourself); `response.url` is the final hop. Raises BlockedURL, BodyTooLarge, httpx errors, or
    httpx.TimeoutException when the whole fetch (every hop and the body) takes longer than `deadline` seconds
    (default DEADLINE_FACTOR x timeout)."""
    limit = _deadline_for(timeout, deadline)
    try:
        async with asyncio.timeout(limit):
            if client is None:
                async with async_client(timeout=timeout) as c:
                    return await _request(c, method, url, headers, params, timeout, max_bytes, max_redirects,
                                          truncate)
            return await _request(client, method, url, headers, params, timeout, max_bytes, max_redirects, truncate)
    except TimeoutError:
        raise _too_slow(url, limit) from None


async def _request(client: httpx.AsyncClient, method: str, url: str | httpx.URL, headers: dict | None,
                   params: dict | None, timeout, max_bytes: int, max_redirects: int, truncate: bool) -> httpx.Response:
    first, hdrs = _prepare(url, params, headers)
    current = first
    for hop in range(max_redirects + 1):
        guarded, resolve = _client_checks_itself(client, current)
        if not guarded:
            await acheck_url(current, resolve=resolve)
        req = client.build_request(method, current, headers=hdrs, timeout=timeout)
        resp = await client.send(req, stream=True, follow_redirects=False)
        try:
            check_peer(resp)
            if (nxt := _redirect(resp, req, first, current, hop, max_redirects, hdrs)) is not None:
                current, hdrs = nxt
                continue
            if method.upper() == "HEAD":  # no body: no size or Content-Encoding check (a 30 MB PDF is fine)
                return _final(resp, req, b"")
            body = _Body(resp, max_bytes, truncate)
            if body.in_memory:
                body.feed(resp.content)
            else:
                async for raw in resp.aiter_raw():
                    if body.feed(raw):
                        break
        finally:
            await resp.aclose()
        return _final(resp, req, body.bytes())
    raise BlockedURL(f"more than {max_redirects} redirects from {first.host}")  # not reached


async def get(url: str | httpx.URL, **kw: Any) -> httpx.Response:
    return await request("GET", url, **kw)


async def head(url: str | httpx.URL, **kw: Any) -> httpx.Response:
    return await request("HEAD", url, **kw)


def request_sync(method: str, url: str | httpx.URL, *, client: httpx.Client | None = None,
                 headers: dict | None = None, params: dict | None = None,
                 timeout: float | httpx.Timeout = DEFAULT_TIMEOUT, max_bytes: int = MAX_BYTES,
                 max_redirects: int = MAX_REDIRECTS, truncate: bool = False,
                 deadline: float | None = None) -> httpx.Response:
    """`request` for blocking code (a worker thread): the same checks on every hop, the same cap and deadline. The
    deadline is checked before each hop and after each chunk, and no read waits longer than what is left of it, so a
    dripping server is cut off at the deadline."""
    limit = _deadline_for(timeout, deadline)
    end = time.monotonic() + limit
    if client is None:
        with sync_client(timeout=timeout) as c:
            return _request_sync(c, method, url, headers, params, timeout, max_bytes, max_redirects, truncate,
                                 end, limit)
    return _request_sync(client, method, url, headers, params, timeout, max_bytes, max_redirects, truncate, end,
                         limit)


def _left(end: float, url: httpx.URL, limit: float, req: httpx.Request | None = None) -> float:
    left = end - time.monotonic()
    if left <= 0:
        raise _too_slow(url, limit, req)
    return left


def _request_sync(client: httpx.Client, method: str, url: str | httpx.URL, headers: dict | None,
                  params: dict | None, timeout, max_bytes: int, max_redirects: int, truncate: bool, end: float,
                  limit: float) -> httpx.Response:
    first, hdrs = _prepare(url, params, headers)
    current = first
    per = timeout if isinstance(timeout, httpx.Timeout) else httpx.Timeout(timeout)
    for hop in range(max_redirects + 1):
        guarded, resolve = _client_checks_itself(client, current)
        if not guarded:
            check_url(current)
            if resolve:
                check_host(current)
        left = _left(end, current, limit)
        hop_timeout = httpx.Timeout(connect=min(per.connect or left, left), read=min(per.read or left, left),
                                    write=min(per.write or left, left), pool=min(per.pool or left, left))
        req = client.build_request(method, current, headers=hdrs, timeout=hop_timeout)
        resp = client.send(req, stream=True, follow_redirects=False)
        try:
            check_peer(resp)
            if (nxt := _redirect(resp, req, first, current, hop, max_redirects, hdrs)) is not None:
                current, hdrs = nxt
                continue
            if method.upper() == "HEAD":  # no body: no size or Content-Encoding check
                return _final(resp, req, b"")
            body = _Body(resp, max_bytes, truncate)
            if body.in_memory:
                body.feed(resp.content)
            else:
                for raw in resp.iter_raw():
                    if body.feed(raw):
                        break
                    _left(end, current, limit, req)
        finally:
            resp.close()
        return _final(resp, req, body.bytes())
    raise BlockedURL(f"more than {max_redirects} redirects from {first.host}")  # not reached


def get_sync(url: str | httpx.URL, **kw: Any) -> httpx.Response:
    return request_sync("GET", url, **kw)

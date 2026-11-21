"""Outbound HTTP to URLs the engine did not choose itself (claude/eng-keys-ssrf).

Web search results, links in a lesson, a YouTube page's caption URL and every redirect come from the internet, so
an attacker can choose them. Without this, a page that redirects to http://127.0.0.1:8791/text (the VS Code
companion), http://127.0.0.1:8787 (this engine), a router at 192.168.1.1 or 169.254.169.254 would have the engine
fetch it and hand the answer to a model, a card or the lesson. Every outbound fetch of such a URL goes through here:

- http and https only, no user:password@ in the URL;
- redirects are followed by hand (follow_redirects=False on the wire), at most MAX_REDIRECTS hops, and a Cookie or
  Authorization header is dropped when a hop leaves the first host;
- before each hop the host is resolved with getaddrinfo and EVERY address must be public (`ip_allowed`): no
  loopback, RFC 1918, link-local / 169.254.169.254, CGNAT 100.64/10, multicast, ULA fc00::/7, 0.0.0.0 / ::, and no
  IPv4-mapped, 6to4 or NAT64 spelling of one;
- after connecting, the peer address the socket really reached (response.extensions['network_stream']
  .get_extra_info('server_addr')) is checked too, which defeats DNS rebinding between the check and the connect;
- the body is capped (MAX_BYTES, 2 MB, by default; decoded bytes, so a gzip bomb stops early), timeouts always,
  no cookie jar, no proxy or .netrc from the environment (trust_env=False).

`get` / `head` fetch one URL. `async_client` builds a client whose transport makes the same checks on every request
and every redirect hop, for code that hands one client to many helpers (the finder). Refusals raise `BlockedURL`
(an httpx.RequestError, so `except httpx.HTTPError` callers treat it as unreachable); an oversized body raises
`BodyTooLarge` unless the caller asked for `truncate=True`.

Tests: an httpx.MockTransport makes no connection, so nothing is resolved for it (literal IPs and schemes are still
checked). To exercise resolution, wrap the mock in a transport of your own and monkeypatch socket.getaddrinfo.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from http.cookiejar import CookieJar, DefaultCookiePolicy
from typing import Any

import httpx

log = logging.getLogger("server.netsafe")

MAX_BYTES = 2 * 1024 * 1024
PAGE_MAX_BYTES = 8 * 1024 * 1024  # a YouTube watch page is 1-3 MB of HTML; caption tracks of long videos a few MB
MAX_REDIRECTS = 3
DEFAULT_TIMEOUT = 10.0
SCHEMES = ("http", "https")
_CROSS_HOST_DROP = ("cookie", "authorization", "proxy-authorization")
# tests swap in a fake network (a transport that is not an httpx.MockTransport is resolved like the real one)
TRANSPORT: httpx.AsyncBaseTransport | None = None

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
    """Refuse a response whose socket reached a non-public address (DNS rebinding after the check). Transports that
    report no network stream (HTTP/2, test transports) are judged by the pre-connect check alone."""
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


def _client_checks_itself(client: httpx.AsyncClient, url: httpx.URL) -> tuple[bool, bool]:
    """(guarded, resolve): does the client's transport already check (a GuardTransport), and does it connect at all."""
    try:
        t = client._transport_for_url(url)  # httpx picks a mount (a proxy) per URL
    except Exception:  # noqa: BLE001  another httpx: check everything ourselves
        return False, True
    return isinstance(t, GuardTransport), _makes_connections(t)


async def _read_capped(response: httpx.Response, max_bytes: int, truncate: bool) -> bytes:
    declared = response.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > max_bytes and not truncate:
        raise BodyTooLarge(f"{response.request.url.host}: {declared} bytes is over the {max_bytes}-byte cap")
    out = bytearray()
    async for chunk in response.aiter_bytes():
        out += chunk
        if len(out) > max_bytes:
            if truncate:
                del out[max_bytes:]
                break
            raise BodyTooLarge(f"{response.request.url.host}: the body is over the {max_bytes}-byte cap")
    return bytes(out)


def _same_host(a: httpx.URL, b: httpx.URL) -> bool:
    return (a.scheme, a.host, _port(a)) == (b.scheme, b.host, _port(b)) or (
        a.host == b.host and a.scheme == "http" and b.scheme == "https")


async def request(method: str, url: str | httpx.URL, *, client: httpx.AsyncClient | None = None,
                  headers: dict | None = None, params: dict | None = None,
                  timeout: float | httpx.Timeout = DEFAULT_TIMEOUT, max_bytes: int = MAX_BYTES,
                  max_redirects: int = MAX_REDIRECTS, truncate: bool = False) -> httpx.Response:
    """One GET / HEAD with every hop checked and the body capped. Returns a read response (any status; call
    raise_for_status yourself); `response.url` is the final hop. Raises BlockedURL, BodyTooLarge or httpx errors."""
    if client is None:
        async with async_client(timeout=timeout) as c:
            return await _request(c, method, url, headers, params, timeout, max_bytes, max_redirects, truncate)
    return await _request(client, method, url, headers, params, timeout, max_bytes, max_redirects, truncate)


async def _request(client: httpx.AsyncClient, method: str, url: str | httpx.URL, headers: dict | None,
                   params: dict | None, timeout, max_bytes: int, max_redirects: int, truncate: bool) -> httpx.Response:
    first = check_url(url)
    if params:
        first = first.copy_merge_params(params)
    current, hdrs = first, dict(headers or {})
    for hop in range(max_redirects + 1):
        guarded, resolve = _client_checks_itself(client, current)
        if not guarded:
            await acheck_url(current, resolve=resolve)
        req = client.build_request(method, current, headers=hdrs, timeout=timeout)
        resp = await client.send(req, stream=True, follow_redirects=False)
        try:
            check_peer(resp)
            location = resp.headers.get("location") if resp.is_redirect else None
            if location:
                if hop == max_redirects:
                    raise BlockedURL(f"more than {max_redirects} redirects from {first.host}", request=req)
                try:
                    nxt = current.join(location)
                except (httpx.InvalidURL, ValueError) as e:
                    raise BlockedURL(f"bad redirect from {current.host}: {e}", request=req) from None
                check_url(nxt)
                if not _same_host(first, nxt):
                    hdrs = {k: v for k, v in hdrs.items() if k.lower() not in _CROSS_HOST_DROP}
                current = nxt
                continue
            body = b"" if method.upper() == "HEAD" else await _read_capped(resp, max_bytes, truncate)
        finally:
            await resp.aclose()
        kept = [(k, v) for k, v in resp.headers.multi_items()
                if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")]
        return httpx.Response(resp.status_code, headers=kept, content=body, request=req,
                              extensions={"http_version": resp.extensions.get("http_version", b"HTTP/1.1")})
    raise BlockedURL(f"more than {max_redirects} redirects from {first.host}")  # not reached


async def get(url: str | httpx.URL, **kw: Any) -> httpx.Response:
    return await request("GET", url, **kw)


async def head(url: str | httpx.URL, **kw: Any) -> httpx.Response:
    return await request("HEAD", url, **kw)

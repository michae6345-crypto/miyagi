"""Verify Supabase user access tokens (JWTs) for POST /v1/link.

Asymmetric tokens (ES256, RS256) are checked against the project's JWKS at
${SUPABASE_URL}/auth/v1/.well-known/jwks.json, fetched at most every 10 minutes. Legacy HS256 tokens are
checked with SUPABASE_JWT_SECRET only when it is set. Every token must have aud "authenticated",
iss ${SUPABASE_URL}/auth/v1, a future exp and a non-empty sub.

Nothing here logs or stores the token. The JWKS fetcher is injectable so tests never touch the network.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Callable

import jwt

log = logging.getLogger("miyagi.cloud.auth")

DEFAULT_SUPABASE_URL = "https://wssdpsdbaqtnfhoyimit.supabase.co"
AUDIENCE = "authenticated"
ASYMMETRIC = ("ES256", "RS256")
JWKS_TTL_S = 600.0        # reuse a fetched key set for 10 minutes
RETRY_AFTER_FAIL_S = 30.0  # after a failed fetch, wait this long before asking again
REFRESH_FOR_KID_S = 60.0   # an unknown kid may mean a key rotation: refetch, but not more often than this
MAX_TOKEN_CHARS = 8192

Fetcher = Callable[[str], dict]


class BadAccessToken(Exception):
    """The token is not a valid access token for this project (403 bad_access_token)."""


class AuthUnavailable(Exception):
    """The cloud cannot verify this token right now: no key set and no secret (503 link_unavailable)."""


def http_fetch_jwks(url: str) -> dict:
    """GET the JWKS document. Only called when no fetcher is injected (production)."""
    import httpx

    resp = httpx.get(url, timeout=httpx.Timeout(5.0), follow_redirects=False)
    resp.raise_for_status()
    return resp.json()


class SupabaseVerifier:
    def __init__(self, supabase_url: str = DEFAULT_SUPABASE_URL, jwt_secret: str = "",
                 fetch_jwks: Fetcher | None = None, ttl: float = JWKS_TTL_S,
                 clock: Callable[[], float] = time.time) -> None:
        self.base = supabase_url.rstrip("/")
        self.issuer = f"{self.base}/auth/v1"
        self.jwks_url = f"{self.issuer}/.well-known/jwks.json"
        self.secret = jwt_secret
        self._fetch = fetch_jwks or http_fetch_jwks
        self._ttl = ttl
        self._clock = clock
        self._lock = threading.Lock()
        self._keys: list[jwt.PyJWK] | None = None  # None: never fetched successfully
        self._fetched_at = 0.0
        self._failed_at: float | None = None

    @classmethod
    def from_env(cls, fetch_jwks: Fetcher | None = None) -> "SupabaseVerifier":
        url = os.environ.get("SUPABASE_URL", "").strip() or DEFAULT_SUPABASE_URL
        return cls(url, os.environ.get("SUPABASE_JWT_SECRET", ""), fetch_jwks)

    # key set ---------------------------------------------------------------
    def _parse(self, doc: dict) -> list[jwt.PyJWK]:
        keys = []
        for jwk in (doc or {}).get("keys") or []:
            if not isinstance(jwk, dict):
                continue
            try:
                key = jwt.PyJWK(jwk)
            except (jwt.PyJWKError, jwt.InvalidKeyError, ValueError, TypeError):
                continue  # a key type we cannot use (or a malformed entry): skip it, keep the rest
            if key.algorithm_name in ASYMMETRIC:
                keys.append(key)
        return keys

    def _refresh(self) -> None:
        """Fetch the key set; on failure keep whatever we had (a stale set beats none)."""
        now = self._clock()
        if self._failed_at is not None and now - self._failed_at < RETRY_AFTER_FAIL_S:
            return
        try:
            keys = self._parse(self._fetch(self.jwks_url))
        except Exception as e:  # network, HTTP status, bad JSON: all mean "no fresh keys"
            log.warning("jwks fetch failed: %s", type(e).__name__)
            self._failed_at = now
            return
        if not keys:
            log.warning("jwks has no usable ES256/RS256 keys")
            self._failed_at = now
            return
        self._keys, self._fetched_at, self._failed_at = keys, now, None

    def _keys_for(self, kid: str | None, alg: str) -> list[jwt.PyJWK]:
        with self._lock:
            if self._keys is None or self._clock() - self._fetched_at >= self._ttl:
                self._refresh()
            match = self._match(kid, alg)
            if not match and kid and self._keys is not None and self._clock() - self._fetched_at >= REFRESH_FOR_KID_S:
                self._refresh()  # a new signing key may have been rotated in
                match = self._match(kid, alg)
            if self._keys is None:
                raise AuthUnavailable("no JWKS")
            return match

    def _match(self, kid: str | None, alg: str) -> list[jwt.PyJWK]:
        return [k for k in self._keys or [] if k.algorithm_name == alg and (kid is None or k.key_id == kid)]

    # verification ----------------------------------------------------------
    def verify(self, token: str) -> dict:
        """The token's claims when it is a valid access token for this project.

        Raises BadAccessToken (403) or AuthUnavailable (503)."""
        if not isinstance(token, str) or not token or len(token) > MAX_TOKEN_CHARS:
            raise BadAccessToken("missing")
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError:
            raise BadAccessToken("malformed") from None
        alg = header.get("alg")
        kid = header.get("kid") if isinstance(header.get("kid"), str) else None
        if alg in ASYMMETRIC:
            keys = self._keys_for(kid, alg)
            if not keys:
                raise BadAccessToken("unknown key")
        elif alg == "HS256":
            if not self.secret:
                raise AuthUnavailable("HS256 token and no SUPABASE_JWT_SECRET")
            keys = [self.secret]
        else:
            raise BadAccessToken("algorithm")  # none, HS384, PS256, ...: never accepted
        for key in keys:
            try:
                claims = jwt.decode(token, key.key if isinstance(key, jwt.PyJWK) else key, algorithms=[alg],
                                    audience=AUDIENCE, issuer=self.issuer,
                                    options={"require": ["exp", "aud", "iss", "sub"]})
            except jwt.InvalidSignatureError:
                continue  # without a kid several keys may match; try the next one
            except jwt.PyJWTError:
                raise BadAccessToken("claims") from None
            sub = claims.get("sub")
            if not isinstance(sub, str) or not sub.strip() or len(sub) > 128:
                raise BadAccessToken("sub")
            return claims
        raise BadAccessToken("signature")


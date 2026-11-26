"""Storage for miyagi-cloud: install tokens and usage counters.

This module is the only place that touches the database. The app calls the methods on
`Store` and nothing else, so moving to Postgres (Supabase) later means writing a
`PostgresStore` with the same methods and returning it from `open_store()` when
`DATABASE_URL` is set. Nothing here ever sees a raw token: callers pass the sha256 hex.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS tokens (
    token_hash  TEXT PRIMARY KEY,          -- sha256 hex of the install token; the token itself is never stored
    install_id  TEXT NOT NULL,
    app_version TEXT NOT NULL,
    platform    TEXT NOT NULL,
    created_at  REAL NOT NULL,
    disabled    INTEGER NOT NULL DEFAULT 0
);
-- Which Supabase user an install belongs to (POST /v1/link). One row per install; sign-out never unlinks,
-- and a later link from another account on the same install replaces the user.
CREATE TABLE IF NOT EXISTS links (
    token_hash  TEXT PRIMARY KEY,          -- the install (sha256 hex of its token)
    user_id     TEXT NOT NULL,             -- the Supabase auth user id (the access token's sub)
    linked_at   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS links_user ON links (user_id);
-- One row per token, UTC day, provider and model. `requests` is also the per-token daily
-- request counter that check_quota() will read.
CREATE TABLE IF NOT EXISTS usage (
    token_hash    TEXT NOT NULL,
    day           TEXT NOT NULL,
    provider      TEXT NOT NULL,
    model         TEXT NOT NULL,
    requests      INTEGER NOT NULL DEFAULT 0,
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    usd           REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (token_hash, day, provider, model)
);
CREATE INDEX IF NOT EXISTS usage_day ON usage (day);
-- The first shared lesson cache (first upload wins). No longer read: its rows move to lesson_candidates as
-- pending on startup, so nothing an install uploaded is served without review.
CREATE TABLE IF NOT EXISTS lessons (
    video_id   TEXT NOT NULL,
    schema     INTEGER NOT NULL,
    body       TEXT NOT NULL,              -- the lesson JSON as uploaded (validated as a JSON object)
    bytes      INTEGER NOT NULL,
    uploader   TEXT NOT NULL,              -- token hash of the install that built it
    created_at REAL NOT NULL,
    hits       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (video_id, schema)
);
-- New lesson builds per install per UTC month (ROADMAP 3.7 free tier). One row per video: building the same
-- video again in the same month (a retry, a refresh) does not use another build.
CREATE TABLE IF NOT EXISTS builds (
    token_hash TEXT NOT NULL,
    month      TEXT NOT NULL,              -- YYYY-MM, UTC
    video_id   TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (token_hash, month, video_id)
);
-- Requests per install, UTC day and x-miyagi-role (coach, lesson, scene, ...). A label for the usage view only: the
-- role is set by the client, so no cap reads this table.
CREATE TABLE IF NOT EXISTS role_usage (
    token_hash TEXT NOT NULL,
    day        TEXT NOT NULL,
    role       TEXT NOT NULL,
    requests   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (token_hash, day, role)
);
-- Product events (POST /v1/events): counts only, per install, UTC day and event name. No event bodies.
CREATE TABLE IF NOT EXISTS events (
    token_hash TEXT NOT NULL,
    day        TEXT NOT NULL,
    name       TEXT NOT NULL,
    count      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (token_hash, day, name)
);
CREATE INDEX IF NOT EXISTS events_day ON events (day);
-- Activation funnel (POST /v1/funnel): the earliest time per install and milestone. Names and times only; the
-- install's user, when it has one, comes from `links`.
CREATE TABLE IF NOT EXISTS funnel (
    token_hash TEXT NOT NULL,
    name       TEXT NOT NULL,
    first_at   REAL NOT NULL,              -- epoch seconds, UTC
    PRIMARY KEY (token_hash, name)
);
-- Funnel rows past retention (prune), folded into per-day totals with no install: UTC day of first_at and name.
CREATE TABLE IF NOT EXISTS funnel_daily (
    day      TEXT NOT NULL,
    name     TEXT NOT NULL,
    installs INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, name)
);
-- Shared lesson cache (ROADMAP 3.1, A08): every upload is a candidate per video, schema and uploader. GET serves only
-- the one approved candidate (POST /admin/lessons/{video_id}/approve, or LESSON_AUTO_APPROVE_N matching uploads).
CREATE TABLE IF NOT EXISTS lesson_candidates (
    video_id   TEXT NOT NULL,
    schema     INTEGER NOT NULL,
    uploader   TEXT NOT NULL,              -- token hash of the install that uploaded it ('deleted-<random>' once
                                           -- that install deleted itself: an approved lesson stays, unattributed)
    body       TEXT NOT NULL,              -- the lesson JSON (validated, UTF-8, ensure_ascii off)
    bytes      INTEGER NOT NULL,
    body_hash  TEXT NOT NULL,              -- sha256 of the normalized lesson JSON (sorted keys)
    net        TEXT NOT NULL,              -- keyed hash (Store.hash_net) of the uploader's network (IPv4 /24, IPv6 /48),
                                           -- for auto-approval and the per-network pending bound; '' once approved
    status     TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | revoked (never served, never auto-approved)
    created_at REAL NOT NULL,
    hits       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (video_id, schema, uploader)
);
CREATE INDEX IF NOT EXISTS lesson_candidates_status ON lesson_candidates (status, video_id);
-- Lesson uploads per install and UTC day (the per-token PUT limit).
CREATE TABLE IF NOT EXISTS lesson_puts (
    token_hash TEXT NOT NULL,
    day        TEXT NOT NULL,
    n          INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (token_hash, day)
);
-- Install tokens minted per client network bucket and hour (epoch hours), so a deploy does not reset the limit.
-- Rows older than two days are pruned.
CREATE TABLE IF NOT EXISTS mints (
    bucket TEXT NOT NULL,                  -- keyed hash (Store.hash_net) of the client network: never the address
    hour   INTEGER NOT NULL,               -- unix time // 3600
    n      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (bucket, hour)
);
CREATE INDEX IF NOT EXISTS mints_hour ON mints (hour);
-- Allowlisted scalar props of those events, also as counts: a string or boolean value is counted per value,
-- a number is summed (value '' holds its count and total). Every other prop is dropped before it gets here.
CREATE TABLE IF NOT EXISTS event_props (
    token_hash TEXT NOT NULL,
    day        TEXT NOT NULL,
    name       TEXT NOT NULL,
    key        TEXT NOT NULL,
    value      TEXT NOT NULL,              -- '' for a number
    count      INTEGER NOT NULL DEFAULT 0,
    total      REAL NOT NULL DEFAULT 0,    -- the sum of a number's values
    PRIMARY KEY (token_hash, day, name, key, value)
);
-- What an install had already used on a UTC day when POST /v1/link moved it away from the scope its caps were
-- summed over: a user (from_user, on a relink to another account) or the anonymous network pool (from_net, on its
-- first link). admit_call adds these rows back to that scope, so relinking cannot reset a cap: the spend stays
-- where it was made (and the new user's sum sees the install's whole day too).
CREATE TABLE IF NOT EXISTS moved_usage (
    token_hash TEXT NOT NULL,
    day        TEXT NOT NULL,
    from_user  TEXT,
    from_net   TEXT,
    requests   INTEGER NOT NULL DEFAULT 0,
    usd        REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS moved_usage_day ON moved_usage (day);
-- Events taken per install and UTC receive day: the EVENTS_PER_DAY cap reads it.
CREATE TABLE IF NOT EXISTS event_intake (
    token_hash TEXT NOT NULL,
    day        TEXT NOT NULL,
    taken      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (token_hash, day)
);
-- Operator switches changed at runtime (POST /admin/proxy/pause and /resume). Guard reads 'paused' on every /v1
-- request, so stopping traffic needs no redeploy, and the value survives restarts and deploys.
CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at REAL NOT NULL
);
-- New installs minted per UTC day (POST /v1/install and /v1/register): the NEW_INSTALLS_PER_DAY cap reads it.
CREATE TABLE IF NOT EXISTS install_days (
    day TEXT PRIMARY KEY,
    n   INTEGER NOT NULL DEFAULT 0
);
-- Alerts sent per UTC day and key (spend_50, token:<prefix>, ...), so each fires at most once a day, across restarts.
CREATE TABLE IF NOT EXISTS alerts_sent (
    day     TEXT NOT NULL,
    key     TEXT NOT NULL,
    sent_at REAL NOT NULL,
    PRIMARY KEY (day, key)
);
-- Accounts whose local data is already wiped (POST /v1/account/delete) but whose Supabase auth user could not be
-- deleted yet (no SUPABASE_SERVICE_ROLE_KEY, or Supabase failed). /admin/deletions lists and retries them; a row
-- goes away as soon as the Supabase user is gone.
CREATE TABLE IF NOT EXISTS deletion_requests (
    user_id       TEXT PRIMARY KEY,
    requested_day TEXT NOT NULL
);
-- Videos (and schema) whose approved lesson an operator revoked (POST /admin/lessons/{video_id}/revoke). Nothing for
-- them is auto-approved again, whoever uploads it; only an operator's explicit approve serves one. Kept on its own so an
-- uploader deleting their account (which deletes their non-approved candidates) cannot lift it. Holds no install.
-- Lesson builds in progress (POST /v1/lessons/{id}/build): while an install's claim is unexpired, another install
-- asking to build the same video and schema is told {"held": true} and waits for the upload instead of building it
-- too. schema 0: the claim named no schema (it then matches every schema). Released by the claimer's PUT, by any
-- stored lesson for that video and schema, by expiry (pruned) and by the claimer's account delete.
-- Region block checks (REGION_BLOCK) per UTC day, country ('unknown' when none) and outcome: counts only. No install,
-- no address, no time: the country of one request is never stored.
CREATE TABLE IF NOT EXISTS region_days (
    day     TEXT NOT NULL,
    country TEXT NOT NULL,
    blocked INTEGER NOT NULL,
    n       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, country, blocked)
);
CREATE TABLE IF NOT EXISTS lesson_claims (
    video_id   TEXT NOT NULL,
    schema     INTEGER NOT NULL,
    token_hash TEXT NOT NULL,              -- the claiming install (sha256 hex of its token)
    claimed_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    PRIMARY KEY (video_id, schema, token_hash)
);
CREATE TABLE IF NOT EXISTS lesson_revocations (
    video_id   TEXT NOT NULL,
    schema     INTEGER NOT NULL,
    revoked_at REAL NOT NULL,
    PRIMARY KEY (video_id, schema)
);
-- Durable identity (abuse): id_hash is an HMAC-SHA256 of the normalized provider email, never the email. It survives
-- account deletion, so a ban and the day's spend / month's builds cannot be reset by deleting and signing in again.
CREATE TABLE IF NOT EXISTS banned_identities (
    id_hash    TEXT PRIMARY KEY,
    reason     TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
-- Which identity a live Supabase user is (written on link, dropped with the account): lets admin ban by user id.
CREATE TABLE IF NOT EXISTS user_identity (
    user_id TEXT PRIMARY KEY,
    id_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS user_identity_hash ON user_identity (id_hash);
-- Written by delete_account: what the identity had used on that UTC day (requests, usd, tokens), counted into the
-- caps of any later account with the same id_hash until the day ends.
CREATE TABLE IF NOT EXISTS identity_usage (
    id_hash  TEXT NOT NULL,
    day      TEXT NOT NULL,
    requests INTEGER NOT NULL DEFAULT 0,
    usd      REAL NOT NULL DEFAULT 0,
    tokens   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (id_hash, day)
);
-- Same for the month's lesson builds (a count: the videos themselves are not kept).
CREATE TABLE IF NOT EXISTS identity_builds (
    id_hash TEXT NOT NULL,
    month   TEXT NOT NULL,
    builds  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (id_hash, month)
);
"""

log = logging.getLogger("miyagi.cloud")

# Per-install detail rows (usage, role_usage, events, event_props, builds) are kept this many days; older usage and
# event rows are folded into per-day totals under AGGREGATE (no install), the rest deleted. At least 35: the monthly
# build cap and the 30-day admin view read them.
MIN_RETAIN_DAYS = 35
SHORT_RETAIN_DAYS = 2  # rows only today's caps read (event_intake, moved_usage, lesson_puts, alerts_sent)
AGGREGATE = "*"  # the token_hash of folded per-day totals: no install

NET_HASH_PREFIX = "n1:"
_NET_PLAIN = ("", "legacy", "unknown")  # placeholders, not networks: never hashed


def net_key_from_env() -> tuple[bytes, str]:
    """The secret the network hashes are keyed with, and where it came from. NET_HASH_KEY when set; else derived
    from ADMIN_TOKEN (a strong secret every deploy has); else random per process (the hashes then change on every
    restart: the mint and per-network limits reset, nothing else breaks)."""
    k = os.environ.get("NET_HASH_KEY", "").strip()
    if k:
        return k.encode(), "NET_HASH_KEY"
    a = os.environ.get("ADMIN_TOKEN", "").strip()
    if a:
        return hmac.new(a.encode(), b"miyagi-cloud net hash v1", hashlib.sha256).digest(), "ADMIN_TOKEN"
    return secrets.token_bytes(32), "random"

def identity_key_from_env() -> bytes:
    """The secret identity hashes are keyed with. IDENTITY_HASH_KEY when set; else derived from ADMIN_TOKEN (so bans
    and carry-overs survive restarts on every deploy); else a fixed dev value (hashes then only match within one
    deployment with the same default, which is fine for local runs and tests)."""
    k = os.environ.get("IDENTITY_HASH_KEY", "").strip()
    if k:
        return k.encode()
    a = os.environ.get("ADMIN_TOKEN", "").strip()
    if a:
        return hmac.new(a.encode(), b"miyagi-cloud identity hash v1", hashlib.sha256).digest()
    return hashlib.sha256(b"miyagi-cloud dev identity key").digest()


def normalize_email(email) -> str | None:
    """Lowercased, trimmed email; for gmail.com / googlemail.com also without dots and any +tag in the local part
    (Google treats those as the same mailbox). None when it is not an address."""
    if not isinstance(email, str):
        return None
    e = email.strip().lower()
    local, sep, domain = e.rpartition("@")
    if not sep or not local or not domain or len(e) > 320:
        return None
    if domain in ("gmail.com", "googlemail.com"):
        local = local.split("+", 1)[0].replace(".", "")
        domain = "gmail.com"
        if not local:
            return None
    return f"{local}@{domain}"


PLANS = ("free", "pro")  # free: the caps in app.py apply; pro: no caps

PREFIX_LEN = 12  # how much of the token hash the admin views show


def lesson_hash(lesson) -> str:
    """sha256 of a lesson's normalized JSON (sorted keys, no whitespace): identical lessons hash alike."""
    norm = json.dumps(lesson, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _utc_day(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")


def _days_ago(n: int) -> str:
    return datetime.fromtimestamp(time.time() - n * 86400, timezone.utc).strftime("%Y-%m-%d")


def this_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def default_db_path() -> str:
    if os.environ.get("DB_PATH"):
        return os.environ["DB_PATH"]
    return "/var/data/miyagi.db" if os.path.isdir("/var/data") else "./miyagi.db"


class Store:
    """SQLite store. Calls are short and serialized by a lock; fine for one Render instance."""

    def __init__(self, path: str, net_key: bytes | None = None, identity_key: bytes | None = None) -> None:
        self.path = path
        self._identity_key = identity_key if identity_key is not None else identity_key_from_env()
        if net_key is None:
            net_key, source = net_key_from_env()
            if source == "random":
                log.warning("no NET_HASH_KEY or ADMIN_TOKEN: network hashes use a per-process key (mint and "
                            "per-network limits reset on restart)")
        self._net_key = net_key
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)
        cols = {r["name"] for r in self._db.execute("PRAGMA table_info(tokens)")}
        if "plan" not in cols:  # databases from before the free tier
            self._db.execute("ALTER TABLE tokens ADD COLUMN plan TEXT NOT NULL DEFAULT 'free'")
        if "mint_net" not in cols:  # the network a token was minted from (NULL for older tokens: no network cap)
            self._db.execute("ALTER TABLE tokens ADD COLUMN mint_net TEXT")
        self._db.execute("CREATE INDEX IF NOT EXISTS tokens_mint_net ON tokens (mint_net)")
        self._migrate_first_writer_lessons()
        self._minimise_stored_networks()
        self._pruned_hour = -1

    # network hashes -------------------------------------------------------------
    def hash_net(self, net: str | None) -> str | None:
        """A keyed hash (HMAC-SHA256, 96 bits) of a client network bucket. The proxy groups by it (mint limits, the
        anonymous per-network spend ceiling, the pending-lesson bound and auto-approval) and never stores the
        address or prefix itself. Idempotent: an existing hash, a placeholder ('', 'legacy', 'unknown') or None
        comes back unchanged."""
        if net is None or net in _NET_PLAIN or net.startswith(NET_HASH_PREFIX):
            return net
        return NET_HASH_PREFIX + hmac.new(self._net_key, net.encode("utf-8"), hashlib.sha256).hexdigest()[:24]

    def identity_hash(self, email) -> str | None:
        """The durable identity key for a provider email: HMAC-SHA256 (hex) of the normalized address; None when the
        token carried no usable email. The email itself is never stored."""
        e = normalize_email(email)
        if e is None:
            return None
        return hmac.new(self._identity_key, e.encode("utf-8"), hashlib.sha256).hexdigest()

    def is_banned(self, id_hash: str | None) -> bool:
        return bool(id_hash) and bool(self._q("SELECT 1 FROM banned_identities WHERE id_hash = ?", (id_hash,)))

    def user_banned(self, user_id: str) -> bool:
        """The live user's identity is banned."""
        return bool(self._q("SELECT 1 FROM user_identity u JOIN banned_identities b ON b.id_hash = u.id_hash "
                            "WHERE u.user_id = ?", (user_id,)))

    def identity_of(self, user_id: str) -> str | None:
        rows = self._q("SELECT id_hash FROM user_identity WHERE user_id = ?", (user_id,))
        return rows[0]["id_hash"] if rows else None

    def ban_identity(self, id_hash: str, reason: str = "") -> int:
        """Ban the identity and disable every install token linked to a user with it. Returns how many tokens."""
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._db.execute("INSERT INTO banned_identities (id_hash, reason, created_at) VALUES (?, ?, ?) "
                                 "ON CONFLICT (id_hash) DO UPDATE SET reason = excluded.reason",
                                 (id_hash, reason[:200], time.time()))
                n = self._db.execute("UPDATE tokens SET disabled = 1 WHERE token_hash IN (SELECT token_hash FROM links "
                                     "WHERE user_id IN (SELECT user_id FROM user_identity WHERE id_hash = ?))",
                                     (id_hash,)).rowcount
                self._db.execute("COMMIT")
                return n
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

    def unban_identity(self, id_hash: str) -> bool:
        with self._lock:
            return self._db.execute("DELETE FROM banned_identities WHERE id_hash = ?", (id_hash,)).rowcount > 0

    def banned_identities(self) -> list[dict]:
        return [{"id": r["id_hash"][:PREFIX_LEN], "reason": r["reason"], "created_at": r["created_at"]}
                for r in self._q("SELECT id_hash, reason, created_at FROM banned_identities ORDER BY created_at")]

    def _minimise_stored_networks(self) -> None:
        """Databases from before the hashes: every stored address or prefix becomes its keyed hash (so the limits
        keep grouping the same networks), approved lessons drop theirs, linked installs drop their mint network
        (only anonymous installs are capped by it), and the client-chosen install_id becomes the token prefix."""
        self._db.create_function("net_hash", 1, self.hash_net, deterministic=True)
        raw = f"NOT LIKE '{NET_HASH_PREFIX}%'"
        self._db.execute(f"UPDATE tokens SET mint_net = net_hash(mint_net) WHERE mint_net IS NOT NULL AND mint_net {raw}")
        self._db.execute("UPDATE tokens SET mint_net = NULL WHERE mint_net IS NOT NULL "
                         "AND token_hash IN (SELECT token_hash FROM links)")
        self._db.execute(f"UPDATE mints SET bucket = net_hash(bucket) WHERE bucket {raw}")
        self._db.execute(f"UPDATE moved_usage SET from_net = net_hash(from_net) WHERE from_net IS NOT NULL AND from_net {raw}")
        self._db.execute(f"UPDATE lesson_candidates SET net = net_hash(net) WHERE status = 'pending' AND net {raw}")
        self._db.execute("UPDATE lesson_candidates SET net = '' WHERE status = 'approved' AND net != ''")
        self._db.execute(f"UPDATE tokens SET install_id = substr(token_hash, 1, {PREFIX_LEN}) "
                         f"WHERE install_id != substr(token_hash, 1, {PREFIX_LEN})")

    def _migrate_first_writer_lessons(self) -> None:
        """Lessons cached by the first-upload-wins version become pending candidates: nobody reviewed them."""
        rows = self._db.execute("SELECT video_id, schema, body, bytes, uploader, created_at FROM lessons").fetchall()
        for r in rows:
            try:
                h = lesson_hash(json.loads(r["body"]))
            except ValueError:
                h = hashlib.sha256(r["body"].encode()).hexdigest()
            self._db.execute("INSERT OR IGNORE INTO lesson_candidates (video_id, schema, uploader, body, bytes, body_hash, net, "
                             "status, created_at) VALUES (?, ?, ?, ?, ?, ?, 'legacy', 'pending', ?)",
                             (r["video_id"], r["schema"], r["uploader"], r["body"], r["bytes"], h, r["created_at"]))
        if rows:
            self._db.execute("DELETE FROM lessons")

    def _q(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(sql, args).fetchall()

    # tokens ---------------------------------------------------------------
    def add_token(self, token_hash: str, install_id: str, app_version: str, platform: str, mint_net: str | None = None) -> None:
        """mint_net: the client network it was minted from (IPv4 address or IPv6 /48), for the anonymous per-network cap;
        stored as its keyed hash only. install_id is not kept: the column holds the token prefix (a client-chosen id
        would be one more identifier with no use here)."""
        del install_id
        self._q("INSERT INTO tokens (token_hash, install_id, app_version, platform, created_at, mint_net) VALUES (?, ?, ?, ?, ?, ?)",
                (token_hash, token_hash[:PREFIX_LEN], app_version, platform, time.time(), self.hash_net(mint_net)))

    def get_token(self, token_hash: str) -> dict | None:
        rows = self._q("SELECT token_hash, disabled, plan, mint_net FROM tokens WHERE token_hash = ?", (token_hash,))
        return dict(rows[0]) if rows else None

    def set_disabled(self, prefix: str, disabled: bool) -> list[str]:
        """Disable/enable the tokens whose hash starts with `prefix`; returns the matched hashes."""
        rows = self._q("SELECT token_hash FROM tokens WHERE substr(token_hash, 1, ?) = ?", (len(prefix), prefix))
        hashes = [r["token_hash"] for r in rows]
        if len(hashes) == 1:
            self._q("UPDATE tokens SET disabled = ? WHERE token_hash = ?", (int(disabled), hashes[0]))
        return hashes

    def set_plan(self, prefix: str, plan: str) -> list[str]:
        """Set the plan of the token whose hash starts with `prefix` (when exactly one matches); returns the matches."""
        rows = self._q("SELECT token_hash FROM tokens WHERE substr(token_hash, 1, ?) = ?", (len(prefix), prefix))
        hashes = [r["token_hash"] for r in rows]
        if len(hashes) == 1:
            self._q("UPDATE tokens SET plan = ? WHERE token_hash = ?", (plan, hashes[0]))
        return hashes

    # lesson cache ----------------------------------------------------------
    def get_lesson(self, video_id: str, schema: int) -> dict | None:
        """The approved lesson ({body, created_at}) for this video and schema, counting a hit; None when there is none.
        Pending candidates are never served."""
        with self._lock:
            row = self._db.execute("SELECT uploader, body, created_at FROM lesson_candidates WHERE video_id = ? AND schema = ? "
                                   "AND status = 'approved' ORDER BY created_at LIMIT 1", (video_id, schema)).fetchone()
            if row is None:
                return None
            self._db.execute("UPDATE lesson_candidates SET hits = hits + 1 WHERE video_id = ? AND schema = ? AND uploader = ?",
                             (video_id, schema, row["uploader"]))
            return {"body": row["body"], "created_at": row["created_at"]}

    def put_candidate(self, video_id: str, schema: int, uploader: str, body: str, body_hash: str, net: str, *,
                      max_pending_bytes: int = 0, max_net_bytes: int = 0, max_age_s: float = 0) -> str | None:
        """Store (or replace) this uploader's candidate for the video and schema, as pending. Another uploader's
        candidate is never touched, so nobody can block or overwrite someone else's upload.

        In the same transaction: pending candidates older than max_age_s are dropped first, then the upload is
        refused when it would take the pending bytes past max_pending_bytes in total or past max_net_bytes for its
        uploader network (0 = no bound; the uploader's own candidate it replaces does not count). Returns None when
        stored, else the bound hit: "pending_total" | "pending_net"."""
        size, now = len(body.encode("utf-8")), time.time()
        net = self.hash_net(net)
        mine = "NOT (video_id = ? AND schema = ? AND uploader = ?)"
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                if max_age_s > 0:
                    self._db.execute("DELETE FROM lesson_candidates WHERE status = 'pending' AND created_at < ?", (now - max_age_s,))
                if max_pending_bytes > 0:
                    total = self._db.execute(f"SELECT COALESCE(SUM(bytes), 0) FROM lesson_candidates WHERE status = 'pending' "
                                             f"AND {mine}", (video_id, schema, uploader)).fetchone()[0]
                    if total + size > max_pending_bytes:
                        self._db.execute("COMMIT")  # keep the prune
                        return "pending_total"
                if max_net_bytes > 0:
                    used = self._db.execute(f"SELECT COALESCE(SUM(bytes), 0) FROM lesson_candidates WHERE status = 'pending' "
                                            f"AND net = ? AND {mine}", (net, video_id, schema, uploader)).fetchone()[0]
                    if used + size > max_net_bytes:
                        self._db.execute("COMMIT")
                        return "pending_net"
                self._db.execute("INSERT INTO lesson_candidates (video_id, schema, uploader, body, bytes, body_hash, net, status, "
                                 "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?) ON CONFLICT (video_id, schema, uploader) "
                                 "DO UPDATE SET body = excluded.body, bytes = excluded.bytes, body_hash = excluded.body_hash, "
                                 "net = excluded.net, created_at = excluded.created_at, "
                                 "status = CASE WHEN lesson_candidates.status = 'revoked' THEN 'revoked' ELSE 'pending' END",
                                 (video_id, schema, uploader, body, size, body_hash, net, now))
                self._db.execute("COMMIT")
                return None
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

    def lesson_candidates(self, video_id: str, hash_prefix: str, schema: int | None = None) -> list[dict]:
        """Every candidate of `video_id` whose body hash starts with `hash_prefix` (and schema, when given), with its
        full body: what an operator reads before approving it."""
        sql = (f"SELECT video_id, schema, body_hash AS hash, substr(uploader, 1, {PREFIX_LEN}) AS uploader, status, bytes, "
               "created_at, hits, body FROM lesson_candidates WHERE video_id = ? AND substr(body_hash, 1, ?) = ?")
        args: tuple = (video_id, len(hash_prefix), hash_prefix)
        if schema is not None:
            sql, args = sql + " AND schema = ?", (*args, schema)
        return [dict(r) for r in self._q(sql + " ORDER BY created_at LIMIT 50", args)]

    def _approve_row(self, video_id: str, schema: int, uploader: str) -> None:
        self._db.execute("UPDATE lesson_candidates SET status = 'pending' WHERE video_id = ? AND schema = ? AND status = 'approved'",
                         (video_id, schema))
        self._db.execute("UPDATE lesson_candidates SET status = 'approved', net = '' WHERE video_id = ? AND schema = ? "
                         "AND uploader = ?", (video_id, schema, uploader))

    def approve_lesson(self, video_id: str, hash_prefix: str, schema: int | None = None) -> list[dict]:
        """Approve the candidate of `video_id` whose body hash starts with `hash_prefix` (and schema, when given).
        Approves only when exactly one (schema, body hash) matches; returns the matching groups either way."""
        with self._lock:
            sql = ("SELECT schema, body_hash, MIN(created_at) AS first FROM lesson_candidates WHERE video_id = ? "
                   "AND substr(body_hash, 1, ?) = ?")
            args: list = [video_id, len(hash_prefix), hash_prefix]
            if schema is not None:
                sql, args = sql + " AND schema = ?", [*args, schema]
            groups = [dict(r) for r in self._db.execute(sql + " GROUP BY schema, body_hash", args).fetchall()]
            if len(groups) == 1:
                g = groups[0]
                row = self._db.execute("SELECT uploader FROM lesson_candidates WHERE video_id = ? AND schema = ? AND body_hash = ? "
                                       "ORDER BY created_at LIMIT 1", (video_id, g["schema"], g["body_hash"])).fetchone()
                self._approve_row(video_id, g["schema"], row["uploader"])
            return groups

    def auto_approve(self, video_id: str, schema: int, body_hash: str, n: int) -> bool:
        """With n > 0 and nothing approved yet: approve when n uploaders on n different networks sent this same lesson."""
        if n <= 0:
            return False
        with self._lock:
            if self._db.execute("SELECT 1 FROM lesson_candidates WHERE video_id = ? AND schema = ? AND status = 'approved'",
                                (video_id, schema)).fetchone():
                return False
            row = self._db.execute("SELECT COUNT(DISTINCT uploader) AS u, COUNT(DISTINCT net) AS nets FROM lesson_candidates "
                                   "WHERE video_id = ? AND schema = ? AND body_hash = ? AND net NOT IN ('', 'legacy', 'unknown')",
                                   (video_id, schema, body_hash)).fetchone()
            if row["u"] < n or row["nets"] < n:
                return False
            first = self._db.execute("SELECT uploader FROM lesson_candidates WHERE video_id = ? AND schema = ? AND body_hash = ? "
                                     "ORDER BY created_at LIMIT 1", (video_id, schema, body_hash)).fetchone()
            self._approve_row(video_id, schema, first["uploader"])
            return True

    def auto_approve_validated(self, video_id: str, schema: int, uploader: str) -> bool:
        """Approve this uploader's candidate (it passed lesson_safety.review) unless the video and schema already serve
        an approved lesson, were revoked by an operator, or this candidate itself is revoked. True when approved."""
        with self._lock:
            if self._db.execute("SELECT 1 FROM lesson_revocations WHERE video_id = ? AND schema = ?", (video_id, schema)).fetchone():
                return False
            if self._db.execute("SELECT 1 FROM lesson_candidates WHERE video_id = ? AND schema = ? AND status = 'approved'",
                                (video_id, schema)).fetchone():
                return False
            row = self._db.execute("SELECT status FROM lesson_candidates WHERE video_id = ? AND schema = ? AND uploader = ?",
                                   (video_id, schema, uploader)).fetchone()
            if row is None or row["status"] != "pending":
                return False
            self._approve_row(video_id, schema, uploader)
            return True

    def revoke_lesson(self, video_id: str, schema: int | None = None) -> list[int]:
        """Stop serving the approved lesson of `video_id` (one schema, or every schema that has one; with a schema and
        nothing approved, the revocation is still recorded) and stop auto-approval for it. Returns the schemas revoked."""
        with self._lock:
            if schema is None:
                schemas = [r[0] for r in self._db.execute("SELECT DISTINCT schema FROM lesson_candidates WHERE video_id = ? "
                                                         "AND status = 'approved'", (video_id,)).fetchall()]
            else:
                schemas = [schema]
            for sc in schemas:
                self._db.execute("UPDATE lesson_candidates SET status = 'revoked' WHERE video_id = ? AND schema = ? "
                                 "AND status = 'approved'", (video_id, sc))
                self._db.execute("INSERT INTO lesson_revocations (video_id, schema, revoked_at) VALUES (?, ?, ?) "
                                 "ON CONFLICT (video_id, schema) DO UPDATE SET revoked_at = excluded.revoked_at",
                                 (video_id, sc, time.time()))
            return schemas

    def revoked(self, video_id: str, schema: int) -> bool:
        return bool(self._q("SELECT 1 FROM lesson_revocations WHERE video_id = ? AND schema = ?", (video_id, schema)))

    def pending_lessons(self, limit: int = 200) -> list[dict]:
        """Pending candidates, newest first, with their body (the admin view shows what it installs and runs)."""
        rows = self._q(f"SELECT video_id, schema, substr(body_hash, 1, 16) AS hash, substr(uploader, 1, {PREFIX_LEN}) AS uploader, "
                       "bytes, created_at, body FROM lesson_candidates WHERE status = 'pending' ORDER BY created_at DESC LIMIT ?",
                       (limit,))
        return [dict(r) for r in rows]

    def delete_lessons(self, video_id: str) -> int:
        """Drop every candidate (approved or not, every schema) of one video."""
        with self._lock:
            return self._db.execute("DELETE FROM lesson_candidates WHERE video_id = ?", (video_id,)).rowcount

    def delete_lessons_by_uploader(self, prefix: str) -> int:
        """Drop every candidate uploaded by the install(s) whose token hash starts with `prefix`."""
        with self._lock:
            return self._db.execute("DELETE FROM lesson_candidates WHERE substr(uploader, 1, ?) = ?", (len(prefix), prefix)).rowcount

    def claim_lesson_put(self, token_hash: str, cap: int) -> tuple[bool, int]:
        """Count one lesson upload for this install today unless `cap` (> 0) is reached. Returns (allowed, used)."""
        day = today()
        with self._lock:
            row = self._db.execute("SELECT n FROM lesson_puts WHERE token_hash = ? AND day = ?", (token_hash, day)).fetchone()
            used = int(row[0]) if row else 0
            if cap > 0 and used >= cap:
                return False, used
            self._db.execute("INSERT INTO lesson_puts (token_hash, day, n) VALUES (?, ?, 1) "
                             "ON CONFLICT (token_hash, day) DO UPDATE SET n = n + 1", (token_hash, day))
            self._db.execute("DELETE FROM lesson_puts WHERE day < ?", (_days_ago(SHORT_RETAIN_DAYS),))
            return True, used + 1

    # install token minting (POST /v1/install, /v1/register) --------------
    def mint_check(self, bucket: str, per_hour: int, per_day: int, global_max: int, now: float | None = None,
                   new_per_day: int = 0) -> dict:
        """Count one mint for `bucket` unless a limit is reached, in one transaction. 0 turns a limit off.

        new_per_day: every bucket together in the current UTC day (the daily new-install cap, D13), checked first.
        per_hour: this bucket in the current clock hour. per_day: this bucket over the last 24 clock hours.
        global_max: every bucket together in the current clock hour.
        Returns {"hit": None | "new_installs" | "hour" | "day" | "global", "used", "cap", "retry_s",
        "global": mints this hour}."""
        t = time.time() if now is None else now
        bucket = self.hash_net(bucket)
        hour = int(t // 3600)
        to_next_hour = (hour + 1) * 3600 - t
        day = _utc_day(t)
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                if self._pruned_hour != hour:
                    self._db.execute("DELETE FROM mints WHERE hour < ?", (hour - 48,))
                    self._pruned_hour = hour
                g = int(self._db.execute("SELECT COALESCE(SUM(n), 0) FROM mints WHERE hour = ?", (hour,)).fetchone()[0])
                hit = None
                if new_per_day > 0:
                    row = self._db.execute("SELECT n FROM install_days WHERE day = ?", (day,)).fetchone()
                    used = int(row[0]) if row else 0
                    if used >= new_per_day:
                        hit = {"hit": "new_installs", "used": used, "cap": new_per_day, "retry_s": (t // 86400 + 1) * 86400 - t}
                if hit is None and global_max > 0 and g >= global_max:
                    hit = {"hit": "global", "used": g, "cap": global_max, "retry_s": to_next_hour}
                if hit is None and per_hour > 0:
                    row = self._db.execute("SELECT n FROM mints WHERE bucket = ? AND hour = ?", (bucket, hour)).fetchone()
                    used = int(row[0]) if row else 0
                    if used >= per_hour:
                        hit = {"hit": "hour", "used": used, "cap": per_hour, "retry_s": to_next_hour}
                if hit is None and per_day > 0:
                    rows = self._db.execute("SELECT hour, n FROM mints WHERE bucket = ? AND hour > ? ORDER BY hour",
                                            (bucket, hour - 24)).fetchall()
                    used = sum(int(r["n"]) for r in rows)
                    if used >= per_day:
                        hit = {"hit": "day", "used": used, "cap": per_day, "retry_s": (int(rows[0]["hour"]) + 24) * 3600 - t}
                if hit is not None:
                    self._db.execute("ROLLBACK")
                    return {**hit, "global": g}
                self._db.execute("INSERT INTO mints (bucket, hour, n) VALUES (?, ?, 1) "
                                 "ON CONFLICT (bucket, hour) DO UPDATE SET n = n + 1", (bucket, hour))
                self._db.execute("INSERT INTO install_days (day, n) VALUES (?, 1) "
                                 "ON CONFLICT (day) DO UPDATE SET n = n + 1", (day,))
                self._db.execute("COMMIT")
                return {"hit": None, "used": 0, "cap": 0, "retry_s": 0, "global": g + 1}
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

    # lesson build quota ----------------------------------------------------
    def builds_in_month(self, token_hash: str, month: str | None = None, user_id: str | None = None) -> int:
        """Distinct videos claimed this month by this install, or with `user_id` by every install linked to that user."""
        scope, arg = self._build_scope(token_hash, user_id)
        m = month or this_month()
        with self._lock:
            n = self._db.execute(f"SELECT COUNT(DISTINCT video_id) FROM builds WHERE month = ? AND {scope}", (m, arg)).fetchone()[0]
            return int(n) + self._build_carry(user_id, m)

    def _build_carry(self, user_id: str | None, month: str) -> int:
        """Builds this identity used this month before an account deletion (identity_builds). Lock held."""
        if not user_id:
            return 0
        r = self._db.execute("SELECT COALESCE(SUM(b.builds), 0) FROM identity_builds b JOIN user_identity u "
                             "ON u.id_hash = b.id_hash WHERE u.user_id = ? AND b.month = ?", (user_id, month)).fetchone()
        return int(r[0])

    @staticmethod
    def _build_scope(token_hash: str, user_id: str | None) -> tuple[str, str]:
        if user_id:
            return "token_hash IN (SELECT token_hash FROM links WHERE user_id = ?)", user_id
        return "token_hash = ?", token_hash

    def has_build(self, token_hash: str, video_id: str) -> bool:
        """This install claimed a build of this video (any month)."""
        return bool(self._q("SELECT 1 FROM builds WHERE token_hash = ? AND video_id = ? LIMIT 1", (token_hash, video_id)))

    def claim_lesson_build(self, token_hash: str, video_id: str, schema: int, cap: int, user_id: str | None = None,
                           ttl_s: float = 0, now: float | None = None) -> tuple[str, int]:
        """POST /v1/lessons/{id}/build in one step under the lock. ("held", 0) when another install holds an unexpired
        claim for this video and schema (schema 0 on either side matches any): nothing is counted. Else the build
        quota (claim_build): ("capped", used) or ("ok", used); "ok" also records this install's claim for ttl_s
        seconds (0 = no claims). The claimer's own repeat claim is "ok" again and does not extend its claim."""
        t = time.time() if now is None else now
        with self._lock:
            if ttl_s > 0 and self._db.execute(
                    "SELECT 1 FROM lesson_claims WHERE video_id = ? AND (schema = ? OR schema = 0 OR ? = 0) "
                    "AND token_hash != ? AND expires_at > ? LIMIT 1", (video_id, schema, schema, token_hash, t)).fetchone():
                return "held", 0
            ok, used = self._claim_build_locked(token_hash, video_id, cap, user_id)
            if not ok:
                return "capped", used
            if ttl_s > 0 and not self._db.execute("SELECT 1 FROM lesson_claims WHERE video_id = ? AND schema = ? "
                                                  "AND token_hash = ? AND expires_at > ?",
                                                  (video_id, schema, token_hash, t)).fetchone():
                self._db.execute("INSERT INTO lesson_claims (video_id, schema, token_hash, claimed_at, expires_at) "
                                 "VALUES (?, ?, ?, ?, ?) ON CONFLICT (video_id, schema, token_hash) DO UPDATE SET "
                                 "claimed_at = excluded.claimed_at, expires_at = excluded.expires_at",
                                 (video_id, schema, token_hash, t, t + ttl_s))
            return "ok", used

    def release_lesson_claims(self, video_id: str, schema: int, token_hash: str | None = None) -> int:
        """Drop the claims on this video and schema (and the ones that named no schema): this install's only, or with
        token_hash None everyone's (a lesson was stored). Returns how many."""
        sql, args = "DELETE FROM lesson_claims WHERE video_id = ? AND (schema = ? OR schema = 0)", [video_id, schema]
        if token_hash is not None:
            sql, args = sql + " AND token_hash = ?", [*args, token_hash]
        with self._lock:
            return self._db.execute(sql, args).rowcount

    def lesson_claims_of(self, token_hash: str) -> list[dict]:
        return [dict(r) for r in self._q("SELECT video_id, schema, expires_at FROM lesson_claims WHERE token_hash = ?",
                                         (token_hash,))]

    def claim_build(self, token_hash: str, video_id: str, cap: int, user_id: str | None = None) -> tuple[bool, int]:
        """Use one of this month's builds for `video_id`, atomically. cap <= 0 means no cap. Returns (allowed, builds
        used this month after the call). Counted per install, or with `user_id` per user: distinct videos claimed by
        every install linked to that user, so linking more Macs does not multiply the cap. A video already claimed this
        month in that scope is free (another of the user's installs gets its own row, which PUT needs)."""
        with self._lock:
            return self._claim_build_locked(token_hash, video_id, cap, user_id)

    def _claim_build_locked(self, token_hash: str, video_id: str, cap: int, user_id: str | None) -> tuple[bool, int]:
        month = this_month()
        scope, arg = self._build_scope(token_hash, user_id)
        n = self._db.execute(f"SELECT COUNT(DISTINCT video_id) FROM builds WHERE month = ? AND {scope}", (month, arg)).fetchone()[0]
        n += self._build_carry(user_id, month)
        if self._db.execute("SELECT 1 FROM builds WHERE token_hash = ? AND month = ? AND video_id = ?",
                            (token_hash, month, video_id)).fetchone():
            return True, n
        claimed = self._db.execute(f"SELECT 1 FROM builds WHERE month = ? AND video_id = ? AND {scope}",
                                   (month, video_id, arg)).fetchone()
        if not claimed and cap > 0 and n >= cap:
            return False, n
        self._db.execute("INSERT INTO builds (token_hash, month, video_id, created_at) VALUES (?, ?, ?, ?)",
                         (token_hash, month, video_id, time.time()))
        return True, n if claimed else n + 1

    # per-role daily requests ------------------------------------------------
    def count_role(self, token_hash: str, role: str) -> None:
        self._q("INSERT INTO role_usage (token_hash, day, role, requests) VALUES (?, ?, ?, 1) "
                "ON CONFLICT (token_hash, day, role) DO UPDATE SET requests = requests + 1", (token_hash, today(), role))

    def role_requests_today(self, token_hash: str, role: str) -> int:
        rows = self._q("SELECT requests FROM role_usage WHERE token_hash = ? AND day = ? AND role = ?", (token_hash, today(), role))
        return int(rows[0]["requests"]) if rows else 0

    # admission: caps checked and counted in one step -------------------------
    def admit_call(self, token_hash: str, provider: str, model: str, role: str | None, daily_cap: int = 0, *,
                   usd_cap: float = 0.0, user_id: str | None = None, global_usd_cap: float = 0.0, reserve_usd: float = 0.0,
                   net: str | None = None, net_usd_cap: float = 0.0, token_cap: int = 0,
                   dry_run: bool = False) -> tuple[str | None, float, float]:
        """Count one forwarded AI call unless a cap is reached, and reserve its estimated cost. Check, count and
        reserve happen under one lock and one transaction, so parallel calls cannot all slip in under a cap.

        Every cap keys on the install token or the linked user (or the anonymous installs of one mint network), counted
        here from the usage table. `role` (the client's x-miyagi-role) is only a label: counted in role_usage for the
        usage view, never read by a cap, so a client cannot lift or move a cap by changing it.

        global_usd_cap: every install together per UTC day, reservations included (0 = none: the abuse brake).
        daily_cap / usd_cap: calls / estimated USD per UTC day (0 = none), for this install, or with `user_id` for
        every install linked to that user together.
        token_cap: settled tokens (input, cache included, plus output) per UTC day on the same scope (0 = none). Tokens
        are written when a call settles, not reserved, so parallel calls can pass it by the calls in flight.
        net / net_usd_cap: estimated USD per UTC day of every unlinked install minted from network `net` together
        (0 or no net = none); the caller passes them for anonymous installs only.
        reserve_usd is added to this call's usage row now; settle() swaps it for the real cost when the call ends.
        dry_run: check only, count nothing.
        Returns (None, 0, 0) when admitted, else (the cap hit: "global_usd" | "daily" | "usd" | "tokens" | "net_usd",
        used, cap)
        with nothing counted."""
        day = today()
        net = self.hash_net(net)
        reserve_usd = max(float(reserve_usd), 0.0)
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                if global_usd_cap > 0:
                    spent = float(self._db.execute("SELECT COALESCE(SUM(usd), 0) FROM usage WHERE day = ?", (day,)).fetchone()[0])
                    if spent >= global_usd_cap or spent + reserve_usd > global_usd_cap:
                        self._db.execute("ROLLBACK")
                        return "global_usd", spent, global_usd_cap
                if daily_cap > 0 or usd_cap > 0 or token_cap > 0:
                    reqs, usd, toks = self._scope_usage(day, token_hash, user_id)
                    if daily_cap > 0 and int(reqs) >= daily_cap:
                        self._db.execute("ROLLBACK")
                        return "daily", int(reqs), daily_cap
                    if usd_cap > 0 and (float(usd) >= usd_cap or float(usd) + reserve_usd > usd_cap):
                        self._db.execute("ROLLBACK")
                        return "usd", float(usd), usd_cap
                    if token_cap > 0 and int(toks) >= token_cap:
                        self._db.execute("ROLLBACK")
                        return "tokens", int(toks), token_cap
                if net and net_usd_cap > 0:
                    net_usd = float(self._db.execute(
                        "SELECT COALESCE(SUM(u.usd), 0) FROM usage u JOIN tokens t ON t.token_hash = u.token_hash "
                        "WHERE u.day = ? AND t.mint_net = ? AND u.token_hash NOT IN (SELECT token_hash FROM links)",
                        (day, net)).fetchone()[0])
                    net_usd += float(self._db.execute("SELECT COALESCE(SUM(usd), 0) FROM moved_usage WHERE day = ? AND from_net = ?",
                                                      (day, net)).fetchone()[0])
                    if net_usd >= net_usd_cap or net_usd + reserve_usd > net_usd_cap:
                        self._db.execute("ROLLBACK")
                        return "net_usd", net_usd, net_usd_cap
                if dry_run:
                    self._db.execute("ROLLBACK")
                    return None, 0, 0
                self._db.execute("INSERT INTO usage (token_hash, day, provider, model, requests, usd) VALUES (?, ?, ?, ?, 1, ?) "
                                 "ON CONFLICT (token_hash, day, provider, model) DO UPDATE SET requests = requests + 1, "
                                 "usd = usd + excluded.usd", (token_hash, day, provider, model, reserve_usd))
                if role:
                    self._db.execute("INSERT INTO role_usage (token_hash, day, role, requests) VALUES (?, ?, ?, 1) "
                                     "ON CONFLICT (token_hash, day, role) DO UPDATE SET requests = requests + 1",
                                     (token_hash, day, role))
                self._db.execute("COMMIT")
                return None, 0, 0
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

    def _scope_usage(self, day: str, token_hash: str | None, user_id: str | None) -> tuple[int, float, int]:
        """(requests, usd, tokens) on `day` for one install, or with `user_id` for every install linked to that user plus
        what installs relinked away from the user had used that day (moved_usage: requests and usd). What admit_call's
        caps read; call with the lock held."""
        if user_id:
            scope, arg = "token_hash IN (SELECT token_hash FROM links WHERE user_id = ?)", user_id
        else:
            scope, arg = "token_hash = ?", token_hash
        reqs, usd, toks = self._db.execute(
            f"SELECT COALESCE(SUM(requests), 0), COALESCE(SUM(usd), 0), "
            f"COALESCE(SUM(input_tokens + output_tokens), 0) FROM usage WHERE day = ? AND {scope}", (day, arg)).fetchone()
        reqs, usd, toks = int(reqs), float(usd), int(toks)
        if user_id:
            mr, mu = self._db.execute("SELECT COALESCE(SUM(requests), 0), COALESCE(SUM(usd), 0) FROM moved_usage "
                                      "WHERE day = ? AND from_user = ?", (day, user_id)).fetchone()
            reqs, usd = reqs + int(mr), usd + float(mu)
            cr, cu, ct = self._db.execute(
                "SELECT COALESCE(SUM(i.requests), 0), COALESCE(SUM(i.usd), 0), COALESCE(SUM(i.tokens), 0) FROM identity_usage i "
                "JOIN user_identity u ON u.id_hash = i.id_hash WHERE u.user_id = ? AND i.day = ?", (user_id, day)).fetchone()
            reqs, usd, toks = reqs + int(cr), usd + float(cu), toks + int(ct)
        return reqs, usd, toks

    def user_usage_today(self, user_id: str) -> tuple[int, float, int]:
        """(requests, estimated usd, tokens) so far this UTC day for every install linked to `user_id`: exactly what
        LINKED_DAILY_REQUESTS / _USD / _TOKENS are checked against (reservations of calls in flight included)."""
        with self._lock:
            return self._scope_usage(today(), None, user_id)

    def add_region_counts(self, rows: dict[tuple[str, str, int], int]) -> None:
        """Add {(day, country, blocked): n} to region_days."""
        with self._lock:
            self._db.executemany("INSERT INTO region_days (day, country, blocked, n) VALUES (?, ?, ?, ?) "
                                 "ON CONFLICT (day, country, blocked) DO UPDATE SET n = n + excluded.n",
                                 [(d, c, b, n) for (d, c, b), n in rows.items()])

    def region_report(self, days: int = 7) -> list[dict]:
        since = _days_ago(max(days - 1, 0))
        return [dict(r) for r in self._q("SELECT day, country, SUM(CASE WHEN blocked = 0 THEN n ELSE 0 END) AS allowed, "
                                         "SUM(CASE WHEN blocked = 1 THEN n ELSE 0 END) AS blocked FROM region_days "
                                         "WHERE day >= ? GROUP BY day, country ORDER BY day DESC, blocked DESC, allowed DESC",
                                         (since,))]

    def usd_today(self) -> float:
        """Estimated spend so far this UTC day, every install together, in-flight reservations included (the
        DAILY_USD_CAP brake and the spend alerts read it)."""
        return float(self._q("SELECT COALESCE(SUM(usd), 0) AS usd FROM usage WHERE day = ?", (today(),))[0]["usd"])

    # runtime switches (POST /admin/proxy/pause, /resume) -----------------------
    def get_setting(self, key: str) -> str | None:
        rows = self._q("SELECT value FROM settings WHERE key = ?", (key,))
        return rows[0]["value"] if rows else None

    def set_setting(self, key: str, value: str) -> None:
        self._q("INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) ON CONFLICT (key) DO UPDATE SET "
                "value = excluded.value, updated_at = excluded.updated_at", (key, value, time.time()))

    def paused(self) -> bool:
        """The operators' runtime pause (settings 'paused' = '1'). Read on every /v1 request."""
        return self.get_setting("paused") == "1"

    def set_paused(self, paused: bool) -> None:
        self.set_setting("paused", "1" if paused else "0")

    def ping(self) -> bool:
        """The database answers a read of its own tables (/healthz db_ok)."""
        try:
            self._q("SELECT COUNT(*) FROM settings")
            return True
        except sqlite3.Error:
            return False

    # new installs per UTC day (NEW_INSTALLS_PER_DAY) ---------------------------
    def new_installs_on(self, day: str | None = None) -> int:
        rows = self._q("SELECT n FROM install_days WHERE day = ?", (day or today(),))
        return int(rows[0]["n"]) if rows else 0

    # alerts ------------------------------------------------------------------
    def claim_alert(self, key: str, day: str | None = None) -> bool:
        """Record that alert `key` fires today. True only for the first claim of that key on that UTC day (across
        processes and restarts), so each alert is sent at most once a day. Rows older than SHORT_RETAIN_DAYS are pruned
        (only today's are read, and a token:<prefix> key names an install)."""
        d = day or today()
        with self._lock:
            n = self._db.execute("INSERT OR IGNORE INTO alerts_sent (day, key, sent_at) VALUES (?, ?, ?)",
                                 (d, key, time.time())).rowcount
            if n:
                self._db.execute("DELETE FROM alerts_sent WHERE day < ?", (_days_ago(SHORT_RETAIN_DAYS),))
            return n == 1

    def alerts_on(self, day: str | None = None) -> list[str]:
        return [r["key"] for r in self._q("SELECT key FROM alerts_sent WHERE day = ? ORDER BY sent_at", (day or today(),))]

    # usage ----------------------------------------------------------------
    def count_request(self, token_hash: str, provider: str, model: str) -> None:
        self._q("INSERT INTO usage (token_hash, day, provider, model, requests) VALUES (?, ?, ?, ?, 1) "
                "ON CONFLICT (token_hash, day, provider, model) DO UPDATE SET requests = requests + 1",
                (token_hash, today(), provider, model))

    def add_tokens(self, token_hash: str, provider: str, model: str, input_tokens: int, output_tokens: int, usd: float) -> None:
        self._q("INSERT INTO usage (token_hash, day, provider, model, input_tokens, output_tokens, usd) VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (token_hash, day, provider, model) DO UPDATE SET input_tokens = input_tokens + excluded.input_tokens, "
                "output_tokens = output_tokens + excluded.output_tokens, usd = usd + excluded.usd",
                (token_hash, today(), provider, model, input_tokens, output_tokens, usd))

    def settle(self, token_hash: str, provider: str, reserved_model: str, reserve_day: str, reserve_usd: float,
               model: str, input_tokens: int, output_tokens: int, usd: float) -> None:
        """Swap a call's reservation (admit_call reserve_usd, on its requested model's row of reserve_day) for its real
        tokens and cost (on the model that answered, today), in one transaction."""
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                if reserve_usd > 0:
                    self._db.execute("UPDATE usage SET usd = MAX(usd - ?, 0) WHERE token_hash = ? AND day = ? AND provider = ? "
                                     "AND model = ?", (reserve_usd, token_hash, reserve_day, provider, reserved_model))
                if input_tokens or output_tokens or usd:
                    self._db.execute("INSERT INTO usage (token_hash, day, provider, model, input_tokens, output_tokens, usd) "
                                     "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (token_hash, day, provider, model) DO UPDATE SET "
                                     "input_tokens = input_tokens + excluded.input_tokens, "
                                     "output_tokens = output_tokens + excluded.output_tokens, usd = usd + excluded.usd",
                                     (token_hash, today(), provider, model, input_tokens, output_tokens, usd))
                self._db.execute("COMMIT")
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

    def usd_today_for(self, token_hash: str) -> float:
        rows = self._q("SELECT COALESCE(SUM(usd), 0) AS usd FROM usage WHERE token_hash = ? AND day = ?", (token_hash, today()))
        return float(rows[0]["usd"])

    def requests_today(self, token_hash: str) -> int:
        rows = self._q("SELECT COALESCE(SUM(requests), 0) AS n FROM usage WHERE token_hash = ? AND day = ?", (token_hash, today()))
        return int(rows[0]["n"])

    # product events (POST /v1/events) --------------------------------------
    def add_events(self, token_hash: str, events: list[tuple[str, str, dict]], daily_cap: int) -> int:
        """Count `events` ([(day, name, props)], props already cut down to allowlisted scalars) for one install.
        At most `daily_cap` events per install and UTC receive day are kept (0 = no cap); the rest are dropped.
        Returns how many were counted."""
        if not events:
            return 0
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                room = len(events)
                if daily_cap > 0:
                    # the per-day cap counts what arrived today, whatever day each event says it happened
                    taken = self._db.execute("SELECT taken FROM event_intake WHERE token_hash = ? AND day = ?",
                                             (token_hash, today())).fetchone()
                    room = max(0, min(room, daily_cap - (int(taken[0]) if taken else 0)))
                if room:
                    self._db.execute("INSERT INTO event_intake (token_hash, day, taken) VALUES (?, ?, ?) "
                                     "ON CONFLICT (token_hash, day) DO UPDATE SET taken = taken + excluded.taken",
                                     (token_hash, today(), room))
                for day, name, props in events[:room]:
                    self._db.execute("INSERT INTO events (token_hash, day, name, count) VALUES (?, ?, ?, 1) "
                                     "ON CONFLICT (token_hash, day, name) DO UPDATE SET count = count + 1",
                                     (token_hash, day, name))
                    for key, value in props.items():
                        if isinstance(value, bool):
                            v, total = ("true" if value else "false"), 0.0
                        elif isinstance(value, (int, float)):
                            v, total = "", float(value)
                        else:
                            v, total = str(value), 0.0
                        self._db.execute("INSERT INTO event_props (token_hash, day, name, key, value, count, total) "
                                         "VALUES (?, ?, ?, ?, ?, 1, ?) ON CONFLICT (token_hash, day, name, key, value) "
                                         "DO UPDATE SET count = count + 1, total = total + excluded.total",
                                         (token_hash, day, name, key, v, total))
                self._db.execute("COMMIT")
                return room
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

    def event_counts(self, token_hash: str | None = None, day: str | None = None) -> dict[str, int]:
        """{event name: count} for one UTC day (default today), for one install or all of them."""
        sql, args = "SELECT name, SUM(count) AS n FROM events WHERE day = ?", [day or today()]
        if token_hash:
            sql, args = sql + " AND token_hash = ?", [*args, token_hash]
        return {r["name"]: int(r["n"]) for r in self._q(sql + " GROUP BY name", tuple(args))}

    def event_props_rows(self, token_hash: str, day: str | None = None) -> list[dict]:
        return [dict(r) for r in self._q("SELECT name, key, value, count, total FROM event_props WHERE token_hash = ? AND day = ? "
                                         "ORDER BY name, key, value", (token_hash, day or today()))]

    # funnel ---------------------------------------------------------------
    def add_funnel(self, token_hash: str, items: list[tuple[str, float]]) -> int:
        """Record milestones [(name, epoch seconds)] for one install, keeping the earliest time per name."""
        with self._lock:
            for name, at in items:
                self._db.execute("INSERT INTO funnel (token_hash, name, first_at) VALUES (?, ?, ?) "
                                 "ON CONFLICT (token_hash, name) DO UPDATE SET first_at = MIN(first_at, excluded.first_at)",
                                 (token_hash, name, float(at)))
        return len(items)

    def funnel_rows(self, token_hash: str | None = None) -> list[dict]:
        sql, args = "SELECT token_hash, name, first_at FROM funnel", ()
        if token_hash:
            sql, args = sql + " WHERE token_hash = ?", (token_hash,)
        return [dict(r) for r in self._q(sql + " ORDER BY token_hash, first_at", args)]

    def funnel_report(self, steps: list[str], since: float = 0) -> dict:
        """Per milestone, in `steps` order: installs that reached it, the share of the first step, and the median
        seconds from the step before (installs that have both). Installs counted from their first step's time."""
        by: dict[str, dict[str, float]] = {}
        for r in self._q("SELECT token_hash, name, first_at FROM funnel"):
            by.setdefault(r["token_hash"], {})[r["name"]] = float(r["first_at"])
        cohort = {h: m for h, m in by.items() if steps and steps[0] in m and m[steps[0]] >= since}
        out, base = [], len(cohort)
        for i, step in enumerate(steps):
            reached = [m for m in cohort.values() if step in m]
            gaps = sorted(m[step] - m[steps[i - 1]] for m in reached if i and steps[i - 1] in m and m[step] >= m[steps[i - 1]])
            mid = len(gaps) // 2
            median = None if not gaps else gaps[mid] if len(gaps) % 2 else (gaps[mid - 1] + gaps[mid]) / 2
            out.append({"name": step, "installs": len(reached), "share": round(len(reached) / base, 4) if base else 0.0,
                        "median_s_from_prev": None if median is None else round(median, 1)})
        older = {r["name"]: int(r["n"]) for r in self._q("SELECT name, SUM(installs) AS n FROM funnel_daily GROUP BY name")}
        return {"installs": base, "since": since, "steps": out, "pruned_totals": older,
                "installs_minted": int(self._q("SELECT COUNT(*) FROM tokens")[0][0]),
                "installs_linked": int(self._q("SELECT COUNT(*) FROM links")[0][0])}

    # links ----------------------------------------------------------------
    def link_user(self, token_hash: str, user_id: str, id_hash: str | None = None) -> None:
        """Link an install to a user. Re-linking the same pair keeps the first linked_at."""
        self.link_user_capped(token_hash, user_id, 0, id_hash)

    def _keep_usage_behind(self, token_hash: str, user_id: str) -> None:
        """Inside link_user_capped's transaction, before the link changes: when the install moves to `user_id` from
        another user, or from the anonymous pool of its mint network, record what it used today under the scope it
        leaves (moved_usage), so that scope's caps still count it."""
        cur = self._db.execute("SELECT user_id FROM links WHERE token_hash = ?", (token_hash,)).fetchone()
        old_user = cur[0] if cur else None
        if old_user == user_id:
            return
        net = None
        if old_user is None:
            row = self._db.execute("SELECT mint_net FROM tokens WHERE token_hash = ?", (token_hash,)).fetchone()
            net = row[0] if row else None
            if not net:
                return
        day = today()
        reqs, usd = self._db.execute("SELECT COALESCE(SUM(requests), 0), COALESCE(SUM(usd), 0) FROM usage "
                                     "WHERE token_hash = ? AND day = ?", (token_hash, day)).fetchone()
        if int(reqs) or float(usd):
            self._db.execute("INSERT INTO moved_usage (token_hash, day, from_user, from_net, requests, usd) "
                             "VALUES (?, ?, ?, ?, ?, ?)", (token_hash, day, old_user, net, int(reqs), float(usd)))

    def link_user_capped(self, token_hash: str, user_id: str, max_installs: int, id_hash: str | None = None) -> bool:
        """link_user, unless the user already has `max_installs` (> 0) other installs linked. Returns whether it linked.
        The install's usage today stays counted against the user or network pool it leaves (_keep_usage_behind)."""
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                if max_installs > 0:
                    others = int(self._db.execute("SELECT COUNT(*) FROM links WHERE user_id = ? AND token_hash != ?",
                                                  (user_id, token_hash)).fetchone()[0])
                    if others >= max_installs:
                        self._db.execute("ROLLBACK")
                        return False
                self._keep_usage_behind(token_hash, user_id)
                if id_hash:
                    self._db.execute("INSERT INTO user_identity (user_id, id_hash) VALUES (?, ?) "
                                     "ON CONFLICT (user_id) DO UPDATE SET id_hash = excluded.id_hash", (user_id, id_hash))
                self._db.execute("INSERT INTO links (token_hash, user_id, linked_at) VALUES (?, ?, ?) "
                                 "ON CONFLICT (token_hash) DO UPDATE SET user_id = excluded.user_id, linked_at = excluded.linked_at "
                                 "WHERE links.user_id != excluded.user_id", (token_hash, user_id, time.time()))
                # a linked install is capped per user, never by its mint network (and never unlinks): drop it
                self._db.execute("UPDATE tokens SET mint_net = NULL WHERE token_hash = ?", (token_hash,))
                self._db.execute("COMMIT")
                return True
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

    def get_link(self, token_hash: str) -> dict | None:
        rows = self._q("SELECT user_id, linked_at FROM links WHERE token_hash = ?", (token_hash,))
        return dict(rows[0]) if rows else None

    # account deletion (POST /v1/account/delete) --------------------------------
    def installs_of(self, user_id: str) -> list[str]:
        return [r["token_hash"] for r in self._q("SELECT token_hash FROM links WHERE user_id = ?", (user_id,))]

    def _carry_over(self, user_id: str | None, id_hash: str | None, hs: list[str], day: str) -> None:
        """Inside delete_account's transaction, before anything is deleted: write what the identity used today and this
        month (usage of its installs plus what moved away from the user today, and its builds) to identity_usage /
        identity_builds, added to what an earlier deletion left. Nothing is written without an identity."""
        if not user_id:
            return
        if not id_hash:
            row = self._db.execute("SELECT id_hash FROM user_identity WHERE user_id = ?", (user_id,)).fetchone()
            id_hash = row[0] if row else None
        if not id_hash:
            return
        inn = f"IN ({','.join('?' * len(hs))})" if hs else "IN (NULL)"
        r, u, t = self._db.execute(f"SELECT COALESCE(SUM(requests), 0), COALESCE(SUM(usd), 0), COALESCE(SUM(input_tokens + "
                                   f"output_tokens), 0) FROM usage WHERE day = ? AND token_hash {inn}", (day, *hs)).fetchone()
        mr, mu = self._db.execute("SELECT COALESCE(SUM(requests), 0), COALESCE(SUM(usd), 0) FROM moved_usage "
                                  "WHERE day = ? AND from_user = ?", (day, user_id)).fetchone()
        r, u = int(r) + int(mr), float(u) + float(mu)
        if r or u or int(t):
            self._db.execute("INSERT INTO identity_usage (id_hash, day, requests, usd, tokens) VALUES (?, ?, ?, ?, ?) "
                             "ON CONFLICT (id_hash, day) DO UPDATE SET requests = requests + excluded.requests, "
                             "usd = usd + excluded.usd, tokens = tokens + excluded.tokens", (id_hash, day, r, u, int(t)))
        month = this_month()
        b = self._db.execute(f"SELECT COUNT(DISTINCT video_id) FROM builds WHERE month = ? AND token_hash {inn}",
                             (month, *hs)).fetchone()[0]
        if int(b):
            self._db.execute("INSERT INTO identity_builds (id_hash, month, builds) VALUES (?, ?, ?) "
                             "ON CONFLICT (id_hash, month) DO UPDATE SET builds = builds + excluded.builds",
                             (id_hash, month, int(b)))

    def delete_account(self, token_hash: str | None, user_id: str | None = None, id_hash: str | None = None) -> dict:
        """Delete every row tied to install `token_hash` (None: none) and, with `user_id`, to that user and every install linked to
        it, in one transaction. Returns {"installs": n, <table>: rows deleted or scrubbed}.

        Kept, with nothing that points back at anyone:
        - an approved shared lesson the install uploaded: its uploader becomes 'deleted-<random>' and its network
          hash is cleared. Its body is the lesson for a public video (shared, reviewed content), not the learner's.
        - disabled install tokens stay (still disabled, detached from the user): deleting an account never lifts a
          ban. The day's usage and month's builds of the user's identity (id_hash) are carried over (identity_usage,
          identity_builds) so deleting and signing in again does not reset the caps; banned_identities is never touched.
        - today's spend of the deleted installs, folded into the per-day total row (token_hash AGGREGATE), so the
          global brake and spend alerts still see what today cost; and, for an anonymous install, today's spend
          against its mint network's hash (moved_usage, no install, pruned after SHORT_RETAIN_DAYS), so deleting and
          re-minting cannot reset ANON_DAILY_USD_PER_NETWORK. Older usage rows are deleted outright."""
        day = today()
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                hashes = {token_hash} if token_hash else set()
                if user_id:
                    hashes |= {r[0] for r in self._db.execute("SELECT token_hash FROM links WHERE user_id = ?", (user_id,))}
                hs = sorted(hashes)
                inn = f"IN ({','.join('?' * len(hs))})"
                n: dict[str, int] = {"installs": len(hs)}
                self._carry_over(user_id, id_hash, hs, day)

                anon = self._db.execute(f"SELECT t.mint_net, COALESCE(SUM(u.requests), 0), COALESCE(SUM(u.usd), 0) FROM tokens t "
                                        f"JOIN usage u ON u.token_hash = t.token_hash AND u.day = ? WHERE t.token_hash {inn} "
                                        f"AND t.mint_net IS NOT NULL AND t.token_hash NOT IN (SELECT token_hash FROM links) "
                                        f"GROUP BY t.mint_net", (day, *hs)).fetchall()
                for net, reqs, usd in anon:
                    if int(reqs) or float(usd):
                        self._db.execute("INSERT INTO moved_usage (token_hash, day, from_user, from_net, requests, usd) "
                                         "VALUES (?, ?, NULL, ?, ?, ?)", (AGGREGATE, day, net, int(reqs), float(usd)))
                self._db.execute(f"INSERT INTO usage (token_hash, day, provider, model, requests, input_tokens, output_tokens, usd) "
                                 f"SELECT ?, day, provider, model, SUM(requests), SUM(input_tokens), SUM(output_tokens), SUM(usd) "
                                 f"FROM usage WHERE day = ? AND token_hash {inn} GROUP BY day, provider, model "
                                 f"ON CONFLICT (token_hash, day, provider, model) DO UPDATE SET requests = requests + excluded.requests, "
                                 f"input_tokens = input_tokens + excluded.input_tokens, output_tokens = output_tokens + "
                                 f"excluded.output_tokens, usd = usd + excluded.usd", (AGGREGATE, day, *hs))

                for table in ("usage", "role_usage", "builds", "events", "event_props", "event_intake", "lesson_puts", "funnel",
                              "lesson_claims"):
                    n[table] = self._db.execute(f"DELETE FROM {table} WHERE token_hash {inn}", hs).rowcount
                n["moved_usage"] = self._db.execute(f"UPDATE moved_usage SET token_hash = ? WHERE token_hash {inn}",
                                                    (AGGREGATE, *hs)).rowcount  # what they moved away from OTHER scopes
                if user_id:
                    n["moved_usage"] += self._db.execute("DELETE FROM moved_usage WHERE from_user = ?", (user_id,)).rowcount
                n["lesson_candidates"] = self._db.execute(f"DELETE FROM lesson_candidates WHERE uploader {inn} "
                                                          f"AND status != 'approved'", hs).rowcount
                n["lessons_scrubbed"] = 0
                for table, extra in (("lesson_candidates", ", net = ''"), ("lessons", "")):
                    for (rowid,) in self._db.execute(f"SELECT rowid FROM {table} WHERE uploader {inn}", hs).fetchall():
                        self._db.execute(f"UPDATE {table} SET uploader = ?{extra} WHERE rowid = ?",
                                         ("deleted-" + secrets.token_hex(8), rowid))
                        n["lessons_scrubbed"] += 1
                n["alerts_sent"] = self._db.execute(f"DELETE FROM alerts_sent WHERE key {inn}",
                                                    [f"token:{h[:PREFIX_LEN]}" for h in hs]).rowcount
                link_sql, link_args = f"DELETE FROM links WHERE token_hash {inn}", list(hs)
                if user_id:
                    link_sql, link_args = link_sql + " OR user_id = ?", [*hs, user_id]
                n["links"] = self._db.execute(link_sql, link_args).rowcount
                n["tokens"] = self._db.execute(f"DELETE FROM tokens WHERE token_hash {inn} AND disabled = 0", hs).rowcount
                if user_id:
                    self._db.execute("DELETE FROM user_identity WHERE user_id = ?", (user_id,))
                self._db.execute("COMMIT")
                return n
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

    def add_deletion_request(self, user_id: str) -> None:
        self._q("INSERT OR IGNORE INTO deletion_requests (user_id, requested_day) VALUES (?, ?)", (user_id, today()))

    def deletion_requests(self) -> list[dict]:
        return [dict(r) for r in self._q("SELECT user_id, requested_day FROM deletion_requests ORDER BY requested_day, user_id")]

    def clear_deletion_request(self, user_id: str) -> None:
        self._q("DELETE FROM deletion_requests WHERE user_id = ?", (user_id,))

    # retention -------------------------------------------------------------------
    def prune(self, retain_days: int = MIN_RETAIN_DAYS, pending_max_age_s: float = 0, now: float | None = None,
              mint_net_days: float = 0) -> dict:
        """Drop what no cap, limit or view needs any more, in one transaction (run hourly and at startup):
        - usage, events, event_props older than retain_days (at least MIN_RETAIN_DAYS): folded into per-day totals
          under AGGREGATE (no install), then deleted; role_usage and builds that old: deleted;
        - event_intake, moved_usage, lesson_puts, alerts_sent older than SHORT_RETAIN_DAYS; mints older than 48 hours;
        - expired lesson build claims (lesson_claims);
        - funnel rows whose first_at is older than retain_days: counted per UTC day and name into funnel_daily
          (no install), then deleted;
        - pending lesson candidates older than pending_max_age_s (0 = keep);
        - the mint network hash of installs minted more than mint_net_days ago (0 = keep while the install is
          anonymous; linking or deleting drops it anyway). Such an install is then capped per install only.
        Returns {table: rows deleted}."""
        t = time.time() if now is None else now
        keep = max(int(retain_days), MIN_RETAIN_DAYS)
        cut = datetime.fromtimestamp(t - keep * 86400, timezone.utc).strftime("%Y-%m-%d")
        short = datetime.fromtimestamp(t - SHORT_RETAIN_DAYS * 86400, timezone.utc).strftime("%Y-%m-%d")
        n: dict[str, int] = {}
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                old = "day < ? AND token_hash != ?"
                self._db.execute(f"INSERT INTO usage (token_hash, day, provider, model, requests, input_tokens, output_tokens, usd) "
                                 f"SELECT ?, day, provider, model, SUM(requests), SUM(input_tokens), SUM(output_tokens), SUM(usd) "
                                 f"FROM usage WHERE {old} GROUP BY day, provider, model "
                                 f"ON CONFLICT (token_hash, day, provider, model) DO UPDATE SET requests = requests + excluded.requests, "
                                 f"input_tokens = input_tokens + excluded.input_tokens, output_tokens = output_tokens + "
                                 f"excluded.output_tokens, usd = usd + excluded.usd", (AGGREGATE, cut, AGGREGATE))
                self._db.execute(f"INSERT INTO events (token_hash, day, name, count) SELECT ?, day, name, SUM(count) FROM events "
                                 f"WHERE {old} GROUP BY day, name ON CONFLICT (token_hash, day, name) "
                                 f"DO UPDATE SET count = count + excluded.count", (AGGREGATE, cut, AGGREGATE))
                self._db.execute(f"INSERT INTO event_props (token_hash, day, name, key, value, count, total) "
                                 f"SELECT ?, day, name, key, value, SUM(count), SUM(total) FROM event_props WHERE {old} "
                                 f"GROUP BY day, name, key, value ON CONFLICT (token_hash, day, name, key, value) "
                                 f"DO UPDATE SET count = count + excluded.count, total = total + excluded.total",
                                 (AGGREGATE, cut, AGGREGATE))
                for table in ("usage", "events", "event_props"):
                    n[table] = self._db.execute(f"DELETE FROM {table} WHERE {old}", (cut, AGGREGATE)).rowcount
                n["role_usage"] = self._db.execute("DELETE FROM role_usage WHERE day < ?", (cut,)).rowcount
                n["builds"] = self._db.execute("DELETE FROM builds WHERE created_at < ?", (t - keep * 86400,)).rowcount
                for table in ("event_intake", "moved_usage", "lesson_puts", "alerts_sent"):
                    n[table] = self._db.execute(f"DELETE FROM {table} WHERE day < ?", (short,)).rowcount
                n["mints"] = self._db.execute("DELETE FROM mints WHERE hour < ?", (int(t // 3600) - 48,)).rowcount
                n["lesson_claims"] = self._db.execute("DELETE FROM lesson_claims WHERE expires_at <= ?", (t,)).rowcount
                n["identity_usage"] = self._db.execute("DELETE FROM identity_usage WHERE day < ?", (short,)).rowcount
                n["identity_builds"] = self._db.execute("DELETE FROM identity_builds WHERE month < ?",
                                                        (datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m"),)).rowcount
                n["region_days"] = self._db.execute("DELETE FROM region_days WHERE day < ?", (cut,)).rowcount
                # funnel: a row older than retention (by its own first_at) is counted into funnel_daily, then deleted
                self._db.execute("INSERT INTO funnel_daily (day, name, installs) SELECT strftime('%Y-%m-%d', first_at, "
                                 "'unixepoch'), name, COUNT(*) FROM funnel WHERE first_at < ? GROUP BY 1, 2 "
                                 "ON CONFLICT (day, name) DO UPDATE SET installs = installs + excluded.installs",
                                 (t - keep * 86400,))
                n["funnel"] = self._db.execute("DELETE FROM funnel WHERE first_at < ?", (t - keep * 86400,)).rowcount
                n["mint_net"] = 0
                if mint_net_days > 0:
                    n["mint_net"] = self._db.execute("UPDATE tokens SET mint_net = NULL WHERE mint_net IS NOT NULL "
                                                     "AND created_at < ?", (t - mint_net_days * 86400,)).rowcount
                n["lesson_candidates"] = 0
                if pending_max_age_s > 0:
                    n["lesson_candidates"] = self._db.execute("DELETE FROM lesson_candidates WHERE status = 'pending' "
                                                              "AND created_at < ?", (t - pending_max_age_s,)).rowcount
                self._db.execute("COMMIT")
                return n
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

    def usage_report(self, days: int = 30) -> dict:
        """Totals per token-hash prefix, per day, and per (day, prefix, model) for the last `days` days."""
        since = datetime.fromtimestamp(time.time() - days * 86400, timezone.utc).strftime("%Y-%m-%d")
        sums = "SUM(requests) AS requests, SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens, ROUND(SUM(usd), 4) AS usd"
        by_token = self._q(
            f"SELECT substr(u.token_hash, 1, {PREFIX_LEN}) AS token, MAX(COALESCE(t.disabled, 0)) AS disabled, MAX(l.user_id) AS user_id, {sums} "
            "FROM usage u LEFT JOIN tokens t ON t.token_hash = u.token_hash LEFT JOIN links l ON l.token_hash = u.token_hash "
            "WHERE day >= ? GROUP BY u.token_hash ORDER BY usd DESC", (since,))
        by_day = self._q(f"SELECT day, COUNT(DISTINCT token_hash) AS tokens, {sums} FROM usage WHERE day >= ? GROUP BY day ORDER BY day DESC", (since,))
        rows = self._q(f"SELECT day, substr(token_hash, 1, {PREFIX_LEN}) AS token, provider, model, {sums} FROM usage "
                       "WHERE day >= ? GROUP BY day, token_hash, provider, model ORDER BY day DESC, usd DESC", (since,))
        total = self._q(f"SELECT {sums} FROM usage WHERE day >= ?", (since,))[0]
        n_tokens = self._q("SELECT COUNT(*) AS n, COALESCE(SUM(disabled), 0) AS disabled FROM tokens")[0]
        lessons = self._q("SELECT COALESCE(SUM(status = 'approved'), 0) AS cached, COALESCE(SUM(status = 'pending'), 0) AS pending, "
                          "COALESCE(SUM(status = 'revoked'), 0) AS revoked, "
                          "COALESCE(SUM(hits), 0) AS hits, COALESCE(SUM(bytes), 0) AS bytes FROM lesson_candidates")[0]
        builds = self._q("SELECT COUNT(*) AS n FROM builds WHERE month = ?", (this_month(),))[0]
        events = self._q("SELECT day, name, SUM(count) AS count, COUNT(DISTINCT token_hash) AS installs FROM events "
                         "WHERE day >= ? GROUP BY day, name ORDER BY day DESC, count DESC", (since,))
        return {
            "since": since,
            "total": {k: (total[k] or 0) for k in total.keys()},
            "registered_tokens": n_tokens["n"],
            "disabled_tokens": n_tokens["disabled"],
            "by_token": [dict(r) | {"disabled": bool(r["disabled"])} for r in by_token],
            "by_day": [dict(r) for r in by_day],
            "by_day_token_model": [dict(r) for r in rows],
            "lessons": {**dict(lessons), "builds_this_month": builds["n"]},
            "usd_today": round(self.usd_today(), 4),
            "new_installs_today": self.new_installs_on(),
            "paused": self.paused(),
            "alerts_today": self.alerts_on(),
            "events": [dict(r) for r in events],
        }


def open_store() -> Store:
    # Postgres seam: when DATABASE_URL is set, return a PostgresStore with the same methods.
    return Store(default_db_path())

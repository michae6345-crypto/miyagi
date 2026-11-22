"""Storage for miyagi-cloud: install tokens and usage counters.

This module is the only place that touches the database. The app calls the methods on
`Store` and nothing else, so moving to Postgres (Supabase) later means writing a
`PostgresStore` with the same methods and returning it from `open_store()` when
`DATABASE_URL` is set. Nothing here ever sees a raw token: callers pass the sha256 hex.
"""

from __future__ import annotations

import hashlib
import json
import os
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
-- Requests per install, UTC day and x-miyagi-role (coach, lesson, scene, ...): the coach's daily cap reads it.
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
-- Shared lesson cache (ROADMAP 3.1, A08): every upload is a candidate per video, schema and uploader. GET serves only
-- the one approved candidate (POST /admin/lessons/{video_id}/approve, or LESSON_AUTO_APPROVE_N matching uploads).
CREATE TABLE IF NOT EXISTS lesson_candidates (
    video_id   TEXT NOT NULL,
    schema     INTEGER NOT NULL,
    uploader   TEXT NOT NULL,              -- token hash of the install that uploaded it
    body       TEXT NOT NULL,              -- the lesson JSON (validated, UTF-8, ensure_ascii off)
    bytes      INTEGER NOT NULL,
    body_hash  TEXT NOT NULL,              -- sha256 of the normalized lesson JSON (sorted keys)
    net        TEXT NOT NULL,              -- the uploader's network (IPv4 /24, IPv6 /48) for auto-approval
    status     TEXT NOT NULL DEFAULT 'pending',  -- pending | approved
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
    bucket TEXT NOT NULL,                  -- client IP (IPv4) or its /64 (IPv6)
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
"""

PLANS = ("free", "pro")  # free: the caps in app.py apply; pro: no caps

PREFIX_LEN = 12  # how much of the token hash the admin views show


def lesson_hash(lesson) -> str:
    """sha256 of a lesson's normalized JSON (sorted keys, no whitespace): identical lessons hash alike."""
    norm = json.dumps(lesson, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


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

    def __init__(self, path: str) -> None:
        self.path = path
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
        self._pruned_hour = -1

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
        """mint_net: the client network it was minted from (IPv4 address or IPv6 /48), for the anonymous per-network cap."""
        self._q("INSERT INTO tokens (token_hash, install_id, app_version, platform, created_at, mint_net) VALUES (?, ?, ?, ?, ?, ?)",
                (token_hash, install_id, app_version, platform, time.time(), mint_net))

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
                                 "net = excluded.net, status = 'pending', created_at = excluded.created_at",
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
        self._db.execute("UPDATE lesson_candidates SET status = 'approved' WHERE video_id = ? AND schema = ? AND uploader = ?",
                         (video_id, schema, uploader))

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
                                   "WHERE video_id = ? AND schema = ? AND body_hash = ? AND net NOT IN ('legacy', 'unknown')",
                                   (video_id, schema, body_hash)).fetchone()
            if row["u"] < n or row["nets"] < n:
                return False
            first = self._db.execute("SELECT uploader FROM lesson_candidates WHERE video_id = ? AND schema = ? AND body_hash = ? "
                                     "ORDER BY created_at LIMIT 1", (video_id, schema, body_hash)).fetchone()
            self._approve_row(video_id, schema, first["uploader"])
            return True

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
            self._db.execute("DELETE FROM lesson_puts WHERE day < ?", (_days_ago(2),))
            return True, used + 1

    # install token minting (POST /v1/install, /v1/register) --------------
    def mint_check(self, bucket: str, per_hour: int, per_day: int, global_max: int, now: float | None = None) -> dict:
        """Count one mint for `bucket` unless a limit is reached, in one transaction. 0 turns a limit off.

        per_hour: this bucket in the current clock hour. per_day: this bucket over the last 24 clock hours.
        global_max: every bucket together in the current clock hour.
        Returns {"hit": None | "hour" | "day" | "global", "used", "cap", "retry_s", "global": mints this hour}."""
        t = time.time() if now is None else now
        hour = int(t // 3600)
        to_next_hour = (hour + 1) * 3600 - t
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                if self._pruned_hour != hour:
                    self._db.execute("DELETE FROM mints WHERE hour < ?", (hour - 48,))
                    self._pruned_hour = hour
                g = int(self._db.execute("SELECT COALESCE(SUM(n), 0) FROM mints WHERE hour = ?", (hour,)).fetchone()[0])
                hit = None
                if global_max > 0 and g >= global_max:
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
                self._db.execute("COMMIT")
                return {"hit": None, "used": 0, "cap": 0, "retry_s": 0, "global": g + 1}
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

    # lesson build quota ----------------------------------------------------
    def builds_in_month(self, token_hash: str, month: str | None = None) -> int:
        rows = self._q("SELECT COUNT(*) AS n FROM builds WHERE token_hash = ? AND month = ?", (token_hash, month or this_month()))
        return int(rows[0]["n"])

    def has_build(self, token_hash: str, video_id: str) -> bool:
        """This install claimed a build of this video (any month)."""
        return bool(self._q("SELECT 1 FROM builds WHERE token_hash = ? AND video_id = ? LIMIT 1", (token_hash, video_id)))

    def claim_build(self, token_hash: str, video_id: str, cap: int) -> tuple[bool, int]:
        """Use one of this month's builds for `video_id`, atomically. A video already claimed this month is free.
        cap <= 0 means no cap. Returns (allowed, builds used this month after the call)."""
        month = this_month()
        with self._lock:
            n = self._db.execute("SELECT COUNT(*) FROM builds WHERE token_hash = ? AND month = ?", (token_hash, month)).fetchone()[0]
            if self._db.execute("SELECT 1 FROM builds WHERE token_hash = ? AND month = ? AND video_id = ?",
                                (token_hash, month, video_id)).fetchone():
                return True, n
            if cap > 0 and n >= cap:
                return False, n
            self._db.execute("INSERT INTO builds (token_hash, month, video_id, created_at) VALUES (?, ?, ?, ?)",
                             (token_hash, month, video_id, time.time()))
            return True, n + 1

    # per-role daily requests ------------------------------------------------
    def count_role(self, token_hash: str, role: str) -> None:
        self._q("INSERT INTO role_usage (token_hash, day, role, requests) VALUES (?, ?, ?, 1) "
                "ON CONFLICT (token_hash, day, role) DO UPDATE SET requests = requests + 1", (token_hash, today(), role))

    def role_requests_today(self, token_hash: str, role: str) -> int:
        rows = self._q("SELECT requests FROM role_usage WHERE token_hash = ? AND day = ? AND role = ?", (token_hash, today(), role))
        return int(rows[0]["requests"]) if rows else 0

    # admission: caps checked and counted in one step -------------------------
    def admit_call(self, token_hash: str, provider: str, model: str, role: str | None,
                   role_caps: dict[str, int], daily_cap: int, *, usd_cap: float = 0.0, user_id: str | None = None,
                   global_usd_cap: float = 0.0, reserve_usd: float = 0.0, net: str | None = None, net_usd_cap: float = 0.0,
                   dry_run: bool = False) -> tuple[str | None, float, float]:
        """Count one forwarded AI call unless a cap is reached, and reserve its estimated cost. Check, count and
        reserve happen under one lock and one transaction, so parallel calls cannot all slip in under a cap.

        global_usd_cap: every install together per UTC day, reservations included (0 = none).
        role_caps: {role: calls per UTC day} for this install (0 or absent = no cap).
        daily_cap / usd_cap: calls / estimated USD per UTC day (0 = none), for this install, or with `user_id` for
        every install linked to that user together.
        net / net_usd_cap: estimated USD per UTC day of every unlinked install minted from network `net` together
        (0 or no net = none); the caller passes them for anonymous installs only.
        reserve_usd is added to this call's usage row now; settle() swaps it for the real cost when the call ends.
        dry_run: check only, count nothing.
        Returns (None, 0, 0) when admitted, else (the cap hit: "global_usd" | "role" | "daily" | "usd" | "net_usd", used, cap)
        with nothing counted."""
        day = today()
        reserve_usd = max(float(reserve_usd), 0.0)
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                if global_usd_cap > 0:
                    spent = float(self._db.execute("SELECT COALESCE(SUM(usd), 0) FROM usage WHERE day = ?", (day,)).fetchone()[0])
                    if spent >= global_usd_cap or spent + reserve_usd > global_usd_cap:
                        self._db.execute("ROLLBACK")
                        return "global_usd", spent, global_usd_cap
                cap = role_caps.get(role or "", 0)
                if role and cap > 0:
                    row = self._db.execute("SELECT requests FROM role_usage WHERE token_hash = ? AND day = ? AND role = ?",
                                           (token_hash, day, role)).fetchone()
                    used = int(row[0]) if row else 0
                    if used >= cap:
                        self._db.execute("ROLLBACK")
                        return "role", used, cap
                if daily_cap > 0 or usd_cap > 0:
                    if user_id:
                        scope, arg = "token_hash IN (SELECT token_hash FROM links WHERE user_id = ?)", user_id
                    else:
                        scope, arg = "token_hash = ?", token_hash
                    reqs, usd = self._db.execute(f"SELECT COALESCE(SUM(requests), 0), COALESCE(SUM(usd), 0) FROM usage "
                                                 f"WHERE day = ? AND {scope}", (day, arg)).fetchone()
                    if user_id:  # what installs relinked away from this user had used today
                        mr, mu = self._db.execute("SELECT COALESCE(SUM(requests), 0), COALESCE(SUM(usd), 0) FROM moved_usage "
                                                  "WHERE day = ? AND from_user = ?", (day, user_id)).fetchone()
                        reqs, usd = int(reqs) + int(mr), float(usd) + float(mu)
                    if daily_cap > 0 and int(reqs) >= daily_cap:
                        self._db.execute("ROLLBACK")
                        return "daily", int(reqs), daily_cap
                    if usd_cap > 0 and (float(usd) >= usd_cap or float(usd) + reserve_usd > usd_cap):
                        self._db.execute("ROLLBACK")
                        return "usd", float(usd), usd_cap
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

    def usd_today(self) -> float:
        """Estimated spend so far this UTC day, every install together (the DAILY_USD_CAP kill switch reads it)."""
        return float(self._q("SELECT COALESCE(SUM(usd), 0) AS usd FROM usage WHERE day = ?", (today(),))[0]["usd"])

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

    # links ----------------------------------------------------------------
    def link_user(self, token_hash: str, user_id: str) -> None:
        """Link an install to a user. Re-linking the same pair keeps the first linked_at."""
        self.link_user_capped(token_hash, user_id, 0)

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

    def link_user_capped(self, token_hash: str, user_id: str, max_installs: int) -> bool:
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
                self._db.execute("INSERT INTO links (token_hash, user_id, linked_at) VALUES (?, ?, ?) "
                                 "ON CONFLICT (token_hash) DO UPDATE SET user_id = excluded.user_id, linked_at = excluded.linked_at "
                                 "WHERE links.user_id != excluded.user_id", (token_hash, user_id, time.time()))
                self._db.execute("COMMIT")
                return True
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

    def get_link(self, token_hash: str) -> dict | None:
        rows = self._q("SELECT user_id, linked_at FROM links WHERE token_hash = ?", (token_hash,))
        return dict(rows[0]) if rows else None

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
            "events": [dict(r) for r in events],
        }


def open_store() -> Store:
    # Postgres seam: when DATABASE_URL is set, return a PostgresStore with the same methods.
    return Store(default_db_path())

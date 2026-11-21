"""Storage for miyagi-cloud: install tokens and usage counters.

This module is the only place that touches the database. The app calls the methods on
`Store` and nothing else, so moving to Postgres (Supabase) later means writing a
`PostgresStore` with the same methods and returning it from `open_store()` when
`DATABASE_URL` is set. Nothing here ever sees a raw token: callers pass the sha256 hex.
"""

from __future__ import annotations

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
-- Shared lesson cache (ROADMAP 3.1): one video draft per YouTube video id and draft schema version, shared
-- by every install. First upload wins; operators remove a bad one with DELETE /admin/lessons/{video_id}.
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
"""

PLANS = ("free", "pro")  # free: the caps in app.py apply; pro: no caps

PREFIX_LEN = 12  # how much of the token hash the admin views show


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


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

    def _q(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(sql, args).fetchall()

    # tokens ---------------------------------------------------------------
    def add_token(self, token_hash: str, install_id: str, app_version: str, platform: str) -> None:
        self._q("INSERT INTO tokens (token_hash, install_id, app_version, platform, created_at) VALUES (?, ?, ?, ?, ?)",
                (token_hash, install_id, app_version, platform, time.time()))

    def get_token(self, token_hash: str) -> dict | None:
        rows = self._q("SELECT token_hash, disabled, plan FROM tokens WHERE token_hash = ?", (token_hash,))
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
        """The cached lesson ({body, created_at}) for this video and schema, counting a hit; None on a miss."""
        with self._lock:
            row = self._db.execute("SELECT body, created_at FROM lessons WHERE video_id = ? AND schema = ?",
                                   (video_id, schema)).fetchone()
            if row is None:
                return None
            self._db.execute("UPDATE lessons SET hits = hits + 1 WHERE video_id = ? AND schema = ?", (video_id, schema))
            return dict(row)

    def put_lesson(self, video_id: str, schema: int, body: str, uploader: str) -> bool:
        """Store a lesson unless one is already cached for this video and schema (first upload wins)."""
        with self._lock:
            cur = self._db.execute("INSERT OR IGNORE INTO lessons (video_id, schema, body, bytes, uploader, created_at) "
                                   "VALUES (?, ?, ?, ?, ?, ?)", (video_id, schema, body, len(body.encode()), uploader, time.time()))
            return cur.rowcount == 1

    def delete_lessons(self, video_id: str) -> int:
        with self._lock:
            return self._db.execute("DELETE FROM lessons WHERE video_id = ?", (video_id,)).rowcount

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

    def requests_today(self, token_hash: str) -> int:
        rows = self._q("SELECT COALESCE(SUM(requests), 0) AS n FROM usage WHERE token_hash = ? AND day = ?", (token_hash, today()))
        return int(rows[0]["n"])

    def usage_report(self, days: int = 30) -> dict:
        """Totals per token-hash prefix, per day, and per (day, prefix, model) for the last `days` days."""
        since = datetime.fromtimestamp(time.time() - days * 86400, timezone.utc).strftime("%Y-%m-%d")
        sums = "SUM(requests) AS requests, SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens, ROUND(SUM(usd), 4) AS usd"
        by_token = self._q(
            f"SELECT substr(u.token_hash, 1, {PREFIX_LEN}) AS token, MAX(COALESCE(t.disabled, 0)) AS disabled, {sums} "
            "FROM usage u LEFT JOIN tokens t ON t.token_hash = u.token_hash WHERE day >= ? GROUP BY u.token_hash ORDER BY usd DESC", (since,))
        by_day = self._q(f"SELECT day, COUNT(DISTINCT token_hash) AS tokens, {sums} FROM usage WHERE day >= ? GROUP BY day ORDER BY day DESC", (since,))
        rows = self._q(f"SELECT day, substr(token_hash, 1, {PREFIX_LEN}) AS token, provider, model, {sums} FROM usage "
                       "WHERE day >= ? GROUP BY day, token_hash, provider, model ORDER BY day DESC, usd DESC", (since,))
        total = self._q(f"SELECT {sums} FROM usage WHERE day >= ?", (since,))[0]
        n_tokens = self._q("SELECT COUNT(*) AS n, COALESCE(SUM(disabled), 0) AS disabled FROM tokens")[0]
        lessons = self._q("SELECT COUNT(*) AS cached, COALESCE(SUM(hits), 0) AS hits, COALESCE(SUM(bytes), 0) AS bytes FROM lessons")[0]
        builds = self._q("SELECT COUNT(*) AS n FROM builds WHERE month = ?", (this_month(),))[0]
        return {
            "since": since,
            "total": {k: (total[k] or 0) for k in total.keys()},
            "registered_tokens": n_tokens["n"],
            "disabled_tokens": n_tokens["disabled"],
            "by_token": [dict(r) | {"disabled": bool(r["disabled"])} for r in by_token],
            "by_day": [dict(r) for r in by_day],
            "by_day_token_model": [dict(r) for r in rows],
            "lessons": {**dict(lessons), "builds_this_month": builds["n"]},
        }


def open_store() -> Store:
    # Postgres seam: when DATABASE_URL is set, return a PostgresStore with the same methods.
    return Store(default_db_path())

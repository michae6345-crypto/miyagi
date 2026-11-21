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
"""

PREFIX_LEN = 12  # how much of the token hash the admin views show


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


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

    def _q(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(sql, args).fetchall()

    # tokens ---------------------------------------------------------------
    def add_token(self, token_hash: str, install_id: str, app_version: str, platform: str) -> None:
        self._q("INSERT INTO tokens (token_hash, install_id, app_version, platform, created_at) VALUES (?, ?, ?, ?, ?)",
                (token_hash, install_id, app_version, platform, time.time()))

    def get_token(self, token_hash: str) -> dict | None:
        rows = self._q("SELECT token_hash, disabled FROM tokens WHERE token_hash = ?", (token_hash,))
        return dict(rows[0]) if rows else None

    def set_disabled(self, prefix: str, disabled: bool) -> list[str]:
        """Disable/enable the tokens whose hash starts with `prefix`; returns the matched hashes."""
        rows = self._q("SELECT token_hash FROM tokens WHERE substr(token_hash, 1, ?) = ?", (len(prefix), prefix))
        hashes = [r["token_hash"] for r in rows]
        if len(hashes) == 1:
            self._q("UPDATE tokens SET disabled = ? WHERE token_hash = ?", (int(disabled), hashes[0]))
        return hashes

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

    # links ----------------------------------------------------------------
    def link_user(self, token_hash: str, user_id: str) -> None:
        """Link an install to a user. Re-linking the same pair keeps the first linked_at."""
        self._q("INSERT INTO links (token_hash, user_id, linked_at) VALUES (?, ?, ?) "
                "ON CONFLICT (token_hash) DO UPDATE SET user_id = excluded.user_id, linked_at = excluded.linked_at "
                "WHERE links.user_id != excluded.user_id", (token_hash, user_id, time.time()))

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
        return {
            "since": since,
            "total": {k: (total[k] or 0) for k in total.keys()},
            "registered_tokens": n_tokens["n"],
            "disabled_tokens": n_tokens["disabled"],
            "by_token": [dict(r) | {"disabled": bool(r["disabled"])} for r in by_token],
            "by_day": [dict(r) for r in by_day],
            "by_day_token_model": [dict(r) for r in rows],
        }


def open_store() -> Store:
    # Postgres seam: when DATABASE_URL is set, return a PostgresStore with the same methods.
    return Store(default_db_path())

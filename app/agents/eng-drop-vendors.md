# eng-drop-vendors (E-vendors: drop Bright Data + Tiger)

**Status:** done, pushed, not merged · **Branch:** `claude/eng-drop-vendors` (from `origin/claude/eng-cloud-client`) · **Engine only** (no app files, no port)

## Goal
A downloaded miyagi never asks for a Bright Data key or a Tiger Data URL, and the engine runs (and imports) with neither key and without psycopg. DISTRIBUTION-PLAN section 6: "Stop asking for Bright Data and Tiger: `config.py` `KEY_ENV`, `psycopg` out of `pyproject.toml`; full code removal later (ROADMAP 3.6)". Tiger's job (the learning-event and run-metric memory) moves to a local SQLite file under the engine data dir. Plus BUILD-PLAN E4's `FINDER_GEMINI_FALLBACK=0` in `finder/core.py`.

## What changed (server/)
- `config.py`
  - `KEY_ENV` is now `anthropic, gemini, elevenlabs, miyagiToken`. A `brightdata` / `tigerUrl` value in `config.keys` is ignored (never stored, never exported to `os.environ`), and `config.status` no longer carries them (`apply_keys` builds the status from `KEY_ENV`).
  - `ENV_ONLY_KEYS = {"brightdata": "BRIGHTDATA_API_KEY"}`: `get_key("brightdata")` reads `.env` only, so Bright Data stays an optional dev extra. `RETIRED_KEYS = ("brightdata", "tigerUrl")` names what the app may still send.
  - `safe_env()` still strips `BRIGHTDATA_*`, `TIGER_*` (and now names `BRIGHTDATA_API_KEY` / `TIGER_DATABASE_URL` explicitly).
- `pyproject.toml`: `psycopg[binary]` removed from the engine dependencies.
- `checks/tiger.py`: same module name and API (`record_event`, `record_metric`, `record_run`, `get_writer`, `TigerWriter`, `replay_spool`, `spool_status`, `stats`, `_redact`), so `orchestrator.modules`, `orchestrator.tiger_runs` and `checks.stats_web` work unchanged.
  - `TigerWriter()` (what the engine uses) writes to the **local store** `metrics_db_path()`: `$MIYAGI_METRICS_DB`, else `<engine data dir>/metrics.sqlite`, the data dir being `$MIYAGI_STATE_DIR` or `~/miyagi/state` (same folder as `server.sessions.store`). Tables `learning_events`, `training_metrics`, `runs` with the contract's columns (`shared/contracts/tiger-schema.sql`), times as unix seconds (UTC), indexes on (lesson_id, time) and (run_id, time), `runs` upserted with the same merge rules. WAL journal, file created `0600` (a `question` event can hold the learner's text). NaN metric values are stored as NULL. Odd values (a list in `tail`) are stored as JSON text, so one bad row cannot poison a batch or the spool.
  - The spool stays as the fallback: if the store can't be opened or written, batches go to `~/.miyagi/tiger-spool` (`$TUT_SPOOL_DIR`) and the writer retries every 30 s, then loads the whole spool, `tut run`'s files included, into the store. One warning per outage. **First start on a Mac that already has a spool:** it is loaded into the store once, in the writer thread (never the engine loop).
  - TIGER_DATABASE_URL is no longer read by the writer (the env-following `_sync_dsn` is gone). The psycopg path remains only for an explicit `TigerWriter(dsn=...)` (tests, dev tools) and `python -m server.checks.tiger --tiger`.
  - `stats(conn)` also takes a local store connection (row totals, rows/s, latency of the two panel reads on raw rows). `local_summary()` and `open_local()` are new.
  - CLI: `python -m server.checks.tiger --ping` shows the local store path, row counts, newest row and spool backlog; `--flush-spool` loads the spool into it; `--tiger` keeps the old Tiger checks.
- `screen/metrics.py`: its own Tiger writer (screen OCR metrics) is a no-op when psycopg is not installed, even with `TIGER_DATABASE_URL` in `.env` (before: a retry loop on a missing driver). Its "not persisted" log is INFO now.
- `finder/core.py`: Gemini scoring fallback is `FINDER_GEMINI_FALLBACK=0` by default (env.py already) and now also never runs in miyagi cloud mode (`server.config.mode("gemini") == "cloud"`: the cloud's Gemini is video only). Docstring notes Bright Data is optional.

Bright Data needed no code change to be a no-op: `finder` (`brightdata.available`), `coach/web.py` (`configured()`) and `lesson/transcript.py` (`_brightdata_config()`) all skip it when no key is set, and the app can no longer supply one.

## Checks run
- `python -m py_compile` on the 4 changed .py files: OK.
- `python -I` import (keys empty: `ANTHROPIC_API_KEY= GEMINI_API_KEY= BRIGHTDATA_API_KEY= TIGER_DATABASE_URL=`, temp `MIYAGI_STATE_DIR`) of `server.config`, `checks.tiger`, `checks.stats_web`, `checks.curves`, `screen.metrics`, `screen.reader`, `finder.core`, `finder.env`, `finder.brightdata`, `coach.web`, `lesson.transcript`, `orchestrator.tiger_runs`, `orchestrator.modules`, `orchestrator.main`: OK, psycopg never imported. `coach.web.configured()` and `finder` `has_brightdata` are False.
- An offline script (scratchpad, not committed; psycopg blocked by an import hook, temp dirs only, no network): config ignores app `brightdata`/`tigerUrl`, `.env` Bright Data still read, `safe_env` strips both; the writer stores events (step duration filled), metrics (NaN as NULL), the run upsert (exit code and end merged), loads a `tut run` spool file (skips a malformed line, deletes the file), creates the db `0600`; an unwritable store spools then loads on retry; `stats()` and `local_summary()` on the store; screen Tiger writer is a no-op with a URL set; finder fallback off by default and off in cloud mode; `apply_keys` status has no `brightdata`/`tigerUrl`. All pass.
- CLI `--ping`, `--flush-spool`, `--ping --json` against a temp store: OK.
- No pytest, no paid calls, nothing touched on :8787.

## Core requests
1. **Contract (`shared/contracts/events.ts` + `events.py`, Adrian, `contract:` commit):** make `brightdata` and `tigerUrl` optional (or remove them) in `config.keys` and `KeyStatusEvent["config.status"]` / `ConfigStatus`. Until then the hub logs "config.status does not match events.ts; sending anyway" on each `config.keys` (and raises under `ORCH_STRICT=1`), because `ConfigStatus` still requires both.
2. **App (`michael/app-cloud-token`, `features/settings/keys.ts` + `Settings.tsx`):** drop `brightdata` and `tigerUrl` from `KEY_NAMES` and the Settings rows (the engine ignores them now, and `config.status` no longer reports them, so those rows would show no state).
3. **`server/conftest.py` (tests):** also set `MIYAGI_METRICS_DB` (or `MIYAGI_STATE_DIR`) to a temp path in `_private_tiger_spool`, so a test run never writes into `~/miyagi/state/metrics.sqlite`.
4. **Tests to update (not run here):** `checks/tests/test_tiger.py::test_follows_a_tiger_url_sent_after_start` (env-following removed: a writer without `dsn` is the local store); `test_ping_*` and `screen/tests/test_errors.py::test_tiger_status_states` / `test_tiger_retries_*` need `pytest.importorskip("psycopg")`; `tests/test_rehearsal_keys.py` / `tests/demo_rehearsal.py` still list `brightdata` / `tigerUrl` (harmless: ignored). Worth adding a local-store test (my offline script's cases).
5. **`checks/stats_web.py` (/stats) and `checks/curves.py`:** still read Tiger only (continuous aggregates), so /stats shows offline unless a dev sets `TIGER_DATABASE_URL` with psycopg. Point them at `open_local()` (raw-row queries) or remove them with the rest of Tiger in ROADMAP 3.6. `checks/README.md` (Tiger writer section) needs the same update.
6. **`cli/` (`tut`):** `cli/pyproject.toml` still depends on psycopg and `tut` still writes to Tiger / the spool; the engine now loads that spool into the local store. Decide in ROADMAP 3.6 (bundle build `scripts/bundle-engine.mjs` already plans to prune `psycopg_binary`).
7. **`orchestrator/main.py` (optional):** if the contract keeps the two fields required for a while, add `status.update({k: "missing" for k in server_config.RETIRED_KEYS})` in `apply_keys` to keep validation quiet.

## Notes
- Engine on :8787 must be restarted (and `uv sync` re-run) to pick this up; `uv sync` will remove psycopg from the venv, after which a `.env` `TIGER_DATABASE_URL` does nothing.
- `finder/core.py` is also in E4's file list; the change here is three lines in `_Run.__init__` plus a helper, so a merge is mechanical.

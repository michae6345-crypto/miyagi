# server/checks (owner: Michael / E3)

```python
from server.checks import evaluate_step, RunContext, step_passed, FILE_CHECK_TYPES

ctx = RunContext(workdir=lesson_workdir, command=last_cmd, running=False, exit_code=0,
                 output_tail=last_lines, metrics={"loss": [(step, value), ...]},
                 visual={"c9": {"pass": True, "detail": "..."}})
results = evaluate_step(step, ctx)                         # [{checkId, label, status, detail}]
results = evaluate_step(step, ctx, types=FILE_CHECK_TYPES) # on a file save
results = evaluate_step(step, ctx, screen=screen.latest())  # screen-first: ScreenObservation (dict or object)
results = evaluate_step(step, screen=obs, types=SCREEN_CHECK_TYPES)  # on a new OCR frame
results = evaluate_step(step, ctx, which="precision")      # the step's optional precision_checks ("all" = both)

gate = evaluate_gate(step, ctx, screen=obs, precision_mode=False)
# -> {passed, via: "checks"|"precision"|None, checks: [...], precision: [...]}
if step_passed(results): ...                               # every check passes (and there is at least one)
```

**`checks` vs `precision_checks`.** `checks` (screen-gradable) gate the step. `precision_checks` (file_*, command_exit_ok,
::metric:: names; ids `s{n}p{k}`) are backups for precision mode (known workdir / `tut run`). In screen mode `evaluate_gate`
doesn't evaluate them at all, so they can never block a step. In precision mode the step passes if all `checks` pass **or**
all (non-empty) `precision_checks` pass: an extra route to green, never an extra hurdle.

A **pure function**: no network, no DB, no model calls. It never raises: a malformed check is reported as `fail`.

| type | pass | fail | pending |
|---|---|---|---|
| `screen_contains` | regex found in the OCR text (scoped to `app` windows if given; also tried with whitespace collapsed, so it survives OCR line wraps) | not seen; or `app` not on screen once the segment is over (detail: "open Terminal so I can check: …") | no screen reading at all, or `app` not on screen while the segment still plays |
| `screen_absent` | regex not in the (scoped) OCR text; or `app`/screen not visible once the segment is over (a hidden Terminal can't show a Traceback) | still showing (detail quotes it); only ever when the pattern is actually seen | `app`/screen not visible while the segment still plays |
| `file_exists` | file present | missing | – |
| `file_contains` | regex (MULTILINE) found; detail gives `file:line` | file missing / no match / bad regex | – |
| `command_exit_ok` | the last run of the same script exited 0 | exited ≠ 0 | no run yet, still running, or the last run was a different script (flags may differ) |
| `output_contains` | regex in the output tail | run ended without a match | no run / still running |
| `metric_threshold` | median of the last 5 points (≤ `by_step`) satisfies `op value` | `by_step` reached or run ended without it | still training |
| `metric_trend` | see below | see below | < 6 points or < 50 % of `window` covered |
| `visual` | `ctx.visual[id].pass` | `ctx.visual[id]` is false | no verdict supplied (the orchestrator calls the vision model) |

### Screen-first details (`screen.py`)
- **Hidden apps never leave a check pending forever.** `RunContext.segment_done` (True once the step's video segment
  has played; `None` = unknown, treated as done) decides: after the segment, `screen_absent` on a hidden app passes,
  `screen_contains` on a hidden app fails with "open <app> so I can check: <label>", and a screen-read metric
  (`metric_pattern` + `app`) whose app is hidden fails with "open <app> so I can read <metric>". A fail is what lets
  the orchestrator's idle/stuck help fire; `pending` never does. With no screen reading at all, `screen_contains`
  stays pending (not the learner's fault). Orchestrator wiring: pass `segment_done=session.segment_done` in the context.
- Accepts a ScreenObservation `{t, app, windows[{app,title,rect}], blocks[{text,rect,confidence,app?}]}` or `{app: [lines]|text}`.
  A block belongs to the frontmost window (first in `windows`) that contains its centre. Rects can be `{x,y,w,h}`/`{x,y,width,height}`/`[x,y,w,h]`.
  `app` matching is a case-insensitive substring. Blocks with confidence < 0.3 are dropped.
- `metric_pattern` (on `metric_threshold`/`metric_trend`): `ctx.metrics[metric]` is authoritative, so E6/the orchestrator should accumulate
  screen-read metrics there (run_id `screen-<lesson>`). Only when it's empty does the evaluator apply the pattern itself to the visible
  terminal text (+ run output). Named groups `step`/`value` (without `step`, line order is used); it tolerates OCR slips like `O.25`.
  Without `metric`, the series is keyed by the check id. `extract_metrics(pattern, text)` is exported so E6 can reuse the same parser.

### Lesson file and run evidence ("Just teach me", QA 11-14)
The orchestrator (`LessonSession._settle_checks` / `_need_run`) uses three pure helpers so checks neither un-pass nor false-pass:
- `screen_check_on_file(check, path, window_open=True)`: a VS Code `screen_contains` graded on the lesson's file on disk,
  for frames that can't show the lesson window (another folder's VS Code window in front, or no editor text). Pass when
  the pattern is in the file; else "not in <file> yet", or "Open VS Code so I can check it." only when no lesson window exists.
- A `screen_contains` that passed in a step stays passed (latched in the session) unless the editor's text lacks it:
  the VS Code companion's live buffer when it holds unsaved edits of the file, else the file on disk once saved after
  the pass. OCR misreads while the learner types into an unsaved (still empty) file never un-pass it.
- `terminal_runs(command, rows, expect)` -> `(runs, error, shows)`: how often terminal rows show `command` run (followed
  by another row, so a typed-but-unrun command never counts), and `run_output`'s verdict on the output under the last
  run (not "shown" when a later row runs the same program: it may be a misread newer run). With
  `command_matches(expected, actual)` for `tut run` / Run it for me / VS Code `command_end` runs, this is the run
  evidence a run step needs: its code being on screen is not enough. A command with no script (`python3 --version`,
  `node -v`) matches as a whole, at the end of the row / command line (`python` == `python3`).
- `run_output(lines, expect)` -> `(error, shows)`: `shows` = an `expect` regex is in the output; `error` = a crash
  (traceback, `XError:` line, "command not found") the step didn't ask for. An expected pattern found in the error
  lines ("run it and see the ZeroDivisionError") makes the crash the step's point; output printed before a crash doesn't.

### `metric_trend`: thresholds
The window is the points with `step ≥ latest_step − window` (default 1000; pending below 8 points or < 50 % coverage).
A trend needs **both** gates (Mann-Kendall test + Sen's slope):
1. **Significance:** the Mann-Kendall z-score (rank-based, so it scales with the noise automatically): `|z| ≥ 2.576` for `not_flat` (p<0.01, two-sided),
   `z ≤ −2.326` for `decreasing` (p<0.01, one-sided).
2. **Effect size:** the Theil–Sen relative change across the window (on log10 values when all are positive) is `≥ 5 %` (`not_flat`, same direction as z)
   or a drop of `≥ 2 %` (`decreasing`). This keeps a real but negligible drift (a PINN plateau creeping 0.2504 → 0.2490) from counting as progress.

Seed sweeps (300 seeds, 31 or 151 points per window):

| | flat curve, 10 % noise | flat curve, 20 % noise | loss decaying ~4× per window |
|---|---|---|---|
| before | 61/300 (not_flat), 72/300 (decreasing) falsely passed | 136/300 | passes |
| now | ≤ 3/300 | ≤ 3/300 | ≥ 98 % pass (tests) |

The trade-off: a *slow* decline of about 11 % per window under 10 % per-point noise with only 31 points is often graded "plateau" (about a third pass).
Log more often or use a larger `window` if that matters. Constants are at the top of `evaluator.py`.

**Divergence:** a NaN/inf (or `None`) as the latest point, or anywhere in the trend window, **fails** `metric_threshold`/`metric_trend`
("loss diverged: nan at step N") instead of grading the stale finite values. `tut run` forwards NaN as `{"value": null, "nonfinite": "nan"}`,
and screen OCR reads `nan`/`inf`.

`trend_stats(points)` is exported so the coach can quote the numbers.

## Watcher
```python
from server.checks.watcher import watch_workdir
w = watch_workdir(workdir, on_change=lambda paths: ...)   # paths are relative to the workdir, debounced 250 ms
async for paths in w.changes(): ...                       # or from asyncio
w.stop()
```
It uses watchdog (FSEvents) when available and falls back to polling (0.5 s). It ignores `.git`, `__pycache__`, `.venv`,
`node_modules`, `runs/`, `wandb/`, swap and temp files. `python -m server.checks.watcher <dir>` runs it standalone.

## Curves vs the tutorial (Tiger Data)
`server.checks.curves.compare_to_reference(conn, learner_run_id, metric="loss")` runs `sql/compare_curves.sql`
on the `metrics_1s` continuous aggregate (set it up with `tut db init` / `tut db load-ref`, see `cli/README.md`).

## Tests
`python -m pytest server/checks -p no:asyncio`. They include a flat PINN loss that must FAIL `not_flat` and a dropping one that must PASS.

## Tiger writers (`tiger.py`): the time-series memory of every session
```python
from server.checks.tiger import record_event, record_metric
record_event("step_started", lesson_id, step_id, video_t)                       # every transition:
record_event("check_fail", lesson_id, step_id, video_t, {"check_id": "s4c2", "detail": "..."})
record_event("step_passed", lesson_id, step_id, video_t)   # duration_s filled in from the matching step_started
record_metric(f"screen-{lesson_id}", "loss", step, value)  # any numeric signal (loss, tests passing, build ms, ...)
```
- Kinds: `step_started | check_pass | check_fail | offtrack | fix_applied | question | step_passed`. `check_id` from the payload goes in its own column.
  Every row carries `session_id` (`$TUT_SESSION_ID` or random per engine process).
- Non-blocking: an in-memory queue, with a daemon thread `COPY`ing batches every 0.5 s. It never blocks or raises into the engine.
- **Offline-safe:** when Tiger can't be reached (no URL, the venue Wi-Fi drops the port, a write error), batches go to a local spool
  `~/.miyagi/tiger-spool/*.jsonl` (`$TUT_SPOOL_DIR` overrides; capped at 200 MB, beyond that rows are counted in `dropped`). It retries every **30 s**
  and, once connected, uploads every spool file first (the engine's own and `tut run`'s `tut-<run_id>.jsonl`). Each file is claimed by rename
  so it's never uploaded twice, and deleted once stored. There is one warning per outage, and the password is redacted from errors.
  `get_writer().flush()` on shutdown; `get_writer().counters()` gives in-process rows written and flush ms.
- Continuous aggregates (`shared/contracts/tiger-schema.sql`, real-time + refresh policies in `cli/sql/tiger-extras.sql`):
  `metrics_1s` (live curves), `time_per_step` (avg/min/max seconds per step), `check_fail_rate` (fails/passes/evaluations per check),
  `stuck_heatmap` (offtrack + check_fail per 15 s of video), `learner_progress` (per session per minute: steps/checks passed, fails, offtracks; take a running sum for cumulative progress).
- **Prove the connection** (e.g. on a phone hotspot): `python -m server.checks.tiger --ping` prints the host:port (never the user or password),
  TCP connect ms, login ms, PostgreSQL/timescaledb versions, `SELECT 1` round trip, the hypertables and continuous aggregates present (and missing),
  row counts and the spool backlog. Exit 0 = reachable. `--json` gives a machine-readable version; `--flush-spool` uploads the spool now.
- **Ports:** a Tiger Cloud service listens on its own (high) port from the connection string. That's the one venue Wi-Fi tends to block.
  If you enable **connection pooling** (pgBouncer) in the Console, the pooler is the *same host on another port*, which may or may not get through
  (copy it from the Console's *Connection pooling* tab or `<service>-credentials.txt`, use the session pool for `COPY`). Tiger's docs list no endpoint on
  443 or 5432, so don't count on one. If `--ping` says the TCP connect failed, use a phone hotspot; nothing is lost meanwhile because of the spool.
  ([connection pooling](https://www.tigerdata.com/docs/use-timescale/latest/services/connection-pooling), [finding connection details](https://www.tigerdata.com/docs/integrate/find-connection-details))
- `stats(conn)` (connection in autocommit) → `{training_metrics: {rows_per_s, total}, learning_events: {...}, chunks, query_ms: {live_curve, stuck_heatmap}}`. This is what `tut stats` prints.

## Stats page (`stats_web.py`): Tiger, visible
Mount it in the orchestrator (two lines):
```python
from server.checks.stats_web import router as stats_router
app.include_router(stats_router)
```
Then open **http://localhost:8787/stats**. For the app: `stats_web.OPEN_STATS_LINK` = `<a href="http://localhost:8787/stats" target="_blank" rel="noopener">Open stats</a>`
(in Electron: `shell.openExternal("http://localhost:8787/stats")`).
- Read-only. The page polls `GET /stats/data` every 2 s (optional `?run_id=&lesson_id=&source_id=&metric=`; by default the newest learner run and lesson).
- Panels, all read from continuous aggregates: the live curve (`metrics_1s`, log scale) with the **same lesson's** tutorial curve dashed and aligned by step,
  time per step (`time_per_step`), where learners get stuck per 15 s of video (`stuck_heatmap`), check fail rate (`check_fail_rate`), plus ingest rows/s,
  row totals, chunk count and the measured ms of every panel query.
- Offline (no URL, unreachable, connection dropped mid-query): `{"online": false, "error", "spool"}`. The page shows
  **"Tiger offline: N rows spooled, will upload on reconnect"** and blanks every number. It never shows stale or made-up values. After a failed connect
  it answers "offline" instantly for 10 s, so a 2 s refresh doesn't hammer the network. Chart.js 4.4.1 comes from cdnjs; with no internet the tables still work.

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
| `screen_contains` | regex found in the OCR text (scoped to `app` windows if given; also tried with whitespace collapsed, so it survives OCR line wraps) | not seen | no observation, or `app` not on screen |
| `screen_absent` | regex not in the (scoped) OCR text | still showing (detail quotes it) | no observation, or `app` not on screen |
| `file_exists` | file present | missing | – |
| `file_contains` | regex (MULTILINE) found; detail gives `file:line` | file missing / no match / bad regex | – |
| `command_exit_ok` | the last run of the same script exited 0 | exited ≠ 0 | no run yet, still running, or the last run was a different script (flags may differ) |
| `output_contains` | regex in the output tail | run ended without a match | no run / still running |
| `metric_threshold` | median of the last 5 points (≤ `by_step`) satisfies `op value` | `by_step` reached or run ended without it | still training |
| `metric_trend` | see below | see below | < 6 points or < 50 % of `window` covered |
| `visual` | `ctx.visual[id].pass` | `ctx.visual[id]` is false | no verdict supplied (the orchestrator calls the vision model) |

### Screen-first details (`screen.py`)
- Accepts a ScreenObservation `{t, app, windows[{app,title,rect}], blocks[{text,rect,confidence,app?}]}` or `{app: [lines]|text}`.
  A block belongs to the frontmost window (first in `windows`) that contains its centre. Rects can be `{x,y,w,h}`/`{x,y,width,height}`/`[x,y,w,h]`.
  `app` matching is a case-insensitive substring. Blocks with confidence < 0.3 are dropped.
- `metric_pattern` (on `metric_threshold`/`metric_trend`): `ctx.metrics[metric]` is authoritative, so E6/the orchestrator should accumulate
  screen-read metrics there (run_id `screen-<lesson>`). Only when it's empty does the evaluator apply the pattern itself to the visible
  terminal text (+ run output). Named groups `step`/`value` (without `step`, line order is used); it tolerates OCR slips like `O.25`.
  Without `metric`, the series is keyed by the check id. `extract_metrics(pattern, text)` is exported so E6 can reuse the same parser.

### `metric_trend`: thresholds
The window is the points with `step ≥ latest_step − window` (default window 1000). Two robust estimates of the relative change:
1. **median of thirds**: `1 − median(last third) / median(first third)`. Immune to spikes and minibatch noise.
2. **Theil–Sen**: the median pairwise slope of `log10(value)` against step (raw values if any are ≤ 0), turned into a relative change over the window span.

- `not_flat` passes when **both** estimates show **≥ 5 %** change across the window, in the same direction (`NOT_FLAT_MIN_REL_CHANGE`). 
  For example, a β=30 PINN plateau (0.2504 → 0.2490 over 1500 steps, ±3 % noise) fails, and a loss still decaying passes. It ignores direction
  (it means literally "not flat"); use `decreasing` when the direction matters.
- `decreasing` passes when both show a **≥ 2 %** drop (`DECREASING_MIN_REL_DROP`).
- NaN/inf points are ignored. The constants live at the top of `evaluator.py`.

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

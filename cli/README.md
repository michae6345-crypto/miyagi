# cli: `tut run` (owner: Michael / E3)

Runs the learner's command under a PTY (so output stays live and colored), passes every byte through
unchanged, parses `::metric::` lines (`shared/contracts/metric-protocol.md`), and reports the run to:

- **the engine** at `POST http://localhost:8787/ingest`: the body is a JSON **array** of events, at most about 5 POSTs/s:
  `run_started {run_id, command, cwd, lesson_id, step_id, source}` → `metric {run_id, step, name, value}` (≤50 per name per POST) →
  `output {run_id, lines[]}` (ANSI stripped) → `run_ended {run_id, exit_code}`.
  If the reply to the first POST is JSON with `lesson_id`/`step_id`, the run is tagged with them in Tiger.
- **Tiger Data** (`TIGER_DATABASE_URL`): a `runs` row (command, start/end, exit code, last 200 lines) and
  `training_metrics` rows inserted with batched `COPY` every second.

If the engine or the DB is down it prints **one** dim warning on stderr and keeps the passthrough
(the engine sink keeps retrying and replays `run_started` once the engine comes back). The exit code
is the child's (signal → 128+n). NaN/inf metrics go to Tiger but are skipped on the wire (invalid JSON for the app).

## Install (Python ≥ 3.11)
```bash
uv venv .venv --python 3.12 && uv pip install -e cli -e "server[dev]"
source .venv/bin/activate
```
`.env` is read from the current directory upwards, the repo root, or the main checkout when run from a worktree.

## Use
```bash
tut run python pinn_convection.py --beta 30          # what the learner types
tut run --hide-metrics python train.py               # hide ::metric:: lines from the terminal
tut run --step s5 -v python -c 'print("::metric:: {\"step\": 1, \"name\": \"loss\", \"value\": 0.5}")'
```
Flags: `--step/--lesson` (or `TUT_STEP_ID`/`TUT_LESSON_ID`), `--source tutorial`, `--engine URL`
(or `TUT_INGEST_URL`; `ENGINE_URL=ws://host:port` is mapped to `http://host:port/ingest`), `--no-engine`, `--no-db`, `-v`.
The child gets `TUT_RUN_ID` in its environment.

## Tiger Data setup and the tutorial reference curve
```bash
tut db init                                           # shared/contracts/tiger-schema.sql + cli/sql/tiger-extras.sql
tut db load-ref curve.csv --lesson pinn --step s5     # run with source='tutorial'
tut db compare <learner_run_id> [--ref <ref_run_id>] [--json]
```
- `init` runs each statement on its own in autocommit (continuous aggregates can't be created inside a transaction).
  `tiger-extras.sql` turns `metrics_1s`/`stuck_heatmap` into real-time aggregates and adds refresh
  policies. Without that, `WITH NO DATA` caggs stay empty on TimescaleDB ≥ 2.13.
- `load-ref` accepts `step,loss[,val_loss...]` (wide) or `step,name,value` / `step,value` (long); the step column may be
  `step/epoch/iter/global_step`, with optional `time` (ISO) or `elapsed` (s) columns. Without times, the points are spaced 1 s
  apart ending now, so each lands in its own `metrics_1s` bucket. It then calls `refresh_continuous_aggregate`.
  `cli/examples/pinn_convection_reference.synthetic.csv` is a **synthetic** curve for testing; replace it with the real tutorial's.
- `compare` runs `server/checks/sql/compare_curves.sql` (via `server.checks.curves.compare_to_reference`): the learner's and
  tutorial's `metrics_1s` buckets aligned by **training step** (nearest within 10 % / 50 steps), with
  `gap_decades = log10(learner/tutorial)` and a one-line summary the coach can quote.

## Tests
```bash
python -m pytest cli/tests -p no:asyncio
```

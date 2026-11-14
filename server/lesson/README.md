# server/lesson: YouTube tutorial → step graph (E2)

```python
from server.lesson import build_lesson
graph = await build_lesson(url, goal="train a PINN on the convection equation", workdir="demo/pinn")
```

Returns a graph that validates against `shared/contracts/step-graph.schema.json`. Optional
`api_key=` takes the app's bring-your-own Gemini key (`config.keys.gemini`) over `.env`.

**Screen-first checks.** Each step's `checks` are graded from the learner's screen:
`screen_contains` / `screen_absent` (short OCR-tolerant regex, scoped to an `app` such as "Code" or "Terminal")
and `metric_threshold` / `metric_trend` with a `metric_pattern` (named groups `step`, `value`) that reads
the loss off terminal lines. The precision-mode backups (`file_*`, `command_exit_ok`, metrics by
`::metric::` name) go in an extra per-step **`precision_checks`** list, because a step passes only when
ALL `checks` pass and these can't be evaluated without a known workdir / `tut run`. Targets carry `app` +
a short on-screen `match` ("def lossPDE"). Extra top-level `build` = models, timing, leftover warnings.

## Pipeline
1. **Watch** (`gemini.watch_video`): the public YouTube URL goes straight to Gemini as `file_data`
   with structured JSON output: steps with MM:SS bounds, titles, instructions, the code written,
   draft checks, targets, explanation timestamps, hint ladder, common mistakes, library versions.
2. **Detail** (`gemini.step_detail`, opt-in `detail=True` / `--detail`): each step is re-sent clipped with
   `start_offset`/`end_offset` at 2 fps so on-screen code is legible (default sampling is 1 fps). Costs one
   request per step, which the free tier (5/min, 20/day per model) can't afford; failures are non-fatal.
3. **Adapt** (`gemini.adapt_checks`, text only): rewrites checks/targets against the learner's workdir
   (`workdir.scan` finds files, `log_metric`/`::metric::` names, argparse flags).
4. **Validate**: jsonschema + `schema.lint`: regexes compile, screen patterns ≤ 80 chars, every screen metric
   check has a `metric_pattern` with `step`/`value` groups, `::metric::` names are actually printed, files
   exist or are new source files, `checks` only hold screen-gradable types, no `visual`, ≤6-word titles,
   ≥1 screen check per step. Problems are fed back to step 3 (3 attempts). Then `repair` moves misplaced
   file checks to `precision_checks`, drops what's still broken, falls back to a literal screen match of the
   step's target, and lists anything left in `build.warnings`. Metric checks on `::metric::` names the workdir
   really prints get the protocol `metric_pattern` filled in deterministically (`complete_metric_checks`).
5. **Cache**: `demo/cache/lessons/<hash>.json`, hash = (video id, normalized goal, workdir folder name,
   fingerprint of its file names + printed `::metric::` names), so the cache survives other laptops and
   learner edits but re-adapts when the project layout changes. A graph whose adapt pass failed comes
   back with `build.adapted=false` and a leading warning and is **not** cached. The video-only draft is cached in
   `demo/cache/lessons/raw/` so re-adapting to a new workdir costs one cheap text call.

Models: `LESSON_MODEL` (video pass, default `gemini-4-hydrogen`), `LESSON_FAST_MODEL`
(detail + adapt, default `gemini-3.8-flash`), then `LESSON_FALLBACK_MODELS` (default
`gemini-3.7-flash,gemini-3.6-flash,gemini-3.5-flash`) when a model is overloaded (503), out of daily quota
or gone (404). Per-minute 429s wait for the server's retry delay (≤ 45 s). `build.adapted=false` means the adapt
pass never got through: checks come from the video draft; rerun with `readapt=True` / `--readapt` (reuses the
cached video draft, costs only the adapt calls). Key: `GEMINI_API_KEY` in `.env` at the repo root
(or the main checkout root when running from a worktree).

## CLI
```bash
python -m server.lesson "https://www.youtube.com/watch?v=AXXnSzmpyoI" \
  --goal "train a physics-informed neural network in PyTorch" \
  --workdir server/lesson/fixtures/diffusion_workdir \
  --report server/lesson/fixtures/toscano_pinn_part1.expected.json > graph.json
```
Graph → stdout, precision report → stderr. `--refresh` ignores all caches, `--readapt` redoes only the adapt
pass, `--detail` turns on step 2,
`--graph FILE` scores an existing graph.

## Precision report (`precision.py`)
Aligns generated steps to the hand-written ones by time IoU, then reports step P/R/F1, median
start/end error, check-type recall, **whether each generated `screen_contains`/`file_contains` regex
accepts the correct code** (`solution` per fixture step), regexes that already pass on `starter` code
(vacuous), **whether each `metric_pattern` parses real training output** (`sample_output`), the share of
screen-first checks, library recall and lint problems.

## Fixtures
- `fixtures/toscano_pinn_part1.expected.json`: expected graph for Juan Toscano's *Learning PIML Part 1:
  PINNs* (public, 24 min, PyTorch, 1D diffusion). Step bounds = the video's chapter marks.
- `fixtures/diffusion_workdir/pinn_diffusion.py`: a learner's finished code for that lesson (same
  structure as the tutorial notebook, logs `loss`/`test_loss` via `::metric::`; 2000 Adam steps ≈ 30 s on CPU,
  loss ≈ 3e-3).

Tests: `pytest server/lesson/tests` (Gemini faked; no key needed).

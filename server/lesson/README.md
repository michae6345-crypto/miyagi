# server/lesson: YouTube tutorial → step graph (E2)

```python
from server.lesson import build_lesson
graph = await build_lesson(url, goal="train a PINN on the convection equation", workdir="demo/pinn")
```

Returns a graph that validates against `shared/contracts/step-graph.schema.json` (plus an extra
top-level `build` object with the models used, timing and any leftover warnings).

## Pipeline
1. **Watch** (`gemini.watch_video`): the public YouTube URL goes straight to Gemini as `file_data`
   with structured JSON output: steps with MM:SS bounds, titles, instructions, the code written,
   draft checks, targets, explanation timestamps, hint ladder, common mistakes, library versions.
2. **Detail** (`gemini.step_detail`): each step is re-sent clipped with `start_offset`/`end_offset`
   at 2 fps so on-screen code is legible (default sampling is 1 fps). Runs 4 at a time; failures are non-fatal.
3. **Adapt** (`gemini.adapt_checks`, text only): rewrites checks/targets against the learner's workdir
   (`workdir.scan` finds files, `log_metric`/`::metric::` names, argparse flags).
4. **Validate**: jsonschema + `schema.lint` (regex compiles, metric is actually printed, file exists or
   is a new source file, no `visual`, ≤6-word titles, ≥1 check). Problems are fed back to step 3
   (3 attempts); checks still broken are dropped and listed in `build.warnings`.
5. **Cache**: `demo/cache/lessons/<hash>.json`, hash = (video id, normalized goal, workdir folder name),
   so the cache survives other laptops and learner edits. The video-only draft is cached in
   `demo/cache/lessons/raw/` so re-adapting to a new workdir costs one cheap text call.

Models: `LESSON_MODEL` (video pass, default `gemini-4-hydrogen`), `LESSON_FAST_MODEL`
(detail + adapt, default `gemini-3.8-flash`). Key: `GEMINI_API_KEY` in `.env` at the repo root
(or the main checkout root when running from a worktree).

## CLI
```bash
python -m server.lesson "https://www.youtube.com/watch?v=AXXnSzmpyoI" \
  --goal "train a physics-informed neural network in PyTorch" \
  --workdir server/lesson/fixtures/diffusion_workdir \
  --report server/lesson/fixtures/toscano_pinn_part1.expected.json > graph.json
```
Graph → stdout, precision report → stderr. `--refresh` ignores the cache, `--no-detail` skips step 2,
`--graph FILE` scores an existing graph.

## Precision report (`precision.py`)
Aligns generated steps to the hand-written ones by time IoU, then reports step P/R/F1, median
start/end error, check-type recall, **whether each generated `file_contains` regex accepts the
correct code** (`solution` per fixture step), regexes that already pass on `starter` code (vacuous),
library recall and lint problems.

## Fixtures
- `fixtures/toscano_pinn_part1.expected.json`: expected graph for Juan Toscano's *Learning PIML Part 1:
  PINNs* (public, 24 min, PyTorch, 1D diffusion). Step bounds = the video's chapter marks.
- `fixtures/diffusion_workdir/pinn_diffusion.py`: a learner's finished code for that lesson (same
  structure as the tutorial notebook, logs `loss`/`test_loss` via `::metric::`; 2000 Adam steps ≈ 30 s on CPU,
  loss ≈ 3e-3).

Tests: `pytest server/lesson/tests` (Gemini faked; no key needed).

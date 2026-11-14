# Stage-by-stage run on 4 non-PINN topics (2026-11-14, ~14:00, venue Wi-Fi)

`scripts/stage.py` drives the **LIVE** engine (DEMO=0, ORCH_AUTOSTART=0, own port) over the real WebSocket
protocol, one stage at a time, and prints what each stage did. Nothing in it calls a module directly.

```bash
.venv/bin/python scripts/stage.py search "pandas groupby tutorial"     # learn -> search.result* -> search.done
.venv/bin/python scripts/stage.py build 1 "pandas groupby tutorial"    # build_lesson(result #1) -> lesson.building* -> lesson.ready + step-graph outline
.venv/bin/python scripts/stage.py build https://www.youtube.com/watch?v=... "goal"   # learn_url
.venv/bin/python scripts/stage.py run                                   # live step.started / check.updated / spotlight / offtrack / card
.venv/bin/python scripts/stage.py run --seconds 60 --send hint --send "sleep 5" --send explain   # scripted actions
.venv/bin/python scripts/stage.py engine status|start|stop|log
```

- **Engine:** starts (or reuses) one on `--port` (default 8790) through `scripts/stage_engine.py`. That launcher has its own
  command line, so a `pkill -f server.orchestrator.main` aimed at the :8787 engine doesn't kill it. One did, mid-build, at 14:02.
- **Options:** `--no-screen` sets ORCH_SCREEN=0. `--workdir DIR` sets TUT_WORKDIR. `--env K=V` passes extra engine env, e.g. a
  different Gemini model. `--fresh` restarts the engine. `--open` sets ORCH_OPEN_WORKSPACE=1.
- **search** prints each `search.result` with its arrival time, kind, finder source, score, verified flag and reason. Then it prints
  the finder's **final** ranking from its cache file (after the Gemini "skim" of the top videos) and marks the rows whose score
  changed after the app already got them.
- **build** prints the progress ticks, then the full step graph. `lesson.ready` only has summaries, so the graph is read from the
  builder's cache file, or walked via `/debug/goto` + `/state`. The outline shows checks, precision checks, metric patterns, video
  ranges and workdir, plus the builder path (Gemini video / Claude transcript / cache) and a **PINN-leak scan** (pinn, convection,
  PDE, collocation, Latin-hypercube, exact_solution, IC/BC, the hero video ids, a `demo/pinn` workdir).
- **Logs:** every search/build appends a JSON record to `demo/runs/stage-results.jsonl`. The engine log is
  `demo/runs/stage-engine-<port>.log`. Both are gitignored.

## Results

Default config = what `scripts/miyagi-engine.sh` does today (TUT_WORKDIR = `demo/pinn-lab`, E2's default Gemini models).
"#1" = the finder's final rows[0] (its best video), which is what `stage build 1` sends as `resultIds`.

| topic | search: first / done | top 5 (finder final ranking) | picked | build (default config) | build (workaround: flash-lite models) | steps | checks machine-checkable? | PINN leakage |
|---|---|---|---|---|---|---|---|---|
| react useEffect cleanup | 3.4 s / 9.0 s, 28 rows | 1. Net Ninja "Full React Tutorial #24 - useEffect Cleanup" (96, video) · 2. learn-co react-hooks-use-effect-cleanup (95, repo) · 3. Codevolution "useEffect with cleanup" (94, video) · 4. "useEffect cleanUp functions" (93, video) · 5. dev.to cleanup guide (90, blog) | #1 Net Ninja (aKOQtGLT-Yk) | **OK 82.7 s**, Gemini watched (gemini-4-hydrogen), adapt gemini-3.6-flash (3.8/3.7 flash out of quota) | n/a | 5 | yes **only in the control run**: `screen_contains` regexes on Code (`new AbortController()`, `signal: abortCont.signal`, `err.name === 'AbortError'`) + Chrome console | **SEVERE**: step titles are React, but every instruction and check was rewritten for `pinn_diffusion.py` ("Import torch…", `def exact`, "Sample collocation points", `class PINN`, loss ≤ 1e-2). Engine workdir = `demo/pinn-lab` |
| git rebase interactive | 3.7 s / 11.7 s, 30 rows | 1. "Module 11: Interactive Rebasing (git rebase -i)…" (98, video, **0 views, uploaded 1 day ago**) · 2. "git interactive rebase - Undo, Edit & Squash" (98, video) · 3. dmuth/git-rebase-i-playground (95, repo) · 4. davidboothe/git-rebase-example (95, repo) · 5. "Git Rebase --interactive: EXPLAINED" (91, video) | #1 Module 11 (6r4eLCEIBHk) | **OK 56.9 s**, Gemini watched (gemini-4-hydrogen), adapt gemini-3.6-flash. The retry adapt hit 429 and the Claude fallback hit 400 (see F5) | n/a | 10 | yes, Terminal OCR regexes (`ref: refs/heads/main`, `tree [0-9a-f]{40}`, `Switched to branch '…'`, `HEAD@{n}:`). A few are weak: `\btrue\b`, and `screen_absent Traceback\|Error\|fatal:` on every step. **But no step is about `rebase -i`**: the lesson covers .git internals, stash, rerere, reflog and plumbing (steps stop at 8:34 of a 13:08 video) | workdir only (`demo/pinn-lab`). The builder's validator asked for a loss metric check because the PINN workdir prints `loss` |
| pandas groupby tutorial | 1st try 3.7 s / 5.3 s, 19 rows, **0 videos**. Retry 3.6 s / 18.3 s, 30 rows | 1. "Mastering Pandas .groupby() in 10 Minutes!" (95, video) · 2. learn-co dsc-pandas-groupby (95, notebook) · 3. QuantEcon groupby.ipynb Colab (95) · 4. GroupBy-Operations.ipynb Colab (95) · 5. realpython pandas-groupby (95, blog) | #1 (_zsKKcnX-qE) | **FAILED 3.2 s**: `gemini-4-hydrogen` 429 daily quota, fallback models already marked exhausted, Claude transcript path: YouTube blocks youtube-transcript-api from this IP, Bright Data unlocker zone not set | **OK 55.5 s**, video gemini-3.5-flash-lite, adapt gemini-3.1-flash-lite | 10 | yes, but brittle: exact-code regexes like `df\.groupby\("Department"\)\["Salary"\]\.mean\(\)` and `.mean\(\)\.sort_values\(ascending=True\)` fail on single quotes or a different column name. No output check | workdir only (`demo/pinn-lab`). Precision check s1p1 reported "groupby.ipynb not found" because it looked in pinn-lab. The adapt pass retried 3× for the PINN workdir's "no metric check" |
| train a diffusion model in pytorch | 2.4 s / 16.7 s, 37 rows | 1. "Coding a Diffusion Model From Scratch in PyTorch (DDPM)" (98, video) · 2. lucidrains/denoising-diffusion-pytorch (95, repo) · 3. HF diffusers basic_training.ipynb (95) · 4. HF "Train a diffusion model" (95, blog) · 5. Jackson-Kang/Pytorch-Diffusion-Model-Tutorial (95, repo) | #1 (TgTQE_muXec) | **FAILED 2.1 s**: `Gemini call failed on []: None` (every model already marked exhausted in-process) + same transcript block | **OK 43.8 s**, video + adapt gemini-3.1-flash-lite | 4 | weak: 4 steps cover 0:16–9:45 of a 28-min video. **No training step and no loss metric check**, although the goal is "train". Checks: `import torch`, `BETA_START = 1e-4`, `def q_sample`, `DataLoader(train_set`; precision `EPOCHS\s*=\s*20` | **SEVERE**: the DDPM lesson was rewritten into the PINN code: "Import torch, numpy, and the **Latin-hypercube** sampler in **pinn_diffusion.py**", `def exact_solution`, "training data for **initial and boundary conditions**", `boundary_points`. No PINN leak in search |

**Control run** (`--workdir <empty dir>`, flash-lite models, same cached video drafts, adapt pass only):
- react: 4.5 s, all 5 steps are clean React/AbortController steps.
- diffusion: 2.4 s, 4 clean DDPM steps (`ddpm_mnist.ipynb`, `q_sample`, MNIST DataLoader).

**The PINN leak comes entirely from the workdir the orchestrator hands to the builder.**

**`stage run` (gate + coach)** on the DDPM lesson, no screen reader, so the precision checks are graded:
- `hint` and `explain` returned real coach cards in 1–3 s.
- `ask "why does the fetch need an abort signal?"` got a correct answer that flags the question as off-step.
- Creating `ddpm_mnist.ipynb`: `check pass` → `step.passed s1 → s2` → `step.started s2`, all within 0.4 s.
- Saving `EPOCHS = 10`: `check fail` → `status thinking` → `offtrack [warn] "Not yet: Hyperparameters in file"` 11 s later. The card is
  a generic playbook card (file-only failures use no model), so it doesn't say "20, not 10".

### Per stage

| stage | verdict | owner |
|---|---|---|
| search (finder) | **works, ~2.5–3.7 s to first row, 5–18 s done**; streamed order and scores aren't the final ranking (F3); one run returned 0 videos and cached that (F4); ranks a 0-view day-old video first (F7) | E7 finder (+ E4 for F3) |
| search → build handoff | **broken for default picks**: `build_lesson` with no ids picks the first *streamed* row, which was a repo/blog/notebook in 3 of 4 topics (F3) | E4 orchestrator |
| build (lesson) | **works when Gemini has quota (44–83 s)**, otherwise **dead**: no flash-lite in the default chain, the Claude transcript fallback is blocked by YouTube, and the Claude adapt fallback 400s (F2, F5, F6) | E2 lesson |
| build: workdir | **broken for any non-PINN topic**: every lesson gets `demo/pinn-lab` as its workdir, and the adapt pass rewrites the checks for the PINN code (F1) | E4 orchestrator (root cause) + E2 lesson (should reject an unrelated workdir) |
| checks | machine-checkable for react / git / pandas (screen regexes on Code/Terminal/Chrome), but often over-literal (F8); diffusion had no metric check (F8) | E2 lesson (check authoring), E3 checks |
| gate + coach | **works** (pass → advance in < 0.5 s; fail → offtrack in ~11 s; hint/explain/answer cards live) | E4 / E5 |

## Failures

### F1 · E4 orchestrator (root cause) + E2 lesson: every lesson is adapted to the PINN workdir — SEVERE
- **Symptom:** for "react useEffect cleanup" and "train a diffusion model in pytorch", the video's step titles are right, but the
  instructions and checks are rewritten for `pinn_diffusion.py` (collocation points, Latin hypercube, `exact_solution`, IC/BC,
  `class PINN`, loss ≤ 1e-2). git and pandas kept their content, but their engine workdir is still `demo/pinn-lab`: the file watcher,
  the precision checks ("groupby.ipynb not found") and VS Code all point at the PINN folder.
- **Where:** `server/orchestrator/session.py:_build`:
  `graph = await self.m.build_lesson(url, goal, str(config.default_workdir()))`. `config.default_workdir()` = TUT_WORKDIR, else
  `demo/pinn-lab`, and `scripts/miyagi-engine.sh` exports `TUT_WORKDIR=$ROOT/demo/pinn-lab`. `load_graph` then uses
  `resolve_workdir()`, where TUT_WORKDIR beats `lesson.workdir`. The builder's `scan(workdir)` feeds `pinn_diffusion.py` into the
  adapt prompt, and its validator demands a metric check because that workdir prints `loss` (3 adapt retries per build, which burns quota).
- **Proof:** the same cached video drafts, adapted against an empty workdir, give clean lessons (react 5 steps, DDPM 4 steps, zero leaks).
- **Fix (E4):** when a lesson is launched from `learn` / `learn_url`, don't pass the hero workdir. Pass a fresh per-topic folder
  (e.g. `~/miyagi/<slug>` or `demo/work/<lesson-slug>`, empty or created by the step-0 instructions). Keep TUT_WORKDIR only for the
  autostarted hero lesson, or only when the user explicitly picked a folder.
- **Fix (E2):** in the adapt pass, if the workdir's files and libraries don't match the video's topic and libraries (e.g. the video
  uses react but the workdir is torch-only), ignore the workdir contents (treat it as empty) and add a build warning. Don't demand
  a metric check just because the workdir prints `loss`.

### F2 · E2 lesson: the build dies once the free-tier Gemini models are out of quota (pandas, diffusion)
- **Exact errors:**
  - pandas: `Could not build the lesson: lesson.build_lesson failed: RuntimeError: no engine could build the lesson: gemini: Gemini call failed on ['gemini-4-hydrogen']: 429 RESOURCE_EXHAUSTED … claude: no transcript for _zsKKcnX-qE: brightdata: BRIGHTDATA_API_KEY/BRIGHTDATA_UNLOCKER_ZONE not set; youtube-transcript-api: Could not retrieve a transcript … YouTube is blocking requests from your IP.`
  - diffusion, one minute later in the same process: `gemini: Gemini call failed on []: None` (3.8/3.7/3.6/3.5-flash were already in the in-process `_exhausted` set).
- **Workaround that worked (env only, no code change):**
  `LESSON_MODEL=gemini-3.1-flash-lite LESSON_FAST_MODEL=gemini-3.1-flash-lite LESSON_FALLBACK_MODELS=gemini-3.5-flash-lite`.
  Pandas then built in 55 s and diffusion in 44 s. The lite model's lessons are thinner (DDPM: 4 steps, no training step).
- **Fix:**
  - Append `gemini-3.1-flash-lite,gemini-3.5-flash-lite` to the default `LESSON_FALLBACK_MODELS`. The video pass then degrades
    instead of dying.
  - Make the error say "all Gemini models out of daily quota" instead of `failed on []: None`.
  - For the transcript path without Bright Data, fetch the caption track's `baseUrl` (`&fmt=json3`) from the watch page's
    `captionTracks` with plain httpx before trying youtube-transcript-api, which is IP-blocked here.
  - Longer term: a paid Gemini key for the demo.

### F3 · E4 orchestrator (+ E7): the app never gets the finder's final ranking; the default pick is the first streamed row
- **Symptoms:**
  - In 3 of 4 topics the first streamed `search.result` was a repo, blog or notebook (react: `lukakobal/React-84-useEffect-cleanup`;
    pandas: a blog, then a learn-co notebook on the retry; diffusion: `lucidrains/denoising-diffusion-pytorch`). Only git led with a video.
  - `session.build_lesson([])` falls back to `next(iter(self.results.values()))`, the first streamed row, and that would fail with
    `only YouTube sources are supported`.
  - The deep pass's re-scores never reach the app. git: the app saw 95/80/80 for the videos the finder finally scored 98/98/91;
    pandas: 43 → 98. That's because the orchestrator doesn't pass `emit_updates=True` and dedups on `id`.
  - `search.done` carries no order.
- **Fix (E4):**
  - Pass `emit_updates=True` and re-emit an updated row (same id) instead of dropping it.
  - Remember the finder's returned list. When no `resultIds` are given, use `final[0]` (always a video per E7's contract), or
    the first `kind == "video"` row.
  - Optionally add `ranked: [ids]` to `search.done`, a contract-safe new field.
- **(E7):** the README says "the first batch waits for the YouTube results so the UI leads with videos", but GitHub rows still
  arrive first (3.4 s, same timestamp as the YouTube rows).

### F4 · E7 finder: a search with 0 videos was cached for 7 days (pandas, 1st try)
- **Symptom:**
  - "pandas groupby tutorial" returned 19 rows (blogs and notebooks) and **0 videos**. `providers` lists `youtube` and no note
    explains it.
  - The cache file (`demo/cache/search/pandas-groupby-tutorial-*.json`, copy in `demo/runs/pandas-novideo-search.json` locally)
    then served the same 0-video list to every repeat search.
  - The same query, run standalone with `--no-cache` a minute later, found 10 + 1 videos, and so did the engine after I deleted
    the cache file.
- **Fix:**
  - Never cache a result set with no `kind == "video"` row.
  - When the YouTube provider returns 0 videos, add a note and retry once (e.g. with the topic variant).
  - Treat "no video" as a failure, because rows[0] must be a video.

### F5 · E2 lesson: the Claude fallback for the adapt pass always 400s
- **Exact error:** `adapt pass failed (attempt 2): … claude: Claude call failed (400): … 'invalid_request_error', 'message': 'Schemas contains too many optional parameters (26), which would make grammar compil…'`
- **Effect:** once the Gemini flash models are out of quota, there is no adapt fallback. The git lesson shipped attempt 1's graph
  with a validator problem left in.
- **Fix:** simplify the structured-output schema used by `claude.adapt_checks`. Make fields required and nullable instead of
  optional, or split per-check-type schemas, or drop strict tool schema and validate in Python.

### F6 · E2 lesson / ops: daily Gemini quota disappears after ~2 lesson builds
- **Symptom:**
  - At 14:00 `gemini-3.8-flash` and `gemini-3.7-flash` were already exhausted. After the react and git builds,
    `gemini-3.6-flash`, `gemini-3.5-flash` and `gemini-4-hydrogen` were exhausted too.
  - Each build spends 1 video call plus 1–3 adapt calls. F1 adds 2 extra retries.
- **Fix:** F1 and F2 (the retries and the model chain), plus a paid key or several keys for the demo. Cache the demo lessons
  ahead of time.

### F7 · E7 finder: ranks a 0-view, 1-day-old video first, and its content doesn't match the title
- **Symptom:**
  - The git #1 pick, "Module 11: Interactive Rebasing (git rebase -i) & History Rewriting" (MasterTechTopics, 13:08, 0 views,
    1 day ago), got skim score 98.
  - The lesson Gemini built from it has **no `rebase -i` step**: it covers .git internals, stash, rerere, reflog and plumbing.
    Either the video doesn't teach it, or the builder stopped at 8:34 of 13:08.
- **Fix (E7):**
  - Penalize view count < ~100 and age < ~1 week in triage.
  - Have the skim prompt check that the *goal's key action* (here `git rebase -i`) is actually performed on screen, not just
    named in the title.
- **(E2):** add a build warning when the steps cover < 70 % of the video, or when no step mentions the goal's key term.

### F8 · E2 lesson (check authoring): checks are machine-checkable but over-literal; "train" goals get no metric check
- **Over-literal patterns:**
  - pandas: `df\.groupby\("Department"\)\["Salary"\]\.mean\(\)` fails on single quotes or a renamed column.
  - pandas: `\.mean\(\)\.sort_values\(ascending=True\)` requires an argument that is the default anyway.
  - DDPM: `EPOCHS\s*=\s*20` hard-codes the video's value.
- **Too generic:**
  - git: `\btrue\b` on the Terminal.
  - `screen_absent Traceback|Error|fatal:` on 6 of 10 git steps, which stays red after any old error on screen.
- **DDPM:** with flash-lite the lesson has no training step and no `metric_*` check for "train a diffusion model".
- **Fix:**
  - Prompt and validate for quote-agnostic, structure-level patterns (`groupby\(\s*\[?['"]`), and for no hard-coded
    hyperparameter values unless the step is "set X to Y".
  - Require a metric check whenever the goal contains train/fit, using the video's own logging.
  - Scope `screen_absent` error checks to new output (E3: only lines that appeared during this step).

### F9 · E4 orchestrator / contract: `learn_url` has no goal
- **Symptom:** `learn_url {url}` builds with `goal = self.query`, the last `learn` query or `""`. A pasted link after a different
  search gets the wrong goal, which drives step framing and the goal-keyed cache.
- **Fix:** add an optional `goal` to `learn_url` (additive contract change). Otherwise reset `self.query` on `learn_url` and let
  E2 derive the goal from the video title.

### F10 · infra: the stage engine was killed mid-build by an external `pkill`
- **Symptom:** at 14:02:35 the :8790 engine got a clean uvicorn "Shutting down" during the git build. The cause wasn't stage.py:
  the matching pattern was `server.orchestrator.main`. stage.py now launches through `scripts/stage_engine.py`.
- **Suggestion to all sessions:** kill by port (`lsof -ti tcp:8787 | xargs kill`) instead of `pkill -f`.

### Minor
- **E6 screen:** with the display asleep, the screen reader logs a full traceback every second
  (`ScreenUnavailableError: display returned no image (asleep, locked, or switching Spaces?)`). Log it once per state change.
- **E4:** `diagrams: missing` in `/health` (no `server.diagrams` module on integration/live). The `diagram` action errors in LIVE: `diagram: server.diagrams.build isn't available yet` (verified with `stage run --send diagram`).
- **E7:** Bright Data is still inactive (`zone "serp_api1" not found`, `zone "web_unlocker1" not found`), and Gemini Search
  grounding returns 429 on every search. Both are noted per search, and the finder falls back fine.
- **E5:** the offtrack card for a file-only failure is generic ("Define T, BETA_START, … EPOCHS"). It could quote the failing
  check's expected value (`EPOCHS = 20`).

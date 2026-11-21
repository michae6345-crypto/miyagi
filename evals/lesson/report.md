# Lesson builder on 5 non-PINN tutorials

Run on **2026-11-14 at 13:58 PST**, live with no cache (`build_lesson(..., cache=False)`), using E2's branch tip
`claude/michael-lesson-135f28@47dba31` ("Gemini only watches (45 s cap), Claude does the rest; per-stack checks").
`server/lesson` was overlaid on `integration/live@2cc33e8`.
Each video got a fresh empty workdir, i.e. a learner starting from scratch. Engine `auto`.
Re-run: `python evals/lesson/run.py --src <checkout>`. Raw graphs are in `results/<id>.json`, automatic grades in `results/grades.json`,
build logs in `results/<id>.log` (gitignored; per-pass timings are quoted below). Transcripts were used for spot checks but are not committed.

## Latest (`dec3653`): Gemini billing returns 402; localhost fix verified

Runs (both with `--saved-captions`):
- `results-dec3653-default/`: all 5 with defaults.
- `results-dec3653-claude/`: fastapi-rest and pandas-30min only, `LESSON_ENGINE=claude`.

- **Gemini's billing has stopped working: every Gemini call returns `HTTP 402 Payment Required`**, on both `gemini-4-hydrogen` and `gemini-3.7-flash`. Billing on the key needs fixing (out of credit or turned off); this is ops, not E2.
- **The builder doesn't fail fast on 402.** `gemini._classify` treats it as a temporary error, so `auto` keeps retrying until the 75 s cap before using Claude's draft (which was ready at ~15 s).
  - Every default build took 82–90 s instead of ~30 s, and all five ended up Claude-built.
  - The progressive pandas build took **191 s**, and its first part was ready only after 65.5 s.
  - Fix: classify 402 like 401/403 (fatal for the whole process, as `auth`) so the race takes Claude's draft immediately. Report "Gemini billing: 402" in the build's human-readable error.
- **The localhost fix works.** FastAPI s1 now ends "…and open http://127.0.0.1:8000." on both paths (the URL sits right before the period), and there are no link warnings.
- **The progressive step budget is untested on Gemini** because of the 402. The Claude-built progressive pandas has 11 steps (was 19) over 4/4 parts; Claude single-pass has 8.

## Run on `4ceb5de`: localhost/link fixes, vague-setup lint, progressive long videos

Two runs, one after the other, both with `--saved-captions`:
- `results-4ceb5de-default/`: defaults, Gemini preferred.
- `results-4ceb5de-claude/`: `LESSON_ENGINE=claude`.

| Lesson | Default: builtBy, total | Claude only: total | Score default / Claude | Checks default / Claude | goalMatch |
|---|---|---|---|---|---|
| react-useeffect | gemini, 49 s | 35 s | 8.5 / 9 | 20 / 28 | 0.95 |
| git-rebase | gemini, 57 s | 24 s | 8 / 8 | 11 / 15 | 0.95 |
| pandas-30min | gemini, 62 s, **first part ready in 19.8 s**, 4/4 parts done | 34 s | 8.5 / 9 | 51 (19 steps) / 37 (9 steps) | 0.88 / 0.85 |
| rust-cli | gemini, 48 s | 30 s | 9 / 9 | 38 / 45 | 0.85 |
| fastapi-rest | gemini, 65 s | 29 s | 9 / **8.5** | 29 / 34 | 0.95 |

**What the fixes did:**
- **Gemini's git setup is back, and it works.** `step.code` has a full script. I ran it in a temp folder: it builds `main` and `feature/login` from the same base, and `git rebase main` stops at "CONFLICT (content): Merge conflict in index.js", as the lesson expects.
- **Per-stack error text now covers steps without a run command.** There are no Python `Traceback` checks in React on either path.
- **Gemini FastAPI instructions read cleanly.** Its localhost mentions survive, and every lesson-visible URL resolves (only the PanadasTutorial repo, 200).
- **Progressive build works.** pandas (30:36) is split into 4 parts by chapter, and the first steps are playable after 19.8 s instead of after the whole build.
- `lesson.goalMatch` looks sensible: 0.85–0.95 for all five.

**Still wrong:**
1. **A localhost URL at the end of a sentence is still stripped** (`links._checkable`).
   - Claude FastAPI s1 now ends "Start it with `uvicorn main:app --reload` and **open .**", and build.warnings says "removed a link that does not resolve (http://127.0.0.1:8000)".
   - Cause: `_LOCAL.match(u)` runs on the raw match `http://127.0.0.1:8000.`, trailing period included, so `(:\d+)?(/|$)` fails. The period is only removed afterwards by `rstrip`.
   - Reproduced: `_checkable('open http://127.0.0.1:8000.')` returns `{'http://127.0.0.1:8000'}`. The same URL followed by " in your browser" or "/docs." is correctly ignored.
   - Fix: `rstrip(".,;:!?")` before testing `_LOCAL`.
2. **Splitting long videos doubles the step count.** pandas went from 9 steps to 19. Some are 29–40 s micro-steps (s2 "Import pandas", s14 "Delete a row", s16–s18 count / group / sort as three steps). Each passes the 20 s merge rule, but 19 steps for a 30-min video is a lot of pausing. Consider merging adjacent steps across part boundaries, or a per-part step budget.
3. **Gemini checks are still thinner** (11–38 vs 15–45 per lesson). E2 says this isn't done yet.

## Run on `e721457`: link verification, Claude concurrency cap and 429 backoff

Two runs, one after the other, both with `--saved-captions`:
- `results-e721457-default/`: defaults, which now prefer Gemini.
- `results-e721457-claude/`: `LESSON_ENGINE=claude`.

| Lesson | Default: builtBy, total (Gemini pass) | Claude only: total | Score default / Claude | Checks (per step) default / Claude |
|---|---|---|---|---|
| react-useeffect | gemini, 47 s (36 s) | 29 s | 8.5 / 8.5 | 20 (1–4) / 25 (2–6) |
| git-rebase | gemini, 45 s (38 s) | 21 s | **6.5** / 8 | 14 (2–3) / 17 (3–4) |
| pandas-30min | gemini, 65 s (54 s) | 34 s | 9 / 9 | 29 (2–5) / 38 (2–7) |
| rust-cli | gemini, 45 s (36 s) | 28 s | 9 / 9 | 29 (2–5) / 42 (5–6) |
| fastapi-rest | gemini, 54 s (40 s) | 24 s | **7.5** / 8.5 | 26 (2–4) / 33 (3–5) |

**What works:**
- `lesson.builtBy` is set correctly on every graph.
- No 429s at all, even with 5 builds in parallel. The concurrency cap and backoff work.
- Gemini builds are faster than at 6573187 (45–65 s, was 46–94 s), and Claude-only is 21–34 s.
- No made-up links. My grader's URL check finds only the real PanadasTutorial repo (200).

**New problems, ranked:**
1. **Regression: the link checker strips the learner's own localhost URLs and leaves broken sentences** (`links.py`).
   - FastAPI on Gemini, s1: "Run the server with `uvicorn main:app --reload` and **openin your browser**."
   - FastAPI on Gemini, s2: "From a second terminal, run **`curl -X POST ''`** to add an item."
   - On the Claude path it silently dropped the FastAPI hints that contained `http://127.0.0.1:8000/...`.
   - The learner's dev server is never up at build time, so `localhost`, `127.0.0.1`, `0.0.0.0`, `[::1]` and `*.localhost` must be exempt. Never cut a URL out of a backticked command; drop the whole sentence or keep it.
2. **Gemini's git step 1 is vague again.**
   - It says: "Initialize a git repo with a main branch and a local feature branch (e.g. feature/login) whose commits change index.js and package.json differently from main". `step.code` is empty and there are no commands, so the learner has to design the conflicting history themselves.
   - The setup lint only fires on clone/download/get/put wording, so "initialize" slipped through. At 6573187 the same lesson had a working setup script; this varies run to run.
   - Fixes: require a backticked command or `code` in any step-1 setup that creates state. Or, simpler, reuse the Claude draft's step-1 setup, which is computed in parallel anyway and gave exact commands in every Claude run.
3. **Python `Traceback` in React on the Claude path.** s3, s4 and s7 have `screen_absent Terminal 'Traceback|Error:|ERR!'`. These steps have no `run_command`, so the per-stack swap seems to key off the run command. Key it off the lesson's stack (libraries/files) instead.
4. **Gemini checks are still thinner:** 14–29 per lesson against 17–42, and Gemini React s4 has a single check.
   - The adapt pass only sees Gemini's draft for those steps. Give it the Claude draft's code and checks for the overlapping time range as extra context; that draft is already computed in parallel.

## Gemini is the default (`6573187`): both paths compared

E2 changed four things:
- `auto` now waits up to 75 s for Gemini.
- Gemini gets the title, length, chapters and description.
- New lints for setup steps and for steps that repeat the previous step's checks.
- Notebook steps get a run step.

I ran each path on its own, one after the other, to avoid the 429 contention from last time:
- `results-6573187-default/`: defaults, no env overrides.
- `results-6573187-claude/`: `LESSON_ENGINE=claude`.

Both used `--saved-captions` for the Claude transcript. The grader now also **fetches every URL a lesson tells the learner to visit** (`grade.py: _url_status`).

| Lesson | Default: winner, total (Gemini pass) | Claude only: total (Claude pass) | Score default / Claude | Checks | Real-output matches | URLs (status) |
|---|---|---|---|---|---|---|
| react-useeffect | **Gemini**, 46 s (36 s) | 56 s (22 s) | 8.5 / 8.5 | 18 / 25 | 2/2 / 3/6 | – |
| git-rebase | **Gemini**, 48 s (41 s) | 22 s (15 s) | 8 / 8 | 14 / 15 | 9/12 / 9/13 | – |
| pandas-30min | **Gemini**, 94 s (67 s) | 63 s (27 s) | 9 / 9 | 32 / 37 | 4/4 / 2/2 | PanadasTutorial repo: 200 / 200 |
| rust-cli | **Gemini**, 65 s (57 s) | 30 s (19 s) | 9 / 9 | 38 / 49 | 11/19 / 19/27 | – |
| fastapi-rest | **Gemini**, 55 s (43 s) | 26 s (14 s) | 9 / 9 | 24 / 33 | 8/10 / 16/17 | – |

- **The default now uses Gemini 5/5**, with no env overrides. Claude's draft was still computed in parallel and went unused.
- **Gemini lessons now match Claude's scores.** Last time Gemini scored git 5 and pandas 7.5; now it is 8 and 9.
  - pandas step 1 links the real dataset repo from the description (HTTP 200).
  - git step 1 has a full setup script in the step's `code`. **I ran it in a temp folder:** it builds `main` and `feature/login` from the same base, and `git rebase main` then hits a conflict on `index.js`, applies the empty middle commit cleanly, and conflicts again on `package.json`. That is exactly the video's sequence.
  - No made-up URLs, and no demo literals in the screen checks (`DEFAULT_USER`, `/login`).
- **Gemini lessons are still slower and a bit thinner.** They take 46–94 s against 22–63 s for Claude-only, and have 18–38 checks against 25–49.
  - pandas is the slow one: a 67 s Gemini pass plus three adapt rounds of ~9 s.
  - "fast mode unavailable (429)" fallbacks showed up even with one eval run at a time (5 builds in parallel), which slows the adapt rounds.

**Verdict: yes, the Gemini path is good enough to be the default**, and it now is. A Gemini-watched lesson scores level with the Claude path on all five stacks, with step timing at least as accurate, and nothing it tells the learner to visit is made up.

The cost is about 45–95 s per new lesson, against ~25–60 s on Claude. For the demo, pre-build the hero lesson into the cache and show the build progress for live builds.

**Small remaining items:**
1. **Show the setup script.** Gemini git step 1 says "run the setup command" and the command exists only in `step.code`. The app must show `code` for setup steps, or the builder should inline it as a backticked block in the instructions.
2. **Handle Claude 429s.** Retry with backoff, cap concurrent Claude calls, and give Gemini its full timeout once Claude has failed (from the sixth run). Status unknown, and the 429 fast-mode fallbacks still appear.
3. **Gemini checks are thinner** than Claude's. Still fine at this level, but the second-pass check density (React s6–s8) is worth a look.

## Sixth run (`4fd6ed8`): parallel adapt batches, per-stack error text, explicit prerequisites

Two runs on this commit:
- `results-4fd6ed8-race/`: default `auto` race. Rust, FastAPI and pandas were re-run on their own after the first attempt hit a Claude 429.
- `results-4fd6ed8-gemfirst/`: `LESSON_GEMINI_TIMEOUT=75 LESSON_GEMINI_GRACE=60`.

Both used `--saved-captions`, since YouTube still blocks caption requests from this machine.

| Lesson | Default race: total (e2582e8) | Video pass + adapt rounds | Gemini-first: total, winner |
|---|---|---|---|
| react-useeffect | **36 s** (50 s) | Claude 13.5 s; adapt 5.0 + 5.1 + 4.5 s | 58 s, Gemini (48 s pass) |
| git-rebase | **29 s** (30 s) | Claude 13.9 s; adapt 3.8 + 2.9 s | 50 s, Gemini (40 s) |
| pandas-30min | **35 s** (42 s) | Claude 14.6 s; adapt 4.9 + 4.4 + 3.2 s | 64 s, Gemini (38 s) |
| rust-cli | **37 s** (47 s) | Claude 15.6 s; adapt **5.8** (was 33.6) + 5.4 + 2.6 s | 80 s, Gemini (54 s) |
| fastapi-rest | **34 s** (76 s) | Claude 14.5 s; adapt 5.0 + 4.6 + 2.1 s | 62 s, Gemini (41 s) |

Gemini-first times are inflated by the rate-limit contention described below.

**What the fixes did:**
- **Parallel adapt batches work.** Round 1 takes 3.8–5.8 s for every lesson. The default race now builds any of the five in 29–37 s, the fastest of all runs, with 0 leftover warnings.
- **Per-stack error text works.** React uses `ERR!|Error:|error\s+TS\d+`, Rust uses `error\[E\d+\]`, git uses `fatal:`, and the Python stacks keep `Traceback`.
- **Prerequisites are better on the Claude path.** git s3 says "create `feature/login` from main with three commits, where the first and third change the same line of `app.txt` that two new main commits also change". There are no demo literals.

**New findings:**
1. **Gemini made up a URL.** The Gemini-first git step 1 says "Clone https://github.com/philomatics/git-rebase-example (or init a repo where …)". **That URL returns 404.** The channel's GitHub user exists, but the repo doesn't, and the video description links no repo. Every URL in a lesson must come from the description/transcript or be checked live; otherwise drop it.
2. **A Claude 429 can sink a build.** My first default race ran 10 builds at once (two eval runs in parallel) and hit "Number of concurrent requests" 429s. The Claude video pass failed outright with no backoff, and with Gemini still under its 45 s cap, **rust-cli and fastapi-rest failed on both engines**. A single demo build won't hit this, but the parallel fan-out (segmentation + per-step detail + adapt batches) multiplies concurrent requests.
   - Fixes: retry 429s with backoff and cap concurrent Claude calls; and when Claude has failed, let Gemini run to its full timeout instead of 45 s.
3. **The default race still never picks Gemini.** Unchanged since e2582e8: Claude wins 5/5 under the defaults. The Gemini-first env settings won 5/5 again.

**Scores:**
- Default race (Claude): React 9, git 8, pandas 9, Rust 9, FastAPI 9.
- Gemini-first: React 8, git **5** (made-up clone URL), pandas 7.5 (still no dataset link), Rust 9, FastAPI 9.

## Gemini path vs Claude path (`e2582e8`, Gemini paid tier)

Gemini billing is on now, so `gemini-4-hydrogen` answers. Four runs on the same code (`e2582e8`) with default models:

| Folder | Setup | What it shows |
|---|---|---|
| `results-e2582e8-race/` | default `auto` race, `--saved-captions` | what the demo does today |
| `results-e2582e8-gemini45/` | `LESSON_ENGINE=gemini`, default 45 s cap | **4/5 fail** with "no answer within 45s"; only git (9:44) finishes |
| `results-e2582e8-gemini300/` | `LESSON_ENGINE=gemini`, cap raised to 300 s | Gemini's real speed and quality |
| `results-e2582e8-race-gemfirst/` | `auto`, `LESSON_GEMINI_TIMEOUT=75`, `LESSON_GEMINI_GRACE=60`, `--saved-captions` | a race that prefers Gemini |

In every Gemini run the adapt pass (writing checks for the learner's workdir) is Claude, as designed.

### Per-stage timing and race winner

| Lesson | Claude video pass | Gemini video pass | Total, default race (winner) | Total, Gemini-first race (winner) | Total, Gemini only |
|---|---|---|---|---|---|
| react-useeffect (19:51) | 16.0 s | 44.1 s / 40.0 s | 50.0 s (**Claude**) | 53.9 s (**Gemini**) | 63.3 s |
| git-rebase (9:44) | 13.1 s | 35.4 s / 33.8 s | 30.4 s (**Claude**) | 41.7 s (**Gemini**) | 42.9 s |
| pandas-30min (30:36) | 13.0 s | 54.6 s / 58.3 s | 41.7 s (**Claude**) | 73.8 s (**Gemini**) | 67.0 s |
| rust-cli (28:09) | 22.9 s | 50.3 s / 45.8 s | 47.1 s (**Claude**) | 74.0 s (**Gemini**) | 61.4 s |
| fastapi-rest (15:16) | 20.9 s | 53.3 s / 41.4 s | 75.5 s (**Claude**) | 57.0 s (**Gemini**) | 70.5 s |

- **With today's defaults, Gemini never wins: 0/5.** Claude's draft is ready at 13–23 s and Gemini then gets only 8 s more. Gemini on 0.5 fps needs 34–58 s.
- **With `LESSON_GEMINI_TIMEOUT=75 LESSON_GEMINI_GRACE=60`, Gemini wins 5/5.** Total time is 42–74 s, against 30–76 s for the Claude-won race, and Claude's draft is still computed in parallel as a fallback.
- Each adapt pass adds 7–20 s on either path.

### Quality, side by side

Scores are my manual read: Claude = default race; Gemini = the Gemini-only run, with the Gemini-first race read for git and pandas.

| Lesson | Score Claude / Gemini | Checks | Real-output matches | Step starts vs chapter marks (median, within 10 s) | Notes |
|---|---|---|---|---|---|
| react | 8.5 / 8 | 32 / 19 | 8/10 / 2/2 | 0 s, 8/9 / 1 s, 8/9 | Gemini: s3 repeats s2's checks with no `[]` check, so s3 passes immediately. s7/s8 have one check each. |
| git | 8 / **5.5** | 15 / 14 | 10/14 / 6/11 | 25 s / 41 s (covers only the hands-on part) | Gemini, **in both Gemini runs**: step 1 says "Clone the example repository", but the video links no repo. It brings back `DEFAULT_USER\s*=` and `app\.post\(.{0,2}/login`. Claude: step 1 gives commands to rebuild the repo. |
| pandas | 9 / 7.5 | 33 / 18 | 3/3 / 4/4 | 0 s, 5/8 / 1 s, 6/9 | Gemini: says "Put orders.csv from the tutorial repository" with **no URL** (Claude gives the link from the description). s3 has an alternative `…\|print\(df\)` that passes on code. s7–s9 have no output check. |
| rust | 9 / 9 | 41 / 30 | 14/23 / 5/13 | no chapters; same starts ±2 s | Gemini reads exact versions off the screen (owo-colors 4.2.1, tabled 0.20.0, chrono 0.4.41) and the real project name `bestls`. |
| fastapi | 9 / 9 | 34 / 22 | 16/18 / 9/10 | **15 s**, 4/8 / **1 s**, 5/9 | Gemini timestamps are much closer to the chapters. It reads the on-screen pins (fastapi 0.94.0, pydantic 1.10.5) and adds an install step. |

**What Gemini does better:**
- Step boundaries are as good or better: median 1 s from the chapter marks, against up to 15 s for the transcript path.
- It reads what is only on screen: exact versions, project and file names.
- It covers the video more fully: 77–82 % against 71–81 %.

**What Gemini does worse:**
- **It can't see the video description**, so the setup step can't include the dataset or repo link (pandas), and it invents a repo to clone when there isn't one (git).
- It copies demo literals visible on screen into the checks, which the adapt pass doesn't fully remove (git s3).
- Its checks are thinner, about 40 % fewer per lesson. Notebook steps get no `run_command`, so the output-check rule never fires (pandas s7–s9).

### Verdict: is the Gemini path good enough to be the default?

**Yes, for code-on-screen tutorials like the demo, once the race is set to prefer Gemini.**
- React, Rust and FastAPI score 8–9 on Gemini. That is level with Claude, with better timestamps and on-screen details, in 54–74 s.
- **With today's defaults, the demo will never use Gemini**, even with billing on, because Claude always finishes first.
- The minimum change is `LESSON_GEMINI_TIMEOUT=75 LESSON_GEMINI_GRACE=60`, measured above: Gemini won 5/5.

**Not yet for arbitrary tutorials whose starting state is off camera.** git and pandas drop to 5.5 and 7.5 because Gemini never sees the description, and a "clone the example repository" step with no repo can't be followed. Fixes 2–3 below close that gap.

### Fixes, ranked (sent to E2)
1. **Make `auto` prefer Gemini** (`builder._watch`, builder.py:256; `GEMINI_GRACE_S` / `GEMINI_VIDEO_TIMEOUT_S`, :244–245).
   - Wait for Gemini up to ~75 s and use the Claude draft only if Gemini fails or times out.
   - Claude already runs in parallel, so a Gemini failure costs nothing extra.
   - Measured with env overrides: Gemini 5/5, 42–74 s.
2. **Give Gemini the text metadata too** (`gemini.watch_video`, gemini.py:225: `parts = [_video_part(...), WATCH_PROMPT]`).
   - Add the title, description and chapter list as a text part, like the Claude prompt has (`transcript.format_for_prompt` without the transcript).
   - Fetch the watch-page metadata separately from captions; it loaded fine while captions were 429ing.
   - This fixes the missing dataset link (pandas) and the starting-state context (git).
3. **Lint the setup step.** Flag a step 1 that says clone/download/"from the tutorial repository" without a URL or the exact commands. "Clone the example repository" appeared in 2/2 Gemini git builds. The fix is either the link from the description or recreate commands, which the Claude draft already has and could be reused.
4. **Demo literals still pass through from Gemini drafts.** `DEFAULT_USER\s*=` and `/login` came back in both Gemini git builds. Treat identifiers that only exist in the tutorial's off-camera starting state (not created by any lesson step's instructions) as `precision_checks` material, not screen gates.
5. **Thin Gemini checks.**
   - Give notebook steps a `run_command` (or treat `.ipynb` steps as run steps) so the standard-output rule fires.
   - Flag consecutive steps with identical check sets: React s3 duplicates s2, so s3 passes instantly.

## Fourth run (`e2582e8`): adapt loop converges, standard output checks

Same setup again (`--saved-captions`, Claude path only; Gemini still at quota). Results are in `results-e2582e8/`.

| Lesson | Time (38f85bc / 9d5fbb9) | Adapt rounds (problems left → steps re-sent) | Leftover warnings | Run steps with an output check | Manual /10 |
|---|---|---|---|---|---|
| react-useeffect | 53 s (45 / 20) | 3 (12 in 8 → 7 in 5 → 5 in 3) | 0 | 1/1 (`Local:\s+http://localhost:\d+`) | 8.5 |
| git-rebase | 29 s (29 / 18) | 2 (1 → 1, stopped) | 0 | 5/5 | 8 |
| pandas-30min | **47 s** (108 / 49) | 3 (11 in 5 → 1 in 1 → 2, stopped, kept the best) | **0** (was 3) | **9/9**: notebook steps use `rows x columns` / `RangeIndex:` / `Name:…dtype:` in Code | **9** |
| rust-cli | **83 s** (115 / 72) | 2 (4 in 3 → done) | 0 | 9/9 (`Finished\s+\S*\s*(dev\|release\|test)` + program output) | 9 |
| fastapi-rest | 40 s (43 / 22) | 3 (7 in 4 → 2 in 1 → 2, stopped) | 0 | 8/8 (uvicorn access-log lines) | 9 |

- **Both fixes work.** Leftover `build.warnings` went from 4 to 0, and every step with a `run_command` has an output check. Re-sending only the failing steps makes later rounds take 1.5–8.6 s instead of 25–29 s, and the "no better, stop" rule fired in 3 lessons.
- The checks are the strongest of the four runs. Real-output matches: FastAPI 15/16, Rust 16/24, git 8/11, React 4/4, pandas 4/4. The grader finds 0 vague or code-echo checks.
- **Time is still above 9d5fbb9** (+0 to +33 s). The first adapt round now does most of the work (Rust 33.6 s, pandas 12.8 s, React 11.2 s). React still needed all 3 rounds because the problem count kept dropping (12 → 7 → 5).
- **The git lesson's structure varies between runs.** This time s1 includes a clean warm-up rebase and s3 asks the learner to build the conflicting commits. s3 doesn't say to make the two matching commits on `main` first, so the instruction is incomplete. Each version is coherent on its own, but it changes from run to run.

**Small remaining fixes:**
1. **Speed up the first adapt round.** Adapt the steps in parallel batches, the way the video pass already works, instead of one call for the whole graph. Round 1 is now the slowest piece (Rust 34 s).
2. **Use a stack-specific error pattern.** React s2, s3 and s7 use `screen_absent Terminal 'Traceback|Error:|ERR!'`. Python's `Traceback` never appears in a Vite terminal. Harmless, but use the stack's own error text instead (e.g. `error\[E` for Rust, `fatal:` for git, `ERR!|Error:` for npm).
3. **Still untested live:** the Gemini path and the 8 s grace period, until the Gemini quota resets.

## Third run (`38f85bc`): fixes for the 4 remaining issues

Same setup as the second run below: Gemini at its daily quota and YouTube refusing caption requests, so this used `--saved-captions` and only the Claude path ran. Results are in `results-38f85bc/`.

| Lesson | Time (9d5fbb9) | Steps | Adapt rounds (problems left after each) | Leftover warnings | Manual /10 |
|---|---|---|---|---|---|
| react-useeffect | 45 s (20 s) | 9 | 3 (10 → 6 → 5) | s7 `npm run dev` has no output check | 8.5 |
| git-rebase | 29 s (18 s) | 5 | 1 (clean) | – | 8 |
| pandas-30min | **108 s** (49 s) | 9 | 3 (13 → 6 → 7) | s5, s6, s8 "notebook cell" steps have no output check | 8 |
| rust-cli | **115 s** (72 s) | 8 | 3 (4 → 1 → 2) | – | 9 |
| fastapi-rest | 43 s (22 s) | 8 | 3 (5 → 2 → 3) | – | 9 |

**What the fixes changed:**
- **Fixed:** React's any-window "Subtract" / "Change color" checks that passed on the editor are gone. The grader finds 0 any-window checks matching the learner's code.
- **Fixed:** the vague patterns are gone (`\*\s*\S+`, `\|\s*/`, `\bmain\b`, `\S+\s+0\.1\.0`). The git lesson still starts with the practice-repo setup step and uses only real git output.
- **Regression: the lint and the model don't converge.** 4/5 lessons use all 3 adapt rounds, and the problem count stops falling after round 2. Each round regenerates every step: 25–29 s for pandas and Rust, ~10 s for the others. The build then falls back to `repair` anyway. Net effect: +11 to +59 s per lesson compared with 9d5fbb9.
- **Not fixed: notebook steps still lack a real output check.** pandas s5 `Country|Quantity|Category`, s6 `CustomerName` and s8 `Order\s+ID` are scoped to `Code`. They match the cell's own code (`df['Country']`, `rename(columns={'OrderID': 'Order ID'})`), so they correctly don't count as output. But the model never offers a printed-DataFrame pattern instead, so each of these steps ships with a warning and a check that passes from the code alone.
- **Untested:** Gemini's 8 s grace period. Gemini failed instantly on quota, so the race never ran.

**Next fixes (ranked):**
1. **Make the adapt loop converge or stop early** (`builder._adapt`, `ADAPT_ATTEMPTS`).
   - Send only the failing steps back, not the whole graph; that is most of the 25–29 s per round.
   - Stop retrying when a round doesn't reduce the problem count, and let `repair` handle the rest.
   - This would bring pandas and Rust back to ~50–60 s.
2. **Fill in the output check deterministically when the model doesn't.** In `repair`, add a stack-standard output check to any run step left without one:
   - Vite: `Local:\s+http://localhost:\d+` for `npm run dev`.
   - pandas notebook: `\d+\s*rows\s*[x×]\s*\d+\s*columns|dtype:\s*\w+|Name:\s*\w+`.
   - pytest: `\d+\s+passed`; cargo: `Finished`; uvicorn: `Uvicorn\s*running\s*on`.
   - Adding the same list to the adapt prompt should also stop the loop from asking for them 3 times.

## Re-run on E2's fixes (`9d5fbb9`), 2026-11-14 ~14:40 PST

The same 5 videos with the same goals, a fresh empty workdir and `cache=False`. Results are in `results-9d5fbb9/`.
Two things outside the builder were down during this run:
- **Gemini** was at its daily quota: 429 on all 4 models.
- **YouTube** returned 429 on caption requests from this IP. The run had no fallback route for captions.

A strict live run therefore failed on both engines, and each failure was reported honestly; nothing was made up. To still measure the Claude path and the fixes, this run used `--saved-captions evals/lesson/results`.
That option feeds the real captions fetched by the first run (same day), plus the live title, description and chapters from the watch page. Each graph records this in `meta.captions`. **The Gemini path at 9d5fbb9 is untested.**

| Lesson | Time to lesson (was) | Steps (was) | Manual /10 (was) | What changed |
|---|---|---|---|---|
| react-useeffect | **20 s** (50 s, Gemini) | 7 (9) | **8.5** (8) | **Setup:** step 1 sets up Vite (`npm create vite@latest`) and has a `Local:\s+http://localhost:\d+` check. **Still wrong:** two any-window checks pass on the editor alone (`(?i)subtract`, `change\s*colou?r`). |
| git-rebase | **18 s** (41 s, Gemini) | 5 (8) | **8** (5.5) | **Now playable:** step 1 builds the practice repo (`git init -b main`, `feature/login`, conflicting commits on `app.txt`), with checks `Initialized empty Git repository` and `Switched to a new branch`. **Fixed:** demo literals are gone (`CONFLICT \(content\)`, `Successfully rebased`, `working tree clean`), and the theory is attached as explanations (coverage 17 % → 53 %). **Weak spots:** s2 `\*\s*\S+` / `\bmain\b` and s1 `\|\s*/`. |
| pandas-30min | **49 s** (179 s) | 9 (9) | **8.5** (8.5) | **Setup:** step 1 links the real dataset repo (github.com/techwithtim/PanadasTutorial, from the description, HTTP 200). **Fixed:** "40 entries" → `> 0`. **Still wrong:** two "table displayed" checks match the code itself (`Category\|Country\|Quantity`, `Country\|Customer`), and 7 lint warnings are false positives (below). |
| rust-cli | **72 s** (174 s) | 8 (9) | **9** (8) | **Better:** every step has `error\[E\d+\]\|could not compile`, the `long_path` echo check is gone, and output checks are real (`-h,\s*--help`, `-V,\s*--version`, `FileEntry\s*\{`, `\[\{.{0,3}name`). |
| fastapi-rest | **22 s** (170 s) | 8 (8) | **9** (8) | **Better:** curl-echo checks are replaced by uvicorn access-log lines, e.g. `POST\s*/items\S*\s*HTTP/1\.1\S*\s*200` and `HTTP/1\.1\S*\s*404`. Terminal checks match real output 15/17 (was 6/11). |

All 5 builds are schema-valid and lint-clean, with no PINN leakage. All 5 of the previous fixes landed and show in the output.

### Remaining fixes after 9d5fbb9 (ranked)
1. **Output checks that pass on the code itself.**
   - Two kinds remain:
     - React s3 `(?i)subtract` and s4 `(?i)change\s*colou?r`: app-less, so they match in any window, including the editor showing `subtractCount` / `changeColor`.
     - pandas s5 `Category|Country|Quantity` and s6 `Country|Customer`: scoped to `Code`, labelled "Filtered table displayed", but `df['Country']` is in the cell.
   - Fix: generalize the run_command-echo lint to the code the learner types. Reject an output check whose pattern matches `step.code`, the backticked code in the instructions, or a `Code` target's `match`.
   - This matters most for app-less checks, now that "any window" includes the editor.
2. **The race still waits for Gemini after Claude has finished.** Rust's Claude video pass finished at 20.9 s, but the build waited until Gemini timed out at 45 s.
   - Once Claude has a valid draft, give Gemini a short grace period (e.g. 5–10 s) or take Claude immediately. Rust would go from 72 s to ~50 s.
   - Rust's adapt took 27 s, with lint retries.
3. **The notebook lint is a false positive.** "runs X but has no check on its output" fired on 7 pandas steps whose `run_command` is "Run each notebook cell (Shift+Enter)", and stayed in `build.warnings`.
   - Notebook output appears in the editor (`Code`), so a Code-scoped output check (`dtype:`, `rows x columns`, `RangeIndex`) should count.
   - "Run the cell" isn't a shell command and shouldn't be treated as one.
4. **Minimum specificity for generic checks.** Examples: `\*\s*\S+` (any `*`), `\|\s*/`, `\bmain\b` (git) and `\S+\s+0\.1\.0` (rust).
   - These are learner-generic but almost always true. Require ≥4 literal alphanumerics, or one real tool keyword, per screen pattern.
5. **Ops, not E2: captions need another route.** With Gemini on a free-tier daily cap and YouTube rate-limiting caption requests, the Claude path has no captions and neither engine can build.
   - (At the time a scraping service was the planned route; it has since been removed.)
   - Until captions load, a fresh lesson on the demo machine can fail on both engines; cached lessons still work.

## Scores (first run, 47dba31)

| Lesson | Stack | Video | Path (video / adapt) | Time to lesson | Steps | Checks (metric) | Auto | **Manual /10** |
|---|---|---|---|---|---|---|---|---|
| [react-useeffect](https://www.youtube.com/watch?v=L-1sP3Ljhsg) | React | 19:51, Bro Code, 2024 | gemini-4-hydrogen / claude-opus-5-5 | **50 s** | 9 | 22 (0) | 8.4 | **8** |
| [git-rebase](https://www.youtube.com/watch?v=DkWDHzmMvyg) | git | 9:44, Philomatics, 2024 | gemini-4-hydrogen / claude-opus-5-5 | **41 s** | 8 | 15 (0) | 8.0 | **5.5** |
| [pandas-30min](https://www.youtube.com/watch?v=EXIgjIBu4EU) | pandas | 30:36, Tech With Tim, 2025 | claude-opus-5-5 (transcript) / claude | **179 s** | 9 | 29 (1) | 9.5 | **8.5** |
| [rust-cli](https://www.youtube.com/watch?v=5UA9UWWAagc) | Rust/clap | 28:09, Jonkero, 2025 | claude-opus-5-5 (transcript) / claude | **174 s** | 9 | 26 (0) | 8.2 | **8** |
| [fastapi-rest](https://www.youtube.com/watch?v=iWS9ogMPOI0) | FastAPI | 15:16, pixegami, 2023 | claude-opus-5-5 (transcript) / claude | **170 s** | 8 | 23 (0) | 8.9 | **8** |

**Bottom line:** the builder generalizes well beyond PINNs.
- All 5 lessons built, with 0 errors, 0 schema errors and 0 lint problems.
- Every step title matches what happens in the video at that time (43/43 steps checked against the transcript).
- There is **no PINN or physics leakage** in any output.
- The checks fit each stack: `error\[E\d+\]|panicked` for Rust, real git messages for git, `Uvicorn running on` for FastAPI, and `RangeIndex: N entries` for pandas.

The weak spots are time-to-lesson on the Claude path (~3 min) and lessons that can't be followed from an empty folder. Checks that fit only the tutorial's own data or pass on what the learner types are the next problem.

## Automatic checks (grade.py)

| | react | git | pandas | rust | fastapi |
|---|---|---|---|---|---|
| Contract schema valid / lint clean | ✓ / ✓ | ✓ / ✓ | ✓ / ✓ | ✓ / ✓ | ✓ / ✓ |
| Video ranges ordered, inside the video | ✓ | ✓ | ✓ | ✓ | ✓ |
| Coverage of the video | 77 % | **17 %** | 75 % | 89 % | 59 % |
| Step titles grounded in the transcript window | 9/9 | 8/8 | 9/9 | 9/9 | 8/8 |
| Generic-only steps (just "no error") | 0 | 0 | 0 | 0 | 0 |
| Generic `Traceback\|Error` checks | 0 | 0 | 1 | 0 | 2 |
| Python `Traceback` in a non-Python stack | 0 | 0 | – | 0 | – |
| Terminal/browser checks matching real tool output* | 1/7 | 4/11 | 3/3 | 1/10 | 6/11 |
| Explanations timestamped outside their step | 0 | 2 | 2 | 1 | **5** |
| PINN/ML vocabulary leakage | none | none | none | none | none |
| Hints/mistakes copied between lessons | none | none | none | none | none |

\* This compares checks against a fixed set of real tool-output lines per stack (`TOOL_OUTPUT` in grade.py): vite, git, cargo, uvicorn and pandas reprs.
Most "misses" are fine because they match the tutorial program's *own* output, e.g. `Path does not exist`, `EVENT LISTENER ADDED` or `Size B`. Each one was checked by hand below.
The auto score is a rough composite. The manual score is the verdict.

## Per-lesson reading

### react-useeffect: 8/10 (Gemini watched it)
- **Steps** follow the video's 10 chapters almost exactly: setup 2:00, no dependencies 3:25, empty array 4:50, one dependency 5:51, multiple dependencies 7:25, example 2 11:33, cleanup 15:51, multiple hooks 17:31.
  The theory chapter "why use useEffect()" (9:57–11:33) is correctly skipped.
- **Checks** are specific code fragments: `useState,\s*useEffect`, `\},\s*\[\s*\]\s*\)`, `\[count,\s*color\]`, `removeEventListener\(.{1,2}resize`. Each step also has a browser check.
- **Issues:**
  - Every browser check is scoped to `Google Chrome`, so a Safari or Arc user can never pass.
  - `EVENT LISTENER ADDED/REMOVED` only appears if the DevTools console is open, and the instructions never say to open it.
  - `Size: \d+ x \d+` is the **tab title**: small text that OCR is unlikely to read.
  - There is no "dev server running" check (`Local:\s+http://localhost`), even though `STACK_GUIDE` suggests one.
  - There is no "create the Vite project" step: s1 starts by editing an existing `MyComponent.jsx`.

### git-rebase: 5.5/10 (Gemini watched it)
- **Where it's right:** the hands-on part (5:58–8:11) is followed exactly, and the checks use real git output.
  - `Merge conflict in index.js` comes from `CONFLICT (content): Merge conflict in index.js`.
  - `rebase in progress`, `all conflicts fixed`, `Successfully rebased`, `working tree clean`, and `<<<<<<<|>>>>>>>` absent in the editor are also real git output.
  - The Vim `:wq` hint and "git rebase --continue, not git commit" match the narration (7:09–7:16, 6:50).
- **Why it scores low:**
  1. **The lesson can't be followed from an empty folder.** The video rebases a demo repo that was set up off camera, with `feature/login` and conflicting commits in `index.js` and `package.json`. The repo isn't linked, and no step tells the learner how to create it. Step 1 is already "run `git rebase main`".
  2. **Checks are tied to the tutorial's demo content:** `DEFAULT_USER\s*=\s*.?admin`, `\]\s*Add\s*login\s*endpoint`, `On branch feature/login`.
     A learner rebasing their own branch fails every step, because a step passes only when **all** of its checks pass.
  3. **The clips are tiny:** 6 s, 14 s, 20 s, 10 s, 29 s, 4 s, 10 s and 4 s, covering 17 % of the video.
     The first 6 minutes explain *why* and *how* rebase works. That theory reaches the learner only as two `explanations` on s1 (2:26, 5:14), both timestamped before s1's clip starts (5:58).
     The 4–6 s steps make "pause the video at step end" feel jumpy.

### pandas-30min: 8.5/10 (Claude, from the transcript)
- **Steps** match the narration: uv/pip + `read_csv` (0:42–4:12), Jupyter notebook (8:47), head/info/describe (11:01), selection (13:32), boolean filters (17:40), `loc` updates (22:03), drop/rename (25:48), groupby (28:06) and `to_csv` (29:44).
  The odd-looking "set Product to 'Tim' for Anna" is really in the video (23:31–23:53).
- **Checks** are good pandas fragments plus real repr lines: `\d+\s*rows\s*x\s*\d+\s*columns`, `RangeIndex(start=0`, `Name:\s*Price,\s*dtype`. The single metric check reads `RangeIndex:\s*(?P<value>\d+)\s*entries` from `df.info()`.
- **Issues:**
  - The metric `entries >= 40` and `UNITED\s*STATES` only pass with the tutorial's `orders.csv`. No step says where to get that file.
  - s7 has a generic `screen_absent Code 'Traceback|KeyError'`.
  - s2's `\d+ rows x \d+ columns` is scoped to `Code`. That is correct for a notebook in VS Code, but not for one in Jupyter in the browser.

### rust-cli: 8/10 (Claude, from the transcript)
- **Steps** cover the whole build:
  - `cargo new best_ls` + clap derive (0:18), `#[command(version, about)]` (3:24) and a default path (4:52);
  - `exists` + owo-colors (6:09), `read_dir` (9:02) and metadata structs + strum (11:36);
  - a tabled table (17:29), chrono dates (21:34) and a `--json` flag with serde_json (24:09).
- Claude correctly turned the auto-caption mishearings "oo colors", "Kronos crate" and "Jason crate" into `owo-colors`, `chrono` and `serde_json`. The `clap 4.5.39` version is from the narration (0:57).
- The checks fit Rust: `derive\(.{0,20}Parser`, `Cli::parse\(\)`, `Usage:\s*best_ls`, `error\[E\d+\]|panicked` (not Traceback), `DateTime<\s*Utc\s*>`.
- **Issues:**
  - Some Terminal checks match what the learner *types*, not the output: s3's `long_path` passes as soon as `cargo run -- long_path` is on screen. s5's `Cargo\.toml` is loose.
  - There is no `Finished`/`Compiling` cargo build check.
  - s6 spans 5:40 of video.
  - The `precision_checks` paths (`best_ls/src/main.rs`) disagree with the targets (`src/main.rs`).

### fastapi-rest: 8/10 (Claude, from the transcript)
- **Steps** match the video: hello world + uvicorn (0:46), POST `/items` with curl (2:37), `/items/{item_id}` (3:41), `HTTPException` 404 (5:26), `limit` query (7:12), the Pydantic `Item` (8:45), `response_model` (10:42) and `/docs` (11:47).
  curl, apple/orange, `limit 3` and `/docs` are all in the transcript.
- The checks are good (`Uvicorn\s*running\s*on`, `class\s*Item\(\s*BaseModel\s*\)`, `detail.{0,4}Item\s*\d+\s*not\s*found`, `response_model\s*=\s*list\[\s*Item`).
- **Issues:**
  - Two Terminal checks match the typed command, not the response: s3 `items/\d+` and s5 `items\?limit=\d+`.
  - Browser checks are scoped to `Google Chrome` only.
  - There are 2 generic `Traceback|Error:` checks.
  - 5 of 8 steps have explanation timestamps before the step starts (e.g. s2 starts at 2:37 and its explanation is at 2:21). The overlay will jump outside the step's clip.

## Time to lesson

| Path | Videos | Gemini video pass | Claude video pass | Adapt (Claude) | Total |
|---|---|---|---|---|---|
| Gemini watched | git (9:44), react (19:51) | 35.5 s, **42.8 s** (cap 45 s) | – | 5–8 s | 41–50 s |
| Gemini timed out → Claude | fastapi (15:16), rust (28:09), pandas (30:36) | 45 s wasted | 117–127 s | 7–9 s | **170–179 s** |

- Every video of 15 min or more hit the 45 s Gemini cap, and React made it with only 2 s to spare.
- On the Claude path, 45 s of the ~3 min is spent waiting for a Gemini answer that never gets used.
- The transcript is already prefetched in parallel (`_watch`), but Claude only starts after the cap.
- Each Claude call also wastes one round trip on a structured-output 400 ("schema too complex"). The fallback is remembered only per process (`claude._schema_too_complex`).

## Top 5 fixes, ranked by impact

Line numbers refer to `server/lesson` at `47dba31`.

1. **Race the engines instead of running them in sequence**: `builder._watch` (builder.py:217) and `GEMINI_VIDEO_TIMEOUT_S` (:206).
   - Start `claude.watch_transcript` as soon as `info_task` resolves, alongside Gemini. Take Gemini if it returns valid steps within the cap, else Claude. Cancel the loser.
   - This saves ~45 s on every video of 15 min or more (3 of 5 here: 170–179 s → ~125–135 s), and the React case at 42.8 s stops being a coin flip.
   - Also try `media_resolution` LOW / `fps=0.5` for the full-video pass (`gemini.watch_video`, gemini.py:213; `_generate_json` already supports `media_low`). That way long videos can finish under the cap at all.
   - Optionally skip the always-failing structured-output attempt (`claude._generate_json`) when the schema is the known-too-complex one.
2. **A lesson must be playable from an empty workdir: add a setup step.** Edit `WATCH_PROMPT` (gemini.py:183) and `TRANSCRIPT_NOTE` (claude.py), and add an `ADAPT_PROMPT` rule when `WorkdirInfo.exists`/`files` is empty (workdir.py:39).
   - When the tutorial starts from a pre-existing repo, dataset or project (git demo repo, `orders.csv`, an existing Vite app), step 1 must say how to get there. Use the link in the description, or give the exact commands that recreate the state. For git: `git init`, two branches and conflicting commits.
   - Today git-rebase can't be followed at all, and pandas/React assume files the learner doesn't have.
3. **Don't make a step depend on the tutorial's private names and data.** Edit `ADAPT_PROMPT`/`ADAPT_SYSTEM` (gemini.py:245–257) plus a lint rule in `schema.lint` (schema.py:49).
   - A step passes only when ALL of its checks pass. Each step should therefore have one stack-generic check: tool-output formats (`Successfully\s*rebased`, `CONFLICT`, `RangeIndex:\s*\d+\s*entries`), API names and syntax.
   - Literal demo content goes in the precision backups or a secondary check, not the screen gate. Examples: `DEFAULT_USER = admin`, `Add login endpoint`, `feature/login`, `entries >= 40`, `UNITED STATES`.
   - Lint for this deterministically: flag a check whose pattern contains a string literal/identifier that appears in neither the learner's workdir nor the instructions the learner is told to type.
4. **Reject Terminal checks that pass on the learner's own typed command.**
   - Add to `schema.check_problems` (schema.py:83), with access to the step's `run_command` and `targets[].match`, or to `builder.normalize_checks` (builder.py:412).
   - Flag a `screen_contains` Terminal pattern when `re.search(pattern, run_command or target.match)` succeeds: it matches the command line, not the output. Feed it back to the adapt pass.
   - This catches `items\?limit=\d+` and `items/\d+` (fastapi) and `long_path` (rust).
   - The same rule should require at least one *output* check per run step: `Finished` for cargo, `Local:` for vite, `Uvicorn running on`.
5. **Fix the timing and clip shape**: `builder.normalize_draft` (builder.py:315) and `assemble` (:371).
   - Pull each explanation timestamp into its step, or extend the step's start back to the first explanation. 10 explanations land outside their step: fastapi 5, git 2, pandas 2, rust 1. Also sort explanations, since rust s4 has 510 s before 483 s.
   - Merge micro-steps shorter than ~20 s (git has eight steps of 4–29 s).
   - Attach the skipped conceptual section as `explanations` of the first hands-on step (git 0:00–5:58 explains the whole idea).
   - Separately, browser checks hardcode `app: "Google Chrome"`. Either have E6 accept a `browser` alias (Chrome/Safari/Arc), or emit the learner's actual browser.

Not a problem here, but cheap to fix: the shared prompt still uses PINN examples. `WATCH_PROMPT` common_mistakes (gemini.py:208) uses "requires_grad=True … create_graph=True", and the libraries example (:209) is `"torch": "2.x"`. Nothing leaked into these 5 lessons, but a stack-neutral example costs nothing.

## Method notes and limits
- **Videos:** found via YouTube search, then verified with oEmbed (HTTP 200) and the watch page (length, publish date, captions) on 2026-11-14. Details are in `videos.json`.
  The git tutorial is 9:44, just under the 10-minute floor. It was the best hands-on terminal rebase tutorial from 2023 or later; the 10–40 min alternatives were GUI-only (GitHub Desktop) or conceptual.
- **"Grounded in transcript"** only shows that a step's title or instruction words appear in the transcript near its time range. Code identifiers are often not spoken, so `code_checks_grounded` undercounts. Gemini-path code checks (React, git) can't be verified from captions at all; they were judged on plausibility and on the chapters.
- **Not tested:** whether the regexes actually match on a real OCR'd screen (needs E6's reader on a live screen), or `detail=True` (the per-step Gemini clip pass, which is off by default).

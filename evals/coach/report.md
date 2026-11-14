# Coach on non-PINN beginner mistakes: React, pandas, git

**Question.** The coach had only been checked end to end on the PINN example (`lr=0.3`). This eval asks whether it works on other topics, so the demo isn't limited to PINNs.

**Answer.** Partly. When Opus actually writes the card, the diagnosis and pointing are good (7/9 cards point at the right line). Two things outside the model sink most cases:

- **The step gate goes green while an error is on screen** in 3 of the 5 non-firing cases, so the coach never speaks.
- **Haiku triage routes screen-only failures to the generic "template" hint.** The orchestrator passes no `error_text` for screen-first lessons.

On top of that, "Do it for me" breaks on git (multi-line edits, a `git-rebase-todo` that isn't in the workdir, OCR'd anchors) and needs an extra Opus call for every notebook fix.

Run: 2026-11-14, `claude/coach-qa-42e015` at `148433b` (integration/live), live `claude-opus-5-5` / `claude-haiku-5-5`, Bright Data on. Lessons are snapshots in [`lessons/`](lessons/) of the cached graphs for `ZipmUa9N7Os`, `_zsKKcnX-qE` and `42392W7SgnE`. The cached builds were being regenerated while this ran.

## Pass/fail table

Columns:
- **Fires** is the real orchestrator gate: `evaluate_gate(..., precision_mode=True)`. Precision mode is on whenever the lesson folder exists, which is always.
- **Diagnosis** is graded by hand against the real cause (see *Cases*).
- **Line** means the coach's streamed `targets` and the orchestrator's spotlight both land on the offending line.
- **Patch** means "Do it for me" was applied the way the learner would apply it, then the real check was re-run: React 18 StrictMode mount/tick/unmount, the notebook re-executed with nbclient, or git finishing the rebase.
- **Latency** is targets streamed / card returned, measured from the `diagnose()` call.

| Case | Mistake (real output on screen) | Fires | Diagnosis | Line | Patch: minimal + correct | Latency (targets / card) | Result |
|---|---|---|---|---|---|---|---|
| **R1** React s3 | `return clearInterval(intervalId);`: calls it instead of returning a cleanup. Timer stuck at 0 | **NO**: screen checks only look for `clearInterval(` | **FAIL** (forced): rules → template "What does setInterval return…" | **FAIL**: no targets | PASS: 2→4 lines via Opus, 1 interval, ticks, 0 after unmount | — / instant (template); patch 3.3 s | **FAIL** |
| **R2** React s3 | Cleanup calls `intervalId`, variable is `interval`. CRA `Failed to compile … no-undef` | **NO**: precision `file_contains clearInterval` + `return () =>` turn it green | PASS: "saved as interval on line 7… rename to intervalId" | PASS (line 7, line 14, eslint line) | PASS: 1 line, from the card's diff | 4.9 / 6.9 s | **FAIL** (gate); coach PASS |
| **R3** React s1 | Imports only `useState`, calls `useEffect`. `Failed to compile` | yes (`s1c4`) | PASS | PASS | PASS: 1 line (import) | 8.1 / 9.8 s (6.1 s waiting for web) | **PASS** |
| **P1** pandas s2 | `df.groupby("Department").mean()`. `TypeError` (string column `Employee`) | **NO**: precision `file_contains groupby\(` in the .ipynb turns it green | PASS: "averages every column, including the string column Employee… select ["Salary"]" | PASS | PASS: 1 line, but only via a 2nd Opus call (JSON-escaped .ipynb line) | 7.1 / 9.0 s | **FAIL** (gate); coach PASS |
| **P2** pandas s3 | `groupby("Department", "Experience_Years")`. `ValueError: level name Experience_Years is not the name of the index` | yes | PARTIAL: fix right, but says the 2nd positional arg is `axis` (pandas 2). Installed pandas 3.1.1 says `level` on screen | PASS (via coach target: `diff.yours` was empty) | PASS: 1 line via 2nd Opus call | 4.1 / 6.3 s | **PARTIAL** |
| **P3** pandas s4 | `.agg({"Salary": [mean, max, min], …})`. `NameError: name 'mean' is not defined` | **NO**: precision `\.agg\(` turns it green | PASS | PASS | PASS: 1 line via 2nd Opus call | 4.2 / 6.7 s | **FAIL** (gate); coach PASS |
| **G1** git s5 | `squash` on the FIRST todo line. `error: cannot 'squash' without a previous commit` | yes (`s5c2`) | PASS: "Set line 1 back to pick and change Cleanup to squash" | PASS | **FAIL**: the diff only changes line 1. The rebase "succeeds" with nothing squashed (5 commits) | 4.7 / 6.7 s | **FAIL** |
| **G2** git s3 | At the `edit` stop: removed the debug line, `--continue` without `git add`. Git's misleading "You must edit all merge conflicts… git add" | yes (`s3c2`) | **FAIL**: Haiku → template "Change only the first line's pick keyword to edit…" (already done) | **FAIL**: no targets | **FAIL**: 0-line patch, no `diff.command`. Rebase still stuck | — / 2.8 s | **FAIL** |
| **G3** git s5 | Moved `Cleanup` above `Add logout endpoint` → CONFLICT, then `--continue` with markers. `index.js: needs merge` | yes | PARTIAL: names the unresolved markers, but "keep the logout route" leads to a 2nd conflict on the next pick | PASS | **FAIL**: `diff.yours = "10 <<<<< HEAD"` (OCR text + gutter number) → "no safe patch". The copied command `git add index.js && git rebase --continue` **commits the conflict markers** if pasted first (verified) | 4.0 / 6.1 s | **FAIL** |

**Totals**
- **Realistic layout:** in the orchestrator run with the folder `npx create-react-app demo-app` really makes, R3 doesn't fire either (see the next table). There, no React case reaches the coach.
- **Fires:** 5/9 through the orchestrator gate. 8/9 with screen checks alone (R1 is invisible to both).
- **Diagnosis:** 5 correct, 2 partial, 2 wrong.
- **Line:** 7/9.
- **Patch correct after re-run:** 6/9. Every correct patch is 1 line, except R1's appropriate 2→4.
- **Card latency:** median 6.7 s (6.1–9.8). Targets stream at 4.0–8.1 s.
- **Whole chain right:** R3 only. P2 partial.

### Through the orchestrator (own engine, `:8796`)

`:8793` was taken by E4's own test engine, so this ran on `:8796`.

Setup: LIVE mode, `ORCH_AUTOSTART` with the cached React lesson (cache hit through the real builder), and the R3 screen replayed via `TUT_SCREEN_FIXTURE`. The learner was scripted over the WebSocket with `run_engine.py`.

| | root layout (`TUT_WORKDIR` = the CRA app) | nested layout (lesson folder holding `demo-app/`, what s1's `npx create-react-app demo-app` makes) |
|---|---|---|
| gate fails on `s1c4`, level-2 card | yes, card 6.6 s after `thinking` (streamed spotlight at 4.8 s) | **no**: the gate passes at once via precision (`demo-app/src/Components/Timer.js` exists and contains `setInterval(`). The app is shown `s1c4 No compile errors ✓ "confirmed by your files"` while CRA says *Failed to compile* |
| save → level-2 card | 29.3 s (≈20 s of it waiting for this Mac's real keyboard/mouse to go idle; the engine reads HID) | the first save counts as the learner acting → `step.passed` 0.6 s later, moving on to s2 with the build broken |
| repeat save ≥ 20 s later → level 3 with diff | yes (14.4 s, typing guard) | never reached |
| Do it for me → preview → confirm → file written | yes, 1-line patch | never reached (it would also miss the file: `diff.file` is `src/Components/Timer.js`, relative to `demo-app/`) |
| post-fix screen → `step.passed` | yes, 0.5 s after the screen changed | **false pass** |

## What breaks, ranked by impact

1. **Precision mode turns steps green over a visible error** (E4/E3, gate). `evaluate_gate` passes when *all precision checks* pass, even while a screen check like `screen_absent "Failed to compile|Traceback"` is failing. R2, P1 and P3 go green with a compile error or traceback on screen, and the coach never speaks. So does R3 in the real engine with the CRA-nested folder, where the app even shows the failing check as "✓ confirmed by your files". This one defect hides most mistakes from the coach in any non-PINN demo.
2. **Screen-first lessons give the coach no `error_text`** (E4) **and triage treats that as "nothing ran"** (E5). The orchestrator only passes `tut run` tails. Rule 1 then sends R1 to the template card ("only file checks failing; nothing run yet"). Haiku sends G2 to the template card ("no error output… has not yet run the rebase steps") even though git's refusal is on screen. Web grounding also runs on a generic query and returns off-topic pages (P3: a Spark repo and an r/datascience SQL thread; not cited, luckily).
3. **Web grounding blocks Opus for up to 6 s** (E5). Card time is max(Haiku triage 1.6–2.9 s, web wait up to 6 s) plus Opus 3.5–4.7 s. R3 waited the full 6 s timeout and got 0 sources: 9.8 s instead of about 5.5 s. P1 lost about 3 s the same way.
4. **Multi-edit fixes ship as single-line diffs** (E5). In G1 the card says two edits, the diff carries one, and "Do it for me" reuses the card's diff because it applies cleanly. The result runs but skips the step's goal.
5. **Notebooks** (E5/E4).
   - `apply_fix` can't anchor plain-Python `yours` in `.ipynb` JSON, so every pandas fix needs a 2nd Opus call (+2.5–3 s).
   - The 6000-char code excerpt is raw notebook JSON, mostly outputs with ANSI codes.
   - `target_location` returns line 332 of the JSON for `.agg(`.
6. **The code excerpt and patch target come from OCR when the step's file isn't at the workdir root** (E4). This covers `git-rebase-todo`, which lives in `.git/rebase-merge/`, and CRA's nested `demo-app/`. The coach then copies OCR text into `diff.yours` (`"10 <<<<< HEAD"`). `apply_fix` can't find it, and `_apply_fix` can't open `workdir/diff.file`.
7. **Unsafe terminal fixes** (E5). G3's `git add index.js && git rebase --continue` commits conflict markers when pasted before the edit. The advice also resolves a reorder conflict the wrong way: the right move is `git rebase --abort` and putting `squash` under the commit it belongs to.
8. **The installed version vs the lesson's version** (E5). P2 explained a pandas 3 error with pandas 2 semantics (`axis`), contradicting the traceback on screen. `pandas>=2.0` installs 3.1.1 today.
9. **No-op patches** (E5). G2's "Do it for me" returned a 0-line patch, which would show an empty "Apply this fix?" preview. Its summary was right ("stage it and continue rebase"), but no command was attached.

What works well:
- Targets stream first and land on the right line.
- The orchestrator's `diff.yours` spotlight finds the line even through OCR noise (`intervalld`, `<<<<<`, `agg (f"Salary"`).
- Bodies end with the concrete action.
- Guiding questions are specific.
- Diffs are minimal.
- The prompt cache works: 7–10.7k cached tokens read per call.

## Re-run against E5's fixes (PR #1 @ `d219e52`, merged locally onto integration/live)

Same 9 cases and harness. Records: [`results-e5-d219e52/`](results-e5-d219e52/). The gate is unchanged, because those fixes are E4's, so **fires stays 5/9**.

| Case | Before | After `d219e52` |
|---|---|---|
| **G2** | FAIL: template card, 0-line patch | **PASS**: Opus "Edited index.js was never staged… Run git add index.js, then git rebase --continue", sent as a command fix. The rebase finishes and the debug line is gone from history. It cites the right Stack Overflow answer |
| **G1** | FAIL: diff fixed only line 1, nothing squashed | **REGRESSION**: `expected` is now the 4 rewritten todo lines, but `yours` is still only line 1. Applying it duplicates three picks (a 7-line todo), and `git rebase --continue` stops in a CONFLICT (`could not apply 7a428b4... Add login endpoint`) |
| **G3** | PARTIAL / FAIL | No `diff.command` any more, so nothing pastes the markers in ✓. `yours` is now the whole OCR'd block with gutter numbers and OCR errors (`(req, res) = {`, `res. json`), so still "no safe patch". The advice still says "keep the logout route", which causes a 2nd conflict |
| **P1, P2** | patch only via a 2nd Opus call | **Unchanged**. `session._code_excerpt` cuts the `.ipynb` at 6000 chars, so the JSON no longer parses and `notebook_code` returns it unchanged. Verified: the full P1 file → 443 chars of cell sources; the 6000-char cut → raw JSON. P1's `expected` came back JSON-escaped and `yours` was empty again |
| **P3** | patch via a 2nd Opus call | ✓ The card's own diff now applies inside the notebook cell (notebook-aware `apply_fix`) |
| **P2** | says `axis` | still says `axis` |
| **R3** | 9.8 s card | 6.3 s card |
| **R1** | template (no error on screen) | unchanged; this is a gate issue, since nothing errors |

After the fixes:
- **Diagnosis:** 6 right, 2 partial, 1 wrong (R1, forced). **Line:** 8/9. **Patch correct after re-run:** 7/9 (G1 and G3 fail).
- **Latency:** pre-Opus time is now 2.0–3.1 s, worst card 7.4 s (was 9.8). But web grounding now runs on every case, because screen errors feed it, and 6 of 8 cards hit the 3 s cap. So the median card is 6.9 s (was 6.7).
- **Web sources:** on-topic for git. Still generic for React and pandas ("webpack compiled with 1 error", generic TypeError Q&A).

## Cases

Every output on screen is real:
- git 2.50 ran each rebase.
- nbclient executed the notebook with pandas 3.1.1, which `pandas>=2.0` installs today.
- The React component ran under react-test-renderer 18 with fake timers.

Only the CRA dev-server banner (react-scripts 5 format) is written by hand, with the line and column of the undefined name computed from the file.

Each screen is drawn as VS Code + Terminal (+ Chrome for React) at Retina scale. It is then OCR'd by the engine's own `observe_image`: Apple Vision, window assignment and reading order. That gives the same `ScreenObservation` shape and the same OCR noise as a live frame. Notebook outputs follow VS Code's default `textLineLimit=30`, so long tracebacks show their first 30 lines and the "Output is truncated" notice.

Each case passes the cursor (`cursor.under`) and the `ScreenContext` exactly as `session._coach` builds them. Screens and OCR: `cases/<id>/screen.png`, `screen.json` (fixture sidecar), `obs.json`. Full per-case records: `results/<id>.json` (card, `_meta` triage/route/usage, inputs, patch, check output, gates before/after).

## Re-run

```bash
uv venv -p 3.12 .venv && uv pip install -p .venv/bin/python -e "server[dev]" pandas nbclient nbformat ipykernel
(mkdir -p /tmp/reactenv && cd /tmp/reactenv && npm init -y && npm i react@18.3.1 react-dom@18.3.1 react-test-renderer@18.3.1 esbuild@0.24.2)
REACT_ENV=/tmp/reactenv .venv/bin/python -m evals.coach.run_coach            # 9 cases, live API (~3 min)
.venv/bin/python -m evals.coach.spotlight && .venv/bin/python -m evals.coach.summary
REACT_ENV=/tmp/reactenv .venv/bin/python -m evals.coach.run_engine --layout root   # own engine on :8796
```

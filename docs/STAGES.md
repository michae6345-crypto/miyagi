# Stage-by-stage runs on 4 non-PINN topics (2026-11-14, venue Wi-Fi)

Three runs, newest first:
- **Gemini paid** (14:23–14:29, integration/live 4ff1417: billing on, same key).
- **after** (~14:15, 36eaf92: per-lesson workspaces, human build errors, Bright Data zones live).
- **before** (~14:00, 2cc33e8).

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

## Actions QA: Explain / Show me / Hint / Diagram / Back (integration/live 3123eb6, 15:21–15:40)

Run with `.venv/bin/python scripts/stage_actions.py --screen fixture|real [--only <lesson>]`. It uses one LIVE engine on :8790
with ORCH_SCREEN=1. Each lesson is started from cache; the S8 preflight card is answered with `build`, as a learner would.

At step 1 and step 2 it sends `explain`, `show_me`, `hint` ×3, `diagram` and `back`, one at a time, and records every event for 8 s.
Before the actions it reports `video.state` inside the clip, so the segment timer can't fire mid-test.

Pass criteria:
- Something visible within 1 s: status thinking, a spotlight with a rect, a video.seek, or the card itself.
- The result within 6 s: a card (explain, hint), a diagram (diagram), or a video.seek (show_me, back).
- Every spotlight rect is non-empty and on the 1728×1117 display.
- At most one card per action, and the 3 hints differ.
- No `error` event.
- After `end_lesson`, nothing else for 8 s.

**Screens:**
- **fixture**: `TUT_SCREEN_FIXTURE=server/screen/fixtures/vscode_terminal_flat.png`, i.e. VS Code with `pinn_convection.py` plus a Terminal.
- **real**: the desktop. Code is not visible, but E6's capture fails here anyway (A-1).

**Lessons:**
- PINN hero (AXXnSzmpyoI)
- React useEffect (V8FvyuObouc)
- "notebook": linear regression in numpy (Jj7WD71qQWE, a Jupyter lesson). It stands in for an LLM notebook lesson: both short LLM
  videos tried (NiZdkwx9t5Q 11:00, vXg6XwI3fts 14:09) failed to build with "Couldn't read this video (… long): YouTube is
  rate-limiting caption downloads on this network; Gemini didn't finish watching in time" (soak bug S1, E2).
- PINN convection (unBU1PwCnvQ), fixture only, because its targets (`class PINN(nn.Module):`) are the code in the fixture. This tests
  spotlight rects.

| lesson | screen | step | explain | show_me | hint 1 / 2 / 3 | diagram | back | end_lesson |
|---|---|---|---|---|---|---|---|---|
| PINN hero | fixture | 1 · 2 | ✓ thinking 0 s → card 3.0 s · 2.8 s | ✓ seek 0 s (target not on screen → no spot) | ✓ cards 0 s, all different | ✓ thinking 0 s → `graph` 0 s (prefetched) | ✓ seek 0 s | ✓ |
| React useEffect | fixture | 1 · 2 | ✓ card 2.7 s · 2.4 s | ✓ seek 0 s | ✓ | ✓ `graph` 0 s | ✓ | ✓ |
| notebook (lin. reg.) | fixture | 1 · 2 | ✓ card 2.8 s · 2.6 s | ✓ seek 0 s | ✓ | ✓ `graph` 0 s | ✓ | ✓ |
| PINN convection | fixture | 1 · 2 | ✓ card 2.7 s · 2.8 s | ✓ seek 0 s + **spotlight 328,252 175×27** (step 1; step 2's target isn't on the fixture) | ✓ | ✓ `network` 0 s | ✓ | ✓ |
| PINN hero | real | 1 · 2 | ✓ | ✓ seek only | ✓ | ✓ | ✓ | ✓ |
| React useEffect | real | 1 · 2 | ✓ | ✓ seek only | ✓ | ✓ | ✓ | ✓ |
| notebook (lin. reg.) | real | 1 · 2 | ✓ | ✓ seek only | ✓ | ✓ | ✓ | ✓ |

**Totals:** fixture 45/45 + 15/15 PASS, real 45/45 PASS.
- No duplicate cards and no `error`.
- Nothing after `end_lesson`.
- The one spotlight sent was on-screen and non-empty.

So the engine answers every action at once. The "dead" feeling comes from what the learner can and can't see:

**A-1 · E6 screen (+ E4): on this Mac the screen reader sees nothing, and nobody is told.**
- `server/screen/macos.capture_main_display()` → `Quartz.CGDisplayCreateImage(CGMainDisplayID())` returns `None` on every frame
  in the engine process: `ScreenUnavailableError: display returned no image (asleep, locked, or switching Spaces?)`.
- Meanwhile `screencapture -x` from the same shell captures the screen fine (7 MB PNG), the session is unlocked, and
  `CGPreflightScreenCaptureAccess()` is True.
- `CGDisplayCreateImage` is deprecated on macOS 15+, and this Mac runs Darwin 25.
- Result on the real screen: Show me never spotlights (every `locate_match` raises), screen checks stay "waiting for screen",
  and diagrams and explain cards get no screen context.
- **E4:** the app gets no `error` or screen status, `/state` reports `screen: true`, and the log prints a traceback per frame.
- Fix:
  - **E6:** capture via ScreenCaptureKit (`SCScreenshotManager`), or fall back to `screencapture -x -t png` when
    CGDisplayCreateImage returns None.
  - **E4:** when `reader.status` is `error` / `no_permission`, tell the app once (an error card "Miyagi can't see your screen
    right now"), and make `show_me` say why there's no spotlight.

**A-2 · E5 coach: the hint ladder feels canned.**
- Three presses give levels 0 → 1 → **3**; level 2 ("paper") is skipped every time.
- Level 0, titled "A question first", is an instruction, not a question: "In the first cell, import numpy as np, pandas as pd, and
  matplotlib.pyplot as plt."
- Level 1 is a template that reads oddly: "The tutorial covers Linear model f(x) = wx + b here." / "The tutorial covers Returning a
  cleanup arrow function from useEffect to prevent unmounted state updates here."
- Titles are the same three strings on every step ("A question first", "Rewatch this part", "Compare with the tutorial"), so
  consecutive presses look identical at a glance.
- Fix:
  - Make level 0 an actual question about the step's check.
  - Write level 1 as a sentence with the jump time ("Rewatch 0:44, where he writes f(x) = wx + b").
  - Include level 2 or renumber.
  - Use step-specific titles.

**A-3 · E4 orchestrator (minor): a raw prefix in the human build error.** The new E2 wording reaches the app as
`lesson.build_lesson failed: RuntimeError: Couldn't read this video (11:00 long): …`. `human_build_error` doesn't match it, so the
module/exception prefix leaks. Strip `<module>.<fn> failed: <Exc>:` before showing it.

**Not engine-side (for the app, Adrian):** the engine sends `card` within 0–3 s and `diagram` (kind `graph` / `network`)
instantly for every action. If the app still looks dead, check that it renders `card.kind` hint/explain with `videoJump`, the
`diagram` kind `graph` (new in the contract), and `video.seek` while the video panel is hidden.

### Actions re-check after the fixes, OFFLINE (cost freeze): integration/live 085c832, 15:50–15:56

Both checks made zero API calls. Keys were blanked, HTTP(S) went to a dead proxy, and the engine ran DEMO=1 with
`ORCH_STUBS=coach,diagrams,finder,lesson`. The cached React lesson was autostarted from `ORCH_LESSON`, so there was no
search, preflight or build.

**E5 hint ladder (4a646bd): PASS on 8 lesson-steps.** `.venv/bin/python scripts/stage_hints.py` calls `server.coach.hint()`
directly on the cached PINN hero, React, linear-regression and convection lessons, steps 1 and 2, levels 0–3.
- Level 0 is a question, e.g. "Which sampling library is needed for collocation points?" or "How do you build a 2D space-time
  grid from 1D tensors in PyTorch?".
- Level 1 reads "Rewatch 2:44, where the tutorial shows purpose of pyDOE and Latin Hypercube Sampling.", with
  `videoJump {t: 164, label: "Rewatch 2:44"}`.
- Three presses give levels 0 → 1 → **2** ("Key idea").
- Titles are step-specific ("Question · Install pyDOE and import…").
- No level repeats another.
- Nit (E5): when level 0 is built from a check label, it reads "Does your output show “Imports numpy as np” yet? If not, what
  step produces it?". A check label isn't program output; better: "Have you imported numpy as np yet?".

**E4 screen-down notice (27c1804): PASS, with one timing FAIL.** Real screen; E6's capture still returns no image on 085c832.
- On a lesson start with a dead screen, the app gets one `error`, "Miyagi can't see your screen right now, so screen checks and
  Show me are paused.", at 13.5 s. It's sent once in 50 s (no repeat).
- **FAIL:** `show_me` sends `video.seek` + `video.play` at 0 s, but the "I can't see your screen" card only arrives at **8.5 s**.
  `_show_where()` first runs `locate`, which tries a fresh capture and blocks ~8.5 s before "locate failed".
- Fix (E4): in `show_me`, check `screen_down_reason()` *before* `_show_where()` and send the card at once. Or have the screen
  bridge's `locate` return None immediately while `reader.status` is `error`.

**E6 capture is still dead on this Mac.** `capture_main_display()` raises `ScreenUnavailableError` on 085c832, the same as
before; see A-1.

### Real-screen spotlights after E6's capture fix, OFFLINE: integration/live b37a767 (includes a0e1ecd / e23a751), 15:57–16:02

Zero API calls: keys blanked, dead proxy, DEMO=1 + `ORCH_STUBS=coach,diagrams,finder,lesson`. Each lesson was autostarted
from a scratch copy of the cached React lesson whose step-1 target is text that is on the screen right now. Script:
`scripts/stage_spotlight.py <lesson.json>`. The test changed nothing on the screen; Michael was using the Mac at the time.

- **Capture works.**
  - The reader captures in 0.36–0.82 s per frame, `status ok`, `source live`.
  - ScreenCaptureKit is refused for the engine process ("SCStreamErrorDomain -3801: The user declined TCCs for application,
    window, display capture"), so E6's fallback `screencapture` + overlay masking does the work.
  - `macos.capture_main_display()` (CG) still returns None, but it's now the last resort.
  - To get the SCK path (overlay left out), grant Screen Recording to the app that runs the engine.
- **Exact text target → real rect: PASS.** Target `{app: Code, match: "Welcome"}` (VS Code's tab). `show_me` → `spotlight` at
  0.0 s, rect `{x: 69.3, y: 71.8, w: 74.8, h: 24.6}`, `matched: "Welcome"`, `app: Code`. It's on-screen and non-empty, and the
  same on the second press.
- **Target not on screen → window fallback: PASS.** The target was `{app: Claude, match: "integration/live"}`, but by test time the
  screen had changed. `show_me` → `spotlight` at 0.0 s around the visible VS Code window, rect `{0, 33, 865×1010}` (the window's
  exact frame), with no match text.
- No `error` and no screen-down notice while capture works.
- **Still open (E4):** `show_me` still calls `_show_where()` → `locate` *before* checking `screen_down_reason()`. When capture is
  down, the "I can't see your screen" card comes ~8.5 s late (measured on 085c832). I couldn't re-test this now that capture works.

## Soak: 10 topics back to back, integration/live 9f89e04, Gemini paid, 14:44–15:07

Run with `.venv/bin/python scripts/stage_soak.py [--open] [--only "topic[=pinned url]"]`. One LIVE engine on :8790 with default
models and empty caches. Per topic it does `learn` → `build_lesson`(the finder's final #1, or the pinned URL) → waits for
`lesson.ready` (fails on > 120 s with no event at all) → waits for the setup card → `end_lesson`, and asserts a clean idle
before the next topic. Records go to `demo/runs/stage-soak.jsonl`.

The first pass ran with ORCH_OPEN_WORKSPACE=0, so the engine sends no setup card. The setup column comes from a second pass with
`--open`: same lessons from cache, and VS Code still opens only on the learner's `open_editor`.

| # | topic | search first · done (videos) | pick (kind, length) | build path | "fitting checks" starts at | full lesson | steps | builtBy | setup card (2nd pass) | end_lesson |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | build an LLM from scratch (pinned Karpathy kCc8FmEb1nY) | 3.5 · 18.3 s (17) | "Let's build GPT: from scratch, in code, spelled out." (video, 1:56:20) | Gemini timed out; transcript failed | — | **FAILED 75.0 s**: "Building this lesson is taking too long. Try again, or pick another video." | — | — | — | clean |
| 2 | react useEffect cleanup | 4.2 · 12.0 s (17) | "React useEffect Cleanup Function" (video, 5:38) | Gemini watched + Claude adapted | 34.1 s | **OK 45.6 s** | 5 | gemini | editor ✓ · vscode, node, chrome (missing) | clean |
| 3 | pandas groupby | 3.5 · 14.4 s (15) | "Mastering Pandas .groupby() in 10 Minutes!" (video, 10:27) | Gemini + Claude | 50.1 s | **OK 62.9 s** | 10 | gemini | editor ✓ · vscode, python, pandas/numpy/ipykernel (missing) | clean |
| 4 | git rebase interactive | 3.5 · 15.7 s (18) | "git interactive rebase - Undo, Edit & Squash…" (video, 7:52) | Gemini + Claude | 50.1 s | **OK 57.7 s** | 5 | gemini | "Ready to go" · vscode, git | clean |
| 5 | fastapi crud api | 5.2 · 18.3 s (22) | "How to Build a FastAPI SQLite REST API in Python \| CRUD" (video, 14:26) | Gemini + Claude | 57.1 s | **OK 62.9 s** | 7 | gemini | editor ✓ · vscode, python, fastapi/uvicorn/sqlalchemy/pydantic (missing) | clean |
| 6 | rust cli with clap | 4.4 · 17.5 s (12) | "Build a Rust CLI Tool from Scratch (clap, serde, anyhow)" (video, 12:59) | Gemini timed out; transcript failed | — | **FAILED 75.0 s, twice** (same message as #1) | — | — | — | clean |
| 6b | rust cli with clap, pinned the 5:46 video (fD9ptABVQbI) | (cached) | "Rust Command Line Argument Parsing (A Better Way With Clap)" (video, 5:46) | Gemini + Claude | 37.2 s | **OK 46.6 s** | 5 | gemini | editor ✓ · vscode, rust (missing) | clean |
| 7 | docker compose for a node app | 3.5 · 16.3 s (23) | "Docker Compose Full Stack App: React, Node.js & PostgreSQL" (video, 9:20) | Gemini + Claude | 43.1 s ("Steps ready") | **OK 61.4 s** | 8 | gemini | editor ✓ · vscode, docker (missing), node | clean |
| 8 | make an AI agent with no code | 4.0 · 14.2 s (23) | "How to Build Your First AI Agent in Claude Code (It Runs Your Week)" (video, 19:23) | Gemini + Claude | 50.1 s | **OK 57.9 s** | 9 | gemini | **no editor** (`editorNeeded: false`, no open_editor button) · claude-desktop (missing), claude-code | clean |
| 9 | linear regression in numpy | 4.5 · 14.7 s (18) | "Linear Regression FROM SCRATCH (no scikit-learn, just math)" (video, 10:24) | Gemini + Claude | 58.1 s | **OK 79.1 s** | 7 | gemini | editor ✓ · vscode, python, ipykernel/numpy/pandas/matplotlib (missing) | clean |
| 10 | css flexbox layout | 3.5 · 20.5 s (13) | "Learn CSS Flexbox in 20 Minutes (Course)" (video, 20:37) | Gemini + Claude | 49.1 s | **OK 57.4 s** | 10 | gemini | "Ready to go" · vscode | clean |

**Totals:**
- 8 of 10 topics built: 45–79 s to the full lesson, every one Gemini-watched (`gemini-4-hydrogen`) and Claude-adapted (`claude-opus-5-5`).
- No crash, no hang over 120 s.
- No wrong-topic lesson: every lesson title and its steps name the topic's terms, e.g. rebase steps "Edit / Split / Squash".
- No PINN leak; every workdir is under `~/miyagi/lessons/<slug>`.
- 10 of 10 `end_lesson` calls were clean.
- Search: 3.5–5.2 s to the first row, 12–20.5 s done, 12–23 videos per topic.
- No preflight card exists on integration/live yet.

### Bugs from the soak

**S1 · E2 lesson: any video Gemini can't finish in 75 s fails to build, and nothing falls back.**
- Karpathy (1:56:20) and the rust pick (12:59, a dense code-along) both died at exactly 75.0 s, rust twice:
  - `gemini video pass failed: no answer within 75s`
  - the transcript path had already failed: `brightdata captions: Bright Data returned an empty body; timedtext: Client error '429 Too Many Requests'`
- A 5:46 rust video built in 46.6 s, and a 20:37 CSS video in 57.4 s, so duration alone doesn't predict the failure.
- Fix:
  - Once the Claude transcript draft has failed, let Gemini keep going up to `ORCH_BUILD_TIMEOUT_S` instead of the 75 s race cap
    (`GEMINI_VIDEO_TIMEOUT_S`).
  - For videos over ~30 min, use a lower fps or a segmented pass.
  - When it still fails, the error should suggest the finder's next shorter video, not just "pick another video".
- Owner: E2 (the E4 message is fine).

**S2 · E7 finder / ranking: the pick for "no code" is a Claude Code video.**
- "make an AI agent with no code" picked "How to Build Your First AI Agent in Claude Code" (score 93) over "From Zero to Your
  First AI Agent in 25 Minutes (No Coding)" (91) and "Build Your First AI Agent in 20 Minutes (No Coding)" (91).
- The lesson itself works (no editor; the setup card needs Claude Desktop + Claude Code), so this is a judgment call, not a crash.
- Suggest: boost results whose title or skim matches the "no code" constraint.

**S3 · E4 orchestrator (minor): the "Steps ready" stage is almost never visible.**
- `steps_ready` is replaced by `adapting` within the same second, so the 1 s ticker showed "Steps ready" in 1 of 8 builds.
- The app has no "first steps" moment: the learner waits 45–79 s for everything.
- Suggest: emit a `lesson.building` the moment the stage changes, and optionally send the draft step titles early.

**S4 · E4 orchestrator (minor): `lesson.builtBy` isn't in `lesson.ready`.** The app's `lesson.ready` payload has only
id/title/sources, so the app can't show "watched the video" vs "read the transcript". Add `builtBy` to the payload, which is a
contract-safe new field.

**Note:** setup check items are what's missing on *this* Mac (no chrome, docker, rust, pandas, etc.), which is correct behavior.

## Lifecycle: end lesson and resume

`.venv/bin/python scripts/stage_lifecycle.py end|resume` runs each case on the :8790 engine with an app-like WebSocket client, records every event and asserts the cleanup. Lessons come from the builders' caches, so each start takes seconds. Results are appended to `demo/runs/stage-lifecycle.jsonl`.

### end_lesson: integration/live fc56c0f, 14:35

What every case asserts after ending:
- `lesson.ended` arrives with the right `reason`, followed by `status idle`.
- `spotlight {clear}` and `video.pause` are sent.
- For 3–6 s afterwards, no diagram, card, offtrack, check, step or video event arrives.
- `/state` shows phase idle, no lesson and no step.
- A newly connected client's snapshot is only `[status]`.
- A fresh lesson starts afterwards at step index 0 with pending checks.

| case | result | event sequence (relative to the client's start) |
|---|---|---|
| `end_lesson` over WS, diagram request in flight | **FAIL** (1 of 9 checks) | 0.14 card hint · 0.17 status thinking · 0.47 spotlight clear · 0.47 video.pause · 0.47 lesson.ended `end_lesson` · 0.47 status idle · **3.92 diagram** ("Timer renders, then the effect runs once") · **3.92 status watching** · 7.58 lesson.ready (fresh) · step.started #1 · check.updated ×2 · video.seek · video.play · status watching |
| `curl -X POST :8790/end`, explain request in flight | **FAIL** (1 of 10 checks) | 7.64 status thinking · 7.94 spotlight clear · video.pause · lesson.ended `POST /end` · status idle · **10.91 card explain** ("Timer state with an interval effect") · **10.91 status watching**. POST /end with nothing running: `{"ok": true, "ended": null}` (it emits another lesson.ended + idle, which is harmless). Then a fresh lesson.ready + step.started #1 |
| new `learn` while a lesson runs | **PASS** | 15.12 card hint · 15.42 spotlight clear · video.pause · lesson.ended `new lesson` · status idle · thinking · search.done · idle · 19.48 lesson.ready (git) · step.started #1 |
| `end_lesson` while a lesson is being built (extra) | **PASS** | 34.61 status thinking (building) · 37.66 lesson.ended `end_lesson` · status idle. Nothing afterwards: no lesson.ready, progress or error |

### end_lesson re-run: integration/live fa6bd86 (includes 1d21923 "diagrams never cross lessons; end_lesson idempotent"), 14:40

| case | fc56c0f | fa6bd86 | what changed |
|---|---|---|---|
| `end_lesson` over WS, diagram request in flight | FAIL | **PASS** | no diagram after `lesson.ended` anymore (0.48 s lesson.ended, then quiet for 6 s) |
| `POST /end`, explain request in flight | FAIL | **FAIL** | 7.96 lesson.ended `POST /end` · status idle · **10.60 card explain** ("Timer state driven by an interval") · **10.60 status watching** |
| new `learn` while a lesson runs | PASS | **PASS** | |
| `end_lesson` mid-build | PASS | **PASS** | |

### end_lesson re-run: integration/live 9f89e04 (includes 148433b "lesson epoch"), 14:42: **all 4 PASS**

| case | fc56c0f | fa6bd86 | 9f89e04 |
|---|---|---|---|
| `end_lesson` over WS, diagram in flight | FAIL | PASS | **PASS** |
| `POST /end`, explain in flight | FAIL | FAIL | **PASS**: lesson.ended at 7.96 s, then no card/diagram/status for 6 s; a new client's snapshot is `[status]` |
| new `learn` while a lesson runs | PASS | PASS | **PASS** |
| `end_lesson` mid-build | PASS | PASS | **PASS** |

**L1 is fixed by 148433b.** The history is kept below.

**L1 (fixed in 148433b) · E4 orchestrator: an explain/ask card in flight lands after the lesson ended (the diagram part is fixed).**
- `session._action`'s `explain` / `ask` branch awaits `m.explain(...)`, then emits `card` and
  `status watching|offtrack|passed` without checking the lesson is still the same one.
- The app shows a card for a lesson that's gone and goes back to "watching" while the engine is idle.
- Fix (same as for diagrams): `gen = self.step_gen` before the await, and drop the card and the status update if
  `gen != self.step_gen`. Do the same for `hint` if it ever becomes async.
- Minor: `POST /end` with nothing running still emits `lesson.ended {reason: "POST /end"}` (no lessonId) + `status idle`. That's
  harmless, but the app may flash its "lesson ended" UI.

### resume: integration/live fa6bd86 (S7), 14:40

Setup for each case: start a lesson, `/debug/pass` to step 2, report `video.state {t: start+7}` (80 s), then disconnect.
The engine offers the card only when the app returns after ≥ `ORCH_RESUME_AFTER_S` (10 s) to a lesson it already showed.

| case | result | event sequence |
|---|---|---|
| reconnect after 12 s away → card → `resume` → `end_lesson` | **PASS** (15/15) | snapshot: `video.pause` · `card resume` "Continue where you left off?" ("React useEffect Cleanup Tutorial · step 2: Toggle Timer in App component", actions `resume`, `end_lesson`), with no step.started, video.seek or video.play. `action resume`: lesson.ready · step.started #2 s2 (same step) · check.updated · `video.seek {t: 80.0, play: true}` (same position) · status watching. `action end_lesson`: spotlight clear · video.pause · lesson.ended `end_lesson` · status idle, then quiet for 3 s; /state idle; a new client sees `[status]` |
| quick reconnect (2 s blip) | **PASS** | no card: lesson.ready · step.started #2 s2 · check.updated · status watching (continues as designed) |
| **engine restart while away**, then reconnect | **FAIL** | after the restart `/state` is phase idle, no lesson, no step; the returning app's snapshot is just `status idle`, with no resume card |

**L2 · E4 orchestrator: resume doesn't survive an engine restart.**
- The lesson, step index, check states and `video_t` live only in `LessonSession` memory.
- A restart (crash, `scripts/miyagi-engine.sh` re-run, laptop sleep) loses the lesson, so the resume card never comes.
- Fix:
  - Persist a small session file on every step change and on each `video.state` (throttled): lesson id or graph path, step
    index, check states, `video_t`, `seen_lesson`. Put it in e.g. `~/miyagi/session.json` or `demo/runs/session.json`.
  - On boot, load it, set `awaiting_resume = True` and `seen_lesson`, so the first app connection gets the card.
  - Delete the file on `end_lesson`.

## "Just teach me" acceptance check (lesson mode), 2026-11-14 16:00–17:30

`scripts/stage_lessonmode.py` (offline, **0 API calls**) runs the real Engine in-process: DEMO=1, finder/lesson/diagrams stubbed,
the coach real but with no key, and HTTP(S) going to a dead proxy. The screen is the real ScreenReader on rendered VS Code
screenshots (Apple Vision OCR, local), with the terminal panel open or closed. Each step shows the editor before (held 22 s) and
after the step's work. Editor commands are recorded, never run, and S2's Accessibility snapshot and real-window wrong-folder
detector are stubbed out. Lesson: cached `text-c541a8d6` (7-step Python calculator).

Items:
- (a) one spotlight per step, re-sent only after a > 12 px move, at most one per 2 s
- (b) run step boxes the terminal panel, or says "Open the terminal: ⌃`"; typing step boxes the target line; never the tab/breadcrumb row
- (c) no offtrack/auto-card in a step's first 20 s and never two within 8 s (hub: a run step's "Run it" offer is exempt)
- (d) a run step never starts while its file is empty (hub: Skip twice is the learner's choice)
- (e) editor opened once, no second `-n`, no Cursor
- (f) instructions: one sentence, ≤ 10 words, no absolute path or mkdir
- (g) box clears when VS Code isn't frontmost and comes back on return
- (h) "Save with ⌘S" when the title shows ●
- (i) wrong-folder card with open_editor
- (j) Do it for me / Run it for me on the first help card
- plus: the screen-down card ≤ 1 s after show_me

| integration/live | terminal | a | b | c | d | e | f | g | h | i | j | screen-down |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 3875eec | open | FAIL (s7: 2 boxes 0.3 s apart) | PASS | FAIL ("Looks done?" +0 s) | PASS | PASS | PASS | — | — | — | — | PASS |
| 3875eec | closed | FAIL | FAIL (no "⌃`"; s7 boxes the tab row) | FAIL | FAIL (s2 started on an empty file) | PASS | PASS | — | — | — | — | PASS |
| 72b6da0 (E4 round 2) | open | PASS | PASS | PASS | PASS | PASS | PASS | FAIL (box never returns) | PASS (2.6 s) | PASS (2.5 s) | PASS | PASS |
| 054aa06 | open | PASS | PASS | FAIL→exempt ("Run it" offer) | PASS | PASS | PASS | FAIL | PASS (2.2 s) | PASS (1.5 s, S2 detector off) | PASS | PASS |
| **c3c9019 (last)** | open | PASS | PASS | PASS | PASS | PASS | PASS | **FAIL** | PASS | PASS | PASS | PASS |
| **c3c9019 (last)** | closed | FAIL* | PASS | PASS | FAIL* | PASS | PASS | — | — | — | PASS | PASS |

\* Harness artifact: when the engine refuses to start the run step on an empty file (E4's save-first redirect back to s1 with
"calculator.py is still empty", which is correct), the harness's start-wait path still jumps with the debug `goto`. The second jump
starts s2 (E4 redirects once per run step) and leaves a short s1 row with no box. The fix for next time: wait-path → `skip_step`.

**Open for E4:**
- (g): `_spot_follows_app` clears the box but doesn't reset `spot_rect` / `_spot_caption`, so `_show_spot(steady=True)` won't
  re-send the same box when VS Code is frontmost again.
- s2, s3 and s5 don't advance by themselves within 12 s of the "done" screen.
- Live build only: crash at `session.py:2123` (`re.escape(first[0])` with no `diff.yours`).
- Live build only: s1 box on the tab row.

**Live tier** (`scripts/stage_lessonmode_live.py`, needs `--approved`; OFF since 17:20, cost freeze at $84 of a $100 cap):
- Setup: Claude key, LESSON_ENGINE=claude, Gemini/Google blank; Anthropic SDK hook logs tokens and $ by model and caller; $1 cap per round.
- Round 1, "build a to-do list app in python": first step at 11.6 s, full lesson at 43.6 s, 6 steps, builtBy claude, **$0.265**.
  - E5 coach $0.134
  - E2 research (Sonnet + 4 web searches) $0.117
  - E2 steps $0.014
- E2 rule FAIL: typing steps keep Terminal checks (they also carry a run_command), but the instruction only says "type …". The
  coach then repeated "Program has not been run yet".
- Topic 2 was stopped seconds after start (no result, spend unrecorded).

## Run 3: Gemini paid, integration/live 4ff1417, 14:23–14:29

Setup:
- Own LIVE engine on :8790, `--no-screen`.
- **E2's default models, no env overrides**, no TUT_WORKDIR. Michael's :8787 engine was not touched.
- Every earlier finder and lesson cache in this worktree was moved aside, so every search and build ran live.
- Picked = the finder's final rows[0] (`stage build 1`).

### Before / after / Gemini paid

| topic | search: before / after / **paid** (first row · done · videos) | build: before / after / **paid** | steps (paid) | PINN leak (paid) |
|---|---|---|---|---|
| react useEffect cleanup | 3.4 s · 9.0 s · 10 / 4.0 · 17.7 · 6 / **3.9 · 12.2 · 23** | OK 82.7 s (PINN-poisoned) / FAILED 5.0 s / **OK 44.3 s** | 4 | none |
| git rebase interactive | 3.7 · 11.7 · 10 / 3.6 · 18.3 · 8 / **3.0 · 12.4 · 10** | OK 56.9 s (not about `rebase -i`) / FAILED 5.5 s / **OK 69.1 s** | 5 | none |
| pandas groupby tutorial | 3.7 · 5.3 · **0** / 7.2 · 18.3 · 8 / **3.1 · 13.3 · 18** | FAILED 3.2 s / FAILED 5.8 s / **OK 50.9 s** | 8 | none |
| train a diffusion model in pytorch | 2.4 · 16.7 · 11 / 6.0 · 18.3 · 1 / **3.1 · 13.3 · 16** | FAILED 2.1 s / FAILED 5.6 s / **FAILED 45.0 s** ("taking too long") | — | — |

### Gemini paid: per topic

Every build that worked took the same path: **Gemini watched the video** (`gemini-4-hydrogen`) and **Claude fit the checks** (`claude-opus-5-5`, two passes). The Claude transcript path, which races Gemini, failed on every build within ~5 s: Bright Data returns an empty body for both the watch page and the captions, and `timedtext` returns 429.

Per-stage seconds come from the `lesson.building` stage changes: *watching* → *fitting the checks* → *second pass* → *setting up the project folder* → *ready*.

| topic | search first · done | picked video | build | watching | fit checks | 2nd pass | project folder | result | steps | checks |
|---|---|---|---|---|---|---|---|---|---|---|
| react useEffect cleanup | 3.9 s · 12.2 s (36 rows) | "useEffect with Clean Up in React \| React JS Tutorial" (Rapid Tutor, 6:02, ZipmUa9N7Os) | gemini + claude adapt | 33.1 s | 4.0 s | 4.7 s | 2.5 s | **OK 44.3 s** | 4 | screen regexes on Code (`setInterval\(`, `clearInterval\(`, `return\s*\(\)\s*=>`, `setSeconds\(\s*0\s*\)`) + Terminal `Compiled successfully` |
| git rebase interactive | 3.0 s · 12.4 s (30 rows) | "git interactive rebase - Undo, Edit & Squash git commits with a single command" (Philomatics, 7:52, 42392W7SgnE) | gemini + claude adapt | 34.0 s | 6.0 s | 10.2 s | **18.9 s** | **OK 69.1 s** | 5 | Terminal OCR of git's own output (`Waiting for your editor`, `Stopped at [0-9a-f]+`, `Successfully rebased`, `Unstaged changes after reset`) + `squash [0-9a-f]{5,}` in the todo file. Now really about `rebase -i` |
| pandas groupby tutorial | 3.1 s · 13.3 s (36 rows) | "Mastering Pandas .groupby() in 10 Minutes!" (Onur Baltaci, 10:27, _zsKKcnX-qE) | gemini + claude adapt | 36.1 s | 7.0 s | 5.5 s | 2.3 s | **OK 50.9 s** | 8 | learner-generic Code regexes (`groupby\(\s*\[`, `groupby\(.*\.agg\(`, `apply\(\s*lambda`, `\.dt\.month`) + output shapes (`dtype:\s*float64`) |
| train a diffusion model in pytorch | 3.1 s · 13.3 s (47 rows) | #1 "Coding a Diffusion Model From Scratch in PyTorch (DDPM)" (28:30, TgTQE_muXec). Also tried #3, "Diffusion Models \| PyTorch Implementation" (22:26, TBCRlnwJtZU) | gemini (timed out); claude transcript failed | 45.0 s → cut | — | — | — | **FAILED 45.0 s** both times | — | — |

**Diffusion's exact error.**
- App message: `error: "Building this lesson is taking too long. Try again, or pick another video."`, then
  `lesson.building {failed: true}`.
- Engine log: `server.lesson WARNING claude video pass failed: no transcript for TgTQE_muXec: brightdata watch page: Bright Data returned an empty body; brightdata captions: Bright Data returned an empty body; timedtext: Client error '429 Too Many Requests'` (at 5 s),
  then `server.lesson WARNING gemini video pass failed: no answer within 45s`.
- Search's other video candidates for this topic are 22–224 min long, so on this network no diffusion lesson can be built
  right now.

### Still broken (Gemini paid)

**P1 · E2 lesson: long videos (≳ 20 min) can never build here.**
- `server/lesson/builder.py`: `GEMINI_VIDEO_TIMEOUT_S = 45.0` caps Gemini's video pass. The comment says "past this the Claude
  transcript path is faster", but that path dies in ~5 s on this network, and the cap still kills Gemini at 45 s.
- The working builds needed 33–36 s to watch 6–10 min videos, so 22–28 min videos need more.
- Fix:
  - Only enforce the cap while the Claude draft is still alive (or ready). Once Claude has failed, let Gemini run up to
    `ORCH_BUILD_TIMEOUT_S` (300 s).
  - Scale the cap with `durationS` (the finder already knows it).
  - Or lower `LESSON_GEMINI_FPS` further for long videos.
- Owner: E2. The error message is fine (E4).

**P2 · E2 lesson / Bright Data: the transcript path is dead on this network.** Every build: `Bright Data returned an empty body`
(watch page and captions), then `timedtext` 429. The paid key makes Gemini carry every build alone. Fix: see A1 (log the
unlocker's HTTP status; the zone may need YouTube or JS rendering enabled).

**P3 · E4 orchestrator: "Setting up your project folder" took 18.9 s on git** (2.3–2.5 s on the others). That's S2's Claude
starter files. Worth a cap, or doing it after `lesson.ready` so the learner can start watching.

**Fixed since the last run:**
- **A3:** the YouTube search fallback works again. No `youtube failed` notes; 10–23 videos per topic.
- **A5:** no `google.com/goto` URLs in any result.

**Still open:**
- **F3 (E4):** the app still only sees pre-skim scores (react #1: 82 seen vs 93 final; git: 85 vs 94), and the default pick is the
  first streamed row.
- **F9 (E4):** `learn_url` has no goal.
- **A4 (S4/E4): reproduced on 4ff1417.** `stage run --send diagram` on the pandas lesson's step s1 returned the *React* diagram
  ("Timer mounts once, and the effect starts setInterval…") from two lessons earlier, with `kind: "graph"`. The cache key
  needs the lesson id, and `"graph"` isn't in the contract.

## Re-run (after): integration/live 36eaf92, 14:15–14:18

Setup:
- Default config: own LIVE engine on :8790, `--no-screen`, no TUT_WORKDIR, no model overrides. Michael's :8787 engine was not touched.
- Gemini was at daily quota, as announced. The finder and lesson caches from the first run were moved aside, so every search and
  build ran live.
- `stage build 1` = the finder's final rows[0].

### Before / after

| topic | search before (first / done, rows, videos) | search after | build before (default config) | build after (default config) | workdir after | PINN leak before → after |
|---|---|---|---|---|---|---|
| react useEffect cleanup | 3.4 / 9.0 s, 28 rows, 10 videos | 4.0 / 17.7 s, 17 rows, 6 videos | OK 82.7 s, 5 steps | **FAILED 5.0 s**: "Couldn't watch this video: Gemini's quota is used up and YouTube is rate-limiting this network…" | n/a (no build) | SEVERE → none |
| git rebase interactive | 3.7 / 11.7 s, 30 rows, 10 videos | 3.6 / 18.3 s, 26 rows, 8 videos | OK 56.9 s, 10 steps (no `rebase -i` step) | **FAILED 5.5 s**: "Couldn't get this video's transcript: YouTube is rate-limiting this network…" | n/a | workdir → none |
| pandas groupby tutorial | 3.7 / 5.3 s, 19 rows, **0 videos** (retry 30 rows) | 7.2 / 18.3 s, 24 rows, 8 videos | FAILED 3.2 s (Gemini 429 + transcript blocked) | **FAILED 5.8 s**, same message as git | n/a | workdir → none |
| train a diffusion model in pytorch | 2.4 / 16.7 s, 37 rows, 11 videos | 6.0 / 18.3 s, 30 rows, **1 video** | FAILED 2.1 s (`Gemini call failed on []: None`) | **FAILED 5.6 s**, same message as git | n/a | SEVERE → none |

**Picked (#1, the finder's best video):**
- react: "React Hooks Tutorial - 9 - useEffect cleanUp functions" (MJy9SAldcpM)
- git: "Git Rebase Interactive :: A Practical Example" (tukOm3Afd8s)
- pandas: "Python Pandas Tutorial 7. Group By (Split Apply Combine)" (Wb2Tp35dZ-I)
- diffusion: "Train Diffusion Models - Line by line code example" (KiP-q8LkmQ8)

**Why every build failed (engine log), the same chain each time:**
1. Gemini video pass: `gemini-4-hydrogen`, `gemini-3.7-flash`, `gemini-3.6-flash` and `gemini-3.5-flash` all return 429 RESOURCE_EXHAUSTED.
   From the second build on, the error is `Gemini call failed on []: None` (all marked exhausted in-process).
2. Claude transcript path:
   - `brightdata watch page: Bright Data returned an empty body`
   - `brightdata captions: Bright Data returned an empty body`
   - `timedtext: Client error '429 Too Many Requests' for url 'https://www.youtube.com/api/timedtext?...'`

Progress is honest now: the stage names show ("Couldn't watch the video; reading the transcript instead"), and every failure ended
with `error` + `lesson.building {failed: true}` + idle in ≤ 6 s.

**Workspace fix verified on the cached video drafts.** I restored this morning's raw drafts for react (aKOQtGLT-Yk) and DDPM
(TgTQE_muXec), so only the adapt pass runs. No model was forced: the default chain fell through to Claude.

| lesson | build | workdir | adapt | leak | checks |
|---|---|---|---|---|---|
| react, "useEffect Cleanup with AbortController" | OK 10.7 s, 5 steps | `~/miyagi/lessons/useeffect-cleanup-with-abortcontroller-f5383c` (README.md only) | **claude-opus-5-5** (the old 400 is gone) | none | learner-generic now: `new\s+AbortController\(\)`, `signal\s*:\s*\w+\.signal`, `=>\s*\w+\.abort\(\)` |
| DDPM, "Implementing DDPM from Scratch" | OK 5.7 s, 4 steps | `~/miyagi/lessons/implementing-ddpm-from-scratch-c10798` | claude-opus-5-5 | none | clean (`q_sample`, `cumprod(`, `datasets.MNIST(`). `T\s*=\s*\d+` is generic. Still no training step, because the draft came from flash-lite |

### Status of the first run's findings

| # | finding | status |
|---|---|---|
| F1 | every lesson adapted to `demo/pinn-lab` | **fixed** (verified above) |
| F2 | build dies when Gemini quota is gone | **still broken**, now with a human error instead of a hang. No flash-lite in the default video chain, and the transcript path is blocked (see A1, A2) |
| F3 | first streamed row is the default pick; skim scores never reach the app | **still open**: first streamed row was a repo/notebook in 4/4 topics, and the app saw 82 vs the final 90 (react), 78 vs 91 (pandas) |
| F4 | 0-video search cached | not reproduced. Diffusion returned **1** video (see A3) |
| F5 | Claude adapt 400 (schema) | **fixed** (claude-opus-5-5 adapted both lessons) |
| F6 | Gemini daily quota | still the blocker |
| F7 | 0-view / new video ranked first | not seen this run (the picks have views). Not re-verified |
| F8 | over-literal checks | **improved** (patterns are structure-level now) |
| F9 | `learn_url` has no goal | still open |
| F10 | external pkill | no kill this run |
| minor | `diagrams: missing` | **fixed** (`diagrams: real`), but see A4 |

### Still broken after the fixes (owners)

**A1 · E2 lesson (+ ops): no build can succeed on this network without Gemini quota.**
- The transcript fallback's three sources all fail: Bright Data watch page = empty body, Bright Data captions = empty body,
  direct timedtext = 429.
- The video chain has no `gemini-3.1-flash-lite` / `gemini-3.5-flash-lite` (it worked at 14:07 today).
- Once every model is exhausted the error is still `Gemini call failed on []: None`.
- Fix:
  - Find out why the unlocker returns empty bodies for youtube.com (zone needs the "premium domains" / YouTube permission? JS
    rendering?) and log the HTTP status.
  - Add the lite models as the last fallback.
  - Name the exhausted models in the error.
  - For the demo: a paid key, or a phone hotspot (fresh IP for timedtext).

**A2 · E4 orchestrator (human error wording): after the first build, the message drops the Gemini cause.** Builds 2–4 said only
"YouTube is rate-limiting this network". Gemini was also out, but E2's text was `failed on []: None` with no "quota" in it, so
`human_build_error` only matched the YouTube branch. Fix: once E2 names the exhausted models (A1), or if E4 also matches
`failed on []`, say both causes.

**A3 · E7 finder: YouTube search via Bright Data fails, with no direct fallback.**
- Every search noted `youtube failed: RuntimeError: YouTube results page had no ytInitialData`, and the same for `youtube-2`.
- A direct `httpx` GET of the same results URL from this network at 14:17 returned 200 with ytInitialData and 12 videos.
- `sources.youtube_search` only falls back to a direct fetch when the unlocker *raises*, not when it returns a page without
  ytInitialData.
- Result: fewer videos (diffusion 11 → 1; they now come only from other providers) and slower searches (done 5–17 s → 18.3 s
  for all four).
- Fix: if the unlocker page has no ytInitialData, fetch directly. Prefer the direct fetch first for YouTube since it works here.

**A4 · S4 diagrams + E4 orchestrator: diagram from the wrong lesson, and an off-contract `kind`.**
- After switching from the react lesson to DDPM, `stage run --send diagram` on DDPM step s1 returned the React diagram ("The
  function returned from the useEffect callback runs when Home unmounts…").
- Cause: `server/diagrams/build.py:cache_key` = (step id, hash(code + screen), question, kind). Every lesson has an `s1`, and with no
  code and no screen yet the hash is the same, so the cache (and the per-step prefetch) collides across lessons.
- The payload's `kind` is `"graph"`, which isn't in `events.ts` (`"network" | "gradients" | "heatmap"`). Either the contract needs a
  `contract:` PR or the app will drop or misrender it.
- Fix: add the lesson id (or the step title + instructions) to the cache key, and clear the cache on `load_graph`. Add `"graph"`
  to the contract.

**A5 · E7 finder: unresolved Google redirect URLs reach the app.** Bright Data SERP rows come through as
`https://www.google.com/goto?url=CAES…` with `meta "Blog · google.com"` and `verified: True`. That happened in all 4 searches (3 rows
in react). Fix: resolve the `goto` redirect (or decode `url=`) before verifying, and drop the row if it can't be resolved.

**A6 · E7 finder: other degradation noted on each search.**
- Bright Data comment fetches fail with empty messages (`comments for <vid> failed:`).
- Gemini skims time out at 6–7 s.
- Claude triage got a 429 rate_limit_error on pandas, and the Gemini triage fallback a 503.
- Scores fall back to keywords, which is fine, but rows reach the app with pre-skim scores (F3).

**Still open from the first run:**
- F3 (E4): default pick is the first streamed row, and skim re-scores don't reach the app.
- F9 (E4): `learn_url` has no goal.
- The DDPM draft has no training/metric step (E2, flash-lite draft).
- E6's per-second traceback when the display sleeps was not re-checked (ran with `--no-screen`).

## Before: first run (integration/live 2cc33e8, ~14:00)

### Results

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

### Failures (first run)

#### F1 · E4 orchestrator (root cause) + E2 lesson: every lesson is adapted to the PINN workdir — SEVERE
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

#### F2 · E2 lesson: the build dies once the free-tier Gemini models are out of quota (pandas, diffusion)
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

#### F3 · E4 orchestrator (+ E7): the app never gets the finder's final ranking; the default pick is the first streamed row
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

#### F4 · E7 finder: a search with 0 videos was cached for 7 days (pandas, 1st try)
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

#### F5 · E2 lesson: the Claude fallback for the adapt pass always 400s
- **Exact error:** `adapt pass failed (attempt 2): … claude: Claude call failed (400): … 'invalid_request_error', 'message': 'Schemas contains too many optional parameters (26), which would make grammar compil…'`
- **Effect:** once the Gemini flash models are out of quota, there is no adapt fallback. The git lesson shipped attempt 1's graph
  with a validator problem left in.
- **Fix:** simplify the structured-output schema used by `claude.adapt_checks`. Make fields required and nullable instead of
  optional, or split per-check-type schemas, or drop strict tool schema and validate in Python.

#### F6 · E2 lesson / ops: daily Gemini quota disappears after ~2 lesson builds
- **Symptom:**
  - At 14:00 `gemini-3.8-flash` and `gemini-3.7-flash` were already exhausted. After the react and git builds,
    `gemini-3.6-flash`, `gemini-3.5-flash` and `gemini-4-hydrogen` were exhausted too.
  - Each build spends 1 video call plus 1–3 adapt calls. F1 adds 2 extra retries.
- **Fix:** F1 and F2 (the retries and the model chain), plus a paid key or several keys for the demo. Cache the demo lessons
  ahead of time.

#### F7 · E7 finder: ranks a 0-view, 1-day-old video first, and its content doesn't match the title
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

#### F8 · E2 lesson (check authoring): checks are machine-checkable but over-literal; "train" goals get no metric check
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

#### F9 · E4 orchestrator / contract: `learn_url` has no goal
- **Symptom:** `learn_url {url}` builds with `goal = self.query`, the last `learn` query or `""`. A pasted link after a different
  search gets the wrong goal, which drives step framing and the goal-keyed cache.
- **Fix:** add an optional `goal` to `learn_url` (additive contract change). Otherwise reset `self.query` on `learn_url` and let
  E2 derive the goal from the video title.

#### F10 · infra: the stage engine was killed mid-build by an external `pkill`
- **Symptom:** at 14:02:35 the :8790 engine got a clean uvicorn "Shutting down" during the git build. The cause wasn't stage.py:
  the matching pattern was `server.orchestrator.main`. stage.py now launches through `scripts/stage_engine.py`.
- **Suggestion to all sessions:** kill by port (`lsof -ti tcp:8787 | xargs kill`) instead of `pkill -f`.

#### Minor
- **E6 screen:** with the display asleep, the screen reader logs a full traceback every second
  (`ScreenUnavailableError: display returned no image (asleep, locked, or switching Spaces?)`). Log it once per state change.
- **E4:** `diagrams: missing` in `/health` (no `server.diagrams` module on integration/live). The `diagram` action errors in LIVE: `diagram: server.diagrams.build isn't available yet` (verified with `stage run --send diagram`).
- **E7:** Bright Data is still inactive (`zone "serp_api1" not found`, `zone "web_unlocker1" not found`), and Gemini Search
  grounding returns 429 on every search. Both are noted per search, and the finder falls back fine.
- **E5:** the offtrack card for a file-only failure is generic ("Define T, BETA_START, … EPOCHS"). It could quote the failing
  check's expected value (`EPOCHS = 20`).

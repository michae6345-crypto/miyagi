# server/orchestrator (E4): the engine hub

FastAPI app `server.orchestrator.main:app` on **:8787**. It speaks `shared/contracts/events.ts` over WebSocket `/`
(Python mirror: `shared/contracts/events.py`), takes `tut run` events on `POST /ingest`, and owns the lesson state machine.

## Run

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e "server[dev]"
TUT_WORKDIR=/tmp/tut-work .venv/bin/python -m server.orchestrator.main        # engine on :8787 (ORCH_SCREEN=0 to skip the screen reader)
.venv/bin/python -m server.orchestrator.client                                  # print events; type `learn pinn`, `build`, `hint`, ...
.venv/bin/python -m server.orchestrator.client --autopilot --speed 3            # full scripted lesson incl. the β=30 hero loop
.venv/bin/python -m pytest server/orchestrator -q                               # state-machine tests
```

### Live mode (the default): `scripts/miyagi-engine.sh`

```bash
scripts/miyagi-engine.sh          # LIVE on 0.0.0.0:8787; DEMO=1 scripts/miyagi-engine.sh for cached/canned data
```
**LIVE uses only real modules.** `learn` calls `server.finder.search` (streamed), `build_lesson`/`learn_url` call `server.lesson.build_lesson`
(Gemini; E2's `demo/cache/lessons/` makes a known video instant), then live screen checks and the real coach. A missing or failing module sends
an **`error` event** with the reason, never canned data. `lesson.building` reports elapsed time while Gemini works (1–2 min for a long video).
Stubs and fixtures run **only with `DEMO=1`** (or the dev/test flag `ORCH_STUBS`).

The script exports `ORCH_SCREEN=1` (frames ~1/s, OCR only on change, re-evaluate per frame, spotlight via `locate_match`) and
`ORCH_OPEN_WORKSPACE=1` (on `lesson.ready`: `open -a "Visual Studio Code" <workdir>`, falling back to `code <workdir>`; on each `step.started`: `code -r -g <file>:<line>`).
**LIVE starts with no lesson:** it waits for the launcher's `learn`. Each lesson gets its own workspace from S2's `server/workspace`
(`build_workdir(url)` before the build, `prepare(graph, goal)` after it: `~/miyagi/lessons/<slug>` with starter files, shown as "Setting up your project folder"),
opened with `open_editor` (`code -n <dir> -g <file>`). `TUT_WORKDIR` pins one folder for development. If Screen Recording is denied, the script prints exactly where to grant it.
**The stage hero is `scripts/miyagi-demo.sh`:** the same engine with `ORCH_HERO_WORKDIR=demo/pinn-lab ORCH_AUTOSTART=1 ORCH_LESSON_URL=AXXnSzmpyoI`
(E2's cached Toscano lesson; hero failure `lr = 0.3`, see `demo/pinn-lab/README.md`).
No real screen handy? `TUT_SCREEN_FIXTURE=server/screen/fixtures/vscode_terminal_flat.png` replays a saved VS Code + Terminal screenshot.

`demo/recordings/engine-sample.jsonl` is ~60 s of real engine output (OCR, spotlight rects, live coach card, hint/explain, diagram, green) in
`app/mock`'s `{wait, type, payload}` format.

`--autopilot` is a fake learner that drives the **real** state machine. It reports player positions (`video.state`), writes the canned
PINN solution into the workdir step by step, and POSTs simulated training runs to `/ingest`: a β=30 plateau, then `apply_fix`,
then a β-curriculum run. It only writes `pinn_convection.py` and refuses to overwrite one it didn't create, so point
`TUT_WORKDIR` at a scratch folder. **Adrian:** run the engine and the autopilot, then point the app's `ENGINE_URL` at
`ws://localhost:8787` to watch a whole lesson stream in.

## Env

| var | default | meaning |
|---|---|---|
| `ENGINE_PORT` | 8787 | port |
| `ENGINE_HOST` | 127.0.0.1 | bind address; `0.0.0.0` for LAN access (empty = 127.0.0.1) |
| `MIYAGI_ENGINE_TOKEN` | (none) | the app's per-launch token: required on the WebSocket, every POST (also from this Mac) and any request from another machine |
| `MIYAGI_ENGINE_TOKEN_DIR` | `~/.miyagi/engine-tokens` | where the engine publishes its token (`<port>.json`, 0600) for the companion, `tut run` and the dev CLI |
| `MIYAGI_DEBUG_ROUTES` | 0 | `1` = serve `/debug/*` and `/demo/*` (also on with `DEMO=1`); off they answer 404. The app's engine never sets it |
| `ORCH_LESSON` | (none) | DEMO only: step-graph JSON to use as the lesson |
| `ORCH_AUTOSTART` | 0 | `1` = start a lesson at boot: `ORCH_LESSON_URL` via the real builder (LIVE) or `ORCH_LESSON` (DEMO) |
| `ORCH_OPEN_WORKSPACE` | 0 | `1` = open the workdir in VS Code and jump to each step's target |
| `ORCH_SCREEN_INTERVAL_S` | 1.0 | seconds between screen captures |
| `ORCH_PRECISION` | auto | `auto` (workdir on disk or a `tut run`), `on`, or `off` (screen checks only) |
| `ORCH_BUILD_TIMEOUT_S` | 300 | a live lesson build taking longer becomes an `error` event |
| `TUT_WORKDIR` | per lesson: `~/miyagi/lessons/<slug>` | pin the learner's folder (watched for saves); `miyagi-demo.sh` sets `demo/pinn-lab` |
| `DEMO` | 0 | `1` = serve `demo/cache/` files and canned stubs, never call live APIs (checks stay real) |
| `ORCH_STUBS` | (empty) | `all` or `lesson,coach,...` = force stubs even if the real module exists |
| `ORCH_SCREEN` | 1 | start the whole-screen reader (`server.screen`, macOS + Screen Recording permission). `0` = files + `tut run` only |
| `ORCH_STRICT` | 0 | `1` = raise on any event that doesn't validate against the contract (tests use this) |
| `ORCH_IDLE_GATE_S` | 5 | idle seconds before the coach may speak |
| `MIYAGI_SCENE_EVERY_S` | 5 | Haiku scene look ([scene_watch.py](scene_watch.py)): one look this often while a step is active and the screen changed; `0` = off. Off in DEMO / `ORCH_STUBS=coach`, without the real screen reader, and under pytest unless set |
| `MIYAGI_SCENE_MAX_PER_HOUR` | 720 | hard cap on scene looks in any hour |
| `MIYAGI_SCENE_STOP_AFTER` | 30 | scene looks stop after this many identical scenes in a row, until a save or a big screen change |
| `MIYAGI_SCENE_CAP_S` | = every | > every lets a repeated scene back off (PeriodicGate doubling up to this) |
| `MIYAGI_SCENE_TIMEOUT_S` | 8 | one look's timeout (a slow look is skipped, never retried) |
| `ORCH_RECORD` | 1 | record every ingest event to `demo/runs/<run_id>.jsonl` (gitignored) |
| `MIYAGI_CURATED` | 1 | curated "Just teach me" lessons ([curated.py](curated.py)): a neural-network goal gets the hand-built NN lesson instantly (no build), its network diagrams pushed to the drawer's right-hand panel and redrawn from the learner's run. `0` = build every lesson. See `docs/NN-DEMO.md` |
| `MIYAGI_CONTEXT_MEMORY` | 1 | lesson memory ([context_memory.py](context_memory.py), `server/context/README.md`): short local notes of checks, files, screen errors, setup and coach cards, given to explain / diagnose / judge as an untrusted "what we know so far" block. `0` = off. Off under pytest unless set to `1` |
| `MIYAGI_CONTEXT_DIR` | `~/miyagi/state/context` | where those notes and the file-scan cache live (folder 0700, files 0600); Delete my data empties it |

## Modules

`modules.py` calls the real `server.<module>.<fn>`. In LIVE mode a missing or raising module becomes an `error` event. With `DEMO=1`,
`demo/cache/` and then `stubs.py` answer instead. `GET /health` shows each module as `real`, `demo`, `stub (ORCH_STUBS)` or `missing`.

| module | what the orchestrator calls |
|---|---|
| lesson | `await build_lesson(source_url, goal, workdir, api_key=get_key("gemini")) -> step graph`, with a timeout, then `ORCH_LESSON`, then the stub |
| keys | `server/config.py`: `get_key("anthropic")` (the app's `config.keys` > `.env`) for every module |
| checks | `evaluate_gate(step, ctx, screen=lines_by_app, precision_mode=bool) -> {passed, via, checks, precision}`. `ctx` is `server.checks.RunContext(**matching fields)` (workdir, exit_code, output_tail, metrics, command, running, screen), or our `context.RunContext`. Only runs started **during the current step** count; a `tut run` beats the same curve read off the screen. |
| coach | `set_lesson(graph)`; `await diagnose(step, failed_checks, metrics, code_excerpt, error_text=tail)` → `public(card)` → `offtrack`; `await explain(step, question, context)` → `card`; `hint(step, level, last_offtrack)` → `card`; `apply_fix(diff, file_text)["new_text"]` (written only on the learner's `apply_fix`, and only if it compiles) |
| screen | `get_reader()`: `start`, `subscribe(on_obs)` → re-evaluate, `locate_match(match, app)` → `spotlight{rect}`, `watch_metrics(lesson_id, {metric: metric_pattern})` → metrics, `set_overlay_bounds` ← `overlay.bounds` |
| finder | `await search(query) -> [search.result payload + "url"]` (the `url` is what `build_lesson` gets) |
| diagrams | `await build(kind, step=step, ctx=ctx) -> diagram payload` (`kind` is network, gradients or heatmap) |

Sync and async functions both work, and dicts, dataclasses or pydantic models are all accepted as return values.

## The state machine (`session.py`), screen-first

**Two routes to green** (see `step-graph.schema.json`): a step's `checks` are screen-gradable (`screen_contains`, `screen_absent`, and `metric_*` with a
`metric_pattern` read off the terminal). In **precision mode** (the workdir exists on disk, or a `tut run` happened this step) the step also passes when all
of its `precision_checks` (file_*, command_exit_ok, ::metric::) pass. The checklist the app sees is `checks`, mirrored green when the other route passes. With
no screen reader running it's the `precision_checks`, since screen checks could never move. Spotlights are screen rects from `locate_match`; with no
screen, nothing is spotlighted.


- `learn` → `search.result`* → `search.done`. `build_lesson` / `learn_url` → `lesson.building`* → `lesson.ready` → step 0.
- **Step start:** `step.started`, `check.updated(pending)` per check, `video.seek{start, play:true}` + `video.play`, `status watching`.
- **Segment end** (`video.state` reaches `step.video.end`; if the player never reports, a wall-clock timer does it): pass right away if the checks
  already pass, otherwise `video.pause` + `spotlight` on the step's first target.
- **Evaluate** on every new screen frame (the reader only fires when the screen changed), on file save (polling watcher on the workdir), on `run_ended`, and every 0.5 s while metrics stream in (from `tut run` or OCR'd terminal lines). Only *changes* emit `check.updated`.
  All checks pass (and the learner did something, or the segment ended) → `step.passed{stepId, nextStepId}`, `spotlight{clear}`, then 0.4 s later the next step's
  `step.started` + `video.seek` + `video.play`. On the last step: `step.passed{stepId}` + `video.play`.
- **Don't-nag gate.** A failing check is shown as `pending` until the gate opens. It opens on a run ending with failures, on 2 consecutive failing
  evaluations, or after 5 s idle once the learner has engaged with the step. Then the engine sends `status thinking` → `coach.diagnose` → `offtrack` + `spotlight`
  (on the screen rect of `diff.yours` if visible, else the step target) + `status offtrack`. Screen frames count as learner activity only after the step's clip ends. The same failure set on the same run is coached only once.
- **Actions:**
  - `back` seeks to the start of the step (`text:"prev"` goes back a step). With no clip to rewind (a "Just teach me" lesson) it goes back a step.
    A step gone back to is never passed by a click or key alone (its code may already be in the file): a save, a run, Check, or
    "Looks done?" → Confirm passes it again.
  - `show_me` replays the clip and turns the spotlight on.
  - `explain` and `ask` return a coach `card`. `explain` with `text` (the drawer's "Explain more" on selected lesson
    text) explains that selection instead, like VS Code's "Miyagi: Explain this" (POST /vscode/event
    `explain_selection`): see `selection.py`.
  - `hint` walks the hint ladder.
  - `diagram` returns `gradients` after a metric failure and `network` otherwise, or the kind named in `text`.
  - `voice_toggle` flips the voice flag.
  - `apply_fix` replaces the last offtrack `diff.yours` line with `diff.expected`, only when the learner explicitly asks for it.
  - Every action gets a visible answer: one that sends no card / offtrack / diagram / spotlight / step / video / error (nothing to confirm,
    to undo, to go back to…) answers with a short `card {kind:"answer"}` notice. Exceptions, whose effect is elsewhere: `voice_toggle`,
    `skip_setup`, `install`, `open_editor`, `open_in_browser`. Not a notice: Show me while its box is already up, or a card identical
    to one sent moments ago (both are already on screen). Check / Skip / Confirm on a step that already passed say "This step is done";
    Check's notice keeps the off-track card's buttons (Do it for me / Run it, Skip).
  - Every command from the app is logged at INFO as one `<- ` line (`<- action ask "why does divide…"`, text cut at 60 chars; `config.keys` by
    name only; `video.state` / `overlay.bounds` at DEBUG), next to the outbound `-> ` lines, when the command runs. A command that arrives
    while another is still running also logs at once: `<- action hint queued behind action ask (0 waiting)`. Speaking decisions log as
    `speak? <step> <reason>: …`.
- **Reconnect:** a new socket gets a snapshot (`lesson.ready`, `step.started`, check states, the open offtrack card, `status`).
- **Build metrics (`build_metrics.py`):** every build is timed from the command's arrival (`learn` / `learn_url` / `build_lesson` /
  `library.start` / `review.start`) to `lesson.ready` and the first `step.started`, by stage (`preflight`, `setup`, `captions`,
  `plan`, `steps`, `checks`, `handoff`, `workspace`, `hold`, `start`). One `build.metrics {json}` INFO line per build (ok / failed /
  cancelled) and the same JSON appended to `~/miyagi/state/build-metrics.jsonl` (`$MIYAGI_STATE_DIR`; the last 500 builds).
  `python -c "from server.orchestrator import build_metrics as b; print(*b.read(limit=5), sep='\n')"` prints the last five.
  `lesson.ready.buildS` (optional) carries the command -> ready seconds.

## Ambient help: explain this error ([ambient.py](ambient.py), `server/ambient_errors`)

`ambient.set`, `error.explain` and `error.dismiss` are answered beside the command queue and listed in
`engine.hello.capabilities`. With "Spot errors" on (per connection, off by default) and no lesson running, the screen
reader runs (`session._sync_screen_soon` asks `ambient_screen`) and `Engine.on_screen` hands its frames to the error
watcher instead of the lesson; errors on screen 1 s go out as `error.seen` (local only, no model). Explain makes at
most one Haiku call per error (`coach.explain_error`), 20 per rolling hour (`server/ambient_cap.py`, shared with
How-do-I). See `server/ambient_errors/README.md`.

## Ending a lesson

`curl -X POST localhost:8787/end` (or `python -m server.orchestrator.client end`, or the app's `end_lesson` command) cancels any build or diagnosis, clears the
spotlight and video, records `lesson_ended`, and sends `lesson.ended` + `status idle`. A new `learn` while a lesson runs ends it first.
The app's `end_lesson` command (the bar's / launcher's End) ends with reason `stopped`: the saved progress is kept (marked `stopped`)
and offered back by the resume card ("Continue where you left off?") when the app next connects; only its Continue restores it.
Building any lesson, the same one too, starts over and replaces it. `POST /end` and the resume card's "Start a new lesson"
(`action end_lesson`) discard it.

## VS Code

Never opened automatically. After `lesson.ready`, a lesson that happens in an editor (its targets or checks name Code/Terminal or files)
gets a card "Open VS Code?" with `actions: ["open_editor"]`. VS Code opens, and per-step `code -g` jumps start, only after the learner says yes.
If S2's `server.workspace.requirements(graph, folder)` exists, its summary and items (tools needed / installed) fill the card.
Lessons in other apps (Blender, Figma…) never get the card.

## HTTP

Also handled on the socket: `overlay.bounds` → screen reader (OCR ignores our own UI); `config.keys` → used over `.env` (process env, never logged) and answered
with `config.status` (`ok`/`env`/`missing`, never the keys).

`POST /ingest` takes one event, a list of events, or `{"events":[...]}` in the engine-internal.md shapes. A `metric` event can also carry
`"metrics":[{step,name,value},...]`. The reply carries `{lesson_id, step_id}` so `tut run` can tag its Tiger run. Debug routes: `GET /state`, and (dev only, `MIYAGI_DEBUG_ROUTES=1` or `DEMO=1`) `GET /events?since=N`, `POST /debug/pass`, `POST /debug/goto/{i}`, `POST /debug/lesson`.

## DEMO=1 cache layout (read from `demo/cache/`; any missing file falls back to the stub)

```
search.json  or  search/*.json      list of search.result payloads (each with "url")
lesson.json  or  lessons/*.json     step graph (newest lessons/*.json wins)
coach/<stepId>.json                 offtrack payload for that step
cards/<stepId>-explain.json, cards/<stepId>-answer.json, cards/<stepId>-hint<level>.json
diagrams/<kind>.json                diagram payload
runs/<name>.jsonl                   a recorded `tut run` ({"dt", "event"} per line), replayable
```

## Recording and replaying training runs (the demo safety net)

Every `/ingest` event is appended to `demo/runs/<run_id>.jsonl`. `POST /demo/replay {"name"?: "<stem>", "speed"?: 1}` feeds a recording
(from `demo/cache/runs/` first, then `demo/runs/`; the newest one if no name is given) back through the state machine, keeping its original pacing
and using a fresh run_id, exactly as if the learner had just run it. `GET /demo/runs` lists recordings. From the client, type `runs` or `replay <name>`.
**Before the 9 AM freeze, copy the good β-curriculum take into `demo/cache/runs/`.**

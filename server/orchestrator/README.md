# server/orchestrator (E4): the engine hub

FastAPI app `server.orchestrator.main:app` on **:8787**. It speaks `shared/contracts/events.ts` over WebSocket `/`
(Python mirror: `shared/contracts/events.py`), takes `tut run` events on `POST /ingest`, and owns the lesson state machine.

## Run

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e "server[dev]"
TUT_WORKDIR=/tmp/tut-work .venv/bin/python -m server.orchestrator.main        # engine on :8787
.venv/bin/python -m server.orchestrator.client                                  # print events; type `learn pinn`, `build`, `hint`, ...
.venv/bin/python -m server.orchestrator.client --autopilot --speed 3            # full scripted lesson incl. the β=30 hero loop
.venv/bin/python -m pytest server/orchestrator -q                               # state-machine tests
```

`--autopilot` is a fake learner that drives the **real** state machine. It reports player positions (`video.state`), writes the canned
PINN solution into the workdir step by step, and POSTs simulated training runs to `/ingest`: a β=30 plateau, then `apply_fix`,
then a β-curriculum run. It only writes `pinn_convection.py` and refuses to overwrite one it didn't create, so point
`TUT_WORKDIR` at a scratch folder. **Adrian:** run the engine and the autopilot, then point the app's `ENGINE_URL` at
`ws://localhost:8787` to watch a whole lesson stream in.

## Env

| var | default | meaning |
|---|---|---|
| `ENGINE_PORT` | 8787 | port |
| `TUT_WORKDIR` | lesson's `workdir`, else `demo/pinn` | folder the learner works in (watched for saves) |
| `DEMO` | 0 | `1` = serve `demo/cache/` files, never call live APIs (falls back to stubs) |
| `ORCH_STUBS` | (empty) | `all` or `lesson,coach,...` = force stubs even if the real module exists |
| `ORCH_STRICT` | 0 | `1` = raise on any event that doesn't validate against the contract (tests use this) |
| `ORCH_IDLE_GATE_S` | 5 | idle seconds before the coach may speak |

## Modules: stubs first, real when they land

`modules.py` resolves each module per call: the real `server.<module>.<fn>` if it exists, else the stub in `stubs.py`.
**If a real function raises, the error is logged and the stub answers instead**, so a flaky API can't take the demo down.
`GET /health` shows which one is live (`real` / `stub` / `demo-cache`).

| module | what the orchestrator calls |
|---|---|
| lesson | `await build_lesson(source_url, goal, workdir) -> step graph` |
| checks | `evaluate_step(step, ctx) -> [{checkId, label, status, detail}]`. `ctx` is `context.RunContext` (`workdir`, `last_run`, `exit_code`, `output_tail`, `metrics`, `runs`), or `server.checks.RunContext(**matching fields)` if checks exports one. Only runs started **during the current step** count. |
| coach | `await diagnose(step, failed_checks, metrics_summary, code_excerpt) -> offtrack payload`; `await explain(step, question, context) -> card`; `hint(step, level) -> card` |
| finder | `await search(query) -> [search.result payload + "url"]` (the `url` is what `build_lesson` gets) |
| diagrams | `await build(kind, step=step, ctx=ctx) -> diagram payload` (`kind` is network, gradients or heatmap) |

Sync and async functions both work, and dicts, dataclasses or pydantic models are all accepted as return values.

## The state machine (`session.py`)

- `learn` → `search.result`* → `search.done`. `build_lesson` / `learn_url` → `lesson.building`* → `lesson.ready` → step 0.
- **Step start:** `step.started`, `check.updated(pending)` per check, `video.seek{start, play:true}` + `video.play`, `status watching`.
- **Segment end** (`video.state` reaches `step.video.end`; if the player never reports, a wall-clock timer does it): pass right away if the checks
  already pass, otherwise `video.pause` + `spotlight` on the step's first target.
- **Evaluate** on file save (polling watcher on the workdir), on `run_ended`, and every 0.5 s during a run that is sending metrics. Only *changes* emit `check.updated`.
  All checks pass (and the learner did something, or the segment ended) → `step.passed{stepId, nextStepId}`, `spotlight{clear}`, then 0.4 s later the next step's
  `step.started` + `video.seek` + `video.play`. On the last step: `step.passed{stepId}` + `video.play`.
- **Don't-nag gate.** A failing check is shown as `pending` until the gate opens. It opens on a run ending with failures, on 2 consecutive failing
  evaluations, or after 5 s idle once the learner has engaged with the step. Then the engine sends `status thinking` → `coach.diagnose` → `offtrack` + `spotlight`
  (on `diff.file:line` if given, else the step target) + `status offtrack`. The same failure set on the same run is coached only once.
- **Actions:**
  - `back` seeks to the start of the step (`text:"prev"` goes back a step).
  - `show_me` replays the clip and turns the spotlight on.
  - `explain` and `ask` return a coach `card`.
  - `hint` walks the hint ladder.
  - `diagram` returns `gradients` after a metric failure and `network` otherwise, or the kind named in `text`.
  - `voice_toggle` flips the voice flag.
  - `apply_fix` replaces the last offtrack `diff.yours` line with `diff.expected`, only when the learner explicitly asks for it.
- **Reconnect:** a new socket gets a snapshot (`lesson.ready`, `step.started`, check states, the open offtrack card, `status`).

## HTTP

`POST /ingest` takes one event, a list of events, or `{"events":[...]}` in the engine-internal.md shapes. A `metric` event can also carry
`"metrics":[{step,name,value},...]`. Debug routes: `GET /state`, `GET /events?since=N`, `POST /debug/pass`, `POST /debug/goto/{i}`, `POST /debug/lesson`.

## DEMO=1 cache layout (read from `demo/cache/`; any missing file falls back to the stub)

```
search.json  or  search/*.json      list of search.result payloads (each with "url")
lesson.json  or  lessons/*.json     step graph (newest lessons/*.json wins)
coach/<stepId>.json                 offtrack payload for that step
cards/<stepId>-explain.json, cards/<stepId>-answer.json, cards/<stepId>-hint<level>.json
diagrams/<kind>.json                diagram payload
```

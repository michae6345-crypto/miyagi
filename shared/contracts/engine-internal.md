# Engine internals: how the server modules talk to each other

All Python 3.11+, one package `server` (deps in `server/pyproject.toml`; **add a dependency there in its own tiny commit, don't reformat the file**). The orchestrator is the hub; the other modules are libraries it calls.

```
tut run (cli/) ──POST /ingest──▶ orchestrator ──WS :8787──▶ Electron app
                                   │  ├─ lesson.build_lesson()     (E2)
                                   │  ├─ checks.evaluate_step()    (E3)
                                   │  ├─ coach.diagnose()/explain()/hint()  (E5)
                                   │  ├─ finder.search()           (teammate 3)
                                   │  └─ diagrams.build()          (teammate 3)
                                   └─ Tiger Data (training_metrics, runs, learning_events)
```

## server/lesson (E2)
- `async def build_lesson(source_url: str, goal: str, workdir: str) -> dict`: returns a step graph that validates against `shared/contracts/step-graph.schema.json`. Uses Gemini with the YouTube URL. Caches to `demo/cache/lessons/<hash>.json`; return the cached one if present (the demo must never wait on Gemini).

## server/checks (E3) + cli/ (E3)
- `tut run <cmd...>`: runs the command, streams stdout through, parses `::metric::` lines, writes to Tiger Data, and POSTs to `http://localhost:8787/ingest`:
  - `{"kind":"run_started","run_id","command","cwd"}`
  - `{"kind":"metric","run_id","step","name","value"}` (batch them, ~5/s max)
  - `{"kind":"output","run_id","lines":[...]}`
  - `{"kind":"run_ended","run_id","exit_code"}`
- `def evaluate_step(step: dict, ctx: RunContext) -> list[CheckResult]`: pure function. `RunContext` holds `workdir`, the last run (`exit_code`, `output_tail`) and `metrics: dict[name, list[(step, value)]]`. `CheckResult = {checkId, label, status: "pending"|"pass"|"fail", detail}`.
- A file watcher (watchdog or polling) on the workdir; on save, the orchestrator re-evaluates `file_*` checks.

## server/coach (E5)
- `async def diagnose(step, failed_checks, metrics_summary, code_excerpt) -> dict`: returns an `offtrack` payload (see `events.ts`). Claude Opus (`claude-opus-5-5`), adaptive thinking, low/medium effort, prompt-cache the lesson context. Knows domain failure modes, e.g. PINN convection at large β → curriculum on β (Krishnapriyan et al., NeurIPS 2021).
- `async def explain(step, question, context) -> dict`: returns a `card` payload, including a `videoJump` when the lesson's `explanations` cover the topic.
- `def hint(step, level: int) -> dict`: walks the hint ladder (question → video timestamp → paper → diff). **Never auto-patches by default.**
- `async def fix_outdated(error_text, libraries) -> dict | None`: Bright Data search of the docs/changelog → a suggested fix.

## server/orchestrator (E4)
- FastAPI app `server.orchestrator.main:app`, served on :8787: WebSocket `/` (the events.ts protocol) + `POST /ingest`.
- Owns the lesson state machine: active step → evaluate checks on file change and on run end → `check.updated` / `step.passed` → `video.seek` + `video.play` for the next step; on failure → (don't-nag gate: idle ≥ 5s, or a run ended, or 2 consecutive fails) → `coach.diagnose` → `offtrack` + `spotlight`.
- Routes the `action` commands (back / explain / diagram / show_me / hint / voice_toggle / ask / apply_fix).
- `DEMO=1` → replays `demo/cache/` results so the demo never depends on live APIs.
- **Starts with stubs for every module** (return canned data) so the app can connect within the first hour.

# server/coach (E5)

Turns a failed step into the card the learner sees. Owner: Michael (engine).

```python
from server import coach
coach.set_lesson(step_graph)                                   # once per lesson → cached prompt prefix
card = await coach.diagnose(step, failed_checks, ctx.metrics, code, error_text=output_tail)
send("offtrack", coach.public(card))                          # strips private `_meta`
send("card", coach.public(await coach.explain(step, None, {"metrics_summary": ctx.metrics})))
send("card", coach.hint(step, level))                          # 0 question → 1 video → 2 paper → 3 diff
patch = coach.apply_fix(card["diff"], file_text)              # proposal only; app writes `new_text` after the learner accepts
fix = await coach.fix_outdated(error_text, lesson["libraries"])  # offtrack-shaped dict or None
```

| Function | Returns | Model |
|---|---|---|
| `diagnose(step, failed_checks, metrics_summary, code_excerpt, *, error_text="")` | `offtrack` payload (+ `_meta`) | triage → Opus 5.5 (low effort) or no model |
| `explain(step, question, context)` | `card` with `videoJump` when a step `explanations` entry matches | Opus 5.5 |
| `hint(step, level, last_offtrack=None)` | `card` kind `hint` (+ `level`, `diff`, `citation`, `actions`) | none |
| `apply_fix(diff, file_text)` | `{unified_diff, new_text, requires_confirmation: True}`; never writes | none |
| `fix_outdated(error_text, libraries)` | offtrack-shaped fix with source URL, or `None` | known table → Bright Data SERP + Unlocker → Opus |
| `triage(...)` | route `template` / `playbook` / `opus` | rules, then Haiku 5.5 for the ambiguous middle |

`metrics_summary` accepts `RunContext.metrics` (`{name: [(step, value)]}`), a string, or a summary dict.

## Design

- **Triage first** (`triage.py`). Nothing run yet + only file checks failing → the step's own hint, no model. Exact error signature from the playbook (e.g. CUDA on a Mac) → curated card in milliseconds. Metric failures (the hero case) → Opus directly. Only the ambiguous middle pays for a Haiku call; any doubt goes to Opus.
- **Playbook** (`playbook.py`): PINN convection at large β → β curriculum (Krishnapriyan et al., NeurIPS 2021, arXiv 2109.01050); PINN loss imbalance (Wang, Teng & Perdikaris); missing `zero_grad()`; CUDA vs MPS on Mac; LR too high; PINN inputs without `requires_grad`. It's in the cached system prompt, used by the deterministic matcher, and is the **offline fallback card** when the API is down, times out or refuses, so the demo never shows a blank.
- **Citations are whitelisted.** The model picks a `citation_id` from the playbook + lesson `sources`; unknown ids are dropped. It can't invent a paper.
- **Limits enforced in code**: title ≤ 8 words, body clamped near 30 words, `apply_fix` only offered when there is a diff.
- **API call** (`llm.py`): `claude-opus-5-5`, `thinking: adaptive`, `output_config: {effort: "low", format: json_schema}`, two `cache_control` breakpoints (instructions+playbook, then lesson context rendered with sorted keys), and server-side refusal fallback (`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`). Haiku 5.5 for triage at low effort.

## Running

```bash
uv venv -p 3.12 .venv && uv pip install -p .venv -e "server[dev]"
.venv/bin/python -m server.coach demo --json --ladder --explain      # live if ANTHROPIC_API_KEY, else replays fixtures
.venv/bin/python -m server.coach demo --live --record               # call the API and save fixtures for CI
.venv/bin/python -m pytest server/coach -q                          # no network
```

Fixtures in `server/coach/fixtures/` are recorded live responses (Opus 5.5 diagnose + explain for the demo case, Haiku 5.5 triage for an MPS error), keyed by a hash of the request. Re-record with `--live --record` after changing the demo case. Env: `ANTHROPIC_API_KEY`, `BRIGHTDATA_API_KEY`, `BRIGHTDATA_SERP_ZONE`, `BRIGHTDATA_UNLOCKER_ZONE`; `COACH_REPLAY_DIR` / `COACH_RECORD_DIR` for fixtures.

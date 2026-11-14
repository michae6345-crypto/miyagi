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
| `hint(step, level, last_offtrack=None)` | `card` kind `hint` (+ `level`, `diff`, `citation`, `actions`). Follows the latest diagnosis: 0 = its `guidingQuestion`, 1 = the video moment about that issue (else the step segment), 2 = its source, 3 = its diff. Works with the public card too | none |
| `apply_fix(diff, file_text)` | `{unified_diff, new_text, requires_confirmation: True}`; never writes | none |
| `fix_outdated(error_text, libraries)` | offtrack-shaped fix with source URL, or `None` | known table → Bright Data SERP + Unlocker → Opus |
| `triage(...)` | route `template` / `playbook` / `opus` | rules, then Haiku 5.5 for the ambiguous middle |

`metrics_summary` accepts `RunContext.metrics` (`{name: [(step, value)]}`), a string, or a summary dict.

## Screen understanding (docs/research/screen-understanding.md, build list #7 and #8)

```python
screen = coach.ScreenContext.from_observation(obs, image, cursor=(x, y), file=ax_file, line=ax_line, element=ax_el)
await coach.warm()                                   # at start and after set_lesson: TLS + cached prefix (both schemas)
task = coach.inflight.start("diagnose", coach.diagnose(step, failed, metrics, code, screen=screen,
                                                       on_targets=lambda t: send_spotlight(t[0]["rect"])))
coach.cancel()                                       # on any real user action: aborts the stream
card = await task                                    # offtrack + "targets": [{boxId, label, text, rect}]
patch = await coach.do_it_for_me(step, file, file_text)   # {file, unified_diff, summary, line, new_text}
targets = await coach.locate("the learning rate", screen)  # exact text → no model; else Claude Haiku
```

- **Set-of-mark payload.** The text comes first: context, then "Cursor at (x, y) over [id] "…" (app), line N of file", then the numbered box list. Two JPEGs follow: the whole screen at 1280 px wide with every box outlined, numbered in the margin and the cursor ringed, and a full-resolution 400×400 crop around the cursor. The 120 boxes nearest the cursor are kept. Rects are in screen points with a top-left origin, the same space as `spotlight`.
- **Targets first.** With a screen, `targets` is the first property in the JSON schema. The reply streams, and `on_targets` fires as soon as that array is complete. Live: targets at 2.9 s of a 4.65 s reply, first text at 1.5 s after `warm()`. Several targets are allowed, each labelled in 3 words or fewer. Unknown ids are dropped. `explain(..., context={"screen": s, "on_targets": cb})` works the same way.
- **Cancel / warm.** `inflight.start(key, coro)` replaces the previous task under that key, and `cancel()` closes the HTTP stream. `warm()` sends the exact diagnose request shape with `max_tokens=1`; 0 is rejected when an output format is set. Live: the first diagnosis after `warm()` read 4,505 cached tokens.
- **Do it for me.** It uses the latest diagnosis's diff when that applies cleanly. Otherwise Opus writes a patch, retried once with the reason it failed. The patch is accepted only if `apply_fix` finds the lines and, for Python, the result compiles. Otherwise it raises `CoachUnavailable`. It never writes files. The summary is the card's action sentence ("Lower the learning rate to 1e-3").
- **locate** asks `claude-haiku-5-5` (effort low) to pick box ids from the same set-of-mark images. Screen and code reading is Claude only; there is no Gemini in `server/coach`.
- **Computer use** is not used. If icon finding ever needs it, the tool is `computer_toolset_20260801`, because `computer_20251124` returns 400 on Opus 5.5.

## Orchestrator contract notes (E4)

- `diagnose(..., cursor={"x", "y", "under": {"text", "app", "rect"}})` and `explain(..., {"cursor": ...})` tell the coach what the learner points at, when no full `screen` is attached.
- The body's last sentence states the fix in words ("Set lr to 1e-3 in the Adam optimizer."), because E4 shows the first offtrack as hint level 2 with the diff hidden. Bodies are about 30 words. Up to 42 pass untouched; past that, the cause is shortened and the action sentence is never cut.
- `diff.command` carries a terminal fix (`pip install pandas`). It can come alone (`expected` empty) or with a code diff. E4 copies it to the clipboard.
- `hint(step, 0, last_offtrack)` asks the card's `guidingQuestion`, else the playbook entry's, else a question built from the card's title. A cached card from before guiding questions still gets an issue-specific question.

## Design

- **General, web-grounded** (GENERALITY RULE). `web.py` detects the library and symbol from any error on screen (Python tracebacks, eslint/React, Node, npm, CLI tools). It then fetches the official docs/changelog (`docs_for`) and Stack Overflow / GitHub / Reddit posts (`community_signals`) through Bright Data (SERP restricted to official domains, then Web Unlocker). This runs in parallel with triage and has a 6 s budget. The pages go into the Opus prompt as `[web:N]`, and the card cites the URL it used. When `server.finder.web` (E7) lands, its `docs_for` / `community_signals` are used instead. With no Bright Data keys or a timeout, the coach falls back to playbook and lesson sources.
- **Metric flags work for any metric.** Direction comes from the step's checks (`op >` means higher is better). Without a check, names like acc/score/pass count as "up", everything else as "down".

- **Triage first** (`triage.py`). Nothing run yet + only file checks failing → the step's own hint, no model. Exact error signature from the playbook (e.g. CUDA on a Mac) → curated card in milliseconds. Metric failures (the hero case) → Opus directly. Only the ambiguous middle pays for a Haiku call; any doubt goes to Opus.
- **Playbook** (`playbook.py`): general failure modes, none tied to one demo. PINN total loss missing the IC/BC term (Raissi et al. 2019); PINN loss imbalance (Wang, Teng & Perdikaris); PINN convection at large β → β curriculum (Krishnapriyan et al., NeurIPS 2021); missing `zero_grad()`; CUDA vs MPS on Mac; LR too high; PINN inputs without `requires_grad`. Playbook diffs are only generic one-liners (e.g. `optimizer.zero_grad()`); Opus writes the tailored diff from the learner's actual code. A "low loss but wrong solution" metric flag fires when a loss-like metric falls more than 90% while an error metric (rel_l2, err...) barely moves. It's in the cached system prompt, used by the deterministic matcher, and is the **offline fallback card** when the API is down, times out or refuses, so the demo never shows a blank.
- **Citations are whitelisted.** The model picks a `citation_id` from the playbook + lesson `sources`; unknown ids are dropped. It can't invent a paper.
- **Limits enforced in code**: title ≤ 8 words, body clamped near 30 words, `apply_fix` only offered when there is a diff.
- **API call** (`llm.py`): `claude-opus-5-5`, `thinking: adaptive`, `output_config: {effort: "low", format: json_schema}`, two `cache_control` breakpoints (instructions+playbook, then lesson context rendered with sorted keys), and server-side refusal fallback (`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`). Haiku 5.5 for triage at low effort.

## Running

```bash
uv venv -p 3.12 .venv && uv pip install -p .venv -e "server[dev]"
.venv/bin/python -m server.coach demo --json --ladder --explain      # hero: diffusion PINN, lr=0.3, loss oscillates; live if a key, else replay
.venv/bin/python -m server.coach demo --case diffusion-bc             # also: diffusion-grad, convection
rm server/coach/fixtures/*.json && .venv/bin/python -m server.coach.tests.record_fixtures   # re-record every fixture live
.venv/bin/python -m server.coach demo --live --record               # call the API and save fixtures for CI
.venv/bin/python -m pytest server/coach -q                          # no network
```

**No canned cards outside `DEMO=1`.** If Opus is unavailable (no key, API error, refusal), `diagnose`/`explain` raise `CoachUnavailable(reason)`; `fix_outdated` raises `OutdatedFixUnavailable(reason)` when it cannot search or read the docs, and returns `None` only when it read them and none documents a fix. With `DEMO=1` the curated playbook card is used instead. Triage-chosen template/playbook cards (nothing run yet, or an exact known error) are deliberate routes, not fallbacks.

**Keys (BYOK):** `coach.set_keys(config_keys)` (delegates to `server.config` when present); otherwise env / `.env` found upward from cwd, plus `$TUT_ENV`.

Fixtures in `server/coach/fixtures/` are recorded live responses: Opus 5.5 diagnose + explain for the PINN demo, Opus for a React hooks lint error and a removed pandas API (`tests/generic_cases.py`, with Bright Data replaced by excerpts of the real react.dev / pandas pages), and Haiku 5.5 triage, keyed by a hash of the request. Re-record with `--live --record` after changing the demo case. Env: `ANTHROPIC_API_KEY`, `BRIGHTDATA_API_KEY`, `BRIGHTDATA_SERP_ZONE`, `BRIGHTDATA_UNLOCKER_ZONE`; `COACH_REPLAY_DIR` / `COACH_RECORD_DIR` for fixtures.

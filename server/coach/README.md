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

## Cost policy

- **Models:** Opus (`claude-opus-5-5`) writes only the diagnosis card. Triage, pointing/locate, explain, "Do it for me" and `fix_outdated` use Haiku (`claude-haiku-5-5`). To override one purpose, set `COACH_MODEL_<PURPOSE>` (see `llm.model_for`).
- **Prompt caching:** every system prompt carries `cache_control`. `warm()` pre-writes the diagnose prefix.
- **Cost freeze:** run offline tests only. `tests/record_fixtures.py` makes paid calls and refuses to run without `COACH_ALLOW_LIVE=1`.

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

## Non-PINN robustness (S9 QA: React / pandas / git)

- **Errors on screen count.** When `error_text` is empty and a `screen` is passed, error and refusal lines visible on screen become the error text: Traceback, `error:`, `fatal:`, "needs merge", CONFLICT, "You must…", "Failed to compile" and so on. Triage then never sends an erroring learner to the "do the step" card, even if Haiku says to.
- **Web lookups** run only with error text that isn't self-explaining (NameError, ReferenceError, no-undef and SyntaxError skip it), capped at 1.5 s. The error line itself goes into the prompt as "THE ERROR MESSAGE (your cause must agree with exactly what it says…)".
- **Prompt rules:**
  - Trust the error on screen over the lesson's library versions.
  - The diff is one contiguous block (up to 8 lines) that makes every edit the action sentence asks for.
  - Never `git add` / `--continue` while conflict markers remain. `_shape` also drops such a command unless the diff itself removes the markers.
- **`apply_fix`:**
  - It tolerates OCR'd anchors: it strips gutter line numbers and gutter-only lines, then maps each line fuzzily (difflib ratio ≥ 0.8). When the screen-read lines keep the editor's gutter numbers, those numbers are used as the file's line numbers, provided the text there agrees (ratio ≥ 0.7). The fuzzy pass may skip up to 2 blank or conflict-marker rows that OCR dropped. That covers OCR errors like `<<<<<` for `<<<<<<<` and `=` for `=>`.
  - When `expected` rewrites more lines than `yours` covers, the span widens over neighbours that `expected` rewrites (similarity ≥ 0.7). A patch is rejected only if it would repeat a contiguous run of 2 or more lines at its edges; single repeated lines like `});` are normal code. A `git-rebase-todo` patch must keep every commit hash exactly once.
  - It rejects no-op patches.
  - It edits `.ipynb` cell by cell (sources only, outputs kept, `indent=1`, magics ignored for the compile check). Excerpts of notebooks are cell sources, not raw JSON, even when the orchestrator truncates the JSON at 6000 characters.
- **`do_it_for_me`:**
  - It returns `{command, …}` for terminal fixes.
  - It reuses the diagnosis's diff only if it contains every value the action sentence names ("…to `squash`", "…to 1e-3"); otherwise Opus writes the patch.

## Holds: when the coach must not diagnose

`diagnose(..., file_state={"path", "saved", "wrong_folder"}, code_source="file"|"screen")` can return a card with `hold`. The orchestrator must NOT show such a card as an offtrack, and no model is called. This came from Michael's live misdiagnosis of an unsaved, OCR'd `def add(a, b):` with a hover tooltip over it.
- `hold: "wrong_folder"`: the learner is editing a same-named file in another folder. The orchestrator shows its own card.
- `hold: "unsaved"`: `saved` is false, or the screen shows the step's file unsaved (●, `Untitled-N`). The only message is "Save with ⌘S so I can check it."
- `hold: "unconfirmed"`: the code excerpt is OCR (`code_source="screen"`) and differs from the previous read of this step. Two agreeing reads are needed before any diagnosis; until then the coach says nothing.
- **Prompt:** OCR text and editor overlays such as tooltips never justify claiming a line is malformed.
- **Step judge:** a check about a file (its `file`, or a label naming the step's file) passes only if the workspace file is saved and non-empty. Unsaved gives a "Save so I can check" card; not seen or empty gives nothing.

## Step judge (judge.py)

Deterministic checks sometimes can't see that the learner is done: visual or setup steps, or a file outside the workdir. `StepJudge` asks Haiku, check by check, from the screen text and the workspace files.

```python
judge = coach.StepJudge()                       # one per session; per-step rate limit + change detection inside
if judge.should_judge(step, check_results, idle_s=idle, video_playing=playing, screen=obs, files=files, focused_app=app):
    j = await judge.judge(step, check_results, screen=obs, files=files, focused_app=app)   # None if unavailable
    for ev in j["events"]: emit(ev["type"], ev["payload"])     # check.updated status "pass", detail "Claude saw it on screen: …"
    if j["card"]: emit("card", j["card"])
```

- **Gate:** a check is not yet passed, the learner has been idle at least 8 s, the video isn't playing, at most one judgment per 20 s per step, and only when the screen text or the files changed.
- **Passing checks:** a check the machine still has as `pending` passes when Claude says done with confidence ≥ 0.8.
- **Disagreement:** if a deterministic check says `fail` while Claude says done (confidence ≥ 0.6), Claude never overrules it. You get the card `{kind: "answer", title: "Looks done?", body: ≤12 words, actions: ["confirm", "skip_step"], checkIds}` instead.
- **Ahead of the lesson:** if the learner is already on a later step, the card is `{title: "Already ahead?", actions: ["skip_step"], targetStepId}`. An earlier step on screen gives no card.
- **Setup steps:** these are judged done when the tool is visibly open or installed.
- **Check button** (action `check_step`): `await coach.judge_step(step, screen, files, check_results=...)` runs the same judgment with no gates. It returns `{checks: {id: {verdict: done|not_done|unsure, reason, evidence}}, done, missing (≤12 words), where, target: {text, rect} | None}`.
- **Reading the editor.** `pointing.editor_state(screen)` reads window titles and boxes: the real app name, the open file, an unsaved `Untitled-N`, and the `●` unsaved marker. The step's expected file comes from its checks or targets, or from its instructions ("save it as calculator.py"). `where` then says exactly what to do: "You're in VS Code on an unsaved file. Save it as calculator.py in the lesson folder". Pointing and hints use this too, and it overrides Haiku's generic `where`.
- **Inputs:** `screen` may be an E6 `ScreenObservation` (`lines_by_app`), a `ScreenContext`, a `{app: [lines]}` dict or plain text. `files` is `{path: text}`, notebooks become cell sources.

## Pointing: Explain / Show me / Hint (pointing.py)

Every coach answer about the screen carries `targets` (`[{boxId, label, text, rect}]`, screen points), or a `where` instruction when the place isn't on screen. There is never a fake target.
- `await coach.show_me(step, screen, last_offtrack)` returns `{stepId, targets, caption, where}`. It points at the diagnosed line if there is one, else the step's `targets[].match` (whole word), else Haiku.
- `coach.hint(step, level, last_offtrack, screen=screen)` stays synchronous and uses an exact match only. Levels 0 and 1 lead with `where` ("Open your code first: Open pinn_diffusion.py in your editor. Then: …") when the code isn't visible. Terminal lines that merely mention the file don't count as the code.
- `await coach.explain(step, q, {"screen": s, "on_targets": cb})` points in parallel with the Opus text. `cb` fires first: live, at 1.7 s, against a 3.1 s card. Opus gets text only.
- `await coach.point(step, screen, about=...)` is the shared helper. An exact match takes about 0 ms. Otherwise `claude-haiku-5-5` (thinking disabled, text only, 3 s cap) picks box ids, live in 1.0–1.8 s. If nothing matches, `where` is either derived from the step (file, `.ipynb`, or the terminal command) or Haiku's 12-word instruction.

## Voice (ElevenLabs track)

`voice.py` speaks short lines only: the step title on `step.started`, the card title on `offtrack`, and "Nice, step passed." on `step.passed`.
- **Synthesis:** ElevenLabs streaming TTS (`POST /v1/text-to-speech/{voice_id}/stream`, `eleven_flash_v2_5`, `mp3_44100_128`). The MP3 is cached under `~/.cache/sandhacks-tutor/tts` by a hash of voice, model and text, and identical concurrent lines make one request.
- **Readable text:** 1e-3 is read as 0.001, β as beta, lr as learning rate.
- **Serving:** `voice.router` serves `GET /tts/<hash>.mp3`; names are validated as hex only.
- **Payload:** `speak_event(event, payload)` returns the existing contract's `speak` payload `{audioUrl, text}`, or `None`. It never raises; a failure means no audio and one log line.
- **Prefetch:** `voice.prefetch([titles])` right after the lesson loads makes step starts instant.
- **Gate:** E4 owns it (voice toggled on, and no keystroke in the last 2 s).

## Orchestrator contract notes (E4)
- **Latency.** Web grounding runs only when there is an error message to look up, capped at 4 s, and keeps whatever lookups finished in time. A metric-only failure like the hero goes straight to Opus. Live, with Bright Data configured: card in 3.4 s after `warm()`. Rehearsal had measured 7–8 s while it waited on unused searches.
- **Offline stage fallback (opt-in).** With `COACH_OFFLINE_FALLBACK=1`, if Opus is unreachable (network/proxy down) and the playbook matches the learner's code with confidence ≥ 0.6, `diagnose` returns that playbook card marked `offline: true` (and `_meta.route=playbook`, `fallback_reason`). API errors, refusals and weak matches still raise `CoachUnavailable`. It is off by default because of the no-fake rule.

- `diagnose(..., cursor={"x", "y", "under": {"text", "app", "rect"}})` and `explain(..., {"cursor": ...})` tell the coach what the learner points at, when no full `screen` is attached.
- The body's last sentence states the fix in words ("Set lr to 1e-3 in the Adam optimizer."), because E4 shows the first offtrack as hint level 2 with the diff hidden. Bodies are about 30 words. Up to 42 pass untouched; past that, the cause is shortened and the action sentence is never cut.
- `diff.command` carries a terminal fix (`pip install pandas`). It can come alone (`expected` empty) or with a code diff. E4 copies it to the clipboard.
- `hint(step, 0, last_offtrack)` asks the card's `guidingQuestion`, else the playbook entry's, else a question built from the card's title. A cached card from before guiding questions still gets an issue-specific question.

## Design

- **General, web-grounded** (GENERALITY RULE). `web.py` detects the library and symbol from any error on screen (Python tracebacks, eslint/React, Node, npm, CLI tools). It then fetches the official docs/changelog (`docs_for`) and Stack Overflow / GitHub / Reddit posts (`community_signals`) through Bright Data (SERP restricted to official domains, then Web Unlocker). This runs in parallel with triage and has a 6 s budget. The pages go into the Opus prompt as `[web:N]`, and the card cites the URL it used. When `server.finder.web` (E7) lands, its `docs_for` / `community_signals` are used instead. With no Bright Data keys or a timeout, the coach falls back to playbook and lesson sources.
- **Metric flags work for any metric.** Direction comes from the step's checks (`op >` means higher is better). Without a check, names like acc/score/pass count as "up", everything else as "down".

- **Triage first** (`triage.py`). Nothing run yet + only file checks failing → the step's own hint, no model. Exact error signature from the playbook (e.g. CUDA on a Mac) → curated card in milliseconds. Metric failures (the hero case) → Opus directly. Only the ambiguous middle pays for a Haiku call; any doubt goes to Opus.
- **Playbook** (`playbook.py`): general failure modes, none tied to one demo. PINN total loss missing the IC/BC term (Raissi et al. 2019); PINN loss imbalance (Wang, Teng & Perdikaris); PINN convection at large β → β curriculum (Krishnapriyan et al., NeurIPS 2021); missing `zero_grad()`; CUDA vs MPS on Mac; LR too high; PINN inputs without `requires_grad`. Git: a squash/fixup placed above the commit whose code it edits → `git rebase --abort` and reorder. Playbook diffs are only generic one-liners (e.g. `optimizer.zero_grad()`); Opus writes the tailored diff from the learner's actual code. A "low loss but wrong solution" metric flag fires when a loss-like metric falls more than 90% while an error metric (rel_l2, err...) barely moves. It's in the cached system prompt, used by the deterministic matcher, and is the **offline fallback card** when the API is down, times out or refuses, so the demo never shows a blank.
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

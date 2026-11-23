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
| `explain_selection(step, selection, context)` | `card` kind `explain` about text the learner selected (VS Code "Miyagi: Explain this", the drawer's "Explain more"); the step is context only. `selection` comes from `server/orchestrator/selection.py`, with the card's title | Sonnet 5.5 (`COACH_MODEL_EXPLAIN_SELECTION`) |
| `hint(step, level, last_offtrack=None)` | `card` kind `hint` (+ `level`, `diff`, `citation`, `actions`). Follows the latest diagnosis: 0 = its `guidingQuestion`, 1 = the video moment about that issue (else the step segment), 2 = its source, 3 = its diff. Works with the public card too | none |
| `apply_fix(diff, file_text)` | `{unified_diff, new_text, requires_confirmation: True}`; never writes | none |
| `fix_outdated(error_text, libraries)` | offtrack-shaped fix with source URL, or `None` | known table → DuckDuckGo search + page GET → Opus |
| `triage(...)` | route `template` / `playbook` / `opus` | rules, then Haiku 5.5 for the ambiguous middle |

`metrics_summary` accepts `RunContext.metrics` (`{name: [(step, value)]}`), a string, or a summary dict.

## Cost policy

- **Models:** Sonnet (`claude-sonnet-5-5`) writes the diagnosis card (spend cap: never Opus by default; `COACH_MODEL_DIAGNOSE=claude-opus-5-5` to opt in). Triage, pointing/locate, explain, "Do it for me" and `fix_outdated` use Haiku (`claude-haiku-5-5`). To override one purpose, set `COACH_MODEL_<PURPOSE>` (see `llm.model_for`).
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

## Which file is open: only the editor window says so

The active file comes only from E6's `reader.vscode_window()` (`{app, title, path, file, dirty}`), the companion extension (`{path, dirty}`), the macOS window list, or accessibility title boxes. It never comes from OCR text. This came from Michael's case: "Editor shows README.md" while notes.py was active, with README.md only in the Explorer and VS Code's inline chat covering line 1.
- **Inputs:** pass `active_file=` to `diagnose` and `judge_step`, or set `ScreenContext.active_file`.
- **Prompt:** an "ACTIVE FILE" line appears only when that source is known. Otherwise a system rule forbids naming the open file.
- **Post-filter:** card bodies drop question sentences, and drop "the editor shows X" claims when the active file is unknown. If nothing true is left, the card becomes `hold: "unconfirmed"`, which is silent.
- **Empty file at a code step:** this is not started, not off track: "Type `notes = []` on line 1 of notes.py in VS Code."

## "Just teach me" text lessons (lesson.mode = "lesson"; S9 copy QA)

Copy rules: at most 12 words, name the file and VS Code (never Cursor), no glued check labels, one action.
- **Start:** the not-started card and `start_instruction()` give ONE action built from the step's `code` or `run_command`: "In VS Code, type `def add(a, b):` in calculator.py." or "Run `python3 calculator.py` in the VS Code terminal."
- **Hint after the auto card** moves up a rung instead of repeating it: "Type this" with the step's full `code` and Show me, or "Run this". Video steps get "Step details" (the full instructions).
- **Questions** never quote a check label. They ask about the code: "Which line of calculator.py defines add, and is it there yet?", "What does `python3 calculator.py` print right now?".
- **Show me / where:** lesson mode created the file, so it says "Open calculator.py in VS Code".
- **No model available:** a visible error gets a card that names it (`route: error_offline`), e.g. "`def` needs a name: line 4 of calculator.py." It never gets the not-started card.
- **Opus cards in lesson mode:** `body` is one action of ≤12 words naming the file and VS Code; `why` holds the reason, for Explain.

## Zero-cost mode: DEMO=1 or ORCH_STUBS includes the coach

`llm.offline_mode()` is true with `DEMO=1`, or with `ORCH_STUBS=all` or a list naming `coach` (e.g. `lesson,coach`). In that mode nothing paid leaves the coach. Recorded fixtures (`COACH_REPLAY_DIR`) still replay. S11 had counted 19 Claude calls in one DEMO rehearsal take.
- **Claude:** `structured_call` refuses before any network call. `diagnose` and `explain` return their offline cards (playbook or template).
- **Step judge:** `StepJudge.should_judge` is always false, so it never runs on a timer. `judge_step` (the Check button) returns `{offline: true}`: machine-passed checks are "done", the rest "unsure", and `done` is true only if every check already passed.
- **Other calls:** `warm()` is skipped, `locate` uses exact text only, `point` falls back to `where`, and the live web is never called.
- **Voice:** already-cached audio still plays; nothing new is synthesized.

## Cost gate for periodic calls (gate.py)

Michael's key: the step judge called Haiku every ~20 s while he was away with the display asleep. `PeriodicGate` now guards it, and is exported for any other periodic coach call. The rules:
1. **Only on change:** the screen text or the files must have changed. OCR is hashed without clocks, dates or percentages and ignoring line order. Files are hashed by `{path: mtime}` when available.
2. **Never when the screen reader is down or the display is asleep:** `should_judge(..., screen_ok=, display_asleep=)`, and `screen=None` also counts as down.
3. **Backoff:** while the verdict stays the same, the interval doubles: 20 s → 40 → 80 … capped at 5 min. A new verdict or a save resets it to 20 s.
4. **Stop:** after 3 identical verdicts it stops until a save, or until ≥ 25% of the screen's lines change (another app in front). A scrolling log doesn't wake it.

`diagnose` remembers its inputs per step for 10 min (failed checks, last metric values, code, error text, screen signature). An identical repeat returns the previous card (`_meta.memo`) with no model call.

## Holds: when the coach must not diagnose

`diagnose(..., file_state={"path", "saved", "wrong_folder"}, code_source="file"|"screen")` can return a card with `hold`. The orchestrator must NOT show such a card as an offtrack, and no model is called. This came from Michael's live misdiagnosis of an unsaved, OCR'd `def add(a, b):` with a hover tooltip over it.
- `hold: "wrong_folder"`: the learner is editing a same-named file in another folder. The orchestrator shows its own card.
- `hold: "unsaved"`: `saved` is false, or the screen shows the step's file unsaved (●, `Untitled-N`). The only message is "Save with ⌘S so I can check it." The learner rarely sees it: `server/orchestrator/quiet_save.py` saves the file through the VS Code companion instead and drops the card, and shows it only when the companion can't save.
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
    if j["card"] and shown(j["card"]): judge.card_shown(step["id"], j["card"])   # only cards the learner saw
```

- **Gate:** a check is not yet passed, the learner has been idle at least 8 s, the video isn't playing, at most one judgment per 20 s per step, and only when the screen text or the files changed (an app switch over the same text is not a change). The backoff follows Claude's per-check verdicts only, so a card going up never resets it to 20 s.
- **Passing checks:** a check the machine still has as `pending` passes when Claude says done with confidence ≥ 0.8.
- **Judge cards** are step-status cards, never answers: `kind: "step"`, `source: "judge"`, and they carry no `skip_step` (the bar owns Skip). `j["done"]` is the whole step's verdict (every check passed by the machine or seen done by Claude, confidence ≥ 0.6).
- **Disagreement:** if a deterministic check says `fail` while Claude says done (confidence ≥ 0.6), Claude never overrules it. When Claude sees the whole step done you get `{title: "Looks done?", verdict: "done", body: ≤12 words, actions: ["confirm"], checkIds}` (Yes vouches for `checkIds`). When other checks are still not done you get `{title: "Not yet", verdict: "not_done", body: what is left (≤12 words), actions: ["hint", "show_me"], checkIds: the missing checks}` instead, never "Looks done?".
- **No repeats:** after `card_shown`, the same card (title + checkIds) is not offered again for that step until the files change.
- **Ahead of the lesson:** if the learner is already on a later step, the card is `{title: "Already ahead?", actions: [], targetStepId}`. An earlier step on screen gives no card.
- **Setup steps:** these are judged done when the tool is visibly open or installed.
- **Check button** (action `check_step`): `await coach.judge_step(step, screen, files, check_results=...)` runs the same judgment with no gates. It returns `{checks: {id: {verdict: done|not_done|unsure, reason, evidence}}, done, missing (≤12 words), where, target: {text, rect} | None}`.
- **Reading the editor.** `pointing.editor_state(screen)` reads window titles and boxes: the real app name, the open file, an unsaved `Untitled-N`, and the `●` unsaved marker. The step's expected file comes from its checks or targets, or from its instructions ("save it as calculator.py"). `where` then says exactly what to do: "You're in VS Code on an unsaved file. Save it as calculator.py in the lesson folder". Pointing and hints use this too, and it overrides Haiku's generic `where`.
- **Inputs:** `screen` may be an E6 `ScreenObservation` (`lines_by_app`), a `ScreenContext`, a `{app: [lines]}` dict or plain text. `files` is `{path: text}`, notebooks become cell sources.

## Scene look (scene.py)

Every ~5 s during a lesson step (when the screen changed), the orchestrator's `scene_watch.py` sends Haiku 5.5 one
downscaled screenshot (<= 1280 px; Miyagi's overlay, other folders' VS Code windows and private apps blacked out) plus
the step (title, file, code, run command, check labels, what the spotlight points at) and gets strict JSON back:
`{app, window_title, active_file, step_file_open, step_code_visible, typed_fraction, error_visible, dialog_visible,
learner_doing, spotlight_target_visible}`. Thinking off, effort low, ~2.1-2.6K tokens in, 50-160 out: ~$0.0003 a look,
one INFO line each (`scene look s2 812ms img 1280x800 in=2310 out=95 $0.00028 (total $0.0123, 41 looks) | …`).

- `scene.fresh(step_id)` is the latest look when < 8 s old. The judge and Explain add it as one prompt line labelled
  "context only, not evidence" (Explain in lesson mode leaves the active file out); Hint drops its "Open <file>" Where
  row when the look saw the step's file as the active tab and the editor window doesn't disagree.
- `scene.with_error(step_id, text)`: diagnose appends an error a look saw (< 15 s ago, after the step ran something)
  to its error text when the terminal / OCR text doesn't already have it. No extra call.
- A look never passes or fails a check. `scene.FakeLook([...])` replaces `look()` in tests (no API).

## Pointing: Explain / Show me / Hint (pointing.py)

Every coach answer about the screen carries `targets` (`[{boxId, label, text, rect}]`, screen points), or a `where` instruction when the place isn't on screen. There is never a fake target.
- `await coach.show_me(step, screen, last_offtrack)` returns `{stepId, targets, caption, where}`. It points at the diagnosed line if there is one, else the step's `targets[].match` (whole word), else Haiku.
- `coach.hint(step, level, last_offtrack, screen=screen)` stays synchronous and uses an exact match only. When the code isn't visible the card carries `where` ("Open pinn_diffusion.py in your editor"); the app shows it as the Where row with Open, and the body stays the hint itself (never "Open … Then: …"). Terminal lines that merely mention the file don't count as the code.
- `await coach.explain(step, q, {"screen": s, "on_targets": cb})` points in parallel with the Opus text. `cb` fires first: live, at 1.7 s, against a 3.1 s card. Opus gets text only.
- `await coach.point(step, screen, about=...)` is the shared helper. An exact match takes about 0 ms. Otherwise `claude-haiku-5-5` (thinking disabled, text only, 3 s cap) picks box ids, live in 1.0–1.8 s. If nothing matches, `where` is either derived from the step (file, `.ipynb`, or the terminal command) or Haiku's 12-word instruction.

## Circle to ask (circle.py, Nov 22)

The learner holds Fn+Control and circles part of the screen. The app sends the existing ask command with the circle's bounding box: `action {kind: "ask", text, region: ScreenRegion, source: "circle", askId}`. `text` is the spoken words, or "What is this?" when nothing was said; the engine uses that default for an empty text too. It works with or without a lesson.

```python
out = await coach.circle_ask(step, "What is this?", region, obs=obs, image=pil,
                             context={"lesson": ..., "memory": ..., "lesson_folder": ...}, ask_id="a1")
# -> {kind: "answer", title, body, askId, region, stepId?, marks: [Annotation], _meta}
```

- **Engine path.** `main.py` passes `region`, `askId` and `source` to `LessonSession.action`. `_action` hands an ask that has a region to `server/orchestrator/circle_ask.py`, ahead of the "No lesson is running yet." check. Because it runs inside `action()`, proactive cards wait while the question is answered, the same as a typed ask.
- **One frame.** `ScreenBridge.ask_frame(region.displayId, region)` -> `ScreenReader.capture_once` captures and OCRs one frame now (~0.3-0.5 s, capped at 3 s) on the display the learner circled on. If that display id is not active, it reads the active display that holds most of the circle (`macos.pick_display`). If no display holds it or it can't be captured, it reads the usual display (`macos.target_display_id`). It always tries: the reader's last error (`down_reason`) can be stale while it is paused, so it only picks the words of the "can't see" card when nothing was captured. The learner asked, so it also captures while the reader is paused (no lesson step). It only checks the macOS permission and never prompts. The frame is published nowhere: no `on_screen` / `screen.seen` / check / spotlight from it, and the reader's last frame, display key and blank streak stay as they were. A blank frame gives no picture. If the capture fails but the last frame is under 5 s old and live, the answer uses that frame's text, with no picture.
- **DEMO fixture.** With `DEMO=1` and no Screen Recording the reader swaps in a fixture PNG (`source "fixture:..."`). A circle ask never explains that: it gets the plain "I can't see your screen" card. Only an explicit `TUT_SCREEN_FIXTURE` (dev, tests) is read as the screen.
- **Region.** `clamp_region` makes the numbers finite and the size positive. It keeps the part on the captured display (a region off that display gets "I couldn't read that screen"), caps each side at 1200 points around the centre, and makes a tap at least 24 points, slid back inside the display. The prompt says when part of the circle was cut.
- **Boxes.** Only the OCR / accessibility boxes with at least 30% of their area inside the region plus 12 points are kept, through the shared `ScreenContext`. The crop blacks out every secret row of the whole frame (also a long key row with only a sliver inside the circle) and other projects' VS Code windows, as everywhere else.
- **Prompt.** It carries the step (context only), the lesson's memory notes (`server/context`, only with a lesson), the circled text and box list inside `<untrusted source="screen">` blocks with `DATA_RULE` in the system prompt, the learner's words, and a JPEG crop of the region (long side 1280 px or less) when the frame has a picture. Model: Haiku (`coach.circle_ask`, `COACH_MODEL_CIRCLE_ASK`), thinking off, effort low, `max_tokens` 600, 10 s timeout, with the connection retries every learner question gets (12 s budget). With the 3 s capture, every circle ask is answered within about 25 s (`circle_ask.ANSWER_WITHIN_S`, also in the contract), so the app can set its pending-circle timeout to match.
- **The crop** is built in memory for this one request. It is never written to disk, logged, recorded as a fixture image, or put in the card or `_meta`. The session record keeps only the question and the region's size.
- **Answer.** The card is `card {kind: "answer", title (6 words or fewer), body (about 45 words), askId, region}`, with the region echoed as the app sent it so the card sits next to the circle. A body sentence that talks to an AI (`flag_injection`) is dropped.
- **Buddy circle.** When the answer names one box inside the region (the model's `box_id`, and either the label shares a real word with that box's text or the body says at least half of its real words; stop words like "the", "to" or "is" never count), `annotate {marks: [{id, x, y, w, h, displayId, label, why: "answer", askId, stepId?}], holdMs: 6000}` follows. There is no mark when that box is the only thing in the circle, because the learner's own ink already shows it.
- **No model** (no key, `DEMO=1` / offline, an API error, a stubbed coach): the card is "Here's what I read" with up to 20 words of the circled text, or "Nothing to read there". It never raises "Couldn't reach Claude".
- **No screen** (no Screen Recording, no reader, display asleep): "I can't see your screen", with "Turn on Screen Recording for miyagi in System Settings." when it is the permission.
- **Every circle gets a card with its askId.** A failed ask gets "Claude couldn't answer" (with Try again, in a lesson) or "I couldn't read that", stamped with `askId` and `region`. If the learner changed step while it was answered, a short "We moved on" card (no `stepId`) goes out instead of the old step's answer. Only an ask whose lesson ended meanwhile gets no card: the app's pending-circle timeout covers that one.
- **Before you start.** A circle ask while the "Before you start" sheet is up does not begin the lesson: circling the screen is not a step control.
- **Typed and voice asks** with an `askId` get it echoed on their answer card. Nothing else changes for them.
- **Keystrokes stay work.** Only a typed ask marks the learner's recent keys as typed into miyagi (E5 `inputs.mark_foreign`). A circle ask (with a region) or a voice ask types nothing there, so their VS Code keys still count as lesson work.
- **`why: "point"` marks** are reserved in the contract. The engine sends only `"answer"` marks. The coach's pointing reaches the app through `spotlight`, `card.targets` and `offtrack` targets, and the buddy draws from those on the app side.

**Not verified yet.** Everything above ran only in offline tests with fakes (`server/coach/tests/test_circle.py`, `server/orchestrator/tests/test_circle_ask.py`, `server/screen/tests/test_capture_once.py`). Nothing ran in Electron, against a real multi-monitor setup, or against a live model. Still open:
- whether Electron's `Display.id` equals the CGDirectDisplayID on every Mac setup (mirrored displays, Sidecar);
- the real OCR boxes and crop alignment on a Retina display;
- Haiku's answer quality, and how often it picks a `box_id` the answer really names;
- the end-to-end latency.

The app also has to add `'annotate'` to the KNOWN set in `app/src/common/wire.ts` (a core request) before it sees the event.

## Voice (ElevenLabs track)

`voice.py` speaks short lines only: the step title on `step.started`, the card title on `offtrack`, and "Nice, step passed." on `step.passed`.
- **Synthesis:** ElevenLabs streaming TTS (`POST /v1/text-to-speech/{voice_id}/stream`, `eleven_flash_v2_5`, `mp3_44100_128`). The MP3 is cached under `~/.cache/sandhacks-tutor/tts` by a hash of voice, model and text, and identical concurrent lines make one request.
- **Readable text:** 1e-3 is read as 0.001, β as beta, lr as learning rate.
- **Serving:** `voice.router` serves `GET /tts/<hash>.mp3`; names are validated as hex only.
- **Payload:** `speak_event(event, payload)` returns the existing contract's `speak` payload `{audioUrl, text}`, or `None`. It never raises; a failure means no audio and one log line.
- **Prefetch:** `voice.prefetch([titles])` right after the lesson loads makes step starts instant.
- **Gate:** E4 owns it (voice toggled on, and no keystroke in the last 2 s).

## Fast circle to ask, streamed (fast_ask.py + orchestrator/circle_ask.py + orchestrator/fast_region.py, Nov 22)

Goal: the first words of the answer show within about 1 s of releasing Fn+Control (miyagi-v2/CIRCLE-TO-ASK-SPEED.md). Nothing here is measured live yet. The streaming speed-up also needs the cloud proxy's streaming (`claude/eng-proxy-next`); a cloud that still buffers works the same, only slower (the words arrive together).

- **The hold.** The app (v2-integration `features/ptt`) sends `ask.warm {pttId?}` on every hold past the minimum, but only when `engine.hello.capabilities` lists `"ask.warm"`; `Engine.capabilities()` lists it. main.py answers it beside the command queue (INSTANT) with `fast_ask.warm_soon(source, ptt_id=...)` (pttId and source go to the log only): the keep-alive client to the miyagi cloud or Anthropic opens (HTTP/2 when the `h2` package is installed, else HTTP/1.1 keep-alive), and at most once per 4 minutes per (route, model) one `max_tokens: 0` request, never streamed, writes the cached prefix (the fixed `SYSTEM_PROMPT`, about 800 tokens, over the 512 minimum, with `cache_control`; that model's thinking and effort). Both ask models are warmed: Haiku 5.5 (the default "What is this?" ask, about $0.0001) and Sonnet 5.5. In between, a free touch (`GET /healthz` on the cloud, `models.retrieve` direct) keeps the engine-to-cloud connection open. An ask restarts its own model's 4 minute window.
- **The circle (keys still held).** The app's helper (miyagi-listen, `ptt:capture`) captures the circled region while the keys are held and the action ask carries it: `action {kind: "ask", region, source: "circle", askId, capture: AskCapture}`. main.py stamps `release_t` (`time.monotonic()`) on the action as it arrives, before the command queue, and passes `capture` and `release_t` through `LessonSession.action` / `_action` to `circle_ask.answer`.
- **The crop.** `circle_ask._stream` calls `shared.capture_file.take_capture(capture)` first: realpath inside the per-user `miyagi-capture` folder, the helper's file name, a regular 0600 file of this user, a JPEG whose own size is `w x h`; it reads it and deletes it (also offline, so the file never stays). Nothing is captured at release then. Only when it returns None (no capture, an older app, a failed check) does `fast_region.frame_for` capture the display now (`ask_frame`, 0.3 to 3 s) and crop it from the frame's `ScreenContext.pil()` (secret rows blacked out): `jpeg, rect, W, H = fast_ask.crop_region(screen_ctx, clip)`, the rect being exactly what the JPEG shows. **Never pass the raw frame**, and never a rect you computed yourself. `ask_stream` takes bytes (or a PIL image) only, never a path: a path from the WebSocket payload goes through `take_capture` and nowhere else.
- **The ask.** `res = await fast_ask.ask_stream(jpeg, rect, W, H, words, lesson_context, emit=session.emit, ask_id=..., display_id=..., step_id=..., release_t=..., should_stop=...)`. `lesson_context`: `{lesson, step, memory, screen_text, app}` as strings (`fast_region.lesson_context()`); the screen text, app, lesson and memory go in `<untrusted>` blocks (the helper's crop has no OCR text: the picture alone).
- **Request.** Image first, then the text (the crop size in pixels, the context, the words), history as text only, `stream: true`, `max_tokens` 1024, effort low, thinking off: Sonnet 5.5 sends `between_tools` (its `disabled` is a 400), Haiku 5.5 sends `disabled`. Haiku answers short simple questions ("what is this?"); Sonnet the rest (`coach.fast_ask` / `coach.fast_ask_simple` in server/models.py). Fast ask is hard-pinned to Haiku 5.5 / Sonnet 5.5: an Opus, Fable or Mythos override becomes Sonnet (or Haiku for the simple ask), also with `MIYAGI_ALLOW_OPUS=1`.
- **Stream.** Line 1 is `[DRAW:x,y,r:label]` or `[DRAW:none]` in crop pixels. `DrawStream` parses it as chunks arrive (split tags, malformed, missing, words before the tag on line 1, a reply wrapped in a ``` fence). A valid tag is clamped into the crop (a radius of 0 or less to `MIN_R_PX`) and mapped to screen points (origin + px * crop points / W, the same formula as `capture_file.crop_to_screen`), then goes out at once as `annotate {marks: [{why: "answer", askId, ...}], holdMs}`. Every word is `answer.delta {askId, seq, text}`; the end is `answer.done {askId, text, complete, fallback?, reason?}`. Only a full, valid `[DRAW:...]` is taken out of the words, so "[drawer]", "[draw.io]" and a trailing "[D" stay; lone ``` lines are dropped from `answer.done.text`.
- **The card.** `circle_ask.answer`: `res.error == "moved_on"` or a step-gen change: `moved_on()`. `res.ok`: the card `{kind: "answer", askId, region, stepId, title: res.title, body: res.text}` with no extra `annotate` (the mark went out already). Words streamed and then it broke (`res.deltas > 0`): `failed_card` replaces them. Otherwise (offline, no key, a cloud refusal, a 4xx, no picture): the one-shot `session.m.circle_ask` card as before, with the frame `frame_for` already took or a capture now.
- **Injection sentences.** Deltas go out as the words arrive, so a sentence the engine flags as an injection can show in them. `answer.done.text` never has it, and the contract says the app must replace the deltas with it.
- **Refusals.** A refusal after words (Haiku 5.5 has no server-side fallback) sends `answer.done {text: "", complete: false, reason: "refusal"}`, so the declined words leave the screen, and the failed card follows. Sonnet 5.5 runs with the server-side fallback (`fallbacks: "default"`).
- **Failures.** A dropped connection, a 5xx / overloaded error or a broken stream: one retry of the same request without streaming (`answer.done fallback: true`). A cloud refusal (paused, quota, auth), a 4xx, a refusal, offline mode, no key: no retry.
- **Cost tally.** Every billed attempt counts: a broken stream's snapshot usage, the retry, and after a server-side fallback every entry of `usage.iterations` (the top-level usage covers only the final attempt), each at its own model's rate, so the tally matches what the cloud reserves and settles.
- **Metrics.** One `ask.metrics {json}` log line per ask, and `<state dir>/ask-metrics.jsonl` (last 500, appended in a worker thread so a slow disk never holds the event loop): hold to warm, hold to release, release to request / first byte / first token / mark / done, model, route, token counts. Never the question, the answer or the picture.

### What the warm-up keeps warm (and what it does not)

- The free touch (`GET /healthz`) keeps only the engine-to-cloud link warm. The cloud keeps its own link to Anthropic for `UPSTREAM_KEEPALIVE_S` (90 s, cloud/README.md), so between two billed warm-ups (4 minutes apart) that cloud-to-Anthropic TLS link goes cold; an ask then pays one extra TLS handshake on the cloud side (about 100 to 200 ms). This is accepted: `/healthz` never reaches Anthropic, and a cheap upstream touch would be a billed call or a new cloud route. A hold right after a billed warm-up (or an ask) finds every link warm.
- The billed warm-ups (2 per 4 minutes at most: Haiku and Sonnet, so at most 30 an hour) count toward the cloud's rate limits like any `/v1/anthropic/*` call: per install token (2400 an hour) when the token is known, else the 100 an hour per-IP limit. `/healthz` touches are never limited.
- A cloud that still buffers SSE (production before `claude/eng-proxy-next`): everything works, the words just arrive at once with `answer.done`.

### Core requests (Adrian, app core)

- None for this lane. The app already sends `ask.warm {pttId}` on each hold (v2-integration `ptt.ts`, gated on the hello capability, which this engine now lists) and `capture` on the circle ask (`ptt:capture`). The helper's crop leaves the overlay (and its ink) out. The release fallback (`ask_frame`) is the same capture the one-shot circle ask used before, so whether its picture shows the ink is unchanged by this lane and not checked here; with the helper's crop on every circle ask it only runs for an older app or a failed check.

## Orchestrator contract notes (E4)
- **Latency.** Web grounding runs only when there is an error message to look up, capped at 4 s, and keeps whatever lookups finished in time. A metric-only failure like the hero goes straight to Opus. Live: card in 3.4 s after `warm()`. Rehearsal had measured 7–8 s while it waited on unused searches.
- **Offline stage fallback (opt-in).** With `COACH_OFFLINE_FALLBACK=1`, if Opus is unreachable (network/proxy down) and the playbook matches the learner's code with confidence ≥ 0.6, `diagnose` returns that playbook card marked `offline: true` (and `_meta.route=playbook`, `fallback_reason`). API errors, refusals and weak matches still raise `CoachUnavailable`. It is off by default because of the no-fake rule.

- `diagnose(..., cursor={"x", "y", "under": {"text", "app", "rect"}})` and `explain(..., {"cursor": ...})` tell the coach what the learner points at, when no full `screen` is attached.
- The body's last sentence states the fix in words ("Set lr to 1e-3 in the Adam optimizer."), because E4 shows the first offtrack as hint level 2 with the diff hidden. Bodies are about 30 words. Up to 42 pass untouched; past that, the cause is shortened and the action sentence is never cut.
- `diff.command` carries a terminal fix (`pip install pandas`). It can come alone (`expected` empty) or with a code diff. E4 copies it to the clipboard.
- `hint(step, 0, last_offtrack)` asks the card's `guidingQuestion`, else the playbook entry's, else a question built from the card's title. A cached card from before guiding questions still gets an issue-specific question.

## Design

- **General, web-grounded** (GENERALITY RULE). `web.py` detects the library and symbol from any error on screen (Python tracebacks, eslint/React, Node, npm, CLI tools). It then fetches the official docs/changelog (`docs_for`) and Stack Overflow / GitHub / Reddit posts (`community_signals`) through DuckDuckGo's HTML search (restricted to official domains with `site:`), then a plain GET of the page. This runs in parallel with triage and has a 6 s budget. The pages go into the Opus prompt as `[web:N]`, and the card cites the URL it used. When `server.finder.web` (E7) lands, its `docs_for` / `community_signals` are used instead. With the web off (`COACH_WEB=0`, offline mode) or a timeout, the coach falls back to playbook and lesson sources.
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

Fixtures in `server/coach/fixtures/` are recorded live responses: Opus 5.5 diagnose + explain for the PINN demo, Opus for a React hooks lint error and a removed pandas API (`tests/generic_cases.py`, with the web replaced by excerpts of the real react.dev / pandas pages), and Haiku 5.5 triage, keyed by a hash of the request. Re-record with `--live --record` after changing the demo case. Env: `ANTHROPIC_API_KEY`; `COACH_WEB=0` turns live web search off (tests set it); `COACH_REPLAY_DIR` / `COACH_RECORD_DIR` for fixtures.

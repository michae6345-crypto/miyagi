# eng-session (E3: session fields for the v2 lesson panel)

**Status:** implemented, pushed, not merged · **Branch:** `claude/eng-session` (from `origin/claude/eng-drop-vendors`) · **Engine only** (no app files, no port) · BUILD-PLAN section 3, E3

## Goal
The engine sends what the v2 lesson panel, Home-Building, the error surfaces and the completion panel draw (W0-1 contract, `origin/michael/app-core-v2` `shared/contracts/events.py`): what the engine is doing, which hint rung, which lines are missing, what the learner just did, where to type, the build checklist, why a build failed, a paused lesson when VS Code is closed, the kernel blocker, and the completion result. Every field is optional and additive. New event types and card kind `complete` go out only to a v2 app.

## Files (only these)
`server/orchestrator/session.py`, `server/orchestrator/curated.py`, `server/orchestrator/lesson_end.py`, `server/workspace/editor.py`, `server/sessions/store.py`.

## What changed
- **v2 app gate** (`session.py`): `LessonSession.app_v2`, set by `note_app_v2(type_)` when the app sends any v2 command (`V2_COMMANDS`: health.get, permission.open, library.*, progress.get, panel.state), or `MIYAGI_APP_V2=1`. Only then do `lesson.paused`, `lesson.resumed`, `blocker` and card kind `complete` go out. An older app sees none of them.
- **`status.detail`** (6 words max): `_status(state, detail=...)`. Sent when the state or the detail changes. Details on each thinking state: Checking your work, Writing a hint, Writing an explanation, Writing an answer, Drawing a diagram, Building your lesson, Writing your lesson, Loading the lesson, Finding a lesson, Looking at the video, Building the next steps, Looking at your code, Writing the fix, Typing the step for you, Running it for you, Downloading the files, Opening VS Code. A reconnect while a build runs replays the detail too.
- **`card.hintStep`** on hint cards for the current step (`hint_step`):
  - the diagnosed look-then-fix hint (`card_copy.diagnosed_hint`): n of 2;
  - the curated cached ladder: `curated.hint_rung` (n counts from when the loss got stuck, as `hint_card` does) of `curated.hint_count`;
  - the coach's four levels (`coach/hints.py LEVELS`): level + 1 of 4;
  - otherwise none (no "of" we can't stand behind).
- **Not yet cards** (title "Not yet" or verdict `not_done`, current step, not a run step): `missingLines` (each line of the step's code, dedented once with each line's own indent kept so a loop body stays indented, `ok` when the learner's text has it with spaces ignored, else `missing`) plus `fixCaption` ("Add the first line, then run the cell" / "..., then check again"). Only when something is missing and the step has at most 8 lines. The learner's text comes from the notebook's cells, else VS Code's live buffer (companion), else the file on disk, read in a thread. While the kernel blocker is up, step/hint/where cards carry `waiting: "Watching for a kernel to start"`.
- **`step.passed.summary`** (12 words max, never on a skip): a run step's real numbers from the learner's own run (`lesson_end.metric_line`, e.g. "Loss 0.49 → 0.0009 in your last run."), else the step's `summary` / `what`. Nothing when neither fits.
- **`step.started.where` / `then`** (`where_then`, in `_step_started_payload`, so replays carry them too):
  - notebook: "Type this in the new cell" (Les-Working / Les-Checking wording), then "Then run it with the arrow beside the cell.";
  - file: "Type this in calc.py";
  - run step: "Run this in the terminal". The curated lesson's run steps add "Or click ▷ at the top right of nn.py." (`curated.step_copy`).
- **`lesson.building`** (shaped in `emit`, and in the reconnect snapshot):
  - `stage` + `phases`: Watching the video (or "Reading the transcript") / Finding the steps / Writing the checks / Ready to start. Text lessons: Planning the steps / Writing the checks / Ready to start. Mapped from the existing stage messages (`build_stage_of`).
  - `source`: YouTube title (and `durationS`, `channel`) from the picked search row, else "YouTube video"; for a goal, the goal or the curated title.
  - `etaS`: the existing `ORCH_BUILD_EXPECTED_S` estimate minus the time elapsed, only while 30 s or more are left (video builds only).
  - Failed builds add `failCode` (`build_fail_code`: too_long / network / provider / no_captions / no_steps / unreadable_code / unknown; 401 / 429 / ssl matched as words, never inside a video id or URL; a rate limit on the transcript or YouTube is `network`, Gemini quota or budget is `provider`, and `no_captions` is only a missing transcript), `failReason` (the message's first sentence) and `source`. They add `alternatives` only from E1's `server.lesson.library` (`kind: "library"`, id, title, meta such as "Jupyter in VS Code, 6 steps"). Until E1 merges that list is empty.
  - No transcript-only alternative: the engine has no `learn_url.transcriptOnly` path yet (core request 4).
- **Pause and blockers** (v2 app, a running lesson, the real screen reader only):
  - `tick` polls `editor.lesson_window_state(workdir)` every 3 s. It never polls in the first 30 s after the engine opened VS Code (a cold start). Two sure misses in a row (VS Code quit, or windows open but none on the lesson folder) send `lesson.paused {reason: "editor_closed", title "VS Code closed. Lesson paused.", body "Your place is saved. Reopen the notebook and pick up at <step>.", stepId}` plus `blocker {kind: "editor_closed", title, body, action: "open_editor"}`, and clear the box.
  - While paused, `tick` holds the scene look, the judge, the stuck card and the coach. `_held_by_pause` drops the engine's own `where`/`step` cards, off-tracks and boxes: these would duplicate the app's paused surface (the "duplicate screen card"). Check, Confirm, Hint and Show me answer with `lesson.paused` again.
  - When the window is back: `lesson.resumed` and `blocker {kind, clear: true}`, the screen reader resyncs and the step's box goes out again.
  - Notebook lessons: a VS Code OCR line reading exactly "Select Kernel" sends `blocker {kind: "kernel", title "Pick a kernel so your cells can run", body "No kernel is running, so I cannot check this cell.", rect}`. The rect is that control in screen points, re-sent only when it moves 4 pt or more. Two frames without it, with VS Code on screen, send `{kind: "kernel", clear: true}`. A non-skipped `step.passed` clears it too (a notebook check that passed ran a kernel), and `_kernel_check` clears it once the step has passed, so it never stays up on Les-Passed or leaks `waiting` onto the next step.
  - `lesson.ready` / `lesson.ended` reset the pause and the blockers. A reconnect snapshot replays them (`v2_snapshot`) and no longer replays an off-track while paused.
- **`panel_state(open, rect)`** (for E2's dispatch): notes v2. When an open panel's left edge moved, it narrows the lesson window to sit beside it (`editor.fit_beside_drawer`, only windows that reach under the panel, Accessibility only, never in tests). A collapsed panel keeps the room as it is, so the window doesn't jump.
- **Completion** (`lesson_end.py`):
  - The card always carries `result {passed, skipped, total, minutes?, lessonId, title}`. Skips count as skips. `minutes` only when this engine ran the lesson from step 1 (`lesson_wall_t0`; a restored lesson has none).
  - Kind is `complete` for a v2 app, else `step` as before.
  - After the card goes out, `store.attach_completion` puts its exact `skillMap` (assisted steps practiced, the real proof) and `result` on the history entry.
- **History** (`store.py`): `record_completed` stores `skillMap` (made with `lesson.skillmap.skill_map` from the passed and skipped steps when not given) and `result {passed, skipped, total}` on each `history.json` entry. E1's `sessions/progress.py` reads both. New `lesson_result()` and `attach_completion()` (an entry finished within the last hour only).
- **Editor room** (`editor.py`):
  - `DRAWER_W` is 392: panel 360 + inset 16 + gap 16. `fit_full` uses it only for a v2 app (`session.note_app_v2` → `editor.note_app_v2`, or `MIYAGI_APP_V2=1`) or once a panel.state rect was reported; otherwise it keeps the v1 drawer's `DRAWER_W_V1` 436, so this branch can land on run-live before A1's 360 panel without the v1 drawer covering VS Code's Run button and panel toggle. `MIYAGI_DRAWER_W` still overrides both.
  - `fit_full(visible, panel=None)`: the one pure frame rule, shared by `make_fullscreen` and `fit_beside_drawer`. The frame sits under the pill and above the bar, and ends 16 pt left of the reported panel, else `drawer_reserve()` short (392 v2, 436 v1), never under `EDITOR_FRACTION`. At 1440 wide that is 1048 pt from x 0 for a v2 app (panel at x 1064), 1004 pt for the v1 drawer.
  - `note_panel(open, rect)` / `panel_rect()` keep the panel's edge.
  - `lesson_window_state(folder)` returns True, False or None. It returns None (no pause) when titles can't be read, e.g. no Screen Recording grant, or VS Code runs with no window.

## Checks run
- `python -m py_compile` on the 5 files: OK (run-live's venv interpreter, Python 3.12).
- Import check with the keys empty (`ANTHROPIC_API_KEY= GEMINI_API_KEY= BRIGHTDATA_API_KEY= TIGER_DATABASE_URL=`) and `python -I`, with this worktree put first on `sys.path` (plain `-I` resolves `server` to run-live's tree through the venv's `.pth`): `server.orchestrator.session`, `curated`, `lesson_end`, `main`, `server.workspace.editor`, `server.sessions.store`, all from this worktree: OK.
- An offline script (scratchpad, not committed; temp state dir, no network, no model calls): 67 checks pass. It covers:
  - the pure helpers (stages, phases, fail codes, where/then, missing lines and captions, hint rungs, word caps, em-dash removal);
  - `fit_full` (1048 at 1440, a reported panel at 1000 → 984, the minimum fraction);
  - `record_completed` with a skip (result 5/1/6, skillMap stored) and `attach_completion`;
  - `lesson_end.result` (no minutes for a restored lesson) and the card kind (step for an older app, complete for v2);
  - `status.detail` dedupe, `step.passed.summary` (none on a skip), where/then on the curated steps, `lesson.building` fields;
  - no pause for an older app, pause then resume, the held where-card and off-track, Check answered with `lesson.paused`, the snapshot replay;
  - the curated hint rung (1 of 2);
  - `_v2_tick`: two misses pause and the body names nn.py and Backprop, back resumes, kernel blocker with rect, no re-send, clear after two frames.
- No pytest, no paid calls, nothing touched on :8787, no app or VS Code touched.

## Core requests
1. **W0-1 contract on this tree** (`shared/contracts/events.py` + `events.ts`, the `contract:` PR from `michael/app-core-v2`): the run-live / eng branches still carry the old contract. Until it lands, `Hub.encode` warns, or raises under `ORCH_STRICT=1`, on `lesson.paused`, `lesson.resumed`, `blocker`, card kind `complete` and status state `busy`. All of these go out only to a v2 app, so nothing changes for today's app. The new fields on existing events pass already (`extra="allow"`).
2. **E2 (`orchestrator/main.py` dispatch)**:
   - for every v2 command call `engine.session.note_app_v2(msg.type)` before handling it;
   - `panel.state` → `await s.panel_state(p.open, p.rect.model_dump() if p.rect else None)`;
   - `ws_endpoint`: decide whether `app_v2` should reset per connection (it is sticky today: one app per engine).
   - Better long term: an app hello listing its own capabilities (contract), so the engine needn't infer v2 from a command.
3. **A2 / A8 (cards, completion)**: card kind `complete` (with `skillMap` and `result`) arrives only after the app sent a v2 command (panel.state is enough). Route it to A8's completion panel, never to the step-card table. `result.minutes` is absent when unknown: show no time rather than 0.
4. **Transcript-only builds**: Err-LessonBuildFailed's "Try transcript only" needs `learn_url {transcriptOnly}` handled in `session.learn_url` → `modules.build_lesson` → `lesson/builder.py` (no such path today). Until then the engine sends no `transcript` alternative, only library ones.
5. **A7 (errors)**:
   - `blocker editor_closed` carries `action: "open_editor"`: Reopen sends `action {kind: "open_editor"}`, End sends `end_lesson`;
   - `blocker kernel` has no action, only `rect`, the real Select Kernel control to point at with ▷;
   - `lesson.paused.reason` is `editor_closed` only for now. `kernel` stays a blocker, not a pause: the mockup shows it in context with the step.
   - on `lesson.ready` and `lesson.ended` the engine sends `blocker {kind, clear: true}` for each blocker it still holds, then forgets them; no `lesson.resumed` follows a pause there. The app drops every blocker and the paused surface on either event anyway.
6. **`screen/ax.py` (not this lane)**: a `ui:select_kernel` AX key (like `ui:interpreter`) would give the kernel blocker an exact rect without OCR. Today it is the OCR line's rect.
7. **Tests to update (not run here)**:
   - assertions on exact `status` payloads (`{"state": "thinking"}`) now see `detail` on the thinking states listed above;
   - a same-state status with a new detail is one more `status` event;
   - failed `lesson.building` payloads gain `failCode` / `failReason` (and `source`);
   - `step.started` payloads with code gain `where` (and `then`);
   - history entries gain `skillMap` and `result`;
   - `DRAWER_W` constant 436 → 392, but `fit_full` still reserves 436 (`DRAWER_W_V1`) until a v2 app is known. Several assertions break on merge (the list below). `server/orchestrator/tests/test_t10_layout.py:51` (`test_full_screen_layout_starts_below_the_pill`) checks `w == 1728 - E.DRAWER_W` (now 1336) while the v1 frame is 1292. New expectation: `w == 1728 - E.drawer_reserve()` (or `1728 - E.DRAWER_W_V1`).
   - `server/orchestrator/tests/test_session.py:1035`: the mid-build snapshot status is now `{"state": "thinking", "detail": "Building your lesson"}`, not `{"state": "thinking"}`.
   - `server/orchestrator/tests/test_session.py:1045` (`test_build_success_still_loads_the_lesson`): `rig.of("lesson.building")[-1] == {"message": "Lesson ready", "progress": 1.0}` fails. "Lesson ready" (session.py, `_build`) goes out before `load_graph` clears `_build_v2`, so `_building_v2` adds `stage: "ready"`, `phases` (all done) and `source {kind: "youtube", title: "YouTube video", url}`. New expectation: compare only `message` and `progress` (`{k: ev[k] for k in ("message", "progress")}`), or include the three v2 keys. The curated and text builds' "Lesson ready" events carry the same `stage` / `phases` plus `source {kind: "goal", title}` when a title is known; any test that compares those payloads whole needs the same change.
   - `step.passed.summary` on a run step uses the run's metric line only when it comes from the newest run ("... in your last run."); an earlier step's run falls through to the step's own `summary` / `what`.
   - `server/workspace/editor.py` keeps `_app_v2` and `_panel_rect` as module globals that stay set. A test that calls `note_app_v2()` or `panel_state()` leaks the 392 reserve into every later layout test, so those tests need a reset fixture (`monkeypatch.setattr(E, "_app_v2", False)` and `monkeypatch.setattr(E, "_panel_rect", None)`, autouse in the layout test modules).
   - Worth adding: the offline script's cases (scratchpad `e3_check.py`).
8. **Wave 2 integrator**: once the shortcut bar is off in lesson mode (`Feature.enabled`), `MIYAGI_BAR_CLEARANCE` can drop to 0 so the editor uses the full height beside the panel.

## Fix round 1
- Kernel blocker cleared on a passed step (`_v2_shape` step.passed, `_kernel_check`).
- Not yet rows keep relative indentation (`textwrap.dedent`, `rstrip`); matching stays whitespace-insensitive.
- `lesson.building.source.channel` from the picked search row.
- `build_fail_code`: word-boundary status codes and ssl; rate limits classified before the transcript test.
- `fit_full`: 392 only for a v2 app or a reported panel, else 436 (no merge-order dependency on A1).
- where copy: "Type this in the new cell".
- Removed the unused `_panel_x`.
- Checks: py_compile and the empty-key `-I` import of session, editor and main pass; an offline probe (scratchpad `e3_fix1_probe.py`, 23 checks: fail codes, indent rows, where copy, fit_full v1/v2/panel, kernel clear on pass and on step.passed, a skip keeps it) passes.

## Notes
- The editor_closed poll catches VS Code quit, or the lesson's window closed while other VS Code windows stay open. It does not catch the last window closed while VS Code keeps running: titles alone can't tell that from "titles unreadable", and a false pause is worse than a missed one.
- `card.hintStep` for the live coach reads the card's own `level` (0..3 of 4). If a level is skipped (no video timestamp), the rung follows the level, not the press count.
- `missingLines` compares whole lines with whitespace and a trailing `# comment` (outside quotes, after a space) removed, on both the step's and the learner's side; the shown `text` stays as written. A line typed with a different variable name counts as missing, which is the point of the Not yet.

## Fix round 2
- `snapshot`: the final reconnect status keeps `detail` while thinking ("Checking your work", "Writing a hint", "Drawing a diagram"), like the mid-build branch.
- `missing_lines`: a trailing comment outside quotes is dropped from both sides before comparing (`x = x / 255.0  # scale` matches `x = x / 255.0`); `"a # b"` and `x#y` are left alone.
- Core request 7 now names the two assertions that change on merge and the editor globals that need a reset fixture.

## Fix round 3
- `_passed_summary`: the metric line counts only from the newest run (the one that passed the step). An earlier step's "Loss 2.3 → 0.1 when you ran it." is not this step's number; it falls through to the step's `summary` / `what`.
- `emit` on `lesson.ready` / `lesson.ended`: a v2 app gets `blocker {kind, clear: true}` (raw, no re-entry) for each held blocker before they are reset. Core request 5 says the app drops blockers and the paused surface on both events.
- Core request 7 now also names `test_session.py:1045` ("Lesson ready" gains `stage`, `phases`, `source`) and the curated / text "Lesson ready" payloads.

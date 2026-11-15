# cards

**Status:** pass 3 done: the off-track card is layout C (side by side, Adrian's pick), off track has no hue anywhere in cards. Merged core 369d97b. Checked in the stage (headless Chrome), screenshots re-shot. Not pushed. · **Priority:** P0 · **Port:** 5177 · **Branch:** `adrian/cards`

## Goal
Coach cards that grow out of the pill. **Off-track** (amber): what's wrong in ≤12 words, the yours-vs-tutorial loss curve, "expected vs yours", the checks, and Show me / Explain / Apply fix. **Back on track** (green) after a recovered step; auto-hides. **Explain / Hint / Answer** cards from the engine, with an optional "jump to 7:00" video link. Calm: no shaking, no red.

## Owns
- `app/src/renderer/src/features/cards/`
- `app/mock/scenarios/cards.json` (optional: a `metric` stream for the live curve)

## Contract
- **In** (engine → app): `offtrack`, `step.passed`, `card`, `metric {runId, step, name, value}` (live curve), `check.updated`
- **Out** (app → engine): `action {kind: show_me | explain | apply_fix | hint}`

## Plugs in as
islandModes: offtrack (70), success (60), card (50)

## Done when
- Off-track matches the Apple restyle of mockup 06
- The curve draws from live `metric` events (the mock's `offtrack.curve` is the fallback)
- Apply fix → the card collapses, checks re-run, the success card shows when it passes
- Every card readable in 2 seconds

## Test
`npm run dev:web -- --port 5177` → `http://localhost:5177/?scenario=full`. Ctrl+K → type anything → Enter → Enter builds the lesson. Alt+E / Alt+H at step 4 or 6 → explain / hint card. About 30 s in, step 6 goes off-track (loss curve is live). Alt+E there → explain with a video jump; Esc returns to the off-track card. Apply fix → "Waiting for the fix" (the loss drops live) → "Back on track" → auto-hides. Esc dismisses; the HUD's Reset restarts.
`?scenario=offtrack` checks the fallback (no `metric` events: the curve comes from `offtrack.curve`, the success card shows the checks instead of a curve). `?scenario=cards` alone does nothing (it only overrides segments of the full run).
**Pass 2 flows (same `?scenario=full`):**
- Paste a YouTube link in the launcher (Ctrl+K, paste, Enter) → **preflight** card (Coding · 24 min · 7 chapters, Needs …). Build → the lesson builds, then a **setup** card: Install on PyTorch (progress lines, then a check), two linked files, Download tutorial files / Skip / Open Cursor.
- At step 7 (after Apply fix at step 6), Alt+S → "Code not visible" with the **where** line and its Open button.
- At step 6: Esc closes the off-track card, Alt+H brings it back.
- Every card button that waits on the engine shows the spinner (the mock sends `status thinking` around these).

**Pass 3 (layout C):** `?scenario=cards` = the word-count off-track on its own (level 2: question + diff + failing check; press Hint for level 3 and "Fix it"; Fix it passes the step). `?scenario=full` = the PINN off-track at step 6 (level 3: diff + failing check + sparkline).

Screenshots: `agents/shots/cards-*.png`: offtrack-c-wordcount, offtrack-c-wordcount-l3, offtrack-c-narrow, offtrack-c-pinn, offtrack-c-pinn-fixing, offtrack-c-pinn-success, offtrack, offtrack-stage, offtrack-question, explain, hint, fixing-1/2, success, generic-accuracy, preflight, preflight-warning, setup, setup-installing, download-busy, where, where-busy.

## Adrian's spec
**First pass (no spec from Adrian yet):** build to the mockups in `docs/mockups/` (01–05 are the target look; 06–07 are earlier explorations to restyle in the Apple look) and the animation + placement spec in `docs/FRONTEND-HANDOFF.md`. Don't spend time on colors (Adrian's theme comes later). Adrian reviews after this pass and writes his spec here for pass 2.

## Core requests
1. ~~**HMR on feature files**~~: fixed in core 0876da5 (lazy registry).
2. **Island sizes / timing: no change needed.** Off-track is ~620 wide (layout C; 300–620, following the overlay width, stacked below 520) × ~250–300 tall. This is wider than `pill.maxCardWidth` (520), on Adrian's pick; the island handles it. Earlier sizes: off-track was 460 wide, "Waiting for the fix" ~386, "Back on track" ~251, explain/hint 420 wide. All fit under `maxCardWidth` 520.
4. **Off-track demo copy in `mock/scenarios/offtrack.json` (core) doesn't follow the kit voice yet.** Suggested, step 6 `offtrack`: `title` "Loss is flat at 0.25", `body` "Add a β curriculum, then rerun.", `reason` "flat for 5,200 epochs" (the curve caption already says the metric). `explain_step6` body (18 words → 11): "Steep waves make early gradients vanish. The net settles flat." The cards only render what the engine sends, so this is a mock change, not a cards change.
5. **Links from the overlay window.** Only the player window has `setWindowOpenHandler` (https → `shell.openExternal`). The citation link and a setup row's "Get it" use `window.open`, which in the overlay would open a new Electron window. Suggest the same handler on every window in `main/index.ts`.
6. **Pick another during a build.** The launcher's Enter puts the pill in "building" (`startBuild`) before the preflight card. After Pick another reopens the launcher, nothing clears `building` until the next `lesson.building`/`lesson.ready`. Core (or the launcher) should clear it when the launcher reopens without a build.
3. *(FYI, nothing to do now)* Metrics live in `features/cards/store.ts` (`useCards(s => s.metrics)`, `useSeries()`), readable by other features (e.g. the overview card could show the live loss). If several features end up needing them, move them into `core/lesson.ts` later.

## Notes
**Pass 3: layout C (Adrian: "side by side")**
- Width: ~620, from the overlay's width (`offtrackWidth`: 32 px margin, 300–620). An invisible overlay layer (`cards-width`) reports `layout.width` into `useOverlayWidth`; the off-track mode's `width` is a getter, and its `useActive` subscribes so the island re-renders. Below 520 the two columns stack (`data-layout="stacked"`).
- Left: the white ring `StatusDot` + "Not yet" (color.label), ✕; the title (18 px semibold); the guiding question, or the body (2 lines) when there's none; Show me / Explain / Hint (`OptionButton`, platform keycaps, always shown); at level 3 with `apply_fix` the one white `PrimaryButton` "Fix it" (right). The press spinner (ink track on pastel/white) and ⌥H reopen are unchanged. The citation is one faint line (a link).
- Right (`Evidence.tsx`): `fill.field`, radius 14, mono 12 px; one table, yours | expected. Rows: the diff (code, `· L{line}` faint, the file as a faint label), each failing check (label; `detail` without "yours" | the expected value read from the label: a comparison like "< 1e-2", else its last number like "1,804", else "—"), the curve as a monochrome sparkline (yours white, tutorial faint) with both end values (live data only). Checked: no hue in the panel.
- No amber anywhere in `features/cards/`: the preflight warning and the "where" line are muted text with a lucide `Info` glyph; "yours" labels are faint.
- Mock: `?scenario=cards` plays the word-count off-track (connect → a 3-step word-count lesson; Hint → level 3; Fix it → passed). In `full`, `connect` is reset, so it doesn't run there.

**Pass 2 (functional, Michael's live-test list):**
- **Never look dead.** Every card button (white, pastel and quiet) swaps its icon for the core `Spinner` while `useThinking() && usePressed().kind === kind`. Engine-card buttons that wait on an answer (download, open_editor, build, confirm, apply_fix, undo, resume, end_lesson) also keep the card up, spinner on, until the engine answers: a new card or event, `status` leaving "thinking", `lesson.building` for the preflight Build, or 10 s. Skip and Pick another close at once; per-row Install / Open never close it.
- **Preflight** (`card.kind "preflight"`): one meta line (style · length · chapters · captions; captions come from the finder's `search.result` for the same videoId/url), "Needs …" from `card.items` (+ "N to install"), `warning` in amber, Build / Pick another with `recommended` as the white primary. Pick another sends `pick_another` and opens the launcher (`launcher:toggle`).
- **Download / setup**: `download` reads `setup.actionLabels.download ?? 'Download'`, quiet unless it's the only button. `setup.resources` listed under the items (icon by kind, name, kind). `open_editor` reads `Open ${setup.editorLabel}`. Setup rows follow `install.method`: "download" opens its URL ("Get it"), "open" sends `open_in_browser`, "none" has no button.
- **`card.where`**: one line ("Open plot_solution.py in Cursor") with an Open button (`open_editor`); the card's own open_editor button is then not repeated.
- **`guidingQuestion`** shows under the body on the off-track card and on engine cards, in `color.label`.
- **⌥H** while the off-track card is closed (and nothing else is up) brings it back and is claimed, so no new hint request goes out. With the card open, ⌥H asks for a hint as before.
- **Citation**: the label is a link (`window.open`), see core request 5.
- **Mock**: `learn_url` → preflight (overrides happy's `learn_url` on purpose: paste → preflight → Build → happy's `lesson`), `action:build` → lesson + setup card, `action:install` → progress → re-sent card, `action:download` / `action:open_editor` → thinking then quiet, `action:show_me@step7` → the where card.

**Brand (Miyagi kit, `app/brand/BRAND.md`)**: amber only while off track (the off-track header and dot, the "yours" line, the "Yours" diff row, a failing check). Green only once passed (the success header, the re-run line on the success card, passing checks). Everything else is neutral: the tutorial line and "Expected" label are muted white, the re-run line is white while waiting, hint/explain/answer cards are muted. Apply fix is the white `CardButton` with a wrench icon (the old wand had sparkles). The success headline is `copy.passed` ("Good. Now the next one."). No gradient fills, glows, blue, purple or emoji. UI copy says "rerun" like the kit.

**What pass 1 does**
- **Off-track** (`data-card="offtrack"`): header line like the expanded pill ("Step 6 of 7 · ● Off track", the engine's `reason` on the right), title, body clamped to 2 lines, the loss curve (yours amber vs tutorial blue, live value at the end dot, a soft ring while points keep arriving), expected vs yours, the checks, Show me / Explain / (Hint) / Apply fix, footer with the citation and "Video waits until all pass". The dot pulses amber twice (core `StatusDot`). No red, no shaking.
- **Apply fix** sends `action {kind:"apply_fix"}` and collapses the card into **"Waiting for the fix"** (`data-card="fixing"`). Michael: the engine writes the file only when it knows the project folder, so the card never says "applied". It shows "Line N (of file) should read" + the expected line from `offtrack.diff`, then "Not in your file yet? Make the change, then re-run." Below: the re-run's curve (green "now" vs dashed amber "before fix") drawing live, and the checks re-running. A new `offtrack` reopens the full card.
- **Back on track** (`data-card="success"`, after `step.passed` on a step that went off-track): "Step 6 done", "Good. Now the next one.", the engine's summary, now-vs-before curve (or the checks when there's no live data), a draining hairline for the 4.8 s auto-hide.
- **Explain / Hint / Answer** (`data-card="explain|hint|answer"`): icon + label + "Step N of M", title, body clamped to 3 lines. A title that only repeats the label ("Hint") is dropped and the body becomes the headline. The video jump ("Watch 14:30 · why it fails") sets `core/lesson.video` and closes the card.
- **Back to off-track**: an explain card or a diagram opened over the off-track card returns to it when closed (Esc / ✕ / video jump), so the demo goes Off-track → Explain → Esc → Apply fix without hovering the pill.

**Live curve (`metric`), generic for any metric**
- `store.ts` keeps one series per metric name: the current run plus the run before it. A new run starts when `runId` changes or `step` goes backwards (the learner re-ran the script). Runs are thinned past 400 points.
- Which metric: the one named by `offtrack.curve.label` if it streams, else the most recently updated one. The caption is the metric's `name` (never a hardcoded label).
- Scale: one scale per chart, picked from all its lines: log10 only when every value is positive and they span ≥ 30× (a loss falling 1 → 1e-4); otherwise linear (accuracy rising 0.6 → 0.95, an error count falling to 0). Higher values plot higher.
- Tutorial reference (confirmed by Michael): `metric` events with `runId:"tutorial"`; "yours" = every other runId (e.g. `screen-<lesson>`). The mock streams the tutorial run at the start of step 6. Without live data, both lines come from the optional `offtrack.curve` arrays; the two sources are never mixed on one chart (their units may differ).
- "Before / after the fix" = runs that started before / after the latest `offtrack` (by event order, not time), so it also works when the learner fixes the code themself and re-runs.
- No PINN / β / loss strings in UI code: everything shown comes from the payloads (`offtrack.title/body/diff/reason/citation`, check labels, metric names). Checked with `cards-generic-accuracy.png` (a synthetic "val accuracy" off-track).

**Mock (`mock/scenarios/cards.json`)**: overrides `after_step5` → `step6` + `metrics_flat` (the tutorial's reference run as `runId:"tutorial"`, then the learner's run as `runId:"screen-pinn-convection"`: 26 points, epochs 0–7,000, flat at 0.25, ending just before the off-track fires), and adds `action:apply_fix@step6` → `fix` + `metrics_drop` (β curriculum 1→30, five saw-tooth stages ending at 6.08e-4, ends just before the loss check passes). Nothing else. If another feature's scenario (sorted after "cards") also overrides `after_step5`, the stream stops: keep that segment to this file.

**Not in the contract (mock-only extras, read leniently):** `offtrack.reason`, `offtrack.curve`, `step.passed.summary`. Ask Michael to add them, or the cards simply hide those bits.

**Left**: Adrian's spec; ⌘↵ for Apply fix (the overlay window isn't focused, so it needs a global shortcut: a core request if wanted); pause the success auto-hide on hover; the main-process link handler (core request 5).

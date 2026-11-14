# cards

**Status:** pass 1 done (Apple restyle + live curve), waiting for Adrian's review · **Priority:** P0 · **Port:** 5177 · **Branch:** `adrian/cards`

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
`npm run dev:web -- --port 5177` → `http://localhost:5177/?scenario=full`. Ctrl+K → type anything → Enter → Enter builds the lesson. Alt+E / Alt+H at step 4 or 6 → explain / hint card. About 30 s in, step 6 goes off-track (loss curve is live). Alt+E there → explain with a video jump; Esc returns to the off-track card. Apply fix → "Applying the fix" (the loss drops live) → "Back on track" → auto-hides. Esc dismisses; the HUD's Reset restarts.
`?scenario=offtrack` checks the fallback (no `metric` events: the curve comes from `offtrack.curve`, the success card shows the checks instead of a curve). `?scenario=cards` alone does nothing (it only overrides segments of the full run).
Screenshots: `agents/shots/cards-*.png` (offtrack, offtrack-stage, explain, hint, fixing-1/2, success, generic-accuracy).

## Adrian's spec
**First pass (no spec from Adrian yet):** build to the mockups in `docs/mockups/` (01–05 are the target look; 06–07 are earlier explorations to restyle in the Apple look) and the animation + placement spec in `docs/FRONTEND-HANDOFF.md`. Don't spend time on colors (Adrian's theme comes later). Adrian reviews after this pass and writes his spec here for pass 2.

## Core requests
1. **HMR on feature files** (small, not blocking): editing a file under `features/cards/` logs `Cannot access 'default' before initialization` from `core/registry.ts` (the eager `import.meta.glob`) and the update doesn't apply until a full reload. Suggest `if (import.meta.hot) import.meta.hot.accept(() => location.reload())` in `registry.ts`, or a note in CLAUDE.md to reload after edits.
2. **Island sizes / timing: no change needed.** Off-track is 460 wide × ~472 tall, "Applying the fix" ~313, "Back on track" ~251, explain/hint 420 wide. All fit under `maxCardWidth` 520.
3. *(FYI, nothing to do now)* Metrics live in `features/cards/store.ts` (`useCards(s => s.metrics)`, `useSeries()`), readable by other features (e.g. the overview card could show the live loss). If several features end up needing them, move them into `core/lesson.ts` later.

## Notes
**What pass 1 does**
- **Off-track** (`data-card="offtrack"`): header line like the expanded pill ("Step 6 of 7 · ● Off track", the engine's `reason` on the right), title, body clamped to 2 lines, the loss curve (yours amber vs tutorial blue, live value at the end dot, a soft ring while points keep arriving), expected vs yours, the checks, Show me / Explain / (Hint) / Apply fix, footer with the citation and "Video waits until all pass". The dot pulses amber twice (core `StatusDot`). No red, no shaking.
- **Apply fix** sends `action {kind:"apply_fix"}` and collapses the card into **"Applying the fix"** (`data-card="fixing"`): the applied line, the retrain's curve (green "now" vs dashed amber "before fix") drawing live, the checks re-running. A new `offtrack` reopens the full card.
- **Back on track** (`data-card="success"`, after `step.passed` on a step that went off-track): "Step 6 done", the engine's summary, now-vs-before curve (or the checks when there's no live data), a draining hairline for the 4.8 s auto-hide.
- **Explain / Hint / Answer** (`data-card="explain|hint|answer"`): icon + label + "Step N of M", title, body clamped to 3 lines. A title that only repeats the label ("Hint") is dropped and the body becomes the headline. The video jump ("Watch 14:30 · why it fails") sets `core/lesson.video` and closes the card.
- **Back to off-track**: an explain card or a diagram opened over the off-track card returns to it when closed (Esc / ✕ / video jump), so the demo goes Off-track → Explain → Esc → Apply fix without hovering the pill.

**Live curve (`metric`), generic for any metric**
- `store.ts` keeps one series per metric name: the current run plus the run before it. A new run starts when `runId` changes or `step` goes backwards (the learner re-ran the script). Runs are thinned past 400 points.
- Which metric: the one named by `offtrack.curve.label` if it streams, else the most recently updated one. The caption is the metric's `name` (never a hardcoded label).
- Scale: one scale per chart, picked from all its lines: log10 only when every value is positive and they span ≥ 30× (a loss falling 1 → 1e-4); otherwise linear (accuracy rising 0.6 → 0.95, an error count falling to 0). Higher values plot higher.
- Tutorial reference: `metric` with `runId:"tutorial"` (the mock streams it). Without live data, both lines come from the optional `offtrack.curve` arrays; the two sources are never mixed on one chart (their units may differ).
- "Before / after the fix" = runs that started before / after the latest `offtrack` (by event order, not time), so it also works when the learner fixes the code themself and re-runs.
- No PINN / β / loss strings in UI code: everything shown comes from the payloads (`offtrack.title/body/diff/reason/citation`, check labels, metric names). Checked with `cards-generic-accuracy.png` (a synthetic "val accuracy" off-track).

**Mock (`mock/scenarios/cards.json`)**: overrides `after_step5` → `step6` + `metrics_flat` (the tutorial's reference run as `runId:"tutorial"`, then 26 points, epochs 0–7,000, flat at 0.25, ending just before the off-track fires), and adds `action:apply_fix@step6` → `fix` + `metrics_drop` (β curriculum 1→30, five saw-tooth stages ending at 6.08e-4, ends just before the loss check passes). Nothing else. If another feature's scenario (sorted after "cards") also overrides `after_step5`, the stream stops: keep that segment to this file.

**Not in the contract (mock-only extras, read leniently):** `offtrack.reason`, `offtrack.curve`, `step.passed.summary`. Ask Michael to add them, or the cards simply hide those bits.

**Left for pass 2**: Adrian's spec and theme; ⌘↵ for Apply fix (the overlay window isn't focused, so it needs a global shortcut: a core request if wanted); pause the success auto-hide on hover; open the citation link (needs a main-process `shell.openExternal`).

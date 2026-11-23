# pill

**v2 (A2 `michael/app-pill-cards`, port 5187):** pass 1 done on core-v2 `4c9898d`, typecheck green, checked in the stage (headless Chromium at 1440x900, the Browser pane was not used). Draft PR #172 into `adrian/shell`. Not checked in Electron. No independent reviewer round yet (this session had no agent tool for it).

## v2 (A2)

Mockups: Les-Mini, the pill lines of Les-Working / Checking / NotYet / Passed, the Err-KernelInContext card footer, the Err-VSCodeSetup sheet. Files: `features/pill/**`, `features/cards/**`, `mock/scenarios/pill-cards.json`, this brief and `cards.md`.

**What works**
- **Compact pill (Les-Working):** "[bonsai] Normalize the pixels  2 of 6 ●". There's no "Step N ·" lead-in. The count is "N of M" at 12 px in the label color, and M is the outline count when the engine sends one, so it never jumps. The dot is 8 px.
- **Phase lines** (from core `useStepPhase`), with the same "2 of 6" and no dot:
  - Checking: "[spinner] Checking your work" while a `check_step` press is being thought about.
  - Not yet: "[white ring] Not yet" while off track or a check fails. The ring has no hue.
  - Passed: "[green check] Step 2 passed". The check draws in, and it's the only green on the pill.
- **The pass with the panel in play:** when the panel is shown or collapsed (core/dock `open || collapsed`), the pill says "Step N passed" for exactly as long as the panel holds Les-Passed (decision 7: the learner moves on with the panel's Next step). The engine sends `step.started` for the next step right after `step.passed`, so the pill doesn't wait for it: it reads A1's held pass (`usePanel` `heldPass`, `pill/store.ts useHeldPass`, found through `cards/panel.ts panelStore()`). Until A1 is on the branch, a pill-local stand-in holds the passed step the same way (until any press, or a step that isn't after it). Without the panel, the pill still runs ahead to the next step at 560 ms, as before. The mock now sends `step.started` at once after `step.passed`, like the engine. Checked on a throwaway local merge with `origin/michael/app-lesson-panel` (not pushed): typecheck green, and in the stage 1.2 s after the pass the engine is on step 3 while A1's panel shows Les-Passed ("Step done.", Next step) and the pill reads "Step 2 passed 2 of 6".
- **Mini (Les-Mini), island mode `mini`, priority 9:** shows while core/dock is `collapsed` and a step is running.
  - It's 380 wide (`dock.miniW`) and 34 tall, as decision 6 says.
  - It shows the bonsai or the phase glyph, then the title, then StepDots `bars` (passed green, this step white, the rest faint; past 10 steps it switches to one 96 px proportional track), then "2 of 6" and the dot.
  - The whole pill is a button that opens the panel. It asks through the core `panel` UI event first, then A1's `openPanel`, and with neither it just clears `collapsed`.
  - It steps aside while the pill's own notice line shows, and while A7's lines would show (engine disconnected or busy, lesson paused, a blocker), so "Reconnecting", "Lesson paused" or a kernel blocker is never hidden by it.
- **Panel-routed cards:** while the panel is shown (open and not collapsed), the island skips the off-track card (including its "Waiting for the fix" view), the step-passed success card and the hint card. A1's `isPanelRouted` decides once it's there (`features/cards/panel.ts`), for the hint card and the off-track: an off-track that carries a fix (diff, level 3, apply_fix) stays on the island, where "Do it for me" lives. The success card stays routed either way (A1 doesn't model it; Les-Passed draws it). Before A1, a fallback list (offtrack, success, hint) stands in.
  - The shots show the island side: in `pill-cards-notyet-panel` (after `check_step`: `lesson.offtrack` set) and `pill-cards-hint-panel` (after `pc_hint` fired; taken before the spend-on-route change, when `useCards.getState().card.kind === 'hint'` still held; now the routed hint is dropped from the store, which the shot can't tell apart) the panel is shown (`&pc=panel`), the only island layer is `compact`, and the pill reads "Not yet". The control `pill-cards-hint-nopanel` is the same hint state with no panel: the hint card is on the island.
  - What they don't show: the panel drawing the hint. This branch has no A1, so the stage's panel is the old drawer, which has no Les-NotYet or Les-Hint view; that's why the two panel shots look alike. The panel half of "no double render" needs the A1 + A2 shared scenario.
  - **What comes back on collapse (Mini):** only what the panel hasn't shown. A card or off-track routed away while the panel was shown is spent (`cards/store.ts consumeRouted`): the hint card is dropped from the store (also one the learner closed in the panel with its ✕), and the off-track is closed like its ✕ (a re-send of the same one stays closed). So collapsing never replays them out of the pill. What does grow from the pill in Mini: a card that arrives while collapsed, a new off-track (new step, higher level or new title), any card the panel doesn't draw (setup, where, explain, show me, a hint or off-track with a fix preview), the "applying the fix" view, and the off-track again on the Hint key (⌥H brings it back, as before). Success never shows in Mini: A8's step-passed card (priority 55) is Mini's.
  - Hovering Mini never peeks at the off-track card: the hover is how the learner reaches Mini's click to open the panel, most of all in Not yet.
  - With the panel shown, the Hint key no longer "brings the off-track card back". It asks for a hint as usual.
- **`card.waiting` (Err-KernelInContext):** a footer under a hairline, with the dashed gray watching ring (decision 5: never a spinner) and the engine's text at 12 px.
- **VS Code setup sheet (Err-VSCodeSetup):** a `setup` card turns into this sheet when the only things missing are the editor (kind `editor`) and/or its helper (tool or label matches companion / vscode-ext / miyagi-helper / "helper extension").
  - It's 352 wide and grows from the pill. It has the bonsai and "miyagi" with a ✕, then "One thing left before the lesson." and "The helper lets miyagi run and check your code."
  - Below that is a bordered list. A row that's present gets a ring with a white tick; a missing row gets a hollow white ring, with no green and no hue.
  - Only rows the button can act on: a download with a url (opens it), an `open` row, or one the engine installs (pip / brew / brew_cask, the setup card's Install rows). Only those send `install`. A missing editor or helper with `install.method "none"` keeps the regular setup card, which offers no Install for it, so "Installing helper" can't spin with no answer coming. The mock's helper row uses `brew_cask` as a stand-in until the contract has a method for it (Core request 4).
  - Then comes one white lg primary, "Install extension" (it changes to "Installing helper" with a spinner while busy, and "Try again" after an error), and the caption "No terminal. VS Code reloads once, your files stay open."
  - If VS Code itself is missing, the sheet reads "miyagi needs VS Code to teach this." / "Install it and miyagi picks up on its own." with a "Get VS Code" button (its download URL).
  - Every editor label goes through `copy.editorName`, in the sheet, the regular setup rows and the "Open <editor>" button.
- **Card kind `complete`** (core-v2 Core request 2): cards ignores it, because it's the complete feature's (A8).
- **Card targets** (core-v2 Core request 1): `cards/store.ts` publishes the open card's target rects as `reserveRect('card-targets', ...)`, so core can drop its `useCards` import from `islandPlace.ts`.

**How to see it:** `npm run dev:web -- --port 5187`, then open `http://localhost:5187/?scenario=pill-cards&size=1440x900&clean`.
- Stage params:
  - add `&pc=panel` to mark the panel as shown, or `&pc=mini` to collapse it to the Mini pill;
  - both are stand-ins until A1's `?scenario=lesson-panel&panel=...` exists, and A1's own dock state wins.
- The flow, in order:
  1. The setup sheet comes up. Install extension shows progress.
  2. Then "Ready to go" appears, and the lesson moves to step 2 of 6.
  3. Press `check_step` (the panel's Check my work; in the stage use the console, see below). The pill shows Checking, then Not yet.
  4. Press `hint` to get the hint card ("Hint 1 of 2").
  5. Press `check_step` again. The pill shows "Step 2 passed", and the engine starts step 3 at once. With `&pc=panel` or `&pc=mini` the pill keeps "Step 2 passed" (the panel's held pass) until the next press; with no panel it moves to "Build the model 3 of 6" at 560 ms.
  6. 1.5 s after step 3 starts, the "No kernel" card with its waiting footer appears, and it's withdrawn 6 s after that.
- Console: `(await import('/src/core/shortcuts.ts')).sendAction('check_step')`. Restart the dev server after the JSON changes; HMR leaves a stale module copy for console imports.

**Shots** (`agents/shots/`):
- `pill-cards-working`, `-checking`, `-notyet-pill`
- `-notyet-panel` and `-hint-panel` (panel shown, no card on the island; the hint one was taken with `card.kind === 'hint'`), `-hint-nopanel` (control: the same hint state with no panel, the hint card on the island)
- `-passed-panel` (re-shot in fix round 3 with `step.started` sent at once: 1.2 s after the pass the engine is on step 3 (`stepId pc-3`) and the pill still reads "Step 2 passed". The stage's panel is the old drawer, so it already shows step 3; with A1 it is Les-Passed.)
- `-mini`, `-mini-checking`, `-mini-passed` (re-shot the same way: Mini holds "Step 2 passed" with the engine on step 3), `-mini-step3`
- `-mini-collapse-hover` (fix round 3: panel shown through Not yet and the hint, both spent there; collapsed to Mini and hovered: only `mini` on the island, no replayed hint or off-track)
- `-kernel-waiting`
- `-setup-sheet`, `-setup-installing`

**Deviations (brand rules win over the mockups)**
- Pill height stays 34 (decision 6), not the mockups' 36. The lead glyph is in a 16 px box, not 18.
- The sheet's primary is 15 px / 600 (the core lg PrimaryButton), not 14 px.
- The sheet's "miyagi" label uses the system font. The mockup uses Google Sans Flex (CLAUDE.md: app text is the system font).
- The mockup's "Installing helper" and "Connected to VS Code" pill lines are not built. Installing shows on the sheet's own button. "Connected" would claim more than "the install finished".
- With the panel open, Mini is not used. The pill is the compact line.

## Core requests (A2)
1. **A1 (overview, drawer):** the overview hover card (priority 20) should stay off while core/dock is `open || collapsed`. Over Mini, hovering for 150 ms swaps the pill for the overview card, so the learner can't click Mini to open the panel.
2. **A1:** please export `isPanelRouted` and either `openPanel` from any drawer module, or `useDrawer.getState().openPanel`. A2 finds them at runtime. `isPanelRouted` always gets an object: `isPanelRouted(card)` for an engine card (every `card.kind`), and `isPanelRouted({ kind: 'offtrack', ...offtrack })` with the live `lesson.offtrack` for Not yet and its Waiting for the fix view. A2 never asks about `'success'` (step passed): it stays routed while the panel shows, because Les-Passed draws it. Answering the `panel` UI event with `true` (core/bus `PanelRequest 'open'`) is enough for the Mini click.
3. ~~**Priority table (README):** Mini at 9 sits above A7's net-offline/busy (6) and reconnecting/blocker (7) lines.~~ Fixed in A2: Mini now steps aside while the engine is disconnected or busy, or the lesson is paused or has a blocker (as it already did for the pill's notice line), and comes back once they clear. No README change needed.
4. **Contract:** `SetupItem.install.method` has no value for "a VS Code extension the engine installs through the code CLI". The sheet now sends `action install {text: tool}` only for pip / brew / brew_cask (what the engine's `setup_rows.INSTALL_METHODS` runs); a helper row with `"none"` keeps the regular setup card. The mock uses `"brew_cask"` as a stand-in. A method such as `"vscode_ext"` (and the engine installing it) would make the helper row real (contract PR, Michael); the sheet would then add it to the methods it sends `install` for.
6. **A1:** please re-export the panel store from `features/drawer/store.ts` (`export { usePanel } from './v2/panelStore'`, or a `heldPass()` getter plus its store). A2 reads `usePanel.getState().heldPass` read-only so the pill says "Step N passed" as long as Les-Passed is up. Until the re-export, `cards/panel.ts` finds it by the module's exact path (`import.meta.glob('../drawer/v2/panelStore.ts', { eager: true })`); with the re-export that line can go. (Alternative: core `useStepPhase` reports `'passed'` while a pass is held, and the pill needs neither.)
5. **Copy to confirm (Adrian):** "No terminal. VS Code reloads once, your files stay open." comes from the mockup. Check that E3's helper install really reloads VS Code once.

**Status:** pass 2 (functional: notice, thinking, offline, next part) done, waiting on Adrian's review · **Priority:** P0 · **Port:** 5174 · **Branch:** `adrian/pill`

Pass 2 (Michael's audit + live test), on core `be157ff`:
- ✅ **Notice line** (audit P1-2): when core's `notice` changes, the pill shows the bonsai and that one line for 5 s, then returns to its state. Errors are white too: nothing red, no extra icon, `role="alert"`. Engine `error`s and a failed build land there; a failed build no longer leaves its message behind (`shots/pill-notice.png`).
- ✅ **Thinking** (Michael P0-2): while `useThinking()`, the bonsai crossfades to the small core Spinner in the same 16px spot, so Alt+E / Alt+S / Alt+H never look dead (`shots/pill-thinking.png`).
- ✅ **Offline** (audit P1-3): after `connected` has been false for 2 s (no flash at startup or on a hiccup), idle reads "Offline" in gray with no key chip; mid-lesson the status dot goes hollow and gray (`shots/pill-states.png`, last two rows).
- ✅ **Next part** (long videos): after a pass with `pendingNext` (or while the lesson is still `complete: false`), the pill shows "Next part is still building" with the spinner where the ring was, instead of "Lesson complete"; when `lesson.updated` appends the next step, the pill moves to it (`shots/pill-next-part.png`).
- ✅ **Calm** (#33): nothing animates without a real state change. Checked: the building text stays the same element across the timer tick; the same notice again only holds longer; thinking and offline crossfade only when they flip.

Earlier passes:
- ✅ Matches mockup 01: measured spacing, type, ring and dot (`shots/pill-vs-mockup.png`).
- ✅ The step-pass moment is one gesture: check draws → ring advances → flash → text crossfades to the next step at 560ms (`shots/pill-step-pass.png`).
- ✅ Off-track: the dot eases to amber and pulses twice (scale only, no glow), once per episode (`shots/pill-offtrack.png`).
- ✅ Last step: "Lesson complete" with the ring closed in green.
- ✅ Miyagi brand: the bonsai is in color, `<MiyagiMark size={16} />` (Adrian, Sun Nov 15; it was a one-color white glyph from Sat 2 PM), "Ask Miyagi ⌥Space", white ring/spinner/line, green only at the pass, amber only off track, gray watching, tokens only.
- ✅ Mac notch: core places the pill just under the notch (`pillTop 40`).
- ❌ Not seen in Electron (Windows). Checked in headless Chrome at 1600×1000 (the Browser pane was hidden). Offline was driven by calling core's `setConnected(false)` in the page (the inline mock can't disconnect).

## Goal
The Dynamic-Island pill hugging the notch: idle ("Ask Miyagi ⌥Space"), building (spinner + the `lesson.building` message), and during a lesson "Step 4 · Define the residual" with a progress ring and status dot (gray watching · amber off-track · green passed). Owns **the step-pass moment**: the checkmark draws, the ring advances, the pill flashes green, the text crossfades to the next step, the video resumes 400ms later.

## Owns
- `app/src/renderer/src/features/pill/`

## Contract
- **In** (engine → app): `lesson.building` (incl. `failed`), `lesson.ready` (`complete`), `lesson.updated`, `step.started`, `check.updated`, `step.passed` (`pending`), `offtrack` (status only), `status thinking`, `error`, all read from `core/lesson` (`notice`, `useThinking()`, `pendingNext`, `complete`, `connected`)
- **Out** (app → engine): none (clicking idle opens the launcher via `bridge.emit("launcher:toggle")`)

## Plugs in as
islandModes: idle (0), building (1), compact (2), notice (5: above the pill states, below hover 20 and cards 40+). The morphing container itself is core (`core/Island.tsx`)

## Done when
- Matches mockup 01 (size, type, ring, dot)
- The step-pass sequence feels like one gesture
- Off-track: the dot turns amber and pulses twice, calm
- Mac: hugs the notch (y = 6)
- Pass 2: notices show for ~5 s then return; thinking never looks dead; offline is visible and gray; a pending pass says the next part is building

## Test
`npm run dev:web -- --port 5174` → `http://localhost:5174/?scenario=pill` (or `?scenario=full`). Add `&engine=ws://127.0.0.1:9` while a mock server holds 8787 (Core request 3).

## Adrian's spec
**First pass (no spec from Adrian yet):** build to the mockups in `docs/mockups/` (01–05 are the target look; 06–07 are earlier explorations to restyle in the Apple look) and the animation + placement spec in `docs/FRONTEND-HANDOFF.md`. Don't spend time on colors (Adrian's theme comes later). Adrian reviews after this pass and writes his spec here for pass 2.

## Core requests
_Status on core `be157ff`._

1. ✅ **Landing overshoot: fixed by core** (`justLanded` → `velocity: 0` on the first spring after a landing). Re-measured: 179 → ~298 at the landing → settles at 259, no balloon (was ~540).
2. **Notch shape (decide in pass 2). Placement is done: `pillTop 40` puts the pill under the notch.** Mockups 01 and 02 attach the island to the top edge, not as a free stadium. Measured in 01: flat top at y = 0, body 258×36, flaring to 278 at y = 0 (two small concave "ears"), bottom corners about 14pt round; mockup 02's card has the same attachment with about 24pt bottom corners. If adopted, in `core/Island.tsx` (`top`, `borderRadius`): `top` 0 on Mac, pill height 36, `borderRadius: isPill ? '0 0 14px 14px' : '0 0 24px 24px'`, plus the two inverse-corner ears.
3. **Stage: `?scenario=` is ignored when something listens on 8787. Still open on be157ff** (`bridge.ts:66`). A mock server on 8787 makes every agent's stage play that server's scenario instead of its own `?scenario=`. Suggest: when `?scenario=` is given explicitly, run inline. Workaround: append `&engine=ws://127.0.0.1:9`.
4. ✅ **Button fonts: fixed by core** (`@layer base`). The pill's idle button carries its own `text-[13px] font-medium` again (the inner-span workaround is gone).
5. ✅ **Mono tree: done by core differently.** `MiyagiMark` is now monochrome by default (`mono`, a white filter) and the tree is monochrome everywhere in the app, so "color when it opens" is dropped. The pill still uses its local `MonoMark` (same silhouette, `color.text` mask); switching it to `<MiyagiMark size={16} />` is a safe cleanup for the next pass (left out of pass 2 so every screenshot here matches the code).

## Notes
- **Ring = steps done / total** (computed in the pill), not core's `useProgress().fraction`, which also counts checks inside the step. With check-level progress the last check already fills the ring, so nothing moves visibly at the pass. Now the ring advances exactly one step on the spring at each pass.
- **The pill runs ahead of the engine after a pass.** At +560ms it shows the next step (`step.passed.nextStepId`, else the next entry in `lesson.steps`). In the mock, `step.started` for the next step arrives about 3.9s later. `step.started` then only confirms it (same key, no second crossfade). If the engine starts a different step, the pill crossfades to that one. If the engine is fast (`step.started` during the 560ms check), the check still finishes first (tested in `?scenario=pill`, step 2).
- **Dot color while watching:** settled by the brand: gray watching, amber off track, green passed (mockups 01 and 02 had it green).
- **Off-track pulse once per episode:** when `offtrack` arrives, the cards feature takes the island at once, so the pill isn't visible. The pulse plays when the pill comes back (Esc or ✕), not again on hover remounts.
- **Building:** keeps the last `lesson.building` message through `lesson.ready` (core clears it there), and the line fills to 100% on `lesson.ready`.
- **`island:size` traffic (FYI for core):** when the step text changes, the pill's text slot springs its width over about 300ms. The island re-measures on every frame, so `Island.tsx:63–65` emits `island:size` about 20 times per step change (IPC to main in Electron). This is harmless, but if it ever shows up, emit only when the size settles or while the launcher is closed.
- Generality rule: no PINN-specific UI strings in the pill ("Ask Miyagi", "Building your lesson", "Step N ·", "Lesson complete"). PINN only appears as mock data in `mock/scenarios/pill.json`.
- Reduced motion: `MotionConfig reducedMotion="user"` turns off the y offsets and the scale pulses. Crossfades, color changes and the width spring stay.
- **Mono tree:** `MonoMark` masks the small-cut SVG (`assets/brand/tree-small-dark.svg`) with `color.text`. It's 16px rather than 14, because at 16 the art is about 10.5×12, the optical size of mockup 01's icon, and it sits 15px from the edge and 11px before the text, as in the mockup (pad 13, gap 8). At 14 the tree read as a speck.
- **Slop check (Sat):** the pill has no gradients, glows, emoji, sparkles or purple. It uses one accent (white), the system font, and motion that only marks state changes. The tiny colored tree was the one thing that read as "generated"; it's now the white glyph. Building shows a spinner *and* a progress line on purpose: Adrian chose to keep both (the spinner shows it's alive during long steps, the line shows how far along it is).
- **Brand details:** the ring track is the accent at 22% opacity, like the Activity rings, so no new color. Building now mirrors compact: bonsai left, message, spinner where the ring will be. The check stroke is `color.island` on `color.green`. The ring closes in green only when the lesson is complete, which counts as passed.
- Own pieces in `features/pill/parts.tsx` (`PillRing`, `StatusMark`, `SwapText`, `BuildLine`), not the shared `core/ui/atoms` ones, because the pill sizes (16px ring, 7px dot) differ from the cards'.
- **Notice line:** its own island mode at priority 5, so it replaces whichever pill state is showing and the island springs to the line's width; a card the learner opened (40+) and the hover card (20) stay in front. The pill keeps the notice 5 s (`NOTICE_MS` in `store.ts`). A full reset (dev HUD) clears it; a lesson-scoped reset (reconnect, lesson ended) keeps it, because it may be the reason. Long lines truncate at 380px.
- **Offline:** `OFFLINE_GRACE_MS` 2 s. On reconnect, core resets the lesson (the engine snapshot refills it); the pill just follows.
- **Next part:** the pass moment runs as usual (check, ring, flash), then "Next part is still building" + spinner (the building pill's shape). The next step is looked up again when `lesson.updated` arrives, so the pill doesn't wait for `step.started`.
- **How to see it:** `http://localhost:5174/?scenario=pill&engine=ws://127.0.0.1:9` runs (about 55 s): idle → a build that fails (notice "Couldn't reach Gemini. Try again." for 5 s, back to idle) → a retry build (the timer tick doesn't animate) → step 1 with an error notice mid-step → step 2 with 2 s of thinking (spinner in place of the bonsai) → step 3 off-track (Esc to see the amber pulse) → step 4 passes with `pending` ("Next part is still building") → `lesson.updated` adds step 5 → "Lesson complete". Offline: in the console, `import('/src/core/lesson.ts').then(m => m.setConnected(false))`, wait 2 s. `?scenario=full&engine=ws://127.0.0.1:9`: Ctrl+K, type, Enter, Enter → step 4 passes at about +10s → step 6 goes off-track. HUD Reset restarts.

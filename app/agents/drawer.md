# drawer

**Status:** v2 lesson panel (BUILD-PLAN A1) built, typecheck green, stage-checked in headless Brave; draft PR #174 into `adrian/shell` · **Priority:** P0 · **Port:** 5186 (v2; passes 1-3 used 5184) · **Branch:** `michael/app-lesson-panel`

## v2: lesson feel (round 3, Nov 20, branch `michael/app-lesson-feel`, stage port 5511)
Persona QA fixes for the in-lesson experience. See it: `http://localhost:5511/?scenario=lesson-panel&os=mac&size=1440x900&clean` (`&panel=hint|notyet|checking|passed|mini`; `?scenario=errors&err=engine-offline` for step 3's long code and the demoted primary).

| What | Where | Notes |
|---|---|---|
| In / out | `v2/LessonPanel.tsx`, `store.ts` (`via`) | A lesson's first step slides the panel in from the right edge; collapse morphs it into the Mini pill, reopening grows it back out of the pill (`useDrawer.via`, AnimatePresence `custom`). Reduced motion: opacity only. |
| States animate | `v2/LessonPanel.tsx`, `v2/motion.ts` | The body's height springs to its content (`AutoHeight`, one spring). Screens are keyed per step and work/passed: Not yet / Hint / Passed rise 6 px (house spring, 180 ms fade, 120 ms exit), Working and Checking are one screen. "Next step" (and Enter) slides the passed screen out left and the next step in from the right; Back slides the other way. |
| Passed | `v2/states.tsx` `PassedCheck` | Green circle springs from 0.6, the ink tick draws in 80 ms later over 240 ms, then the line and Up next rise in. The line is core `copy.passed` ("Step done.", Michael's test 7 replaced "Good. Now the next one."). |
| Code box | `v2/StepBody.tsx` | Never clipped: soft-wraps with a hanging indent (indent as padding, continuation +2 columns, `<wbr>` after `( , . = :` so names don't split). Focusable (`tabIndex 0`, focus ring), a neutral Copy chip ("Copied"), a breathing skeleton while a code step's code hasn't arrived. Same wrapping in `MissingBlock`. |
| Hint | `v2/LessonPanel.tsx`, `v2/states.tsx` | The hint sits ABOVE the code (the code never disappears). "Another hint" + Hint keycap while n < of; Hint pressed again asks the engine for the next rung; a new rung rises in keyed on n. Mock: `lesson-panel.json` answers the second press with 2 of 2 (`step_lp_hint1` state segment). |
| Checking | `v2/LessonPanel.tsx`, `v2/states.tsx` | A fixed 16 px slot under the primary holds the caption, so nothing below moves; the "then" line stays. `plainDetail`: "Reading `x` in your kernel" reads "Looking at `x`". |
| Help tiles | `v2/Help.tsx` | Own tile (label over an 18 px keycap slot; the spinner takes the slot, no jump; Watch shows its play glyph there). Five tiles wrap to two rows (3 over 2) so "Show me" / "Diagram" never truncate. Busy from the press itself (any path, `usePressed`), `notify('No answer yet. Try again.')` after 8 s with no answer and no thinking. Pressed: Hint while the hint shows, Explain while its card is open, Diagram while the flyout is out. Hover dims, press dips. |
| Chrome | `v2/Header.tsx`, `v2/KeysRow.tsx`, `v2/ui.tsx` `Tip` | Tooltips with keycaps ("Collapse to the pill  Esc", "Previous step  ⌃⌥←"). Back is labeled "Back ⌃⌥←". Every key item has hover and press feedback. |
| Keyboard | `v2/LessonPanel.tsx` `useEnter` | Enter presses the primary (Check my work / Check again / Next step) unless focus is in a field or on a button, or the launcher is open. No ↵ keycap yet (Core request 7). |
| One primary | `v2/LessonPanel.tsx` | While a blocking island card is up (`err-*`, `onboarding-recovery`), the panel's primary renders as `QuietButton` so the card's action is the only white button. |
| Esc | `store.ts` | An app window open in the stage (`window:stage`: account, library, progress, onboarding) takes Esc; the panel stays. |
| Pill | `pill/index.tsx` | While the panel is open the pill shows only the status ("Watching" + dot, or the phase line without the count). Mini: hover tint, a chevron that brightens, press dip, title "Open the lesson panel", and on the very first collapse "Click to reopen" in the title's place for 2.6 s. |
| Hover card | `overview/clear.ts`, `overview/index.tsx` | Never opens over Mini (it swallowed the click). No "Video waits" in a text lesson; passed segments green. |
| Copy | `errors/lines.tsx`, `errors/cards.tsx` | "Reconnecting… (try 2)", "miyagi is busy. Trying again in 17s", "miyagi stopped responding." |

Shots: `/Users/tripi/sand hacks/miyagi-v2/screens/round3/lesson-*.jpg`.

**Not done here (other lanes):** the launcher's ↑/↓/↵ roving selection and two-step Esc (features/launcher); a Watch row in Settings > Shortcuts (features/settings); docking Explain under the panel's step intro (features/cards, left as the island card for now; its tile now shows pressed).

## v2: lesson panel (A1, Nov 20)
Mockups: Les-Anatomy, Les-Working, Les-Checking, Les-NotYet, Les-Hint, Les-Passed. In a "Just teach me" lesson (`lesson.mode "lesson"`) the drawer is now the docked lesson panel; a video lesson keeps the drawer below (passes 1-3) unchanged. `geometry.ts` `LESSON_PANEL_V2 = false` is a one-line rollback.

### What landed
| Piece | File | Notes |
|---|---|---|
| Panel | `v2/LessonPanel.tsx` | core `GlassCard` surface `panel`, 360 wide at core/dock `panelRect` (x 1064, y 52 at 1440x900), hugs its content up to the dock's height, then the middle scrolls (header and keys stay). Grows out of the island's box (`useIslandBox`) and collapses back into it (the one spring; opacity only with reduced motion). While shown it calls `setDock({open, rect})` with its real height (screen points), so `panel.state` goes out when the engine lists it and the island's cards step around it. |
| View | `v2/view.ts` | `pickView` (pure): passed > checking > notyet > hint > working. `usePanelModel` builds what each state shows. |
| State | `v2/panelStore.ts` | the hint card, the latest judge "Not yet" card and when the latest diagnosis came (card, offtrack, failed check), and the held pass. A hint asked for after a "Not yet" shows the hint; a newer diagnosis shows "Not yet" again. step.passed (not skipped, not already) holds Les-Passed although the engine starts the next step at once (decision 7) until "Next step", an action press, or a pass/fail on the next step. |
| Header | `v2/Header.tsx` | tree, `copy.name`, collapse chevron ("Collapse to the pill"), lesson title, core `StepDots` (current pill white, green once passed), "Step N of M". |
| Step | `v2/StepBody.tsx` | title 20/600, instruction 14 at .78, `where` caption ("Type this" / "Run this" when the engine sends none), the code in full (mono 13/20, scrolls sideways, never truncated), `then` with the play mark. `MissingBlock` for Les-NotYet (`card.missingLines`, `card.fixCaption`). |
| States | `v2/states.tsx` | NotYetBox (white ring, "Not yet", no hue), HintBox (pink Hint chip, "1 of 2" from `hintStep`, ✕), PassedBody (core passed glyph 48, `copy.passed`, `step.passed.summary`, Up next from the next step's title and `what`), CheckingCaption (`status.detail`). Backticks render as mono (React text only). |
| Help | `v2/Help.tsx` | core `OptionTile`s: Explain, Hint, Show me, Diagram via `triggerShortcut`, Watch opens the lesson video at the step's start in the browser (hidden when the step has no clip). Open hint = Hint tile pressed. Spinner on the pressed tile while thinking. |
| Keys | `v2/KeysRow.tsx` | Esc hide, launcher key + "ask miyagi anything" ("ask miyagi" beside a long key such as ⌥Space), Back and Voice as icon buttons on the right (keys in their tooltips), all from `bridge.platform.keys`. |
| Routing | `v2/route.ts`, re-exported by `store.ts` | `isPanelRouted(card \| {kind:'offtrack', ...})` and `usePanelRouted`: true for a hint card, a judge not_done card or a card with `missingLines` for the current step, and for an offtrack without a fix (no diff, not level 3, no apply_fix), only while the panel is open in a lesson-mode lesson. Cards with a diff or output stay on the island. |
| Store | `store.ts` | `openPanel()`, `collapsePanel()` (also on the store: `useDrawer.getState().openPanel()`), `panel` UI event (open / collapse / toggle, claimed), Esc rule below. `useDrawer.open` keeps meaning "the drawer/panel shows", so every reader still works. |
| Layer | `index.tsx` | `PanelLayer` (lesson mode) vs `LegacyLayer` (video lessons, unchanged). The panel shows from the first step.started. It never yields, flips or tucks (the engine fits VS Code beside it); the Diagram flyout still slides out of its inner edge. `runTuck.ts` never tucks with the v2 panel. |
| Shortcut bar | `shortcut-bar/ShortcutBar.tsx` | hidden while `useDock.open`; back when the panel collapses. |
| Overview | `overview/clear.ts` | the hover card never opens while the panel is docked. |
| Stage | `v2/stage.ts`, `mock/scenarios/lesson-panel.json` | `?panel=` asks the inline mock for the scenario's own `stage.panel:<state>` segment once the first step starts (checking is held). |

**Esc** collapses the panel only when nothing else is open: a card, the off-track card, "Back on track", a diagram, the completion panel, "Before you start", the launcher, or the panel's hint (Esc closes the hint first). All `dismiss` handlers run on the same Esc, so a surface that another handler closed during this Esc still counts (`closedNow`, cleared on the next microtask). Electron: the overlay doesn't take focus, so Esc reaches it only where it did before; the panel's "Esc hide" and chevron work everywhere.

**Collapse:** `collapsePanel()` sets `useDock {open:false, collapsed:true}` for A2's Mini pill. Until A2 lands, the labeled "Steps" handle on the right edge stays as the way back (`STEPS_HANDLE_WHEN_COLLAPSED` in `index.tsx`: set it false when A2 merges).

### See it
`npm run dev:web -- --port 5186`, then `http://localhost:5186/?scenario=lesson-panel&panel=working|checking|notyet|hint|passed|mini&os=mac&size=1440x900&clean` (`&os=win` for the Windows keys). Without `panel=` the scenario plays for real: Check my work (1.8 s Checking) → Not yet with the missing line → Hint 1 of 2 → Check again → Les-Passed → Next step → step 3 → Check → step 4. Esc closes the hint, then collapses; the Steps handle reopens.
Shots (headless Brave over CDP, 1440x900): `agents/shots/lesson-panel-{working,checking,notyet,hint,passed,mini,win}.png`. Scripted flow checked: working → checking → notyet → hint → Esc (hint closed, back to notyet) → Esc (collapsed, shortcut bar back) → handle (open, bar hidden) → Check again → passed → Next step → "Build the model". `?scenario=drawer` (a lesson-mode lesson with no video) shows the panel with four help tiles; `?scenario=full` loads with no errors.

### Deviations (brand rules and core limits)
- Help row gap 6 (mockup 8) and core OptionTile's 4 px side padding removed locally (`[&_button[data-option]]:!px-0`): "Show me" truncated at 12/600 in a 58 px tile. Core request 2.
- Body text at white .78 uses `fill.keycapText` (same value; no text token). Core request 1.
- Mockup keycaps (⌥E, ⌘K) replaced by `bridge.platform.keys` (⌃⌥E, ⌥Space on a Mac); Watch has no key (decision 3). Pastels are BRAND.md's (sky #C5E4F9 etc.), not the mockup's #BFE3F5.
- Les-Passed headline is `copy.passed` ("Step done.") per decision 8, not the mockup's literal.
- Back and Voice are 28 px icon buttons with their keys in tooltips: four keycaps plus labels don't fit 320 px.
- No Skip step / End lesson in the panel (not in the mockups) and the shortcut bar hides while it's open: they are reachable when the panel is collapsed. Flag for Adrian.
- Pre-A2 the island still draws the judge "Not yet" and hint cards too (visible in the notyet / hint shots); A2 drops them with `isPanelRouted`.
- The old lesson-mode drawer's overview, "Before you start", plan list, sources, concept chips and the code Copy button are not in the v2 panel (not in the mockups).
- Not verified: Electron (`npm run dev`), the engine's real `where`/`then`/`hintStep`/`missingLines` (E3), `panel.state` on a real engine (E2).

### Notes for A2 (pill-cards)
- `import { isPanelRouted, usePanelRouted } from '../drawer/v2/route'` (it imports only core and `v2/panelStore`). Skip a card (or the offtrack card) when `usePanelRouted(card)` / `usePanelRouted({ kind: 'offtrack', ...offtrack })` is true. Reading it never imports the panel UI.
- **Never import `'../drawer/store'` from `cards/store.ts`**: drawer/store imports `../cards/store` and subscribes to `useCards` at module top level, so the cycle leaves `useCards` uninitialized (TDZ) and throws a ReferenceError at load. `'../drawer/store'` is safe only from `cards/index.tsx` or pill code.
- Mini pill: show while `useDock(s => s.collapsed)`; click = `emitUi('panel', 'open')` (core's `panel` UI event; no import of drawer code needed). Then flip `STEPS_HANDLE_WHEN_COLLAPSED` off in `drawer/index.tsx`.
- Esc: drawer/store's `othersOpen` counts only what the learner can see. A card the panel renders (`isPanelRouted`) or the routed offtrack is not "open", and the panel's hint counts only while it is the view on screen (`hintShown()` in `v2/panelStore`, the same rule as view.ts: not under Checking, Passed or a newer Not yet). So the first Esc collapses the panel even if cards/store's `closeTop` clears a hidden card on that Esc.

### Pass 3 (Sat Nov 14, night): "Just teach me" shows what to type
Michael tried a "Just teach me" lesson: the instructions weren't clear and didn't show what to type. The drawer now reads, top to bottom:
- **What we're building**: `lesson.ready.lesson.overview`, one paragraph.
- **Before you start** (collapsed, "3 ideas"): `lesson.primer[]`, each concept's title, body and small example in mono.
- **The plan**: one line per step from `steps[].what` (the title when missing; the title shows on hover). Without a time column the lines wrap to two lines instead of being cut off. Current = highlighted row, passed = the green tick as before, **skipped = a ring with a dash, never green** (`useLesson().skipped`, contract `step.passed.skipped`).
- **The current step**: a neutral Type / Run / Read badge (`kind` code / run / read) + the one-line `instructions`; the **full `code`** (or the exact command) in mono with **Copy**, never truncated (long lines scroll sideways so what you see is what you type); **Why:** + `why`; concept chips (`concepts`, matched to primer items by id or title) that open the primer item in place. Falls back to the spotlight snippet (`overview/snippet`) when `code` is missing. A video lesson without these fields looks exactly as before.
- **Checks** wrap long labels instead of truncating (all lessons).
- Lesson mode is 384 wide (no player to line up with; code needs the room). Video lessons stay 340.
- The header says "Claude wrote this lesson" in lesson mode (core `builtByLabel(builtBy, mode)`, #70). A hairline appears under the header once the list scrolls.
- **Copy**: the overlay is `focusable: false`, and Chromium refuses `navigator.clipboard` and `execCommand('copy')` in an unfocused document (checked in headless Brave). So Electron copies in main: `src/main/features/drawer.ts` handles `drawer:copy` with Electron's `clipboard`. The stage uses a web handler (`navigator.clipboard`). **Electron unverified** (typechecked only).

Data: overview, primer and the plan lines come from core/lesson (`lesson.overview`, `lesson.primer`, `steps[].kind/what`, synced in #70). `plan.ts` keeps only what core doesn't: step.started's kind, why, concepts and code, plus Copy. New files: `plan.ts`, `Teach.tsx` (overview, primer, step detail, code block), `src/main/features/drawer.ts`.

**See it:** `npm run dev:web -- --port 5184` → `http://localhost:5184/?scenario=drawer`: a CLI calculator lesson (lesson mode, so the drawer opens itself) runs ~9 s: step 1 Type passes, step 2 Run (`python3 calculator.py`) passes, step 3 Type stays current with a long check label. Click a concept chip or "Before you start". The old GPT video demo: Ctrl+K, paste a YouTube link, Enter (`learn_url@step_calc`). Shots: `agents/shots/drawer-plan-*.png` (run, code, concept, primer, light, video-unchanged), taken in headless Brave at 2×.

### Pass 2 (Sat Nov 14, evening): light / dark
**Works** (headless Chrome over CDP, 30/30 checks in dark AND in light):
- Everything on `theme.glass`: panel, text, rows, dividers, the ✕, the scrollbar and the edge tab flip with Settings → Appearance (`setPrefs({appearance:'light'})`). No `backdrop-filter`.
- Without blur the .9 glass let the player's video and text show through, so the panel draws an inset layer of the same `glass.bg` under its content (~99% opaque, tokens only; the ghost went from 25 to 2 grey levels). See Core request 6.
- Done steps and passed checks are core `GlassCheck` (`glass.pass`: bright green on dark, `#1C8A3C` on light); spinners are core `GlassSpinner` (`core/ui/glass`). Current = ring + dot in `glass.text`, locked = faint ring. Failed check = `glass.offTrack` (apricot). A step that completes while the drawer is open draws its tick in; ticks already there when it opens don't. Colors go through `style`, never SVG attributes. Only the empty ring and the check-list wrapper are local (Core request 5).
- Kind tiles: dark keeps the 16% pastel wash + pastel glyph. Light: the wash and glyph vanish on paper, so the tile is the pastel itself with an ink glyph, like the shortcut bar's option tiles. One line in `KindTile` to revert.
- Height hugs the content (a 3-step lesson: 635 px), up to the old full column (840 px), then the list scrolls. The spotlight check uses the real height: open = the panel, closed = only the tab.
- core `clock()` (hours) and `alpha()` replace the local copies; core's window-open handler replaces `drawer:open-url` (main file removed).
- Lesson mode (from shell): "Step N of M" label, the current step's instructions, opens itself for a "Just teach me" lesson.

**See it:** `http://localhost:5184/?scenario=drawer&drawer=open`, then in the console `(await import('/src/core/prefs.ts')).setPrefs({appearance:'light'})` (`'system'` to go back). Shots: `agents/shots/drawer-*.png` (dark) and `drawer-light-*.png`.

**Left:** Electron unverified (Windows SAC). The tab-on-the-player's-border question from pass 1 is still open.

### Pass 1 (Sat Nov 14)
**Works** (verified in headless Chrome over CDP, 22/22 checks; the Browser pane was hidden, so motion froze there):
- Tab: 4×40 at `fill.track`, 6px from the right edge, vertically centered on the work area, inside a 22×64 `data-hit` box; hover stretches the bar (transform only). Hidden while the drawer is open.
- Drawer: `color.glass` panel, `radius.card`, 340 wide, same top and bottom as the player's dock (ends above the shortcut bar). Slides in from the edge on the spring, out on `springOut`. Close: ✕, Esc (`dismiss`), new lesson, `reset`.
- Steps: done = white check, current = white ring with a dot + its live checks (core `CheckList`: green only on passed checks, amber only on a failed one), locked = empty ring in `color.faint`. Start time column (`h:mm:ss` past an hour). Clicking a done/current row → `seekVideo(step.video.start)`; locked rows don't respond.
- Part by part: appended steps fade in (40ms stagger); rows already on screen keep their exact opacity/transform and their title x (sampled every frame across both `lesson.updated`). Last quiet row "More steps coming" + "Part 3 of 3" from `parts`; "Next part is still building" with a spinner while `pendingNext`; gone when `complete`.
- Sources: one row each, video = thumbnail, others = `kindTone` tile (16% wash + glyph). Click → `window.open` (core's handler sends http(s) to the default browser); new tab in the stage.
- Spotlight: while the spotlight hole touches the drawer's column, the drawer and the tab slide away; if the learner had it open it slides back 700ms after the target moves on. The spotlight's caption already avoids the drawer (it reads `data-hit`).

**See it:** `http://localhost:5184/?scenario=drawer` → click the bar on the right edge. `&drawer=open` starts it open (stage only) to watch the whole ~30 s run: 3 steps, the learner catches up with the build, part 2 (steps 4–7), part 3 (8–11), then a spotlight on the left (drawer stays) and one on the right (drawer yields, comes back). Alt+H replays the spotlight. `?scenario=offtrack&drawer=open` shows a complete lesson. Shots: `agents/shots/drawer-*.png`.

**Left / for Adrian:**
- The bar sits on the player's right border (the player docks 8px in, the bar is 6px in), so it reads like a grabber on the player's edge. Keep, or move it to 2px from the edge (inside the gutter)?
- The player's chapter list shows done chapters with the green tick; the drawer uses a white check per this brief. Pick one for both (see Core request 1). *Pass 2: green (`glass.pass`), per the integrator.*
- Electron unverified (Windows SAC): click-through over the tab, Esc reaching the overlay.

## Goal
A slim tab on the right edge (vertically centered, 6px from the edge). Click → a lesson drawer slides in: every step as done / current / locked, the current step's checks, and the lesson's sources. With long videos (Michael: Karpathy's 2-hour GPT video) the steps arrive part by part, so the drawer is where you see what's coming.

## Owns
- `app/src/renderer/src/features/drawer/`
- `app/mock/scenarios/drawer.json` (a long lesson: `lesson.ready` with `complete:false`, then two `lesson.updated`)

## Contract (read from `core/lesson`)
- `lesson` (title, sources, `builtBy` → `builtByLabel()`), `steps`, `passed`, `stepId`, `checks`, `complete`, `parts`, `pendingNext`
- **`lesson.updated`** replaces `steps` (ids stable, new steps appended): new rows fade in; existing rows must not re-animate.
- `complete === false` → a last quiet row "More steps coming" (with `parts` → "Part 2 of 5"); `pendingNext` → "Next part is still building".
- Sources: one row each with its kind tile (`theme.kindTone`: notebook/repo sky, paper pink, blog lilac; video = thumbnail). Click opens the URL (`window.open`; main denies new windows and opens https externally).
- Click a step row with `video` → `seekVideo(step.video.start)` (core). There is no "jump to step" command: ask under Core requests if you want one.
- **Out:** none.

## Adrian's spec (pass 1, from his feedback on the other features)
- Black glass panel (`color.glass`), white text, system font, `radius.card`. The tab: 4×40 white at `fill.track`, `data-hit`.
- States: done = check (core `CheckIcon`, white), current = white, locked = `color.faint`. Green only for the passed tick on the current step's checks (core `CheckList`). No amber unless off track.
- Labels only; step titles from the data. ≤12 words of chrome copy.
- Never covers the spotlight target: when a `spotlight` rect intersects the drawer, slide it closed.
- The one spring; transform/opacity only.

## Done when
- Steps, checks, sources; part-by-part updates without re-animating; never covers the spotlight

## Test
`npm run dev:web -- --port 5184` → `http://localhost:5184/?scenario=drawer`. Restart the dev server after adding the folder and the scenario.

## Core requests
**v2 (A1):**
- **1. A body text token** (`color.body` = white .78, Les-* instructions and Up next): the panel uses `fill.keycapText`, which has that value.
- **2. OptionTile side padding 0** (core/ui/HelpRow.tsx), as in the Les-* mockups: five tiles in a 360 panel leave "Show me" ~50 px and it truncates. Workaround: `[&_button[data-option]]:!px-0` on the panel's row (v2/Help.tsx).
- **3. OptionTile `pressed`** (Les-Hint: an ink ring inside, the pastel ring outside, `aria-pressed`): built as a wrapper in v2/Help.tsx.
- **4. Esc in Electron**: the overlay is `focusable: false`, so Esc never reaches it; if "Esc hide" should work while the editor has focus it needs a main-side shortcut while the panel is open (main/index.ts).
- **5. `step.passed.summary` and a "next step started" hint**: the panel holds Les-Passed locally because the engine starts the next step at once; if the engine (E3) waits for the learner (a `next` action), the hold can go.
- **6. A `watch` key** in `bridge.platform.keys` (main/platform.ts; Alt+V / ⌃⌥V is voice today, so pick a free one) and a Watch row in Settings > Shortcuts. Workaround: Watch's slot shows its play glyph.
- **7. A `confirm` key** (↵ / Enter) in `bridge.platform.keys`, so the panel's primary can show the keycap for its Enter binding. Workaround: Enter works, no keycap shown.
- **8. Dock clear of VS Code's tab and toolbar band** (core/dock `panelRect`, islandPlace): start the docked panel and centered cards below about y 96 on a full-screen editor, and add a full-screen VS Code backdrop to the lesson-panel stage so it can be checked. Persona QA: top 52 sits on the editor tab row.
- **9. Core `copy.passed`**: the lane brief asked for "Good. Now the next one." on Les-Passed; core says "Step done." (Michael, test 7). Kept core; change it there if the brand line should come back.
- **10. OptionTile**: v2/Help.tsx now draws its own tile (keycap slot, busy at press, pressed ring, two rows at five). Fold that into core `OptionTile` / `HelpRow` when convenient.
- **11. Esc in Electron app windows**: the stage fix (`window:stage`) covers the browser stage; in Electron each window has its own keys, so check there that Esc in the account window never reaches the overlay's `dismiss`.

**Earlier passes:**
1. **A shared step-state icon** (`StepIcon {status: 'done' | 'current' | 'locked'}` in `core/ui/atoms.tsx`, on glass tokens), used by the player's Chapters and the drawer, so both show a step the same way. *Workaround:* `StepIcon` / `Tick` / `Ring` in `Drawer.tsx`.
2. ~~`clock()` with hours~~ done in core.
3. ~~`setWindowOpenHandler` on every window~~ done in core; the drawer's main-process workaround is gone.
4. ~~`alpha(hex, a)` in `core/theme.ts`~~ done in core.
5. **A glass `CheckList`** (and a glass empty ring, CheckIcon's pending state) in `core/ui/glass`: `GlassCheck` and `GlassSpinner` landed (used now), the list and the ring didn't. *Workaround:* `GlassCheckList` + `Ring` in `Drawer.tsx`, built from the core glass atoms.
6. **An opaque glass background** (`glass.solid`, or `--glass-bg` closer to 1): with `backdrop-filter` gone, `.9`/`.92` lets whatever is under a panel show through (for the drawer, the player's moving video). *Workaround:* an inset `glass.bg` layer under the drawer's content (`boxShadow`), ~99% opaque.
7. ~~Sync the "Just teach me" contract fields into the app~~ done in #70; the drawer uses the shared `StepKind` / `PrimerItem` / `StepSummary` and core's `lesson`, the local types are gone.
8. ~~`builtByLabel` for lesson mode~~ done in #70 ("Claude wrote this lesson"); the drawer passes `lesson.mode`.

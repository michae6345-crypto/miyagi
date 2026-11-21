# progress (A8)

**Status:** pass 1 done: step-passed card, completion restyle, review reminder, Progress window; typecheck green; draft PR #173 into `adrian/shell` · **Priority:** P1 · **Port:** 5193 · **Branch:** `michael/app-progress`

## Goal
The learner sees how far they got: a small step-passed card out of the island while the lesson panel is collapsed
(Mini), the lesson-complete card (408 wide, every number from the engine), a spaced-review reminder (fixture data until
a scheduler exists) and the Progress app window (skills, this week, review), with honest empty states.

## Owns
- `app/src/renderer/src/features/progress/**` (index, store, types, StepPassed, ReviewReminder, Window, web)
- `app/src/renderer/src/features/complete/**` (index, store, Panel, types, net; Network.tsx removed)
- `app/src/main/features/progress.ts`
- `app/mock/scenarios/progress.json`, `app/mock/scenarios/complete.json`
- `app/agents/progress.md`, `app/agents/shots/progress-*.png`

## Mockups
Prog-Step-Passed, Prog-Completion, Prog-Review-Reminder, Prog-Progress-Window.

## What landed
| Surface | Plugs in as | Notes |
|---|---|---|
| Step passed | island mode `step-passed`, priority 55, 368 wide | Snapshot on `step.passed` (not skipped, not already): "Step N of M", `copy.passed`, `step.passed.summary` (else "<title> passed"), a stable bar track (passed green, skipped faint, next brighter), Next title, one primary Continue. Active only while `useDock.collapsed` and not `useDock.open` (decision 7), or a video lesson once `SHOW_ON_VIDEO` (index.tsx, false) is flipped. Never on the last step (the completion takes over). Closes after 4.5 s, on Continue / Esc, when the panel opens (and stays closed when it collapses again), on a new lesson or reset. |
| Completion | island mode `complete`, priority 64, 408 wide (clamped to the overlay) | Header (bonsai, wordmark, dismiss keycap, close). "Lesson complete" under a green check only when nothing was skipped; otherwise "Lesson finished" under the skipped ring. Counts from `card.result` when they add up (passed + skipped <= total), else from this lesson's own step events; "5 of 6 passed, 1 skipped". Result box: the engine's card title and body plus the learner's own printed metric (newest metric series) or the trained network's loss. Steps list with status glyphs (scrolls past 8). Next up from `skillMap.next[0]`. Done (quiet) + Start next lesson (the one primary); with no next lesson, Done is the primary. |
| Review reminder | island mode `review`, priority 42, 432 wide | The overlay asks `progress.get` once per app session, 1.5 s after `engine.hello`, only while no lesson runs, only when the engine lists it (stage: only with `?review`). Only that answer opens the reminder (the window's own request never does). Start review disabled unless the engine lists `review.start`; Later (Esc) closes it. A lesson starting closes it. |
| Progress window | app window `progress` (kind 'app', 1100x760), `openProgress()` | Skills groups ("N of M mastered", each skill's state: Mastered green, Practicing white 55%, Not started bare), the last completed lesson, This week (days active; minutes and streak only when non-null), Review queue with Start review (disabled unless `review.start`). Loading line, then empty states for `progress` null / `week` null / `review` null. Asks on every open and again when capabilities arrive. |
| Main | `main/features/progress.ts` | `progress:caps` (EngineLink.can for progress.get / review.start / library.start) and `progress:last` (the last `progress` payload, cleared on disconnect), because an app window opened mid-lesson never saw engine.hello. No network, no URLs, no files. |

Start next lesson: enabled with a cached next lesson (`next.id` + `library.start` listed: `library.start {id}`, zero model calls), or outside the browser stage with the goal (`learn {query: goal, mode: 'lesson'}`, the pre-v2 behaviour). Otherwise disabled. In the stage it is enabled only because complete.json's next lesson carries an id and the mock lists `library.start`.

## Deviations from the mockups (and why)
- Island cards are black (`color.island`), not the mockups' rgba(28,28,30,.96) glass: every island card stays black and grows from the pill.
- The completion card is island-born, centered under the notch (islandPlace keeps it off the docked panel), not docked at the right as drawn.
- Passed line is `copy.passed` ("Step done.") per decision 8, not "Good. Now the next one.".
- Completion has no "Test accuracy / Checked in cell 6" line: the contract has no such fields. The result box shows the engine's card title / body and the learner's own printed number instead. The old skill chips and network picture are gone (not in the mockup; the window shows skills).
- Skill bars are full width in their state's tone: the contract counts states, not fractions, so no partial bars.
- Week bars are one height (contract `days: boolean[]`, Monday first); today is highlighted only when active.
- Review chips are "Due today" and "N due": no minutes or last-seen data exists.
- Track names use the UI font (they are data, not always package names).
- Progress window review copy says "your own work" (not only notebooks).

## Test
`npm run typecheck` green. Stage `npm run dev:web -- --port 5193`:
- `?scenario=progress&hold&clean&size=1440x900` step card held at "Step 3 of 6" (hold = stage only: no timer, shown as if Mini). Without `hold` no card shows (panel not collapsed); with `setDock({collapsed:true})` it shows and closes after 4.5 s; `setDock({open:true})` closes it at once (all checked in the page).
- `?scenario=progress&window=progress&clean&size=1440x900` window with the fixture; `?scenario=core-v2&window=progress` partial (week / review null); `?scenario=full&window=progress` all empty states.
- `?scenario=full&review&clean&size=1440x900` review reminder (Start review disabled).
- `?scenario=complete&clean&size=1440x900` completion (6 of 6, Start next lesson enabled through library.start). With `hold` the last step shows no step card.
- Brand lint over the package: no hex, no typed keycaps, no Cursor, no em dashes, no innerHTML, no console.log, no openExternal.
Shots: `progress-step-passed.png`, `progress-completion.png`, `progress-completion-skipped.png` (a skipped step dispatched in the page: "Lesson finished", "5 of 6 passed, 1 skipped", Done primary), `progress-review-reminder.png`, `progress-window.png`, `progress-window-partial.png`, `progress-window-empty.png`.
Not verified: Electron (`npm run dev`), the window's `data-drag` title bar, `progress:caps` against a live engine (cost freeze; no live engine), the independent reviewer round (no reviewer agent available in this run).

## Core requests
1. **bridge.ts** (integrator): the inline mock's built-in `engine.hello` fires inside `createWebBridge`, before main.tsx subscribes, so the stage never sees it (`?scenario=full` has no capabilities). Replay `log` on `ready()` or start the inline mock after the first `onEvent`. Workaround: progress.json and complete.json send their own hello.
2. **main/engine.ts** (integrator): the replay log keeps only search rows after `lesson.ready`, so it drops `engine.hello`; an app window opened mid-lesson can't use `canSend()`. Keep the last hello in the log. Workaround: `progress:caps` in main/features/progress.ts.
3. **Contract** (Michael): `review.start {label}` (capability, Python mirror, main's outgoing allowlist and `V2_COMMANDS`). Until then Start review stays disabled; `startReview` sends it only when listed.
4. **Contract** (Michael): `SkillNext.id?` (a cached library lesson, `^[A-Za-z0-9_-]{1,64}$`) and `SkillNext.estMinutes?`, so Start next lesson can use `library.start` (zero model calls) and show "About N min". The app already reads both when present.
5. **agents/README.md** island table (integrator): add `42 review reminder (progress)`; 55 and 64 are as listed.
6. **core/ui/Mark.tsx** (integrator): `MiyagiWordmark` sets only the `height` attribute, which Tailwind's preflight (`img {height:auto}`) overrides, so it renders at the SVG's natural size. Set `style.height`. Workaround: `className="h-[Npx] w-auto"`.
7. **A1** (lesson panel): call `setDock({ collapsed: true })` when collapsing to Mini and `{ collapsed: false }` when reopening; the step card reads `useDock.collapsed` / `open`.
8. **E3** (engine): send `step.passed.summary`, the `card {kind:"complete", result, skillMap}` on the last step, and `skillMap.next[].id` when the next lesson is cached.
9. **Entry point**: nothing opens the Progress window yet. A5 (launcher) or A9 (account menu) should add `openProgress()` from core/surfaces.
10. **A2** (cards): skip `kind "complete"` (CardKindV2) in the cards store so its priority 50 card doesn't linger under or after the completion card (W0 core request 2).

## Notes
- `SHOW_ON_VIDEO` lives in `features/progress/index.tsx` (false).
- `STAGE_HOLD` (`?hold`) and the `?review` launch check are browser-stage only (`engineMode() === 'inline'`).

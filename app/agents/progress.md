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
`progress-step-passed.png` is a `?hold` stage artifact: the step card shows next to the open lesson panel only because the stage-only `hold` forces it and the old drawer does not set `useDock.open`. In the app the card never shows while the panel is open (decision 7).
Fix round 1: the completion's green check and "Lesson complete" now need counts with no skip and every step passed (`passed >= total`); missed passes or no counts show "Lesson finished" under the plain ring. This week and Review show no empty-state copy while the window is still loading.
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

## Round 3 (surfaces lane, michael/app-surfaces-feel)

**Landed**
- `mock/scenarios/progress.json` now answers `progress.get` with the dashboard fixture's full shape (`stageAnchor`, per-day `activity`, per-skill `reps`, `inProgress`, `next`, `settings`) and a review list of mastered skills only (`due: 2`, `when` filled for the reminder card). The stage window no longer shows "6 of 13 mastered" beside "Not tracked yet". **This is the stage only:** `activity`, `stageAnchor` and per-skill `reps` are not in `shared/contracts/events.ts` (only `week` is, and the real engine sends `week: null`), so the real app still shows the persona blocker.
- Completion card (features/complete): no confetti; the hero check springs in, then the result, the steps (ticking in one by one), "Skills in <track>" with the mastered skills as chips ("and N more") and Next up settle in 40 ms apart. Opacity only with reduced motion.

**Stage:** `?scenario=progress&window=progress&clean&size=1440x900`, `?scenario=complete&clean&size=1440x900` (press Next step). Shots: `surfaces-progress-window.jpg`, `surfaces-complete.jpg` in `/Users/tripi/sand hacks/miyagi-v2/screens/round3/`.

**Requests to the home lane (features/dashboard owns the Progress window body)**
1. Hide Today / This week / Rhythm (or one line) when `activity` is null; remove the Goal stepper until daily reps exist; derive reps from passed steps.
2. Start review: the card's white primary when due > 0, or say why it is off ("Review opens after this lesson"); split Review into "Due now" and "Coming up"; list mastered skills only.
3. Skill-node tooltips in a portal (they clip under the row); Skills scroller with a bottom fade and padding; Practicing as a half-filled ring, Locked dashed or with a lock glyph, Review due as a neutral "due" chip, not a dot on the green check.
4. Engine: `review.items` only for mastered skills; `progress.week` / `activity` from passed steps.

**Fix round 1 (surfaces)**
- Contract-faithful stage: `?scenario=progress-contract&window=progress&clean&size=1440x900` answers `progress.get` with the contract's shape only (`skills[].items`, `completed[].at`, `review`) and `week: null`, as the real engine does. It shows the real state ("6 of 13 mastered" beside "Not tracked yet"), so the home lane and QA see what learners see. Its trigger is step-scoped (`progress.get@step_progress_contract`), so `full` keeps the rich payload.
- **The "Not tracked yet" blocker stays open** until the home lane's request 1 (hide the activity blocks when there is no activity) and engine request 4 (`week` / `activity` from passed steps, plus a `contract:` PR for `activity`, `stageAnchor` and `reps`) land.
- Completion card: Skills, Next up and the actions wait for the last visible step row (`after = 4 + min(steps, ROWS)`), so the replay reads top to bottom. This lesson's skills come first with a quiet "new" tag when a node carries `lesson: true`; without it the track order stays and nothing is tagged. The `complete` scenario marks Backpropagation and Training loop.

**Contract request (fix round 1)**
5. `SkillNode.lesson?: boolean` on `card.skillMap.nodes` (server/lesson/skillmap.py): true on the skills this lesson taught, so the completion card can name the skill that leveled up. `features/complete/types.ts` already reads it when it is exactly `true`.

**Fix round 2 (surfaces)**
- Completion card fits the screen (round 3 review blocker: the Skills block pushed it to 906 px on a 900 px screen and an 8-step lesson clipped Start next lesson). `complete/room.ts` reports the room (pillTop to the work area's bottom, less 16 px) from an invisible overlay layer; the card caps there. The hero and the actions stay put and the middle (result, steps, skills, next up) scrolls on its own with a faded edge (top or bottom, whichever hides more; focusable while it scrolls). When the full middle doesn't fit, Skills folds to one row (the first chip, this lesson's own when tagged, then "and N more"), which is enough for a 6-step lesson at 1440x900. The step list no longer has its own scroller (one scroll, not two).
- Shots: `surfaces-complete-fit.jpg` (1440x900, fits, no scroll), `surfaces-complete-short-scrolled.jpg` (1440x700, middle scrolled to the end, actions visible).

**Still open, tracked for the home lane (not this lane's files)**
- The Progress window persona blocker is unchanged in the real app: with `?scenario=progress-contract` (what the real engine sends) the window still shows "Not tracked yet" on four cards, the Goal stepper, a disabled "Start review" beside "3 due", Review listing Practicing skills (groupby, broadcasting), and the keras row clipped at the bottom of the Skills card (`review-surfaces-progress-contract.jpg`). Requests 1 to 4 above are the fix and must land before learners see this window.
- The rich stage mock (`mock/scenarios/progress.json`) also clips the numpy row and the Review list ("Arrays" is cut off) in `review-surfaces-progress.jpg`: the Skills and Review cards need a scroller with padding (request 3).

# drawer

**Status:** pass 1 done, awaiting Adrian's review (not pushed) · **Priority:** P2 · **Port:** 5184 · **Branch:** `adrian/drawer`

### Pass 1 (Sat Nov 14)
**Works** (verified in headless Chrome over CDP, 22/22 checks; the Browser pane was hidden, so motion froze there):
- Tab: 4×40 at `fill.track`, 6px from the right edge, vertically centered on the work area, inside a 22×64 `data-hit` box; hover stretches the bar (transform only). Hidden while the drawer is open.
- Drawer: `color.glass` panel, `radius.card`, 340 wide, same top and bottom as the player's dock (ends above the shortcut bar). Slides in from the edge on the spring, out on `springOut`. Close: ✕, Esc (`dismiss`), new lesson, `reset`.
- Steps: done = white check, current = white ring with a dot + its live checks (core `CheckList`: green only on passed checks, amber only on a failed one), locked = empty ring in `color.faint`. Start time column (`h:mm:ss` past an hour). Clicking a done/current row → `seekVideo(step.video.start)`; locked rows don't respond.
- Part by part: appended steps fade in (40ms stagger); rows already on screen keep their exact opacity/transform and their title x (sampled every frame across both `lesson.updated`). Last quiet row "More steps coming" + "Part 3 of 3" from `parts`; "Next part is still building" with a spinner while `pendingNext`; gone when `complete`.
- Sources: one row each, video = thumbnail, others = `kindTone` tile (16% wash + glyph). Click → default browser via `drawer:open-url` (main, http(s) only); new tab in the stage.
- Spotlight: while the spotlight hole touches the drawer's column, the drawer and the tab slide away; if the learner had it open it slides back 700ms after the target moves on. The spotlight's caption already avoids the drawer (it reads `data-hit`).

**See it:** `http://localhost:5184/?scenario=drawer` → click the bar on the right edge. `&drawer=open` starts it open (stage only) to watch the whole ~30 s run: 3 steps, the learner catches up with the build, part 2 (steps 4–7), part 3 (8–11), then a spotlight on the left (drawer stays) and one on the right (drawer yields, comes back). Alt+H replays the spotlight. `?scenario=offtrack&drawer=open` shows a complete lesson. Shots: `agents/shots/drawer-*.png`.

**Left / for Adrian:**
- The bar sits on the player's right border (the player docks 8px in, the bar is 6px in), so it reads like a grabber on the player's edge. Keep, or move it to 2px from the edge (inside the gutter)?
- The player's chapter list shows done chapters with the green tick; the drawer uses a white check per this brief. Pick one for both (see Core request 1).
- Electron unverified (Windows SAC): `drawer:open-url`, click-through over the tab, Esc reaching the overlay.

## Goal
A slim tab on the right edge (vertically centered, 6px from the edge). Click → a lesson drawer slides in: every step as done / current / locked, the current step's checks, and the lesson's sources. With long videos (Michael: Karpathy's 2-hour GPT video) the steps arrive part by part, so the drawer is where you see what's coming.

## Owns
- `app/src/renderer/src/features/drawer/`
- `app/mock/scenarios/drawer.json` (a long lesson: `lesson.ready` with `complete:false`, then two `lesson.updated`)
- `app/src/main/features/drawer.ts` (`drawer:open-url` → default browser)

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
1. **A shared step-state icon** (`StepIcon {status: 'done' | 'current' | 'locked'}` in `core/ui/atoms.tsx`), used by the player's Chapters and the drawer, so both show a step the same way. `CheckIcon` only has the green pass. *Workaround:* the drawer draws its own (same geometry as `CheckIcon`, white fill).
2. **`clock()` with hours** (`1:02:00`, not `62:00`): long videos are the point of part-by-part. The player shows `60:18`, `116:20` today. *Workaround:* local `stamp()` in `Drawer.tsx`.
3. **`setWindowOpenHandler` on the overlay window** (and every `ctx.createWindow` window): deny, and `shell.openExternal` for http(s). Today only the player's window has one, so `window.open` from the overlay opens a bare Electron window. *Workaround:* `src/main/features/drawer.ts` handles `drawer:open-url`.
4. **`alpha(hex, a)` in `core/theme.ts`** (or a core `KindTile` atom): the launcher and the drawer each carry a copy for the `kindTone` wash.

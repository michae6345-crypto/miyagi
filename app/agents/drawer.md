# drawer

**Status:** pass 2 done (light/dark glass, content-fit height), awaiting review (not pushed) · **Priority:** P2 · **Port:** 5184 · **Branch:** `adrian/drawer`

### Pass 2 (Sat Nov 14, evening): light / dark
**Works** (headless Chrome over CDP, 28/28 checks in dark AND in light):
- Everything on `theme.glass`: panel, text, rows, dividers, the ✕, the scrollbar and the edge tab flip with Settings → Appearance (`setPrefs({appearance:'light'})`). No `backdrop-filter`.
- Without blur the .9 glass let the player's video and text show through, so the panel draws an inset layer of the same `glass.bg` under its content (~99% opaque, tokens only; the ghost went from 25 to 2 grey levels). See Core request 6.
- Done steps and passed checks are `glass.pass` (bright green on dark, `#1C8A3C` on light, the tick knocked out in `glass.buttonText`). Current = ring + dot in `glass.text`, locked = faint ring. Failed check = `glass.offTrack` (apricot). The check list is drawn locally on glass tokens (Core request 5).
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
1. **A shared step-state icon** (`StepIcon {status: 'done' | 'current' | 'locked'}` in `core/ui/atoms.tsx`, on glass tokens), used by the player's Chapters and the drawer, so both show a step the same way. *Workaround:* `StepIcon` / `Tick` / `Ring` in `Drawer.tsx`.
2. ~~`clock()` with hours~~ done in core.
3. ~~`setWindowOpenHandler` on every window~~ done in core; the drawer's main-process workaround is gone.
4. ~~`alpha(hex, a)` in `core/theme.ts`~~ done in core.
5. **`CheckList` / `CheckIcon` / `Spinner` on glass** (pass 2): core's are drawn for the black island (white text, white rings, `color.green`), so on a light glass panel the labels vanish. A `surface?: 'island' | 'glass'` prop (glass = `theme.glass.*`) would do. *Workaround:* `GlassCheckList` in `Drawer.tsx` (same layout and motion). The player's checks will hit the same thing when it moves to glass.
6. **An opaque glass background** (`glass.solid`, or `--glass-bg` closer to 1): with `backdrop-filter` gone, `.9`/`.92` lets whatever is under a panel show through (for the drawer, the player's moving video). *Workaround:* an inset `glass.bg` layer under the drawer's content (`boxShadow`), ~99% opaque.

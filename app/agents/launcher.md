# launcher

**Status:** brand pass done (Miyagi brand kit + Adrian's "no unnecessary writing" cuts), rebased on `adrian/shell` db72ef9, waiting for Adrian's review · **Priority:** P0 · **Port:** 5176 · **Branch:** `adrian/launcher`

## Goal
Launcher born from the notch island (⌥Space; Ctrl+Shift+Space on Windows). **Since Sat ~2 PM (Michael): the island expands down into the launcher and every exit collapses it back into the island; nothing opens mid-screen.** Type what you want to learn → results stream in (it grows down) → Build lesson → it collapses back up into the pill (the signature transition). Pasting a YouTube link skips search. **During a lesson** it becomes "Ask about this step": Enter sends `action {kind:"ask", text}` and the answer comes back as a card.

## Owns
- `app/src/renderer/src/features/launcher/`

## Contract
- **In** (engine → app): `search.result`, `search.done`, `lesson.building`, `lesson.ready`, `error`
- **Out** (app → engine): `learn {query}`, `learn_url {url}`, `build_lesson {resultIds}`, `action {kind:"ask", text}`

## Plugs in as
`windows: [{ route: 'launcher', stage: 'fill' }]`; the window itself is created by core

## Done when
- [x] Grows out of the island's exact shape (`launcher:open {from}`) at `pillTop`, 640 wide, black island look (mockups 01/02/05); grows down as results stream in; results stagger in 40ms; the highlight glides
- [x] Brand kit (`app/brand/BRAND.md`): bonsai mark in the field, "Ask Miyagi anything", monochrome (white accent, no glow / gradient / extra hues), white primary button with ink text, amber/green unused
- [x] Build lesson → collapses onto the 300×34 pill rect (hand-back at ~400ms), no flicker *on the launcher side*. The island overshoots right after the swap: Core request 1
- [x] URL paste → `learn_url`
- [x] Ask mode during a lesson
- [x] Empty / searching / error states (plus engine offline)
- [x] Esc and click-outside collapse it back into the island (never fades out mid-screen)

## Test
`npm run dev:web -- --port 5176` → `http://localhost:5176/?scenario=full`
- **Search + build:** Ctrl+K (the pill grows into the launcher), type anything or click a suggestion chip, Enter (rows stream in, it grows down), ↑↓ or hover, Enter again → it collapses into the pill.
- **Ask:** once "Step 4 · Define the residual" shows, Ctrl+K → ask mode (a faint step line, placeholder "Ask about this step"; Tab flips to a new lesson and back), type, Enter → it collapses back into the step pill and the answer card grows out. The mock answers at step 4 and step 6 (`mock/scenarios/launcher.json`); the chips send Explain / Hint.
- **Link:** paste a YouTube link (e.g. `https://www.youtube.com/watch?v=kCc8FmEb1nY&t=1m30s`) → one row, Enter → `learn_url`.
- **States:** `?scenario=launcher` has no `learn` trigger, so a search stays in flight (skeletons). Answer it from the console: `(await import('/src/core/bus.ts')).dispatch({type:'search.done',payload:{total:0}})` (empty) or `{type:'error',payload:{message:'…'}}` (error).
- Esc / click outside / Ctrl+K again collapse it back into whatever the island showed (pill or card); the HUD's Reset closes it and clears the field.

## Adrian's spec
**First pass (no spec from Adrian yet):** build to the mockups in `docs/mockups/` (01–05 are the target look; 06–07 are earlier explorations to restyle in the Apple look) and the animation + placement spec in `docs/FRONTEND-HANDOFF.md`. Don't spend time on colors (Adrian's theme comes later). Adrian reviews after this pass and writes his spec here for pass 2.

## Core requests
1. **`core/Island.tsx`: zero the velocity after the landing snap (visible glitch, please fix).** On `pill:receive` the island snaps to 300×34 with `transition={{ duration: 0 }}`. That leaves a huge velocity on the width value, and the next spring launches with it: right after Build lesson the pill balloons to ~826px wide and shrinks back over ~400ms (`shots/launcher-06-build-strip.png`, last frames). **Verified fix** (tried locally, reverted): `transition={landing ? { duration: 0 } : { ...(isPill ? springOut : spring), velocity: 0 }}`. The pill then settles 300 → 256 with no overshoot. A narrower version only zeroes it for the first spring after a landing (a `justLanded` ref), so other interruptions keep their momentum.
2. **`core/Island.tsx`: no content crossfade on the landing frame** (lower priority, not seen in the stage). If `lesson.building` hasn't reached the overlay window when `pill:receive` arrives (Electron windows are separate; a slow engine), the island switches idle → building at the swap and "Learn anything" fades out for 80ms under the just-landed pill. Suggest: when `pill:receive` changes the mode, show the new content at full opacity with no exit/enter for that one change.
3. **`core/theme.ts` tokens** for the neutral fills now in `features/launcher/tint.ts` (white at low alphas on the black island: field fill/border, chip fill/hover/border/text, row highlight, icon tile/glyph, skeleton, footer rule, backdrop dim; ink at .1 for the keycap on the white button). Also export the island's two **shadows** (pill `'0 2px 10px rgba(0,0,0,.25)'`, card `'0 24px 60px rgba(0,0,0,.5)'`, both hard-coded in Island.tsx) as tokens: the launcher must match them exactly to hand over invisibly.
4. **`core/theme.ts`: `launcher` = `{ width: 640 }`** (the notch launcher; `topRatio` is gone). The launcher uses a local `WIDTH = 640` until then.
5. *(Optional)* **Live island size during a collapse.** The launcher collapses to the `from` size it got at open. If the island's size changes while the launcher is open (e.g. the step changes), the island reappears at its new size and springs there. Fine for now; if it shows, main could re-send `{from}` with `launcher:close`.

## Notes
Window show/hide/focus is core (`src/main/index.ts`); the shrink target comes from `bridge.platform.pillTop` + `theme.pill`.

**Brand pass (Sat ~2:30 PM): Miyagi brand kit + Adrian's cuts.** Built on the UI polish session's monochrome pass (5584cf5; it replaced an earlier glow/aurora look Adrian rejected).
- Rebase note: `adrian/shell` had picked up 34cf806, the UI polish session's first, pre-amend glow commit (prettier-default formatting). The rebase resolved every launcher file to the final monochrome versions (single quotes, no semicolons); `index.tsx`, `store.ts`, `youtube.ts` are unchanged since 3644feb.
- **Brand:** the bonsai `<MiyagiMark size={17} />` replaces the sparkle in the field (a spinner while searching); placeholder `copy.launcherPlaceholder` ("Ask Miyagi anything"); `color.accent` is white, so the caret and the "Best" label are white; the primary footer action is the brand button (white `color.accent` fill, `color.onAccent` ink text, ink keycap) only when it can act, otherwise a quiet label; error and offline notes are white, never amber (amber = off-track only).
- **Adrian: "no unnecessary writing; a functional, clear, concise workflow."** No titles: search mode is field → suggestion chips (idle) or rows → footer; ask mode adds one faint line above the field ("Step 4 · Define the residual"), placeholder "Ask about this step", Explain / Hint chips. No "Top results"/"Searching" label (the field's spinner shows searching). The footer is keys only, showing the ones that apply now: "Choose ↑↓" (2+ rows), "New lesson ⇥" / "Back to step ⇥" (during a lesson), and the primary "Search ↵" / "Build lesson ↵" / "Ask ↵". Words appear only when something is wrong ("Offline", a partial-results error). Rows are title + meta; only the best row is labelled ("Best"). The link row is just the video.
- Kept: suggestion chips (Adrian likes them), Enter searches then Enter builds the highlighted row, Tab toggle, every exit collapsing into the island, the hand-over invariants (exit targets keep every key; `focus({preventScroll})`; single-layer shadows equal to core/Island's).
- Checked in headless Chrome on the brand core: open from the island (220 wide → 640×159 idle), grow with results (→ 304), build / link → 300×34, ask → the 260×34 step pill, Esc / click outside → the 420×196 answer card, hand-back at ~290–430ms; Tab, chips, button, link paste, empty / error / offline, reduced motion, Reset, arrow clamping; no console errors. Core request 1 (island overshoot after the swap) is still there.
- Shots: `agents/shots/launcher-brand-*.png` (05 open, 06 build, 08 ask, 14 Esc are frame strips). The older pre-brand shots were removed.

**Pass 1, notch version (Sat afternoon, after the 2 PM direction change):**
- **Open:** `launcher:open {from:{w,h}}` → the panel starts on that exact shape (top = `pillTop`, centered, black, radius h/2 for a pill or 24 for a card, same shadow) and springs to 640 wide × its content height. The island's own content (whatever island mode is active, e.g. "Learn anything ⌥Space") fades out inside it in 80ms; the launcher's content fades in after 60ms, rising 4px. The core island hides itself meanwhile.
- **Height = content:** a ResizeObserver feeds the content height to the panel spring, so it grows down as skeletons and rows arrive (192 → 416px in the mock). The results list itself no longer animates its height.
- **Exits all collapse:** Esc / click outside / toggle and ask → back to `from` (pill or card) with that island mode's content fading in, then `launcher:hidden`. Build lesson / link → onto 300×34 with the `building` content, then `launcher:built`. Exit springs end within 1px (`restDelta 1`), so the island is back at ~400ms.
- Focus uses `preventScroll`: while the panel is still pill-sized it clips its content, and a plain `focus()` scrolled the content up (the title showed cut off).
- Light dim (`rgba(0,0,0,.18)`), no blur. Placeholder copy is generic ("Search a topic, or paste a YouTube link").
- Reads island modes through the lazy registry (`getIslandModes()`, core 0876da5). Re-checked all flows on that core: same hand-over, and the Core request 1 overshoot is still there (~952px after the swap).
- Pressing ⌥Space again *during* a collapse (~400ms) is swallowed: main still thinks the launcher is open until `launcher:hidden`.
- Shots: 05 open, 06 build, 08 ask and 14 Esc are frame strips; 01–04, 07, 09–13 are states.

**Pass 1, first version (Sat, mid-screen Spotlight panel; superseded by the notch version above, kept for what still applies):**
- Files: `Launcher.tsx` (panel, phases, motion), `Rows.tsx` (result / link / skeleton / message rows), `store.ts` (search + error), `youtube.ts` (link parsing), `tint.ts` (local fills until the theme has tokens).
- **Phases:** `open → closing` (Esc, click outside, toggle; `launcher:hidden`) · `open → building` (Build lesson or link; morph, then `launcher:built`) · `open → sending` (ask; fly into the pill + fade, then `launcher:hidden`). A safety timer finishes an exit if its animation never completes, so the launcher can't get stuck.
- **The build collapse** lands on the pill's exact pixels (`pillTop`, 300×34, r17, black, pill shadow; measured 650,6 300×34). On the landed pill it renders the pill feature's own `building` island mode (looked up in `islandModes`; fallback included), so the swap shows identical pixels whatever the pill agent ships.
- **Highlight:** one element animated on `y` (spring) instead of a shared `layoutId`. Same glide, but a layoutId glide is off by the stage's CSS scale factor (it measures viewport px); this one is exact at any scale and only animates transform.
- **Rows** are absolutely slotted (64px), so a skeleton and the result replacing it crossfade in place. Entrances are at least 40ms apart: a batch (e.g. reopening) staggers, a stream just flows in.
- **Mode** is picked on open: a lesson exists → ask mode (title "Ask about this step", "Step N of M · title", Explain/Hint chips that fire the normal shortcuts). Otherwise search.
- **Link paste** replaces the whole field. Recognised: `watch?v=`, `youtu.be/`, `shorts/`, `live/`, `embed/`, with `t=`/`start=`. The row shows YouTube's public thumbnail (`i.ytimg.com`). Typing a link works too.
- **Errors:** an engine `error` lands in the launcher when a search is in flight or the panel is open. With no results it's the row; with partial results it's the footer (amber). `connected=false` shows "Engine offline" in the footer.
- **Reduced motion:** crossfades only (open and every exit become 200ms fades at full size, then the hand-over).
- Exit targets keep every key of the open target: a key dropped from `animate` settles instantly and ends the animation early (this cut the Esc fade short).
- **Not checked:** Electron (separate windows): the swap timing, focus return and `TUT_NATIVE_GLASS` all need Michael's Mac. 
- **How it was checked:** the Browser pane was hidden (0 frames), so every flow ran in headless Chrome over CDP against the stage: real frames, timings and DOM probes. Screenshots: `agents/shots/launcher-*.png`.
- **Ideas for pass 2:** Tab to start a new lesson from ask mode; mic button (voice query) is decorative today; show the step count once the engine sends it with results ("7 steps" in the mockup).

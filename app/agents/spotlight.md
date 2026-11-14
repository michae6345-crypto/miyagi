# spotlight

**Status:** pass 1 done (awaiting Adrian's review) · **Priority:** P0 · **Port:** 5178 · **Branch:** `adrian/spotlight`

## Goal
Screen-first building mode: the engine's screen reader finds where you should work (in any app) and sends a rectangle. We dim the screen to 55%, cut a rounded glowing hole there (it springs when the target moves; the glow pulses once, then stays still), and put a small glass caption beside it with a voice button.

## Owns
- `app/src/renderer/src/features/spotlight/`

## Contract
- **In** (engine → app): `spotlight {rect:{x,y,w,h}, caption, app?, matched?}` in screen points, or `{clear:true}`; cleared on `step.started` / `step.passed`
- **Out** (app → engine): nothing directly; core sends `overlay.bounds` for every `data-hit` / `data-ui` element (keep the caption marked `data-ui`)

## Plugs in as
overlayLayers: spotlight (z 10)

## Done when
- The cut-out lands exactly on the rect (points; multi-display origin via `layout.origin`)
- The caption flips left at the screen edge
- Fallback mode: a glowing outline only, no dim (the cut-order item)
- Never blocks typing (click-through)

## Test
`npm run dev:web -- --port 5178` → `http://localhost:5178/?scenario=full` (or `?scenario=spotlight` once you add `mock/scenarios/spotlight.json`)

## Adrian's spec
**First pass (no spec from Adrian yet):** build to the mockups in `docs/mockups/` (01–05 are the target look; 06–07 are earlier explorations to restyle in the Apple look) and the animation + placement spec in `docs/FRONTEND-HANDOFF.md`. Don't spend time on colors (Adrian's theme comes later). Adrian reviews after this pass and writes his spec here for pass 2.

## Core requests
1. **Overlay on the target's display.** The overlay window covers the display nearest the cursor at startup (`displayNow()` in `src/main/index.ts`), so a target on another display isn't drawn at all. Either one overlay per display, or move the overlay to `screen.getDisplayMatching(rect)` when a `spotlight` arrives. The layer is already ready for it: each window converts with its own `layout.origin`, draws only if the hole touches it, and the caption goes to the window holding most of the target.
2. **A hook for the overlay's other UI rects** (the same set core already reports as `overlay.bounds`), e.g. `useUiRects()` from `core/Overlay.tsx`, so the caption can stay clear of the shortcut bar / pill / cards. Local workaround: `useOtherUi()` in `Spotlight.tsx` reads `[data-hit],[data-ui]` from the DOM every 400ms.
3. **Theme tokens** `dim` (black at 0.55) and a light accent (ring + code text). For now: `DIM` is a local constant and the light/soft accents are `color-mix()` of `color.accent`, so Adrian's theme already carries through.
4. (dev) Vite doesn't see a new `mock/scenarios/*.json` until the dev server restarts (`mock/` is outside the Vite root). Worth a line in `agents/README.md` for the other agents.

## Notes
**Pass 1 (what works, all checked in the stage at 1600×1000 with headless Chrome; shots in `agents/shots/spotlight-*.png`):**
- **Dim + cut-out:** black at 55%, fades in over 280ms (container opacity). Rounded hole (r 12) = target + 8pt padding, grown to at least 44×30 around its center. Step 4's rect lands at 60,411 690×124, exactly mockup 04's cut-out.
- **Spring:** the hole is ONE set of motion values (x, y, w, h) sprung with the shared spring; the mask cut-out, glow and ring all read them (attributes written per frame, no React re-render). Retargeting mid-flight keeps velocity. Measured: ~240ms to land (`spotlight-06-spring-mid.png` is a real mid-flight frame).
- **Glow:** pulses once per new target (0.6 → 1 → 0.6 over 1.2s, measured 0.95 at 0.6s, 0.6 at 1.5s), then stays still. A new target re-pulses; a re-sent target doesn't.
- **OCR jitter:** a re-sent target within 2pt with the same caption is ignored, so the hole doesn't wobble on every screen read.
- **Caption** (glass, `data-ui`; voice button `data-hit`): right of the hole, top-aligned (offset 21 like the mockup) → flips left at the right edge → below / above when the target is too wide → inside only if nothing fits. Always clamped to the work area (menu bar, dock, top and bottom edges). Keeps clear of the shortcut bar, pill and cards (see Core request 2). Springs with the hole when the target moves.
- **Fallback (cut order):** `SPOTLIGHT_MODE` in `store.ts` (`'dim'` | `'outline'`); `?spotlight=outline` overrides it in the stage. Outline = glow + ring + caption, no dim (`spotlight-07-outline-fallback.png`).
- **Multi-display:** local = screen − `layout.origin` (both primary-top-left points; negative origins for displays left of / above the primary work). Only the display the target is on draws it (dimming a display with no hole would hide the player); a target straddling two displays gets its caption where most of it is. Math is in `place.ts` (pure) and was checked with node asserts, including negative origins.
- **Click-through:** the layer is `pointer-events: none`; only the voice button takes the pointer. The dim itself is not `data-ui`, so the engine's OCR still reads the screen under it.
- **Reduced motion:** no spring, no pulse, no caption slide; crossfades only.

**How to see it:** `npm run dev:web -- --port 5178` → `http://localhost:5178/?scenario=full`. Ctrl+K, type anything, Enter, Enter → step 4's spotlight ~1s after the lesson builds. Step 5 starts ~14s in: press **Alt+H** within its first ~2s to play the tour (`mock/scenarios/spotlight.json`: optimizer line → loss table → the video's heatmap, which flips the caption left → clear). Add `&spotlight=outline` for the fallback.

**For Adrian (decisions / tuning):**
- Mockup 04 reads darker than the spec's 55% (≈72% measured on its pixels); one constant, `DIM.opacity` in `Spotlight.tsx`.
- The caption's first line shows `Step N · <app>`; mockup 04 shows "line 22", which the engine doesn't send.
- Esc doesn't clear the spotlight: the engine owns it (cleared on `step.started` / `step.passed` / `{clear:true}`), and Esc already closes cards.
- The mock's `spotlight.code` field isn't in the contract; the caption shows `code ?? matched`.

**For Michael (engine):** send rects in global screen points (primary display's top-left = 0,0), so a capture of a secondary display needs its display origin added. The app pads by 8pt itself, so the engine's `locate()` can send the tight union of the matched lines.

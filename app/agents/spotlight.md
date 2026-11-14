# spotlight

**Status:** pass 2 (functional, Michael's P0-2) done on top of UI polish's look · **Priority:** P0 · **Port:** 5178 · **Branch:** `adrian/spotlight`

## Goal
Screen-first building mode: the engine's screen reader finds where you should work (in any app) and sends a rectangle. We dim the screen (`scrim.spotlight`, 66%), cut a rounded hole there edged with a white hairline (it springs when the target moves), and put a one-line island caption 8px beside it. It stays until the engine clears it, the step moves on, or the learner dismisses the card it came with.

## Owns
- `app/src/renderer/src/features/spotlight/`

## Contract
- **In** (engine → app): `spotlight {rect:{x,y,w,h}, caption, app?, matched?}` in screen points, or `{clear:true}`; also `card.targets` / `offtrack.targets` (extra cut-outs). Cleared on `{clear:true}`, `step.started`, `step.passed`, `lesson.ready`, reset / `lesson.ended`, or ✕ / Esc on the card it came with. Empty / zero-size / off-screen rect → core `notify(caption)`
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
1. ~~**Overlay on the primary display (v1).**~~ **Done in core**: the overlay and launcher open on the primary display. No spotlight change needed (the layer converts with `layout.origin`).
2. **A hook for the overlay's other UI rects** (the same set core already reports as `overlay.bounds`), e.g. `useUiRects()` from `core/Overlay.tsx`, so the caption can stay clear of the shortcut bar / pill / cards, **plus the player window's live rect** (it's its own window in Electron and the user can drag it). Local workarounds: `useOtherUi()` in `Spotlight.tsx` reads `[data-hit],[data-ui]` from the DOM every 400ms, and `index.tsx` avoids the player's default dock rect via `features/player/dock.ts` (a read-only import of the player's pure helper).
3. ~~**Theme token** `dim`~~ **Done in core**: `scrim.spotlight` (`rgba(0,0,0,.66)`, Adrian's value) in `core/theme.ts`; the spotlight now uses it (measured: 66% dim, unchanged).
4. ~~(dev) Vite doesn't see a new `mock/scenarios/*.json` until the dev server restarts~~ **Done in core**: documented for all agents (`da6ea3f`).

## Notes
**Pass 2: functional (Michael's P0-2: "Show me / Explain / Hint must visibly point at my screen"), look unchanged from UI polish. Shots `agents/shots/spotlight-0*.png` (re-shot; the old brand/state shots are gone):**
- **It stays.** Every `spotlight` renders the dim + cut-out and stays until `{clear:true}`, `step.started`, `step.passed` (the video resumes then; a dim over it would hide it), `lesson.ready`, reset / `lesson.ended`, or the learner dismisses the card it came with. No timeout (the 900ms pass hold is gone). Checked: still up after 9s; Esc with no card leaves it alone.
- **It follows its card.** The card that was open when the spotlight arrived (or that opens within 1.5s after it) owns it: ✕ / Esc on that card clears the spotlight too. An off-track card under an explain card or diagram still counts as open, so closing the explain card keeps the spotlight.
- **Nothing to point at → the pill.** An empty / non-finite / zero-size rect, or one with less than 25% of its hole on the primary display, draws no dim and calls `notify(caption)` once per target. **Gap (not spotlight's code):** no pill branch renders `lesson.notice` yet, so the notice is set but not visible.
- **Smooth replace.** A new spotlight springs the one cut-out from the old place (no remount). A `{clear:true}` (or a new step) waits 300ms (`REPLACE_GRACE_MS`) before fading, so clear + new spotlight is a move: measured dim opacity 1.0 on all 70 frames across it. An identical re-sent spotlight (≤2pt jitter) changes nothing, not even the pulse.
- **Multi-target.** `card.targets` / `offtrack.targets`: the engine spotlights `targets[0]`; every other on-screen target gets its own cut-out in the same dim, the same hairline at 70%, and a one-line island label above it (`data-ui`). The caption keeps clear of them. When the main spotlight moves to another target, the old one becomes an extra.
- **Click-through.** The layer is `pointer-events: none`; the dim isn't hit-tested and isn't `data-ui`. Only the caption (and target labels) are `data-ui`; the voice button (shown only while voice is on) is `data-hit`.

**How to see pass 2:** `http://localhost:5178/?scenario=full` → Ctrl+K, type, Enter, Enter. Step 5 starts ~14s in: press **Alt+H** in its first ~2s. The tour (`mock/scenarios/spotlight.json`): an off-screen rect (notice, no dim) → a hint card with 3 targets (spotlight on the optimizer, labeled extras on the loss table and `create_graph`) → the same spotlight re-sent (nothing moves) → clear + new spotlight 150ms later (the cut-out springs to the loss table, no dim flash) → it stays: press **Esc** to close the card and the spotlight with it (or wait for the step to pass).

**Adrian's feedback ("sleek, more contrast, a little color"); superseded by UI polish (one white hairline, no state color):**
- Color only carries state, the same meaning as the pill's dot and the cards: the hairline is **white** while Miyagi watches, **amber** when off track, **green** when the step passes. The ring re-pulses on each state change, and on `step.passed` it holds green for 900ms (`PASS_HOLD_MS` in `store.ts`) before fading out. A 7px status dot (gray / amber / green) leads the caption's first line.
- More contrast: the dim is 66% (was 55%), the ring rests at 0.9 opacity (was 0.6), and the code line is bright mono at 78% (was muted).
- Still on brand: no new hue, no glow, no gradient. If Adrian wants a decorative accent color beyond the status colors, that's a brand-kit change (`core/theme.ts`).

**Brand pass (Miyagi kit, `app/brand/BRAND.md`); the look was later refined by UI polish:**
- The blurred blue glow ring is gone. The ring is a crisp 1.5px white hairline (`color.accent`) over a faint `color.onAccent` keyline at 0.35, so it still reads over light apps. No SVG filters. It still springs with the cut-out and pulses once in opacity (0.6 → 1 → 0.6).
- The outline fallback uses the same hairline (no dim).
- Caption: system font on the brand scale (13 / 15), title in `color.text`, code in muted white mono (`color.label`, `font.mono`). The voice button is white on dark when on (`color.accent` fill, `color.onAccent` icon) and quiet glass when off (`color.hairline` fill, `color.label` icon). No blues, `color-mix` accents or hard-coded colors left, except the dim's black (Core request 3) and the mask's luminance white/black.
- With the lesson player now docked on the right, the caption keeps off it. Step 4's caption therefore sits **below** the residual block instead of to its right (mockup 04 predates the docked player). When every ideal spot is covered, it slides along the hole to the nearest free spot (≤160pt), or takes the least-covered spot, so it never jumps across the screen. The tour's third stop moved to `create_graph=True` (lines 20–21), which now flips left because of the player.
- The `spotlight-0*.png` shots are pre-brand (blue glow); the `spotlight-brand-*` set replaces them.

**Pass 1 (history; checked in the stage at 1600×1000 with headless Chrome):**
- **Dim + cut-out:** black at 55%, fades in over 280ms (container opacity). Rounded hole (r 12) = target + 8pt padding, grown to at least 44×30 around its center. Step 4's rect lands at 60,411 690×124, exactly mockup 04's cut-out.
- **Spring:** the hole is ONE set of motion values (x, y, w, h) sprung with the shared spring; the mask cut-out, glow and ring all read them (attributes written per frame, no React re-render). Retargeting mid-flight keeps velocity. Measured: ~240ms to land (`spotlight-06-spring-mid.png` is a real mid-flight frame).
- **Glow:** pulses once per new target (0.6 → 1 → 0.6 over 1.2s, measured 0.95 at 0.6s, 0.6 at 1.5s), then stays still. A new target re-pulses; a re-sent target doesn't.
- **OCR jitter:** a re-sent target within 2pt with the same caption is ignored, so the hole doesn't wobble on every screen read.
- **Caption** (glass, `data-ui`; voice button `data-hit`): right of the hole, top-aligned (offset 21 like the mockup) → flips left at the right edge → below / above when the target is too wide → inside only if nothing fits. Always clamped to the work area (menu bar, dock, top and bottom edges). Keeps clear of the shortcut bar, pill and cards (see Core request 2). Springs with the hole when the target moves.
- **Fallback (cut order):** `SPOTLIGHT_MODE` in `store.ts` (`'dim'` | `'outline'`); `?spotlight=outline` overrides it in the stage. Outline = glow + ring + caption, no dim (`spotlight-07-outline-fallback.png`).
- **Multi-display:** local = screen − `layout.origin` (both primary-top-left points; negative origins for displays left of / above the primary work). Only the display the target is on draws it (dimming a display with no hole would hide the player); a target straddling two displays gets its caption where most of it is. Math is in `place.ts` (pure) and was checked with node asserts, including negative origins.
- **Click-through:** the layer is `pointer-events: none`; only the voice button takes the pointer. The dim itself is not `data-ui`, so the engine's OCR still reads the screen under it.
- **Reduced motion:** no spring, no pulse, no caption slide; crossfades only.

**How to see it:** see "How to see pass 2" above. Add `&spotlight=outline` for the fallback.

**For Adrian (decisions / tuning):**
- Mockup 04 reads darker than the spec's 55% (≈72% measured on its pixels); one constant, `DIM.opacity` in `Spotlight.tsx`.
- The caption's first line shows `Step N · <app>`; mockup 04 shows "line 22", which the engine doesn't send.
- Esc doesn't clear the spotlight: the engine owns it (cleared on `step.started` / `step.passed` / `{clear:true}`), and Esc already closes cards.
- The mock's `spotlight.code` field isn't in the contract; the caption shows `code ?? matched`.

**For Michael (engine):** the layer follows the convention pinned in `events.ts` (points, top-left, primary display's full frame, menu bar included); on the primary display `layout.origin` is (0,0), so rects are used as-is and only the caption is kept out of the menu bar (work area). The app pads by 8pt itself, so `locate()` can send the tight union of the matched lines.

**Rule check after the core update:** no PINN-specific strings in the feature's UI code (the demo wording lives only in `mock/scenarios/spotlight.json`). The caption is anchored beside the target, not born from the notch island: the island rule names the launcher, cards, diagrams and settings, and FRONTEND-HANDOFF places the caption next to the highlighted block. Adrian's call for pass 2 if he wants it to grow out of the island instead.

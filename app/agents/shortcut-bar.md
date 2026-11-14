# shortcut-bar

**Status:** pass 2 done: UI polish (afdb33a) and voice (72980d4) merged; spinner, press, Voice tile (on / speaking only, ready for voice 4a47bf3), diagram state, checked in the stage · **Priority:** P1 · **Port:** 5179 · **Branch:** `adrian/shortcut-bar`

## Goal
The bar at the bottom during a lesson: an Ask field (opens the launcher in ask mode) and Back · Explain · Diagram · Show me · Hint · Voice. It must never look dead: a pressed action shows a spinner until the engine answers (Michael's P0-2: "pressing them feels dead").

## Owns
- `app/src/renderer/src/features/shortcut-bar/`

## Contract
- **Out:** `triggerShortcut(kind)` (core: it records the pressed kind and sends `action {kind}`)
- **In:** `useThinking()` (core/lesson: `status thinking`, 2–5 s model calls) + `usePressed()` (core/shortcuts) → spinner on the pressed tile while `thinking && pressed.kind === kind`; diagrams store (open), voice store (on / speaking)

## Adrian's spec (pass 2: the pastel options mapping, BRAND.md)
- Icon tiles: 28px rounded-[8px] square. **Explain, Diagram = sky · Show me = lilac · Hint = pink** (`theme.actionTone`), ink glyph (`color.onAccent`). **Back, Voice = neutral** (`fill.button`, white glyph). Label under the tile stays white.
- Keycaps: **always `bridge.platform.keys[kind]`** (⌥E on Mac, Alt+E on Windows). Never type a key label by hand.
- Ask field: `<MiyagiMark size={14} />` + "Ask anything" + `<Kbd>{bridge.platform.keys.launcher}</Kbd>`. No sparkle.
- Thinking: the pressed tile's glyph becomes the core `Spinner` (ink on pastel). Pressed shortcut scales to 0.94 for 90 ms.
- Voice on: tile stays neutral, glyph white, a 3-bar equalizer while audio plays (voice store).
- Remove the `blue` variable; divider = `fill.rule`; tokens only.
- Copy: labels only (Back, Explain, Diagram, Show me, Hint, Voice).

## Done when
- Pastel mapping exact; keycaps from the platform; spinner while thinking; equalizer while speaking
- Appears with the lesson (y 16 → 0), 24px above the dock / taskbar

## Test
`npm run dev:web -- --port 5179` → `http://localhost:5179/?scenario=full`, Alt+E / Alt+D / Alt+S / Alt+H.

## Pass 2 (functional), Sat
- **Never look dead** (`Busy.tsx`): `<Glyph kind tone>` swaps the tile's glyph for the core `Spinner` (same size, the glyph's color) while `useThinking() && usePressed().kind === kind`, with one guard: the thinking spell must start ≤ 6 s after the press (or already be running at the press). Show me is answered by `video.seek`, which doesn't clear `usePressed`, so without it a later coach run would spin a stale tile (Back / Voice no longer set it: core 82d54fc). `role="status"` + `data-busy` on the spinner.
- **Press** (`press.ts`): one module-level `onUi('shortcut')` listener (claimed or not) → the matching tile scales to 0.94 for 90 ms. Covers bar clicks, global keys (Overlay routes them through `triggerShortcut`), stage keys and the launcher's chips (same window in the stage). A second press restarts the timer.
- **Voice** (`Equalizer.tsx`): reads only `on` / `speaking` from `features/voice/store.ts`; the tile's click goes through `toggleVoice()` (the ⌥V path). Voice now speaks with the computer's own voice (`adrian/voice` 4a47bf3, ElevenLabs dropped), which can't be metered, so `level` is gone and the three ink bars loop on their own rhythms while `speaking`. On = UI polish's white tile with an ink glyph + `aria-pressed`. ⌥V is claimed by voice (never reaches the engine), so the Voice tile never spins; it still dips for 90 ms. Typechecked against both the shell store (with `level`) and 4a47bf3's (without). Reduced motion: still rest shape.
- **Diagram** open state: `useDiagram(d => d.open)` (diagrams store on `adrian/shell`) → lit + `aria-pressed`. ⌥D while open is claimed by the diagrams store (closes it), and still dips the tile.
- **Mock** (`mock/scenarios/shortcut-bar.json`, merged into `full`): Explain / Hint / Diagram / Show me at steps 4–6 send `status thinking`, then the existing answer after 1.2–2 s, then `status watching` (step 4) / `offtrack` (step 6). Spotlight's Hint at step 5 is untouched.
- **Checked in the stage** (headless Chrome over CDP, `?scenario=full&engine=ws://127.0.0.1:9`): Alt+E / Alt+H / Alt+D spin only the pressed tile from `status thinking` until the answer; press dip samples 1 → 0.94 at ~90 ms → 1 at ~180 ms for both a key and a click; a Show me press 10 s old does not spin on a later thinking; a press while already thinking spins until idle; Diagram `aria-pressed` true while open, false after Esc; Voice on → lit, speaking → bars move. Not checked: Electron (cross-window, see Core request 1), real ElevenLabs audio driving `speaking`.
- **Shots:** `agents/shots/shortcut-bar-{explain-thinking,hint-thinking,explain-answered,diagram-open,voice-on,voice-speaking,voice-states}.png` (voice-states = off · on quiet · off again).
- **Merged UI polish** (`origin/adrian/shell` efed46a + be157ff, merge afdb33a): their tiles, Ask field and tokens kept as is. Their inline `thinking && sent === kind` spinner and inline equalizer were replaced by `Glyph` / `Equalizer` (one implementation each), fed the tile's glyph color (`tile.color`: ink on pastel and on the white Voice-on tile, white on neutral) at the tile's 16px glyph size.

## Core requests
1. **Cross-window press (Electron).** The launcher is its own window: its Explain / Hint chips call `triggerShortcut` there, so the overlay's bar gets neither the 90 ms dip nor `usePressed` (no spinner on the bar tile for a chip press). Route chips through main to the overlay's `'shortcut'` signal (the same path as global keys), or broadcast `usePressed`. Works in the browser stage (one window).
2. **When a press is spent.** Back / Voice are done (82d54fc). Left: clear `usePressed` when the thinking spell after it ends (`thinking` → anything else) and on `video.seek` (Show me's answer). Then the 6 s guard in `Busy.tsx` can go.
3. **Spinner track on light tiles.** `Spinner`'s track is fixed `fill.trackSoft` (white 14%), which disappears on the pastel and white tiles (the ink arc reads fine). A `track` prop (e.g. `fill.onAccentKey`, ink 10%) would let tiles pass an ink track.
4. (Global shortcut registration is core: `src/main/index.ts`.)

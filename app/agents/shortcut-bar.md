# shortcut-bar

**Status:** pass 3 done (Sat): labels only, keycaps on hover / ⌥ held, glass tokens (light + dark), quiet step controls; two layouts for Adrian to pick (`all` default, `more` via `?bar=more`) · **Priority:** P1 · **Port:** 5179 · **Branch:** `adrian/shortcut-bar`

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

## Pass 3 (Adrian: "simpler"), Sat
- **Labels only.** A tile is its 30px glyph tile + label; the keycap line is gone. The bar is 74px (was 88).
- **Keycaps on demand** (`Tile.tsx`, `keys.ts`): hover a tile → its keycap floats above the bar (a small glass chip, `data-ui`, from `bridge.platform.keys`). Hold ⌥ (Alt) → every tile's keycap shows; released, blurred or hidden → gone. Only `e.key === 'Alt'` counts, so AltGr typing doesn't flash them. In Electron the overlay never has focus, so hover is the way there. The Ask field keeps its ⌥Space keycap inline.
- **Step controls**: one hairline divider between the action tiles and Check · Skip step · End lesson. Check is the one primary (`glass.button`); Skip step / End lesson are quiet (`glass.field` tile, `glass.label` glyph and label). The divider after the Ask field is gone (the field's own border separates it).
- **Two layouts** (`layout.ts`): `all` (default, 9 tiles) and `more` (`?bar=more` in the stage): Explain · Diagram · Show me · Hint · Voice | Check · More, where More opens a small glass menu above the bar with Back (⌥←), Skip step, End lesson. The menu closes on a pick, a second click, Esc (`dismiss`) or a pointerdown elsewhere. Small shadow (`shadows.pill`): the panel shadow dimmed the Check tile below. Adrian picks one; then delete the other (and `layout.ts`).
- **Light mode**: every bar color is `theme.glass.*` (surface, hairline, shadow, text, label, divider, neutral / quiet tiles, keycaps, hover, lit). Pastel tiles keep ink glyphs. Voice on / Check = `glass.button` + `glass.buttonText`. MiyagiMark tone follows `useAppearance()`. Hover and lit fills are plain CSS (`hover:bg-[var(--glass-field)]`), not motion, so a live appearance switch repaints at once. Spinner arc on Check resolves the CSS variable (checked: paper on ink in light).
- **Checked in the stage** (headless Chrome, both appearances, both layouts): no keycaps at rest; hover Explain → ⌥E only; Alt down → ⌥←, ⌥E, ⌥D, ⌥S, ⌥H, ⌥V (More layout: no ⌥←), Alt up → none; Alt+E / Alt+H spin only their tile; Check spinner while `check_step` thinks; Voice on + speaking → equalizer on the ink tile; Diagram open → lit; More menu opens with Back ⌥← / Skip step / End lesson, closes on Esc and on an outside pointerdown, Skip step sends `skip_step`; `setPrefs({appearance:'light'})` flips the bar live (bg `rgba(250,250,248,.92)`, ink text).
- **Not checked**: Electron (hover keycaps over the click-through overlay, the More menu's outside click: clicks outside `data-hit` go to other apps, so there it closes by a pick or a second click). The stage's own "Reset" chip overlaps the left end of the wider `all` bar in the browser stage only.
- **Spinners on glass** (shell a277088 merged in 3475e64): each tile look carries its busy spinner. Pastel option tiles: the core ink `Spinner` on a `fill.onAccentKey` track. Neutral / quiet tiles: `GlassSpinner` (colors via CSS, so the glass variables resolve) on `glass.track`. Check / Voice on (`glass.button`): `GlassSpinner` in `glass.buttonText` on that color at 18% (`color-mix`), since no glass token reads on the button in both appearances. Checked in dark and light: Explain, Check, Skip step each show a visible ring and arc (`shortcut-bar-simple-spinners.png`).
- **Shots:** `agents/shots/shortcut-bar-simple-{all-dark,all-light,more,spinners}.png` (sheets: rest · hover · Alt held · thinking, light adds Check thinking · Voice speaking · Diagram open; more = rest and menu, dark and light, plus Alt held) and singles `shortcut-bar-simple-{all-dark-rest,all-light-rest,more-dark-menu,more-light-menu}.png`.

## Core requests
1. ~~Cross-window press (Electron)~~: done in core (0825d10, launcher chips run in the overlay), so the bar's dip and spinner cover them.
2. **When a press is spent.** Back / Voice are done (82d54fc). Left: clear `usePressed` when the thinking spell after it ends (`thinking` → anything else) and on `video.seek` (Show me's answer). Then the 6 s guard in `Busy.tsx` can go.
3. ~~Spinner track on light tiles~~: done (`Spinner track`, `core/ui/glass.tsx` GlassSpinner).
4. **A glass keycap.** `Kbd` is fixed to `fill.key` / `fill.keyText` (dark only). The bar uses a local `GlassKey` (`glass.key` / `glass.keyText`) meanwhile; a `Kbd tone="glass"` (or Kbd reading glass tokens) would let every glass panel share it.
5. (Global shortcut registration is core: `src/main/index.ts`.)

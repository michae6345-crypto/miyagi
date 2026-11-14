# shortcut-bar

**Status:** v1 built · pass 2 · **Priority:** P1 · **Port:** 5179 · **Branch:** `adrian/shortcut-bar`

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

## Core requests
_None yet._ (Global shortcut registration is core: `src/main/index.ts`.)

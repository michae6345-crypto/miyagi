# Video lesson calm (screen 28)

Problem: in a video lesson the drawer, the player, the 78px shortcut bar and the spotlight dim were all loud at once.

## Decision: one primary surface at a time
| Surface | Before | After |
| --- | --- | --- |
| Player | on | unchanged, it is the primary surface |
| Drawer | on | unchanged (steps and checks) |
| Shortcut bar | full bar always | while the drawer is open: one slim row of 36px icon tiles. Every action is kept (ask, Back, Explain, Diagram, Show me, Hint, Check, Skip, End); names and keycaps move to aria-labels and a caption: hover or keyboard focus shows the tile's label and keycap over it at once, and holding Alt shows every tile's keycap (the full tile's Alt reveal). The title tooltip stays as the slow fallback. Drawer closed: full bar returns. |
| Spotlight | stays until the engine clears it | video lessons: shows on step start, on Not yet, and on Hint or Explain (a card with targets, or the press itself), fades after 4 s or the first real keystroke. A faded box stays gone while the engine re-sends it, until the next step or one of those asks. Show me answers keep the old lifetime (the learner asked, Michael's P0-2). |

Why a slim row and not hidden: Explain, Diagram, Show me and Hint have no other button in a video lesson (the drawer has none, the player has Check, Replay, Skip). Hiding would remove function. Check, Skip and End are duplicated in the player, but only in its waiting state, so they stay as quiet icons. Only End armed ("Tap to end") gets the primary fill.

Untouched: "Just teach me" lessons (v2 panel, no bar, no player; their "type here" box is the lesson), the notch island, every surface still born from it, push-to-talk.

## Code
- `features/spotlight/calm.ts` pure gate (arm, admit, shown, keystroke, reset) and `isTyping`
- `features/spotlight/store.ts` wires the gate (step.started, offtrack and cards with targets arm it, a Hint or Explain press arms it once, Show me pins, keydown fades)
- `features/shortcut-bar/slim.ts` rule and height, `useSlim.ts` hook, `Tile.tsx` slim tile, `ShortcutBar.tsx`, `lift.ts` (height-aware), `index.tsx`
- Tests: `test/calm.test.ts` (pure gate), `test/calmStore.test.ts` (the store wiring: gate closed, Hint, Explain, card, Show me pin, refused-then-offtrack replay, "Just teach me" untouched, keydown)

## Shots (stage `?scenario=full`, Ctrl+K, topic, Enter, Enter)
- `shots/video-calm-1-before.png` all four up
- `shots/video-calm-2-after-step-start.png` slim bar, spotlight at step start
- `shots/video-calm-3-after-faded.png` spotlight faded after 4 s
- `shots/video-calm-4-after-drawer-closed.png` drawer closed, full bar back

## Not verified
- Electron: the overlay never has key focus, so the keystroke fade and the Alt keycap reveal only work in the stage; in the app the 4 s count is the real fade and hover is the way to read a tile.
- The slim row while the drawer has yielded to a spotlight (open but hidden) stays slim.
- Light appearance, Windows and real engine OCR re-sends (only the mock). Shot 4 (drawer closed) was not compared against light mode. The slim caption is hover, focus or Alt only (headless shots cannot show it), so with the drawer open a first-time learner sees icons until they hover; spec screen 28 lists a labelled bar there. Decision for Michael: keep icons-only (calm) or show labels once per lesson.
- The Hint or Explain arm is one-shot and 4 s: a re-send after the fade does not bring the box back.

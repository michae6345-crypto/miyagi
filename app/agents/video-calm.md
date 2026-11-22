# Video lesson calm (screen 28)

Problem: in a video lesson the drawer, the player, the 78px shortcut bar and the spotlight dim were all loud at once.

## Decision: one primary surface at a time
| Surface | Before | After |
| --- | --- | --- |
| Player | on | unchanged, it is the primary surface |
| Drawer | on | unchanged (steps and checks) |
| Shortcut bar | full bar always | while the drawer is open: one slim row of 36px icon tiles. Every action is kept (ask, Back, Explain, Diagram, Show me, Hint, Check, Skip, End); names and keycaps move to tooltips and aria-labels. Drawer closed: full bar returns. |
| Spotlight | stays until the engine clears it | video lessons: shows on step start and on Not yet, fades after 4 s or the first real keystroke. A faded box stays gone while the engine re-sends it, until the next step or Not yet. Show me answers keep the old lifetime (the learner asked, Michael's P0-2). |

Why a slim row and not hidden: Explain, Diagram, Show me and Hint have no other button in a video lesson (the drawer has none, the player has Check, Replay, Skip). Hiding would remove function. Check, Skip and End are duplicated in the player, but only in its waiting state, so they stay as quiet icons. Only End armed ("Tap to end") gets the primary fill.

Untouched: "Just teach me" lessons (v2 panel, no bar, no player; their "type here" box is the lesson), the notch island, every surface still born from it, push-to-talk.

## Code
- `features/spotlight/calm.ts` pure gate (arm, admit, shown, keystroke, reset) and `isTyping`
- `features/spotlight/store.ts` wires the gate (step.started and offtrack arm it, Show me pins, keydown fades)
- `features/shortcut-bar/slim.ts` rule and height, `useSlim.ts` hook, `Tile.tsx` slim tile, `ShortcutBar.tsx`, `lift.ts` (height-aware), `index.tsx`
- Test: `test/calm.test.ts`

## Shots (stage `?scenario=full`, Ctrl+K, topic, Enter, Enter)
- `shots/video-calm-1-before.png` all four up
- `shots/video-calm-2-after-step-start.png` slim bar, spotlight at step start
- `shots/video-calm-3-after-faded.png` spotlight faded after 4 s
- `shots/video-calm-4-after-drawer-closed.png` drawer closed, full bar back

## Not verified
- Electron: the overlay never has key focus, so the keystroke fade only works in the stage; in the app the 4 s count is the real fade. A global typing signal from main would need a core request.
- The slim row while the drawer has yielded to a spotlight (open but hidden) stays slim.
- Light appearance, Windows, real engine OCR re-sends (only the mock).

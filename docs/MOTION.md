# Motion

Piece 3 of Michael's Nov 21 email. Adrian owns it (branch `adrian/motion`, stacked on `michael/v2-integration`). The goal is every animation smooth and consistent: one set of springs, no dropped frames, no layout jumps, safe to interrupt, and Reduce Motion respected.

This file is the spec. The code's single source of truth is `app/src/renderer/src/core/ui/motion.ts`. `core/theme.ts` re-exports the same tokens, so older imports keep working.

## The vocabulary

| Token | Value | Use |
|---|---|---|
| `spring` | stiffness 420, damping 34, mass 0.9 | Anything that moves, scales or morphs. About 90% of the way in 0.13 s, settled in about 0.35 s, with a hair of overshoot. |
| `springOut` | stiffness 420, damping 38, mass 0.9 | Leaving and collapsing. Same speed, critically damped, so nothing that goes away bounces. |
| `fade.in` | 180 ms, `ease.out` | Opacity arriving. |
| `fade.out` | 120 ms, `ease.out` | Opacity leaving. Always quicker than arriving, so two states never sit on top of each other. |
| `fade.slow` | 240 ms, `ease.out` | A big surface's opacity (a panel, a window layer). |
| `fade.tint` | 120 ms, `ease.out` | Hover and press tint layers (`.mg-press`). The pressed tint is 40 ms. |
| `fade.instant` | 80 ms | A layer swapped out under a morph. |
| `beat` | 60 ms | One step of a sequence: content after its frame, a tick after its circle. Two beats is the longest anything waits on screen. |
| `press` | scale .97 (.96 for big tiles) on `spring` | Every pressable thing. Never below .95, never a tween. |
| `stagger` | 35 ms apart, 6 px rise, capped at 8 | Lists that arrive together. Child 9 and on arrive with child 8. |
| `ease.out` | `cubic-bezier(.23, 1, .32, 1)` | The only curve for enters and exits. `ease.inOut` only for a there-and-back flash. |
| Loops | dots 1.2 s, skeleton 2 s, spinner 1 s (CSS) | Only waiting indicators loop. They stop when their wait ends. |

Helpers in the same file: `enter(delay)` (move on the spring, fade on its own clock), `rise(reduced, { y, delay })`, `riseIn`, `staggerList` and `riseItem`, `staggerDelay(i)`, `textSwap`, `draw(reduced)` for stroke draws, `pop(reduced)` for glyphs, `pressMotion(disabled, large)`, and `sizeMove(reduced)` for width and height morphs.

## Rules

1. **Move on the spring, fade on a tween.** A spring on opacity reads as a lag, and a tween on movement can't be retargeted with its velocity. `enter()` gives both at once.
2. **Transform and opacity only.** Never animate `top`, `left`, margins, padding, `box-shadow`, `filter`, `background-color` or `color` per frame. A hover color is an opacity layer (`.mg-press`), and a shadow change is a crossfade.
   The one exception is a **size morph**: the island's width and height, the lesson panel's body height, the launcher's and settings sheet's grow out of the island, and the pill's text slot. These boxes have to change their real size because other things read them (the dock, click-through bounds and the engine's `overlay.bounds`). Each is kept cheap: an absolute or clipped box with `contain: layout`, a small subtree, and nothing outside it reflowing. The measured cost is in the tables below. With Reduce Motion a size morph snaps (`sizeMove`).
3. **Interrupt-safe.** Every animation starts from where the element is now. Springs retarget with their velocity, so a click halfway through turns the motion around instead of restarting it. That means:
   - No `key` that changes on every update just to replay an animation (a remount can't retarget). Key by identity (a step, a card), not by position or a counter.
   - `AnimatePresence` uses `popLayout` or an absolute slot for swaps, not `mode="wait"` (which queues a click behind an exit).
   - Every `setTimeout`, `requestAnimationFrame` and imperative `animate()` is cleared or stopped on unmount and when its reason changes.
   - Enter-key and click guards (double submits, in-flight locks) belong to the bug-hunt branch (`adrian/bug-hunt`). This layer only guarantees the UI is never left half-drawn.
4. **No layout jumps.** Space for a state that comes and goes is reserved (a fixed slot) or measured and sprung (a size morph). Text that changes width sits in a slot that springs to the new width. Nothing mounts into the flow without one of the two.
5. **Reduce Motion.** Chromium maps macOS Reduce Motion and Windows "Show animations in Windows" (off) to `prefers-reduced-motion: reduce`. With it on:
   - Nothing travels, scales or morphs. `MotionConfig reducedMotion="user"` (`main.tsx`) drops transform and `layout` animations. The helpers cover what it doesn't: size morphs snap, stroke draws become fades, `rise` and `textSwap` fade in place.
   - Fades stay but get no longer. A state change is a 180 ms crossfade or instant.
   - Waiting indicators never freeze (a frozen spinner reads as a hang). They pulse slower instead (`styles.css`).
   - No smooth scrolling.
6. **Loops are for waiting only,** and they stop when hidden. A `requestAnimationFrame` loop that runs for as long as a view is mounted steals frames from everything else on the overlay.

## Inventory

What moves, where it lives, how it was timed on `michael/v2-integration` (f067de5b), what was wrong, and the target. "RM" means Reduce Motion. File paths are under `app/src/renderer/src/`.

### Lesson panel (v2, `features/drawer/v2/`)

| Animation | Where | Before | Problems | Target |
|---|---|---|---|---|
| Panel slides in from the right edge | `LessonPanel.tsx` variants | x on `spring`, opacity 240 ms | Opacity literal. The dock report on every ResizeObserver tick moves the island during the slide. | `spring` + `fade.slow` |
| Panel leaves to the edge | same | x on `springOut`, opacity 200 ms after 60 ms | Literals | `springOut` + `fade.out` after a `beat` |
| Collapse into the Mini pill / grow back out | same, via `useDrawer.via` | x, y, scale toward the island's box; opacity 160 to 180 ms | Literals. The pill's box is read once per render, so a collapse that starts while the island is still springing aims at a stale box. | Same motion on tokens. Re-entering mid-collapse retargets (AnimatePresence keeps the node). |
| Body height follows its content | `AutoHeight` | `height` on `spring`, instant with RM | A size morph: the panel and everything under the body relayout every frame. | Kept as a size morph (rule 2), with `contain: layout` on the panel so nothing outside it reflows |
| Working ↔ Checking | `Work` | The button's label and spinner swap in place. The caption fades into a fixed 16 px slot. | none (fixed slot) | unchanged |
| Not yet, Hint arrive / leave | `Work`, `states.tsx` | rise 6 px, 180 ms fade in, 120 ms out (`drawer/v2/motion.ts` `rise`) | The rise was copied in three files (`drawer/v2`, `library`, `core/ui`). | `core/ui/motion` `rise` |
| A new hint rung replaces the old | `HintBox` | `popLayout`, keyed on the rung | none | `rise` |
| Not yet ring | `NotYetBox` | scale .85 → 1 on `spring`, opacity 180 ms | Literal | `pop(reduced, .85)` |
| Passed: circle, tick, words, Up next | `PassedCheck`, `PassedBody` | circle from .6 on `spring`; tick draws 240 ms after 80 ms; words +100 ms; Up next +160 ms | Literal delays, three different ones | circle `pop`, tick `draw` after a `beat`, words and Up next one and two beats later |
| Next step / Back slide | `Screens` | old out 28 px left, new in from 28 px right, opacity delayed 50 ms | Literal delay | `beat` |
| Paused (a blocking card is up) | `LessonPanel`, `Work` | opacity to .5 over 200 ms | Literal | `fade.in` |
| Code arrives over the skeleton | `StepBody.tsx` | 180 ms fade with a 4 px rise, all on one tween | The rise is a tween, not the spring. | `rise` |
| Code skeleton breathes | `CodeSkeleton` | opacity 1 → .4, 2 s loop (2.6 s with RM) | ok (waiting indicator) | unchanged |
| Tooltips | `ui.tsx` `Tip` | 120 ms in, 80 ms out | Literals | `fade.tint` / `fade.instant` |

### Island, pill and Mini (`core/Island.tsx`, `features/pill/`)

| Animation | Where | Before | Problems | Target |
|---|---|---|---|---|
| The black shape morphs between modes | `Island.tsx` | width, height and radius on `spring` (`springOut` back to pill size) | A size morph. With RM it still springs (MotionConfig doesn't cover sizes). The shadow snaps from the pill's to the card's at the start. | Size morph kept (rule 2), snaps with RM |
| Mode content crossfade | `Island.tsx` `Layer` | old out in 80 ms; new from .96 and 4 px on `spring`, fade 180 ms after 60 ms | ok, the reference for the rest | tokens (`fade.instant`, `enter(beat)`) |
| Step passed flash | `Island.tsx` | green tint 0 → .25 → 0 over 600 ms | Keyed on a counter (fine: it's a one-shot). Literal. | `ease.inOut` flash, kept |
| After a landing from the launcher | `Island.tsx` | a 700 ms timer clears `justLanded` | The timer is never cleared on unmount. | cleared |
| Text slot springs to the new width | `pill/parts.tsx` `SwapText` | `width` on `spring`; old text up 7 px in 100 ms ease-in, new from below over 240 ms after 110 ms | Size morph that still springs with RM. Ease-in exit and a third set of numbers. | `textSwap`, `sizeMove` |
| Mini title swap and "Click to reopen" | `pill/index.tsx` `Mini` | same numbers as SwapText, copied | Copied literals | `textSwap` |
| Mini press, Undo press, hover fill | `pill/index.tsx` | scale .98 and .96 on 120 ms tweens; `backgroundColor` tween | Tweened press, color animated per frame | `pressMotion`; tint as before (it's a 34 px pill, kept) |
| Passed check in the pill | `pill/parts.tsx` `StatusMark` | circle from 7/16 on `spring`; tick draws 250 ms | The draw plays with RM. | `draw(reduced)` |
| Off-track dot pulse | `StatusMark`, `core/ui/atoms.tsx`, `glass.tsx` | scale 1 → 1.35 twice over 0.9 to 1.1 s | ok with RM (scale is dropped) | tokens |
| Dot color | `StatusMark` | CSS `background-color .3s ease` | Literal CSS | 240 ms `--mg-ease-out` |

### First run and home (`features/onboarding/Intro.tsx`, `features/shell/`, `features/library/`)

| Animation | Where | Before | Problems | Target |
|---|---|---|---|---|
| Bonsai intro: tree grows, wordmark, line | `Intro.tsx` | tree scale .86 → 1 on `spring` and a cover sliding up over 1.05 s; wordmark at .95 s; line at 1.3 s | ok. Skip works mid-animation (the shared `layoutId` flies from wherever the tree is). RM shows one still frame. | unchanged (a one-time brand moment, its own timeline) |
| Tree flies into the header, strip, sidebar | `shell/flow/FlowMark.tsx`, `MARK_ID` | `layoutId` on `spring` | ok | unchanged |
| Flow → home hand-off | `shell/flow/motion.ts` | screen out 120 ms; paper out 220 ms after 100 ms; sidebar in on `spring` after 40 ms; home in after 140 ms; wordmark after 320 ms | Literals (0.22, 0.1, 0.04, 0.14, 0.32, 0.16) | `fade.slow`, multiples of `beat` |
| Strip pill slides between steps | `shell/flow/Strip.tsx` | `layoutId` on `spring`; label color CSS 180 ms | Color transition (fine on a label) | unchanged |
| Home cards rise in turn | `library/motion.tsx` | own copy of rise and stagger (35 ms, cap 8) | Copied literals | `core/ui/motion` `rise` + `staggerDelay` |
| Home ask box states | `library/Home.tsx` | `mode="wait"`, opacity on the spring | A fast typist waits on each exit. Opacity on a spring. | absolute slot (the box already reserves 112 px), `rise` |
| Home Press | `library/motion.tsx` | .97, and .98 for large tiles | Large is .96 everywhere else | `press` |
| Detail page over home | `shell/Shell.tsx` | `riseIn` | ok | unchanged |

### Everything else

Most of the other surfaces were already on the house spring for movement but typed their own fade lengths. They are moved onto the tokens without changing what they do. Structural problems found there:

| Surface | Problem | Status |
|---|---|---|
| Launcher (`features/launcher/Launcher.tsx`) | Grows out of the island by animating width, height, a four-layer `box-shadow` and `background-color` on a 640 px box. Sections are keyed per view with no exit, so typing flashes the body empty while its height springs. | Shadow and color: crossfade layers instead (rule 2). Size morph kept. Section swap: follow-up. |
| Settings sheet (`features/settings/Settings.tsx`) | Same morph from a 300 x 34 pill to 912 x 576 with `box-shadow` per frame | Same as the launcher |
| Diagram flyout (`features/diagrams/Firing.tsx`, `NeuralNet.tsx`) | `setState` on every animation frame for as long as the flyout is open, re-rendering the whole SVG, even after train mode holds its last frame | Loop stops when hidden or settled |
| Diagram draws (`Graph.tsx`, `Heatmap.tsx`, `Diagram.tsx`, `cards/Curve.tsx`) | `pathLength` and `clip-path` draws play with RM. Keyed remounts redraw the whole graph on any data change. | `draw(reduced)`; remount keys: follow-up |
| Spotlight (`features/spotlight/Spotlight.tsx`) | The hole moves by rewriting SVG mask rects every frame (a full-screen repaint). The caption is placed from a guessed size and slides again once measured. | Follow-up (needs a transform-based hole) |
| Loupe (`features/loupe/index.tsx`) | Keyed by the target's rounded position, so every move remounts it and the callout regrows. | Key by target identity |
| Video-lesson drawer, player, shortcut bar (`drawer/Drawer.tsx`, `player/`, `shortcut-bar/`) | Live only for video lessons. Step change pops the detail open with no height animation, the bar's tiles widen and shift the bar, presses are .94 tweens, the volume slider animates width. | Presses and literals onto tokens; the reflows are follow-ups |
| Tips (`features/tips/index.tsx`) | Positions with `left` / `top` from a polling loop | Follow-up |
| Complete panel (`features/complete/Panel.tsx`) | Rises 8 px at 40 ms; the Skills block reflows 1.4 s after the entrance | Tokens; the reflow is a follow-up |

## Measurements

Method: headless Chrome (`--headless=new`) over the DevTools protocol against the browser stage (`npm run dev:web`), 1440 x 900, the `lesson-panel` and `onboarding` scenarios. Each scenario is driven through the app's own stores (the same calls a click makes), three times for timing and once more for geometry. Per run:

- **frame p95 / max**: requestAnimationFrame intervals. Headless Chrome runs its frames uncapped at about 6 ms, so **miss60** counts intervals over 25 ms (a dropped frame at 60 Hz) and **miss120** over 12.5 ms (a dropped frame on a 120 Hz ProMotion display).
- **work p95**: main-thread time per frame, from the frame's rAF to the end of its rendering (a MessageChannel task posted from rAF).
- **layouts, layout ms, style ms**: `Performance.getMetrics` deltas over the scenario.
- **shifts**: `layout-shift` entries (something moved by layout, not by transform).
- **4x CPU** runs the same with `Emulation.setCPUThrottlingRate(4)`, a stand-in for a slow laptop.
- **Reduce Motion** runs with `prefers-reduced-motion: reduce` emulated and reports how far the panel travelled.

- **React commits / panel renders**: commits during the scenario, and how many of them re-rendered `LessonPanel` (a small devtools hook counts fibers whose props or state changed).

The bench lives outside the repo (it drives a local Chrome). It runs against the Vite dev server, so React is the development build and the absolute times are pessimistic; compare before with after, not with a shipped build. Frame p95 is noisy in headless Chrome (its frame cadence moves between 6 and 12 ms with machine load), so the table leaves it out. The numbers are medians of three.

### Before (`michael/v2-integration` at f067de5b)

| Scenario | miss60 | miss120 | max frame | work p95 | layouts | 4x: miss60 | 4x: max frame | React commits | panel renders |
|---|---|---|---|---|---|---|---|---|---|
| panel-edge-in | 1 | 3 | 47 ms | 10.6 ms | 73 | 5 | 660 ms | 36 | 21 |
| panel-edge-out | 0 | 0 | 12 ms | 3.5 ms | 68 | 8 | 121 ms | 67 | 0 |
| mini-collapse | 1 | 1 | 42 ms | 1.1 ms | 70 | 4 | 532 ms | 7 | 2 |
| mini-reopen | 1 | 4 | 67 ms | 9.7 ms | 84 | 7 | 859 ms | 39 | 23 |
| mini-interrupt | 5 | 8 | 55 ms | 1.7 ms | 106 | 8 | 661 ms | 35 | 22 |
| check-notyet | 0 | 11 | 24 ms | 9.3 ms | 152 | 15 | 467 ms | 80 | 64 |
| hint-open | 0 | 4 | 24 ms | 10.8 ms | 58 | 8 | 291 ms | 49 | 48 |
| hint-close | 0 | 1 | 14 ms | 10.9 ms | 62 | 5 | 200 ms | 57 | 55 |
| hint-interrupt | 1 | 6 | 30 ms | 12.3 ms | 85 | 13 | 273 ms | 90 | 86 |
| passed | 3 | 9 | 48 ms | 11.7 ms | 79 | 7 | 279 ms | 54 | 48 |
| next-step | 6 | 9 | 55 ms | 11.6 ms | 52 | 6 | 339 ms | 65 | 61 |
| intro | 0 | 2 | 24 ms | 0.8 ms | 72 | 9 | 297 ms | 10 | 0 |
| flow-to-home | 4 | 9 | 97 ms | 1.5 ms | 139 | 10 | 1091 ms | 18 | 0 |

What the numbers showed:

- **The panel re-renders itself on every frame of its own animations.** `LessonPanel` reports its height to the dock (`setDock`) from a ResizeObserver on the card. While the body's height springs, the card resizes every frame, so the dock gets a new rect every frame. The dock re-renders `PanelLayer`, which re-renders the whole panel (every tile, keycap and code line), and the island re-places itself and publishes a new box, which re-renders the panel again. That's 48 to 86 full-panel renders for one hint, check or Next step. At 4x CPU that is what stretches frames to 200 to 470 ms.
- **The first frame after a reopen or slide-in stalls** (47 to 67 ms, and 530 to 860 ms at 4x). That's the panel's mount plus the same render loop.
- **Interrupts were already safe for the panel.** Every interrupt scenario ended with the panel fully shown, opacity 1 and no transform left over, because `AnimatePresence` re-enters a leaving node instead of remounting it.
- **Reduce Motion was mostly honored.** With it emulated the panel never travelled (0 px in every scenario), the body height and the island's size snapped, and the bonsai's shared-element flights snapped. The gaps are the stroke draws (the pill's passed tick, diagram lines, the Curve) and the launcher's height.

<!-- AFTER -->

## Not verified on Windows

The browser stage can't show these. They need Michael's Mac:

- The Electron overlay itself (Smart App Control blocks the unsigned `electron.exe` on Adrian's laptop).
- System Settings → Accessibility → Display → Reduce motion, toggled while the app is open. Chromium should pick it up live through `prefers-reduced-motion`.
- A 120 Hz ProMotion display. The springs are time-based, so they should look the same, but frames over 8.3 ms show there first.
- The notch: the island growing out of it, and the Mini pill collapsing back into it at the real menu-bar height.
- Native vibrancy behind the panel and the launcher while they move.

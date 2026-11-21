# Motion

Piece 3 of Michael's Nov 21 email. Adrian owns it (branch `adrian/motion`, stacked on `michael/v2-integration`). The goal is every animation smooth and consistent: one set of springs, no dropped frames, no layout jumps, safe to interrupt, and Reduce Motion respected.

This file is the spec. In code, the numbers live in `app/src/renderer/src/core/ui/motionTokens.ts` (plain values, so the main process can compile them) and the helpers in `core/ui/motion.ts`, which re-exports the tokens. Import from `core/ui/motion`. `core/theme.ts` re-exports the tokens too, so older imports keep working.

## The vocabulary

| Token | Value | Use |
|---|---|---|
| `spring` | stiffness 420, damping 34, mass 0.9 | Anything that moves, scales or morphs. About 90% of the way in 0.13 s, settled in about 0.35 s, with a hair of overshoot. |
| `springOut` | stiffness 420, damping 38, mass 0.9 | Leaving and collapsing. Same speed, critically damped, so nothing that goes away bounces. |
| `fade.in` | 180 ms, `ease.out` | Opacity arriving. |
| `fade.out` | 120 ms, `ease.out` | Opacity leaving. Always quicker than arriving, so two states never sit on top of each other. |
| `fade.slow` | 240 ms, `ease.out` | A big surface's opacity (a panel, a window layer). |
| `fade.tint` | 120 ms, `ease.out` | Hover tint layers and fills (`.mg-press`). |
| `fade.press` | 40 ms | The pressed tint (`.mg-press:active`). |
| `fade.instant` | 80 ms | A layer swapped out under a morph. |
| `duration.draw` | 400 ms, `ease.out` | A diagram line or a chart drawing itself (through `draw()`). |
| `beat` | 60 ms | One step of a sequence: content after its frame, a tick after its circle. Two beats is the longest anything waits on screen. |
| `press` | scale .97 (.96 for big tiles) on `spring` | Every pressable thing. Never below .95, never a tween. |
| `stagger` | 35 ms apart, 6 px rise, capped at 8 | Lists that arrive together. Child 9 and on arrive with child 8. |
| `ease.out` | `cubic-bezier(.23, 1, .32, 1)` | The only curve for enters and exits. `ease.inOut` only for a there-and-back flash or a loop. |
| `twoBeats` | scale 1 → 1.35 twice in 1 s, `ease.inOut` | The off-track dot's pulse. |
| Loops | dots 1.2 s, skeleton 2 s, spinner 1 s (CSS) | Only waiting indicators loop. They stop when their wait ends. |

Helpers in `core/ui/motion.ts`: `enter(delay)` (move on the spring, fade on its own clock), `rise(reduced, { y, delay })`, `riseIn`, `staggerList` and `riseItem`, `staggerDelay(i)`, `textSwap`, `draw(reduced, { delay, length, opacity })` for stroke draws, `pop(reduced, from)` for glyphs, `pressMotion(disabled, large)`, `sizeMove(reduced)` for width and height morphs, and `prefersReduced()` for code that can't call the hook.

## Rules

1. **Move on the spring, fade on a tween.** A spring on opacity reads as a lag, and a tween on movement can't be retargeted with its velocity. `enter()` gives both at once.
2. **Transform and opacity only.** Never animate `top`, `left`, margins, padding, `box-shadow`, `filter`, `background-color` or `color` per frame. A hover color is an opacity layer (`.mg-press`), and a shadow change is a crossfade.
   The one exception is a **size morph**: the island's width and height, the lesson panel's body height, the launcher's and settings sheet's grow out of the island, and the pill's text slot. These boxes have to change their real size because other things read them (the dock, click-through bounds and the engine's `overlay.bounds`). Each is a clipped box with a small subtree, so its layout per frame is cheap (well under a millisecond in the tables below). What made them expensive was React, not layout (rule 7). With Reduce Motion a size morph snaps (`sizeMove`).
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
7. **React stays out of the frame loop.** An animation must never feed back into React state on every frame (a ResizeObserver on something that is springing, calling `setState` or a store setter). Publish where a thing is going, not where it is passing through, and make setters ignore values that didn't change. This was the biggest source of dropped frames (see Measurements).

## Inventory

What moves, where it lives, how it was timed on `michael/v2-integration` (f067de5b), what was wrong, and the target. "RM" means Reduce Motion. File paths are under `app/src/renderer/src/`.

### Lesson panel (v2, `features/drawer/v2/`)

| Animation | Where | Before | Problems | Target |
|---|---|---|---|---|
| Panel slides in from the right edge | `LessonPanel.tsx` variants | x on `spring`, opacity 240 ms | Opacity literal. The first frame stalls on the panel's mount (see Measurements). | `spring` + `fade.slow`. The mount stall is a follow-up. |
| Panel leaves to the edge | same | x on `springOut`, opacity 200 ms after 60 ms | Literals | `springOut` + `fade.out` after a `beat` |
| Collapse into the Mini pill / grow back out | same, via `useDrawer.via` | x, y, scale toward the island's box; opacity 160 to 180 ms | Literals. The panel subscribed to the whole island box (a re-render on every island move) and aimed at the box from its last render. | Same motion on tokens. The pill's box is read when the motion starts (`islandBoxNow`). Re-entering mid-collapse retargets (AnimatePresence keeps the node). |
| Body height follows its content | `AutoHeight` | `height` on `spring`, instant with RM | A size morph, and the panel reported every frame of it to the dock, which re-rendered the whole panel and moved the island (rule 7) | Kept as a size morph (rule 2). The dock hears the height the body is springing to, once. |
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
| The black shape morphs between modes | `Island.tsx` | width, height and radius on `spring` (`springOut` back to pill size) | A size morph. It measured its content every frame while the pill's text slot sprang, so it re-rendered and re-aimed its own spring every frame (rule 7). The shadow snaps from the pill's to the card's at the start. | Measures at the slot's target width (`data-swap-w`), so it springs once. Snaps with RM. The shadow snap is a follow-up. |
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
| Launcher (`features/launcher/Launcher.tsx`) | Grows out of the island by animating width, height, a four-layer `box-shadow` and `background-color` on a 640 px box. Its height kept springing with RM. Sections are keyed per view with no exit, so typing flashes the body empty while its height springs. | Done: timings on tokens, height snaps with RM. Follow-up: shadow and color as crossfaded layers, the section swap. |
| Settings sheet (`features/settings/Settings.tsx`) | Same morph from a 300 x 34 pill to 912 x 576 with `box-shadow` per frame | Done: timings on tokens. Follow-up: the shadow, as for the launcher. |
| Diagram flyout (`features/diagrams/Firing.tsx`, `NeuralNet.tsx`) | `setState` on every animation frame for as long as the flyout is open, re-rendering the whole SVG, even after train mode holds its last frame | Follow-up: drive the SVG from motion values instead of React state. It's a deliberate looping visualization (mockup 11), so it needs a rewrite, not a timing change. |
| Diagram draws (`Graph.tsx`, `Heatmap.tsx`, `Diagram.tsx`, `cards/Curve.tsx`) | `pathLength` and `clip-path` draws play with RM. Nodes grew from scale 0 on a tween. Keyed remounts redraw the whole graph on any data change. | Done: `draw()` (a fade with RM), the heatmap sweep fades with RM, nodes grow from .6 on the spring. Follow-up: remount keys. |
| Spotlight (`features/spotlight/Spotlight.tsx`) | The hole moves by rewriting SVG mask rects every frame (a full-screen repaint). The caption is placed from a guessed size and slides again once measured. | Done: timings on tokens. Follow-up: a transform-based hole. |
| Loupe (`features/loupe/index.tsx`) | Keyed by the target's rounded position, so every move remounts it and the callout regrows. | Done: a move under 96 px keeps the callout and it springs there. |
| Video-lesson drawer, player, shortcut bar (`drawer/Drawer.tsx`, `player/`, `shortcut-bar/`) | Live only for video lessons. Step change pops the detail open with no height animation, the bar's tiles widen and shift the bar, presses are .94 tweens, the volume slider animates width, the chapter list smooth-scrolls with RM. | Done: presses on the spring at .97, literals on tokens, no smooth scroll or slider growth with RM. Follow-up: the reflows. |
| Tips (`features/tips/index.tsx`) | Positions with `left` / `top` from a polling loop | Follow-up |
| Complete panel (`features/complete/Panel.tsx`) | Rises 8 px at 40 ms; the Skills block reflows 1.4 s after the entrance | Done: fades on tokens. Follow-up: the 8 px rise and the reflow. |

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

### After (`adrian/motion`)

The first runs of the finished branch looked worse on max frame in scenarios this branch barely touched (the intro moved from 24 to 54 ms), and the machine was busy with other sessions' builds. So the comparison below serves both versions at once (the baseline commit on one Vite server, this branch on another) and alternates them inside every repetition, so they share the same machine load. Five repetitions each, medians, before → after.

| Scenario | miss60 | miss120 | work p95 (ms) | React commits | panel renders |
|---|---|---|---|---|---|
| panel-edge-in | 5 â†’ 1 | 7 â†’ 1 | 6.4 â†’ 1.7 | 22 â†’ 7 | 15 â†’ 2 |
| panel-edge-out | 2 â†’ 1 | 3 â†’ 4 | 10.8 â†’ 7.1 | 44 â†’ 28 | 0 â†’ 0 |
| mini-collapse | 1 â†’ 1 | 4 â†’ 5 | 1.7 â†’ 1.5 | 7 â†’ 7 | 2 â†’ 0 |
| mini-reopen | 5 â†’ 1 | 7 â†’ 2 | 7.0 â†’ 1.2 | 26 â†’ 8 | 17 â†’ 2 |
| mini-interrupt | 6 â†’ 6 | 7 â†’ 7 | 2.1 â†’ 5.3 | 30 â†’ 32 | 19 â†’ 3 |
| check-notyet | 14 â†’ 4 | 19 â†’ 7 | 8.1 â†’ 1.7 | 44 â†’ 19 | 36 â†’ 9 |
| hint-open | 6 â†’ 2 | 19 â†’ 4 | 19.3 â†’ 1.5 | 30 â†’ 8 | 29 â†’ 6 |
| hint-close | 1 â†’ 1 | 10 â†’ 2 | 15.4 â†’ 0.9 | 47 â†’ 3 | 45 â†’ 2 |
| hint-interrupt | 8 â†’ 4 | 28 â†’ 7 | 22.6 â†’ 1.9 | 51 â†’ 11 | 48 â†’ 8 |
| passed | 7 â†’ 3 | 10 â†’ 4 | 15.6 â†’ 2.1 | 26 â†’ 12 | 23 â†’ 5 |
| next-step | 7 â†’ 1 | 9 â†’ 2 | 18.7 â†’ 2.3 | 28 â†’ 8 | 27 â†’ 2 |
| intro | 3 â†’ 2 | 6 â†’ 7 | 1.2 â†’ 1.3 | 10 â†’ 10 | 0 â†’ 0 |
| flow-to-home | 10 â†’ 10 | 15 â†’ 13 | 2.5 â†’ 2.7 | 18 â†’ 18 | 0 â†’ 0 |
| next-back-interrupt | 7 â†’ 1 | 7 â†’ 3 | 9.2 â†’ 1.5 | 51 â†’ 14 | 48 â†’ 6 |

At 4x CPU (the same interleaving, three repetitions, the panel scenarios):

| Scenario (4x CPU) | miss60 | work p95 (ms) | max frame (ms) |
|---|---|---|---|
| panel-edge-in | 5 → 6 | 419.4 → 7.6 | 1012 → 709 |
| mini-reopen | 5 → 7 | 528.9 → 6.5 | 1630 → 907 |
| check-notyet | 17 → 22 | 297.3 → 48.2 | 497 → 564 |
| hint-open | 12 → 10 | 35.1 → 10.3 | 236 → 533 |
| hint-close | 6 → 2 | 105.7 → 4.0 | 133 → 133 |
| passed | 7 → 6 | 6.1 → 5.7 | 273 → 345 |
| next-step | 7 → 6 | 7.0 → 5.6 | 243 → 370 |
| next-back-interrupt | 5 → 4 | 2.9 → 4.1 | 333 → 320 |

On a slow machine the per-frame work still drops by an order of magnitude, but the dropped-frame counts barely move: what's left is the panel's mount in the first frame (follow-up 1) and the layout of the size morphs, both of which grow with the CPU slowdown. This branch fixes the 60 Hz story on a normal machine; the slow-machine one needs the mount fix.

What changed, in numbers:

- **The re-render loop is gone.** `LessonPanel` renders during a hint, a check, Passed or Next step dropped from 23 to 48 to 2 to 9. The main-thread work per frame (p95) dropped from 6 to 23 ms to 1 to 2 ms.
- **Fewer dropped frames where it matters.** At 60 Hz: check 14 → 4, Next step 7 → 1, reopen from the Mini pill 5 → 1, slide-in 5 → 1, Passed 7 → 3, hint 6 → 2. At 120 Hz the hint went from 19 misses to 4 and the hint interrupt from 28 to 7.
- **Interrupts end clean.** Every interrupt scenario (Mini collapse/reopen five times in 600 ms, close a hint and ask again at once, Next step then Back twice inside 160 ms) ends with exactly one screen, opacity 1, no transform left over, and the right view.
- **Unchanged:** the intro and the flow → home hand-off (their misses come from mounting the shell and home, not from motion), Mini collapse, and the Mini interrupt (the island and pill rows re-render on each real mode change). Layout passes went up slightly (the island and panel now lay out on their own frames instead of inside React's renders); layout time stayed under 15 ms over each whole scenario.

### Reduce Motion (after)

With `prefers-reduced-motion: reduce` emulated, the panel, its body and the keys row never travel in any scenario (0 px). The body's height, the island's size and the bonsai's shared-element flights snap in one frame. Stroke draws fade. Opacity changes stay. Waiting indicators keep pulsing (slower).

## Follow-ups

Found and measured here, not done in this branch:

1. **The panel's first frame.** Sliding in or growing out of the Mini pill mounts the whole panel in the animation's first frame: 47 to 91 ms at normal speed in the dev build. Keeping the panel mounted (hidden and inert) while collapsed would remove it, but it touches the Enter-key and focus handling the bug-hunt branch owns.
2. **The island's shadow** snaps from the pill's to the card's when a card opens. A crossfade between two shadow layers would fix it.
3. **Launcher and settings sheet morphs** animate `box-shadow` and `background-color` every frame on a large box. Same crossfade.
4. **Diagram flyout** (`Firing.tsx`, `NeuralNet.tsx`): a React render of the whole SVG on every frame while it is open. Drive it from motion values instead.
5. **Spotlight**: the hole is moved by rewriting SVG mask rects every frame, a full-screen repaint.
6. **Panel slide-out still re-renders the island** about 28 times (the island re-places itself as the dock frees up).
7. Legacy video-lesson reflows (drawer step change, shortcut bar label widths), tips positioning by `left`/`top`, the complete panel's late reflow.

Hand-typed timings left in the app: 47, down from 266. They are loop periods (spinner, skeleton, waiting shimmer), the intro's own 2.5 s timeline, and `duration: 0` snaps.


## Not verified on Windows

The browser stage can't show these. They need Michael's Mac:

- The Electron overlay itself (Smart App Control blocks the unsigned `electron.exe` on Adrian's laptop).
- System Settings → Accessibility → Display → Reduce motion, toggled while the app is open. Chromium should pick it up live through `prefers-reduced-motion`.
- A 120 Hz ProMotion display. The springs are time-based, so they should look the same, but frames over 8.3 ms show there first.
- The notch: the island growing out of it, and the Mini pill collapsing back into it at the real menu-bar height.
- Native vibrancy behind the panel and the launcher while they move.

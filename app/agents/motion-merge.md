# motion-merge

**Status:** merged and reviewed on `michael/app-motion-merge` (from `michael/v2-integration` + `adrian/motion`, PR #208).
Typecheck green, app tests 98/98, brand lint clean on the whole diff against `michael/v2-integration`. Stage and
Electron not run (offline lane, no windows). Adrian's branch is untouched; this branch is what PR #208 looks like once
the Nov 21 lanes (island-close, login-first, fresh-start, video-quiet, theme, home, setup) are under it.

## What was merged
`adrian/motion`: one token set (`core/ui/motionTokens.ts`, helpers in `core/ui/motion.ts`, re-exported by
`core/theme.ts`), the spec `docs/MOTION.md`, the lesson panel and island no longer re-rendering on every frame
(the dock gets the height the body springs to; `useIslandBox(select)` and `islandBoxNow()`), Reduce Motion for size
morphs, stroke draws and smooth scroll, the loupe keyed by target, and every surface moved onto the tokens.

## Conflicts and how they were resolved (both intents kept)
| File | HEAD (lanes) | adrian/motion | Result |
|---|---|---|---|
| `core/Island.tsx` imports | `perf`, `islandSizeFor`, motion tokens from theme | tokens from `core/ui/motion` | both: `perf` + `islandSize` kept, tokens from `core/ui/motion` |
| `core/Island.tsx` size measure | island-close: `apply()` via `islandSizeFor(fixed, layerEmpty, m, pillW)`, `sized` | `data-swap-w` pre-measure (spring once with the text slot), old "0 never wins" rule | island-close rules kept as the only size rule; the swap pre-measure feeds `apply()` and only for a pill (or an empty layer), never a card |
| `core/Island.tsx` size transition | `landing \|\| !sized ? {duration:0} : spring` | `landing \|\| reduced ? instant : spring` | `landing \|\| !sized ? instant : sizeMove(reduced, spring/springOut)` |
| `core/Island.tsx` `Layer` | island-close: empty / unstick checks, local `fade()` | `fade.in`, `beat`, `fade.instant` tokens | tokens; the local `fade()` renamed `unstick()` (it shadowed the `fade` token inside the effect) |
| `core/theme.ts` | theme lane: `layer`, `tone`, `toneFor` after the old motion tokens | old tokens removed, re-exported from motionTokens | re-export kept; old `duration` / `ease` / `press` / `stagger` copies dropped; `layer` / `tone` kept |
| `library/Home.tsx` | home lane: new ask block (one fixed 36 px row, tone chips) | token swap + `popLayout` on the old three-state block | home lane's block kept (it has no `mode="wait"`); send button on `press.scale` + `enter()` |
| `onboarding/Guided.tsx` | setup lane: `Dots`, `StepBars` removed | `StepBars` on tokens | `Dots` kept; its fade on `fade.slow` |
| `onboarding/Ready.tsx` | setup lane: tour screen | token swap on the old rows screen | setup lane's screen kept (already variants-based) |
| `diagrams/Heatmap.tsx` | theme lane: `rawThumb` ramp, `useAppearance` | Reduce Motion fade for the sweep | both |
| `styles.css` | `.mg-lift` reduced-motion rule | no smooth scroll with Reduce Motion | both |

## Follow-up fixes (commit "lanes that landed after PR #208 ...")
Lanes merged after Adrian's base (f067de5b) added motion that PR #208 never saw:
- `onboarding/Dots.tsx`: the current dot's width spring did not snap with Reduce Motion. Now `sizeMove(reduced)`.
- `core/ui/atoms.tsx` `ProgressRing`: `pathLength` on the spring played with Reduce Motion. Now snaps.
- `tips/TourLayer.tsx` sample panel: opacity was on the spring (rule 1). Now `enter(0, fade.slow)` in, `springOut` + `fade.out` out.
- `cards/index.tsx` `Swap`: the 4 px rise was a tween with a literal 60 ms delay. Now `enter(beat)`.

## Review
- **Typecheck:** green (`npm run typecheck`).
- **App tests:** 98/98 (`node --import tsx --import ./test/setup.mjs --test --test-force-exit test/*.test.ts`), including
  `test/islandSize.test.ts`. One earlier full run hung in `test/cloudLink.test.ts` for 10+ minutes while other agents
  were running the same suite; it passes alone (14/14, 0.15 s) and in two later full runs. Not touched by this merge.
- **Checks:** `island-sync.check.ts` ok, `freshStart.check.ts` 755/0. `loginFirst.check.ts` FAILS on
  `index.ts:336 overlay.showInactive outside a gate guard` (`hideLauncher`). Pre-existing: `src/main` is identical to
  `origin/michael/v2-integration` on this branch.
- **Brand lint (whole diff vs v2-integration):** no hex outside theme.ts / styles.css, no "Cursor", no
  `dangerouslySetInnerHTML`, no em dashes, no capitalised product name in copy, nothing defaults to Opus. No copy changed.
- **Reduce Motion:** `MotionConfig reducedMotion="user"` (main.tsx) covers transforms; size morphs (island, panel body,
  pill text slot, launcher row, Dots), stroke draws (`draw`, StatusGlyph, GlassCheck, ProgressRing, Graph), the heatmap
  sweep and smooth scroll are handled by the helpers. Waiting loops slow down instead of freezing (styles.css).
- **No lesson-specific UI:** nothing in the diff keys on a lesson id, title, video or tool (grep of the added lines).
- **Island fix (island-close) not regressed:** size still comes only from `islandSizeFor` (pill-tall pill, empty card
  falls back to the pill, layer never found falls back to the pill); hover drop after a held card closes and on
  `dismiss` untouched; `data-hit` off and `pointer-events-none` while yielded untouched; `Boundary retryMs` + `RestingPill`
  fallback untouched. The only new input is the swap pre-measure, which can only change a pill's width to the width its
  text slot is already springing to. Checked by reading and by `test/islandSize.test.ts`; not re-run in the stage.

## Open, not changed here
- `docs/MOTION.md` still has `<!-- AFTER -->` where the after-measurements go: Adrian's bench (outside the repo) was not
  re-run on the merged branch.
- `AnimatePresence mode="wait"` remains in Login, AccountSheet, AccountWindow, settings Shell, Illustration, Guided's
  status glyph, the video drawer and (new) `tips/TourLayer.tsx` coach marks. Adrian's PR left the older ones on purpose
  or as follow-ups; the tour's is new since his base.
- The follow-ups listed in MOTION.md (spotlight hole, tips positioning, launcher section swap, diagram remount keys,
  complete panel reflow) are still open.
- No unit test covers the swap pre-measure (it lives inside the component).

## Core request
Adrian: three small core edits ride on this branch besides your own PR.
1. `core/Island.tsx`: the conflict resolution above (island-close size rules + your swap pre-measure and `sizeMove`), and
   `Layer`'s local `fade()` renamed `unstick()`.
2. `core/theme.ts`: the theme lane's `layer` / `tone` tokens kept under your re-export; the duplicate motion tokens dropped.
3. `core/ui/atoms.tsx` `ProgressRing`: `transition={sizeMove(reduce, spring)}` so the arc snaps with Reduce Motion.

## Not verified
Electron and the stage (offline lane, no windows): the real Reduce Motion toggle, 120 Hz, the notch, vibrancy, and the
island's X on a real card (the merged logic matches island-close's, which was checked in the stage on its own branch).

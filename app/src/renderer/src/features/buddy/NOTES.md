# buddy (bon): notes and hand-offs

## annotate-yields-to-buddy.patch: NOT applied here (hand-off)

Adrian sent `27-buddy-mockups-b-annotate-yields-to-buddy.patch` (Nov 24, about 15 lines, in
`miyagi-v2/adrian-emails-2026-11-22/files/`). It makes `features/annotate`'s BuddyLayer draw nothing when the buddy
feature has a `buddy` overlay layer, so a mark is circled once (the old drawing moves into a `Strokes` component).

The v4-bon lane did not apply it: buddy drawing (features/annotate, buddy-draw) is owned by another session. Whoever owns
buddy-draw should apply or redo it there. Today the buddy side already yields the other way (Reach.tsx draws nothing
while features/annotate is mounted), so nothing is drawn twice in the meantime. Also from Adrian with it: the engine's
`holdMs` should be longer than 6 s, and the loop color should follow bon's color (skin.ts).

## bon's count from the engine (v4-bon)

- `engine.ts` reads the engine's passed-step counter and hands it to `growth.ts` `syncSteps`. The ui-v4 contract
  (`shared/contracts/UI-V4.md`, `contract: ui-v4 ...`) was not on `origin/michael/app-ui-v4` yet, so `passedOf` reads
  a local typed placeholder (`EngineBon`: `bon.passed`, `activity.stepsPassed`, `stepsPassed`, `passedSteps`, or a
  `passedTotal` on `step.passed`). When the contract lands, keep only its field in `passedOf`.
- The engine's count never lowers the one shown (max of the two), and a sync is quiet: the level-up moment plays only on
  a live `step.passed` that is not skipped and not `already` (wire.ts).
- The localStorage count (`miyagi.buddy.growth`) stays as the fallback for an engine that sends no count.

## The living bonsai in the notch

The pill's notch modes (idle, compact, building) pass `Left: BonEar` (features/pill/index.tsx), which is `<Buddy />`:
the brand tree, in color, swaying while the engine thinks, blooming on a pass, leaning toward what bon points at.
core/Island.tsx's own default stays the static MiyagiMark (core; other modes without a Left still get it).

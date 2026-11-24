# buddy (bon): notes and hand-offs

## annotate-yields-to-buddy.patch: NOT applied here (hand-off)

Adrian sent `27-buddy-mockups-b-annotate-yields-to-buddy.patch` (Nov 24, about 15 lines, in
`miyagi-v2/adrian-emails-2026-11-22/files/`). It makes `features/annotate`'s BuddyLayer draw nothing when the buddy
feature has a `buddy` overlay layer, so a mark is circled once (the old drawing moves into a `Strokes` component).

The v4-bon lane did not apply it: buddy drawing (features/annotate, buddy-draw) is owned by another session. Whoever owns
buddy-draw should apply or redo it there. Today the buddy side already yields the other way (Reach.tsx draws nothing
while features/annotate is mounted), so nothing is drawn twice in the meantime. Also from Adrian with it: the engine's
`holdMs` should be longer than 6 s, and the loop color should follow bon's color (skin.ts).

## bon's count from the engine (v4-bon, ui-v4 contract)

- `engine.ts` (pure, `createBonLink`) is wired in `wire.ts`. On every `engine.hello`: `bon.import {steps, seen}` once per
  Mac (the localStorage count, flag `miyagi.buddy.imported`; the engine keeps the larger), then `bon.get {}`. Each only
  when the hello lists it (`shared/contracts/UI-V4.md` section 2); an older engine gets neither.
- Every `bon` message (`BonState`): `syncSteps(steps)`. The engine's count never lowers the one shown (max of the two),
  and a sync is quiet. A window that opens mid-session misses the hello but follows the count through localStorage.
- `step.passed`: a ui-v4 pass (it carries `counted`, or the hello listed `bon.get` and it carries `key`) grows bon only
  when `counted: true`, under the engine's `key`. Any other pass (older engine, pre-ui-v4 scenarios: the mock's default
  hello lists every V2 command) counts locally when not skipped and not `already`: the fallback. The level-up moment
  plays on that pass (wire.ts), not on `bon.grew`, so it plays once.
- Open: after `data.delete progress` the engine's count drops but the max rule keeps the local one shown.
- Stage: `?scenario=ui-v4` (bon.get answers 24 Sapling; "Can I move on?" passes s3 counted, Budding) and
  `?scenario=buddy` (bon.get answers 14; a counted pass levels up to Sapling, the same key again does not count).

## The living bonsai in the notch

The pill's notch modes (idle, compact, building) pass `Left: BonEar` (features/pill/index.tsx), which is `<Buddy />`:
the brand tree, in color, swaying while the engine thinks, blooming on a pass, leaning toward what bon points at.
core/Island.tsx's own default stays the static MiyagiMark (core; other modes without a Left still get it).

# buddy (bon): notes and hand-offs

## bon draws the marks (michael/bon-full, Nov 24)

- Adrian's `27-buddy-mockups-b-annotate-yields-to-buddy.patch` is applied as sent: `features/annotate`'s BuddyLayer draws
  nothing while this feature has its `buddy` layer (its old drawing is the `Strokes` component), and it registers with
  `yieldsToBuddy: true`, so marks.ts standsDown lets bon draw. One stroke per mark, bon's, in bon's color (skin.ts).
- The step's target: every new spotlight box (the engine's `spotlight` target, the same source features/annotate read)
  is a mark (pointing.ts spotlit, wired in wire.ts). bon flies there, sits on its left (the spotlight's caption has the
  right) and now also throws its loop round it in its color (Reach.tsx no longer skips bridged marks).
- The engine's own `annotate` marks (today a circle-to-ask answer) win while they are up; when they are gone the
  spotlight boxes are marked again (before, one annotate stopped the spotlight pointing for the rest of the session).
- Hold: a spotlight mark stays SPOT_HOLD_MS (10 s) from its birth. A video lesson's calm spotlight dims away after 4 s
  (spotlight/calm.ts); bon keeps pointing past that, and only an engine `spotlight {clear: true}` takes its mark at once.
  The engine's own annotate holdMs went from 6 s to 10 s (server/coach/circle.py, fast_ask.py,
  orchestrator/circle_ask.py; claude/eng-bon-hold into integration/live).

## bon's count from the engine (v4-bon, ui-v4 contract)

- `engine.ts` (pure, `createBonLink`) is wired in `wire.ts`. On every `engine.hello`: `bon.import {steps, seen}` once per
  Mac (the localStorage count, flag `miyagi.buddy.imported`; the engine keeps the larger), then `bon.get {}`. Each only
  when the hello lists it (`shared/contracts/UI-V4.md` section 2); an older engine gets neither.
- Every `bon` message (`BonState`): `syncSteps(steps)`, quiet. A window that opens mid-session misses the hello but follows the count through localStorage.
- `step.passed`: a ui-v4 pass (it carries `counted`, or the hello listed `bon.get` and it carries `key`) grows bon only
  when `counted: true`, under the engine's `key`. Any other pass (older engine, pre-ui-v4 scenarios: the mock's default
  hello lists every V2 command) counts locally when not skipped and not `already`: the fallback. The level-up moment
  plays on that pass (wire.ts), not on `bon.grew`, so it plays once.
- Delete progress: the engine's count is followed down too (growth.ts sync), so after `data.delete progress` (the engine
  pushes the empty `bon`) bon shrinks, and the passes remembered here are forgotten with it. Only the first answer after
  this window's bon.import keeps the larger count (engine.ts), as the engine does on import.
- Stage: `?scenario=ui-v4` (bon.get answers 24 Sapling; "Can I move on?" passes s3 counted, Budding) and
  `?scenario=buddy` (its own engine.hello at 50 ms, so bon.get is sent and answers 14; a counted pass levels up to
  Sapling, the same key again does not count; `data.delete` answers the empty `bon`, bon back to Seed).
- Check: `~/miyagi/tools/playwright/bon-full.mjs <port> <shots dir>` (shots `app/agents/shots/bon-full-*.png`) and
  `bon-hold.mjs` (how long bon holds a spotlight target).

## The living bonsai in the notch

The pill's notch modes (idle, compact, building) pass `Left: BonEar` (features/pill/index.tsx), which is `<Buddy />`:
the brand tree, in color, swaying while the engine thinks, blooming on a pass, leaning toward what bon points at.
core/Island.tsx's own default stays the static MiyagiMark (core; other modes without a Left still get it).

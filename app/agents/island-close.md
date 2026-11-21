# island-close

**Status:** fix done on `michael/app-island-close` (from `michael/v2-integration`). Typecheck green, unit tests green
(`test/islandSize.test.ts`), brand lint clean on the diff. Reproduced and re-checked in the browser stage (lesson-panel,
a text lesson; no video). Not run in Electron.

## Michael's repro (Nov 21)
Drawer / lesson panel open, Esc (or its hide key) plus a click closed the side surfaces and the top island EXPANDED;
its X then left a big empty black rectangle (about 600 x 280, rounded) stuck at the top centre.

## Root causes
1. **Hiding the drawer / panel unfolds a chip into the full card.** `features/cards/index.tsx` `isChip()` / `useChip()`
   (was ~line 1022): an engine step or hint card that repeats the drawer folds to a pill-sized chip only *while the
   drawer is open* (`shown = d.open && !d.concept ...`). Esc / the panel's hide key / a click closes the drawer, the
   fold condition goes false and the `card` island mode's width jumps from pill to `CARD_W`: the island grows into the
   full card. Reproduced in the stage: chip 199x34 became the card 420x109 on "hide".
2. **A card closed under the pointer hands the island straight to a hover card.** `core/Island.tsx` `hover` (set by
   `enter`, ~line 150) stays true while the pointer rests on the island. Click the X: the card closes and, in the same
   render, every hover-wanted mode (the overview card, 440 wide, `features/overview/clear.ts useOverviewActive`; an
   off-track peek, up to 620 wide) wins, so the island grows again instead of collapsing. Reproduced: X on a 420x109
   card turned into the 440x190 overview. Esc (`dismiss`) did not drop hover either.
3. **An empty measurement kept the card's size.** `core/Island.tsx` size `useLayoutEffect` (was lines 89-118): "a 0
   measurement never wins: the last good size stays". A pill-sized mode whose row measured 0 (or whose layer was never
   found after 30 frames) kept the previous CARD's width AND height, and a card whose content rendered nothing kept its
   old height: a pill-rounded black box with nothing in it, card-sized, at the top centre. The island element is
   `data-hit`, so `overlay.bounds` / main's click-catching poll kept eating clicks over it. The island also stayed
   `data-hit` (invisible, opacity 0) while the launcher or settings had it.

## Fix
- `features/cards/index.tsx`: the fold is remembered (`useFolded`: the card's key and the step the drawer showed when
  it folded). Closing the drawer / panel keeps the chip; the learner's tap still opens it; a different card, or the
  same one re-sent with a button or diff, is judged afresh.
- `core/Island.tsx` (Adrian's core, minimal):
  - a held card (not a hover card) that closes while hover is on drops hover during render, so no hover card commits;
    `onUi('dismiss')` drops hover too. Hover comes back on the next pointer entry (checked in the stage).
  - size comes from the new pure `core/islandSize.ts`: a pill is always pill-tall, width = its row, else the last
    pill width (never a card's); a card = fixed width x content height; an empty card, or a layer never found, is the
    pill. So the clickable rect (the island's DOM box, reported as `overlay.bounds` and `overlay:hits`) shrinks with it.
  - while yielded (launcher / settings own the island) it is `pointer-events-none` and not `data-hit`.
- `test/islandSize.test.ts`: the size rules, including the 620 x 280 card -> 0-width pill case.

## Core request
Adrian: please review the `core/Island.tsx` change (hover drop after a held card closes or a `dismiss`, size via
`core/islandSize.ts`, no `data-hit` while yielded) and the new `core/islandSize.ts`. Both were the bug's home, so they
were edited directly and kept small.

## Not verified
Electron (cost freeze / no real app run). If the black box still shows on the Mac, check whether the overlay's frame
loop was paused (the island's spring would freeze mid-shrink); the target size is now always the pill.

# Notch: slanted sides again + pastel gradient in bon's color (Nov 26)

Branch `michael/app-notch-bon-gradient`, cut from `origin/main`.

## What Michael decided
This overrides two of Adrian's MIC-83 commits on main: cb9c4d0f (straight sides) and d5ccc925 (no gradient).
- **Slanted sides.** The open island is an upside-down trapezoid under the curved top ears again.
  `NOTCH_RADII.open` is top 19, bottom 24, taper 18. The peek keeps its small lean (10 / 18 / 5). Closed is still 0, so
  at rest it is the hardware notch. A test fails if the open taper is ever 0.
- **A pastel gradient in bon's color.** `notchGradient(bonColor)` in `core/theme.ts`: pure black down to 35% of the height,
  so it melts into the hardware notch, then a muted pastel of bon's color at the bottom edge (bon's color mixed 35%
  toward white, alpha .30, eased stops so it doesn't band). bon's color is the one the learner picks in setup or in
  Settings (Buddy color, `features/buddy/skin.ts`). Until they pick one it is bon's default color (sand). It follows a
  new pick right away: the island reads `useSkin()`, which updates from the `storage` event.
- Closed, the ears and the short peek stay plain black. With reduced motion the gradient doesn't fade, it just appears.

## Adrian's concerns, and how each one is handled
1. **A hue behind Not yet or an error could read as "passed".** The gradient is opt-in, set in `core/islandTone.ts`.
   Only calm panels get it: the notch home, which covers Continue lesson, ask miyagi, the drop zone, the lessons
   ready to run, the Library row and the idle hover panel. Not yet (`offtrack`), every `err-*` card (error,
   offline, failed build, limits, busy), the permission asks (`ptt-card`, `onboarding-recovery`) and the cloud refusals
   (`signin-card`, `cap-line`) are named there as blocked kinds. Any mode not listed also stays black. The notch home
   itself goes plain black while it is saying a link can't be used (a dropped page it can't teach, or a drop that
   wasn't a link): `IslandMode.useTone`, `features/notch-home/tone.ts`. When a blocked panel takes over, the gradient
   is gone at once. It never fades out behind it.
2. **The faint grey fell to 3.1:1.** While the gradient shows, the island sets brighter muted tokens
   (`islandTextOnTint`: label white 74%, faint `#C4C3BE`, chip text 78%, key text 76%). A test checks every island
   text token (`islandText`: text, label, faint, chip, key and keycap text) against the brightest point of the
   gradient for every bon color, stage-only ones included. Each one has to reach at least 4.5:1 there, and on the
   black top as well.
3. **BRAND.md rule 6 allows no gradient.** `theme.ts` names this as the one exception to "no gradients", says why
   (Michael's call, Nov 26) and lists the limits above. A test checks that the note is there.

## Tests
`test/notchTint.test.ts` (new) checks:
- blocked kinds `notyet`, `error`, `offline`, `permission`, `failed` and `warning` never get the gradient;
- every warning mode maps to a blocked kind;
- calm panels get it only when the island is open and tall;
- the notch home's warning tone turns it off;
- the gradient's stops are right: black to 35%, rising after that, ending at alpha .25 to .40;
- each bon color gets its own lighter pastel;
- the contrast check described above;
- a live color change (a pick, a pick from another window, and the default when none is chosen) gives the new gradient;
- theme.ts has the exception note.

`test/notchIsland.test.ts`: open taper > 0 and the side leans in. `test/islandRest.test.ts`: the open top radius is 19.

## Shots (headless stage, `?scenario=home&notch=real&skin=…`, hover on the notch)
- `shots/notch-bon-gradient-open-sand.png`: bon's default color
- `shots/notch-bon-gradient-open-lilac.png`
- `shots/notch-bon-gradient-open-peach.png`
- `shots/notch-bon-gradient-notyet-black.png`: the Not yet card with bon in lilac, plain black

Script: `~/miyagi/tools/playwright/notch-bon-gradient-shots.mjs <port> <outdir>`.

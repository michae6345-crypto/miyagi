# Notch: Adrian's MIC-83 fixes + slanted sides + pastel green gradient (Nov 25)

Branch `michael/app-notch-gradient`, cut from `michael/app-ui-v4`. Michael's call: take everything Adrian shipped for
the app except his straight-sides look.

## What came in
- **PR #277** (`adrian/mic-83-notch-island`): five of Adrian's seven commits, cherry-picked with his authorship kept:
  - 766adea9 below the menu bar, a hover card stays under the pointer
  - 96873179 a scroll on the notch leans it 8% at most
  - c3377301 the open island's shadow falls downward
  - 1d6f2b68 notch home rows keep their height
  - 6898e6a7 a failed start drops its Retry line in the notch too
  - **Left out:** 282d9fa6 (straight sides, smaller flare) and 12a96152 (no green glow). The tests those two changed
    stay on the slanted shape.
- **PR #279** (`claude/ecstatic-lamport-ppbpkh`): merged as is (a long skills Path pans at full size).

## The look
- **Slanted sides kept.** `NOTCH_RADII.open` is top 19, bottom 24, taper **18** (was 16), so it reads as an
  upside-down trapezoid under the curved top ears. Peek keeps its small lean (taper 5); closed is 0.
- **Pastel green gradient** replaces the radial glow: `hud.notchGradient` in `core/theme.ts`, a linear, eased fill over
  the notch black. It is transparent to 35% (pure black at the top, so it melts into the hardware notch), then rises
  to `rgba(150,228,200,.32)` at the bottom edge. Several stops, so it doesn't band.
- **Only when open and tall:** `gradientOn(open, h)` in `core/notchGeometry.ts` (open and h >= SHORT_OPEN_H 120).
  Closed, ears and the short peek stay plain black. The layer fades in over 0.35 s and is instant with reduced motion.
  The open shape carries `data-notch-gradient` while the gradient shows.
- **Contrast:** on the brightest stop, white text is 9.8:1 and the muted white (60%) is 4.7:1. A test
  checks both. The island pins data-theme="dark", so the light and dark system themes look the same.
- The brand's "no gradients" line in theme.ts now names this one exception.

## Tests
- `test/notchIsland.test.ts`: open taper > 0 and the side path leans in; `gradientOn` is true only open and tall
  (false for the closed shape and the 74 px peek); stops are black to 35% and only rise from there, ending pastel mint
  at .2 to .45; the contrast checks above.
- `npm run typecheck` is clean. Full node suite: 1180/1180 pass.

## Shots (headless Playwright, 1280x800 @2x, `~/miyagi/tools/playwright/notch-gradient-shots.mjs`)
- `shots/notch-gradient-open-{dark,light}.png`: notch home hover panel, 634x242, slanted sides, gradient on
- `shots/notch-gradient-closed-{dark,light}.png`: at rest with ears, plain black
- `shots/notch-gradient-peek-{dark,light}.png`: `ambient-help` drop peek, 320x74, peek radii, plain black

Not checked: Electron on the real notch (the auto-install loop picks this up once it is merged into app-ui-v4).

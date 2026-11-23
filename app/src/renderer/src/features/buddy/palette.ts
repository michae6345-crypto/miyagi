/**
 * Feature: buddy. The buddy's own colors, in one place.
 *
 * A skin is the buddy's color: its body, its leaves, its cheeks and the stroke it draws. One skin is in use (SKIN).
 * Adrian picked mint on Nov 22 and then did not like it on the character (Nov 23), so the others here are candidates
 * for him to pick from; the browser stage's ?skin=<name> shows the whole buddy in one, and ?buddy=colors shows them
 * side by side. Once he picks, the rest go and the pick gets a theme token (brief, Core requests).
 *
 * Where a color is in the brand kit it is read from there. `kit: false` marks one that is not.
 */
import { brand } from '../../core/theme'

/** Its outline, eyes and mouth: the brand ink. The outline is what makes it read over a light app. */
export const INK = brand.ink
/** The glint in its eyes. */
export const GLINT = brand.surface

export type Skin = {
  /** Its body. */
  body: string
  /** Its leaves and stem. */
  leaf: string
  /** Its cheeks. */
  blush: string
  /** The loop it draws, and the numbers of a tour. */
  stroke: string
  /** One line for the color sheet. */
  note: string
  /** Is every color of it in the brand kit. */
  kit: boolean
}

const PINK = brand.pastel.pink
const PINK_DEEP = brand.pastel.pinkDeep
/** The mint of the notch's glow (hud.notchGlow, rgb 150 228 200). Not the pass green. */
const MINT = '#96E4C8'
/** The pot of the logo, in its cut for dark backgrounds (BRAND.md). */
const CLAY = '#C2694A'

export const SKINS = {
  mint: { body: MINT, leaf: brand.pastel.mint, blush: PINK, stroke: MINT, note: 'what it is now', kit: false },
  cream: { body: brand.paper, leaf: brand.paper, blush: PINK, stroke: brand.paper, note: 'the brand paper: white on black, like the buttons', kit: true },
  sand: { body: brand.pastel.sand, leaf: '#F4EEDC', blush: PINK_DEEP, stroke: brand.pastel.sand, note: 'the kit sand', kit: true },
  butter: { body: '#F6DE8E', leaf: '#FBEDBE', blush: PINK_DEEP, stroke: '#F6DE8E', note: 'a soft yellow; the kit has no yellow', kit: false },
  peach: { body: brand.pastel.peach, leaf: brand.pastel.peachLight, blush: PINK_DEEP, stroke: brand.pastel.peach, note: 'the kit peach (also the Watch option)', kit: true },
  clay: { body: CLAY, leaf: brand.pastel.peachLight, blush: PINK_DEEP, stroke: CLAY, note: 'the pot of the logo', kit: true },
  pink: { body: PINK_DEEP, leaf: PINK, blush: '#E98BA8', stroke: PINK_DEEP, note: 'the kit pink (also the Hint option)', kit: true },
  lilac: { body: brand.pastel.lilac, leaf: '#ECE8FF', blush: PINK, stroke: brand.pastel.lilac, note: 'the kit lilac (also Show me)', kit: true },
  sky: { body: brand.pastel.skyDeep, leaf: brand.pastel.sky, blush: PINK, stroke: brand.pastel.skyDeep, note: 'the kit sky; the kit says no blue elsewhere', kit: true }
} as const satisfies Record<string, Skin>
export type SkinName = keyof typeof SKINS

/** The one in use until Adrian picks. */
export const DEFAULT_SKIN: SkinName = 'mint'

/** The skin in use. The browser stage's ?skin=<name> shows another. */
export const SKIN: Skin = (() => {
  const q = typeof location !== 'undefined' ? new URLSearchParams(location.search).get('skin') : null
  return SKINS[q && q in SKINS ? (q as SkinName) : DEFAULT_SKIN]
})()

/**
 * Make it yours: the body colors a learner could pick for their buddy (a proposal; nothing stores the choice yet).
 * The brand's pastels, the deeper cut where there is one, so each holds up over a light app. Its leaves keep the
 * skin's color. `blush`: its cheeks in that color.
 */
export const TINTS = {
  mint: { body: MINT, blush: PINK },
  sky: { body: brand.pastel.skyDeep, blush: PINK },
  pink: { body: PINK_DEEP, blush: '#E98BA8' },
  lilac: { body: brand.pastel.lilac, blush: PINK },
  peach: { body: brand.pastel.peach, blush: PINK_DEEP },
  sand: { body: brand.pastel.sand, blush: PINK }
} as const
export type Tint = keyof typeof TINTS

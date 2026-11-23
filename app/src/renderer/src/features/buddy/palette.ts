/**
 * Feature: buddy. The buddy's own colors, in one place.
 *
 * A skin is the buddy's color: its body, its leaves, its cheeks and the stroke it draws. The learner picks theirs
 * when they set miyagi up, like Clicky's cursor color (Adrian, Nov 23); skin.ts holds the one in use and PICKS is
 * what they choose from. Until they pick it is DEFAULT_SKIN, sand (Adrian picked it from the color sheet on Nov 23,
 * after not liking the mint he had picked on Nov 22).
 * Some skins here are not offered to learners: the cream versions Adrian asked to compare. The browser stage's
 * ?skin=<name> shows the whole buddy in any of them, and ?buddy=colors shows them side by side.
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
  /** A flat shade along its underside (the sprout), where it has one. Not a gradient. */
  shade?: string
  /** Its cheeks. */
  blush: string
  /** The loop it draws, and the numbers of a tour. */
  stroke: string
  /** How opaque the ink keyline under its loop is, where the usual (Reach.tsx KEYLINE) is not enough over a light app. */
  keyline?: number
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
const SAND = brand.pastel.sand
/** Halfway between the brand paper and the sand. */
const IVORY = '#F0EBDD'

export const SKINS = {
  mint: { body: MINT, leaf: brand.pastel.mint, blush: PINK, stroke: MINT, note: 'what it was', kit: false },
  cream: { body: brand.paper, leaf: brand.paper, blush: PINK, stroke: brand.paper, keyline: 0.9, note: 'the brand paper: white on black, like the buttons', kit: true },
  sand: { body: SAND, leaf: brand.paper, blush: PINK_DEEP, stroke: SAND, keyline: 0.75, note: 'the kit sand: the pick', kit: true },
  butter: { body: '#F6DE8E', leaf: '#FBEDBE', blush: PINK_DEEP, stroke: '#F6DE8E', note: 'a soft yellow; the kit has no yellow', kit: false },
  peach: { body: brand.pastel.peach, leaf: brand.pastel.peachLight, blush: PINK_DEEP, stroke: brand.pastel.peach, note: 'the kit peach (also the Watch option)', kit: true },
  clay: { body: CLAY, leaf: brand.pastel.peachLight, blush: PINK_DEEP, stroke: CLAY, note: 'the pot of the logo', kit: true },
  pink: { body: PINK_DEEP, leaf: PINK, blush: '#E98BA8', stroke: PINK_DEEP, note: 'the kit pink (also the Hint option)', kit: true },
  lilac: { body: brand.pastel.lilac, leaf: '#ECE8FF', blush: PINK, stroke: brand.pastel.lilac, note: 'the kit lilac (also Show me)', kit: true },
  sky: { body: brand.pastel.skyDeep, leaf: brand.pastel.sky, blush: PINK, stroke: brand.pastel.skyDeep, note: 'the kit sky; the kit says no blue elsewhere', kit: true },
  // Cream, a few ways (Adrian, Nov 23: "a couple of cream iterations"). `cream` above is the plain one.
  'cream-sand': { body: brand.paper, leaf: SAND, blush: PINK, stroke: brand.paper, keyline: 0.9, note: 'white body, sand leaves', kit: true },
  'cream-shade': { body: brand.paper, leaf: SAND, shade: SAND, blush: PINK, stroke: brand.paper, keyline: 0.9, note: 'white body, a flat sand shade under it, sand leaves', kit: true },
  ivory: { body: IVORY, leaf: brand.paper, blush: PINK, stroke: IVORY, keyline: 0.85, note: 'halfway between cream and sand', kit: false },
  'cream-sage': { body: brand.paper, leaf: '#A9D0A6', blush: PINK, stroke: brand.paper, keyline: 0.9, note: 'white body, green leaves (a new green, not the pass green)', kit: false }
} as const satisfies Record<string, Skin>
export type SkinName = keyof typeof SKINS

/** What the buddy comes in until the learner picks: Adrian's pick from the color sheet, Nov 23. */
export const DEFAULT_SKIN: SkinName = 'sand'

/** The colors a learner can pick from, in the order the picker shows them (ColorPicker.tsx). The rest are stage-only. */
export const PICKS: readonly SkinName[] = ['sand', 'cream', 'butter', 'peach', 'clay', 'pink', 'lilac', 'sky', 'mint']

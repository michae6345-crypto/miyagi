/**
 * Feature: buddy. The buddy's own colors, in one place. All from the brand kit except MINT, which is the mint of the
 * notch's glow (hud.notchGlow, rgb 150 228 200): Adrian picked it for the buddy on Nov 22, deeper than the pastel
 * mint so it holds up over a light app. It is not the pass green. It has no theme token yet (brief, Core requests).
 */
import { brand } from '../../core/theme'

/** The buddy's body, and the stroke it draws. */
export const MINT = '#96E4C8'
/** Its leaves and lighter parts: the brand's pastel mint. */
export const MINT_PALE = brand.pastel.mint
/** Its outline, eyes and mouth: the brand ink. The outline is what makes it read over a light app. */
export const INK = brand.ink
/** Its cheeks: the brand's pastel pink. */
export const BLUSH = brand.pastel.pink
/** The glint in its eyes. */
export const GLINT = brand.surface

/**
 * Make it yours: the body colors a learner could pick for their buddy (a proposal; nothing stores the choice yet).
 * Mint is the one it comes in. The rest are the brand's pastels, the deeper cut where there is one, so each holds up
 * over a light app. Its leaves stay mint in every color: it is still a sprout. `blush`: its cheeks in that color.
 */
export const TINTS = {
  mint: { body: MINT, blush: BLUSH },
  sky: { body: brand.pastel.skyDeep, blush: BLUSH },
  pink: { body: brand.pastel.pinkDeep, blush: '#E98BA8' },
  lilac: { body: brand.pastel.lilac, blush: BLUSH },
  peach: { body: brand.pastel.peach, blush: brand.pastel.pinkDeep },
  sand: { body: brand.pastel.sand, blush: BLUSH }
} as const
export type Tint = keyof typeof TINTS

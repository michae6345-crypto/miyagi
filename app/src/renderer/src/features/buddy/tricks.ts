/**
 * Feature: buddy. The tricks bon plays when it is tapped (Poke.tsx), one per tap, round and round. Pure, so tests read it.
 */
export type Trick = 'hop' | 'wiggle' | 'twirl'
export const TRICKS: Trick[] = ['hop', 'wiggle', 'twirl']
/** How long one trick plays, ms (buddy.css matches it). */
export const TRICK_MS = 720

/** The trick for the nth tap (0-based). */
export const trickFor = (n: number): Trick => TRICKS[((n % TRICKS.length) + TRICKS.length) % TRICKS.length]

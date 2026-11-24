/**
 * Feature: buddy. What the character is called, in one place.
 *
 * Adrian, Nov 23: "we shouldn't say buddy, we need a name that will match the miyagi theme". The name is his to pick
 * and is not picked yet: until it is, NAME is undefined and the copy still says "buddy". When he picks, set NAME here
 * and every screen follows (setup's step, the Settings row, the picker's label).
 *
 * The theme is the bonsai, not the film: the founders dropped the Karate Kid cues on Nov 22 (launch-risk D3), so no
 * dojo words (sensei, deshi, obi, kata). The candidates are all from the tree:
 *   bon      the "bon" of bonsai: the tray the tree grows in
 *   futaba   "two leaves": the first pair of leaves on a sprout, which is what it has on its head
 *   wakaba   "young leaf": in Japan the young-leaf mark is also the sign of a beginner
 *   moyo     from moyogi, the style the logo's tree is grown in
 *   hachi    the pot a bonsai lives in
 * Lowercase, like the brand, also at the start of a sentence ("miyagi is set up on this Mac").
 *
 * The browser stage's ?name=<name> shows every screen with a name, so they can be compared in place.
 * Code keeps saying buddy (the folder, the feature id, the layer id Michael's layer looks for): only the words the
 * learner reads change.
 */
export const NAME_CANDIDATES = ['bon', 'futaba', 'wakaba', 'moyo', 'hachi'] as const

/** Set this when Adrian picks. */
const PICKED: string | undefined = undefined

const fromStage = (): string | undefined => {
  if (typeof window === 'undefined' || 'tut' in window) return undefined // the stage only, never the app
  const q = new URLSearchParams(window.location.search).get('name')?.toLowerCase()
  return q && /^[a-z]{2,12}$/.test(q) ? q : undefined
}

/** Its name, or undefined while it has none. */
export const NAME: string | undefined = fromStage() ?? PICKED

/** The words the learner reads about it. */
export const words = {
  /** Setup's step. */
  stepTitle: NAME ? `Meet ${NAME}` : 'Pick your buddy’s color',
  stepBody: NAME ? 'It points things out and answers when you ask. Pick its color.' : 'It points things out and answers when you ask.',
  stepLater: 'You can change it later in Settings.',
  /** Settings > General. */
  group: NAME ?? 'Buddy',
  row: NAME ? `${NAME}’s color` : 'Buddy color',
  rowCaption: NAME ? `${NAME} and the loops it draws.` : 'Your buddy and the loops it draws.',
  /** The swatches, for a screen reader. */
  colors: NAME ? `${NAME}’s color` : 'Buddy color'
} as const

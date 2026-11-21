/** Push to talk: where a final text goes. Pure, so it is tested offline (test/pttRoute.test.ts). */
export type Routed = 'ask' | 'launcher' | 'none'

/**
 * A lesson is running -> the same ask a typed question makes (about the current step).
 * No lesson -> the launcher opens prefilled in search/build mode; the learner confirms, nothing is built by surprise.
 * Empty -> nothing.
 */
export function routeFor(text: string, lessonActive: boolean): Routed {
  if (!text.trim()) return 'none'
  return lessonActive ? 'ask' : 'launcher'
}

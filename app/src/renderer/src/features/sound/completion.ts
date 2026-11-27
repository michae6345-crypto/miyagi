/**
 * Feature: sound. When the lesson-complete chime may play (MIC-90): once per completion, never for a replay.
 *
 * The engine sends the completion card (card kind "complete", or any card carrying a skillMap) live, a moment after
 * the lesson's last step.passed. It sends the SAME card again with no step.passed before it when:
 *   - the app reconnects or the engine restores the lesson (snapshot: lesson.ready {replay: true}, step.started
 *     {replay: true}, check.updated..., then the card),
 *   - a finished lesson is reopened (a re-sent learn / library.start of the lesson already at its end: the same
 *     snapshot),
 *   - Check or Skip is pressed after the end (the ending card again).
 * So a step.passed for this lesson arms the guard, the first completion card after it plays and disarms it, and
 * anything that starts or re-sends a lesson (lesson.ready, a replayed step.started, a reset) disarms it. Nothing here
 * knows what the lesson is about: it reads only the lesson id the store passes in.
 *
 * Pure module: no imports, so the test drives it directly.
 */

export type CompletionGuard = {
  /** A live step.passed (passed, skipped or already done) in this lesson: its completion card may chime. */
  stepPassed(lessonId: string): void
  /** A completion card for this lesson: true = chime now (and never again for this completion). */
  completed(lessonId: string): boolean
  /** lesson.ready, a replayed step.started (a reconnect / reopen) or a reset: nothing is armed. */
  clear(): void
}

export function createCompletionGuard(): CompletionGuard {
  let armedFor: string | undefined
  return {
    stepPassed(lessonId) {
      armedFor = lessonId
    },
    completed(lessonId) {
      if (armedFor === undefined || armedFor !== lessonId) return false
      armedFor = undefined
      return true
    },
    clear() {
      armedFor = undefined
    }
  }
}

/** Is this engine card the lesson's completion card? (kind "complete", or the older "step" kind with a skillMap.) */
export function isCompletionCard(p: unknown): boolean {
  if (!p || typeof p !== 'object') return false
  const raw = p as { kind?: unknown; skillMap?: unknown }
  return raw.kind === 'complete' || (raw.skillMap !== undefined && raw.skillMap !== null)
}

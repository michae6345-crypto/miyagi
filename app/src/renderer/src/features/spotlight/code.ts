/**
 * Spotlight text, pure (no React): the snippet's missing line(s) (Michael's tests 2-3, A10: "highlight the missing
 * line") and the caption's backticks (A21). Kept apart so it's easy to check on its own.
 */

/** Whitespace-insensitive: indentation and spacing in OCR'd or engine-written code vary. */
const norm = (l: string): string => l.replace(/\s+/g, ' ').trim()

/**
 * Which of the snippet's lines (0-based) the learner is still missing. The evidence, strongest first:
 *   1. the step's off-track diff: the expected lines yours doesn't have (the same rule as the off-track card's
 *      evidence panel);
 *   2. code the caption names in backticks ("Still missing: `return a + b`"): the lines that contain it.
 * Empty when there's no evidence, or when the snippet is a single line (it IS the line to type).
 */
export function missingLines(snippet: string, diff?: { expected: string; yours: string }, caption?: string): Set<number> {
  const lines = snippet.split(/\r?\n/)
  const out = new Set<number>()
  if (lines.filter((l) => norm(l)).length < 2) return out
  if (diff?.expected.trim()) {
    const yours = new Set(diff.yours.split(/\r?\n/).map(norm))
    const added = new Set(diff.expected.split(/\r?\n/).map(norm).filter((l) => l && !yours.has(l)))
    lines.forEach((l, i) => added.has(norm(l)) && out.add(i))
    if (out.size) return out
  }
  const named = Array.from((caption ?? '').matchAll(/`([^`\n]+)`/g), (m) => norm(m[1])).filter((c) => c.length >= 3)
  lines.forEach((l, i) => named.some((c) => norm(l).includes(c)) && out.add(i))
  return out
}

/**
 * A caption for CodeText (Michael's tests 2-3, A21: literal backticks in spotlight captions): backticks become inline
 * mono code, like card titles. A caption cut inside code (an odd number of backticks) gets its closing one.
 */
export const closeTicks = (t: string): string => ((t.match(/`/g)?.length ?? 0) % 2 ? `${t}\`` : t)

/** The caption as plain words, where text shows as-is (the pill's notice, a tooltip): no literal backticks. */
export const plain = (t: string): string => t.replace(/`/g, '')

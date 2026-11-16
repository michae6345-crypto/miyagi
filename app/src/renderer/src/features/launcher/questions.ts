/**
 * Feature: launcher. The ask panel's suggested questions (Michael's review A11: the panel repeated Explain / Hint, which
 * the bar already has; it should suggest questions instead). Built only from the current step's own data: its title,
 * its concepts and its checks. No topic is hardcoded (generality rule); the words around them are plain grammar.
 *
 * At most MAX, most useful first:
 *   a check that isn't passing   → Why isn't “<check>” passing yet?
 *   the step title               → Why do we <title>? (an imperative title) · What's the idea behind <title>?
 *   each concept                 → What is <concept>?
 *   a check still waiting        → What does “<check>” check?
 */
import type { CheckItem } from '../../core/lesson'

export const MAX_QUESTIONS = 3

/**
 * First words of a step title that make it an instruction ("Define the residual", "Read input in a loop"): the title
 * reads as "Why do we …?". Any other title is a thing ("Multi-head attention"): "What's the idea behind …?".
 */
const VERBS = new Set(
  (
    'add apply attach average batch build call change check choose clean clone compare compute configure connect convert count ' +
    'create declare define deploy display draw embed encode evaluate export extract feed fetch filter fit fix follow generate ' +
    'handle implement import initialize initialise install load log loop make map mask measure merge move multiply normalize ' +
    'open parse pass plot plug predict print read refactor register remove render replace return run sample save scale send set ' +
    'show solve sort split stack start store test tokenize train try turn update use wrap write'
  ).split(' ')
)

/** Lowercase the first word when it's an ordinary capitalized word ("Define" → "define"), never an acronym or "LayerNorm". */
function lowerFirst(text: string): string {
  return text.replace(/^([A-Z])([a-z]+)\b/, (_, a: string, b: string) => a.toLowerCase() + b)
}

/** One line: no trailing punctuation, no doubled spaces. */
function clean(text: string): string {
  return text.replace(/\s+/g, ' ').trim().replace(/[.:;!?]+$/, '')
}

export function stepQuestions({ title, concepts, checks }: { title?: string; concepts: string[]; checks: CheckItem[] }): string[] {
  const out: string[] = []
  const failing = checks.find((c) => c.status === 'fail' && clean(c.label))
  const waiting = checks.find((c) => c.status === 'pending' && clean(c.label))
  if (failing) out.push(`Why isn't “${clean(failing.label)}” passing yet?`)
  const t = clean(title ?? '')
  if (t) {
    const first = t.split(' ')[0].toLowerCase()
    out.push(VERBS.has(first) ? `Why do we ${lowerFirst(t)}?` : `What's the idea behind ${lowerFirst(t)}?`)
  }
  for (const c of concepts) {
    const name = clean(c)
    if (name) out.push(`What is ${lowerFirst(name)}?`)
  }
  if (waiting) out.push(`What does “${clean(waiting.label)}” check?`)
  const seen = new Set<string>()
  return out.filter((q) => !seen.has(q.toLowerCase()) && !!seen.add(q.toLowerCase())).slice(0, MAX_QUESTIONS)
}

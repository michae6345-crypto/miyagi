/**
 * Telling the learner's code (or a value) from status text, for the off-track evidence panel (Evidence.tsx).
 * Most check details the engine sends are sentences ABOUT the code: "not in weather.py yet", "weather.py not
 * found", "Open VS Code so I can check it.", "loss 0.25 at step 300, need < 0.01". A sentence that mentions a
 * file, a quote or a number is still a sentence, never code (Michael, review A5, frames 01:08:23 and 01:09:13:
 * the ".py" in "not in weather.py yet" made it render as code).
 */

/** Status leads: a detail that opens like this is about the code ("not in…", "missing", "Open VS Code so…"). */
const LEAD =
  /^(?:not|no|missing|still|waiting|open|collecting|cannot|can't|couldn't|check|invalid|unsupported|exited|run|rerun|rerunning|retraining|nothing|pending|screen|need|needs|empty|unknown|error|failed|timed|skipped|save|create|write|add)(?=\s+[^\s=+\-*/%<>!&|^.,:;)\]}]|:\s|\s*$|…)/i
/** A placeholder for code that isn't there: "(missing)", "<none>", "[not written yet]", "…". */
const PLACEHOLDER = /^(?:[([<]\s*(?:missing|none|nothing|empty|n\/a|not\b[^)\]>]*)\s*[)\]>]|…|\.\.\.|[-–—])$/i
/** Ends like a sentence: a word then a full stop ("…so I can check it."). Code rarely ends on a word and a period. */
const SENTENCE_END = /\s.*[A-Za-z]{2}[.!?]$/

/** A plain word: what a sentence is made of once its filenames, quotes and numbers are taken out. */
const WORD = /^[A-Za-z][A-Za-z']*[,.:;!?]?$/
/** A file or dotted name standing in a sentence: weather.py, src/app.ts, calc.py:, np.mean. */
const FILE = /^[\w~./\\-]*\w\.[A-Za-z]\w{0,5}[,.:;!?)]*$/
const NUM = /^[-+]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)(?:e[-+]?\d+)?%?[,.:;)]*$/i
/** A quoted part (not an apostrophe: "can't" stays a word). */
const QUOTED = /(?<!\w)(['"`])[^'"`]*\1/g
/** English that code doesn't use as a bare word (keywords like in / for / not / is are left out on purpose). */
const ENGLISH = new Set(
  'yet so the an at by to of on need needs found seen showing shown can cannot it its please nothing still open step steps missing output logged written there here has have was were are been should must your you this that than then into does did done wrong try again saved'.split(
    ' '
  )
)

/** Words only, apart from filenames, quotes and numbers: a sentence. Mostly words, some of them English: prose. */
function wordy(s: string): boolean {
  const toks = s
    .replace(QUOTED, ' ')
    .split(/\s+/)
    .filter((t) => t && !FILE.test(t) && !NUM.test(t))
  const words = toks.filter((t) => WORD.test(t))
  if (words.length >= 2 && words.length === toks.length) return true
  return words.length >= 3 && words.length >= toks.length * 0.6 && words.some((w) => ENGLISH.has(w.replace(/[,.:;!?]$/, '').toLowerCase()))
}

/** Status or prose, not code: "not in weather.py yet", "weather.py not found", "Open VS Code so I can check it.". */
export function isProse(text: string): boolean {
  const s = text.trim()
  if (!s) return false
  return LEAD.test(s) || PLACEHOLDER.test(s) || SENTENCE_END.test(s) || wordy(s)
}

/** A whole value on its own: "2.49", "-6.08e-4", "1,115,394", "93%". */
export const NUMBER = /^[-+]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)(?:e[-+]?\d+)?%?$/i
/** A bare literal. */
export const LITERAL = /^(true|false|none|null|nan|undefined|[-+]?inf(inity)?)$/i
/** A code character: a digit, an operator or bracket, a quote, an underscore, or a dot inside a name. */
const CODEY = /[\d=()[\]{}<>"`_]|\.(?=\S)/

/** Reads as code (or a value) on its own: a number, a literal, or code characters in something that isn't prose. */
export function readsAsCode(text: string): boolean {
  const s = text.trim()
  if (!s) return false
  if (NUMBER.test(s) || LITERAL.test(s)) return true
  return CODEY.test(s) && !isProse(s)
}

/**
 * The value in a metric reading, where a sentence carries one: "loss 0.25 at step 300, need < 0.01" → "0.25",
 * "loss diverged: nan at step 30" → "nan". The metric's name comes from the data, so any name matches.
 */
export function readingValue(text: string): string | undefined {
  const m = text.match(/(?:^|\s)([-+]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)(?:e[-+]?\d+)?|[-+]?(?:nan|inf(?:inity)?))\s+at step\s+\d/i)
  return m?.[1]
}

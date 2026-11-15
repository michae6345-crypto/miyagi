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

/**
 * A sentence: apart from filenames, quotes and numbers it's words (all of them, or most), and some of them are
 * English that code doesn't use ("weather.py not found", "Yours is still empty"). "return x" and "import numpy as
 * np" are words too, but no English: code.
 */
function wordy(s: string): boolean {
  const toks = s
    .replace(QUOTED, ' ')
    .split(/\s+/)
    .filter((t) => t && !FILE.test(t) && !NUM.test(t))
  const words = toks.filter((t) => WORD.test(t))
  const english = words.some((w) => ENGLISH.has(w.replace(/[,.:;!?]$/, '').toLowerCase()))
  if (!english || words.length < 2) return false
  return words.length === toks.length || (words.length >= 3 && words.length >= toks.length * 0.6)
}

/**
 * Status or prose, not code: "not in weather.py yet", "weather.py not found", "Open VS Code so I can check it.",
 * "(missing)". Code that happens to be words ("return x") is not prose.
 */
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

// ---------------------------------------------------------------------------
// The diff, one column: your lines (-) then the expected ones (+), the parts that changed inside a line marked
// ---------------------------------------------------------------------------

/** A piece of a line; `changed` = it differs from the line it's paired with. */
export type Part = { text: string; changed: boolean }
/** One row: '-' yours, '+' expected, ' ' both. `parts` only on a line paired with its changed version. */
export type DiffRow = { sign: '-' | '+' | ' '; text: string; parts?: Part[] }

/** Names, runs of space, and single punctuation: `.json()` is 4 tokens, so a change stops at the right place. */
const tokens = (s: string): string[] => s.match(/\w+|\s+|[^\w\s]/g) ?? []
const solid = (s: string): number => s.replace(/\s/g, '').length
const key = (l: string): string => l.replace(/\s+/g, ' ').trim()

/** Longest common subsequence: which items of a and of b are kept (the k-th kept a pairs with the k-th kept b). */
function keep<T>(a: T[], b: T[], eq: (x: T, y: T) => boolean): [boolean[], boolean[]] {
  const n = a.length
  const m = b.length
  const dp = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1))
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) dp[i][j] = eq(a[i], b[j]) ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1])
  const ka = new Array<boolean>(n).fill(false)
  const kb = new Array<boolean>(m).fill(false)
  for (let i = 0, j = 0; i < n && j < m; ) {
    if (eq(a[i], b[j])) {
      ka[i++] = true
      kb[j++] = true
    } else if (dp[i + 1][j] >= dp[i][j + 1]) i++
    else j++
  }
  return [ka, kb]
}

/**
 * A line as parts. Space never stands out on its own: it joins a change only between two changed tokens. One
 * unchanged character between two changes joins them (`verify=False` → `timeout=10` is one change, not two).
 */
function toParts(t: string[], kept: boolean[]): Part[] {
  const out: Part[] = []
  const push = (text: string, changed: boolean): void => {
    const last = out[out.length - 1]
    if (last && last.changed === changed) last.text += text
    else out.push({ text, changed })
  }
  t.forEach((s, i) => push(s, !kept[i] && (s.trim() !== '' || (i > 0 && !kept[i - 1] && i < t.length - 1 && !kept[i + 1]))))
  const joined: Part[] = []
  out.forEach((p, k) => {
    const gap = !p.changed && p.text.length === 1 && out[k - 1]?.changed && out[k + 1]?.changed
    const last = joined[joined.length - 1]
    if (last && (gap || last.changed === p.changed)) last.text += p.text
    else joined.push({ ...p })
  })
  return joined
}

const MAX_TOKENS = 160
/** Two versions of one line, as parts with the changes marked. Undefined when they're mostly different lines. */
function inline(x: string, y: string): [Part[], Part[]] | undefined {
  const a = tokens(x)
  const b = tokens(y)
  if (!a.length || !b.length || a.length > MAX_TOKENS || b.length > MAX_TOKENS) return undefined
  const [ka, kb] = keep(a, b, (p, q) => p === q)
  const same = a.reduce((n, s, i) => n + (ka[i] ? solid(s) : 0), 0)
  if ((2 * same) / Math.max(1, solid(x) + solid(y)) < 0.5) return undefined
  return [toParts(a, ka), toParts(b, kb)]
}

/** A run of removed and added lines: each removed line pairs with the next added one that's mostly the same. */
function hunk(rem: string[], add: string[], rows: DiffRow[]): void {
  const removed: DiffRow[] = rem.map((text) => ({ sign: '-', text }))
  const added: DiffRow[] = add.map((text) => ({ sign: '+', text }))
  let from = 0
  for (const r of removed) {
    for (let q = from; q < added.length; q++) {
      const pair = inline(r.text, added[q].text)
      if (!pair) continue
      ;[r.parts, added[q].parts] = pair
      from = q + 1
      break
    }
  }
  rows.push(...removed, ...added)
}

/**
 * Yours → expected as one column of rows: lines both have (same text, any indentation) as context, then each run
 * of changes as its removed lines and its added lines, a line and its changed version paired so the change inside
 * it can be marked (`response = requests.get(url)` → `….json()`: just `.json()`).
 */
export function diffLines(yours: string, expected: string): DiffRow[] {
  const a = yours ? yours.split(/\r?\n/) : []
  const b = expected ? expected.split(/\r?\n/) : []
  const rows: DiffRow[] = []
  // A very long excerpt: no line matching (it's quadratic), just yours then expected.
  if (a.length * b.length > 10000) {
    hunk(a, b, rows)
    return rows
  }
  const [ka, kb] = keep(a, b, (x, y) => key(x) === key(y))
  let i = 0
  let j = 0
  while (i < a.length || j < b.length) {
    const rem: string[] = []
    const add: string[] = []
    while (i < a.length && !ka[i]) rem.push(a[i++])
    while (j < b.length && !kb[j]) add.push(b[j++])
    hunk(rem, add, rows)
    if (i >= a.length || j >= b.length) break
    rows.push({ sign: ' ', text: b[j] })
    i++
    j++
  }
  return rows
}

/**
 * At most `max` rows: context more than a line away from a change goes first, then the tail (`more` = rows cut).
 * All context (nothing changed) is kept as it is, up to `max`.
 */
export function fitRows(rows: DiffRow[], max: number): { rows: DiffRow[]; more: number } {
  const near = (i: number): boolean => [i - 1, i, i + 1].some((k) => rows[k] && rows[k].sign !== ' ')
  const changes = rows.some((r) => r.sign !== ' ')
  const kept = changes ? rows.filter((r, i) => r.sign !== ' ' || near(i)) : rows
  return { rows: kept.slice(0, max), more: Math.max(0, kept.length - max) }
}

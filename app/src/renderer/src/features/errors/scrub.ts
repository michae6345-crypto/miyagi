/**
 * Feature: errors. What may leave this Mac's memory in "Copy details" and in a crash report (BUILD-PLAN section 6):
 * allowlisted fields only, every value scrubbed (API keys, database URLs, tokens, emails, home paths), no code, no
 * screenshots. Pure (no DOM, no Node): main/features/errors.ts imports it too and scrubs again before the clipboard.
 */

/** The longest Copy details / crash report text we ever hand over. */
export const MAX_TEXT = 6000
/** One field's value. */
const MAX_VALUE = 200

const RULES: ReadonlyArray<[RegExp, string]> = [
  // Provider keys and the install token (the BUILD-PLAN list: sk-ant-, AIza, postgres://, xi-; plus our mi_ token).
  [/sk-ant-[A-Za-z0-9_-]+/g, '[key]'],
  [/\bsk-[A-Za-z0-9_-]{16,}/g, '[key]'],
  [/AIza[0-9A-Za-z_-]{6,}/g, '[key]'],
  [/\bxi-[A-Za-z0-9_-]{6,}/g, '[key]'],
  [/\bmi_[A-Za-z0-9_-]{8,}/g, '[token]'],
  [/\bsk_[A-Za-z0-9]{16,}/g, '[key]'],
  [/postgres(?:ql)?:\/\/\S+/gi, '[database url]'],
  [/Bearer\s+[A-Za-z0-9._~+/=-]+/gi, 'Bearer [token]'],
  [/([?&](?:key|api_key|apikey|token|access_token|auth)=)[^&\s]+/gi, '$1[redacted]'],
  [/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g, '[email]'],
  // Home folders: the learner's name is in the path.
  [/\/Users\/[^/\s:'"]+/g, '~'],
  [/\/home\/[^/\s:'"]+/g, '~'],
  [/[A-Za-z]:\\Users\\[^\\\s:'"]+/gi, '~']
]

/** Long base64-ish runs (an unknown key format) are dropped too. */
const OPAQUE = /\b[A-Za-z0-9_-]{40,}\b/g

/** Scrub one text: secrets, emails and home paths out, control characters (but newlines) out, capped. */
export function scrub(text: string, max = MAX_TEXT): string {
  let s = String(text)
  for (const [re, to] of RULES) s = s.replace(re, to)
  s = s.replace(OPAQUE, '[redacted]')
  // eslint-disable-next-line no-control-regex
  s = s.replace(/[\u0000-\u0009\u000B-\u001F\u007F]/g, ' ')
  return s.length > max ? `${s.slice(0, max - 1)}…` : s
}

/** One allowlisted value: a string or number, scrubbed, one line, capped. Anything else is dropped. */
function value(v: unknown): string | undefined {
  if (typeof v === 'number' && Number.isFinite(v)) return String(v)
  if (typeof v !== 'string') return undefined
  const t = scrub(v.replace(/\s+/g, ' ').trim(), MAX_VALUE)
  return t || undefined
}

/**
 * The fields Copy details may carry, in this order. Nothing outside this list is ever written, whatever the caller
 * passes (the caller builds a plain object; unknown keys are ignored).
 */
export const DETAIL_FIELDS = [
  ['app', 'App'],
  ['system', 'System'],
  ['link', 'Engine link'],
  ['engine', 'Engine'],
  ['engineVersion', 'Engine version'],
  ['contract', 'Contract'],
  ['lesson', 'Lesson'],
  ['step', 'Step'],
  ['status', 'Status'],
  ['lastError', 'Last error'],
  ['at', 'Time']
] as const
export type DetailKey = (typeof DETAIL_FIELDS)[number][0]
export type DetailFields = Partial<Record<DetailKey, string | number>>

export function buildDetails(fields: DetailFields): string {
  const lines = ['miyagi details']
  const f = fields as Record<string, unknown>
  for (const [k, label] of DETAIL_FIELDS) {
    const v = value(f[k])
    if (v) lines.push(`${label}: ${v}`)
  }
  lines.push('Not included: your code or files, screenshots, API keys.')
  return scrub(lines.join('\n'))
}

/** Library lesson ids (events.ts LibraryItem): never a path. */
export const LIBRARY_ID = /^[A-Za-z0-9_-]{1,64}$/

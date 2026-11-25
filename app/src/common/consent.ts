/**
 * Consent before capture (launch register R05 and R06). Pure, shared by main (the launch gate's consent part, the guard
 * on the macOS prompts, the record it stamps) and the renderer (the consent screen in the first run).
 *
 *   CONSENT_VERSION   the policy version the learner agrees to. Change it when the terms or the privacy policy change
 *                     in a way the learner must see: every Mac with an older record is asked again on its next launch
 *                     (the gate's consent part closes until they agree).
 *   LEGAL_URL         the published pages. The app links only to these (auth/model.ts LEGAL, main account.ts).
 *   Consent           { version, at }: kept in prefs.json as `consent`, written only by main (onboarding:agree), with
 *                     main's own clock and CONSENT_VERSION. A renderer's prefs:set can't write it (main/prefs.ts).
 *
 * Nothing is captured and no macOS prompt is asked for before consentCurrent() is true (main/features/onboarding.ts).
 */

/** The terms and privacy policy version this build asks the learner to agree to (the date of the text). */
export const CONSENT_VERSION = '2026-11-21'

/** The published terms and privacy policy. Nothing is ever appended to them. */
export const LEGAL_URL = { terms: 'https://miyagi.study/terms', privacy: 'https://miyagi.study/privacy' } as const

/** Who runs miyagi and how to reach them, wherever the app shows a contact (Adrian, Nov 21). */
export const OPERATOR = 'the miyagi team'
export const CONTACT_EMAIL = 'support@miyagi.study'

/** The record of the learner's "By continuing you agree": which version, and when (an ISO 8601 time from main). */
export type Consent = { version: string; at: string }

const VERSION_RE = /^[0-9A-Za-z][0-9A-Za-z._-]{0,31}$/
const MAX_AT = 40

/** A plain copy of a stored or sent record, or undefined when it is missing or malformed (malformed reads as no consent). */
export function cleanConsent(raw: unknown): Consent | undefined {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return undefined
  const r = raw as Record<string, unknown>
  if (typeof r.version !== 'string' || !VERSION_RE.test(r.version)) return undefined
  if (typeof r.at !== 'string' || r.at.length > MAX_AT || Number.isNaN(Date.parse(r.at))) return undefined
  return { version: r.version, at: r.at }
}

/** The learner agreed to this version (an older version, or none, means ask again). */
export function consentCurrent(raw: unknown, version: string = CONSENT_VERSION): boolean {
  return cleanConsent(raw)?.version === version
}

/** The record main writes when the learner continues: this build's version, the time now. */
export function makeConsent(now: Date = new Date(), version: string = CONSENT_VERSION): Consent {
  return { version, at: now.toISOString() }
}
